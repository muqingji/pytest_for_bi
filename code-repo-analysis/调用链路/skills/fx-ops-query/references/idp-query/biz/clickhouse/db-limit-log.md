# db-limit-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 数据库限流日志，记录数据库访问的限流事件，包括系统负载、是否触发限流、数据库名称、方法调用等信息。用于数据库性能监控和限流策略分析。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_, createTime

---

## 表：biz_db_limit_log_dist

**说明**: 数据库限流日志，记录数据库访问的限流事件，包括系统负载、是否触发限流、数据库名称、方法调用等信息。用于数据库性能监控和限流策略分析。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_db_limit_log', rand(); Distributed('cluster01', 'logger', 'biz_db_limit_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(30)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志写入时间（纳秒级） |
| `_time_second_` | DateTime | 日志写入时间（秒级） |
| `appName` | Nullable(String) | 应用名称 |
| `cost` | Nullable(Int64) | 调用耗时（ms） |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `dbIp` | Nullable(String) | 数据库 IP |
| `dbName` | Nullable(String) | 数据库名称 |
| `ea` | Nullable(String) | 租户账号 |
| `fifteenLoad` | String |  |
| `fiveLoad` | Nullable(Float64) | 5 分钟负载 |
| `isLimit` | String |  |
| `level` | Nullable(Int32) | 限流级别 |
| `methodName` | Nullable(String) | 方法名称 |
| `methodType` | Nullable(String) | 方法类型 |
| `oneLoad` | Nullable(Float64) | 1 分钟负载 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `rate` | Nullable(Float64) | 限流速率 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | Nullable(String) | 服务端 IP |
| `spanId` | String | OpenTelemetry Span ID |
| `tenantId` | Nullable(String) | 租户 ID |
| `tenLoad` | Nullable(Float64) | 10 分钟负载 |
| `traceId` | Nullable(String) | 链路追踪 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
# 1. §2d 单 trace：同窗 + isLimit
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, tenantId, ea, appName, traceId, dbName, isLimit, level, rate, cost, methodName, fiveLoad
 FROM biz_db_limit_log_dist
 WHERE tenantId = '<TENANT_ID>'
  AND _time_second_ >= '<START_TIME>'
  AND _time_second_ <= '<END_TIME>'
  AND traceId = '<TRACE_ID>'
 ORDER BY _time_second_
 LIMIT 50" -j

# 2. 同窗爆发：按 appName / dbName 统计 isLimit=1
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT appName, dbName, count(*) AS limited_hits
 FROM biz_db_limit_log_dist
 WHERE _time_second_ >= '<START_TIME>'
  AND _time_second_ <= '<END_TIME>'
  AND isLimit = 1
 GROUP BY appName, dbName
 ORDER BY limited_hits DESC
 LIMIT 20" -j

# 3. 先 db-limit 捞 traceId（同窗 1～5 分钟），再反查 app_log（推荐）
# 3a — 限流 trace 列表（取 TOP N traceId + 对齐时间）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT traceId, appName, dbName, _time_second_, cost, methodName
 FROM biz_db_limit_log_dist
 WHERE _time_second_ >= '<START_TIME>'
  AND _time_second_ <= '<END_TIME>'
  AND isLimit = 1
  AND traceId != ''
 ORDER BY _time_second_ DESC
 LIMIT 20" -j

# 3b — 对 3a 中某一个 traceId：app_log 同窗 ≤6h（勿裸 traceId）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, level, logger, substring(msg, 1, 500) AS msg
 FROM app_log_dist
 WHERE traceId = '<TRACE_ID_FROM_3a>'
  AND _time_second_ >= '<START_TIME>'
  AND _time_second_ <= '<END_TIME>'
 ORDER BY _time_second_
 LIMIT 50" -j

# 3c — 同一 trace 只看与慢/限流相关的 WARN（StopWatch、MetadataStopWatch、methodName）
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, level, substring(msg, 1, 600) AS msg
 FROM app_log_dist
 WHERE traceId = '<TRACE_ID_FROM_3a>'
  AND _time_second_ >= '<START_TIME>'
  AND _time_second_ <= '<END_TIME>'
  AND level = 'WARN'
  AND (positionCaseInsensitive(msg, 'StopWatch') > 0
    OR positionCaseInsensitive(msg, 'ObjectDataServiceImpl') > 0)
 ORDER BY _time_second_
 LIMIT 30" -j
```

### 与 `app_log_dist` 的关系（反查路径）

1. **定性**：是否 db-limit → **`biz_db_limit_log_dist`** 且 **`isLimit = 1`**（§2d 主路径）。
2. **反查业务表现**：从限流行取 **`traceId`** + **`_time_second_` 窗**，再查 **`app_log_dist`**（禁止无时间窗）。
3. **关联特征**（2026-06-27 样例）：`biz_db_limit_log.cost` 常为 **1500ms**，同窗 `app_log` 出现 **`StopWatch 'ObjectDataServiceImpl.findBySearchQuery': running time = 1500 ms`** 等与 `methodName` 一致的 WARN；**`msg` 里未必出现 dbLimit 字样**，勿用关键词全表扫 `app_log` 代替步骤 1。
4. **关键词兜底**（仅步骤 1 无记录且仍怀疑）：窄窗 `msg` 搜 `dbLimit` / `数据库限流`（命中率低）。

### 易混淆（勿写入 §2d 正文替代）

| 机制 | 表 |
| --- | --- |
| Sentinel 接口限流 | `sentinel_block_dist`（`trace_id`、`resource_name`） |
| APL/API 函数限流 | `biz_log_function_dist`（`errorCode` 含 `RATE_LIMIT` / `extra.rateLimit`） |
| SQL 真慢 | `sql_slow_dist`、`mongo_slow_dist` |
| PG 锁 | `biz_log_pg_lock_dist` |

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
