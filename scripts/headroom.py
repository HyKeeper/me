#!/usr/bin/env python3
"""写前体量预检：看目标条目**还剩多少字符空间**。

为什么需要它
------------
`check.py --budget "<文本>"` 只算「你打算写的那段文本」有多长，
**不知道目标条目已经占了多少**。于是给已有条目追加内容时，几乎必然超限——
本库在 2026-11-03 的一轮会话里因此连报 5 次 ERROR，每次都要现场裁剪。

正确顺序应该是：
    1. `headroom.py --file <目标文件>`   ← 先看还有多少空间（本脚本）
    2. 按剩余空间决定：追加 / 拆分 / 改写
    3. `check.py --pre <目标文件>`        ← 再看语义冲突
    4. 落笔

用法
----
    python3 scripts/headroom.py                  # 默认：只列剩余 < 400 的条目
    python3 scripts/headroom.py --all            # 全部 active 条目
    python3 scripts/headroom.py --limit 600      # 自定义阈值
    python3 scripts/headroom.py --file work/okr.md   # 只查某文件（写前必跑）

只读、幂等。不写任何记忆文件。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402

SOFT = check.BUDGET_SOFT
HARD = check.BUDGET_HARD


def bar(used: int, cap: int, width: int = 12) -> str:
    filled = min(width, round(width * used / cap))
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    argv = sys.argv[1:]
    show_all = "--all" in argv
    limit = 400 if not show_all else HARD + 1
    if "--limit" in argv:
        try:
            limit = int(argv[argv.index("--limit") + 1])
        except (IndexError, ValueError):
            print("--limit 后面需要一个整数")
            return 2

    target = None
    if "--file" in argv:
        i = argv.index("--file")
        target = argv[i + 1] if i + 1 < len(argv) else None
        if not target:
            print("--file 后面需要一个路径片段，例如 work/okr.md")
            return 2

    items, _ = check.parse_all()
    rows = []
    for e in items:
        if e["section"] != "current":
            continue
        if target and target not in e["path"]:
            continue
        # ⚠️ 口径必须与 check_bloat 一致：它只算 body，**不含 notes**
        # （notes 里是 evidence / clarification / 待确认，不计入 1200 硬线）
        n = len(" ".join(e["body"]))
        notes = len(" ".join(e["notes"]))
        rows.append((n, e, notes))
    rows.sort(key=lambda r: -r[0])

    if not rows:
        print(f"没有匹配的 active 条目（--file {target}）")
        return 1

    if target:
        print(f"=== 目标文件：{target} ===")
    print(f"软线 {SOFT}（建议拆分） / 硬线 {HARD}（超即 ERROR）\n")
    print("（字符 = check_bloat 口径，仅 body；附注 = notes，不计入硬线）\n")
    print(f"{'条目':<16}{'文件':<34}{'字符':>6}{'余量':>7}{'附注':>6}  {'占用':<14} 状态")
    print("-" * 104)

    shown = 0
    for n, e, notes in rows:
        room = HARD - n
        if not show_all and not target and room > limit:
            continue
        if n > HARD:
            flag = "🔴 超硬线"
        elif n > SOFT:
            flag = "🟡 超软线"
        elif room < 150:
            flag = "🟠 快满了"
        else:
            flag = "✅"
        print(f"{e['id']:<16}{e['path']:<34}{n:>6}{room:>7}{notes:>6}  {bar(n, HARD):<14} {flag}")
        shown += 1

    print("-" * 96)
    if target:
        print(f"写入前提醒：追加内容长度须 ≤ 最小余量；不够就**拆文件**，不要硬塞。")
    else:
        print(f"共 {len(rows)} 条 active；列出 {shown} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
