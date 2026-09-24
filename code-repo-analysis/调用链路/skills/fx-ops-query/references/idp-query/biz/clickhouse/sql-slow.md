# sql-slow

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: ClickHouse & PG 慢 SQL 查询明细分布式表，收集平台中所有的慢查询执行计划、查询用户与消耗资源。

**租户ID字段**: `ea`

**时间字段**: _time_second_, stamp

---

## 表：sql_slow_dist

**说明**: ClickHouse & PG 慢 SQL 查询明细分布式表，收集平台中所有的慢查询执行计划、查询用户与消耗资源。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster04', 'logger', 'sql_slow_local', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_nanosecond_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime('Asia/Shanghai') | 事件写入 ClickHouse 的秒级时间戳 |
| `app` | String | 应用名称，通常指运行的微服务名称，例如 fs-uc-provider |
| `companyName` | String | 企业名称 |
| `cost` | Int32 | 操作耗时，单位为毫秒 (ms) |
| `dbName` | String | 数据库name |
| `ea` | String | 企业账号/租户账号名称 |
| `ei` | String | 企业唯一标识 ID (Enterprise ID) |
| `extra` | String | 扩展信息 |
| `fail` | Bool | 是否失败 |
| `ip` | String | 产生日志的主机 IP 地址 |
| `parameter` | String | SQL参数 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `query` | String | 查询SQL语句 |
| `queryMD5` | String |  |
| `readBytesLength` | Int32 | 读取字节长度 |
| `readStringLength` | Int32 | 读取字符串长度 |
| `reqId` | String | 请求id |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `size` | Int32 | 大小或数据包容量（字节数） |
| `spanId` | String | OpenTelemetry Span ID |
| `stamp` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 事件发生的时间戳 |
| `tagName` | String | 标签名 |
| `traceId` | String | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `type` | String | SQL类型 |
| `uid` | String | 操作用户的唯一标识 ID |
| `url` | String | HTTP 请求的完整 URL 路径 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `uid` |
| 追踪ID | `traceId` |
| 请求ID | `reqId` |
| 时间 | `_time_second_`, `stamp` |

### 查询示例

```bash
# 查询某应用近1小时慢SQL TOP20
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, app, dbName, cost, query FROM sql_slow_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND cost > 1000 ORDER BY cost DESC LIMIT 20"

# 统计各数据库慢SQL数量与平均耗时
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT dbName, COUNT(*) as cnt, avg(cost) as avg_cost, max(cost) as max_cost FROM sql_slow_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY dbName ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
