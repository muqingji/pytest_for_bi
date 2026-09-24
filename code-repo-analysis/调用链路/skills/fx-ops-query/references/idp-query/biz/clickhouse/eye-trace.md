# eye-trace

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 后端链路追踪日志，记录微服务之间的 RPC 调用和数据库访问的链路信息，包括调用方法、参数、耗时等。用于分布式链路追踪和性能分析。

**租户ID字段**: `tenantId`

**时间字段**: _time_second_, stamp

---

## 表：eye_trace_dist

**说明**: 后端链路追踪日志，记录微服务之间的 RPC 调用和数据库访问的链路信息，包括调用方法、参数、耗时等。用于分布式链路追踪和性能分析。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'eye_trace', rand(); Distributed('cluster01', 'logger', 'eye_trace', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(30)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志写入时间（纳秒级精度） |
| `_time_second_` | DateTime | 日志写入时间（秒级精度） |
| `app` | Nullable(String) | 发起调用的应用名称 |
| `clientIp` | Nullable(String) | 客户端 IP |
| `cost` | Nullable(Int32) | 调用耗时（ms） |
| `ea` | String | 租户账号 |
| `extra` | String |  |
| `fail` | String | 失败标识 |
| `iface` | Nullable(String) | 调用的接口/资源名称 |
| `method` | Nullable(String) | 调用方法名（如 find/mget） |
| `parameter` | String |  |
| `parentRpcId` | String |  |
| `parentSpanId` | String | OpenTelemetry 父 Span ID，标识发起当前 span 的上游 span；根 span 或缺失上游时通常为空 |
| `profile` | Nullable(String) | 环境标识 |
| `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `serverName` | Nullable(String) | 被调用的服务名称（含模块信息） |
| `size` | Nullable(Int32) | 响应大小 |
| `spanId` | String | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 traceId 组合可定位链路中的单个节点 |
| `stamp` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 事件时间戳 |
| `tenantId` | String | 租户 ID |
| `traceId` | Nullable(String) | 链路追踪 ID |
| `uid` | String | 用户 ID |
| `url` | String |  |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `uid` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `stamp` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, app, serverName, iface, cost, fail, substring(parameter, 1, 300) AS param FROM eye_trace_dist WHERE traceId = '<TRACE_ID>' AND _time_second_ BETWEEN '<START>' AND '<END>' ORDER BY _time_second_ DESC LIMIT 50"

fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM eye_trace_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
