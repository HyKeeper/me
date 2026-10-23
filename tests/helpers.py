"""测试公共工具：构造临时记忆库、生成条目文本、绑定模块路径。

设计：
    脚本是"模块级常量指向 memory/"的结构，测试通过 monkey-patch
    模块的 ROOT/MEM 属性来切换目标库，不依赖环境变量、不依赖 pytest。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TS = "2026-01-01T00:00:00+08:00"


def entry(
    eid: str,
    *,
    vf: str = "2026-01-01",
    vu: str | None = None,
    spoken: str = TS,
    recorded: str = TS,
    body: str = "某条事实内容。",
    evidence: str | None = '"用户说的一句话"',
    extra: str = "",
    status: str | None = None,
) -> str:
    """生成一条符合规范的条目文本。"""
    parts = [f"[id: {eid}]", f"[spoken_at: {spoken}]", f"[valid_from: {vf}]", f"[recorded_at: {recorded}]"]
    if vu:
        parts.append(f"[valid_until: {vu}]")
    if status:
        parts.append(f"[status: {status}]")
    if extra:
        parts.append(extra)
    lines = ["- " + " ".join(parts)]
    for b in body.split("\n"):
        lines.append(f"  {b}")
    if evidence is not None:
        lines.append(f"  > evidence: {evidence}")
    return "\n".join(lines)


def doc(topic: str, *entries: str, history: tuple[str, ...] = ()) -> str:
    """生成一个完整的记忆文件内容。"""
    s = f"---\ntopic: {topic}\nupdated: {TS}\n---\n\n## current\n\n"
    s += "\n".join(entries)
    s += "\n\n## history\n\n"
    if history:
        s += "\n".join(history) + "\n"
    return s


class Lib:
    """临时记忆库（自动清理）。"""

    def __init__(self, files: dict[str, str] | None = None):
        self.tmp = Path(tempfile.mkdtemp(prefix="memtest-"))
        self.mem = self.tmp / "memory"
        self.mem.mkdir(parents=True)
        for rel, content in (files or {}).items():
            self.write(rel, content)

    def write(self, rel: str, content: str) -> Path:
        p = self.mem / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def bind(self, *modules):
        """把模块的 ROOT/MEM 指向本临时库。"""
        for m in modules:
            m.ROOT = self.tmp
            m.MEM = self.mem
            if hasattr(m, "CONFIG_PATH"):
                m.CONFIG_PATH = self.mem / "_config.md"
        return modules[0] if len(modules) == 1 else modules

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
