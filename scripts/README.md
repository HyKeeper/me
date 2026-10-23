# scripts/

| 脚本 | 用途 | 用法 | 说明 |
|---|---|---|---|
| `compensation.py` | 北京公积金月缴存额计算 | `python3 scripts/compensation.py --salary 30000 --rate 0.12 --year 2026`（或 `--all-rates`） | 只读、幂等。参数来源 `memory/misc/北京社保公积金参数.md`。**不含五险**，不臆造社保数字。 |
| `check.py` | 记忆库门禁与冲突检测（只读） | `python3 scripts/check.py`（全库）/ `--pre memory/work/xxx.md`（写前） | ERROR=结构违规必须修，WARN=疑似冲突/会过期。含领域规则：薪资↔公积金互洽、出生日期↔年龄漂移。退出码 1 表示有 ERROR。 |
| `init.py` | 初始化新记忆库（开源入口） | `python3 scripts/init.py --name "张三" [--root DIR]` | 建目录骨架 + 生成 `_config.md` / `_index.md` / `events.md`。幂等，不覆盖已有文件，不预填任何个人信息。**含 Python 版本门槛（>= 3.9）**，只拦初始化、不碰主流程。 |
| `memconfig.py` | 读取 `memory/_config.md` 配置 | `python3 scripts/memconfig.py`（打印当前配置） | 所有键有默认值；`self_dir` 为空时自动探测 `people/` 下目录。用于消除脚本里的个人硬编码。 |
| `semantic.py` | 语义相似检索（TF-IDF 字符向量，零模型） | `python3 scripts/semantic.py "文本"` / `--pairs --threshold 0.3` / `--bench` | 纯 CPU：建索引 ~2ms，单查 ~0.03ms。同义词归一表在 `memory/_synonyms.md`。**相似 ≠ 冲突**，只用于候选生成。 |
| `query.py` | 记忆库查询（只读） | `python3 scripts/query.py 某公司`（关键词+别名扩展）/ `--as-of 2023-06`（时点快照）/ `--id emp-001` / `--time 2023` | 实现 §6.1 的 as_of 语义，四档时间分别处理并标注不确定性。 |
| `export.py` | 生成 AI 化个人档案（十层人格模型） | `python3 scripts/export.py` → 根目录 `export-YYYY-MM-DD.md` | 只读 `memory/`。分层规则集中在 `layer_of()`；语言指纹从 evidence 原话统计；已知空洞自动检测。规格见 `ops/export-spec.md`。 |

## 约定

- 每个脚本单一职责、只读或幂等，不允许写坏 `memory/`。
- 改脚本不覆盖旧版，写 `xxx-v2.py` 并在此登记原因。
- 脚本不能替代 §5 的 Read 与写入后自检流程。
