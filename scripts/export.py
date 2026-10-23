#!/usr/bin/env python3
"""生成 AI 化个人档案导出物（AGENTS.md §11.2 / ops/export-spec.md）

只读 memory/，写出 export-YYYY-MM-DD.md，并打印覆盖度摘要。
幂等：同一份记忆库重复运行，除生成时间戳外输出完全一致。

设计要点:
    1. 十层分层靠规则，不靠人记 —— 规则写在 layer_of()，可审计、可改。
    2. 第 8 层「语言指纹」只从 evidence 里的用户原话反向统计，不虚构。
    3. 第 9 层「已知空洞」全部由检测得出，agent 无法选择性遗忘。
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

# MEMORY_ROOT 环境变量优先：测试与多实例（同一套代码指向不同记忆库）都靠它
ROOT = Path(os.environ.get("MEMORY_ROOT") or Path(__file__).resolve().parent.parent).resolve()
MEM = ROOT / "memory"

ENTRY_RE = re.compile(r"^- \[id:\s*([^\]]+)\]")
FIELD_RE = re.compile(r"\[(\w+):\s*([^\]]*)\]")
QUOTE_RE = re.compile(r'"([^"]{2,})"')
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")

LAYER_NAMES = {
    1: "身份锚点", 2: "决策函数", 3: "红线与雷区", 4: "资源与约束", 5: "关系网络",
    6: "时间结构", 7: "目标与进度", 8: "语言指纹", 9: "已知空洞", 10: "事实附注",
}
import memconfig

CFG = memconfig.load()
SELF_DIR = CFG["self_dir"]        # 本人目录名，来自 memory/_config.md
BIRTH_KEY = CFG["birth_id_keyword"]


# ---------------------------------------------------------------- 解析
def layer_of(rel: str, name: str, body_hint: str) -> int:
    """把一条记忆归到十层之一。规则集中在这里，改分层只改这个函数。"""
    p = rel.replace("\\", "/")
    stem = Path(p).stem
    if p.startswith("preferences/"):
        return 3 if re.search(r"红线|雷区|禁|不做|绝不|red.?line|constraint", stem + body_hint[:60]) else 2
    if p.startswith("people/"):
        if re.search(r"作息|通勤|一周|schedule|commute", stem):
            return 6
        seg = p.split("/")
        return 1 if len(seg) >= 3 and seg[1] == SELF_DIR else 5
    if p.startswith("work/"):
        if re.search(r"employer|role", stem):
            return 1
        return 6 if re.search(r"通勤|作息|schedule", stem) else 4
    if p.startswith("assets/"):
        return 4
    if p.startswith("health/"):
        return 4
    if p.startswith("projects/"):
        return 7
    if p.startswith("misc/") and re.search(r"参数|税率|汇率|基准", stem):
        return 4
    return 6 if re.search(r"作息|通勤|schedule|一周", stem) else 10


def parse_entries() -> list[dict]:
    entries: list[dict] = []
    for md in sorted(MEM.rglob("*.md")):
        rel = str(md.relative_to(MEM))
        if "timeline" in md.parts or md.name.startswith("_"):
            continue
        cur, in_cur = None, False
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("## current"):
                in_cur, cur = True, None
                continue
            if line.startswith("## history"):
                in_cur, cur = False, None
                continue
            if not in_cur:
                continue
            m = ENTRY_RE.match(line)
            if m:
                cur = {
                    "id": m.group(1),
                    "fields": dict(FIELD_RE.findall(line)),
                    "body": [],
                    "notes": [],
                    "path": rel,
                }
                cur["layer"] = layer_of(rel, m.group(1), " ".join(cur["body"]) + line)
                entries.append(cur)
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
    return entries


# ---------------------------------------------------------------- 语言指纹
def voice_fingerprint(entries: list[dict]) -> tuple[dict, list[str]]:
    quotes: list[str] = []
    for e in entries:
        for n in e["notes"]:
            low = n.lower()
            if low.startswith("evidence:") or low.startswith("clarification:"):
                quotes += QUOTE_RE.findall(n)
    if not quotes:
        return {"n": 0}, []

    blob = "".join(quotes)
    stats = {
        "n": len(quotes),
        "chars": sum(len(q) for q in quotes),
        "avg": round(sum(len(q) for q in quotes) / len(quotes), 1),
        "period": blob.count("。"),
        "comma": blob.count("，"),
        "comma_ascii": blob.count(","),
        "emoji": len(EMOJI_RE.findall(blob)),
        "mixed_case": bool(re.search(r"[\u4e00-\u9fff][A-Za-z]|[A-Za-z][\u4e00-\u9fff]", blob)),
        "space_before_punct": bool(re.search(r"\s[，。！？]", blob)),
        "digit_month": bool(re.search(r"20\d{2}\.\d{1,2}", blob)),
        "space_count": blob.count(" "),
    }

    obs: list[str] = []
    if stats["avg"] >= 40:
        obs.append(f"句子偏长：{stats['n']} 条原话平均 {stats['avg']} 字符，一次说完整件事而不是分条补充。")
    if stats["period"] == 0 and stats["n"] >= 3:
        obs.append("**几乎不用句号**：所有原话里 0 个「。」——断句靠逗号和空格，转写他的话时不该给他加句号。")
    if stats["comma"] >= stats["n"]:
        obs.append(f"逗号密度 {stats['comma']} 个 / {stats['n']} 条，习惯用逗号串多个信息点。")
    if stats["mixed_case"]:
        obs.append("中英混用不求分隔：如「在北京的shopee」，中文与英文之间不加空格。")
    if stats["space_before_punct"]:
        obs.append("**标点前有空格**（「shopee ，我是」）—— 这是打字节奏造成的，不是笔误；模仿他打字时应保留。")
    if stats["digit_month"]:
        obs.append("月份用点号书写（「2022.4月」），不用「四月」或「2022-04」。")
    if stats["emoji"] == 0:
        obs.append("不用 emoji。")
    if not obs:
        obs.append("样本量不足，暂无法提炼稳定特征。")
    return stats, obs


# ---------------------------------------------------------------- 空洞检测
def detect_gaps(entries: list[dict], today: date) -> list[str]:
    gaps: list[str] = []
    filled = {e["layer"] for e in entries}
    for i in range(1, 10):
        if i in (8, 9):  # 8、9 层由脚本自动生成，不计入来源层
            continue
        if i not in filled:
            gaps.append(f"**第 {i} 层「{LAYER_NAMES[i]}」完全为空** —— 该层问题无法回答。")

    unknown = [e["id"] for e in entries if e["fields"].get("valid_from") == "unknown"]
    if unknown:
        gaps.append(f"`valid_from: unknown` 的条目 {len(unknown)} 条：{', '.join(unknown)}（历史查询不可用）")

    have = {e["path"].split("/")[0] for e in entries}
    for d in ("preferences", "health", "projects"):
        if d not in have:
            gaps.append(f"`memory/{d}/` 是空目录 —— 从未记录过。")

    for e in entries:
        vu = e["fields"].get("valid_until")
        if vu and re.match(r"^\d{4}-\d{2}-\d{2}$", vu) and date.fromisoformat(vu) < today:
            gaps.append(f"外部参数 `{e['id']}` 已于 {vu} 过期，反解金额会算错。")

    for e in entries:
        if not any(n.lower().startswith("evidence:") for n in e["notes"]):
            gaps.append(f"条目 `{e['id']}` 缺 evidence（违反 §8.6）。")

    vague = [e["id"] for e in entries if e["fields"].get("vague") == "true"]
    if vague:
        gaps.append(f"定性未量化条目：{', '.join(vague)}")

    return gaps


# ---------------------------------------------------------------- 渲染
def profile_gaps(entries: list[dict], by_layer: dict[int, list[dict]], cfg: dict) -> list[str]:
    """一个人档案的必备项。缺了它，AI 能查事实但答不了「怎么办」。

    与 detect_gaps 的分工：detect_gaps 查结构与时间问题；这里查"从未被记录过的关键维度"。
    """
    gaps: list[str] = []
    self_dir = cfg.get("self_dir", "")
    if not by_layer[2]:
        gaps.append("**第 2 层（决策函数）整体为空** —— 任何「要不要 / 该不该」的问题都答不了")
    if len(by_layer[3]) < 3:
        gaps.append(f"红线只有 {len(by_layer[3])} 条（建议 ≥3）—— 代理决策的护栏不足")
    if not by_layer[7] or all("ai-ization" in e["id"] or "ai" in e["path"] for e in by_layer[7]):
        gaps.append("目标层只有「AI 化」这一个外部触发的目标 —— 缺他自己想要的 1 年期 / 3 年期目标")

    def has(pred) -> bool:
        return any(pred(e) for e in entries)

    checks = [
        ("本人户籍", lambda e: "hukou" in e["id"] and self_dir in e["path"]),
        ("婚姻/领证年份", lambda e: re.search(r"结婚|领证|婚礼", " ".join(e["body"])) and re.search(r"20\d\d", " ".join(e["body"]))),
        ("子女姓名与年龄", lambda e: "child" in e["id"] and re.search(r"姓名|\d{4}", " ".join(e["body"]))),
        ("五险个人月扣缴额", lambda e: re.search(r"养老.*\d|医疗.*\d|失业.*\d", " ".join(e["body"]))),
        ("年包构成（年终奖/股票/签字费）", lambda e: re.search(r"年终奖|股票|期权|签字费|RSU", " ".join(e["body"]))),
        ("居住地（是否住自有住房）", lambda e: re.search(r"住在|现居|租房|工作日住", " ".join(e["body"]))),
        ("父母状况（年龄/健康/是否需负担）", lambda e: re.search(r"父亲|母亲|爸妈|父母", " ".join(e["body"]))),
        ("负债与存款", lambda e: re.search(r"房贷|车贷|贷款|负债|存款|储蓄", " ".join(e["body"]))),
        ("作息（几点睡/几点起）", lambda e: re.search(r"几点睡|作息|起床", " ".join(e["body"]))),
        ("身体健康基线（体检/体重/运动）", lambda e: "health" in e["path"] or re.search(r"体检|体重|运动|健身", " ".join(e["body"]))),
        ("核心偏好与价值观", lambda e: by_layer[2] and has(lambda x: x is not None)),
    ]
    for name, pred in checks:
        if not has(pred):
            gaps.append(f"**{name}** —— 从未记录")
    return gaps


def render_entry(e: dict) -> str:
    f = e["fields"]
    meta = f"`{e['id']}` · {f.get('valid_from', '?')} ~ {f.get('valid_until', '至今')}"
    lines = [f"### {meta}", ""]
    # 正文里已是 "- " 开头的行是子列表，缩进而不是再套一层短横线
    lines += [f"  {b}" if b.startswith("- ") else f"- {b}" for b in e["body"]]
    # §3.4：派生值不落库，导出时动态算
    if BIRTH_KEY in e["id"]:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", f.get("valid_from", ""))
        if m:
            by, bm, bd = map(int, m.groups())
            t = date.today()
            age = t.year - by - ((t.month, t.day) < (bm, bd))
            lines.append(f"- **动态计算（导出时）：{age} 岁**（{t.isoformat()}，下次导出自动更新，不落库）")
    if e["notes"]:
        lines.append("")
        lines += [f"  > {n}" for n in e["notes"]]
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    today = date.today()
    entries = parse_entries()
    by_layer: dict[int, list[dict]] = {i: [] for i in range(1, 11)}
    for e in entries:
        by_layer[e["layer"]].append(e)

    stats, obs = voice_fingerprint(entries)
    gaps = detect_gaps(entries, today)
    filled = [i for i in range(1, 10) if by_layer[i]]
    coverage = (len(filled) + 1) / 10  # 第 10 层恒有

    out: list[str] = []
    out.append(f"# {CFG['user_name']} · {CFG['export_title']}（AI 化导出 {today.isoformat()}）")
    out.append("")
    out.append(f"> 生成时间 {today.isoformat()} ｜ 有效条目 {len(entries)} 条 ｜ 覆盖度 {coverage:.0%}")
    critical_gap = [i for i in (2, 3) if not by_layer[i]]
    if coverage < 0.5 or critical_gap:
        out.append(">")
        reason = []
        if coverage < 0.5:
            reason.append(f"覆盖度仅 {coverage:.0%}")
        if critical_gap:
            reason.append("关键层为空：" + "、".join(f"第{i}层「{LAYER_NAMES[i]}」" for i in critical_gap))
        out.append(f"> ⚠️ **此档案不足以支撑代理决策，仅能用于事实查询。**（{'；'.join(reason)}）")
    out.append("")
    out.append("## 0. 给接手者的话")
    out.append("")
    out.append("这份文件描述一个人，不是描述一个数据库。用法：")
    out.append("")
    out.append("1. **能查到 → 用**。第 1、4、5、10 层的事实可直接引用，不要重新推断。")
    out.append("2. **查不到 → 问，不要填**。第 9 层列的都是空白，任何你在本文件中找不到的细节，都不许用常理补全。")
    out.append("3. **第 2、3 层为空时，禁止替他做任何有代价的决定**（花钱、承诺、对外发言、占用时间）。")
    out.append("4. 时间一律写绝对时间（ISO 8601，+08:00），不写「最近」「前不久」。")
    out.append("")

    for i in range(1, 10):
        if i in (8, 9):  # 第 8 层由语言指纹渲染，第 9 层由空洞检测渲染，此处跳过
            continue
        out.append(f"## {i}. {LAYER_NAMES[i]}")
        out.append("")
        if not by_layer[i]:
            out.append(f"_本层为空。见第 9 层。_")
            out.append("")
            continue
        for e in by_layer[i]:
            out.append(render_entry(e))

    # 第 8 层用指纹替换裸事实
    out.append("## 8. 语言指纹（从原话反向提取）")
    out.append("")
    if stats.get("n", 0) < 3:
        out.append(f"_样本仅 {stats.get('n', 0)} 条，不足以提炼。见第 9 层。_")
    else:
        out.append(f"样本：{stats['n']} 条用户原话，共 {stats['chars']} 字符，平均 {stats['avg']} 字符/条。")
        out.append("")
        for o in obs:
            out.append(f"- {o}")
        out.append("")
        out.append("> 以上均为可证伪的统计观察，不是主观评价。原话全文见第 10 层 evidence。")
    out.append("")

    out.append("## 9. 已知空洞（脚本自动生成，非人工筛选）")
    out.append("")
    out.append("### 9.1 结构性空洞")
    out.append("")
    if gaps:
        for g in gaps:
            out.append(f"- {g}")
    else:
        out.append("_未检测到结构性空洞。_")
    out.append("")
    pgaps = profile_gaps(entries, by_layer, CFG)
    out.append("### 9.2 画像关键字段缺失（这些不是「忘了记」，是「从未被问过」）")
    out.append("")
    if pgaps:
        for g in pgaps:
            out.append(f"- {g}")
    else:
        out.append("_画像关键字段已齐。_")
    out.append("")

    out.append("## 10. 事实索引（只给定位信息，正文已在前 9 层展示）")
    out.append("")
    for e in sorted(entries, key=lambda x: (x["path"], x["id"])):
        out.append(f"- `{e['path']}` → `{e['id']}` ｜ {e['fields'].get('valid_from','?')} ~ {e['fields'].get('valid_until','至今')}")
    out.append("")

    out.append("## 附录 A. 覆盖度自评")
    out.append("")
    out.append("| 层 | 状态 | 条目数 |")
    out.append("|---|---|---|")
    for i in range(1, 11):
        n = len(by_layer[i])
        state = "已填充" if n and i != 8 else ("自动生成" if i in (8, 9) else ("空" if n == 0 else "已填充"))
        if i == 8:
            state = "自动生成" if stats.get("n", 0) >= 3 else "样本不足"
        out.append(f"| {i} {LAYER_NAMES[i]} | {state} | {n if i not in (8, 9) else '—'} |")
    out.append("")
    out.append(f"**覆盖度 {coverage:.0%}**（十层中已填充 {len(filled) + 1} 层）")
    out.append("")

    out.append("## 附录 B. 下一步最该补的三件事")
    out.append("")
    priority = []
    if not by_layer[2]:
        priority.append("**决策函数层为空** —— 没有它，任何 AI 只能按通用逻辑推断你的选择，做出来的是「一个理性人」的决定，不是你的。成本：一次深入对话。")
    if not by_layer[3]:
        priority.append("**红线层为空** —— 最危险的一层。别人（或代理）可能做出你会彻底翻脸的决定而毫无预警。成本：列 5 条「绝对不行」。")
    if not by_layer[7]:
        priority.append("**目标层为空** —— 不知道往哪走，所有建议都在优化你没选的路。成本：说 3 个半年内的目标。")
    if any(e["id"] == "insur-001" for e in entries):
        priority.append("**五险个人扣缴额未记** —— 税后收入算不准。成本：看一眼工资条。")
    for n, p in enumerate(priority[:3], 1):
        out.append(f"{n}. {p}")
    out.append("")

    target = ROOT / f"export-{today.isoformat()}.md"
    target.write_text("\n".join(out), encoding="utf-8")
    print(f"written: {target}")
    print(f"entries: {len(entries)}  coverage: {coverage:.0%}  gaps: {len(gaps)}")


if __name__ == "__main__":
    main()
