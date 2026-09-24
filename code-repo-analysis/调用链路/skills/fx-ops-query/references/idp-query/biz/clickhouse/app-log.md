# app-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 应用日志分布式表，存储后端 Java/Dubbo 应用的运行日志（按 pod 采集），包括日志级别、调用链追踪、RPC 信息等。 查询必须带 _time_second_ 时间窗（平台 timeGuard ≤24h，建议 1–2h）； 必须优先过滤 app（主键前缀），有环境时再加 profile； msg 子串搜索用 LIKE '%…%'（n≥3 可吃 ngrambf_v1 跳数索引），不要用 hasToken（那是 tokenbf 语义，本表 idx_msg 为 ngram）。

**时间字段**: _time_second_

> [!CAUTION]

---

## 表：app_log_dist

**说明**: 应用日志分布式表，存储后端 Java/Dubbo 应用的运行日志（按 pod 采集），包括日志级别、调用链追踪、RPC 信息等。 查询必须带 _time_second_ 时间窗（平台 timeGuard ≤24h，建议 1–2h）； 必须优先过滤 app（主键前缀），有环境时再加 profile； msg 子串搜索用 LIKE '%…%'（n≥3 可吃 ngrambf_v1 跳数索引），不要用 hasToken（那是 tokenbf 语义，本表 idx_msg 为 ngram）。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster02', 'logger', 'app_log_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(app, profile, _time_second_)` |
| ORDER BY | `(app, profile, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(14)` |
| 跳数/二级索引 | **INDEX**: `idx_trace_id`: traceId TYPE set(0), GRANULARITY 8 |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志时间（纳秒级精度） |
| `_time_second_` | DateTime64(3, 'Asia/Shanghai') | 日志时间（秒级精度）；时间范围过滤必填字段（PARTITION BY toYYYYMMDD(_time_second_)，timeGuard maxHours=24） |
| `app` | LowCardinality(String) | 应用名称，如 fs-uc-provider、fs-developer-platform；PRIMARY KEY 首列，WHERE 必须优先带 app=，否则会扫时间窗内全部应用易超时 |
| `cluster` | String | K8s 集群标识 |
| `ip` | IPv4 | Pod IP 地址 |
| `level` | LowCardinality(String) | 日志级别：INFO/WARN/ERROR 等 |
| `logger` | LowCardinality(String) | 日志记录器（Java logger 类名）。**本表字段名是 `logger`，不是 `loggerName`**（`log_error_dist` 才是 `loggerName`） |
| `msg` | String | 日志消息内容。子串检索推荐 msg LIKE '%keyword%'（keyword 长度 ≥3 可利用 idx_msg ngrambf_v1）； 也可用 position(msg, 'keyword') > 0。勿用 hasToken（面向 tokenbf，且参数须为单个 token、不能含空格）。 仅 msg 过滤而不带 app/时间仍会超时。 |
| `pod` | String | 产生日志的 K8s Pod 名称 |
| `profile` | LowCardinality(String) | 环境标识，如 fstest；PRIMARY KEY 第二列，已知环境时务必加 profile= 以缩小扫描 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `thread` | LowCardinality(String) | 线程名称 |
| `token` | String | 请求 token |
| `traceId` | String | 分布式追踪 ID；有 idx_trace_id（set）时等值过滤更稳，避免无时间窗的 LIKE |
| `userId` | String | 用户 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_` |

### 查询示例

RCA 默认投影（**必须** `app` + `_time_second_`；列名以字段定义为准；时间用字符串窗或 `now() - INTERVAL`）：

```bash
# 按 app + traceId + 时间窗（禁止裸 traceId）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT traceId, _time_second_, app, level, logger, msg, pod FROM app_log_dist WHERE app = '<app>' AND traceId = '<traceId>' AND _time_second_ >= '<T0>' AND _time_second_ <= '<T1>' ORDER BY _time_second_ DESC LIMIT 50" -j

# 查询指定应用的日志
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, app, level, logger, msg FROM app_log_dist WHERE app = 'fs-order-provider' AND _time_second_ > now() - INTERVAL 1 HOUR LIMIT 50" -j

# 查询 ERROR 日志
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, app, pod, logger, substring(msg, 1, 500) as msg FROM app_log_dist WHERE app = 'fs-order-provider' AND level = 'ERROR' AND _time_second_ > now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20" -j

# 按应用统计日志量
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT app, level, COUNT(*) as cnt FROM app_log_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR GROUP BY app, level ORDER BY cnt DESC" -j

# Kafka（fs-kafka-support）：无 audit/dispatch 表，按 logger 精确过滤；列名 logger / msg（不是 loggerName / message）
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT app, logger, level, count() AS cnt
FROM app_log_dist
WHERE _time_second_ > now() - INTERVAL 3 HOUR
  AND (
    logger IN (
      'com.fxiaoke.support.KConsumer',
      'com.fxiaoke.support.ConsumerRunner',
      'com.fxiaoke.support.SingleThreadConsumer',
      'com.fxiaoke.support.KafkaSender',
      'com.fxiaoke.support.SenderManager',
      'com.fxiaoke.support.KafkaUtils'
    )
    OR logger LIKE 'com.fxiaoke.kafka.support.%'
  )
GROUP BY app, logger, level
ORDER BY cnt DESC
LIMIT 40
" -j
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
