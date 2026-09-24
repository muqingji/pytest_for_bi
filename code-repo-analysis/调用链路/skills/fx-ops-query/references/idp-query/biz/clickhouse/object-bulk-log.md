# object-bulk-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 对象数据批量操作日志，记录 ES 索引的批量操作（索引、删除等），包含操作类型、索引名、文档数等

**租户ID字段**: `tenantId`

**时间字段**: _time_second_

---

## 表：object_data_bulk_log_dist

**说明**: 对象数据批量操作日志，记录 ES 索引的批量操作（索引、删除等），包含操作类型、索引名、文档数等

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'object_data_bulk_log_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(_time_second_, tenantId, objectApiName, action, clusterName)` |
| ORDER BY | `(_time_second_, tenantId, objectApiName, action, clusterName)` |
| TTL | `_time_second_ + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 记录时间 |
| `action` | LowCardinality(String) | 操作类型（index/delete 等） |
| `appName` | LowCardinality(String) | 应用名 |
| `clusterName` | LowCardinality(String) | ES 集群名 |
| `index` | String | ES 索引名 |
| `nodes` | Array(String) | ES 节点列表 |
| `num` | Int64 | 文档数量 |
| `objectApiName` | String | 对象 API 名称 |
| `profile` | LowCardinality(String) | 环境 |
| `tenantId` | String | 租户ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查询租户对象批量操作日志
fx-ops idp --profile <profile> query biz-app-log --tenant-id 1 --sql "SELECT _time_second_, tenantId, objectApiName, action, num FROM object_data_bulk_log_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
