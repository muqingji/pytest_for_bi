# biz 表级筛选文档

各方言目录下的 `<biz>.md` 汇总该业务线的 **表级租户筛选**（租户列、时间列、WHERE 模板）与可选的 **表字段说明**，供 Agent 在 `table get` 之外快速对照复杂表。

- 权威来源：执行前仍以 `show columns <biz> <name> -j` 返回的 `filterHint` 为准
- ClickHouse 单表字段定义仍以 `clickhouse/<table>.md` 为准
- 手写维护页（含 `<!-- fx-ops-query:curated -->`）优先于批量整理的同名 biz 文档

## 文档结构

每个 `<dialect>/<biz>.md` 通常含：

- **表级筛选**：租户列、时间列、WHERE 模板（含复杂子查询表）
- **表字段说明**（若有整理）：字段 | 类型 | 说明
- ClickHouse 日志：完整字段定义仍以 `clickhouse/<table>.md` 为准

- 通用带 filter 参数查询语法：见上层 [idp-query-filter-hint.md](../../idp-query-filter-hint.md)
