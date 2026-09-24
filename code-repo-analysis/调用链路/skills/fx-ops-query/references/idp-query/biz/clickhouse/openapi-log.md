# openapi-log

> schema_verified_at: 2026-08-21 | source: foneshare `system.columns`（`logger.biz_log_openapi_dist`）+ 可查询验证；`show columns` 在 foneshare/firstshare 目录 **404**，属 catalog 缺口，**不是**表不存在

**说明**: 外部入站 OpenAPI 调用日志。记录 OpenAPI URL、耗时、错误码与链路追踪。无 `uri` / `method` / `tenantId` 列。

**租户ID字段**: `ei`, `ea`

**时间字段**: `_time_second_`（分区/主过滤）；`createTime` 仅展示事件时间，**禁止**当作分区过滤列

---

## 表：biz_log_openapi_dist

**说明**: OpenAPI 调用日志表，记录通过 OpenAPI 接口的请求和响应详情，包括错误信息、链路追踪等。库：`logger`（Distributed 入口；local 表在 `biz_log.biz_log_openapi`）。

### 存储与索引

> schema_verified_at: 2026-08-21 | local: `biz_log.biz_log_openapi`

| 项 | 值 |
| --- | --- |
| ENGINE | foneshare 实测 `Distributed('cluster01', 'biz_log', 'biz_log_openapi', rand())` |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 时间列（查询） | **`_time_second_`**（强制过滤）；`createTime` 仅 SELECT |

### 字段定义

物理列（`logger.biz_log_openapi_dist`，2026-08-21）。**无** `uri` / `method` / `tenantId`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime | 入库秒级时间（分区/主过滤） |
| `apiName` | Nullable(String) | API 名称 |
| `appId` | LowCardinality(String) | 应用 ID |
| `bizRequestCurl` | Nullable(String) | 业务侧 curl 还原 |
| `bizResponseBody` | Nullable(String) | 业务响应体 |
| `clientIp` | Nullable(String) | 客户端 IP |
| `cost` | Nullable(Int64) | 耗时 (ms) |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 事件创建时间（仅展示） |
| `ea` | Nullable(String) | 租户账号 |
| `ei` | Nullable(String) | 租户 ID |
| `errorType` | LowCardinality(String) | 错误类型 |
| `eventId` | Nullable(String) | 事件 ID |
| `messageId` | Nullable(String) | 消息 ID |
| `module` | Nullable(String) | 模块名称 |
| `openApiErrorCode` | Nullable(String) | OpenAPI 错误码 |
| `openApiErrorMessage` | Nullable(String) | OpenAPI 错误信息 |
| `openApiRequestBody` | Nullable(String) | OpenAPI 请求体 |
| `openApiResponseBody` | Nullable(String) | OpenAPI 响应体 |
| `openApiUrl` | Nullable(String) | OpenAPI URL 路径（**不是** `uri`） |
| `parentSpanId` | Nullable(String) | OpenTelemetry 父 Span ID |
| `podIp` | Nullable(String) | Pod IP |
| `profile` | Nullable(String) | 环境标识 |
| `requestBodyLength` | Nullable(Int64) | 请求体长度 |
| `responseBodyLength` | Nullable(Int64) | 响应体长度 |
| `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 标识 |
| `spanId` | Nullable(String) | OpenTelemetry Span ID |
| `tls` | LowCardinality(String) | TLS 信息 |
| `traceId` | Nullable(String) | 追踪 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 追踪ID | `traceId` |
| URL | `openApiUrl` |
| 时间 | **`_time_second_`** |

### 查询示例

时间窗默认 ≤24h。过滤必须带 `_time_second_`。

```bash
# 按租户 + 时间查 OpenAPI 调用
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, createTime, ei, ea, appId, apiName, openApiUrl, cost, errorType, openApiErrorCode, traceId FROM biz_log_openapi_dist WHERE ei = '<EI>' AND _time_second_ >= '<START>' AND _time_second_ <= '<END>' ORDER BY _time_second_ DESC LIMIT 50"

# 错误请求
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, ei, ea, openApiUrl, errorType, openApiErrorCode, openApiErrorMessage, cost, traceId FROM biz_log_openapi_dist WHERE ei = '<EI>' AND _time_second_ >= '<START>' AND _time_second_ <= '<END>' AND (openApiErrorCode IS NOT NULL AND openApiErrorCode != '') ORDER BY _time_second_ DESC LIMIT 50"

# 按 URL 统计调用量与耗时
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT openApiUrl, count() AS cnt, round(avg(cost), 2) AS avg_cost, max(cost) AS max_cost FROM biz_log_openapi_dist WHERE ei = '<EI>' AND _time_second_ >= '<START>' AND _time_second_ <= '<END>' GROUP BY openApiUrl ORDER BY cnt DESC LIMIT 30"

# 按 traceId 取证
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, ei, ea, openApiUrl, apiName, cost, errorType, openApiErrorCode, traceId, rpcId FROM biz_log_openapi_dist WHERE traceId = '<TRACE_ID>' AND _time_second_ >= '<START>' AND _time_second_ <= '<END>' ORDER BY _time_second_ ASC LIMIT 50"
```

> **禁止**: `FROM ... WHERE createTime > ...` 当主过滤（非分区键）；写 `uri` / `method` / `tenantId`（列不存在）。

---

## 相关文档

- [index.md](./index.md) - ClickHouse 表定义索引
- [high-frequency-cheatsheet.md](./high-frequency-cheatsheet.md) - 时间列规约与集成取证 SQL
- [erp-sync.md](./erp-sync.md) - ERP / iPaaS 集成日志
