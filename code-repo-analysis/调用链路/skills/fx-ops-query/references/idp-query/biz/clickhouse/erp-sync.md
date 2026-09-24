# erp-sync

> schema_verified_at: 2026-08-21 | source: foneshare `system.columns` / `system.tables`；`biz_log_erp_sync_log_dist` 与 `erp_sync_monitor_dist` 另经 `show columns` 对齐

覆盖 5 张集成/同步日志表。SQL 一律 `fx-ops idp query biz-app-log --sql "SELECT ... FROM <表名>"`，**不要**在 `FROM` 里写库名。

| 表名 | 物理库 | 强制时间过滤列 | 有 `_time_second_` | 用途 |
| --- | --- | --- | --- | --- |
| `biz_log_erpsyncdata_dist` | `logger`（local `biz_log`） | **`_time_second_`** | 是 | ERP 吞吐与分阶段耗时 |
| `biz_log_erp_ipaas_log_dist` | `erp_sync` | **`createTime`** | **否** | iPaaS 2.0 集成流结束态 |
| `biz_log_erp_ipaas_probe_log_dist` | `erp_sync` | **`createTime`** | **否** | iPaaS probe / 试跑 |
| `biz_log_erp_sync_log_dist` | `erp_sync` | **`createTime`** | **否** | ERP Sync 1.0 全链路 |
| `erp_sync_monitor_dist` | `logger`（local `biz_log`） | **`_time_second_`** | 是 | 集成通道健康度 |

**erp_sync 库铁律**：无 `_time_second_`。写 `_time_second_` 会 `column_not_found`。分区走 `createTime`。

`show columns` 在 foneshare/firstshare 对 `biz_log_erpsyncdata_dist` / `biz_log_erp_ipaas_log_dist` / `biz_log_erp_ipaas_probe_log_dist` 返回 **404**；`query` 与 `system.columns` 均可用。字段以本页为准，执行前仍应 `show columns`（成功则覆盖本页类型）。

---

## 表：biz_log_erpsyncdata_dist

**说明**: ERP 数据同步吞吐与分阶段耗时明细。含 `sendDoDispatcherTime` / `parseTime` / `listenTime` / `allFinishTime`。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: `_time_second_`（分区/主过滤）；`createTime` 仅展示

### 存储与索引

> schema_verified_at: 2026-08-21 | local: `biz_log.biz_log_erpsyncdata`

| 项 | 值 |
| --- | --- |
| ENGINE | foneshare 实测 `Distributed('cluster01', 'biz_log', 'biz_log_erpsyncdata', rand())` |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| 时间列（查询） | **`_time_second_`** |

### 字段定义

物理列（`logger.biz_log_erpsyncdata_dist`）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime | 入库秒级时间（分区/主过滤） |
| `afterSyncFailed` | Nullable(Bool) | 同步后处理失败 |
| `afterSyncFailedMsg` | String | 同步后失败信息 |
| `allCost` | Nullable(Int32) | 全流程耗时 (ms) |
| `allFinishTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 全流程结束时间 |
| `appName` | Nullable(String) | 服务名称 |
| `count` | Nullable(Int32) | 条数 |
| `cplProcessCost` | Nullable(Int32) | CPL 处理耗时 |
| `cplTriggerCost` | Nullable(Int32) | CPL 触发耗时 |
| `cplWriteCost` | Nullable(Int32) | CPL 写入耗时 |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 事件创建时间（仅展示） |
| `dispatchMqWaitingCost` | Nullable(Int32) | 调度 MQ 等待耗时 |
| `dispatchWaitingCost` | Nullable(Int32) | 调度等待耗时 |
| `ea` | Nullable(String) | 租户账号 |
| `listenTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 监听时间 |
| `parentSpanId` | Nullable(String) | OpenTelemetry 父 Span ID |
| `parseTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 解析时间 |
| `processCost` | Nullable(Int32) | 处理耗时 |
| `reWriteFailed` | Nullable(Bool) | 回写失败 |
| `reWriteFailedMsg` | String | 回写失败信息 |
| `reverseWrite2CrmCost` | Nullable(Int32) | 回写 CRM 耗时 |
| `rpcId` | Nullable(String) | RPC 标识 |
| `sendDoDispatcherTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 发送到 dispatcher 时间 |
| `serverIp` | Nullable(String) | 服务 IP |
| `sourceDataId` | Nullable(String) | 源数据 ID |
| `sourceObjApiName` | Nullable(String) | 源对象 API 名 |
| `spanId` | Nullable(String) | Span ID |
| `syncCost` | Nullable(Int32) | 同步耗时 |
| `syncDataId` | Nullable(String) | 同步数据 ID |
| `syncStepException` | Nullable(Bool) | 同步步骤异常 |
| `syncStepExceptionMsg` | String | 同步步骤异常信息 |
| `tenantId` | Nullable(String) | 租户 ID |
| `throwable` | Nullable(Bool) | 是否抛异常 |
| `throwableMsg` | String | 异常信息 |
| `traceId` | Nullable(String) | 追踪 ID |
| `triggerCost` | Nullable(Int32) | 触发耗时 |
| `writeCost` | Nullable(Int32) | 写入耗时 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 追踪ID | `traceId` |
| 源对象 | `sourceObjApiName` |
| 时间 | **`_time_second_`** |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, ea, sourceObjApiName, sourceDataId, allCost, syncCost, writeCost, processCost, throwable, throwableMsg, syncStepException, traceId FROM biz_log_erpsyncdata_dist WHERE tenantId = '<EI>' AND _time_second_ >= '<START>' AND _time_second_ <= '<END>' ORDER BY _time_second_ DESC LIMIT 50"
```

---

## 表：biz_log_erp_ipaas_log_dist

**说明**: iPaaS 2.0 集成流**结束态**日志。在 `ended` 回调写入；查不到不等于未执行（可能仍在运行或结束态未上报）。**无** `_time_second_` / `rpcId`。

**租户ID字段**: `tenantId`

**时间字段**: **`createTime`**（分区/主过滤）；事件时间 `startTime` / `endTime` / `updateTime`

### 存储与索引

> schema_verified_at: 2026-08-21 | local: `erp_sync.biz_log_erp_ipaas_log`

| 项 | 值 |
| --- | --- |
| ENGINE | `Distributed('func-cluster01', 'erp_sync', 'biz_log_erp_ipaas_log', cityHash64(workflowInstanceId))` |
| PARTITION BY | `toYYYYMM(createTime)`（**按月**，不是 `toYYYYMMDD`） |
| PRIMARY KEY | `(tenantId, startTime, endState)` |
| ORDER BY | `(tenantId, startTime, endState)` |
| 时间列（查询） | **`createTime`** |

### 字段定义

物理列 20 个（`erp_sync.biz_log_erp_ipaas_log_dist`）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `appName` | LowCardinality(String) | 服务名称 |
| `cost` | UInt64 | 耗时 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 日志上报时间（分区/主过滤） |
| `customerLevel` | LowCardinality(String) | 客户等级 |
| `dataId` | String | 业务数据 ID |
| `endState` | LowCardinality(String) | 结束状态 |
| `endTime` | DateTime64(3, 'Asia/Shanghai') | 结束时间 |
| `expireTime` | DateTime64(3, 'Asia/Shanghai') | 过期时间 |
| `flowApiName` | LowCardinality(String) | 集成流 API 名 |
| `flowName` | String | 集成流名称（不稳定主键） |
| `flowVersion` | String | 流版本 |
| `nodeLogs` | String | 节点日志 JSON |
| `remark` | String | 备注 / 失败说明 |
| `serverIp` | String | 服务 IP |
| `startTime` | DateTime64(3, 'Asia/Shanghai') | 开始时间（排序键） |
| `tenantId` | String | 租户 ID |
| `traceId` | String | 追踪 ID |
| `updateTime` | DateTime64(3, 'Asia/Shanghai') | 更新时间 |
| `variables` | String | 变量 JSON |
| `workflowInstanceId` | String | 运行实例 ID（主锚点） |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 实例ID | `workflowInstanceId` |
| 流 API | `flowApiName` |
| 追踪ID | `traceId` |
| 时间 | **`createTime`** |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT createTime, startTime, endTime, tenantId, traceId, workflowInstanceId, flowApiName, flowVersion, dataId, endState, remark, cost, nodeLogs FROM biz_log_erp_ipaas_log_dist WHERE tenantId = '<EI>' AND createTime >= '<START>' AND createTime <= '<END>' AND flowApiName = '<FLOW_API_NAME>' ORDER BY createTime DESC LIMIT 50"
```

锚点优先级：`workflowInstanceId` > `traceId` > `flowApiName + dataId + 时间窗`。`flowName` 不是稳定主键。

---

## 表：biz_log_erp_ipaas_probe_log_dist

**说明**: iPaaS probe / 试跑日志。**无** `_time_second_`，**无** `traceId`。

**租户ID字段**: `tenantId`

**时间字段**: **`createTime`**（分区）；事件时间 `execTime` / `startTime` / `endTime`

### 存储与索引

> schema_verified_at: 2026-08-21 | local: `erp_sync.biz_log_erp_ipaas_probe_log`

| 项 | 值 |
| --- | --- |
| ENGINE | `Distributed('func-cluster01', 'erp_sync', 'biz_log_erp_ipaas_probe_log', cityHash64(tenantId, flowApiName))` |
| PARTITION BY | `toYYYYMMDD(createTime)` |
| PRIMARY KEY | `(tenantId, flowApiName, execTime)` |
| ORDER BY | `(tenantId, flowApiName, execTime)` |
| 时间列（查询） | **`createTime`** |

### 字段定义

物理列 20 个。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `connectorKey` | String | 连接器 key |
| `cost` | Int32 | 耗时 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 上报时间（分区/主过滤） |
| `dataList` | String | 探测数据 |
| `dataListSize` | Int32 | 数据条数 |
| `endTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 结束时间 |
| `execStatus` | Int8 | 执行状态 |
| `execTime` | DateTime64(3, 'Asia/Shanghai') | 执行时间（排序键） |
| `flowApiName` | String | 集成流 API 名 |
| `flowName` | String | 集成流名称 |
| `historyTaskId` | String | 历史任务 ID |
| `logId` | String | 日志 ID |
| `probeLimit` | Int32 | probe limit |
| `probeOffset` | Int32 | probe offset |
| `probeType` | String | probe 类型 |
| `requestParam` | String | 请求参数 |
| `requestUrl` | String | 请求 URL |
| `startTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 开始时间 |
| `tenantId` | String | 租户 ID |
| `triggerKey` | String | 触发 key |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT createTime, execTime, tenantId, flowApiName, probeType, execStatus, cost, requestUrl, connectorKey, logId FROM biz_log_erp_ipaas_probe_log_dist WHERE tenantId = '<EI>' AND createTime >= '<START>' AND createTime <= '<END>' AND flowApiName = '<FLOW_API_NAME>' ORDER BY execTime DESC LIMIT 50"
```

---

## 表：biz_log_erp_sync_log_dist

**说明**: ERP Sync 1.0 集成同步全链路（源/目标数据、调用状态、耗时、错误）。**无** `_time_second_`。物理列**无** `rpcId` / `spanId` / `parentSpanId`。

**租户ID字段**: `tenantId`

**时间字段**: **`createTime`**（分区/主过滤）；`callTime` / `returnTime` 为 Int64 毫秒；`updateTime` 为 DateTime64

### 存储与索引

> schema_verified_at: 2026-08-21 | `show columns` + local `erp_sync.biz_log_erp_sync_log`

| 项 | 值 |
| --- | --- |
| ENGINE | `Distributed('func-cluster01', 'erp_sync', 'biz_log_erp_sync_log', cityHash64(id))` |
| PARTITION BY | `toYYYYMMDD(createTime)` |
| PRIMARY KEY | `(tenantId, id)` |
| ORDER BY | `(tenantId, id)` |
| TTL | `toDateTime(expireTime)` |
| 时间列（查询） | **`createTime`** |

### 字段定义

物理列以 `show columns` 为准（与 `system.columns` 列名一致）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `appName` | LowCardinality(String) | 服务名称 |
| `arg` | Nullable(String) |  |
| `callTime` | Nullable(Int64) | 调用时间（毫秒时间戳） |
| `costTime` | Nullable(Int32) | 耗时（毫秒） |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 日志上报时间（分区/主过滤） |
| `data` | Nullable(String) |  |
| `dataReceiveType` | LowCardinality(Nullable(String)) |  |
| `dcId` | LowCardinality(Nullable(String)) |  |
| `destData` | Nullable(String) |  |
| `destDataId` | Nullable(String) |  |
| `destEventType` | LowCardinality(Nullable(String)) |  |
| `destObjectApiName` | LowCardinality(Nullable(String)) |  |
| `destTenantType` | LowCardinality(Nullable(String)) |  |
| `erpTempData` | Nullable(String) |  |
| `erpTempDataDataId` | Nullable(String) |  |
| `erpTempDataDataNumber` | Nullable(String) |  |
| `erpTempDataTaskNum` | Array(Nullable(String)) | 临时库数据轮询任务编码 |
| `errorCode` | LowCardinality(Nullable(String)) |  |
| `expireTime` | DateTime64(3, 'Asia/Shanghai') | 过期时间 |
| `id` | String | 主键 ID |
| `interfaceMonitorStatus` | LowCardinality(Nullable(String)) |  |
| `interfaceMonitorType` | LowCardinality(Nullable(String)) |  |
| `isDeleted` | Nullable(Bool) |  |
| `logId` | Nullable(String) | 日志 ID |
| `logType` | LowCardinality(String) | 日志类型 |
| `needReturnDestObjectData` | Nullable(String) |  |
| `objApiName` | LowCardinality(Nullable(String)) |  |
| `operatorId` | LowCardinality(Nullable(String)) |  |
| `realObjApiName` | LowCardinality(Nullable(String)) |  |
| `remark` | Nullable(String) |  |
| `result` | Nullable(String) |  |
| `resultDataPresent` | LowCardinality(Nullable(String)) |  |
| `returnTime` | Nullable(Int64) | 返回时间（毫秒时间戳） |
| `serverIp` | String | 发出日志的服务器 IP |
| `sourceData` | Nullable(String) |  |
| `sourceDataId` | Nullable(String) |  |
| `sourceDetailSyncDataIds` | Nullable(String) |  |
| `sourceEventType` | LowCardinality(Nullable(String)) |  |
| `sourceObjectApiName` | LowCardinality(Nullable(String)) |  |
| `sourceTenantType` | LowCardinality(Nullable(String)) |  |
| `streamId` | Nullable(String) |  |
| `syncDataId` | Nullable(String) |  |
| `syncDataStatus` | LowCardinality(Nullable(String)) |  |
| `syncLogStatus` | LowCardinality(Nullable(String)) |  |
| `syncPloyDetailSnapshotId` | Nullable(String) |  |
| `sync_log_is_deleted` | UInt8 | 同步日志删除标记 |
| `sync_log_version` | DateTime64(3, 'Asia/Shanghai') | 同步日志版本 |
| `tenantId` | LowCardinality(String) | 企业/租户 ID |
| `timeFilterArg` | Nullable(String) |  |
| `timeFilterArgEndTime` | Nullable(Int64) | 筛选结束时间 |
| `timeFilterArgFilters` | Nullable(String) |  |
| `timeFilterArgLimit` | LowCardinality(Nullable(String)) |  |
| `timeFilterArgOffset` | LowCardinality(Nullable(String)) |  |
| `timeFilterArgStartTime` | Nullable(Int64) | 筛选开始时间 |
| `traceId` | Nullable(String) | 链路追踪 ID |
| `type` | LowCardinality(Nullable(String)) |  |
| `updateTime` | DateTime64(3, 'Asia/Shanghai') | 日志更新时间 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 追踪ID | `traceId` |
| 时间 | **`createTime`** |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT createTime, tenantId, traceId, objApiName, sourceObjectApiName, destObjectApiName, syncDataStatus, errorCode, costTime, id FROM biz_log_erp_sync_log_dist WHERE tenantId = '<EI>' AND createTime >= '<START>' AND createTime <= '<END>' ORDER BY createTime DESC LIMIT 50"
```

---

## 表：erp_sync_monitor_dist

**说明**: ERP 集成通道健康度（泛化 cost/label/time/num 槽位）。库：`logger`。过滤走 `_time_second_`。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: `_time_second_`（分区/主过滤）；`createTime` 仅展示

### 存储与索引

> schema_verified_at: 2026-08-21 | `show columns` + local `biz_log.erp_sync_monitor`

| 项 | 值 |
| --- | --- |
| ENGINE | foneshare 实测 `Distributed('cluster01', 'biz_log', 'erp_sync_monitor', rand())` |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| 时间列（查询） | **`_time_second_`** |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime | 入库秒级时间（分区/主过滤） |
| `action` | String | 操作动作 |
| `appName` | String | 应用名 |
| `cost1` | Int64 | 耗时槽 1 (ms) |
| `cost2` | Int64 | 耗时槽 2 (ms) |
| `cost3` | Int64 | 耗时槽 3 (ms) |
| `cost4` | Int64 | 耗时槽 4 (ms) |
| `cost5` | Int64 | 耗时槽 5 (ms) |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 事件时间（仅展示） |
| `ea` | String | 租户账号 |
| `eventId` | String | 事件 ID |
| `label1` | String | 标签 1 |
| `label2` | String | 标签 2 |
| `label3` | String | 标签 3 |
| `label4` | String | 标签 4 |
| `label5` | String | 标签 5 |
| `message` | String | 消息 / 异常 |
| `module` | String | 模块 |
| `num1` | Int64 | 计数槽 1 |
| `num2` | Int64 | 计数槽 2 |
| `num3` | Int64 | 计数槽 3 |
| `num4` | Int64 | 计数槽 4 |
| `num5` | Int64 | 计数槽 5 |
| `parameters` | String | 请求参数 |
| `parentSpanId` | Nullable(String) | 父 Span ID |
| `profile` | String | 环境标识 |
| `response` | String | 响应 |
| `rpcId` | Nullable(String) | RPC 标识 |
| `serverIp` | String | 服务 IP |
| `spanId` | Nullable(String) | Span ID |
| `status` | String | 状态 |
| `tenantId` | String | 租户 ID |
| `time1` | DateTime64(3, 'Asia/Shanghai') | 时间槽 1 |
| `time2` | DateTime64(3, 'Asia/Shanghai') | 时间槽 2 |
| `time3` | DateTime64(3, 'Asia/Shanghai') | 时间槽 3 |
| `time4` | DateTime64(3, 'Asia/Shanghai') | 时间槽 4 |
| `time5` | DateTime64(3, 'Asia/Shanghai') | 时间槽 5 |
| `traceId` | String | 追踪 ID |
| `userId` | String | 用户 ID |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, ea, appName, module, action, status, message, cost1, traceId FROM erp_sync_monitor_dist WHERE tenantId = '<EI>' AND _time_second_ >= '<START>' AND _time_second_ <= '<END>' ORDER BY _time_second_ DESC LIMIT 50"
```

---

## 集成取证标准 SQL

执行前 `show columns`；`show columns` 404 时按本页字段写 SQL（catalog 缺口，表仍可 query）。

```sql
-- 1) iPaaS 2.0 结束态（时间列 createTime；无 _time_second_）
SELECT createTime, startTime, endTime, tenantId, traceId, workflowInstanceId,
       flowApiName, flowVersion, dataId, endState, remark, cost, nodeLogs
FROM biz_log_erp_ipaas_log_dist
WHERE tenantId = '<EI>'
  AND createTime >= '<START>' AND createTime <= '<END>'
  AND flowApiName = '<FLOW_API_NAME>'
ORDER BY createTime DESC
LIMIT 50
```

```sql
-- 2) ERP 吞吐 / 失败（时间列 _time_second_）
SELECT _time_second_, tenantId, ea, sourceObjApiName, sourceDataId,
       allCost, syncCost, writeCost, processCost,
       sendDoDispatcherTime, parseTime, listenTime, allFinishTime,
       throwable, throwableMsg, syncStepException, afterSyncFailed, reWriteFailed, traceId
FROM biz_log_erpsyncdata_dist
WHERE tenantId = '<EI>'
  AND _time_second_ >= '<START>' AND _time_second_ <= '<END>'
  AND (throwable = 1 OR syncStepException = 1 OR afterSyncFailed = 1 OR reWriteFailed = 1)
ORDER BY _time_second_ DESC
LIMIT 50
```

```sql
-- 3) ERP Sync 1.0 全链路（时间列 createTime；无 _time_second_）
SELECT createTime, tenantId, traceId, objApiName, sourceObjectApiName, destObjectApiName,
       syncDataStatus, errorCode, costTime, id
FROM biz_log_erp_sync_log_dist
WHERE tenantId = '<EI>'
  AND createTime >= '<START>' AND createTime <= '<END>'
ORDER BY createTime DESC
LIMIT 50
```

```sql
-- 4) ERP 同步量 TopN 企业（长窗聚合；_time_second_ 为 DateTime，epoch 秒用 toDateTime）
-- 已实测：近 30 天窗口 + GROUP BY ea 可正常返回；count 为单次同步条数
SELECT ea, sum(count) AS cnt
FROM biz_log_erpsyncdata_dist
WHERE _time_second_ >= toDateTime(<START_EPOCH_SEC>)
  AND _time_second_ < toDateTime(<END_EPOCH_SEC>)
GROUP BY ea
ORDER BY cnt DESC
LIMIT 20
```

---

## 相关文档

- [index.md](./index.md) - ClickHouse 表定义索引
- [openapi-log.md](./openapi-log.md) - 入站 OpenAPI
- [egress-log.md](./egress-log.md) - 出站 HTTP
- [high-frequency-cheatsheet.md](./high-frequency-cheatsheet.md) - 时间列规约
