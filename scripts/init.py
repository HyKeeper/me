#!/usr/bin/env python3
"""初始化一个新的个人记忆库（开源场景的入口）。

别人 clone 这个仓库后，跑一条命令就能得到可用的骨架：

    python3 scripts/init.py --name "张三"

做的事：
    1. 建目录骨架（memory/*、ops/*）
    2. 生成 memory/_config.md（个人实例配置，不进 git）
    3. 生成 people/_index.md、timeline/events.md 的空模板
    4. 幂等：已存在的文件一律不覆盖

不做的事：
    - 不预填任何个人信息（那是用户的隐私，不是模板）
    - 不动已有的 memory/ 内容
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))

# 运行环境下限。与 pyproject.toml 的 requires-python 保持一致。
# 注意：低于 3.6 的环境连本文件的语法（f-string / 类型注解）都过不了，
# 版本检查只能拦住 3.6~3.8 这一段。更早的版本由 README 的声明兜底。
MIN_PY = (3, 9)

DIRS = [
    "memory/people", "memory/work", "memory/preferences", "memory/health",
    "memory/projects", "memory/misc", "memory/assets", "memory/timeline", "memory/_archive",
    "ops/proposals", "scripts",
]

CONFIG_TMPL = """# 系统配置

> Markdown 表格即配置（AGENTS.md §8.1：Markdown 是唯一事实源）。
> 本文件是你的实例配置，**不要提交进仓库**（.gitignore 已排除）。

| 键 | 值 | 说明 |
|---|---|---|
| user_name | {name} | 导出物标题、报告里显示的名字 |
| self_dir | {name} | `people/` 下代表本人的子目录名 |
| timezone | Asia/Shanghai | 所有时间戳的时区 |
| export_title | 个人档案 | 导出物标题后缀 |
| payroll_enabled | false | 薪资↔公积金互洽规则；有数据且配好下面三个 id 后改 true |
| payroll_salary_id |  | 薪资条目 id |
| payroll_fund_id |  | 公积金条目 id |
| payroll_param_id |  | 政策参数条目 id |
| birth_id_keyword | birth | 识别"出生日期"类条目的 id 关键词 |
| semantic_enabled | true | 语义重合检查开关 |
| semantic_threshold | 0.30 | 语义重合报 INFO 的阈值 |
"""

INDEX_TMPL = """# people 索引

> 每个主体一个子目录。属性仍是一文件一属性（AGENTS.md §3.2）。id 全局唯一，迁移不改号。

| 主体 | 目录 | 与用户关系 | 属性文件 | 最后更新 |
|---|---|---|---|---|
| {name} | `{name}/` | 本人 | （待记录） | {today} |

## 命名约定

- 一人一子目录，属性一文件一属性。
- 主体由目录承载，不用文件名前缀。
- 拆分判断：两个属性是否会**各自独立变化**？会就分文件。
"""

TIMELINE_TMPL = """# 事件时间线

> append-only，永不修改（格式损坏可订正，见 AGENTS.md §6）。
> 每条带条目 id 与事件类型（spoken / valid_from / valid_until / superseded / corrected）。

"""


def write_if_absent(path: Path, content: str) -> bool:
    if path.exists():
        print(f"  跳过（已存在）: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  创建: {path}")
    return True


def main() -> int:
    # 环境门槛只放在这里，不放模块顶层：`import init`（测试、复用）不会被拦。
    # 日常主流程（check / query / export）完全不读这段，零开销。
    if sys.version_info < MIN_PY:
        cur = ".".join(str(x) for x in sys.version_info[:3])
        sys.exit(
            "需要 Python {} 或更高，当前是 {}。\n"
            "本项目零第三方依赖，只需升级 Python 本体，不需要 pip install。".format(
                "{}.{}".format(*MIN_PY), cur
            )
        )

    ap = argparse.ArgumentParser(description="初始化个人记忆库")
    ap.add_argument("--root", default=".", help="项目根目录，默认当前目录")
    ap.add_argument("--name", required=True, help="你的名字（用作 self_dir 与导出标题）")
    ap.add_argument("--force-dirs", action="store_true", help="仅创建目录，不生成配置文件")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    print(f"初始化记忆库于 {root}\n")

    for d in DIRS:
        p = root / d
        p.mkdir(parents=True, exist_ok=True)
        gk = p / ".gitkeep"
        if not gk.exists() and not any(p.iterdir()):
            gk.write_text("", encoding="utf-8")

    if a.force_dirs:
        print("目录已就绪（未生成配置）")
        return 0

    today = datetime.now(TZ).date().isoformat()
    write_if_absent(root / "memory" / "_config.md", CONFIG_TMPL.format(name=a.name))
    write_if_absent(root / "memory" / "people" / "_index.md", INDEX_TMPL.format(name=a.name, today=today))
    write_if_absent(root / "memory" / "timeline" / "events.md", TIMELINE_TMPL)
    (root / "memory" / "people" / a.name).mkdir(parents=True, exist_ok=True)

    print(f"""
就绪。下一步：
  1. 让 agent 读 AGENTS.md，然后开始灌入第一条信息：
        「我是{a.name}，1990 年出生，在 XX 工作」
  2. 校验：  python3 scripts/check.py
  3. 查询：  python3 scripts/query.py "我在哪工作"
  4. 导出：  python3 scripts/export.py   → export-{today}.md

提示：先补第 2 层（决策函数）和第 3 层（红线），
      否则导出物只能查事实，不能替你做决定。见 ops/export-spec.md。
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
