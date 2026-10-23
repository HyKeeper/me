#!/usr/bin/env python3
"""记忆库门禁与冲突检测器（只读，不改任何记忆文件）

存在理由:
    "写入前必须 Read 目标文件" 靠自觉执行是不可靠的 —— agent 会忘、会读漏、
    会读到了却没意识到语义冲突。这个脚本把纪律变成可执行的检查：

        python3 scripts/check.py            # 全库校验（体检/收尾用）
        python3 scripts/check.py --pre PATH # 写前检查（§5 第 4 步门禁）

检查分三级:
    ERROR  结构违规，必须修（违反 §8 宪法级规则）
    WARN   疑似冲突/会过期的写法，需人工判断
    INFO   统计与提示

设计原则:
    - 只读。绝不允许写坏 memory/。
    - 规则可加不可删：新增检查就往下加函数，登记进 CHECKS 列表。
    - 领域规则（薪资↔公积金互洽等）单独一组，因为它们是"这个库特有的常识"。
"""

from __future__ import annotations

import argparse
import os
import difflib
import re
import sys
from datetime import date, datetime
from pathlib import Path

# MEMORY_ROOT 环境变量优先：测试与多实例（同一套代码指向不同记忆库）都靠它
ROOT = Path(os.environ.get("MEMORY_ROOT") or Path(__file__).resolve().parent.parent).resolve()
MEM = ROOT / "memory"

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import semantic  # 可选依赖：拿不到就退化为字面匹配
except Exception:  # pragma: no cover
    semantic = None

import memconfig

CFG = memconfig.load()

ENTRY_RE = re.compile(r"^- \[id:\s*([^\]]+)\]")
FIELD_RE = re.compile(r"\[(\w+):\s*([^\]]*)\]")
REF_RE = re.compile(r"`?([a-z][a-z-]*-\d{3})`?")
TIME_OK = re.compile(r"^(~?\d{4}(?:-\d{2})?(?:-\d{2})?|<= \d{4}-\d{2}-\d{2}|unknown)$")
TS_OK = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00$")
TIME_FIELDS = ("spoken_at", "valid_from", "recorded_at")
VAGUE_WORDS = re.compile(r"满额|不错|挺好|偏低|压力大|还行|一般般|差不多")

# 硬编码派生值：算出来的数写死进库，时间一过就变成错误信息
DERIVED_PATTERNS = [
    (re.compile(r"\d+\s*岁"), "年龄"),
    (re.compile(r"工龄\s*\d+\s*年"), "工龄"),
    (re.compile(r"距今\s*\d+\s*[天月年]"), "距今时长"),
    (re.compile(r"截至\s*recorded_at\s*为\s*\d+"), "按写入时点计算的量"),
]


# --------------------------------------------------------------- 解析
def parse_all() -> tuple[list[dict], list[str]]:
    """返回 (所有条目, 结构问题)。条目含 section=current/history。"""
    items: list[dict] = []
    problems: list[str] = []
    for md in sorted(MEM.rglob("*.md")):
        rel = str(md.relative_to(MEM))
        if "timeline" in md.parts or md.name.startswith("_"):
            continue
        section = None
        cur = None
        for line in md.read_text(encoding="utf-8").splitlines():
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
                cur = {
                    "id": m.group(1),
                    "path": rel,
                    "section": section,
                    "fields": dict(FIELD_RE.findall(line)),
                    "body": [],
                    "notes": [],
                }
                items.append(cur)
                continue
            if cur is None:
                continue
            s = line.strip()
            if not s:
                continue
            if s.startswith(">"):
                cur["notes"].append(s.lstrip(">").strip())
            else:
                cur["body"].append(s)
    return items, problems


def text_of(e: dict) -> str:
    return " ".join(e["body"]) + " " + " ".join(e["notes"])


def nums(s: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", s)]


# --------------------------------------------------------------- 结构规则
def check_structure(items: list[dict]) -> list[tuple[str, str, str]]:
    out = []
    by_file: dict[str, list[dict]] = {}
    for e in items:
        by_file.setdefault(e["path"], []).append(e)

    for path, es in by_file.items():
        actives = [e for e in es if e["section"] == "current"]
        if len(actives) != 1:
            out.append(("ERROR", path, f"current 区有 {len(actives)} 条 active，违反 §8.4（必须恰好 1 条）"))

    seen: dict[str, str] = {}
    for e in items:
        if e["id"] in seen:
            out.append(("ERROR", e["path"], f"id 重复：{e['id']}（另一处在 {seen[e['id']]}）"))
        seen[e["id"]] = e["path"]

    for e in items:
        f = e["fields"]
        # spoken_at / recorded_at 是完整时间戳；valid_from / valid_until 是日期或四档语法
        for k in ("spoken_at", "recorded_at"):
            if k not in f:
                out.append(("ERROR", e["path"], f"{e['id']} 缺必填时间字段 {k}（§8.3）"))
            elif not TS_OK.match(f[k].strip()):
                out.append(("ERROR", e["path"], f"{e['id']} 的 {k}='{f[k]}' 不是合法 ISO 时间戳（需 +08:00）"))
        if "valid_from" not in f:
            out.append(("ERROR", e["path"], f"{e['id']} 缺必填时间字段 valid_from（§8.3）"))
        for k in ("valid_from", "valid_until"):
            if k in f and not TIME_OK.match(f[k].strip()):
                out.append(("ERROR", e["path"], f"{e['id']} 的 {k}='{f[k]}' 不符合四档语法（§3）"))
        if not any(n.lower().startswith("evidence:") for n in e["notes"]):
            out.append(("ERROR", e["path"], f"{e['id']} 缺 evidence（§8.6）"))
        vf, vu = f.get("valid_from", ""), f.get("valid_until", "")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", vf) and re.match(r"^\d{4}-\d{2}-\d{2}$", vu):
            if vf > vu:
                out.append(("ERROR", e["path"], f"{e['id']} valid_from({vf}) 晚于 valid_until({vu})"))
        if re.match(r"^\d{4}-\d{2}-\d{2}$", vf) and vf > date.today().isoformat():
            out.append(("WARN", e["path"], f"{e['id']} valid_from({vf}) 在未来，确认是预期生效日而非笔误"))

    ids = {e["id"] for e in items}
    for e in items:
        for ref in set(REF_RE.findall(text_of(e))):
            if ref not in ids and ref.split("-")[0] not in ("uuid",):
                out.append(("WARN", e["path"], f"{e['id']} 引用了不存在的条目 {ref}（悬空引用）"))
    return out


# --------------------------------------------------------------- 内容规则
def check_content(items: list[dict]) -> list[tuple[str, str, str]]:
    out = []
    today = date.today()
    for e in items:
        if e["section"] != "current":  # history 条目是存档，不参与当前性检查
            continue
        t = text_of(e)
        body = " ".join(e["body"])
        f = e["fields"]
        if f.get("valid_from") == "unknown":
            out.append(("WARN", e["path"], f"{e['id']} valid_from=unknown，历史查询不可用；考虑改 <= {today.isoformat()}"))
        for pat, name in DERIVED_PATTERNS:
            if pat.search(body):
                out.append(("ERROR", e["path"], f"{e['id']} 写死了派生值（{name}）：{pat.pattern} —— 时间一过即错，见 §3.4"))
        if VAGUE_WORDS.search(body) and f.get("vague") not in ("true", "resolved"):
            m = VAGUE_WORDS.search(body)
            out.append(("WARN", e["path"], f"{e['id']} 含定性词「{m.group(0)}」且未标 [vague: true]，无法参与计算"))
        vu = f.get("valid_until")
        if vu and re.match(r"^\d{4}-\d{2}-\d{2}$", vu) and date.fromisoformat(vu) < today:
            out.append(("ERROR", e["path"], f"{e['id']} 已于 {vu} 过期仍在 current 区，外部参数会算错"))
    return out


def check_topic_overlap(items: list[dict]) -> list[tuple[str, str, str]]:
    """同目录内 topic 高度相似的两个文件 = 可能重复记录同一属性。"""
    out = []
    by_dir: dict[str, list[tuple[str, str]]] = {}
    for md in sorted(MEM.rglob("*.md")):
        if "timeline" in md.parts or md.name.startswith("_"):
            continue
        head = md.read_text(encoding="utf-8").split("\n---", 1)[0]
        m = re.search(r"^topic:\s*(.+)$", head, re.M)
        topic = m.group(1).strip() if m else md.stem
        by_dir.setdefault(str(md.parent), []).append((md.stem, topic))
    for d, pairs in by_dir.items():
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                ratio = difflib.SequenceMatcher(None, pairs[i][1], pairs[j][1]).ratio()
                if ratio > 0.7:
                    out.append(("WARN", str(Path(d).relative_to(MEM)), f"topic 相似度 {ratio:.0%}：{pairs[i]} vs {pairs[j]}，疑似同一属性两条记录"))
    return out


# --------------------------------------------------------------- 领域规则（本库特有常识）
def check_payroll(items: list[dict]) -> list[tuple[str, str, str]]:
    """薪资 ↔ 公积金 互洽：反推的缴存基数不能超过工资，且必须落在政策档位上。"""
    out = []
    if not memconfig.get_bool(CFG, "payroll_enabled"):
        return out
    sid, fid, pid = CFG["payroll_salary_id"], CFG["payroll_fund_id"], CFG["payroll_param_id"]
    if not (sid and fid and pid):
        return out
    salary_e = next((e for e in items if e["id"] == sid), None)
    hf_e = next((e for e in items if e["id"] == fid), None)
    param_e = next((e for e in items if e["id"] == pid), None)
    if not (salary_e and hf_e and param_e):
        return out

    def grab(entry: dict, pattern: str) -> float | None:
        m = re.search(pattern, " ".join(entry["body"]))
        return float(m.group(1).replace(",", "")) if m else None

    salary = grab(salary_e, r"月薪\s*([\d,]+)")
    total = grab(hf_e, r"月缴存额\s*([\d,]+)")
    cap = grab(param_e, r"基数上限\s*\**([\d,]+)")
    if not (salary and total and cap):
        out.append(("WARN", "check.py/payroll", f"无法解析薪资/公积金/上限数值（salary={salary}, total={total}, cap={cap}），跳过互洽校验"))
        return out
    matched = [r for r in (0.05, 0.09, 0.10, 0.11, 0.12)
               if abs(min(salary, cap) * r * 2 - total) < 2]
    if not matched:
        out.append(("ERROR", "work/salary.md ↔ work/housing-fund.md",
                    f"工资 {salary:.0f} 与公积金合计 {total:.0f} 不自洽：按上限 {cap:.0f} 反推无匹配比例档"))
    else:
        base = min(salary, cap)
        out.append(("INFO", "work/salary.md ↔ work/housing-fund.md",
                    f"互洽通过：比例 {matched[-1]*100:.0f}%，基数 {base:.0f}（工资 {salary:.0f}，上限 {cap:.0f}）"))
    return out


def check_age_drift(items: list[dict]) -> list[tuple[str, str, str]]:
    """出生日期与任何写死的年龄必然对不上（时间流逝导致）。"""
    out = []
    b = next((e for e in items if CFG["birth_id_keyword"] in e["id"]), None)
    if not b:
        return out
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", b["fields"].get("valid_from", ""))
    if not m:
        return out
    by, bm, bd = map(int, m.groups())
    today = date.today()
    real_age = today.year - by - ((today.month, today.day) < (bm, bd))
    for e in items:
        for mm in re.finditer(r"(\d+)\s*岁", " ".join(e["body"])):
            stated = int(mm.group(1))
            if stated != real_age:
                out.append(("ERROR", e["path"], f"{e['id']} 写死 {stated} 岁，实际今天 {real_age} 岁 —— 派生值漂移"))
    return out


def check_timeline(items: list[dict]) -> list[tuple[str, str, str]]:
    """时间线格式与顺序。append-only 不代表可以接受损坏的行。"""
    out = []
    p = MEM / "timeline" / "events.md"
    if not p.exists():
        return out
    prev = None
    for n, l in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
        st = l.strip()
        if not st or st.startswith("#") or st.startswith(">"):
            continue
        m = re.match(r"^- (\d{4}-\d{2}(?:-\d{2})?)\s+\[", l)
        if not m:
            out.append(("ERROR", "timeline/events.md", f"第 {n} 行格式非法（应为 '- YYYY-MM  [id] 类型：内容'）：{l[:44]!r}"))
            continue
        d = m.group(1)
        if prev and d < prev:
            out.append(("ERROR", "timeline/events.md", f"第 {n} 行时间乱序：{prev} → {d}"))
        prev = d
    return out


def check_semantic_overlap(items: list[dict]) -> list[tuple[str, str, str]]:
    """语义高度重合的条目对。相似≠冲突，所以只报 INFO，由 agent 判断是否重复描述。"""
    if semantic is None:
        return [("WARN", "check.py", "semantic 模块不可用，语义重合检查已跳过")]
    if not memconfig.get_bool(CFG, "semantic_enabled"):
        return out
    try:
        idx = semantic.Index(semantic.parse_docs())
        ps = idx.pairs(memconfig.get_float(CFG, "semantic_threshold"))[:5]
    except Exception as exc:
        return [("WARN", "check.py", f"语义检查失败：{exc}")]
    return [("INFO", f"{a['id']} ↔ {b['id']}",
             f"语义重合 {sim:.2f}（{a['path']} / {b['path']}）—— 相关不等于冲突，确认是否重复描述同一属性")
            for sim, a, b in ps]


def load_alias_groups() -> list[set[str]]:
    """从 memory/_aliases.md 抽取别名组（同一行的前两列 = 同一实体的不同叫法）。"""
    p = MEM / "_aliases.md"
    if not p.exists():
        return []
    groups: list[set[str]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or set(line) <= set("|- :"):
            continue
        cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("用户口径",):
            continue
        grp: set[str] = set()
        for c in cells[:2]:
            for part in re.split(r"[/、,，]", c):
                part = re.sub(r"[（(].*?[)）]", "", part).strip()
                if part and len(part) <= 16:
                    grp.add(part)
        if len(grp) >= 1:
            groups.append(grp)
    return groups


def check_entity_coverage(items: list[dict]) -> list[tuple[str, str, str]]:
    """别名表里登记过的实体，必须真的出现在记忆里。

    别名表的本意是检索，这里把它反用成"实体清单"：
    登记了却没写，说明遗漏；写到了却没登记，说明将来检索不到。
    """
    out = []
    groups = load_alias_groups()
    if not groups:
        return out
    corpus = " ".join(text_of(e) for e in items).lower()
    for grp in groups:
        if any(t.lower() in corpus for t in grp):
            continue  # 组内任一叫法出现过即可，别名本来就是同物异名
        shown = " / ".join(sorted(grp))
        out.append(("WARN", "_aliases.md", f"别名组「{shown}」登记的实体在记忆里一条都没有 —— 或删别名，或补事实"))
    return out


def check_location_pairs(items: list[dict]) -> list[tuple[str, str, str]]:
    """工作地与居住/房产同时存在时，必须补通勤参数。

    这是本轮教训的固化：拿到「雇主 + 居住地」，就该算出通勤耗时，而不是留空。
    不给这一步，"他有房在公司附近吗"这类问题永远答不出。
    """
    out = []
    cur = [e for e in items if e["section"] == "current"]
    has_employer = any(e["path"].startswith("work/employer") or "employer" in e["path"] for e in cur)
    has_home = any(re.search(r"location|房产|house|address|住址", e["path"]) for e in cur)
    has_geo = any(e["path"].startswith("misc/") and re.search(r"地理|geo|通勤|commute", e["path"]) for e in cur)
    if has_employer and has_home and not has_geo:
        out.append(("WARN", "逻辑关联", "同时存在「雇主」与「居住地/房产」，但没有通勤或地理距离参数（§3.3）—— 追问或补查，别让这两条各说各话"))
    return out


def check_public_gap(items: list[dict]) -> list[tuple[str, str, str]]:
    """留空的若是「具体可查属性」，就该自己查，不该标"未说明"。

    只认具体属性词（办公地点/地址/政策/上限/比例/学区…），不认"平台/产品"这类泛词——
    泛词会把它变成噪音，而噪音会让整条规则被忽略。
    外部事实条目自身（misc/、*office*、*geo*）不参与，避免自我循环误报。
    """
    out = []
    ATTR = re.compile(r"办公地点|办公地址|地址|所在地|位于|地理位置|"
                      r"政策|规定|上限|缴存基数|缴存比例|费率|税率|学区|"
                      r"市价|均价|行情|办公点")
    UNK = re.compile(r"未说明|未知|未提及|未给|不清楚|不详|未查|未核实")
    SKIP = re.compile(r"config|_aliases|_synonyms")
    for e in items:
        if e["section"] != "current":
            continue
        if re.search(r"misc/|office|geo|_", e["path"]) or SKIP.search(e["id"]):
            continue
        body = " ".join(e["body"])
        for m in UNK.finditer(body):
            window = body[max(0, m.start() - 50): m.end() + 14]
            hit = ATTR.search(window)
            if hit:
                out.append(("WARN", e["path"],
                            f"{e['id']} 留空了可查属性「{hit.group(0)}」→ 先查证再落笔（§3.3）：…{window.strip()[:44]}…"))
                break
    return out


def check_bloat(items: list[dict]) -> list[tuple[str, str, str]]:
    """单条记忆臃肿：正文过长，或 clarification 层层叠加变成变更日志。

    一条记忆的职责是"描述当前状态"，不是"记录我是怎么改过来的"——后者属于 timeline。
    """
    out = []
    for e in items:
        if e["section"] != "current":
            continue
        n = len(" ".join(e["body"]))
        if n > 1200:
            out.append(("WARN", e["path"], f"{e['id']} 正文 {n} 字符过于臃肿 —— 拆分，或把细节移到 notes / 独立条目"))
        clar = sum(1 for x in e["notes"] if x.lower().startswith("clarification:"))
        if clar >= 3:
            out.append(("WARN", e["path"], f"{e['id']} 累积 {clar} 次 clarification —— 应把澄清内容并入主描述（变更史留在 timeline）"))
    return out



# ---------- 术语同一性与证据忠实性（2026-10-23 新增）----------
# 存在理由: 断言句里混入了原话没有的技术名词，并据此推翻了已校准的裁决。
# 这类错误无法靠"感到不确定时去查"来防（我不会感到不确定），只能靠机械判据。

# 断言性推断动词：出现即说明 agent 在"从 A 推出 B"。
# 刻意收窄——只放强断言词，"反推/推断/推测"这类不算，否则误报会淹没规则。
INFER_MARKERS = re.compile(
    r"直指|即可证明|足以说明|充分说明|说明其具备|表明其具备|因此具备|可作为.{0,8}的证据|这是.{0,6}能力的证据"
)

# 会被"自行添加"的典型技术名词。只收容易跨语境搬运的词。
TECH_TERM_RE = re.compile(
    r"(?<![A-Za-z])(?:K8s|Kubernetes|Istio|Envoy|CRD|CRDs|HPA|QPS|GPU|CPU|Ray|Milvus|BM25|"
    r"Sidecar|OpenVINO|Coscheduling|Pod|PodGroup|scheduler-plugins|binpack|spread|vLLM|OpenRLHF|"
    r"Prometheus|Grafana|Deployment|CloneSet|Rollout)(?![A-Za-z])"
)

TEAM_RE = re.compile(r"团队|赛队|组队|个人赛|团体|单人|联合赛队")
AWARD_RE = re.compile(r"竞赛|大赛|比赛|季军|亚军|冠军|获奖|名次|排名")


def _evidence_text(e: dict) -> str:
    """取条目里 > evidence: 开头的注释行，拼成一串。没有就返回空串。"""
    return " ".join(n for n in e["notes"] if n.lower().startswith("evidence"))


def check_evidence_fidelity(items: list[dict]) -> list[tuple[str, str, str]]:
    """推断句中出现了 evidence 原文没有的技术名词 → WARN。

    误报边界：只有在「含强断言动词的句子」里才查，且 §3.3 允许外部补全，
    所以这永远是 WARN 而非 ERROR——要求人工确认来源，而不是禁止。
    """
    out: list[tuple[str, str, str]] = []
    for e in items:
        if e["section"] != "current":
            continue
        ev = _evidence_text(e)
        if not ev:
            continue
        body = " ".join(e["body"])
        seen: set[str] = set()
        for sent in re.split(r"[。；\n]", body):
            if not INFER_MARKERS.search(sent):
                continue
            for term in TECH_TERM_RE.findall(sent):
                if term in ev or term in seen:
                    continue
                seen.add(term)
                out.append((
                    "WARN", e["path"],
                    f"{e['id']} 断言句出现 evidence 未载的技术名词「{term}」——"
                    f"原话里没有它，确认是外部补全（须标来源）还是自行添加",
                ))
    return out


def load_ambiguous_terms() -> list[str]:
    """从 memory/_ambiguous-terms.md 的表格里取所有加粗的词条。"""
    f = MEM / "_ambiguous-terms.md"
    if not f.exists():
        return []
    terms = []
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*\*\*(.+?)\*\*\s*\|", line)
        if m:
            terms.append(m.group(1).strip())
    return terms


def check_term_homonym(items: list[dict]) -> list[tuple[str, str, str]]:
    """歧义词出现在断言句中且未标 [term: <义项>] → WARN。

    memory/_ambiguous-terms.md 里的词跨语境复用（调度/优化/平台/系统…），
    同一个词不等于同一个技术。断言时必须显式写明义项。
    """
    terms = load_ambiguous_terms()
    if not terms:
        return []
    out: list[tuple[str, str, str]] = []
    for e in items:
        if e["section"] != "current":
            continue
        if "term" in e["fields"]:          # 已显式标注义项，放行
            continue
        body = " ".join(e["body"])
        for sent in re.split(r"[。；\n]", body):
            if not INFER_MARKERS.search(sent):
                continue
            for t in terms:
                if t in sent:
                    out.append((
                        "WARN", e["path"],
                        f"{e['id']} 断言句含歧义词「{t}」但未标 [term: <义项>]——"
                        f"见 memory/_ambiguous-terms.md",
                    ))
                    break
    return out


def check_award_team(items: list[dict]) -> list[tuple[str, str, str]]:
    """记录竞赛/奖项却没标明团队赛还是个人赛 → WARN。

    成因: 竞赛类奖项常为组队赛，名次是团队成绩、个人贡献度未知——
    但很容易被直接当成个人能力证据。
    """
    out: list[tuple[str, str, str]] = []
    for e in items:
        if e["section"] != "current":
            continue
        txt = text_of(e)
        if AWARD_RE.search(txt) and not TEAM_RE.search(txt):
            out.append((
                "WARN", e["path"],
                f"{e['id']} 提到竞赛/奖项但未标明团队赛还是个人赛——名次的个人含义完全不同",
            ))
    return out



# ---------- 代码层隐私（2026-10-23 新增）----------
# 存在理由: .gitignore 把 memory/** 全部排除，宣称"个人数据永不入库"，
# 但代码里的注释、示例、默认参数值、测试 fixture 仍然带着真实姓名、雇主、
# 住址与薪资——等于把个人信息从数据层搬到了代码层。本规则把这条边界变成检查。
#
# 词表**不写在代码里**（否则检查器自己就是泄露源），而是从
# memory/_pii-terms.md 读取——该文件不在 .gitignore 白名单内，永不提交。
# 开源用户没有这个文件时，规则自动跳过。

# 扫描范围用「默认全查、私有豁免」，而不是「手写一份公开名单」。
# 理由（2026-10-23 踩过）：手写公开名单时漏掉了整个 ops/，
# 而那正是记录"如何思考这个人的一生"的地方——范围错了，规则再对也白搭。
SCAN_EXTS = {".py", ".md", ".toml", ".json", ".yaml", ".yml"}
PRIVATE_DIRS = ("memory", "ops")
# 私有目录下仍然会开源的文件（须与 .gitignore 白名单保持一致）
PRIVATE_EXCEPT = {
    "_config.example.md", "_aliases.example.md", "_synonyms.md",
    "lexicon.md", "export-spec.md",
}
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv"}
PII_TERMS_FILE = "_pii-terms.md"


def load_pii_terms() -> list[str]:
    """从私有词表读取要禁的字符串。空行与 # 开头视为注释。"""
    f = MEM / PII_TERMS_FILE
    if not f.exists():
        return []
    terms: list[str] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#") or t.startswith(">"):
            continue
        terms.append(t)
    return terms


def check_pii_in_code(items: list[dict]) -> list[tuple[str, str, str]]:
    """代码文件里出现隐私词表中的词 → ERROR。

    这条不看 items（它是条目检查器），直接扫源码目录。
    之所以定为 ERROR 而不是 WARN：代码是要开源的，误报成本远低于泄露成本；
    确需出现的场合（比如本规则自己的词表名）用 NOQA 注释显式豁免。
    """
    terms = load_pii_terms()
    if not terms:
        return []
    targets: list[Path] = []
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file() or f.suffix not in SCAN_EXTS:
            continue
        if SKIP_DIRS & set(f.parts):
            continue
        rel = f.relative_to(ROOT)
        if rel.parts and rel.parts[0] in PRIVATE_DIRS and f.name not in PRIVATE_EXCEPT:
            continue                      # 私有数据，不进仓库，不必扫
        if f.name == PII_TERMS_FILE:
            continue                      # 词表本身含这些词，豁免（它也不入库）
        if f.name.startswith("export-") and f.suffix == ".md":
            continue                      # 导出物是完整人身档案，由 .gitignore 排除
        targets.append(f)

    out: list[tuple[str, str, str]] = []
    for f in targets:
        rel = str(f.relative_to(ROOT))
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "NOQA" in line:
                continue
            for t in terms:
                if t in line:
                    out.append((
                        "ERROR", rel,
                        f"第 {i} 行含隐私词「{t}」——该文件会开源，改用抽象占位",
                    ))
                    break
    return out



# ---------- 隐私边界完整性（2026-10-23 新增）----------
# 存在理由: .gitignore 的旧写法用 `dir/**` 全排除、再 `!dir/**/` 把目录捞回来。
# 实测三个后果：
#   1. `!memory/**/.gitkeep` 会让 people/ 下的子目录名（真实姓名）进入仓库
#   2. 只守 memory/ 一层时，ops/ 整片裸露——lessons、open-questions、audits
#      里全是个人细节，而 .gitignore 顶部还写着"个人数据永不入库"
#   3. 这种"先排除再捞回"的写法很难推理，改动一次就可能悄悄放开一片
# 本规则防的是边界被无意削弱，而不是边界内容本身。

GITIGNORE_MUST = {
    "memory/": ("memory/*", "memory/**"),
    "ops/": ("ops/*", "ops/**"),
}
# 这些写法会把"目录结构"放回仓库，而 people/ 下的目录名就是真实姓名
GITIGNORE_FORBIDDEN = ("!memory/**", "!ops/**")


def check_gitignore_boundary(items: list[dict]) -> list[tuple[str, str, str]]:
    """隐私目录必须被 .gitignore 覆盖，且不得用通配白名单把目录结构捞回来。"""
    g = ROOT / ".gitignore"
    if not g.exists():
        return [("ERROR", ".gitignore", "文件缺失——隐私边界不存在")]
    lines = [ln.strip() for ln in g.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]

    out: list[tuple[str, str, str]] = []
    for d, pats in GITIGNORE_MUST.items():
        if not any(pt in lines for pt in pats):
            out.append((
                "ERROR", ".gitignore",
                f"缺少对 {d} 的排除规则（需 {' 或 '.join(pats)}）——该目录会整片进入仓库",
            ))
    for bad in GITIGNORE_FORBIDDEN:
        for ln in lines:
            if ln.startswith(bad) and not ln.endswith((".example.md", ".gitkeep")):
                out.append((
                    "WARN", ".gitignore",
                    f"「{ln}」用通配白名单放回目录内容——people/ 下的目录名就是真实姓名，确认是有意为之",
                ))
                break
    return out


CHECKS = [check_structure, check_content, check_topic_overlap, check_payroll, check_age_drift, check_timeline, check_semantic_overlap, check_entity_coverage, check_bloat, check_location_pairs, check_public_gap, check_evidence_fidelity, check_term_homonym, check_award_team, check_pii_in_code, check_gitignore_boundary]


# --------------------------------------------------------------- 写前模式
def get_topic(rel: str) -> str:
    p = MEM / rel
    if not p.exists():
        return Path(rel).stem
    parts = p.read_text(encoding="utf-8").split("---")
    head = parts[1] if len(parts) > 1 else ""
    m = re.search(r"^topic:\s*(.+)$", head, re.M)
    return m.group(1).strip() if m else Path(rel).stem


def pre_check_text(text: str) -> int:
    if semantic is None:
        print("semantic 模块不可用")
        return 0
    idx = semantic.Index(semantic.parse_docs())
    res = idx.query(text, k=8)
    if not res or res[0][0] < 0.05:
        print("  无相关记录。可能是：① 库里确实没这条事实（真空层）")
        print("               ② 你的用词没有被 memory/_synonyms.md 里的概念覆盖 —— 加一行同义词即可。")
        print("  不做推断。")
        return 0
    for score, d in res:
        print(f"  · {score:.3f} {d['id']:14s} {d['path']:32s} {' '.join(d['body'])[:50]}")
    return 0


def pre_check(path: str, text: str | None = None) -> int:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / path if path.startswith("memory/") else MEM / path
    print(f"=== 写前检查 {p.relative_to(ROOT) if p.is_absolute() and ROOT in p.parents else p} ===")
    if not p.exists():
        print("目标文件不存在 → current 区为空，可写 NEW。")
    else:
        body = p.read_text(encoding="utf-8")
        actives = len(re.findall(r"^- \[id:", body.split("## history")[0], re.M))
        print(f"目标文件已存在 → current 区现有 {actives} 条 active（必须为 1，写入后仍须为 1）")
        print("--- 现有内容 ---")
        print(body.split("## history")[0].strip())
        print("---")
    stem = p.stem
    head = p.read_text(encoding="utf-8") if p.exists() else ""
    topic = (re.search(r"^topic:\s*(.+)$", head, re.M) or [None, stem])[1]
    # 检索文本：用户将写入的事实摘要 > 现有正文 + topic > 路径名
    q = (text or "").strip()
    if not q:
        q = topic + " " + " ".join(head.split("## current")[-1].split("## history")[0].split()) if p.exists() else topic + " " + stem.replace("-", " ")
    print("可能相关的条目（写入前请逐个 Read，判断 DUP/CLARIFY/SUPERSEDE/CONFLICT）：")
    self_path = str(p.relative_to(MEM)) if p.is_absolute() and MEM in p.parents else ""
    shown = 0
    if semantic is not None:
        try:
            idx = semantic.Index(semantic.parse_docs())
            for score, d in idx.query(q, k=8):
                if d["path"] == self_path:
                    continue
                print(f"  · {score:.3f} {d['id']:14s} {d['path']:32s} {' '.join(d['body'])[:44]}")
                shown += 1
        except Exception as exc:
            print(f"  （语义检索失败：{exc}，退化为字面匹配）")
    if shown == 0:
        print("  （无相关条目，可为全新属性；仍建议看一眼同目录）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="记忆库门禁与冲突检测（只读）")
    ap.add_argument("--pre", metavar="PATH", help="写前检查模式：检查目标文件及其潜在冲突")
    ap.add_argument("--pre-text", metavar="TEXT", dest="pre_text", help="写前语义检索：直接给出将要写入的事实摘要")
    args = ap.parse_args()
    if args.pre_text:
        print("=== 写前语义检索 ===")
        return pre_check_text(args.pre_text)
    if args.pre:
        return pre_check(args.pre)

    items, _ = parse_all()
    results: list[tuple[str, str, str]] = []
    for fn in CHECKS:
        try:
            results.extend(fn(items))
        except Exception as exc:  # 规则本身出错不能静默
            results.append(("ERROR", "check.py", f"规则 {fn.__name__} 崩溃：{exc}"))

    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    results.sort(key=lambda r: order[r[0]])
    print(f"=== 全库校验 {datetime.now().astimezone().isoformat(timespec='seconds')} ===")
    print(f"active 条目 {sum(1 for e in items if e['section']=='current')} 条 / 文件 {len({e['path'] for e in items})} 个\n")
    for level, where, msg in results:
        print(f"[{level:5s}] {where:42s} {msg}")
    n_err = sum(1 for r in results if r[0] == "ERROR")
    n_warn = sum(1 for r in results if r[0] == "WARN")
    print(f"\n合计：{n_err} ERROR / {n_warn} WARN")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
