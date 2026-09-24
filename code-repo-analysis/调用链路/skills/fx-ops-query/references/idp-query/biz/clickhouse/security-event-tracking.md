# security-event-tracking

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 安全合规事件追踪分布式表，专门追踪异常敏感查询、跨域导出、解密操作的安全合规日志。

**租户ID字段**: `tenantId`

**时间字段**: _time_second_

---

## 表：security_event_tracking_dist

**说明**: 安全合规事件追踪分布式表，专门追踪异常敏感查询、跨域导出、解密操作的安全合规日志。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'security_event_tracking', rand(); Distributed('cluster01', 'logger', 'security_event_tracking', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime('Asia/Shanghai') | 事件写入 ClickHouse 的秒级时间戳 |
| `actionType` | String | 安全动作类型（如查询/导出/解密） |
| `deviceId` | String | 设备ID |
| `deviceType` | String | 设备类型 |
| `eventId` | String | 事件id |
| `eventTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `keywords` | String | 敏感关键词/过滤关键字 |
| `objectIds` | String | 对象/实体ids |
| `objects` | Nullable(String) | 操作对象名称/JSON |
| `operation` | String | 安全审计操作描述 |
| `parameters` | String | 请求参数 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `query` | String | 执行的SQL查询内容 |
| `records` | Array(String) | 操作影响的记录列表 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `sourceIp` | String | 操作来源IP地址 |
| `spanId` | String | OpenTelemetry Span ID |
| `tenantId` | String | 租户/企业 ID |
| `traceId` | String | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
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
# 查询某租户安全事件
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, userId, actionType, operation, sourceIp FROM security_event_tracking_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 DAY ORDER BY _time_second_ DESC LIMIT 50"

# 统计安全事件类型分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT actionType, COUNT(*) as cnt FROM security_event_tracking_dist WHERE _time_second_ >= now() - INTERVAL 1 DAY GROUP BY actionType ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
