#!/usr/bin/env python3
"""提问前的查库门禁：这个问题库里是不是已经有答案了？

背景：本库到 184 条时，agent 仍问过「戴戈庄房子谁在住」——
而 father-live-001 里明明写着答案。原因是提问不像写入那样有前置动作，
问题全靠联想生成。本脚本把「查库」变成一个可执行的步骤。

用法：
    python3 scripts/ask.py "戴戈庄的房子现在谁在住"

输出三段：
    1) 语义最相关的条目（含相似度）
    2) 这些条目的「待确认」行 —— 若你的问题命中其中一条，说明这是**已知空白，可以问**
    3) 结论：先读条目 / 可以问
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import memconfig  # noqa: E402  —— 路径口径的唯一真相见 is_memory_doc()
import semantic  # noqa: E402

HIT_HIGH = 0.30  # 高于此值，几乎一定已经有相关记录
PENDING = re.compile(r"待确认[:：](.+)", re.S)


def pending_lines(path: Path | str) -> list[str]:
    """抽出某个文件里的「待确认」清单。

    注意：这些行都以 ">" 开头，而 semantic.parse_docs() 会过滤掉引用行，
    所以必须直接读文件，不能依赖解析结果。
    """
    text = (semantic.MEM / path).read_text(encoding="utf-8") if not str(path).startswith("/") else Path(path).read_text(encoding="utf-8")
    out = []
    for m in PENDING.finditer(text):
        tail = re.split(r"\n\s*(?:>|$)", m.group(1))[0]
        items = re.split(r"[①②③④⑤⑥⑦⑧⑨⑩]|\n", tail)
        out += [x.strip(" 。；，、") for x in items
                if x.strip(" 。；，、") and not x.strip().startswith("#")]
    return out


def list_all() -> int:
    """列出全库所有「待确认」项 —— 这才是真正的题库。"""
    total = 0
    for md in sorted(semantic.MEM.rglob("*.md")):
        if not memconfig.is_memory_doc(md):
            continue
        items = pending_lines(str(md.relative_to(semantic.MEM)))
        if not items:
            continue
        print(f"\n## {md.relative_to(semantic.MEM)}")
        for it in items:
            total += 1
            print(f"  - {it}")
    print(f"\n--- 共 {total} 条待确认 ---")
    print("提问请从这里挑：这些是**已知空白**；不在这里、且 -- 查库无高相似度命中的，才可能是新空白。")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if sys.argv[1] in ("--list", "-l"):
        return list_all()
    q = " ".join(sys.argv[1:])
    idx = semantic.load_index()
    hits = idx.query(q, k=5)
    top = hits[0][0] if hits else 0.0

    print(f"=== 提问查库：{q} ===")
    print(f"最高相似度 {top:.3f}\n")

    print("--- 最相关条目 ---")
    for score, doc in hits:
        print(f"  {score:.3f}  {doc['id']:<18} {doc['path']}")
        body = " ".join(doc["body"]).replace("\n", " ")
        print(f"         {body[:110]}…")
        for p in pending_lines(doc['path'])[:4]:
            print(f"         ↳ 待确认：{p[:70]}")
        print()

    print("--- 结论 ---")
    if top >= HIT_HIGH:
        print("⚠️  库里有高度相关内容。**先读上面的条目再说**。")
        print("    只有当你的问题命中某个「待确认」项时，才可以直接问用户。")
        return 1
    print("✅ 相关度低，可能是真空白 —— 但仍请扫一眼上面的待确认项，它们才是真正的题库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
