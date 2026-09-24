# mongo-slow

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: MongoDB慢查询日志表，记录慢查询的集合、操作类型、执行计划、锁信息和耗时统计

**租户ID字段**: `tenantId`

**时间字段**: stamp

---

## 表：mongo_slow_dist

**说明**: MongoDB慢查询日志表，记录慢查询的集合、操作类型、执行计划、锁信息和耗时统计

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'mongo_slow_local', rand()); Distributed('cluster01', 'logger', 'mongo_slow_local', rand()) |
| PARTITION BY | `toYYYYMMDD(stamp)` |
| PRIMARY KEY | `stamp` |
| ORDER BY | `stamp` |
| TTL | — |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `stamp` | DateTime64(3, 'Asia/Shanghai') | 慢查询发生时间戳 |
| `level` | LowCardinality(String) | 日志级别（I=Info） |
| `category` | LowCardinality(String) | 操作类型（WRITE/COMMAND等） |
| `conn_id` | Nullable(String) | 数据库连接ID |
| `collection` | Nullable(String) | 操作的数据库集合名称 |
| `appName` | Nullable(String) | 发起查询的应用名称 |
| `tenantId` | String | 租户 ID |
| `cost` | Nullable(UInt32) | 查询耗时（毫秒） |
| `keysExamined` | Nullable(UInt32) | 索引扫描数 |
| `docsExamined` | Nullable(UInt32) | 文档扫描数 |
| `nreturned` | String |  |
| `numYields` | Nullable(UInt32) | 查询让出次数 |
| `reslen` | String |  |
| `cursorid` | String |  |
| `protocol` | String |  |
| `keysInserted` | Nullable(UInt32) | 插入文档涉及的索引键数 |
| `keysDeleted` | Nullable(UInt32) | 删除文档涉及的索引键数 |
| `nMatched` | Nullable(UInt32) | 匹配文档数 |
| `nModified` | Nullable(UInt32) | 修改文档数 |
| `ninserted` | String |  |
| `ndeleted` | String |  |
| `replanned` | String |  |
| `upsert` | String |  |
| `code` | String |  |
| `writeConflicts` | String |  |
| `cursorExhausted` | String |  |
| `fromMultiPlanner` | String |  |
| `hasSortStage` | String |  |
| `locks_Global_acquireCount_r` | Nullable(UInt32) | 全局读锁获取次数 |
| `locks_Global_acquireCount_w` | Nullable(UInt32) | 全局写锁获取次数 |
| `locks_Database_acquireCount_r` | String |  |
| `locks_Database_acquireCount_w` | Nullable(UInt32) | 数据库级写锁获取次数 |
| `locks_Database_acquireWaitCount_w` | String |  |
| `locks_Database_timeAcquiringMicros_w` | String |  |
| `locks_Collection_acquireCount_r` | String |  |
| `locks_Collection_acquireCount_w` | Nullable(UInt32) | 集合级写锁获取次数 |
| `locks_Metadata_acquireCount_w` | Nullable(UInt32) | 元数据写锁获取次数 |
| `locks_oplog_acquireCount_r` | String |  |
| `locks_oplog_acquireCount_w` | Nullable(UInt32) | oplog写锁获取次数 |
| `planSummary` | Nullable(String) | 执行计划摘要 |
| `query` | Nullable(String) | 查询条件 |
| `command` | Nullable(String) | 执行的命令类型 |
| `command_params` | String |  |
| `originatingCommand` | String |  |
| `exception` | String |  |
| `locks` | Nullable(String) | 锁信息详情（JSON） |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 时间 | `stamp` |

### 查询示例

```bash
# 查询近1小时慢MongoDB操作TOP20
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, tenantId, appName, collection, category, cost, docsExamined, nreturned FROM mongo_slow_dist WHERE stamp >= now() - INTERVAL 1 HOUR ORDER BY cost DESC LIMIT 20"

# 统计各集合慢查询分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT collection, COUNT(*) as cnt, avg(cost) as avg_cost, max(docsExamined) as max_docs FROM mongo_slow_dist WHERE stamp >= now() - INTERVAL 1 HOUR GROUP BY collection ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
