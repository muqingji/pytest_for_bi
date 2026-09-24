# api-bus-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: API 网关（API Bus）请求日志，记录经过 API 网关转发的请求信息，包括调用方、被调用方、请求路径、耗时、状态码等。用于接口调用监控和慢请求排查。

**租户ID字段**: `tenant_id`

**时间字段**: _time_second_

---

## 表：apibus_log_dist

**说明**: API 网关（API Bus）请求日志，记录经过 API 网关转发的请求信息，包括调用方、被调用方、请求路径、耗时、状态码等。用于接口调用监控和慢请求排查。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'apibus_log_local', rand(); Distributed('cluster01', 'logger', 'apibus_log_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(caller_ip, trace_id, _time_second_)` |
| ORDER BY | `(caller_ip, trace_id, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(10)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3) | 日志写入时间（秒级精度） |
| `app` | String | 当前应用名称 |
| `caller` | String | 调用方应用名称 |
| `caller_ip` | String | 调用方 IP |
| `click_id` | String |  |
| `cluster` | String | K8s 集群标识 |
| `cost` | Int64 | 请求耗时（ms） |
| `level` | String | 日志级别（INFO/WARN/ERROR） |
| `logger` | String | 日志记录器名称（如 SlowOrError） |
| `origin_app_name` | String | 上游应用名称 |
| `origin_server_ip` | String | 上游服务地址 |
| `parent_span_id` | String |  |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `pod` | String | Pod 名称 |
| `pod_ip` | String | Pod IP 地址 |
| `profile` | String | 环境标识（如 fstest） |
| `request_method` | String | HTTP 请求方法（get/post 等） |
| `request_uri` | String | HTTP 请求 URI |
| `rpc_id` | Nullable(String) | RPC 调用 ID |
| `rpcId` | Nullable(String) | RPC 调用 ID（ALIAS rpc_id） |
| `span_id` | Nullable(String) | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 trace_id 组合可定位链路中的单个节点 |
| `spanId` | Nullable(String) | Span ID（ALIAS span_id） |
| `status_code` | Int32 | HTTP 响应状态码 |
| `tenant_id` | String | 租户 ID |
| `thread` | String | 线程名称 |
| `trace_id` | String | 链路追踪 ID |
| `traceId` | String | 链路追踪 ID（ALIAS trace_id） |
| `user_id` | String | 用户 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenant_id` |
| 用户ID | `user_id` |
| 追踪ID | `trace_id` |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查询租户 API 网关日志
fx-ops idp --profile <profile> query biz-app-log --tenant-id 1 --sql "SELECT _time_second_, app, request_method, request_uri, status_code, cost, tenant_id FROM apibus_log_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"

# 按应用统计请求量
fx-ops idp --profile <profile> query biz-app-log --tenant-id 1 --sql "SELECT app, COUNT(*) as cnt, AVG(cost) as avg_cost FROM apibus_log_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR GROUP BY app ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
