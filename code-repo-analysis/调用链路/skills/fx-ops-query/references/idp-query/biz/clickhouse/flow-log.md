# flow-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 流程排他网关日志，记录工作流中排他网关（条件分支）的执行路径选择

**租户ID字段**: `tenantId`, `ea`

**时间字段**: createTime

---

## 表：fs_flow_exclusive_gateway_log_dist

**说明**: 流程排他网关日志，记录工作流中排他网关（条件分支）的执行路径选择

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'fs_flow_exclusive_gateway_log', rand()); Distributed('cluster01', 'logger', 'fs_flow_exclusive_gateway_log', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | — |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime('Asia/Shanghai') | 入库秒级时间 |
| `activityInstanceId` | String | 活动实例 ID |
| `appId` | String | 应用 ID（如 CRM） |
| `appName` | LowCardinality(String) | 应用名称 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `ea` | String | 租户账号 |
| `exclusiveGatewayId` | String | 排他网关 ID |
| `extra` | String | 扩展信息（JSON） |
| `id` | String | 主键 ID |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | LowCardinality(String) | 服务 IP |
| `spanId` | String | OpenTelemetry Span ID |
| `tenantId` | String | 租户 ID |
| `traceId` | String | 追踪 ID |
| `type` | LowCardinality(String) | 类型（如 workflow） |
| `workflowInstanceId` | String | 工作流实例 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 追踪ID | `traceId` |
| 时间 | `createTime` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, appName, type, workflowInstanceId, exclusiveGatewayId FROM fs_flow_exclusive_gateway_log_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
