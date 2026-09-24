# job-schedule-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: Job 定时任务调度事件日志分布式表，记录调度中心发出 Job 触发指令的事件流水及节点分布。 已知问题：show columns 可能包含 rpcId/spanId/parentSpanId，而底层 job_schedule_event_log_v 视图 SELECT 未解析这些列，导致真实 SELECT * 失败；需 DBA 对齐视图 DDL 与 Distributed 元数据。修复后重启 Pod 刷新内省缓存。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: createTime

---

## 表：job_schedule_event_log_dist

**说明**: Job 定时任务调度事件日志分布式表，记录调度中心发出 Job 触发指令的事件流水及节点分布。 已知问题：show columns 可能包含 rpcId/spanId/parentSpanId，而底层 job_schedule_event_log_v 视图 SELECT 未解析这些列，导致真实 SELECT * 失败；需 DBA 对齐视图 DDL 与 Distributed 元数据。修复后重启 Pod 刷新内省缓存。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'job_schedule_event_log_v', rand(); Distributed('cluster01', 'logger', 'job_schedule_event_log_v', rand() |
| PARTITION BY | `(logType, toYYYYMMDD(_time_second_))` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second` | DateTime | 事件写入ClickHouse的秒级时间戳 |
| `_time_nanosecond` | DateTime64(9, 'Asia/Shanghai') | 事件写入ClickHouse的纳秒级时间戳 |
| `create_time` | DateTime64(3, 'Asia/Shanghai') | 记录创建时间 |
| `appName` | LowCardinality(String) | 应用name |
| `serverIp` | String | 服务端IP地址 |
| `profile` | LowCardinality(String) | 运行环境配置标识（如 prod, test, dev, ale 等） |
| `ea` | String | 企业账号/租户账号名称 |
| `tenantId` | String | 租户/企业 ID |
| `userId` | String | 操作用户的唯一标识 ID |
| `traceId` | String | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `objApiName` | String | obj接口name |
| `bizDataId` | String | 业务数据id |
| `extra` | String | 扩展附加信息 |
| `jobId` | String | 任务/定时任务id |
| `jobParam` | String | 任务/定时任务param |
| `jobGroup` | String | 任务/定时任务group |
| `whereList` | String | 查询条件列表 |
| `ruleApiName` | String | rule接口name |
| `lastMessageId` | String | 最后一条消息ID |
| `executeResult` | String | 执行result |
| `createBy` | Nullable(Int32) | 创建者ID |
| `executeCount` | Nullable(Int32) | 执行count |
| `exceptionCount` | Nullable(Int32) | 异常计数 |
| `JobType` | LowCardinality(String) | 任务/定时任务type |
| `executeType` | LowCardinality(String) | 执行type |
| `newJobFlag` | LowCardinality(String) | new任务/定时任务flag |
| `needCallBack` | LowCardinality(String) | 是否需要回调 |
| `status` | LowCardinality(String) | 状态码或状态标识（如 200, 500, 或 SUCCESS, FAILED） |
| `action` | LowCardinality(String) | 操作动作 |
| `order` | Nullable(Int64) | 排序序号 |
| `costTime` | Nullable(Int64) | 操作耗时，单位为毫秒 (ms) |
| `updateTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 更新时间 |
| `startTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 开始时间 |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `completeTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 完成时间 |
| `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `spanId` | Nullable(String) | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 traceId 组合可定位链路中的单个节点 |
| `parentSpanId` | Nullable(String) | OpenTelemetry 父 Span ID，标识发起当前 span 的上游 span；根 span 或缺失上游时通常为空 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `createTime` |

### 查询示例

```bash
# 查询某任务近1小时调度事件
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT createTime, tenantId, jobId, jobGroup, action, status, executeResult, costTime FROM job_schedule_event_log_dist WHERE jobId = '<id>' AND _time_second >= now() - INTERVAL 1 HOUR ORDER BY createTime DESC LIMIT 50"

# 统计失败调度事件
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT jobId, jobGroup, status, COUNT(*) as cnt FROM job_schedule_event_log_dist WHERE _time_second >= now() - INTERVAL 1 HOUR AND status = 'FAILED' GROUP BY jobId, jobGroup, status ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
- ./xxl-job-log.md - XXL-Job调度日志
- ./schedule-task-log.md - 调度任务事件日志
