# xxl-job-log（XXL-Job / 调度任务日志）

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: XXL-Job 类调度排查需按 **profile 选表**：

| profile | 表 | 说明 |
| --- | --- | --- |
| **foneshare（默认）** | **`schedule_task_event_log_dist`**（首选）/ `job_schedule_event_log_dist` | 公有云 **无** `xxl_job_schedule_log_dist` |
| **ale / mengniu** | `xxl_job_schedule_log_dist` | 专有云 XXL 原生调度表 |

完整 `schedule_task_*` / `job_schedule_*` 字段见 [schedule-task-log.md](./schedule-task-log.md)、[job-schedule-log.md](./job-schedule-log.md)。

**租户 ID 字段**: schedule/job 表常有 `tenantId`；xxl 原生表无  
**时间字段**: `_time_second_`, `createTime`

---

## foneshare 首选：`schedule_task_event_log_dist`

调度任务事件流水（描述含 xxl-job 等任务分片/状态）。**公有云 Job 排查优先本表。**

```bash
# 失败/异常任务
fx-ops idp --profile foneshare query biz-app-log --sql "
SELECT _time_second_, tenantId, ea, taskId, taskName, jobId, action, status,
       finishCode, errorMessage, totalCost, successNum, failedNum
FROM schedule_task_event_log_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND status != 1
ORDER BY _time_second_ DESC
LIMIT 50
" -j

# 按任务聚合失败
fx-ops idp --profile foneshare query biz-app-log --sql "
SELECT taskId, taskName, action, count() AS cnt,
       sum(failedNum) AS total_fail, max(totalCost) AS max_cost
FROM schedule_task_event_log_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
GROUP BY taskId, taskName, action
ORDER BY total_fail DESC
LIMIT 20
" -j
```

备选调度中心事件：`job_schedule_event_log_dist`（`jobId` / `status` / `costTime` / `executeResult`）。

---

## ale / mengniu：`xxl_job_schedule_log_dist`

XXL-Job 原生：触发/执行码、handleLog、cost。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `jobId` / `jobGroup` / `jobDesc` | | 任务 |
| `triggerTime` / `triggerCode` / `triggerMsg` | | 触发 |
| `handleTime` / `handleCode` / `handleMsg` / `handleLog` | | 执行 |
| `cost` | Int64 | 耗时 ms |
| `_time_second_` / `createTime` | | 时间 |

```bash
fx-ops idp --profile ale query biz-app-log --sql "
SELECT createTime, jobId, jobDesc, triggerCode, triggerMsg, handleCode, handleMsg, cost
FROM xxl_job_schedule_log_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND handleCode != 200
ORDER BY createTime DESC
LIMIT 50
" -j
```

foneshare 上对该表 `show columns` / `query` 会 **404**，应改走上一节。

---

## 相关文档

- [schedule-task-log.md](./schedule-task-log.md)
- [job-schedule-log.md](./job-schedule-log.md)
- [table-alias-map.md](./table-alias-map.md)
- [index.md](./index.md)
