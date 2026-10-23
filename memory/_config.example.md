# 系统配置

> Markdown 表格即配置（§8.1 要求 Markdown 是唯一事实源，不引入 yaml/json 状态文件）。
> 开源模板见 `memory/_config.example.md`；本文件是你的实例配置，**不要提交进仓库**。
> 脚本读取方式：`scripts/memconfig.py`。缺省键会回落到内置默认值，因此新增键不会破坏旧库。

| 键 | 值 | 说明 |
|---|---|---|
| user_name | 你的名字 | 导出物标题、报告里显示的名字 |
| self_dir | 你的名字 | `people/` 下代表本人的子目录名 |
| timezone | Asia/Shanghai | 所有时间戳的时区 |
| export_title | 个人档案 | 导出物标题后缀 |
| payroll_enabled | false | 是否启用薪资↔公积金互洽规则；无此数据的用户设 false |
| payroll_salary_id |  | 互洽规则引用的薪资条目 id |
| payroll_fund_id |  | 互洽规则引用的公积金条目 id |
| payroll_param_id |  | 互洽规则引用的政策参数条目 id |
| birth_id_keyword | birth | 用于识别"出生日期"类条目 id 的关键词 |
| semantic_enabled | true | 是否启用语义重合检查 |
| semantic_threshold | 0.30 | 全库语义重合报 INFO 的阈值 |
