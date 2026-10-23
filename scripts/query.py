#!/usr/bin/env python3
"""记忆库查询器（只读）

AGENTS.md §6.1 定义了 as_of 查询语义，但一直只有规则、没有工具。
本脚本把规则变成可执行的查询：

    python3 scripts/query.py 某公司                # 关键词检索（自动展开别名）
    python3 scripts/query.py --as-of 2023-06       # 某个时间点的状态快照
    python3 scripts/query.py --id emp-001          # 单条详情
    python3 scripts/query.py --time 2023           # 某年发生了什么

时间四档（§3）在这里的实现：
    2022-04      → 起点 2022-04-01
    ~2023-03     → 起点 2023-03-01（模糊，输出会标注）
    <= 2026-10-23→ 起点无界，对任意 T <= 2026-10-23 视为可能有效，输出标注"起点不确定"
    unknown      → 命中所有查询，输出标注"生效时间未知"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# MEMORY_ROOT 环境变量优先：测试与多实例（同一套代码指向不同记忆库）都靠它
ROOT = Path(os.environ.get("MEMORY_ROOT") or Path(__file__).resolve().parent.parent).resolve()
MEM = ROOT / "memory"

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import semantic
except Exception:  # pragma: no cover
    semantic = None

ENTRY_RE = re.compile(r"^- \[id:\s*([^\]]+)\]")
FIELD_RE = re.compile(r"\[(\w+):\s*([^\]]*)\]")


# ------------------------------------------------------------ 解析
def parse_entries() -> list[dict]:
    items: list[dict] = []
    for md in sorted(MEM.rglob("*.md")):
        rel = str(md.relative_to(MEM))
        if "timeline" in md.parts or md.name.startswith("_"):
            continue
        section, cur = None, None
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
                cur = {"id": m.group(1), "path": rel, "section": section,
                       "fields": dict(FIELD_RE.findall(line)), "body": [], "notes": []}
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
    return items


def load_aliases() -> list[set[str]]:
    """从 memory/_aliases.md 读表格，每行的实体列构成一个别名组。"""
    p = MEM / "_aliases.md"
    if not p.exists():
        return []
    groups: list[set[str]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or set(line) <= set("|- :"):
            continue
        cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
        # 只取前两列（用户口径 / 标准实体），第 3 列起是描述，不能当别名
        head = cells[:2]
        toks: set[str] = set()
        for c in head:
            if not c or c.startswith("⚠️"):
                continue
            for part in re.split(r"[/、,，]", c):
                part = re.sub(r"[（(].*?[)）]", "", part).strip()
                if part and len(part) <= 16:
                    toks.add(part)
        if len(toks) >= 2:
            groups.append(toks)
    return groups


def expand(query: str, groups: list[set[str]]) -> set[str]:
    """关键词 + 别名闭包。"""
    terms = {query}
    changed = True
    while changed:
        changed = False
        for g in groups:
            if g & terms and not g <= terms:
                terms |= g
                changed = True
    return terms


# ------------------------------------------------------------ 时间
def norm_start(vf: str) -> tuple[str, str]:
    """返回 (可比较起点, 精度说明)。"""
    if vf == "unknown":
        return "0000-00-00", "unknown"
    if vf.startswith("<="):
        return "0000-00-00", "le"
    s = vf.lstrip("~")
    note = "fuzzy" if vf.startswith("~") else "exact"
    if len(s) == 4:
        return s + "-01-01", note + "(year)"
    if len(s) == 7:
        return s + "-01", note + "(month)"
    return s, note


def norm_end(vu: str | None) -> str:
    if not vu:
        return "9999-12-31"
    if vu.startswith("<="):
        return "9999-12-31"
    s = vu.lstrip("~")
    if len(s) == 4:
        return s + "-12-31"
    if len(s) == 7:
        return s + "-31"
    return s


def active_at(e: dict, t: str) -> bool:
    start, note = norm_start(e["fields"].get("valid_from", "unknown"))
    end = norm_end(e["fields"].get("valid_until"))
    if note == "le":
        # 起点无界：只要 t 不晚于上界就视为可能有效
        bound = e["fields"]["valid_from"].split("<=")[1].strip()
        return t <= bound and t <= end
    if note == "unknown":
        return t <= end
    return start <= t <= end


def fmt(e: dict) -> str:
    f = e["fields"]
    tag = {"current": "ACTIVE", "history": "HIST "}[e["section"]]
    return (f"[{tag}] {e['id']:14s} {f.get('valid_from','?'):>14s} ~ {f.get('valid_until','至今'):>10s}  "
            f"{' '.join(e['body'])[:110]}")


# ------------------------------------------------------------ 命令
def cmd_search(q: str, groups: list[set[str]], items: list[dict]) -> None:
    # 优先走语义检索（同义词归一 + TF-IDF），失败或无结果再退回字面
    if semantic is not None:
        try:
            idx = semantic.Index(semantic.parse_docs())
            res = idx.query(q, 8)
            if res and res[0][0] >= 0.05:
                for score, d in res:
                    print(f"{score:.3f}  {d['id']:14s} {d['path']:34s} {' '.join(d['body'])[:80]}")
                return
        except Exception:
            pass
    terms = expand(q, groups)
    if len(terms) > 1:
        print(f"别名扩展：{q} → {' / '.join(sorted(terms))}\n")
    hits = [e for e in items if any(t.lower() in (e["id"] + e["path"] + " ".join(e["body"]) + " ".join(e["notes"])).lower() for t in terms)]
    if not hits:
        print("无匹配。")
        return
    for e in hits:
        print(fmt(e))


def cmd_as_of(t: str, items: list[dict]) -> None:
    print(f"=== as_of {t} 的有效状态 ===\n")
    hits = [e for e in items if active_at(e, t)]
    for e in sorted(hits, key=lambda x: x["path"]):
        note = norm_start(e["fields"].get("valid_from", "unknown"))[1]
        warn = {"le": "  ⚠️起点不确定", "unknown": "  ⚠️生效时间未知", "fuzzy": "  ~模糊时间"}.get(note, "")
        print(f"[{e['id']:14s}] {e['path']:34s} {' '.join(e['body'])[:80]}{warn}")
    print(f"\n共 {len(hits)} 条。{'' if hits else '那段时间没有记录 —— 不做推断。'}")


def cmd_id(i: str, items: list[dict]) -> None:
    for e in items:
        if e["id"] == i:
            print(f"# {e['id']}  ({e['path']}, {e['section']})")
            for b in e["body"]:
                print(f"- {b}")
            for n in e["notes"]:
                print(f"  > {n}")
            return
    print(f"未找到 {i}")


def cmd_time(year: str, items: list[dict]) -> None:
    p = MEM / "timeline" / "events.md"
    print(f"=== {year} 年时间线 ===\n")
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"- {year}"):
            print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description="记忆库查询（只读）")
    ap.add_argument("query", nargs="?", help="关键词")
    ap.add_argument("--as-of", dest="as_of", metavar="YYYY[-MM[-DD]]")
    ap.add_argument("--id")
    ap.add_argument("--time", metavar="YYYY")
    a = ap.parse_args()

    items = parse_entries()
    groups = load_aliases()

    if a.id:
        cmd_id(a.id, items)
    elif a.as_of:
        from calendar import monthrange
        parts = a.as_of.split("-")
        if len(parts) == 3:
            t = a.as_of
        elif len(parts) == 2:
            y, m = int(parts[0]), int(parts[1])
            t = f"{y}-{m:02d}-{monthrange(y, m)[1]:02d}"   # 该月最后一天
        else:
            t = f"{parts[0]}-12-31"
        cmd_as_of(t, items)
    elif a.time:
        cmd_time(a.time, items)
    elif a.query:
        cmd_search(a.query, groups, items)
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
