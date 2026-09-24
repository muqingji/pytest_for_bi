# schedule-task-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 调度任务事件流水日志分布式表，记录 xxl-job 等任务在集群中分片广播、状态转化的事件流水。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_, createTime, _time_nanosecond_

---

## 表：schedule_task_event_log_dist

**说明**: 调度任务事件流水日志分布式表，记录 xxl-job 等任务在集群中分片广播、状态转化的事件流水。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'schedule_task_event_log', rand(); Distributed('cluster01', 'logger', 'schedule_task_event_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_nanosecond_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime`, `_time_nanosecond_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime('Asia/Shanghai') | 事件写入 ClickHouse 的秒级时间戳 |
| `action` | LowCardinality(String) | 调度动作（如start/stop/trigger/sharding等） |
| `allowEndTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `allowStartTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `appName` | LowCardinality(String) | 应用name |
| `batchNum` | Int64 | 数量或统计计数值 |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `creator` | Int32 | 任务创建者用户ID |
| `currentCost` | Int64 | 执行或处理持续时长（毫秒） |
| `cycleType` | Int32 | 周期类型（如小时/天/周/月等） |
| `ea` | LowCardinality(String) | 企业账号/租户账号名称 |
| `errorMessage` | String | 错误message |
| `eventTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `executeCount` | Int32 | 数量或统计计数值 |
| `executeEndTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `executeStartTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `executeTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `executeType` | Int32 | 执行type |
| `extra` | String | 扩展信息/附加参数 |
| `failedNum` | Int64 | 数量或统计计数值 |
| `finishCode` | Int32 | finish代码 |
| `finishMsg` | String | 任务完成消息/结果描述 |
| `funcApiName` | String | func接口name |
| `id` | String | 记录唯一标识ID |
| `jobId` | String | 任务/定时任务id |
| `modifier` | Int32 | 任务修改者用户ID |
| `modifyTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `msgId` | String | 消息ID |
| `objApiName` | String | obj接口name |
| `objDataIds` | String | obj数据ids |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | LowCardinality(String) | 运行环境配置标识（如 prod, test, dev, ale 等） |
| `quotaNeedNum` | Int32 | 数量或统计计数值 |
| `quotaRemainNum` | Int32 | 数量或统计计数值 |
| `quotaTotalNum` | Int32 | 数量或统计计数值 |
| `requestId` | String | 请求id |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | LowCardinality(String) | 执行调度任务的服务器IP地址 |
| `spanId` | String | OpenTelemetry Span ID |
| `status` | Int32 | 状态码或状态标识（如 200, 500, 或 SUCCESS, FAILED） |
| `successNum` | Int64 | 数量或统计计数值 |
| `taskId` | String | 任务id |
| `taskName` | String | 任务name |
| `tenantId` | LowCardinality(String) | 租户/企业 ID |
| `totalCost` | Int64 | 执行或处理持续时长（毫秒） |
| `totalNum` | Int64 | 数量或统计计数值 |
| `traceId` | String | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `userId` | LowCardinality(String) | 操作用户的唯一标识 ID |
| `waitingCost` | Int64 | 执行或处理持续时长（毫秒） |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime`, `_time_nanosecond_` |

### 查询示例

```bash
# 查询失败的任务调度事件
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, taskId, taskName, action, status, finishCode, errorMessage, totalCost FROM schedule_task_event_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND status != 1 ORDER BY _time_second_ DESC LIMIT 50"

# 统计各任务分片执行情况
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT taskId, taskName, action, COUNT(*) as cnt, sum(successNum) as total_success, sum(failedNum) as total_fail FROM schedule_task_event_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY taskId, taskName, action ORDER BY total_fail DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
- ./job-schedule-log.md - Job调度事件日志
- ./xxl-job-log.md - XXL-Job调度日志
