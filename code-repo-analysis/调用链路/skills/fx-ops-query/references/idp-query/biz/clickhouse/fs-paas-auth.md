# fs-paas-auth

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: FS PaaS 平台认证与鉴权日志分布式表，记录 OAuth2、Feishu API 访问过程中的授权鉴权日志。

**租户ID字段**: `tenantId`

**时间字段**: _time_second_

---

## 表：fs_paas_auth_log_dist

**说明**: FS PaaS 平台认证与鉴权日志分布式表，记录 OAuth2、Feishu API 访问过程中的授权鉴权日志。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'fs_paas_auth_log', rand(); Distributed('cluster01', 'logger', 'fs_paas_auth_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(360)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime | 事件写入 ClickHouse 的秒级时间戳 |
| `appId` | LowCardinality(String) | 应用id |
| `args` | String | 方法调用参数（JSON序列化） |
| `caller` | LowCardinality(String) | 调用方服务名称 |
| `cost` | Int64 | 操作耗时，单位为毫秒 (ms) |
| `currentTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `methodName` | LowCardinality(String) | 被调用的鉴权方法名 |
| `outerTenantId` | String | outer租户id |
| `outerUserId` | String | 外部系统用户ID（如飞书开放平台用户ID） |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `realAppId` | LowCardinality(String) | 实际被调用的应用ID |
| `results` | String | 方法调用返回结果（JSON序列化） |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | LowCardinality(String) | 服务端IP地址 |
| `spanId` | String | OpenTelemetry Span ID |
| `tenantId` | String | 租户/企业 ID |
| `threadName` | LowCardinality(String) | 执行线程名称 |
| `traceId` | LowCardinality(String) | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `userId` | String | 操作用户的唯一标识 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查询某租户认证鉴权失败记录
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, userId, methodName, cost, results, traceId FROM fs_paas_auth_log_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR AND results NOT LIKE '%success%' ORDER BY _time_second_ DESC LIMIT 50"

# 统计鉴权方法耗时分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT methodName, COUNT(*) as cnt, avg(cost) as avg_cost, max(cost) as max_cost FROM fs_paas_auth_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY methodName ORDER BY avg_cost DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
