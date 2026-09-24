# biz-log-pg-lock

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: PostgreSQL 数据库锁监控日志分布式表，记录后端 PostgreSQL 实例的排他锁、死锁及慢查询事件。

**租户ID字段**: 无

**时间字段**: _time_second_, createTime

---

## 表：biz_log_pg_lock_dist

**说明**: PostgreSQL 数据库锁监控日志分布式表，记录后端 PostgreSQL 实例的排他锁、死锁及慢查询事件。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_pg_lock', rand(); Distributed('cluster01', 'logger', 'biz_log_pg_lock', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime('Asia/Shanghai') | 事件写入 ClickHouse 的秒级时间戳 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建时间 |
| `dbIp` | LowCardinality(String) | 数据库ip |
| `dbName` | LowCardinality(String) | 数据库name |
| `lockAge` | Int64 | 锁age |
| `lockedPage` | Int32 | 锁定页号 |
| `lockedTuple` | Int32 | 锁定元组号 |
| `lockMode` | LowCardinality(String) | 锁mode |
| `lockPid` | Int32 | 锁pid |
| `lockType` | LowCardinality(String) | 锁type |
| `query` | String | 查询SQL语句 |
| `queryStartTime` | Int64 | 查询开始时间 |
| `tableName` | LowCardinality(String) | 表名 |
| `username` | LowCardinality(String) | 数据库用户名 |
| `waitAge` | Int64 | 等待时长 |
| `waitMode` | LowCardinality(String) | 等待模式 |
| `waitPage` | Int32 | 等待页号 |
| `waitPid` | Int32 | 等待进程ID |
| `waitQuery` | String | 等待查询SQL语句 |
| `waitQueryStartTime` | Int64 | 等待查询开始时间 |
| `waitTuple` | Int32 | 等待元组号 |
| `waitXactStartTime` | Int64 | 等待事务开始时间 |
| `xactStartTime` | Int64 | 事务开始时间 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
# 查询当前活跃的锁
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, dbName, tableName, lockType, lockMode, lockPid, waitPid, lockAge, query FROM biz_log_pg_lock_dist WHERE _time_second_ >= now() - INTERVAL 15 MINUTE ORDER BY lockAge DESC LIMIT 50"

# 统计各数据库锁分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT dbName, lockMode, COUNT(*) as cnt, max(lockAge) as max_age FROM biz_log_pg_lock_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY dbName, lockMode ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
