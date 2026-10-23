#!/usr/bin/env python3
"""语义相似度检索（TF-IDF 字符向量，纯 CPU，零模型，毫秒级）

为什么是这套而不是 embedding:
    本机不提供 embedding 服务、不给 GPU，而语料只有千条级短文本。
    这个规模上，字符 bigram + TF-IDF + 余弦 的检索质量与轻量 embedding 相当，
    但延迟是毫秒而不是百毫秒，且没有冷启动、没有依赖、没有下载。

设计:
    - 中文按字符 2-gram 切分（无需分词器、无词典依赖）
    - 英文/数字按连续片段整词
    - TF-IDF 权重：1+log(tf) × log((1+N)/(1+df))+1
    - 相似候选用倒排索引生成，只算有公共 token 的对 → O(Σ token 的 C(k,2))
    - 只用条目正文，**排除 evidence**：多条目的 evidence 常出自同一句口述，
      带进去会让它们假装相似（实际已踩过一次）

用法:
    python3 scripts/semantic.py "要不要跳槽"        # 检索最相关条目
    python3 scripts/semantic.py --pairs --top 15    # 全库疑似重复/冲突候选
    python3 scripts/semantic.py --bench             # 性能自测
"""

from __future__ import annotations

import argparse
import os
import math
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

# MEMORY_ROOT 环境变量优先：测试与多实例（同一套代码指向不同记忆库）都靠它
ROOT = Path(os.environ.get("MEMORY_ROOT") or Path(__file__).resolve().parent.parent).resolve()
MEM = ROOT / "memory"

ENTRY_RE = re.compile(r"^- \[id:\s*([^\]]+)\]")
FIELD_RE = re.compile(r"\[(\w+):\s*([^\]]*)\]")
EN_RE = re.compile(r"[a-z][a-z0-9+#./]*|\d+(?:[.,]\d+)*")
ZH_SPLIT = re.compile(r"[^\u4e00-\u9fff]+")


_SYN: dict[str, str] = {}


# ============================================================
# 归一的"安全白名单"
# ------------------------------------------------------------
# 教训：把每个词都归一 = 灾难。实测出现
#   「优化 → 裁员」「毕业 → 裁员」「系统 → 操作系统」「平安 → 中国平安」
# 这类映射，任何日常句都会误命中。
#
# 规则：短词（2 字中文 / ≤3 字母英文）默认 **不归一**，只有下列白名单例外。
#   - 两字中文多是日常词，歧义率极高（书/移动/平安/完美/多多/字节/系统/容器…）
#   - 短英文缩写几乎全都多义（PM/GM/BE/FE/DS/MS/ES/TF/Go/Ray/OP/TA…）
# 不归一的词仍可被 bigram 命中——只要文档里出现过同样写法就够了。
# ============================================================
SAFE_ZH2: set[str] = {
    # 专有俗称（只为公司/产品存在，不作他用）
    "鹅厂", "菊厂", "狗家", "果家", "粮厂", "渣浪", "逼乎", "狗东", "节跳",
    "企鹅", "某宝", "小破", "袋鼠", "橙心", "春哥", "弹簧",
    "爪哇", "蟒蛇", "火炬", "萤火", "暗面", "阶跃", "寒武", "昇腾",
    # 关系称谓（语义统一，必须归一无歧）
    "爸爸", "父亲", "老爹", "妈妈", "母亲", "老妈", "老公", "丈夫", "先生",
    "老婆", "媳妇", "妻子", "太太", "爱人", "儿子", "女儿", "孩子", "小孩",
    "宝宝", "爷爷", "奶奶", "外公", "姥爷", "外婆", "姥姥", "哥哥", "弟弟",
    "姐姐", "妹妹", "表哥", "堂哥", "岳父", "岳母", "公公", "婆婆", "大伯",
    "叔叔", "姑姑", "舅舅", "阿姨", "姨妈", "侄子", "侄女", "外甥", "领导",
    "同事", "下属", "本人",
    # 相对时间（记忆系统核心，必须归一）
    "今天", "今日", "昨天", "昨日", "前天", "明天", "后天", "上周", "这周",
    "本周", "下周", "上月", "本月", "下月", "去年", "上年", "今年", "本年",
    "明年", "年初", "年中", "年底", "年末", "上季", "之前", "最近", "近来",
    "刚刚", "刚才", "当初", "当时", "后来", "之后", "一直", "从来", "从没",
    "马上", "立刻", "上礼拜", "下礼拜", "这礼拜",
}

SAFE_EN: set[str] = {
    # 技术/职场里歧义极低的缩写
    "k8s", "crd", "rag", "llm", "okr", "kpi", "sla", "slo", "sre",
    "ceo", "cto", "cfo", "coo", "cpo", "vp", "dba", "ui", "ux", "hr",
    "prd", "etl", "rpc", "vpc", "dns", "ssl", "cdn", "etf", "rsu",
    "mba", "gre", "bmi", "nd", "p+r", "eks", "ecs", "ack", "tke", "cce",
}


def load_synonyms() -> dict[str, str]:
    """三层归一表，优先级由低到高，都映射为 "§xxx" token：
       1. memory/lexicon.md   —— 公共词表（互联网黑话、技术术语、城市简称），**可开源**
       2. memory/_synonyms.md —— 语义概念（工作/薪资/社保…），**可开源**
       3. memory/_aliases.md  —— 私人实体（人名、家庭关系、"我媳妇"），**不进仓库**
    高优先级可覆盖低优先级，因此个人叫法总能盖过公共叫法。
    """
    m: dict[str, str] = {}

    def add(term: str, canon: str, overwrite: bool, source: str = "lexicon") -> None:
        t = re.sub(r"[（(].*?[)）]", "", term).strip().lower()
        if not t or len(t) > 16:
            return
        # 单个汉字（多为代词/虚词）绝不参与归一：把「我」映射成某个实体，
        # 会让所有含「我」的查询塌陷到同一条记忆上。
        if len(t) == 1 and re.match(r"[\u4e00-\u9fff]", t):
            return
        # 短词限制**只针对公共词表**：它收录的是日常词与中英对照，短词歧义高。
        # `_synonyms.md`（语义概念，人工审核）与 `_aliases.md`（私人绑定，只对本人有意义）
        # 不受此限制——"医保→社保""媳妇→配偶"这类归一必须照常生效。
        if source == "lexicon":
            if re.fullmatch(r"[\u4e00-\u9fff]{2}", t) and t not in SAFE_ZH2:
                return
            if re.fullmatch(r"[a-z0-9+#/.]{2,3}", t) and t not in SAFE_EN:
                return
        if overwrite or t not in m:
            m[t] = canon

    public = MEM / "lexicon.md"
    if public.exists():
        for line in public.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or set(line) <= set("|- :"):
                continue
            cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or cells[0].startswith("俗称") or cells[0].startswith("键"):
                continue
            canon = re.sub(r"[（(].*?[)）]", "", cells[1]).strip()
            for part in re.split(r"[/、,，]", cells[0]):
                add(part, canon, overwrite=True, source="lexicon")

    concept = MEM / "_synonyms.md"
    if concept.exists():
        for line in concept.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or set(line) <= set("|- :"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or cells[0] in ("概念",):
                continue
            for term in re.split(r"[/、,，]", cells[1]):
                add(term, cells[0], overwrite=False, source="synonyms")

    priv = MEM / "_aliases.md"
    if priv.exists():
        for line in priv.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or set(line) <= set("|- :"):
                continue
            cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or cells[0] in ("用户口径",) or not cells[1]:
                continue
            canon = re.sub(r"[（(].*?[)）]", "", cells[1]).strip()
            for part in re.split(r"[/、,，]", cells[0]) + [cells[1]]:
                add(part, canon, overwrite=True)
    return m


_SYN_LOADED = False


def tokenize(text: str) -> list[str]:
    """语义归一 + 中文 bigram + 英文数字整词。

    先按同义词表把口语变体替换成「§概念」token（这样「医保」与「五险一金」命中同一维），
    剩下的原文再做 bigram。不做停用词过滤——IDF 会自然降权高频虚词。
    """
    global _SYN_LOADED
    if not _SYN_LOADED:
        _SYN.update(load_synonyms())
        _SYN_LOADED = True
    low = text.lower()
    toks: list[str] = []
    for term in sorted(_SYN, key=len, reverse=True):
        if term in low:
            toks.append("§" + _SYN[term])
            low = low.replace(term, " ")
    toks += [m.group() for m in EN_RE.finditer(low)]
    for seg in ZH_SPLIT.split(low):
        for i in range(len(seg) - 1):
            toks.append(seg[i:i + 2])
    return toks


def parse_docs() -> list[dict]:
    """解析所有 active 条目，只用正文构造检索文本。"""
    docs: list[dict] = []
    for md in sorted(MEM.rglob("*.md")):
        rel = str(md.relative_to(MEM))
        if "timeline" in md.parts or md.name.startswith("_"):
            continue
        text_all = md.read_text(encoding="utf-8")
        mt = re.search(r"^topic:\s*(.+)$", text_all.split("---")[1] if text_all.startswith("---") and len(text_all.split("---")) > 1 else "", re.M)
        file_topic = mt.group(1).strip() if mt else md.stem
        section, cur = None, None
        for line in text_all.splitlines():
            if line.startswith("## current"):
                section, cur = "current", None
                continue
            if line.startswith("## history"):
                section, cur = "history", None
                continue
            if section is None:
                continue
            m = ENTRY_RE.match(line)
            if m:
                cur = {"id": m.group(1), "path": rel, "section": section, "topic": file_topic,
                       "fields": dict(FIELD_RE.findall(line)), "body": []}
                docs.append(cur)
                continue
            if cur is None:
                continue
            s = line.strip()
            if s and not s.startswith(">"):
                cur["body"].append(s)
    return [d for d in docs if d["section"] == "current" and d["body"]]


class Index:
    """倒排索引 + TF-IDF 稀疏向量。"""

    def __init__(self, docs: list[dict]):
        global _SYN, _SYN_LOADED
        _SYN = load_synonyms()
        _SYN_LOADED = True
        self.docs = docs
        self.n = len(docs)
        self.tf: list[Counter] = []
        df: Counter = Counter()
        for d in docs:
            # topic 是人工提炼的字段名，信息密度远高于正文，给 2 倍权重
            c = Counter(tokenize(" ".join(d.get("topic", "") for _ in range(3)) + " " + " ".join(d["body"])))
            self.tf.append(c)
            df.update(c.keys())
        self.idf = {t: math.log((1 + self.n) / (1 + c)) + 1.0 for t, c in df.items()}
        # 倒排 + 向量范数
        self.postings: dict[str, list[tuple[int, float]]] = defaultdict(list)
        self.norm = [0.0] * self.n
        for i, c in enumerate(self.tf):
            for t, cnt in c.items():
                w = (1.0 + math.log(cnt)) * self.idf[t]
                self.postings[t].append((i, w))
                self.norm[i] += w * w
        self.norm = [math.sqrt(x) or 1.0 for x in self.norm]

    # ---------------- 单条查询
    def query(self, text: str, k: int = 5) -> list[tuple[float, dict]]:
        q = Counter(tokenize(text))
        qv = {t: (1.0 + math.log(c)) * self.idf.get(t, self.idf_min()) for t, c in q.items()}
        qn = math.sqrt(sum(w * w for w in qv.values())) or 1.0
        acc: dict[int, float] = defaultdict(float)
        for t, w in qv.items():
            for i, wd in self.postings.get(t, ()):
                acc[i] += w * wd
        # 字段加权：topic 是人工提炼的字段名，命中它比命中正文更有指示性。
        # 这条同时缓解 TF-IDF 的"长文档稀释"——正文越长、实体越杂，单维权重越低，
        # 于是信息最丰富的条目反而排不上去。给 topic 一个与向量范数无关的独立加分。
        q_concepts = {t for t in qv if t.startswith("§")}
        scored = []
        for i, dot in acc.items():
            base = dot / (qn * self.norm[i])
            topic_concepts = {t for t in tokenize(self.docs[i]["topic"]) if t.startswith("§")}
            if q_concepts and topic_concepts:
                overlap = len(q_concepts & topic_concepts) / len(q_concepts)
                base += 0.35 * overlap
            scored.append((base, self.docs[i]))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]

    def idf_min(self) -> float:
        return min(self.idf.values()) if self.idf else 1.0

    # ---------------- 全库两两
    def pairs(self, threshold: float = 0.30) -> list[tuple[float, dict, dict]]:
        acc: dict[tuple[int, int], float] = defaultdict(float)
        for lst in self.postings.values():
            if len(lst) < 2:
                continue
            for (i, wi), (j, wj) in combinations(lst, 2):
                acc[(i, j) if i < j else (j, i)] += wi * wj
        out = []
        for (i, j), dot in acc.items():
            if self.docs[i]["path"] == self.docs[j]["path"]:
                continue
            sim = dot / (self.norm[i] * self.norm[j])
            if sim >= threshold:
                out.append((sim, self.docs[i], self.docs[j]))
        out.sort(key=lambda x: -x[0])
        return out


def load_index() -> Index:
    return Index(parse_docs())


def main() -> int:
    ap = argparse.ArgumentParser(description="语义相似度检索（TF-IDF，零模型）")
    ap.add_argument("text", nargs="?", help="查询文本")
    ap.add_argument("--pairs", action="store_true", help="全库疑似重复/冲突候选对")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--bench", action="store_true", help="性能自测")
    a = ap.parse_args()

    if a.bench:
        import time
        R = 200
        t0 = time.perf_counter()
        idx = load_index()
        t_build = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        for _ in range(R):
            idx.query("要不要跳槽，涨薪机会", k=5)
        t_query = (time.perf_counter() - t1) * 1000 / R
        t2 = time.perf_counter()
        for _ in range(R):
            idx.pairs(0.3)
        t_pairs = (time.perf_counter() - t2) * 1000 / R
        print(f"索引构建 {t_build:.1f} ms ｜ 单次查询 {t_query:.3f} ms（{R} 次均值）｜ 全库两两 {t_pairs:.3f} ms")
        print(f"语料 {idx.n} 条，词典 {len(idx.idf)} token，同义词 {len(_SYN)} 条")
        return 0

    idx = load_index()
    if a.pairs:
        ps = idx.pairs(a.threshold)[: a.top]
        print(f"=== 疑似相关条目对（余弦 ≥ {a.threshold}，前 {len(ps)}）===")
        for sim, x, y in ps:
            print(f"\n{sim:.3f}  {x['id']} ↔ {y['id']}")
            print(f"       {x['path']:34s} {' '.join(x['body'])[:64]}")
            print(f"       {y['path']:34s} {' '.join(y['body'])[:64]}")
        return 0

    if not a.text:
        ap.print_help()
        return 0
    res = idx.query(a.text, a.top)
    if not res or res[0][0] < 0.05:
        print("无相关记录。库里没有覆盖这个主题的条目 —— 不做推断。")
        return 0
    for sim, d in res:
        print(f"{sim:.3f}  {d['id']:14s} {d['path']:34s} {' '.join(d['body'])[:76]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
