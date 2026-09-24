# flow-execution-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 流程执行节点日志，记录工作流中各活动节点（如自定义函数）的执行状态和结果

**租户ID字段**: `tenantId`, `ea`

**时间字段**: createTime

---

## 表：fs_flow_execution_log_dist

**说明**: 流程执行节点日志，记录工作流中各活动节点（如自定义函数）的执行状态和结果

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'fs_flow_execution_log_local', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime('Asia/Shanghai') | 入库秒级时间 |
| `activityId` | String | 活动 ID |
| `appName` | LowCardinality(String) | 应用名称 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `ea` | String | 租户账号 |
| `extra` | String | 扩展信息（JSON，含执行状态） |
| `id` | String | 主键 ID |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | LowCardinality(String) | 服务 IP |
| `spanId` | String | OpenTelemetry Span ID |
| `tenantId` | String | 租户 ID |
| `traceId` | String | 追踪 ID |
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
# 查询某工作流实例的节点执行情况
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT createTime, activityId, extra, traceId FROM fs_flow_execution_log_dist WHERE workflowInstanceId = '<id>' AND _time_second_ >= now() - INTERVAL 7 DAY ORDER BY createTime"

# 统计失败节点分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT appName, activityId, COUNT(*) as cnt FROM fs_flow_execution_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND extra LIKE '%FAIL%' GROUP BY appName, activityId ORDER BY cnt DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
