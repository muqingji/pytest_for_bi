# 业务线索引

## 索引

| 数据库 | 文档 | 数量（live） |
| --- | --- | --- |
| MySQL | ./mysql.md | 12 个 |
| PostgreSQL | ./postgresql.md | 21 个 |
| MongoDB | ./mongodb.md | 44 个 |
| ClickHouse | ./clickhouse.md | 6 个 biz（含 semantic-*） |

> 数量以 `fx-ops idp show datasources` 实测为准；文档可能滞后。foneshare 2026-09-15 实测 84；hwcloud/hws 未必同步新增项。

## 快速导航

| 用途 | 业务线命令 |
| --- | --- |
| CRM 核心 | `paas`、`link-mankeep`、`paas-crm-biz` |
| BI（**双方言**） | `bi` → [bi.md](./bi.md)（postgresql 业务库 + clickhouse 数仓，**必须指明 dialect**） |
| 开放平台 / OAuth | `openapi`（postgresql；原 `open-oauth` 已合并） |
| 企业关系 / 微信 / 关联应用 | `enterprise-relation --dialect postgresql`（原 5 个 open/wechat PG biz 已合并） |
| 客服与工单 | `open-sail`、`online-consult`、`call-center` |
| 云之家 | `open-yunzhijia` |
| 外部 OA | `outer-oa` |
| EIP / ERP 同步策略 | `link-eip-data-sync`（双方言）、`link-eip-data-sync-1`、`link-eip-data-sync-747125`、`link-erp-data-sync` |
| 互联网盘 | `cross-enterprise-sharedisk`（勿用 `oa-netdisk`） |
| 互联公告 | `cross-notice`（勿用 Mongo `open-material`） |
| 医疗主数据 | `hospital-spider` |
| 组织与通讯 | `org-data`、`qixin` |
| 审批与工作流 | `paas-bpm`、`paas-workflow` |
| 日志与审计 | `crm-audit-log`、`biz-app-log` |

## 双方言硬规则

以下 biz 在 catalog 中登记了多个 dialect，**未指定 dialect 会 `dialect_required`**：

| biz | dialects | 推荐写法 |
| --- | --- | --- |
| `bi` | postgresql, clickhouse | `bi --dialect postgresql` / `bi-postgresql` |
| `enterprise-relation` | postgresql, mongodb | `enterprise-relation --dialect postgresql` |
| `open-message` | mysql, mongodb | `open-message --dialect mysql` |
| `link-eip-data-sync` | postgresql, mongodb | `link-eip-data-sync --dialect postgresql` / `link-eip-data-sync-postgresql` |

## 2026-08 合并映射（旧名 → 新名）

| 旧 biz | 新 biz |
| --- | --- |
| `open-oauth` | `openapi` |
| `open-link-app` | `enterprise-relation` (postgresql) |
| `wechat-proxy` | `enterprise-relation` (postgresql) |
| `wechat-notice` | `enterprise-relation` (postgresql) |
| `wechat-union` (postgresql) | `enterprise-relation` (postgresql)；mongodb 条目仍在 |
| `link-enterprise-relation` | `enterprise-relation` (postgresql) |
| `open-qywx` | `open-yunzhijia` |
| `eip-data-sync` / `eip_data_sync` / `syncdata` | `link-eip-data-sync --dialect postgresql`（Mongo 缓冲用 `--dialect mongodb`；独立库 `link-eip-data-sync-1` / `link-eip-data-sync-747125`） |

## 表级筛选文档

| 方言 | 索引 |
| --- | --- |
| MySQL | [mysql/index.md](./mysql/index.md) |
| PostgreSQL | [postgresql/index.md](./postgresql/index.md) |
| MongoDB | [mongodb/index.md](./mongodb/index.md) |
| ClickHouse | [clickhouse/index.md](./clickhouse/index.md)（`biz-app-log` 另见 [clickhouse.md](./clickhouse.md) 单表目录；`system` 库见 [system-db.md](./clickhouse/system-db.md)） |

拼 SQL 通用规则：[idp-query-filter-hint.md](../../idp-query-filter-hint.md)

## 相关文档

- [query 入口](../../idp-query.md)
- [filterHint 拼 SQL](../../idp-query-filter-hint.md)
- [SQL 查询规则](../../idp-query-sql.md)
- [MongoDB 查询规则](../../idp-query-mongodb.md)
- [ClickHouse 查询规则](../../idp-query-clickhouse.md)
- [ClickHouse `system` 库](./clickhouse/system-db.md)
