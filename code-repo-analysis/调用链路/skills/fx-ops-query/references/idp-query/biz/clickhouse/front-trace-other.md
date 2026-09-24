# front-trace-other

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 前端其他链路日志，存储非 HTTP 请求的 span 数据（如小程序、WebSocket 等）

**租户ID字段**: `ei`, `ea`

**时间字段**: _time_second_

---

## 表：front_trace_log_other_dist

**说明**: 前端其他链路日志，存储非 HTTP 请求的 span 数据（如小程序、WebSocket 等）

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'front_trace_log_other_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(tech, os, _time_second_, traceId, spanId, parentSpanId)` |
| ORDER BY | `(tech, os, _time_second_, traceId, spanId, parentSpanId)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(30)` |
| 跳数/二级索引 | **INDEX**: `idx_traceId`: traceId TYPE bloom_filter(0.001), GRANULARITY 1; `idx_operationName`: operationName TYPE set(0), GRANULARITY 1; `idx_duration`: duration TYPE minmax, GRANULARITY 1; `idx_string_attr_key`: mapKeys(stringAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_string_attr_value`: mapValues(stringAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_int_attr_key`: mapKeys(intAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_int_attr_value`: mapValues(intAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_bool_attr_key`: mapKeys(boolAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_bool_attr_value`: mapValues(boolAttributes) TYPE bloom_filter(0.01), GRANULARITY 1; `idx_plat`: plat TYPE set(0) GRANULARITY 1 ) ENGINE = MergeTree PARTITION BY toYYYYMMDD(_time_second_) ORDER BY (tech |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3, 'Asia/Shanghai') | 记录时间（秒级） |
| `traceId` | String | 追踪 ID |
| `spanId` | String | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 traceId 组合可定位链路中的单个节点 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID，标识发起当前 span 的上游 span；根 span 或缺失上游时通常为空 |
| `operationName` | LowCardinality(String) | 操作名称 |
| `startTime` | DateTime64(3, 'Asia/Shanghai') | 开始时间 |
| `endTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `duration` | Int64 | 持续时间（ms） |
| `spanKind` | LowCardinality(String) | span 类型：CLIENT/SERVER 等 |
| `statusCode` | LowCardinality(String) | 状态码 |
| `statusMessge` | String | 状态消息（注意拼写） |
| `page` | LowCardinality(String) | 页面路径 |
| `biz` | LowCardinality(String) | 业务标识 |
| `operation` | LowCardinality(String) | 操作类型（如create/update/delete/转发等） |
| `apiName` | String | API接口名称 |
| `eventId` | String | 事件ID |
| `appId` | LowCardinality(String) | 应用ID |
| `fsAppId` | LowCardinality(String) | FS 应用 ID |
| `appMd5` | LowCardinality(String) | 应用包MD5 |
| `frameMd5` | LowCardinality(String) | 框架MD5值 |
| `frameVer` | LowCardinality(String) | 框架版本号 |
| `grayVariable` | LowCardinality(String) | 灰度变量 |
| `ea` | String | 租户账号 |
| `ei` | String | 租户 ID |
| `userId` | String | 用户 ID |
| `region` | LowCardinality(String) | 地区 |
| `timeZone` | LowCardinality(String) | 时区 |
| `language` | LowCardinality(String) | 语言 |
| `currency` | LowCardinality(String) | 货币 |
| `domain` | LowCardinality(String) | 域名 |
| `phoneName` | LowCardinality(String) | 手机型号 |
| `appVersion` | LowCardinality(String) | 应用版本号 |
| `channelId` | LowCardinality(String) | 渠道ID |
| `city` | LowCardinality(String) | 城市 |
| `continent` | LowCardinality(String) | 大洲 |
| `country` | LowCardinality(String) | 国家 |
| `cpuType` | LowCardinality(String) | CPU类型 |
| `deviceId` | String | 设备ID |
| `deviceType` | LowCardinality(String) | 设备型号 |
| `isChina` | Nullable(Bool) | 是否在中国 |
| `isFirstOpenPage` | Nullable(Bool) | 是否首次打开页面 |
| `official` | Nullable(Bool) | 是否官方版本 |
| `tech` | LowCardinality(String) | 技术栈，如 Ava |
| `os` | LowCardinality(String) | 操作系统 |
| `plat` | LowCardinality(String) | 平台：fs 等 |
| `osVersion` | LowCardinality(String) | 操作系统版本 |
| `province` | LowCardinality(String) | 省份 |
| `http.url` | String | 完整请求 URL |
| `mp.request.type` | LowCardinality(String) | 小程序请求类型 |
| `http.method` | LowCardinality(String) | HTTP 方法：POST/GET 等 |
| `http.status.code` | LowCardinality(String) | HTTP 状态码：200 等 |
| `operationType` | LowCardinality(String) | 操作类型（如查询/导出/聚合等） |
| `browser` | LowCardinality(String) | 浏览器 |
| `browserVersion` | LowCardinality(String) | 浏览器版本 |
| `pathName` | LowCardinality(String) | 路径名 |
| `stringAttributes` | Map(LowCardinality(String), String) | 字符串扩展属性（key-value） |
| `intAttributes` | Map(LowCardinality(String), Int64) | 整数扩展属性（key-value） |
| `boolAttributes` | Map(LowCardinality(String), Bool) | 布尔扩展属性（key-value） |
| `events` | Array(Map(LowCardinality(String), String)) | 事件列表 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |

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
# 按traceId查询前端非HTTP请求
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, traceId, operationName, duration, statusCode FROM front_trace_log_other_dist WHERE traceId = '<traceId>' AND _time_second_ >= now() - INTERVAL 1 DAY ORDER BY _time_second_"

# 查询慢操作TOP20
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT operationName, COUNT(*) as cnt, avg(duration) as avg_dur, max(duration) as max_dur FROM front_trace_log_other_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND duration > 3000 GROUP BY operationName ORDER BY max_dur DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
