# flow-instance-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 流程实例日志，记录工作流/审批流的完整生命周期（从创建到结束），含耗时和状态

**租户ID字段**: `tenantId`, `ea`

**时间字段**: createTime, start

---

## 表：fs_flow_instance_log_dist

**说明**: 流程实例日志，记录工作流/审批流的完整生命周期（从创建到结束），含耗时和状态

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'fs_flow_instance_log', rand()); Distributed('cluster01', 'logger', 'fs_flow_instance_log', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `createTime`, `start` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | String | 主键 ID（= workflowInstanceId） |
| `tenantId` | String | 租户 ID |
| `ea` | String | 租户账号 |
| `traceId` | String | 追踪 ID |
| `appName` | LowCardinality(String) | 应用名称 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `serverIp` | LowCardinality(String) | 服务 IP |
| `appId` | String | 应用 ID（如 CRM） |
| `type` | LowCardinality(String) | 类型（如 workflow） |
| `extraData` | String | 扩展数据（JSON） |
| `workflowInstanceId` | String | 工作流实例 ID |
| `applicantId` | String | 申请人 ID |
| `workflowId` | String | 工作流定义 ID |
| `sourceWorkflowId` | String | 源工作流定义 API 名称 |
| `workflowName` | String | 工作流名称 |
| `crudType` | String | 增删改类型 |
| `objectId` | String | 触发对象 ID |
| `entityId` | String | 触发对象 API 名称 |
| `start` | DateTime64(3, 'Asia/Shanghai') | 开始时间 |
| `end` | DateTime64(3, 'Asia/Shanghai') | 结束时间 |
| `duration` | Nullable(Int64) | 总耗时（ms） |
| `state` | LowCardinality(String) | 状态（如 pass） |
| `_time_second_` | DateTime('Asia/Shanghai') | 入库秒级时间 |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `applicantId` |
| 追踪ID | `traceId` |
| 时间 | `createTime`, `start` |

### 查询示例

```bash
# 查询某工作流实例详情
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT createTime, tenantId, workflowName, state, duration, applicantId FROM fs_flow_instance_log_dist WHERE workflowInstanceId = '<id>' AND _time_second_ >= now() - INTERVAL 7 DAY ORDER BY createTime DESC LIMIT 10"

# 统计近1小时异常流程
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT workflowName, state, COUNT(*) as cnt, avg(duration) as avg_dur FROM fs_flow_instance_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND state != 'pass' GROUP BY workflowName, state ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
