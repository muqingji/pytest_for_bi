# biz-sql-stat

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: SQL 统计日志表，按应用、数据库、表名和 SQL 操作类型聚合记录 SQL 访问次数，用于发现热点库表和读写操作突增

**租户ID字段**: `tenantId`

**时间字段**: _time_second_, createTime

---

## 表：biz_sql_stat_dist

**说明**: SQL 统计日志表，按应用、数据库、表名和 SQL 操作类型聚合记录 SQL 访问次数，用于发现热点库表和读写操作突增

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_sql_stat', rand(); Distributed('cluster01', 'logger', 'biz_sql_stat', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(60)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime | 日志采集时间（秒级） |
| `affectedCount` | Nullable(Int32) | 影响行数 |
| `appName` | Nullable(String) | 应用名称 |
| `batchCount` | Nullable(Int32) | 批量操作次数 |
| `callerIp` | Nullable(String) | 调用方 IP |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 统计生成时间 |
| `dbIp` | Nullable(String) | 数据库实例 IP 和端口 |
| `dbName` | Nullable(String) | 数据库名称 |
| `deleteCount` | Nullable(Int32) | DELETE 次数 |
| `explainCount` | Nullable(Int32) | EXPLAIN 次数 |
| `insertCount` | Nullable(Int32) | INSERT 次数 |
| `joinCount` | Nullable(Int32) | JOIN 次数 |
| `otherCount` | Nullable(Int32) | 其他 SQL 次数 |
| `profile` | Nullable(String) | 环境标识 |
| `selectCount` | Nullable(Int32) | SELECT 次数 |
| `sumCount` | Nullable(Int32) | SUM 聚合次数 |
| `tableName` | Nullable(String) | 数据表名称 |
| `tenantId` | Nullable(String) | 租户 ID |
| `totalCount` | Nullable(Int32) | SQL 总次数 |
| `updateCount` | Nullable(Int32) | UPDATE 次数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
# 查询某数据库的热点表
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT dbName, tableName, SUM(totalCount) as total, SUM(insertCount) as inserts, SUM(updateCount) as updates, SUM(deleteCount) as deletes, SUM(selectCount) as selects FROM biz_sql_stat_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY dbName, tableName ORDER BY total DESC LIMIT 20"

# 查询某应用SQL操作分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT appName, SUM(totalCount) as total, SUM(selectCount) as selects, SUM(insertCount) as inserts, SUM(updateCount) as updates FROM biz_sql_stat_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND appName = '<app>' GROUP BY appName"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
