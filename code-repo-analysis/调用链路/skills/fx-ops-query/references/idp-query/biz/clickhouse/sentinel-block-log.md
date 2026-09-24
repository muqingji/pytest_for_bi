# sentinel-block-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: Sentinel 限流熔断拦截日志分布式表（与 sentinel_block 孪生，列同构）。Open/SQL 可用名：sentinel_block 与 sentinel_block_dist。

**时间字段**: _time_second_

---

## 表：sentinel_block_dist

**说明**: Sentinel 限流熔断拦截日志分布式表（与 sentinel_block 孪生，列同构）。Open/SQL 可用名：sentinel_block 与 sentinel_block_dist。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | — |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(resource_name, _time_second_)` |
| ORDER BY | `(resource_name, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(30)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3) | 拦截事件时间（毫秒精度） |
| `trace_id` | String | 链路追踪 ID（常见 J-E. 前缀；高基、近乎每事件唯一。过滤优先本列） |
| `user_id` | String | 触发拦截的用户标识（多为 {ea}.{uid}；可为空字符串） |
| `count` | Int32 | 本条日志对应的拦截次数（通常为 1，表示一次 block 事件） |
| `resource_name` | String | 被限流/熔断的资源名（业务资源键，如 list/add 类 resource） |
| `interception_reason` | String | 拦截异常类型（常见 ParamFlowException=热点参数限流；亦可能为其它 Sentinel 异常名） |
| `rule` | String | 触发规则标识（常为数值规则码字符串；可与 args 首段对应） |
| `origin` | String | 调用来源（常为空字符串） |
| `rule_id` | Int32 | 规则数字 ID（未填充时可能为 0） |
| `blocked_request` | Int32 | 累计已拦截请求数（限流窗口内计数快照） |
| `curr_thread_num` | Int32 | 当前线程数快照 |
| `args` | String | 拦截上下文参数串（逗号分隔：租户/调用方、对象与动作、API path 等，便于还原被拦请求） |
| `profile` | String | 环境标识 |
| `app` | String | 被拦截服务的应用名 |
| `pod` | String | 处理请求的 Pod 名 |
| `pod_ip` | IPv4 | 处理请求的 Pod IP |
| `traceId` | Nullable(String) | trace_id 的驼峰别名列（可空；过滤优先 trace_id） |
| `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `spanId` | Nullable(String) | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 traceId 组合可定位链路中的单个节点 |
| `parentSpanId` | Nullable(String) | OpenTelemetry 父 Span ID，标识发起当前 span 的上游 span；根 span 或缺失上游时通常为空 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 用户ID | `user_id` |
| 追踪ID | `trace_id` |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查询最近被限流的请求
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, app, resource_name, interception_reason, rule, count FROM sentinel_block_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20"

# 按资源聚合拦截统计
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT resource_name, interception_reason, SUM(count) as total_blocked FROM sentinel_block_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR GROUP BY resource_name, interception_reason ORDER BY total_blocked DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
