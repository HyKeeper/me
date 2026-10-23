#!/usr/bin/env python3
"""读取 memory/_config.md 的键值配置。

设计约束：
    - 配置本身也是 Markdown（§8.1），不引入 yaml/json 的事实源旁路。
    - 所有键都有默认值：新用户不写配置也能跑，新增键不会破坏旧库。
    - 开源场景下，别人的 self_dir、条目 id、是否有薪资数据全都不同，
      因此这里只提供"能力开关 + 指针"，不硬编码任何个人事实。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# MEMORY_ROOT 环境变量优先：测试与多实例（同一套代码指向不同记忆库）都靠它
ROOT = Path(os.environ.get("MEMORY_ROOT") or Path(__file__).resolve().parent.parent).resolve()
MEM = ROOT / "memory"
CONFIG_PATH = MEM / "_config.md"

DEFAULTS: dict[str, str] = {
    "user_name": "本人",
    "self_dir": "",                 # 空 = 自动探测 people/ 下唯一的目录
    "timezone": "Asia/Shanghai",
    "export_title": "个人档案",
    "payroll_enabled": "false",
    "payroll_salary_id": "",
    "payroll_fund_id": "",
    "payroll_param_id": "",
    "birth_id_keyword": "birth",
    "semantic_enabled": "true",
    "semantic_threshold": "0.30",
}


def _parse_table(text: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("键", "") or set(cells[0]) <= set("- "):
            continue
        cfg[cells[0]] = cells[1]
    return cfg


def load() -> dict[str, str]:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        cfg.update({k: v for k, v in _parse_table(CONFIG_PATH.read_text(encoding="utf-8")).items() if k})
    if not cfg["self_dir"]:
        cfg["self_dir"] = detect_self_dir()
    return cfg


def detect_self_dir() -> str:
    """没配 self_dir 时：取 people/ 下唯一的子目录；多个就取第一个并提示。"""
    people = ROOT / "memory" / "people"
    if not people.exists():
        return "本人"
    dirs = sorted(d.name for d in people.iterdir() if d.is_dir())
    if not dirs:
        return "本人"
    return dirs[0]


def get_float(cfg: dict[str, str], key: str) -> float:
    try:
        return float(cfg.get(key, DEFAULTS.get(key, "0")))
    except ValueError:
        return 0.0


def get_bool(cfg: dict[str, str], key: str) -> bool:
    return str(cfg.get(key, DEFAULTS.get(key, "false"))).strip().lower() in ("true", "1", "yes", "on")


if __name__ == "__main__":
    for k, v in load().items():
        print(f"{k:24s} = {v}")
