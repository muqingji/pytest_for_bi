# hulian-log（互联日志）

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 互联同步第一阶段日志，记录数据从源租户分发到目标租户时的匹配和分发结果

**租户ID字段**: `tenantId`, `sourceTenantId`

**时间字段**: _time_second_, createTime

---

## 表：crm_syncfirststage_dist

**说明**: 互联同步第一阶段日志，记录数据从源租户分发到目标租户时的匹配和分发结果

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('func-cluster01', 'hulian_log', 'crm_syncfirststage', rand() |
| PARTITION BY | `toYYYYMMDD(createTime)` |
| PRIMARY KEY | `(sourceTenantId, sourceApiName, sourceDataId, createTime)` |
| ORDER BY | `(sourceTenantId, sourceApiName, sourceDataId, createTime)` |
| TTL | `toDateTime(createTime) + toIntervalDay(3)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime('Asia/Shanghai') | 入库秒级时间 |
| `conditionData` | String | 条件数据（JSON） |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `dataResults` | Array(String) | 数据处理结果 |
| `dataVersion` | String | 数据版本 |
| `eventIdList` | String | 事件 ID 列表 |
| `funResults` | Array(String) | 函数执行结果 |
| `historyPloyDetailId` | String | 历史策略详情 ID |
| `id` | String | 主键 ID |
| `lifeStatus` | String | 生命周期状态 |
| `mappingId` | String | 映射 ID |
| `opType` | LowCardinality(String) | 操作类型 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `snapshotIds` | Array(String) | 快照 ID 列表 |
| `snapshotVersionCodes` | Array(Int64) | 快照版本编码列表 |
| `sourceApiName` | String | 源对象 API 名称（如 ProductObj） |
| `sourceData` | String | 源数据内容（JSON） |
| `sourceDataId` | String | 源数据 ID |
| `sourceDataName` | String | 源数据名称 |
| `sourceEventType` | LowCardinality(String) | 源事件类型 |
| `sourceTenantId` | String | 源租户 ID |
| `spanId` | String | OpenTelemetry Span ID |
| `taskIds` | String | 任务 ID |
| `tenantId` | String | 目标租户 ID 列表（JSON 数组字符串） |
| `tenantResults` | Array(String) | 各目标租户的分发结果 |
| `traceId` | String | 追踪 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId`, `sourceTenantId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

1.根据traceId查询
```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM crm_syncfirststage_dist WHERE traceId='E-S.721787-6a0e7c9d20249f00078eaa68-SalesOrderObj-05cedb' and _time_second_ >=  now() - INTERVAL 1 HOUR LIMIT 50"
```
2.根据sourceDataId查询
```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM crm_syncfirststage_dist WHERE sourceDataId ='6a30b6741634f500064a1615' and _time_second_ >=  now() - INTERVAL 1 HOUR LIMIT 50"
```

## 表：crm_syncsecondstage_dist

**说明**: 互联同步第二阶段日志，记录数据在目标租户侧的实际写入结果（包括目标数据、函数处理结果和同步状态）

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('func-cluster01', 'hulian_log', 'crm_syncsecondstage', rand() |
| PARTITION BY | `toYYYYMM(createTime)` |
| PRIMARY KEY | `(sourceTenantId, sourceApiName, sourceDataId, destTenantId, createTime)` |
| ORDER BY | `(sourceTenantId, sourceApiName, sourceDataId, destTenantId, createTime)` |
| TTL | `toDateTime(createTime) + toIntervalDay(360)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 入库纳秒时间 |
| `_time_second_` | DateTime('Asia/Shanghai') | 入库秒级时间 |
| `afterDuringFucResult` | String | 后置函数处理结果 |
| `afterFuncResult` | String | 后置函数结果 |
| `beforeDuringFucResult` | String | 前置函数处理结果 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `dataVersion` | String | 数据版本 |
| `destData` | String | 目标数据内容（JSON） |
| `destDataId` | String | 目标数据 ID |
| `destDataName` | String | 目标数据名称 |
| `destEventType` | LowCardinality(String) | 目标事件类型 |
| `destTenantId` | String | 目标租户 ID |
| `eventIdArr` | Array(String) | 事件 ID 数组 |
| `eventIdList` | String | 事件 ID 列表 |
| `failDependDataResult` | Array(String) | 依赖数据失败结果 |
| `historyPloyDetailId` | String | 历史策略详情 ID |
| `id` | String | 主键 ID |
| `lifeStatus` | String | 生命周期状态 |
| `mappingId` | String | 映射 ID |
| `opType` | LowCardinality(String) | 操作类型 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `relationResult` | String | 关联结果 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `sourceApiName` | String | 源对象 API 名称 |
| `sourceData` | String | 源数据内容（JSON） |
| `sourceDataId` | String | 源数据 ID |
| `sourceDataName` | String | 源数据名称 |
| `sourceEventType` | LowCardinality(String) | 源事件类型 |
| `sourceTenantId` | String | 源租户 ID |
| `spanId` | String | OpenTelemetry Span ID |
| `syncStatus` | String | 同步状态（如 6=成功） |
| `taskIds` | String | 任务 ID |
| `tenantId` | String | 源租户 ID |
| `traceId` | String | 追踪 ID |
| `writeResult` | String | 写入结果（JSON） |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId`, `destTenantId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

1.根据traceId查询
```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM crm_syncsecondstage_dist WHERE traceId='E-S.721787-6a0e7c9d20249f00078eaa68-SalesOrderObj-05cedb' and _time_second_ >=  now() - INTERVAL 1 HOUR LIMIT 50"
```
2.根据sourceDataId查询
```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM crm_syncsecondstage_dist WHERE sourceDataId='6a30b6741634f500064a1615' and _time_second_ >=  now() - INTERVAL 1 HOUR LIMIT 50"
```

## 表：crm_syncdata_dist

**说明**: CRM 数据双向同步分布式表，记录多租户客户/联系人等核心业务实体的准实时增量同步日志。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'crm_syncdata', rand(); Distributed('cluster01', 'logger', 'crm_syncdata', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime('Asia/Shanghai') | 事件写入 ClickHouse 的秒级时间戳 |
| `clientIp` | String | 客户端真实 IP 地址 |
| `cost` | Nullable(Int64) | 操作耗时，单位为毫秒 (ms) |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `delay` | Nullable(Int64) | 同步延迟（毫秒） |
| `destDataId` | String | dest数据id |
| `destEventType` | Nullable(Int32) | dest事件type |
| `destObjectApiName` | String | dest对象/实体接口name |
| `destTenantId` | String | dest租户id |
| `errorCode` | String | 错误代码 |
| `errorMessage` | String | 错误message |
| `operateType` | Nullable(Int32) | 操作type |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `podId` | String | K8s Pod标识 |
| `profile` | LowCardinality(String) | 运行环境配置标识（如 prod, test, dev, ale 等） |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `sourceDataId` | String | source数据id |
| `sourceEventType` | Nullable(Int32) | source事件type |
| `sourceObjectApiName` | String | source对象/实体接口name |
| `sourceTenantId` | String | source租户id |
| `spanId` | String | OpenTelemetry Span ID |
| `syncPloyDetailSnapshotId` | String | 同步ploy明细/详情snapshotid |
| `syncStatus` | Nullable(Int32) | 同步status |
| `tenantId` | String | 租户/企业 ID |
| `traceId` | String | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `tries` | Nullable(Int32) | 重试次数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

1.根据traceId查询
```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM crm_syncdata_dist WHERE traceId='E-S.721787-6a0e7c9d20249f00078eaa68-SalesOrderObj-05cedb' and _time_second_ >=  now() - INTERVAL 1 HOUR LIMIT 50"
```
2.根据sourceDataId查询
```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM crm_syncdata_dist WHERE sourceDataId='6a30b6741634f500064a1615' and _time_second_ >=  now() - INTERVAL 1 HOUR LIMIT 50"
```

## 表：paas_metadata_changes_dist

**说明**: 业务元数据变更 oplog，记录元数据变更事件的详细过程，包括操作类型、涉及对象、各步骤耗时等。用于追踪业务层发出的元数据变更操作。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'paas_metadata_changes', rand(); Distributed('cluster01', 'logger', 'paas_metadata_changes', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime | 日志采集时间（秒级） |
| `action` | Nullable(String) | 操作类型 |
| `appName` | Nullable(String) | 应用名称 |
| `caller` | String |  |
| `cost` | Nullable(Int64) | 总耗时(ms) |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `ea` | Nullable(String) | 租户账号 |
| `error` | String | 错误信息 / 异常堆栈 |
| `eventId` | String |  |
| `extra` | Nullable(String) | 扩展信息 |
| `isImportPreProcessing` | String |  |
| `isUnionImport` | String |  |
| `message` | String |  |
| `module` | String |  |
| `num` | Nullable(Int32) | 数量 |
| `objectApiName` | String | 对象API名称 |
| `objectApiNames` | Array(String) | 对象API名称列表 |
| `objectId` | String | 对象ID |
| `objectIds` | Array(String) | 对象ID列表 |
| `parameters` | String |  |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | Nullable(String) | 环境标识 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | Nullable(String) | 服务端IP |
| `spanId` | String | OpenTelemetry Span ID |
| `status` | String |  |
| `step1Cost` | Nullable(Int64) | 步骤1耗时(ms) |
| `step2Cost` | Nullable(Int64) | 步骤2耗时(ms) |
| `step3Cost` | Nullable(Int64) | 步骤3耗时(ms) |
| `step4Cost` | Nullable(Int64) | 步骤4耗时(ms) |
| `step5Cost` | Nullable(Int64) | 步骤5耗时(ms) |
| `step6Cost` | Nullable(Int64) | 步骤6耗时(ms) |
| `step7Cost` | Nullable(Int64) | 步骤7耗时(ms) |
| `tenantId` | Nullable(String) | 租户ID |
| `traceId` | Nullable(String) | 链路追踪ID |
| `userId` | String | 用户 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_` |

### 查询示例

1.根据objectId查询
```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM paas_metadata_changes_dist WHERE objectId ='6a311a927673a700078653b3' and _time_second_ >=  now() - INTERVAL 1 HOUR LIMIT 50"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
