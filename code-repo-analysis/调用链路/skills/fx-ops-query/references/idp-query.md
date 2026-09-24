# fx-ops idp query

业务数据直查入口。先用最小命令确认数据源，再按方言读取对应文档。

> **v4.8.1+ 迁移**：查询库/表/列（`catalog`、`table list`、`table get`）已迁移至 `fx-ops idp show` 子命令。`idp query` 仅保留数据直查（`--sql` / `--collection`）。

## 选择规则

| 场景 | 读取 | 命令模板 |
| --- | --- | --- |
| 不知道 biz | 本文 | `fx-ops idp --profile <profile> show datasources -j` |
| 已知 SQL 表，数据源是 MySQL/PostgreSQL | idp-query-sql.md | fixed：`query <biz> --sql "..."`；tenant-route：`query <biz> -t <id> --sql "..."` |
| 已知 MongoDB 集合 | idp-query-mongodb.md | `fx-ops idp query <biz> [--dialect mongodb] [--tenant-id <id>] --collection <name> --filter '<JSON>' -j` |
| 查日志、审计、traceId、慢查询 | idp-query-clickhouse.md | 先按场景选表并 count 预估，再 `fx-ops idp query <biz> --sql "<SQL>" -j` |
| 查 ClickHouse `system` 库（表/进程/query_log） | idp-query/biz/clickhouse/system-db.md | `fx-ops idp query <biz> --sql "SHOW DATABASES"` / `SHOW TABLES FROM system` / `SELECT … FROM system.*` |
| 只知道业务含义 | idp-query/biz/index.md | 先定位 biz，再回到方言文档；注意 2026-08 合并旧名映射 |
## 发现命令

```bash
fx-ops idp --profile <profile> show datasources -j
```

表发现与表结构查询见 idp-query-table.md。

## 公共参数

| 参数 | 说明 |
| --- | --- |
| `--tenant-id`, `-t` | 租户 ID；`routeMode=fixed` 可免，`tenant-route` 必填（见 idp-query-table.md / 各 biz 文档） |
| `--dialect` | 双方言 biz 必填：`bi` / `enterprise-relation` / `open-message` / `link-eip-data-sync`（或 `<biz>-<dialect>`） |
| `--sql` / `--sql-file` / `--sql-from-stdin` | SQL 三选一 |
| `--collection` / `--filter` / `--projection` / `--sort` | MongoDB 查询参数 |
| `--timeout` | 查询超时，默认 30000ms |
| `--max-rows` | 最大返回行数，默认 1000 |
| `-j`, `--json` | 默认使用 JSON，减少后续解析成本 |

## 最小工作流

```bash
# 1. 定位 biz 和方言（禁止死记已删除旧名）
fx-ops idp --profile <profile> show datasources -j

# 2. 发现表和字段 → 见 idp-query-table.md

# 3. 读取方言文档后执行查询
fx-ops idp --profile <profile> query openapi --sql "SELECT ... LIMIT 20" -j
fx-ops idp --profile <profile> query paas --tenant-id <id> --sql "SELECT ... LIMIT 20" -j
fx-ops idp --profile <profile> query enterprise-relation --dialect postgresql --sql "SELECT ... LIMIT 20" -j
```

## 按需索引

- filterHint 与表级筛选模板：idp-query-filter-hint.md
- 各 biz 表级筛选：`idp-query/biz/<dialect>/index.md`
- 表发现与表结构：idp-query-table.md
- SQL 规则：idp-query-sql.md
- MongoDB 规则：idp-query-mongodb.md
- ClickHouse 安全流程：idp-query-clickhouse.md
- ClickHouse `system` 库：idp-query/biz/clickhouse/system-db.md
- SOQL 函数参考：idp-query/soql-functions.md
- 业务线索引：idp-query/biz/index.md
