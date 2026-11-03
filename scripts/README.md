# scripts/

| 脚本 | 用途 | 用法 | 说明 |
|---|---|---|---|
| `compensation.py` | 北京公积金月缴存额计算 | `python3 scripts/compensation.py --salary 30000 --rate 0.12 --year 2026`（或 `--all-rates`） | 只读、幂等。参数来源 `memory/misc/北京社保公积金参数.md`。**不含五险**，不臆造社保数字。 |
| `check.py` | 记忆库门禁与冲突检测（只读） | `python3 scripts/check.py`（全库）/ `--pre memory/work/xxx.md`（写前） | ERROR=结构违规必须修，WARN=疑似冲突/会过期。含领域规则：薪资↔公积金互洽、出生日期↔年龄漂移。退出码 1 表示有 ERROR。 |
| `headroom.py` | **写前体量预检**：看目标条目还剩多少字符 | `python3 scripts/headroom.py`（默认列余量<400）/ `--all` / `--file work/okr.md`（写前必跑） | 只读。口径与 `check_bloat` 一致（**只算 body，不含 notes**）。存在的理由：`--budget` 只算「要写的那段」，不知道目标条目已占多少，追加时几乎必然超限。 |
| `init.py` | 初始化新记忆库（开源入口） | `python3 scripts/init.py --name "张三" [--root DIR]` | 建目录骨架 + 生成 `_config.md` / `_index.md` / `events.md`。幂等，不覆盖已有文件，不预填任何个人信息。**含 Python 版本门槛（>= 3.9）**，只拦初始化、不碰主流程。 |
| `memconfig.py` | 读取 `memory/_config.md` 配置 | `python3 scripts/memconfig.py`（打印当前配置） | 所有键有默认值；`self_dir` 为空时自动探测 `people/` 下目录。用于消除脚本里的个人硬编码。 |
| `semantic.py` | 语义相似检索（TF-IDF 字符向量，零模型） | `python3 scripts/semantic.py "文本"` / `--pairs --threshold 0.3` / `--bench` | 纯 CPU：建索引 ~2ms，单查 ~0.03ms。同义词归一表在 `memory/_synonyms.md`。**相似 ≠ 冲突**，只用于候选生成。 |
| `query.py` | 记忆库查询（只读） | `python3 scripts/query.py 某公司`（关键词+别名扩展）/ `--as-of 2023-06`（时点快照）/ `--id emp-001` / `--time 2023` | 实现 §6.1 的 as_of 语义，四档时间分别处理并标注不确定性。 |
| `export.py` | 生成 AI 化个人档案（十层人格模型） | `python3 scripts/export.py` → 根目录 `export-YYYY-MM-DD.md` | 只读 `memory/`。分层规则集中在 `layer_of()`；语言指纹从 evidence 原话统计；已知空洞自动检测。规格见 `ops/export-spec.md`。 |
| `total-comp.py` | 年度总包合成（只读） | `python3 scripts/total-comp.py [--bonus-months 2\|3] [--price 74.24] [--fx 6.648]` | **每项强制标 pre/post-tax**，混口径不加。股权按税前市值入，不按到手现金入。股价是变量，出敏感带不出点预测。输入参数全部注明来源条目。 |
| `rsu.py` | RSU 已归属／未归属／年度归属股数（只读） | `python3 scripts/rsu.py [--as-of YYYY-MM-DD] [--unit-price 493.5] [--json]` | 从 `memory/work/rsu.md` 的排期表解析，**不持有数据副本**（否则两边静默分叉）。市值是估算，单价必须由使用者给——脚本不联网取价，取来的价立刻过期还会被当事实引用。 |
| `stamp.py` | 时间占位符盖章（幂等） | `python3 scripts/stamp.py [--dry-run]` | 把 `@NOW` / `@TODAY` 替换为真实时间。**写入后必须运行**，`check.py` 会因残留占位符报 ERROR。反引号内的「提到」不会被替换。替代「记得先跑 date」。 |
| `push_via_api.py` | 应急引导推送（github.com:443 不可达时） | 见文件头注释 | 仅在引导阶段用 Git Data API 复制一次已 commit 的本地状态。不处理增量与 merge。token 只从 `~/.git-credentials` 读，不落盘、不进 argv。平时不用。 |
| `ask.py` | **提问前查库**（只读） | `python3 scripts/ask.py "你的问题"` / `--list` | 输出相关条目+相似度+它们的「待确认」项，并给结论。**相似度 ≥0.30 说明库里有答案，先读条目再问。** `--list` 列出全库待确认项，这才是真正的题库。 |

## 约定

- 每个脚本单一职责、只读或幂等，不允许写坏 `memory/`。
- 改脚本不覆盖旧版，写 `xxx-v2.py` 并在此登记原因。
  - **例外：修 bug 直接改原文件**，并在本文件末尾按日期登记（写 v2 会让两个版本并存、更容易跑错）。改动范围限于 bug 修复，不夹带功能。
- 脚本不能替代 §5 的 Read 与写入后自检流程。

## 哪些脚本不进仓库

`.gitignore` 排除以下三个。它们**不含任何真实数据**（token 从 `~/.git-credentials` 读、不落盘；股数与排期不持有副本，只从 `memory/` 现读），但它们暴露「有什么、从哪拿」——公开无收益，故排除：

| 脚本 | 排除原因 |
|---|---|
| `rsu.py` / `total-comp.py` | 会读取 `memory/work/rsu.md` 的排股排期 → 暴露「有股权排期这件事」 |
| `push_via_api.py` | 引导期应急推送，暴露账号操作路径 |

→ 开源使用者会在上表看到这三个名字，**但仓库里没有对应文件，这是设计，不是缺失**。

## 2026-11-02 | check.py 修 bug：_archive/ 被当成 active 记忆

- **问题**：`parse_all()` 只跳过 `timeline/` 和文件名以 `_` 开头的文件，**没跳过 `_archive/` 目录**。整份文件废弃移入 `_archive/` 后，其条目仍被计为 active、仍参与 id 唯一性和臃肿校验，导致「id 重复 ERROR」——即按 AGENTS.md §8 第 2 条正常归档后反而校验失败。
- **修法**：`parse_all()` 与 `check_topic_overlap()` 两处路径过滤各加 `or "_archive" in md.parts`。只改过滤，不改任何校验规则。
- **影响**：`active 条目数` 统计不再包含归档文件；归档文件里的悬空引用/臃肿不再报警（它们本来就不该被校验）。
- 触发者：2026-11-02 拆分 `misc/云原生与Agent市场参数.md` 时发现。

## 2026-11-03 | **路径口径统一**：`_archive/` 过滤从 5 份变成 1 份

- **问题**：`_archive/` 过滤逻辑在 `check.py` / `export.py` / `query.py` / `semantic.py` / `ask.py` 里**各写了一份，且各不相同**：

  | 脚本 | timeline/ | `_` 开头 | `_archive/` |
  |---|---|---|---|
  | `check.py` | ✅ | ✅ | ✅ |
  | `ask.py` | ❌ | ✅ | ✅ |
  | `export.py` / `query.py` / `semantic.py` | ✅ | ✅ | ❌ |

  2026-11-02 修 `check.py` 的 `_archive` 漏网时**只改了 1 处**，另外 3 处照旧 —— 于是：
  1. **`export.py` 导出的交付物里混进 2 条已归档（已作废）的记忆**（214 vs 真实 212）
  2. `query.py` 的 `--as-of` 时点查询会命中废弃值
  3. `semantic.py` / `ask.py` 的语义索引被废弃条目污染 → `--pre` 与提问查库的结果不可靠

- **修法**：在 `memconfig.py` 新增 `is_memory_doc(path)` 与 `MEM_SKIP_PARTS`，5 个脚本全部改为调用它。**不再复制过滤逻辑。**
- **验证**：`export.py` 输出 214 → **212**，与 `check.py` 一致；`query.py` / `semantic.py` / `ask.py --list`（468 条待确认）均正常。
- **触发者**：2026-11-03 自我迭代时写 `headroom.py`，发现它与 `check_bloat` 口径不一致（body vs body+notes），顺藤摸到这一串。
