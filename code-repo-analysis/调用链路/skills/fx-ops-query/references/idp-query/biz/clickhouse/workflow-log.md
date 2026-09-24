# workflow-log（业务工作流执行日志）

> schema_verified_at: 2026-08-01 | platform: v5.10.0
> [!WARNING]
> **已废弃 / 不可查询**：platform v4.37.0 已将 `biz_log_workflow_dist` 从 tenant-filters 移除（variant `all_inactive` / scan 排除）。请改用 [workflow-v2-log.md](./workflow-v2-log.md)。

**说明**: 业务工作流执行日志，记录工作流底层节点的状态变化、参与人、节点跳转历史

**租户ID字段**: `tenantId`

**时间字段**: `_time_second_`、`createTime`

---

## 表：biz_log_workflow_dist

### 存储与索引

| 项 | 值 |
| --- | --- |
| 状态 | **已废弃**，platform 无 `biz_log_workflow_dist.yaml` |

### 字段定义（历史参考，勿查询）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `bizName` | Nullable(String) | 业务名称 |
| `appName` | Nullable(String) | 应用名称 |
| `eventId` | Nullable(String) | 事件ID |
| `traceId` | Nullable(String) | 链路追踪ID |
| `userId` | Nullable(String) | 用户ID |
| `objectApiName` | Nullable(String) | 对象API名称 |
| `objectId` | Nullable(String) | 对象ID |
| `objectData` | Nullable(String) | 对象数据 |
| `batchType` | Nullable(String) | 批量操作类型 |
| `crudType` | Nullable(String) | CRUD操作类型 |
| `source` | Nullable(String) | 事件来源/触发来源 |
| `sourceCrudType` | Nullable(String) | 来源CRUD类型 |
| `triggerData` | Nullable(String) | 触发数据 |
| `status` | Nullable(String) | 状态 |
| `workflowId` | Nullable(String) | 工作流ID |
| `ruleId` | Nullable(String) | 触发规则ID |
| `finishTime` | Nullable(DateTime64(3)) | 完成时间 |
| `dispatchCost` | Nullable(Int64) | 调度耗时(ms) |
| `waitingCost` | Nullable(Int64) | 等待耗时(ms) |
| `profile` | Nullable(String) | 环境标识 |
| `tenantId` | Nullable(String) | 租户ID |
| `createTime` | Nullable(DateTime64(3)) | 创建时间 |
| `modifyTime` | Nullable(DateTime64(3)) | 修改时间 |
| `serverIp` | Nullable(String) | 服务器IP |
| `executeCost` | Nullable(Int64) | 执行耗时(ms) |
| `ea` | Nullable(String) | 租户账号 |
| `error` | Nullable(String) | 错误信息 |
| `tries` | Nullable(Int32) | 重试次数 |
| `id` | Nullable(String) | 记录ID |
| `version` | Nullable(Int32) | 版本 |
| `_time_second_` | DateTime | 日志采集时间（秒级） |
| `_time_nanosecond_` | DateTime64(9) | 日志采集时间（纳秒级） |
| `metadataDelayCost` | Nullable(Int64) | 元数据延迟耗时(ms) |
| `rpcId` | Nullable(String) | RPC调用链层级 |
| `spanId` | Nullable(String) | Span ID |
| `parentSpanId` | Nullable(String) | 父Span ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 工作流ID | `workflowId` |
| 状态 | `status` |
| 时间 | `_time_second_`、`createTime` |

### 查询示例

```bash
# 查询某租户工作流执行错误
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, workflowId, objectApiName, status, error, dispatchCost, executeCost FROM biz_log_workflow_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR AND error != '' ORDER BY _time_second_ DESC LIMIT 50"

# 统计工作流异常分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT workflowId, objectApiName, status, COUNT(*) as cnt, avg(executeCost) as avg_cost FROM biz_log_workflow_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY workflowId, objectApiName, status ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
- ./workflow-v2-log.md - 工作流V2日志
- ./flow-instance-log.md - 流程实例日志
