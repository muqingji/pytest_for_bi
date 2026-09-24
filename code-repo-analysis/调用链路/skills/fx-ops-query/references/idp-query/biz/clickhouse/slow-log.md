# slow-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: SQL 慢查询日志表，记录执行较慢的 SQL 语句详情，包括查询语句、耗时、数据库名、影响行数等

**租户ID字段**: `ei`, `ea`

**时间字段**: _time_second_, stamp, _time_nanosecond_

---

## 表：slow_log_dist

**说明**: SQL 慢查询日志表，记录执行较慢的 SQL 语句详情，包括查询语句、耗时、数据库名、影响行数等

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'slow_log', rand(); Distributed('cluster01', 'logger', 'slow_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_nanosecond_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `stamp`, `_time_nanosecond_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime('Asia/Shanghai') | 日志采集时间（秒级） |
| `app` | String | 应用名称 |
| `companyName` | String | 公司名称 |
| `cost` | Int32 | 耗时(ms)。**是 `cost`，不是 `latency`** |
| `dbName` | String | 数据库名称。**是 `dbName`，不是 `database`/`table`** |
| `ea` | String | 租户账号 |
| `ei` | String | 租户ID |
| `extra` | String | 扩展信息 |
| `fail` | Bool | 是否失败 |
| `ip` | String | 数据库服务器IP |
| `parameter` | String | 参数 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | String | 环境标识（K8s namespace / cms_profile） |
| `query` | String | SQL 查询语句（诊断必选；**不是 `sqlText`**） |
| `queryMD5` | String | SQL语句MD5 |
| `readBytesLength` | Int32 | 读取字节数 |
| `readStringLength` | Int32 | 读取字符串长度 |
| `reqId` | String | 请求ID |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `size` | Int32 | 影响行数 |
| `spanId` | String | OpenTelemetry Span ID |
| `stamp` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 统计时间戳 |
| `tagName` | String | 标签名 |
| `traceId` | String | 追踪ID |
| `type` | String | 数据库类型（如 postgresql） |
| `uid` | String | 用户ID |
| `url` | String | 数据库连接URL |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `uid` |
| 追踪ID | `traceId` |
| 请求ID | `reqId` |
| 时间 | `_time_second_`, `stamp`, `_time_nanosecond_` |

### 查询示例

RCA 默认投影（**必含 `query`/`cost`/`dbName`**；勿写 `database`/`table`/`latency`/`sqlText`）：

```bash
# 按 traceId + 时间窗
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT traceId, _time_second_, app, dbName, cost, size, substring(query, 1, 500) AS query, ei FROM slow_log_dist WHERE traceId = '<traceId>' AND _time_second_ >= '<T0>' AND _time_second_ <= '<T1>' ORDER BY cost DESC LIMIT 50" -j

fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, app, cost, dbName, substring(query, 1, 500) AS query FROM slow_log_dist WHERE ei = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY cost DESC LIMIT 20" -j

fx-ops idp --profile <profile> query biz-app-log --sql "SELECT count() AS cnt, avg(cost) AS avg_ms, max(cost) AS max_ms FROM slow_log_dist WHERE ei = '123' AND _time_second_ >= now() - INTERVAL 30 MINUTE" -j
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
