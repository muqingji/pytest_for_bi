# fs-bi-warehouse 全链路走读手册（10 条主链路）

> 用法：每一条链路都从「API 接口文件 / MQ 消费者 → 方法 → 服务 → 数据层/RPC」完整串联。你只需要按顺序打开文件、找到方法，一行行看。
> 仓库根：`/Users/muqingji/code/Data/fs-bi-warehouse`；主代码模块是 `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/`，公共消息体在 `warehouse-common/.../warehouse/common/mq/message/`，下文路径都省略这些前缀。
> 行号为当前代码实际行号，找不到就按类名/方法名搜索。
> **跨服务跳转指引**：warehouse 是「大数据计算侧」，大部分接口是**被动接收**：被 fs-bi / crm-report / udf-report 调用，或消费 RocketMQ 事件。三条被调链路的源头请看：
> - 统计图保存/查询 → fs-bi 发消息或 HTTP 调 warehouse（见《[全链路走读-fs-bi.md](../后端/全链路走读-fs-bi.md)》链路 3）
> - 统计图保存/变更 → crm-report 发 MQ（见《[全链路走读-fs-bi-crm-report.md](../后端/全链路走读-fs-bi-crm-report.md)》链路 6）
> - 报表保存/变更 → udf-report 发 MQ（见《[全链路走读-fs-bi-udf-report.md](../后端/全链路走读-fs-bi-udf-report.md)》链路 5/6）
> 两个关键 MQ Topic：`bi-warehouse-event`（视图变更，DWSViewChangeConsumer 消费）、`BI_WAREHOUSE_EVENT_TOPIC`（计算事件，DWSComputeConsumer 消费）。

---

## 链路速览表（先看这个：10 秒知道每个链路是干啥的）

| 链路 | 一句话说明（大白话） |
| --- | --- |
| 1 ODS 数据同步（自动） | 业务库数据一变 → 同步到 ClickHouse 明细表 → 发计算事件。整个数据仓库的源头 |
| 2 ODS 手动同步 | 运维手动补数据（按主键补几条 / 按租户整表同步） |
| 3 DWS 聚合计算核心 | 计算事件到达 → 找出受影响的统计图/报表 → 算聚合 → 写入 ClickHouse 聚合表 |
| 4 视图变更→建拓扑 | 用户保存报表/统计图 → 发 MQ → warehouse 预建 CH 聚合表（先建表，不填数） |
| 5 getLatestCalTime | 被 fs-bi 调：查「这个图的数据算到几点了」，前端用来提示更新时间 |
| 6 batchCompareViewField | 被 fs-bi 调：检查「报表字段配置 vs CH 表结构」是否一致，不一致就重建 |
| 7 dbChangeEvent 手动计算 | 消息丢了/算失败时，运维手动补触发一次聚合计算 |
| 8 Merge 任务 | ClickHouse 数据合并：把删除/更新真正落地、去重，每天定时跑 |
| 9 CH 表 DDL 与路由 | 建表、加路由、批量改表结构（DDL）等运维接口 |
| 10 聚合规则启停 | 停用/启用统计图或目标的聚合计算，并清理拓扑表 |

---

## 链路 1：ODS 数据同步（自动链路：上游数据变更 → ClickHouse → 发计算事件）

> **这条链路是干什么的（大白话）**：**场景**：业务系统（CRM/客户管理）的数据发生了变化——新增了一条客户、改了一个订单状态。**它做的事**：warehouse 消费上游的数据变更 MQ 事件 → 从业务库（PG）把变更数据读出来 → 通过 Biz2CHConsumer 增量写入 ClickHouse 明细表 → 同步完成后发「计算事件」给 DWS 层。**理解**：这是整个 BI 数据仓库的「源头」，用户看到的报表数据都从这里开始。


**入口**：RocketMQ 消费者（非 HTTP 接口）
**API 文件**：`ods/mq/TransferEventConsumer.java` → `consumeMessage()`（第 46 行）

```
RocketMQ：上游（PaaS/CRM 等）数据变更事件（ods_event_topics 配置的 topic）
  → TransferEventConsumer.consumeMessage()（ods/mq/TransferEventConsumer.java，第 46 行）
      ├─ 解析 TransferEvent{dbURL(PG连接), chDbURL(CH连接), schema}
      ├─ 灰度 topic 判断（use_gray_topic_ei / use_gray_topic_pgdb）
      └─ dbTransferService.doTransfer2CH(transferEvent)（失败重试 3 次）
          → DBTransferService.doTransfer2CH()（ods/service/DBTransferService.java，第 253 行）
              ├─ 1. 按 pgDB+schema 查同步配置：pgCommonDao.queryDBSyncInfo / 相关 DAO → PostgreSQL（db_sync_info 表）
              ├─ 2. 计算批次号 batchNum
              ├─ 3. 分页读 PG 增量数据（按修改时间/主键过滤）
              ├─ 4. 构造 Biz2CHConsumer：Biz2CHConsumer.getInstance(chClientService, clickhouseTable, ...)
              │     → ods/entity/Biz2CHConsumer.java
              │         ├─ add() 收集变更数据（BizLog）
              │         ├─ save() 批量写（第 175 行）：
              │         │     ├─ queryBeforeData() → chdbService.insertBeforeDataPlus()（第 134 行）反查 CH 历史数据
              │         │     └─ writer.batchWrite(bizLogCache) 批量写入 ClickHouse
              │         └─ → chdbService → ClickHouse（insert/update/delete 生效）
              └─ 5. 同步完成 → pgCommonDao.sendCalculateEvent(dbSyncInfo, ...)（ods/dao/PgCommonDao.java，第 246 行）
                    → 组装 DBUpdateMessage{id, pgDB, chDB, schema, batchNum}
                    → calculateEventProducer.sendMessage(BI_WAREHOUSE_EVENT_TOPIC, DWS_CALC_EVENT, ...)（ods/mq/CalculateEventProducer.java）
                        → RocketMQ 计算事件 → DWSComputeConsumer（见链路 3）
```

**底层落点**：PostgreSQL（同步配置/同步状态表）+ ClickHouse（ODS 层明细表）+ RocketMQ（计算事件）。

**新手要点**：这是整个 BI 数据仓库的「源头」：业务库（PG）数据一变化，就同步到 ClickHouse 明细表，然后通知 DWS 层去聚合。核心是 `Biz2CHConsumer` 这个「增量写入器」。

---

## 链路 2：ODS 手动同步（运维接口）

> **这条链路是干什么的（大白话）**：**场景**：运维发现某张 ClickHouse 表少了几条数据，或者要全量重导某个租户的数据。**它做的事**：调用 `/syncDataByTable`：带主键参数→按主键精确补那几条数据；不带主键→按租户整表同步。**对比链路 1**：链路 1 是业务数据变化自动触发，这条是人工补数。


**API 文件**：`ods/controller/OdsController.java`
**接口方法**：`POST /syncDataByTable` → `syncDataByTable()`（第 330 行）

```
OdsController.syncDataByTable()
  ├─ 参数：ids（db_sync_info 的 id 列表）、tableName、tenantId、primaryKey、partition
  ├─ 有 primaryKey → dbTransferService.syncDataByTenantIdPrimaryKey(ids, tableName, tenantId, pks, true, partitionValue)
  │     → DBTransferService.syncDataByTenantIdPrimaryKey()（ods/service/DBTransferService.java，第 1167 行）
  │         ├─ 查 DBSyncInfo（pgCommonDao.queryDBSyncInfoById）→ PostgreSQL
  │         ├─ resolveSourcePg() 解析源 PG 连接
  │         └─ 按主键查 PG 数据 → Biz2CHConsumer 写入 ClickHouse
  └─ 无 primaryKey → dbTransferService.syncDataByTenantId(idList, tableName, tenantIds, partitionValue)
        → DBTransferService.syncDataByTenantId()（第 1111 行）
            ├─ 查 DBSyncInfo（queryDBSyncInfoById）→ PostgreSQL
            └─ 逐表同步：查 PG 全量/增量数据 → Biz2CHConsumer.getInstance(...) → chdbService → ClickHouse
```

**底层落点**：PostgreSQL（读源数据）+ ClickHouse（写目标表）。

**新手要点**：链路 1 是「自动同步」，这条是「手动补数据」的运维接口。`syncDataByTenantIdPrimaryKey` 按主键精确补几条数据；`syncDataByTenantId` 按租户整表同步。

---

## 链路 3：DWS 聚合计算核心链路（RocketMQ 计算事件 → ClickHouse 聚合）★核心★

> **这条链路是干什么的（大白话）**：**场景**：链路 1 发来计算事件（业务数据已同步完）后，DWS 层开始聚合计算。**它做的事**：①加分布式锁防止重复算 ②找到受这次数据变化影响的统计图/报表（查拓扑表）③给每个视图生成聚合 SQL（全量或增量）④执行 SQL 把聚合结果写入 ClickHouse 的 agg 表 ⑤更新状态和日志；失败自动重试（最多 20 次）。**理解**：用户打开统计图看到的数据，就是这条链路算出来的。


**入口**：RocketMQ 消费者
**API 文件**：`dws/mq/consumer/DWSComputeConsumer.java` → `consumeMessage()`（第 55 行）

```
RocketMQ：BI_WAREHOUSE_EVENT_TOPIC / DWS_CALC_EVENT（链路 1 的 sendCalculateEvent 发的）
  → DWSComputeConsumer.consumeMessage()（dws/mq/consumer/DWSComputeConsumer.java，第 55 行）
      ├─ 解析 DBUpdateMessage{id, pgDB, chDB, schema, batchNum, aggSyncId, dsBatchNum}（warehouse-common/.../mq/message/DBUpdateMessage.java）
      ├─ 灰度 topic 判断（use_gray_topic_ei / use_gray_topic_pgdb）→ 转发灰 topic
      └─ dwsComputeService.dbDataUpdated(dbUpdateMessage)
          → DWSComputeService.dbDataUpdated()（dws/service/DWSComputeService.java，第 210 行）
              ├─ 1. 分布式锁：JedisLock(lockKey = dbSyncInfo.id, 20 分钟)
              ├─ 2. 查同步信息：dbUpdateEventDao.findSyncById(id) → PostgreSQL（db_sync_info）
              ├─ 3. createDbUpdateEventPlus() 构建 DBUpdatedEvent（含变更的 apiName 集合、PG/CH 连接信息）
              ├─ 4. 状态机分派：
              │     ├─ SYNC_ED → before()（第 861 行）：copyBefore / 更新状态为 AGG_ING → PostgreSQL
              │     ├─ COPY_BEFORE_ING → before() 处理增量前数据
              │     └─ ...
              ├─ 5. compute()（第 520 行）★聚合核心★
              │     ├─ selectChangeGoals()（第 885 行）：查出本批次受影响的目标规则（goal_value_obj）
              │     ├─ 遍历受影响的租户（tenantIdObjectDescribeApiNamesMap）
              │     │     └─ topologyTableService.findViewMonitorByTenantId()（dws/service/TopologyTableService.java，第 881 行）
              │     │           → 查受影响的统计图/报表拓扑表监控列表 → PostgreSQL（topology_table_monitor 等）
              │     ├─ 宽表计算：idWideTableService.toIDWideMonitor / executeBatchWideTableMonitor（慢指标宽表）
              │     ├─ 分片线程池：Lists.partition(statViewMonitorList, 每片 ceil(size/threadRate))
              │     │     └─ 每个 TopologyTableMonitor（一个视图的一个字段）：
              │     │           ├─ statRuleMonitor.computeSQL() 生成聚合 SQL
              │     │           ├─ processSameRuleSql / processFilterIDWideTableSql 归类 SQL
              │     │           └─ retryExecuteStatRule()（第 766 行）★执行聚合 SQL★
              │     │                 ├─ 按「全量计算（Prepared）」/「增量计算」拼 CH settings（join_algorithm、max_bytes...）
              │     │                 ├─ 循环重试执行：clickHouseService.executeSQL(tenantId, sql, timeout)
              │     │                 │     → ClickHouseService.executeSQL()（dws/service/ClickHouseService.java，第 117 行）
              │     │                 │         → JdbcConnection.executeUpdate(sql) → ClickHouse（写 agg 聚合表）
              │     │                 └─ 写状态/日志 → PostgreSQL（bi_agg_log 等）
              │     └─ 更新同步状态：dbUpdateEventDao.updateDBStatus(...) → PostgreSQL
              └─ 6. 失败重试：异常时 cal_retry_times +1，重发 MQ（延迟 10s），上限 20 次
```

**底层落点**：PostgreSQL（拓扑/状态/日志表）+ ClickHouse（agg 聚合表写入）+ Redis（分布式锁）。

**新手要点**：这条是用户点名要的「DWS 聚合计算链路」，按顺序读 5 个方法：`consumeMessage`（接消息）→ `dbDataUpdated`（锁+状态）→ `compute`（找受影响的视图）→ `findViewMonitorByTenantId`（查拓扑）→ `retryExecuteStatRule`（执行聚合 SQL 写 CH）。聚合结果就是 fs-bi 统计图查询（《[全链路走读-fs-bi.md](../后端/全链路走读-fs-bi.md)》链路 3/4）读的 ClickHouse 数据。

---

## 链路 4：视图/报表变更 → 创建拓扑表（被 fs-bi / crm-report / udf-report 调）★跨仓库★

> **这条链路是干什么的（大白话）**：**场景**：用户在 BI 门户保存/修改了一个统计图或报表（crm-report/udf-report/fs-bi 会发 MQ 过来）。**它做的事**：消费 `bi-warehouse-event` 消息 → 按 sourceType 分派（0=统计图、1/2=目标、3=报表）→ 根据配置在 ClickHouse 里预建聚合表（拓扑表）→ 状态标记为 Prepared（待计算）。**理解**：只「建表」不「填数」，数据要等链路 3 的下一次计算事件来填。


**入口**：RocketMQ 消费者（`bi-warehouse-event` / `dws_view_event`）
**API 文件**：`dws/mq/consumer/DWSViewChangeConsumer.java` → `consumeMessage()`（第 55 行）

```
上游发消息（三选一）：
  ├─ crm-report 统计图保存：WarehouseEventProducer（TOPIC bi-warehouse-event / TAG dws_view_event / sourceType=0）
  ├─ udf-report 报表保存/查询：WarehouseEventProducer（sourceType=3）
  └─ fs-bi 统计图/目标变更：CallWareHouseDws 或同类 Producer
  → RocketMQ bi-warehouse-event / dws_view_event
  → DWSViewChangeConsumer.consumeMessage()（dws/mq/consumer/DWSViewChangeConsumer.java，第 55 行）
      ├─ 解析 ViewChangeMessage{tenantId, sourceId, sourceType, lang}（warehouse-common/.../mq/message/ViewChangeMessage.java）
      ├─ 校验：userCenterService.isValidateStatus(tenantId) 租户状态
      ├─ 灰度：use_ch_agg / use_ch_agg_pgdb 判断是否允许 CH 聚合
      ├─ tag 判断：
      │     ├─ "dws_tenant_event" → statTopologyService.reCreateTopologyByEI(tenantId, null) 重建整个租户拓扑
      │     ├─ "dws_view_event" ★★
      │     │     ├─ clickHouseService.checkAndAddChRouter(tenantIds) 检查/添加 CH 路由
      │     │     ├─ 有 sourceId → statTopologyService.doCreateTopology(tenantId, sourceId, sourceType, Prepared, lang)
      │     │     │     → StatTopologyService.doCreateTopology()（dws/service/StatTopologyService.java，第 182 行）
      │     │     │         ├─ sourceType=0 → oldStatViewTopologyTransformer.doCreateViewTopology()   统计图拓扑
      │     │     │         ├─ sourceType=1/2 → newGoalTopologyTransformer.doCreateGoalTopology()    目标拓扑
      │     │     │         └─ sourceType=3 → newRptTopologyTransformer.doCreateRptTopology()        报表拓扑
      │     │     │             └─ 每个 Transformer：查报表/统计图的字段、筛选、关系配置（来自 fs-bi/crm-report 的 PG）
      │     │     │                 → 生成 ClickHouse 建表 SQL（CREATE TABLE ... agg_xxx）
      │     │     │                 → clickHouseService 执行建表 → ClickHouse
      │     │     │                 → 记录 topology 状态（Prepared 待计算）→ PostgreSQL（topology_table 等）
      │     │     └─ 无 sourceId → statTopologyService.batchCreateTopologyByEi(tenantId, sourceType, ...) 批量建
      │     └─ "dws_downstream_policy" → biDataSyncPolicyService.checkDataSyncPolicyViewStatus()
      └─ 建好的 Prepared 拓扑在下次计算事件（链路 3）到达时被真正计算填充数据
```

**底层落点**：RocketMQ（bi-warehouse-event）+ PostgreSQL（拓扑配置）+ ClickHouse（建表）。

**新手要点**：这是「上游保存报表/统计图 → warehouse 预建 CH 聚合表」的链路。注意 sourceType 的含义：0=统计图、1/2=目标、3=报表。建表只是「准备」，数据要等链路 3 的计算事件。

---

## 链路 5：被动接口 /getLatestCalTime（被 fs-bi 调用，查数据最近计算时间）★跨仓库★

> **这条链路是干什么的（大白话）**：**场景**：fs-bi 查统计图时，想告诉用户「这个图的数据更新到几点了」。**它做的事**：fs-bi 通过 HTTP 调这个接口（`/getLatestCalTime`），warehouse 查 PostgreSQL 里的聚合时间记录 + 受影响的同步表时间，返回最近计算时间。前端拿它显示「数据更新于 xx 时」。


**API 文件**：`dws/controller/DwsController.java`
**接口方法**：`POST /getLatestCalTime` → `getLastCalTime()`（第 424 行）

```
调用方：fs-bi
  → fs-bi CallWareHouseDws.queryDBLatestSyncTimeByEI()（fs-bi-stat/.../call/CallWareHouseDws.java）
      → HTTP POST {warehouseDwsUrl}/getLatestCalTime，body = StatViewPreArg{tenantId, sourceId, lang}
      → warehouse DwsController.getLastCalTime()（第 424 行）
          └─ statTopologyService.queryDBLatestSyncTimeByEI(statViewPreArg)
              → StatTopologyService.queryDBLatestSyncTimeByEI()（dws/service/StatTopologyService.java，第 472 行）
                  ├─ 1. topologyTableDao.findAggTimeAndEffectApiBySourceId(tenantId, sourceId, lang)
                  │     → PostgreSQL（topology_table 表：查该视图的 latest_agg_time + 影响的 apiNames）
                  ├─ 2. calLatestAggTimeByTables(tenantId, effectApi)
                  │     → findTableSyncInfoByEffectApi → PostgreSQL（db_table_sync_info 表）
                  │     → 反查受影响的同步表，取最近同步时间
                  ├─ 3. 取两者最大值返回
                  └─ 兜底：查不到 → 返回当前时间-15 分钟
          → 返回 Map<tenantId, latestCalTime>（JSON）
      → fs-bi 用这个时间判断「数据是否已经算好」，没算好就提示用户稍后刷新
```

**底层落点**：PostgreSQL（拓扑/同步信息表）。

**新手要点**：fs-bi 查统计图数据前先问 warehouse「这个图的数据算到几点几分了」，如果计算时间落后于期望，说明聚合还在跑。全链路：fs-bi Controller → CallWareHouseDws（HTTP）→ DwsController → StatTopologyService（PG）。

---

## 链路 6：被动接口 /batchCompareViewField（被 fs-bi 调用，比对视图字段变化）★跨仓库★

> **这条链路是干什么的（大白话）**：**场景**：用户改了报表字段后，fs-bi 要判断「ClickHouse 里老的表结构还对不对」。**它做的事**：fs-bi 通过 HTTP 调 `/batchCompareViewField`，warehouse 把「报表当前字段配置」和「CH 表实际结构」做对比（含 DESCRIBE 表），返回差异（新增/删除/类型变化）。fs-bi 据此决定要不要重建拓扑。


**API 文件**：`dws/controller/DwsController.java`
**接口方法**：`POST /batchCompareViewField` → `batchCompareViewField()`（第 431 行）

```
调用方：fs-bi
  → fs-bi CallWareHouseDws.batchCompareViewField()（fs-bi-stat/.../call/CallWareHouseDws.java）
      → HTTP POST {warehouseDwsUrl}/batchCompareViewField，body = StatViewBatchArg{tenantId, statViewArgList}
      → warehouse DwsController.batchCompareViewField()（第 431 行）
          └─ statTopologyService.batchCompareStatView(statViewBatchArg)
              → StatTopologyService.batchCompareStatView()
                  ├─ 逐个视图：对比「报表/统计图当前的字段配置」vs「CH 拓扑表已有的字段」
                  │     ├─ 查当前配置：从上游元数据/拓扑配置 → PostgreSQL
                  │     └─ 查 CH 表结构：clickHouseService / chMetadataService → ClickHouse（DESCRIBE）
                  ├─ 找出：新增字段、删除字段、类型变化
                  └─ 返回 List<Map<String,Object>>（每个视图的差异结果）
          → fs-bi 拿到差异后决定：需要重建拓扑 / 提示用户重新保存
```

**底层落点**：PostgreSQL（拓扑配置）+ ClickHouse（表结构比对）。

**新手要点**：用户改了报表字段后，fs-bi 用这个接口检查「CH 里的老表结构是否和新的配置一致」，不一致就触发重建。全链路：fs-bi Controller → CallWareHouseDws（HTTP）→ DwsController → StatTopologyService → CH。

---

## 链路 7：手动触发计算（dbChangeEvent 运维接口）

> **这条链路是干什么的（大白话）**：**场景**：运维发现某次聚合没算（消息丢了、算失败了、数据补了），手动触发一次。**它做的事**：调 `/dbChangeEvent?id=xx`，warehouse 查出该同步信息，组装成计算消息，直接调用链路 3 的 `dbDataUpdated` 走完整计算流程。**本质**：链路 3 的「手动版」。


**API 文件**：`dws/controller/DwsController.java`
**接口方法**：`POST /dbChangeEvent?id=xxx` → `dbChangeEvent()`（第 376 行）

```
DwsController.dbChangeEvent()
  ├─ dbUpdateEventDao.findSyncById(id) 查同步信息 → PostgreSQL（db_sync_info）
  ├─ 组装 DBUpdateMessage{id, chDB, batchNum, pgDB, schema}
  └─ dwsComputeService.dbDataUpdated(dbUpdateMessage)
      → 与链路 3 完全相同的计算流程（锁 → 状态机 → compute → CH 聚合）
```

**底层落点**：PostgreSQL + ClickHouse（同链路 3）。

**新手要点**：链路 3 是 MQ 自动触发；这条是「消息丢了/算失败了，手动补触发」的运维接口，直接调用同一个 `dbDataUpdated`。

---

## 链路 8：Merge 任务（ClickHouse 数据合并）

> **这条链路是干什么的（大白话）**：**场景**：ClickHouse 的更新/删除是「打标记」，不会立刻生效，需要定期合并（merge）才能让数据真正更新、去重、释放空间。**它做的事**：`/doMergeAgg` 手动触发某个 CH 库的合并；`/scheduleMergeByDb` 触发一轮定时合并任务。合并时按主键比对新旧数据，把删除/更新真正落地。


**API 文件**：`ods/controller/OdsController.java`
**接口方法**：`GET /doMergeAgg/{id}/{needSwitch}` → `doMergeAgg()`（第 141 行）；`POST /scheduleMergeByDb` → `scheduleMergeByDb()`（第 155 行）

```
【单库手动 merge】
OdsController.doMergeAgg()
  ├─ dbTransferService.createCHNodeInfo(id) 构建 CH 节点信息（查配置 → PostgreSQL）
  └─ mergeTaskService.merge(clickhouseNodeInfo, pageSize, chReadTimeOut, needSwitch, false)
      → MergeTaskService.merge()（ods/service/MergeTaskService.java）
          ├─ 分页读取 CH 旧数据 + 新写入数据（同主键比对）
          ├─ 按主键做合并（去重/覆盖/删除标记处理）
          └─ 写回 ClickHouse

【定时 merge】
OdsController.scheduleMergeByDb()
  ├─ CHContext.allowScheduleNewMerge(chURL) 开关校验
  └─ mergeTaskService.scheduleNewMergeByChUrl(chURL, maxLoop)（MergeTaskService.java，第 3320 行）
      → 对该 CH 库启动一轮定时 merge 任务（异步循环处理所有表）
```

**底层落点**：ClickHouse（数据合并写回）+ PostgreSQL（节点配置）。

**新手要点**：ClickHouse 的 update/delete 是「标记+异步合并」，merge 就是把标记真正落地、把重复数据合并掉。BI 场景每天定时 merge 保证查询快。

---

## 链路 9：CH 表 DDL 与路由管理（建表/路由/分区）

> **这条链路是干什么的（大白话）**：**场景**：大数据侧的表结构管理——新增同步表、给租户加 CH 路由、批量改表结构。**它做的事**：`/createChTableSQL` 根据 PG 表结构生成并执行 CH 建表 SQL；`/batchAddChRouter` 给一批租户/库加 ClickHouse 路由配置；`/batchDDLOnCh/{op}` 批量执行加列/改 TTL 等 DDL。**理解**：普通查询链路不会走到这，都是运维/初始化用。


**API 文件**：`ods/controller/OdsController.java`
**接口方法**：`POST /createChTableSQL`（第 367 行）；`POST /batchAddChRouter`（第 276 行）；`POST /batchDDLOnCh/{op}`（第 428 行）

```
【生成建表 SQL】
OdsController.createChTableSQL()
  └─ pgMetadataService.createCHInitSqL(chPublicCreatorArg, true, null)
      → 根据 PG 表结构（列、类型、索引）生成 ClickHouse 建表 SQL
      → 执行建表 → ClickHouse

【批量添加 CH 路由】
OdsController.batchAddChRouter()
  └─ 给一批租户/库添加 ClickHouse 路由配置（chRouter）
      → 路由表 → PostgreSQL / 配置中心
      → 后续查询按路由找到正确的 CH 库

【批量 DDL】
OdsController.batchDDLOnCh(op)（op = alter/add/drop 等）
  └─ 对指定 CH 表批量执行 DDL（加列、改 TTL、分区操作）
      → ClickHouse
```

**底层落点**：ClickHouse（DDL）+ PostgreSQL（路由/元数据）。

**新手要点**：大数据侧「表结构管理」都在这类运维接口：建表、加路由、批量 DDL。普通报表查询链路不会走到这里。

---

## 链路 10：聚合规则启停（统计图/目标规则开关）

> **这条链路是干什么的（大白话）**：**场景**：管理员在 BI 后台停用某个统计图或目标规则（fs-bi 的聚合规则启停接口转发过来）。**它做的事**：`/aggRule/enable` 或 `/goalRule/enable` 收到停用请求 → 更新规则状态（PG）→ 删除/清理对应的 ClickHouse 拓扑表 → 发消息通知相关计算停止。**理解**：停用 = 停止该统计图/目标的聚合计算，省计算资源。


**API 文件**：`dws/controller/DwsController.java`
**接口方法**：`POST /aggRule/enable` → `aggRuleEnable()`（第 87 行）；`POST /goalRule/enable` → `goalRuleEnable()`（第 113 行）

```
DwsController.aggRuleEnable()
  ├─ 参数：AggRuleBatchEnableArg{tenantId, ruleIds, enable}
  ├─ enable=false 时：aggRuleService.sendStopMessage(tenantId, ruleIds)
  │     → AggRuleService.sendStopMessage()（dws/service/AggRuleService.java，第 26 行）
  │         ├─ 更新规则状态（停用）→ PostgreSQL（agg_rule 规则表）
  │         ├─ 删除/停用对应的拓扑表 → ClickHouse + PostgreSQL
  │         └─ 发消息通知相关视图停止计算 → RocketMQ
  └─ 返回停用数量

DwsController.goalRuleEnable()
  └─ 目标规则启停（目标 = 员工业绩目标），逻辑同上，作用于 goal_rule
```

**底层落点**：PostgreSQL（规则表）+ ClickHouse（拓扑清理）+ RocketMQ（通知）。

**新手要点**：fs-bi 的「聚合规则启停」接口（《[全链路走读-fs-bi.md](../后端/全链路走读-fs-bi.md)》链路 6）最终是调到这里。停用 = 停止该统计图/目标的聚合计算并清理拓扑。

---

## 附录 A：被上游调用的接口速查表

| 上游调用方 | 调用方式 | warehouse 接收端 | 对应链路 |
| --- | --- | --- | --- |
| fs-bi（CallWareHouseDws） | HTTP POST | `DwsController /getLatestCalTime`（第 424 行） | 链路 5 |
| fs-bi（CallWareHouseDws） | HTTP POST | `DwsController /batchCompareViewField`（第 431 行） | 链路 6 |
| fs-bi / crm-report / udf-report | RocketMQ `bi-warehouse-event` / `dws_view_event` | `DWSViewChangeConsumer.consumeMessage`（第 55 行） | 链路 4 |
| fs-bi（aggRule/goalRule） | HTTP POST | `DwsController /aggRule/enable`、`/goalRule/enable` | 链路 10 |
| 上游数据平台 | RocketMQ ods 事件 | `TransferEventConsumer.consumeMessage`（第 46 行） | 链路 1 |
| 计算事件（内部） | RocketMQ `BI_WAREHOUSE_EVENT_TOPIC` / `DWS_CALC_EVENT` | `DWSComputeConsumer.consumeMessage`（第 55 行） | 链路 3 |

## 附录 B：其他重要运维接口（未展开）

- `DwsController /dbChangeEvent`（第 376 行）：手动触发聚合计算 → 链路 7
- `DwsController /createPreViewSQL`（第 393 行）、`/createBatchPreViewSQL`（第 407 行）、`/createDetailViewSQL`（第 418 行）：按统计图配置预生成查询 SQL 模板
- `DwsController /batchCreateAggTopology`（第 257 行）：批量创建/删除聚合拓扑
- `DwsController /refreshBillboard`（第 711 行）：刷新排行榜统计图（`billboardService.execBillBoard`，BillboardService 第 66 行）
- `DwsController /reclaimData`、`/reclaimAggData`（第 764/780 行）：回收明细/聚合数据
- `OdsController /batchUpdateSyncDbStatus`（第 169 行）、`/upsertDbSyncInfo`（第 210 行）：同步状态与配置管理
- `OdsController /repairPartition`、`/modifyChTableTTL`：分区修复与 TTL 管理
