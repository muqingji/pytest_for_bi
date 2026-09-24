# bi（多方言）

`bi` 在 catalog 中对应 **两条独立数据源**（PostgreSQL 业务库 + ClickHouse 数仓），使用前 **必须指明方言**，不可默认。

| 方言 | 说明 | 文档 |
| --- | --- | --- |
| **postgresql** | BI 智能分析业务库（仪表盘、报表、维度、度量） | [postgresql/bi.md](./postgresql/bi.md) |
| **clickhouse** | 数据仓库 BI（产品、许可证、模块维度）；含 tables 字段说明 | [clickhouse/bi.md](./clickhouse/bi.md) |

与 `bi-system`（PostgreSQL BI 引擎同步）不同，不要混淆。

## CLI 用法（必读）

`biz` 重名时，执行查询使用带方言后缀的子命令（`bi-postgresql` / `bi-clickhouse`）：

| 操作 | PostgreSQL | ClickHouse |
| --- | --- | --- |
| 表列表 / 表结构 | `show tables bi --dialect postgresql -t <EI> -j` | `show tables bi --dialect clickhouse -t <EI> -j`（租户按表） |
| 执行 SQL | `query bi-postgresql -t <EI> --sql "..." -j` | `query bi-clickhouse --sql "..." -j` |

**禁止**在未带 `--dialect` 的情况下对 `bi` 使用 `show tables` / `show columns`：未显式指定方言时可能命中错误库。

## 选型

- 查 **租户侧 BI 配置、报表元数据、业务表数据** → **postgresql**
- 查 **数仓聚合、许可证/模块统计类 CH 表** → **clickhouse**（配合 [ClickHouse 规则](../../idp-query-clickhouse.md)）

拼 WHERE 规则见 [idp-query-filter-hint.md](../../idp-query-filter-hint.md)。
