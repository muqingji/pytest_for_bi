# frontend-trace-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 前端全链路追踪日志分布式表，存储来自客户端（移动端/小程序/H5）的 HTTP 请求链路 span 数据，包含设备信息、地理位置、请求耗时、状态码等。底层 local 表为 VIEW，UNION 了 http/other/old 三张表。

**租户ID字段**: `ei`, `ea`

**时间字段**: _time_second_

---

## 表：front_trace_log_dist

**说明**: 前端全链路追踪日志分布式表，存储来自客户端（移动端/小程序/H5）的 HTTP 请求链路 span 数据，包含设备信息、地理位置、请求耗时、状态码等。底层 local 表为 VIEW，UNION 了 http/other/old 三张表。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'front_trace_log_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(traceId, _time_second_, spanId, parentSpanId)` |
| ORDER BY | `(traceId, _time_second_, spanId, parentSpanId)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(30)` |
| 跳数/二级索引 | **INDEX**: `idx_traceId`: traceId TYPE bloom_filter(0.001), GRANULARITY 1; `idx_operationName`: operationName TYPE set(0), GRANULARITY 1; `idx_duration`: duration TYPE minmax, GRANULARITY 1; `idx_string_attr_key`: mapKeys(stringAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_string_attr_value`: mapValues(stringAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_int_attr_key`: mapKeys(intAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_int_attr_value`: mapValues(intAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_bool_attr_key`: mapKeys(boolAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_bool_attr_value`: mapValues(boolAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_plat`: plat TYPE set(0), GRANULARITY 1 |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3, 'Asia/Shanghai') | 记录时间（秒级精度） |
| `apiName` | String | API 名称 |
| `appId` | LowCardinality(String) | 应用 ID，如 uipaas_custom |
| `appMd5` | LowCardinality(String) | 应用包 MD5 |
| `appVersion` | LowCardinality(String) | 客户端版本号 |
| `biz` | LowCardinality(String) | 业务标识 |
| `boolAttributes` | Map(LowCardinality(String), Bool) | 布尔扩展属性（key-value） |
| `browser` | LowCardinality(String) | 浏览器 |
| `browserVersion` | LowCardinality(String) | 浏览器版本 |
| `channelId` | LowCardinality(String) | 渠道 ID |
| `city` | LowCardinality(String) | 城市 |
| `continent` | LowCardinality(String) | 大洲 |
| `country` | LowCardinality(String) | 国家 |
| `cpuType` | LowCardinality(String) | CPU 类型 |
| `currency` | LowCardinality(String) | 货币 |
| `deviceId` | String | 设备 ID |
| `deviceType` | LowCardinality(String) | 设备类型 |
| `domain` | LowCardinality(String) | 域名，如 https://www.fxiaoke.com |
| `duration` | Int64 | 持续时间（毫秒） |
| `ea` | String | 租户账号（enterprise account） |
| `ei` | String | 租户 ID（enterprise ID） |
| `endTime` | DateTime64(3, 'Asia/Shanghai') | span 结束时间 |
| `eventId` | String | 事件 ID |
| `events` | Array(Map(LowCardinality(String), String)) | 事件列表 |
| `frameMd5` | LowCardinality(String) | 框架 MD5 |
| `frameVer` | LowCardinality(String) | 框架版本 |
| `fsAppId` | LowCardinality(String) | FS 应用 ID |
| `grayVariable` | LowCardinality(String) | 灰度变量，如 normal |
| `http.method` | LowCardinality(String) | HTTP 方法：POST/GET 等 |
| `http.status.code` | LowCardinality(String) | HTTP 状态码：200 等 |
| `http.url` | String | 完整请求 URL |
| `intAttributes` | Map(LowCardinality(String), Int64) | 整数扩展属性（key-value） |
| `isChina` | Nullable(Bool) | 是否中国 |
| `language` | LowCardinality(String) | 语言，如 zh-CN |
| `mp.request.type` | LowCardinality(String) | 小程序请求类型 |
| `official` | Nullable(Bool) | 是否正式环境 |
| `operation` | LowCardinality(String) | 操作标识 |
| `operationName` | LowCardinality(String) | 操作名称，通常为 API 路径 |
| `operationType` | LowCardinality(String) | 操作类型，如 http |
| `os` | LowCardinality(String) | 操作系统：Android/iOS 等 |
| `osVersion` | LowCardinality(String) | 操作系统版本 |
| `page` | LowCardinality(String) | 页面路径 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID，标识发起当前 span 的上游 span；根 span 或缺失上游时通常为空 |
| `pathName` | LowCardinality(String) | 路径名 |
| `phoneName` | LowCardinality(String) | 手机型号 |
| `plat` | LowCardinality(String) | 平台：fs 等 |
| `province` | LowCardinality(String) | 省份 |
| `region` | LowCardinality(String) | 区域，如 zh_Hans_CN |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `spanId` | String | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 traceId 组合可定位链路中的单个节点 |
| `spanKind` | LowCardinality(String) | span 类型：CLIENT/SERVER 等 |
| `startTime` | DateTime64(3, 'Asia/Shanghai') | span 开始时间 |
| `statusCode` | LowCardinality(String) | 状态码：OK/ERROR 等 |
| `statusMessge` | String | 状态消息（注意拼写） |
| `stringAttributes` | Map(LowCardinality(String), String) | 字符串扩展属性（key-value） |
| `tech` | LowCardinality(String) | 技术栈，如 Ava |
| `timeZone` | LowCardinality(String) | 时区，如 Asia/Shanghai |
| `traceId` | String | 追踪 ID，格式如 FSA-{ea}-{id} |
| `userId` | String | 用户 ID，格式如 {ea}.{ei} |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, operationName, duration, http.status.code, page, ei FROM front_trace_log_dist WHERE traceId = '<TRACE_ID>' AND _time_second_ BETWEEN '<START>' AND '<END>' ORDER BY _time_second_ DESC LIMIT 20"

# 查某租户的错误请求
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, operationName, http.url, http.status.code, duration, deviceType FROM front_trace_log_dist WHERE ei = '123' AND statusCode != '0' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
