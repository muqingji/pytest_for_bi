# paas-op-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: PaaS 平台操作日志分布式表，记录数据库变更操作（CDC/OpLog），包括插入、更新、删除操作的 before/after 数据快照，用于数据审计和变更追踪。

**租户ID字段**: `ei`, `ea`

**时间字段**: _time_second_

**历史覆盖**: TTL 为 180 天。查询窗口超出实际保留范围时标记 `out_of_range` 或 `source_gap`，不能把空结果解释为没有数据库变更。

**空值语义**: `before`、`after` 和 `object_describe_api_name` 可能为空。只有 before/after 均非空、JSON 可解析并能定位到布局结构时，才允许报告具体组件差异。

---

## 表：paas_oplog_dist

**说明**: PaaS 平台操作日志分布式表，记录数据库变更操作（CDC/OpLog），包括插入、更新、删除操作的 before/after 数据快照，用于数据审计和变更追踪。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'paas_oplog_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(ei, ea, _time_second_)` |
| ORDER BY | `(ei, ea, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(180)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 操作时间（秒级精度） |
| `after` | String | 变更后数据（JSON） |
| `before` | String | 变更前数据（JSON） |
| `companyName` | LowCardinality(String) | 企业名称 |
| `db` | String | 数据库名称，如 paas_metadata |
| `ea` | LowCardinality(String) | 租户账号（enterprise account） |
| `ei` | LowCardinality(String) | 租户 ID（enterprise ID） |
| `id` | String | 记录唯一 ID（MongoDB ObjectId 格式） |
| `object_describe_api_name` | String | 对象描述 API 名称 |
| `op` | LowCardinality(String) | 操作类型：I(Insert)/U(Update)/D(Delete)。同一 `id` 同时刻相邻 `D + I` 是更新候选，不是删除后重建；整对象保存可能重写未变化字段。 |
| `schema` | String | 数据库 schema，如 public |
| `status` | LowCardinality(String) | 操作状态 |
| `table` | String | 表名称，如 i18n_entry |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 布局更新候选：精确租户、表和半开时间窗，避免 SELECT * 扫大结果
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, id, op, db, schema, `table`, ei, ea, object_describe_api_name, before, after FROM paas_oplog_dist WHERE ei = '<EI>' AND ea = '<EA>' AND db = 'paas_metadata' AND `table` = 'mt_ui_component' AND _time_second_ >= toDateTime('<START>') AND _time_second_ < toDateTime('<END>') ORDER BY _time_second_ ASC LIMIT 500"
```

若路由只支持 EI 或只返回 EA，按实时 schema 和租户路由文档保留可用的精确租户条件；不能静默放宽成跨租户查询。

## before/after 覆盖检查

在读取大段 JSON 前先做数量和覆盖统计：

```sql
SELECT
  count() AS total,
  countIf(length(trim(before)) > 0) AS before_non_empty,
  countIf(length(trim(after)) > 0) AS after_non_empty,
  countIf(length(trim(before)) > 0 AND length(trim(after)) > 0) AS comparable,
  min(_time_second_) AS first_time,
  max(_time_second_) AS last_time
FROM paas_oplog_dist
WHERE ei = '<EI>'
  AND ea = '<EA>'
  AND db = 'paas_metadata'
  AND `table` = 'mt_ui_component'
  AND _time_second_ >= toDateTime('<START>')
  AND _time_second_ < toDateTime('<END>')
```

`object_describe_api_name` 为空时不能按该列过滤掉记录，应使用布局 API、对象信息、trace、时间和 before/after 内容做后续归并。仅有 version、更新时间或单侧 before/after 时，报告为 `metadata_only` 或 `source_gap`，不能补写具体字段、组件属性或操作人。

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
