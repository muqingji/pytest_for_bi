# fs-cep-slow-error

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: CEP 网关慢请求与错误日志，记录通过 CEP 网关的慢请求和错误请求的详细信息，包括请求参数、响应体、耗时等。用于排查慢接口和错误请求。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_, stamp

---

## 表：fs_cep_slow_error_dist

**说明**: CEP 网关慢请求与错误日志，记录通过 CEP 网关的慢请求和错误请求的详细信息，包括请求参数、响应体、耗时等。用于排查慢接口和错误请求。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'fs_cep_slow_error', rand(); Distributed('cluster01', 'logger', 'fs_cep_slow_error', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志写入时间（纳秒级） |
| `_time_second_` | DateTime | 日志写入时间（秒级） |
| `bizName` | Nullable(String) | 业务模块名称 |
| `body` | Nullable(String) | 响应体内容 |
| `client` | Nullable(String) | 客户端类型 |
| `clientIp` | Nullable(String) | 客户端 IP |
| `cost` | Nullable(Int64) | 请求耗时（ms） |
| `ea` | Nullable(String) | 租户账号 |
| `errorCode` | String |  |
| `extra` | String |  |
| `param` | Nullable(String) | 请求参数 |
| `parentSpanId` | Nullable(String) | 父调用跨度 ID |
| `profile` | String | 环境标识（K8s namespace / cms_profile） |
| `reqId` | Array(String) | 请求 ID 列表 |
| `reqSize` | Nullable(Int32) | 请求体大小 |
| `reqUrl` | Nullable(String) | 请求 URL |
| `rpcId` | Nullable(String) | RPC 调用 ID |
| `serverAddr` | Nullable(String) | 服务端 IP |
| `serverIp` | Nullable(String) | 服务端地址（含端口） |
| `size` | Nullable(Int32) | 响应体大小 |
| `spanId` | Nullable(String) | 当前调用跨度 ID |
| `stamp` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 请求时间戳 |
| `status` | String | 请求状态 |
| `tenantId` | Nullable(String) | 租户 ID |
| `traceId` | Nullable(String) | 链路追踪 ID |
| `uid` | String | 用户 ID（格式：tenantId.userId） |
| `userId` | Nullable(String) | 用户 ID（格式：E.tenantId.userId） |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `uid`, `userId` |
| 追踪ID | `traceId` |
| 请求ID | `reqId` |
| 时间 | `_time_second_`, `stamp` |

### 查询示例

```bash
# 基础查询（不包含大字段）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, traceId, rpcId, reqUrl, errorCode, status, cost, tenantId, ea FROM fs_cep_slow_error_dist WHERE tenantId = '123' AND _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"

# 包含大字段（需截取部分内容）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, traceId, reqUrl, errorCode, status, cost, substring(body, 1, 500) AS body_preview, substring(param, 1, 200) AS param_preview FROM fs_cep_slow_error_dist WHERE tenantId = '123' AND _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

**注意**：
- `body`、`param`、`extra` 字段可能包含大量 JSON 数据，查询时建议使用 `substring()` 截取部分内容，避免响应过大
- `status` 字段为 HTTP 响应状态码；为空时应按缺失状态处理
- `errorCode` 字段包含业务错误码（如 `s311030117`）

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
