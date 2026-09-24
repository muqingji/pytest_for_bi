# biz-log-function

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 函数执行日志，记录自定义函数/事件监听器的执行详情（耗时、队列、错误等）

**租户ID字段**: `tenantId`, `ea`

**时间字段**: `_time_second_`（分区/主过滤）。**`biz_log_function_dist` 无 `createTime`**（实测 `Column createtime does not exist.`）；同文档另外 3 张表有 `createTime`，但仍用 `_time_second_` 过滤。仅历史库 `function_log.biz_log_function_dist` 才有监控表级 `createTime`，`biz-app-log` 的 `FROM biz_log_function_dist` 不走该库。

---

## 表：biz_log_function_dist

**说明**: 函数执行日志，记录自定义函数/事件监听器的执行详情（耗时、队列、错误等）

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_function', rand(); Distributed('cluster01', 'logger', 'biz_log_function', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(60)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | **`_time_second_`**（无 `createTime`） |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime | 入库秒级时间 |
| `apiName` | String | 函数 API 名称 |
| `appName` | String | 应用名称（服务标识） |
| `author` | String | 作者 |
| `cost` | Nullable(Int64) | 执行耗时 |
| `dataId` | String | 数据 ID |
| `ea` | String | 租户账号 |
| `error` | String | 错误信息 |
| `errorCode` | String | 错误码 |
| `extra` | String | 扩展信息 |
| `fail` | String | 失败标识 |
| `id` | String | 主键 ID |
| `lang` | String | 语言 |
| `messageId` | String | 消息 ID |
| `num` | Nullable(Int64) | 调用次数 |
| `occupiedMemory` | Nullable(Int64) | 占用内存 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | String | 环境（如 fstest） |
| `queueId` | Nullable(Int64) | 队列 ID |
| `queueType` | String | 队列类型 |
| `requestId` | String | 请求 ID |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `runType` | LowCardinality(String) | 运行类型 |
| `serverIp` | String | 服务 IP |
| `spanId` | String | OpenTelemetry Span ID |
| `tenantId` | String | 租户 ID |
| `totalCost` | Nullable(Int64) | 总耗时 |
| `traceId` | String | 追踪 ID |
| `type` | LowCardinality(String) | 类型（如 event_listener） |
| `userId` | String | 用户 ID |
| `version` | String | 版本 |
| `waitingCost` | Nullable(Int64) | 等待耗时 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | **`_time_second_`**（无 `createTime`） |

### 查询示例

```bash
# 查函数执行监控（耗时、排队、错误码）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT id, apiName, type, traceId, errorCode, cost, waitingCost, totalCost, queueId, queueType, messageId, extra, _time_second_ FROM biz_log_function_dist WHERE tenantId = '{tenantId}' AND _time_second_ >= '{fromTime}' AND _time_second_ <= '{toTime}' AND traceId = '{traceId}' ORDER BY _time_second_ DESC LIMIT 50"

# 查函数执行失败
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT id, apiName, errorCode, error, _time_second_ FROM biz_log_function_dist WHERE tenantId = '{tenantId}' AND errorCode != '' AND _time_second_ >= '{fromTime}' AND _time_second_ <= '{toTime}' ORDER BY _time_second_ DESC LIMIT 50"

# 异步队列延迟分析（必须 queueId != 0 排除同步）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT formatDateTime(toStartOfMinute(_time_second_), '%Y-%m-%d %H:%i:%s') AS minute, count() AS cnt, round(avg(waitingCost), 2) AS avg_waiting, max(waitingCost) AS max_waiting, round(avg(cost), 2) AS avg_cost FROM biz_log_function_dist WHERE tenantId = '{tenantId}' AND queueId != 0 AND (errorCode IS NULL OR errorCode != 'mq_message_send') AND _time_second_ >= '{fromTime}' AND _time_second_ <= '{toTime}' GROUP BY toStartOfMinute(_time_second_) ORDER BY minute ASC LIMIT 100"

# 查限流命中
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT id, apiName, errorCode, JSONExtractString(extra, 'rateLimit') AS rate_limit_detail, _time_second_ FROM biz_log_function_dist WHERE tenantId = '{tenantId}' AND (errorCode LIKE '%FUNCTION_API_RATE_LIMITER%' OR JSONExtractString(extra, 'rateLimit') != '') AND _time_second_ >= '{fromTime}' AND _time_second_ <= '{toTime}' ORDER BY _time_second_ DESC LIMIT 100"
```

---

## 表：biz_log_function_user_execute_dist

**说明**: 函数用户执行日志，记录函数调用的入参、返回值、异常及执行耗时

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_function_user_execute', rand(); Distributed('cluster01', 'logger', 'biz_log_function_user_execute', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(deleteTime)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime | 入库秒级时间 |
| `bindingApiName` | String | 绑定 API 名称 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `deleteTime` | DateTime64(3, 'Asia/Shanghai') | 删除时间 |
| `durationTime` | Nullable(Int64) | 执行耗时（ms） |
| `exception` | String | 异常信息 |
| `functionApiName` | String | 函数 API 名称 |
| `id` | String | 主键 ID |
| `module` | String | 模块（如 event_listener） |
| `name` | String | 名称 |
| `objectId` | String | 对象 ID |
| `operationTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 操作时间 |
| `parameters` | String | 入参（JSON） |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `returnType` | String | 返回类型 |
| `returnValue` | String | 返回值 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `spanId` | String | OpenTelemetry Span ID |
| `success` | String | 是否成功 |
| `tenantId` | String | 租户 ID |
| `traceId` | String | 追踪 ID |
| `version` | Nullable(String) | 版本 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM biz_log_function_user_execute_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 表：biz_log_inner_function_api_dist

**说明**: 内部函数 API 日志，记录函数内部调用的平台 API（如 LogImpl.info）的请求/响应大小及耗时

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_inner_function_api', rand(); Distributed('cluster01', 'logger', 'biz_log_inner_function_api', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(60)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime | 入库秒级时间 |
| `cost` | Nullable(Int64) | 耗时 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `deprecated` | Bool | 是否已废弃（默认 false） |
| `ea` | String | 租户账号 |
| `funcInstanceId` | String | 函数实例 ID |
| `functionApiName` | String | 函数 API 名称 |
| `innerApiName` | String | 内部 API 名称（如 LogImpl.info） |
| `namespace` | String | 命名空间 |
| `num` | Nullable(Int64) | 调用次数 |
| `objectApiName` | String | 对象 API 名称 |
| `paramName` | String | 参数名 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `reqSize` | Nullable(Int64) | 请求大小 |
| `respSize` | Nullable(Int64) | 响应大小 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `spanId` | String | OpenTelemetry Span ID |
| `tenantId` | String | 租户 ID |
| `totalCost` | Nullable(Int64) | 总耗时 |
| `traceId` | String | 追踪 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM biz_log_inner_function_api_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 表：biz_log_function_user_api_dist

**说明**: 函数用户 API 日志，记录用户调用函数的 console.log/info 等输出内容

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_function_user_api', rand(); Distributed('cluster01', 'logger', 'biz_log_function_user_api', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(deleteTime)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime | 入库秒级时间 |
| `bindingApiName` | String | 绑定 API 名称 |
| `content` | String | 日志内容 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `deleteTime` | DateTime64(3, 'Asia/Shanghai') | 删除时间 |
| `functionApiName` | String | 函数 API 名称 |
| `incrSerialNumber` | Nullable(Int64) | 递增序号 |
| `lineNumber` | Nullable(Int64) | 行号 |
| `logId` | String | 日志 ID |
| `logLevel` | String | 日志级别 |
| `nameSpace` | String | 命名空间（如 event_listener） |
| `operationTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 操作时间 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `spanId` | String | OpenTelemetry Span ID |
| `tenantId` | LowCardinality(String) | 租户 ID |
| `traceId` | String | 追踪 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM biz_log_function_user_api_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
