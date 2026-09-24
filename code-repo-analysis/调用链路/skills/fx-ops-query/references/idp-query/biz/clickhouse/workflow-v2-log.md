# workflow-v2-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 业务工作流 V2 高级日志分布式表，记录改进版工作流引擎中复杂网关、并行任务分支的流转轨迹。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_, createTime

---

## 表：biz_log_workflow_v2_dist

**说明**: 业务工作流 V2 高级日志分布式表，记录改进版工作流引擎中复杂网关、并行任务分支的流转轨迹。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_workflow_v3', rand(); Distributed('cluster01', 'logger', 'biz_log_workflow_v3', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(tenantId, id)` |
| ORDER BY | `(tenantId, id)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime | 事件写入 ClickHouse 的秒级时间戳 |
| `appName` | Nullable(String) | 应用name |
| `batchType` | Nullable(String) | 批次类型 |
| `bizName` | Nullable(String) | 业务名称 |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `crudType` | Nullable(String) | CRUD操作类型(增删改查) |
| `dispatchCost` | Nullable(Int64) | 执行或处理持续时长（毫秒） |
| `ea` | Nullable(String) | 企业账号/租户账号名称 |
| `error` | String | 错误信息 / 异常堆栈 |
| `eventId` | Nullable(String) | 事件id |
| `executeCost` | Nullable(Int64) | 执行或处理持续时长（毫秒） |
| `finishTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `id` | String | 唯一标识 |
| `metadataDelayCost` | Nullable(Int64) | 执行或处理持续时长（毫秒） |
| `modifyTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `objectApiName` | Nullable(String) | 对象/实体 API 名称，例如: SalesOrderObj |
| `objectData` | String |  |
| `objectId` | Nullable(String) | 对象/实体id |
| `profile` | Nullable(String) | 运行环境配置标识（如 prod, test, dev, ale 等） |
| `ruleId` | String |  |
| `serverIp` | Nullable(String) | 服务端IP地址 |
| `source` | Nullable(String) | 来源 |
| `sourceCrudType` | String |  |
| `status` | Nullable(String) | 状态码或状态标识（如 200, 500, 或 SUCCESS, FAILED） |
| `tenantId` | String | 租户/企业 ID |
| `traceId` | Nullable(String) | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `tries` | Nullable(Int32) | 重试次数 |
| `triggerData` | Nullable(String) | trigger数据 |
| `userId` | Nullable(String) | 操作用户的唯一标识 ID |
| `version` | Int32 | 版本 |
| `waitingCost` | Nullable(Int64) | 执行或处理持续时长（毫秒） |
| `workflowId` | String |  |

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
# 查询某租户工作流V2执行记录
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, workflowId, objectApiName, status, error, executeCost FROM biz_log_workflow_v2_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 50"

# 统计并行任务分支异常
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT workflowId, COUNT(*) as cnt, sum(CASE WHEN error != '' THEN 1 ELSE 0 END) as errors FROM biz_log_workflow_v2_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY workflowId ORDER BY errors DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
- ./workflow-log.md - 工作流日志
- ./flow-instance-log.md - 流程实例日志
