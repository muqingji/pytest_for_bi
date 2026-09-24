# log-error

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 应用错误日志，记录各微服务运行时产生的 ERROR 级别日志，包括错误消息、异常堆栈、应用名称等。用于错误监控和故障排查。

**租户ID字段**: `ei`

**时间字段**: _time_second_

---

## 表：log_error_dist

**说明**: 应用错误日志，记录各微服务运行时产生的 ERROR 级别日志，包括错误消息、异常堆栈、应用名称等。用于错误监控和故障排查。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'log_error', rand(); Distributed('cluster01', 'logger', 'log_error', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(366)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志写入时间（纳秒级） |
| `_time_second_` | DateTime('Asia/Shanghai') | 日志写入时间（秒级） |
| `app` | Nullable(String) | 应用名称 |
| `cluster` | LowCardinality(String) | K8s 集群 |
| `companyName` | String | 企业名称 |
| `dbName` | String | 数据库名称 |
| `ea` | String | 租户账号 |
| `ei` | String | 租户 ID |
| `error` | String | 错误信息 / 异常堆栈 |
| `level` | LowCardinality(String) | 日志级别（ERROR） |
| `loggerName` | Nullable(String) | Logger 名称（Java 类名）。**本表字段名是 `loggerName`，不是 `logger`**（`app_log_dist` 才是 `logger`） |
| `msg` | Nullable(String) | 错误消息 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `pod` | Nullable(String) | Pod 名称 |
| `profile` | Nullable(String) | 环境标识 |
| `reqId` | Array(String) | 请求 ID 列表 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `serverIp` | Nullable(String) | 服务端 IP |
| `spanId` | String | OpenTelemetry Span ID |
| `threadName` | Nullable(String) | 线程名称 |
| `token` | String | Token / 异常类型标识（视表语义而定） |
| `traceId` | String | 链路追踪 ID |
| `uid` | String | 用户 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `uid` |
| 追踪ID | `traceId` |
| 请求ID | `reqId` |
| 时间 | `_time_second_` |

### 查询示例

RCA 默认投影（列名以字段定义为准；时间用字符串窗或 `now() - INTERVAL`，勿对 DateTime 列再包 `toDateTime(...)-INTERVAL`）：

```bash
# 按 traceId + 时间窗拉错误堆栈
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT traceId, _time_second_, app, level, loggerName, msg, error, ei, ea, pod FROM log_error_dist WHERE traceId = '<traceId>' AND _time_second_ >= '<T0>' AND _time_second_ <= '<T1>' ORDER BY _time_second_ DESC LIMIT 50" -j

# 按租户 + 近 1 小时
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, app, pod, loggerName, substring(msg, 1, 500) AS content, substring(error, 1, 500) AS error FROM log_error_dist WHERE ei = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20" -j

fx-ops idp --profile <profile> query biz-app-log --sql "SELECT app, COUNT(*) as cnt FROM log_error_dist WHERE ei = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY app ORDER BY cnt DESC" -j

# Kafka 客户端 ERROR（列名 loggerName；空结果 ≠ 无 lag）
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT app, loggerName, level, count() AS cnt
FROM log_error_dist
WHERE _time_second_ > now() - INTERVAL 3 HOUR
  AND (
    loggerName IN (
      'com.fxiaoke.support.KConsumer',
      'com.fxiaoke.support.ConsumerRunner',
      'com.fxiaoke.support.SingleThreadConsumer',
      'com.fxiaoke.support.KafkaSender',
      'com.fxiaoke.support.SenderManager',
      'com.fxiaoke.support.KafkaUtils'
    )
    OR loggerName LIKE 'com.fxiaoke.kafka.support.%'
    OR loggerName LIKE 'org.apache.kafka.%'
  )
GROUP BY app, loggerName, level
ORDER BY cnt DESC
LIMIT 40
" -j
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
