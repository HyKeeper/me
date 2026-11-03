#!/usr/bin/env python3
"""把记忆库里的时间占位符替换为真实时间。

问题背景：agent 手写时间戳时会"估时间"（按轮次累加），把时间写到未来或写偏，
动摇 §8.3「三个时间字段必填」的地基。本脚本让 agent 只写占位符：

    @NOW    -> 现在，ISO 8601 带时区，如 2026-11-02T22:35:12+08:00
    @TODAY  -> 今天，如 2026-11-02

用法：
    python3 scripts/stamp.py            # 替换并报告
    python3 scripts/stamp.py --dry-run  # 只报告，不写入

性质：幂等。没有占位符时不做任何改动。只替换占位符，不触碰其它内容。
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "memory", ROOT / "ops"]

PLACEHOLDER = re.compile(r"@(NOW|TODAY)\b")
# 反引号内是"提到占位符"，不是"使用占位符"——必须原样保留，
# 否则跑一次就会把 AGENTS.md / changelog 里的规则说明改成时间戳。
CODE_SPAN = re.compile(r"(`[^`\n]*`)")


def split_code(text: str) -> list[tuple[bool, str]]:
    """切成 [(是否代码段, 片段), ...]。偶数位是普通文本。"""
    parts = CODE_SPAN.split(text)
    return [(i % 2 == 1, part) for i, part in enumerate(parts)]


def stamp_text(zero_ts: str, zero_day: str, dry: bool) -> tuple[int, int]:
    """返回 (改动文件数, 替换处数)。"""
    files = 0
    hits = 0
    for base in TARGETS:
        if not base.exists():
            continue
        for md in sorted(base.rglob("*.md")):
            try:
                text = md.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            pieces = split_code(text)
            n = sum(len(PLACEHOLDER.findall(part)) for is_code, part in pieces if not is_code)
            if n == 0:
                continue
            new = "".join(
                part if is_code else PLACEHOLDER.sub(
                    lambda m: zero_ts if m.group(1) == "NOW" else zero_day, part)
                for is_code, part in pieces
            )
            hits += n
            files += 1
            print(f"  {md.relative_to(ROOT)}  ×{n}")
            if not dry:
                md.write_text(new, encoding="utf-8")
    return files, hits


def main() -> int:
    ap = argparse.ArgumentParser(description="时间占位符替换（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写入")
    args = ap.parse_args()

    now = datetime.datetime.now().astimezone()
    ts = now.isoformat(timespec="seconds")
    day = now.strftime("%Y-%m-%d")
    print(f"=== stamp {ts} ===")
    files, hits = stamp_text(ts, day, args.dry_run)
    if files == 0:
        print("无占位符，未改动任何文件。")
        return 0
    verb = "将替换" if args.dry_run else "已替换"
    print(f"{verb}：{files} 个文件 / {hits} 处占位符")
    if not args.dry_run:
        print("提示：接着跑 `python3 scripts/check.py` 做全库自检。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
