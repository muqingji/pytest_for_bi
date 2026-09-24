# flow-runtime-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 业务流程运行时日志分布式表，实时记录各类业务流、审批流节点的流转轨迹与处理状态。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_, createTime

---

## 表：biz_flow_runtime_log_dist

**说明**: 业务流程运行时日志分布式表，实时记录各类业务流、审批流节点的流转轨迹与处理状态。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_flow_runtime_log', rand(); Distributed('cluster01', 'logger', 'biz_flow_runtime_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime | 事件写入 ClickHouse 的秒级时间戳 |
| `appName` | Nullable(String) | 应用name |
| `bizName` | Nullable(String) | 业务名称 |
| `cost` | Nullable(Int32) | 操作耗时，单位为毫秒 (ms) |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `data` | Nullable(String) | 数据 |
| `ea` | Nullable(String) | 企业账号/租户账号名称 |
| `objectApiName` | String |  |
| `objectId` | String |  |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | Nullable(String) | 运行环境配置标识（如 prod, test, dev, ale 等） |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | Nullable(String) | 服务端IP地址 |
| `spanId` | String | OpenTelemetry Span ID |
| `status` | String |  |
| `taskId` | String |  |
| `tenantId` | Nullable(String) | 租户/企业 ID |
| `traceId` | Nullable(String) | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `type` | String |  |
| `userId` | String | 用户 ID |
| `version` | Nullable(Int32) | 版本 |
| `workflowInstanceId` | String |  |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
# 查询某租户流程运行时日志
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, appName, objectApiName, status, cost FROM biz_flow_runtime_log_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 50"

# 按对象统计流程节点耗时
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT objectApiName, status, COUNT(*) as cnt, avg(cost) as avg_cost FROM biz_flow_runtime_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY objectApiName, status ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
