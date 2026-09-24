# fx-ops idp show tables / show columns — 表发现与表结构

> **v4.8.1+ 迁移**：`idp query catalog` → `idp show datasources` | `idp query table list` → `idp show tables` | `idp query table get --table <t>` → `idp show columns <ds> <t>`（`<table>` 改为位置参数，不再使用 `--table` flag）。`idp query` 仅保留数据直查（`--sql` / `--collection`）。

在执行查询前，先用 `show tables` 确认目标 datasource 下有哪些表，再用 `show columns` 获取字段定义。

## 命令

```bash
# 列出业务下所有表
fx-ops idp --profile <profile> show tables <biz> -j

# 获取指定表的结构（字段名、类型、索引等）
fx-ops idp --profile <profile> show columns <biz> <table> -j

# ClickHouse 日志统一使用 biz-app-log
fx-ops idp --profile <profile> show tables biz-app-log -j
fx-ops idp --profile <profile> show columns biz-app-log log_error_dist -j
```

## 参数

| 参数 | 说明 |
| --- | --- |
| `<biz>` | 业务线名称，通过 `fx-ops idp show datasources -j` 获取 |
| `<table>` | 表名，`show columns` 时的位置参数（必填） |
| `--tenant-id`, `-t` | 租户 ID；**`routeMode=fixed` 可免**（当前 MySQL 全部 + 多数 PG fixed，如 `openapi`/`enterprise-relation`/`outer-oa`/`oncall`/`tenant-router`）；**`tenant-route` 必填**（如 `paas`/`bi`/`feed`）。以各 biz 文档「路由」行为准 |
| `--dialect` | 数据库方言；**双方言 biz 必填**：`bi`、`enterprise-relation`、`open-message`、`link-eip-data-sync`（或用 `<biz>-<dialect>` 别名） |
| `-j`, `--json` | JSON 输出 |

## 典型用法

```bash
# fixed 路由：免 --tenant-id
fx-ops idp --profile <profile> show tables oncall -j
fx-ops idp --profile <profile> show tables openapi -j
fx-ops idp --profile <profile> show tables enterprise-relation --dialect postgresql -j

# tenant-route：必填 --tenant-id
fx-ops idp --profile <profile> show tables paas --tenant-id <id> -j
fx-ops idp --profile <profile> show columns paas <table> --tenant-id <id> -j
```

## filterHint（JSON 必读）

`show columns` 响应中的 `table.filterHint`：

| 字段 | 说明 |
| --- | --- |
| `tenantColumn` | 租户列名、类型、是否索引 |
| `timeColumn` | 推荐时间过滤列（可为 null） |
| `queryTemplate` | WHERE 片段模板（`$tenantId` / `$tenantAccount`） |

拼 SQL 规则与各 biz 表级清单见 [idp-query-filter-hint.md](./idp-query-filter-hint.md) 与 `idp-query/biz/<dialect>/<biz>.md`。

## 使用场景

- 不确定表名或字段名时，先 `show tables` 再 `show columns`
- 怀疑字段/Schema 变更时，用 `show columns` 确认当前结构
- 首次接触某个 biz，先读 `idp-query/biz/<dialect>/<biz>.md`（复杂筛选表）再 `show columns`

## 注意事项

- `show tables` / `show columns` 主要用于 MySQL、PostgreSQL、MongoDB 表或集合发现
- ClickHouse 查日志时优先读目标真实表的单表 reference（`references/idp-query/biz/clickhouse/`），因为租户字段、时间字段和索引字段差异更重要
- ClickHouse `system` 库走 sql-query 元数据路径（`SHOW DATABASES` / `SHOW TABLES FROM system` / `SELECT FROM system.*`），见 [system-db.md](./idp-query/biz/clickhouse/system-db.md)；`show tables` CLI 列的是业务表，不是 `system.*`
- 应用日志、CEP 网关、慢请求、慢 SQL、SQL 统计等日志的表发现和查询统一使用 `biz-app-log`，再指定真实表名
- `--tenant-id` 是否必填取决于具体 biz，不是所有数据源都需要
