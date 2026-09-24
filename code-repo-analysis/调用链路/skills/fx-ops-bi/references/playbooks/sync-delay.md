# sync-delay：BI 数据同步延迟排查

```yaml
symptom: 同步延迟 / 推送延迟 / 数据未更新 / copier 报错 / MQ 积压
inputs:
 required: [tenant_id, occurred_time]
 optional: [copier_task_id, mq_topic, table_name]
outputs:
 signals: [sync_lag_minutes, mq_consumer_lag, copier_error_rate, last_sync_timestamp]
 next_skills: [fx-ops-query, fx-ops-monitoring, fx-ops-tracing, fx-ops-knowledge]
escalate_when:
 - copier 完全停止消费 → 回抛主控（target_capability=fx-ops-tracing）追踪 copier 进程状态
 - MQ 大面积积压影响多租户 → 回抛 fx-ops 升级为 S2（MQ 积压根因排查归 fx-ops-mq，本模块只查 BI 消费视角）
```

## 排查步骤

> SQL 执行入口：按 `_common.md`「查询入口总表」选择 biz 与方言（CH 业务数据 `query bi-clickhouse`、copier 应用日志 `query biz-app-log`）。

### Step 1：确认数据新鲜度

对比仓库数据的最新时间戳与当前时间，量化延迟：

```sql
-- 查某张 CH 表的最新数据时间（替换表名和时间字段；时间列以 show columns 实测为准，agg_data 的 action_date 为 String，需 toDate 比较）
SELECT max(event_time) AS latest_data_time,
    now() - max(event_time) AS lag_interval
FROM <ch_table>
WHERE tenant_id = '<EI>'
```

如果 `lag_interval` 远超预期（如超过聚合窗口），说明确实存在同步延迟。

### Step 2：定位延迟环节

沿同步链路逐段排查：

**1. 源数据是否写入 op-log：**
- 查业务操作是否产生了 op-log 记录
- 对比操作时间与 op-log 写入时间

**2. MQ 消息是否发送：**
- 检查 MQ topic 的消息生产量
- 检查消费 lag（积压量）

**3. copier 是否正常消费：**
- 查 copier 服务日志是否有报错
- 查 copier 消费 offset 是否推进
- 查 copier 同步延迟监控指标

**4. 聚合框架是否完成：**
- 聚合任务状态（是否在 running / failed / queued）
- 聚合窗口是否已关闭
- 聚合结果是否写入 CH

### Step 3：根据定位结果取证

- **MQ 积压**：回抛主控（`target_capability=fx-ops-monitoring`）查 MQ 消费者指标
- **copier 报错**：回抛主控（`target_capability=fx-ops-tracing`）追踪 copier 错误日志；或按 `_common.md` 入口总表 `query biz-app-log` 查 copier 日志
- **聚合失败**：查聚合任务日志，确认失败原因（数据格式 / 字段缺失 / CH 写入拒绝）
- **CH 写入问题**：回抛主控（`target_capability=fx-ops-monitoring`）查 CH 写入指标

## 实战排查路径

### 路径 1：copier 同步延迟的完整追踪

用户反馈"数据改了但报表没变"或"数据是昨天的"：

**Step 1：确认源数据写入时间**

```sql
-- 查 op-log 最后写入时间
SELECT max(created_at) AS last_oplog_time
FROM <oplog_table>
WHERE object_api_name = '<obj>'
 AND tenant_id = '<TENANT_ID>'
```

**Step 2：确认 copier 消费进度**

```
服务：paas-bi-copier
日志关键词：consume、offset、lag、sync、error
MQ Topic：按业务对象对应的 topic 查
```

查 copier 日志：
- 最后消费的 offset 和时间戳
- 是否有报错（如 CH 写入拒绝、数据格式错误）
- 消费 lag（当前 offset vs 最新 offset 的差值）

**Step 3：确认数据到达 CH 的时间**

> CH 对象列因表而异：`agg_data`/`object_data` 为 `object_id`（无 `object_api_name`），日志类表以 `show columns` 实测为准；下面用 `<ch_object_col>` 占位。

```sql
SELECT max(event_time) AS ch_latest_time
FROM <ch_table>
WHERE tenant_id = '<EI>'
 AND <ch_object_col> = '<obj>'
```

对比 `last_oplog_time`、`copier_last_consume_time`、`ch_latest_time` 三者的差值，定位延迟发生在哪一段。

**Step 4：确认聚合任务是否完成**

```
服务：聚合框架（agg worker）
关键表：agg_data
```

即使数据已写入 CH（如 `object_data`/`agg_log_data_vN`；`mt_data` 字典在 PG 侧且 hwcloud 60001247 实测不存在，勿当作 CH 落点），聚合任务也可能延迟：
- 检查 agg 任务执行状态
- 检查 agg_data 的最新 event_time
- 如果是增量聚合，确认聚合窗口是否已关闭

### 路径 2：MQ 积压导致的大面积延迟

多租户同时反馈数据延迟时：

**Step 1：查 MQ consumer lag**

```
指标：consumer_lag（消费滞后量）
监控：回抛主控（target_capability=fx-ops-monitoring）查 MQ 集群指标
```

**Step 2：确认是否为 copier 服务级别故障**

- copier pod 是否重启过
- copier 消费线程是否全部阻塞
- 是否有大量 error 日志导致消费停滞

**Step 3：确认是否为 CH 写入瓶颈**

```sql
-- 检查 CH part merge 积压
SELECT database, table, count(*) AS parts_count
FROM clusterAllReplicas('default', system, parts)
WHERE active
GROUP BY database, table
ORDER BY parts_count DESC
LIMIT 20
```

如果某张表的 parts_count 异常高（如超过 3000），说明 part merge 积压，CH 写入变慢，导致 copier 消费阻塞。

## 常见根因

| 根因 | 特征 | 处置 |
| --- | --- | --- |
| copier 消费阻塞（下游 CH 写入慢） | MQ lag 持续增长，copier 日志有写入超时 | 检查 CH 写入性能、part merge 积压 |
| MQ 消息丢失 | op-log 有记录但 MQ 无消息 | 检查消息生产者是否正常 |
| 聚合窗口未关闭 | 数据在窗口期内，属于正常延迟 | 告知用户等待窗口关闭 |
| copier 重复消费/死循环 | 消费 offset 不推进，日志重复打印同一条 | 检查消费位点提交是否异常 |
| CH 副本同步延迟 | 写入成功但查询读到的数据不是最新的 | 检查 CH 副本同步状态 |

## 输出要求

本模块收口属**运维性能类**。MQ 积压根因（扩容/消费能力）归 fx-ops-mq，本模块只查 BI 消费视角，需跨界时回抛主控。

结论中必须包含：
- 延迟量化的具体数值（分钟/小时）
- 定位到的延迟环节
- 根因判断和证据
- 建议的恢复动作
- 收口行三选一：`排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下`
