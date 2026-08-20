# fs-bi-warehouse 代码走读详解（新手向 · 超详细版）

> 配套文档：《fs-bi-warehouse-架构分析.md》的「十、代码走读路线」。本文把两条最核心的链路逐行讲透：
> **A. ODS 同步**（PostgreSQL → ClickHouse）与 **B. DWS 聚合计算**（RocketMQ 事件 → ClickHouse 聚合）。
> 仓库根目录：`/Users/muqingji/code/Data/fs-bi-warehouse`；代码默认在 `warehouse-dws/src/main/java` 下。

---

## 0. 读代码前，先认识几个概念（新手速查）

| 概念 | 一句话解释 |
| --- | --- |
| ODS / DWD / DWS | 数仓分层：ODS=原始数据层（同步来的原样数据）、DWD=明细层、DWS=汇总层（算好的聚合结果） |
| 数仓同步 | 把业务库（PostgreSQL）的数据搬到分析库（ClickHouse），BI 报表才查得到 |
| RocketMQ | 消息队列：A 系统发一条消息，B 系统异步收到并处理（解耦、削峰） |
| 消息消费者 | 一直监听队列的程序，收到消息就执行回调方法 |
| 聚合（Aggregation） | 按维度分组求和/计数，如「按月份按部门统计销售额」 |
| 拓扑（Topology） | 表与表之间的「谁依赖谁」关系；源表变了，下游聚合表要跟着重算 |
| 分区（Partition） | ClickHouse 把表按时间/批次分成很多小块，查哪块读哪块，快而且能单独删 |
| 灰度开关 | 按企业/库名放量，新功能先小范围生效 |
| 分布式锁（JedisLock） | 用 Redis 保证「同一任务同时只有一个实例在跑」，防止重复计算 |

**这个仓库的特点**：它是**数据搬运工 + 计算器**，没有「用户点一下查一下」的交互，全是**后台任务 + 事件驱动**：同步完 → 发消息 → 消费者收到 → 算聚合 → 再发消息 → 刷新下游。

---

# 链路 A：ODS 同步（PostgreSQL → ClickHouse）

## A-1. 主链路总览

```
运维/调度触发
   │ ① POST /ods/syncDataByTable（告诉它：同步哪些配置、哪张表）
   ▼
OdsController.syncDataByTable()              ← 控制器：解析参数
   ▼
DBTransferService.syncDataByTenantId()       ← 服务：读同步配置
   ├─ 读 db_sync_info（PG）：这个企业、这张表怎么同步
   ├─ 拿 PG 连接、加载 PG 表结构
   ├─ 校验 ClickHouse 目标表是否存在
   ▼
syncByTenantIdOffline() → transfer2CHByTenantId()
   ├─ 分页读 PostgreSQL 数据
   ▼
Biz2CHConsumer（批量消费者）
   ├─ add()：攒一批
   ├─ batchWrite()：批量写 ClickHouse
   ▼
biz2CHConsumer.save()                         ← 保存点/落库
   ▼
CalculateEventProducer 发「计算事件」→ 进入链路 B
```

## A-2. 控制器：OdsController

文件：`com/fxiaoke/bi/warehouse/ods/controller/OdsController.java`（第 328 行）

```java
@PostMapping("/syncDataByTable")
public String syncDataByTable(@RequestBody Map<String, String> params) {
  String ids = params.get("ids");              // db_sync_info 的 id 列表（同步配置）
  String tableName = params.get("tableName");  // 要同步哪张表
  String tenantId = params.getOrDefault("tenantId", "-1");
  String primaryKey = params.get("primaryKey");
  String partitionValue = params.getOrDefault("partition", "");

  if (StringUtils.isNotBlank(primaryKey)) {
    // 按主键同步（只同步指定记录）
    dbTransferService.syncDataByTenantIdPrimaryKey(ids, tableName, tenantId, pks, true, partitionValue);
  } else {
    // 全表/增量同步
    dbTransferService.syncDataByTenantId(idList, tableName, [tenantId], partitionValue);
  }
  return "send ok";
}
```

**新手解读**：
- `db_sync_info` 是「同步配置表」（存在 PG），一条记录 = 一个「企业 + 数据库 + 表」的同步任务。`ids` 就是这些记录的 id。
- 传了 `primaryKey` 就只同步这几条记录（修数据用）；不传就按配置同步。

## A-3. 服务：DBTransferService

文件：`com/fxiaoke/bi/warehouse/ods/service/DBTransferService.java`（第 1111 行）

```java
public void syncDataByTenantId(String pgDBUrl, String pgSchemaName, String chSchemaName,
                               String chProxyUrl, String tableName, List<String> tenantIds,
                               long batchNum, String partitionValue) {
  // 1) 根据表名判断业务类型（BI 还是 CRM），CRM 特殊表名要映射（mt_data → object_data）
  BizEnum bizEnum = ...;

  // 2) 打开 PG 连接（源）
  try (JdbcConnection jdbcConnection = biPgDataSource.getConnectionByJdbcURL(pgDBUrl, pgSchemaName)) {
    // 3) 加载 PG 表结构（列、类型、主键）——有缓存
    PGSchema pgSchema = pgMetadataService.loadSchemaIfInCache(pgDBUrl, pgSchemaName, tableName);

    // 4) 加载 ClickHouse 目标表结构（不存在就报错返回）
    Optional<ClickhouseTable> clickhouseTableOP = chMetadataService.loadTable(chSchemaName, chProxyUrl, chTableName);

    // 5) 创建"批量写入消费者"（攒一批写一次，不是一条一条写）
    Biz2CHConsumer biz2CHConsumer = Biz2CHConsumer.getInstance(chClientService, clickhouseTable,
        savePointSize, batchNum, chNodeService, chdbService, orderByColumns, batchQueryBeforeSize);

    // 6) 开始搬运：按租户逐批读 PG → 交给 consumer
    this.syncByTenantIdOffline(tenantIds, jdbcConnection, pgSchema, biz2CHConsumer, ...);

    // 7) 保存点落库
    biz2CHConsumer.save();
  }
}
```

**新手解读**：
- 第 3、4 步都在读「表结构」：PG 端要知道源表有哪些列，CH 端要知道目标表长什么样，两边字段要对应。
- `Biz2CHConsumer` 是「攒批」的关键：数据一行行来，攒够一批再一次性写 CH（性能好很多）。
- `try (JdbcConnection ...)` 是 Java 的 try-with-resources：用完自动关闭连接。

## A-4. 批量写入：Biz2CHConsumer

文件：`com/fxiaoke/bi/warehouse/ods/entity/Biz2CHConsumer.java`

```java
// 核心行为（简化）：
public void add(...) {
  this.bizLogCache.add(doc);                    // 先攒到内存
  if (cacheSize >= this.batchQueryBeforeSize) { // 攒够了
    this.writer.batchWrite(this.bizLogCache);   // 批量写 CH
  }
}
// 分区预写
public void insertBeforeDataPlus(clickhouseTable, batchNum, orderByFields, ...) {
  this.chdbService.insertBeforeDataPlus(...);   // 写入分区占位
}
```

**新手解读**：
- `batchQueryBeforeSize` 是「攒多少条写一次」的阈值，类似水桶接满再倒。
- 写入 ClickHouse 底层走 `chdbService`（`core/chdb` 包），它封装了 CH 客户端和分区逻辑。

## A-5. 同步完成 → 发计算事件

同步完成后，`PgCommonDao` 里会发 MQ 事件（`CHContext.DWS_CALC_EVENT` 等），由 `CalculateEventProducer`（`ods/mq/CalculateEventProducer.java`）发送：

```java
producer = new AutoConfMQProducer("fs-bi-warehouse", "OBSConsumer");   // 生产者初始化

public void sendMessage(String topic, String tag, String keys, String body, int hash, long delayMs) {
  Message syncEventMsg = new Message(topic, tag, keys, body.getBytes(StandardCharsets.UTF_8));
  this.producer.send(syncEventMsg, (mqs, msg1, arg) -> {   // 按 hash 选队列（保证同企业消息有序）
    int index = id % mqs.size();
    return mqs.get(index);
  }, hash);
}
```

**新手解读**：
- 消息体是 JSON（`DBUpdateMessage`：id、pgDB、chDB、batchNum、schema、aggSyncId、dsBatchNum）。
- `hash` 选队列的技巧：同一个企业/同一张表的消息永远进同一个队列，消费端就能按顺序处理，避免并发算重。

---

# 链路 B：DWS 聚合计算（RocketMQ 事件 → ClickHouse 聚合）

## B-0. 这一节要解决的问题

数据库同步完成只是「数据到了 ODS」，但 BI 报表要的是**算好的聚合**（比如每个销售每月的业绩）。链路 B 就是：
1. 收到「某某表同步完成」的消息；
2. 找出所有**依赖这张表**的统计视图（拓扑）；
3. 对每个视图按规则生成聚合 SQL；
4. 在 ClickHouse 里执行这些 SQL（`INSERT INTO agg_data SELECT ... GROUP BY ...`）；
5. 通知下游刷新。

## B-1. 消费者：DWSComputeConsumer

文件：`com/fxiaoke/bi/warehouse/dws/mq/consumer/DWSComputeConsumer.java`（第 55 行）

```java
@PostConstruct
public void init() {
  // 创建消费者：组名 fs-bi-warehouse，消费者名 DWSConsumer，回调 this
  consumer = new AutoConfMQPushConsumer("fs-bi-warehouse", "DWSConsumer", this);
}

@Override
public ConsumeConcurrentlyStatus consumeMessage(List<MessageExt> list, ConsumeConcurrentlyContext ctx) {
  list.forEach(msg -> {
    // 1) 解析消息：JSON → DBUpdateMessage 对象
    DBUpdateMessage dbUpdateMessage = DBUpdateMessage.parseFromMsg(msg);

    // 2) 灰度分流：命中灰度的企业/库，转投到灰度 topic
    if (灰度命中) { msg.setTopic(CHContext.BI_WAREHOUSE_EVENT_TOPIC_GRAY);
                   calculateEventProducer.sendMessage(msg, msg.getQueueId()); return; }

    try {
      // 3) ★核心：交给 DWSComputeService 计算
      dwsComputeService.dbDataUpdated(dbUpdateMessage);
    } catch (Exception e) {
      // 4) 失败重试：消息里记 cal_retry_times，最多 20 次；超过就丢弃并报错
      int retryTimes = ...; if (retryTimesInt >= 20) { log.error(...); return; }
      msg.putUserProperty("cal_retry_times", String.valueOf(++retryTimesInt));
      calculateEventProducer.sendMessage(msg, msg.getQueueId(), 10000L);  // 延迟 10s 重投
    }
  });
  return ConsumeConcurrentlyStatus.CONSUME_SUCCESS;
}
```

**新手解读**：
- `AutoConfMQPushConsumer`：公司封装的 RocketMQ 消费者，配置自动从配置中心拉，启动后一直监听队列。
- **重试机制**是消息消费的标准姿势：失败 → 记录重试次数 → 延迟重新投递；次数超限才放弃（防止一条坏消息永远重试）。
- 消息里存的 `batchNum`（批次号）非常重要：聚合时按批次算，同一批数据算完结果也带批次号，方便对账和重算。

## B-2. 计算服务入口：dbDataUpdated

文件：`com/fxiaoke/bi/warehouse/dws/service/DWSComputeService.java`（第 210 行）

```java
public void dbDataUpdated(DBUpdateMessage dbUpdateMessage) {
  // 1) 分布式锁：同一 dbSyncId 只允许一个实例计算（防止重复）
  String lockKey = dbUpdateMessage.getId();
  try (JedisLock jedisLock = new JedisLock(jedisCmd, lockKey, 1000 * 60 * 20)) {
    if (!jedisLock.tryLock()) return;

    // 2) 查同步配置（PG）：这个同步任务是否存在、是否被删除
    DBSyncInfoDO dbSyncInfoDO = dbUpdateEventDao.findSyncById(dbUpdateMessage.getId());
    if (dbSyncInfoDO == null || dbSyncInfoDO.getIsDeleted() == 1) return;

    // 3) 组装"数据库更新事件"DBUpdatedEvent（含批号、分区、变更对象清单）
    DBUpdatedEvent dbUpdateEvent =
        dbUpdateEventDao.createDbUpdateEventPlus(dbSyncInfoDO, dbUpdateMessage.getBatchNum(), ...);
    if (dbUpdateEvent == null) return;

    // 4) 根据当前同步状态机分派（SYNC_ED / COPY_BEFORE_ING / ...）
    SyncStatusEnum syncStatusEnum = SyncStatusEnum.createFromStatus(dbUpdateEvent.getStatus());
    switch (syncStatusEnum) {
      case SYNC_ED -> {
        // 同步完成：先做"计算前准备"（before），再做计算
        if (!this.before(dbUpdateEvent, stopWatch)) {
          QiXinNotifyService.sendTextMessage(...);   // 失败企信报警
          return;
        }
        calculatePgDB.add(dbUpdateMessage.getId());
      }
      case COPY_BEFORE_ING -> { ... }
      ...
    }
    // 5) ★计算入口（内部按企业循环，见 B-3）
    computeData(dbUpdateEvent, stopWatch);
  }
}
```

**新手解读**：
- **分布式锁**：系统可能部署了多个实例，如果没有锁，同一条消息会被多个实例同时处理，聚合就会算两遍。`JedisLock` 用 Redis 实现「谁拿到锁谁干活」。
- **状态机**：同步任务有状态（同步中、计算中、拷贝中……），事件处理要根据状态决定先干什么。`before()` 里可能要做「拷贝上一批数据」等准备动作。

## B-3. 主计算：compute

文件：`com/fxiaoke/bi/warehouse/dws/service/DWSComputeService.java`（第 520 行）

```java
public void compute(DBUpdatedEvent event, StopWatch stopWatch) {
  // 1) 找出本次变更影响了哪些"目标规则"（目标值相关）
  Map<String, Set<String>> changeGoalMap = selectChangeGoals(event);

  // 2) 按企业（tenantId）逐个处理
  event.getTenantIdObjectDescribeApiNamesMap().forEach((tenantId, changedApiNames) -> {
    // 灰度检查：这个企业/库开了"聚合计算"吗？没开直接跳过
    if (!GrayManager.isAllowByRule("use_ch_agg_pgdb", pgDBName) && ...) return;
    // 路由检查：PG 库路由是否有效
    if (!pgMetadataService.checkPgRouter(...)) { QiXinNotifyService.alarmV2(...); return; }

    // 3) ★查拓扑：哪些统计视图依赖了本次变更的对象？（这一步决定"要算什么"）
    List<TopologyTableMonitor> statViewMonitorList =
        topologyTableService.findViewMonitorByTenantId(tenantId, changedApiNames, batchNum, ...);
    if (statViewMonitorList.isEmpty()) { log.info("nothing to calculate"); return; }

    // 4) 宽表计算（部分指标先算增量宽表，再基于宽表聚合）
    Map<String, WideMergedRule> fieldIdToWideRuleMap =
        this.executeBatchWideTableMonitor(tenantId, ea, batchNum, wideTableMonitorList, ...);

    // 5) 并行计算所有统计视图：按线程数分片，每片一个线程
    List<List<TopologyTableMonitor>> monitPartitions = Lists.partition(statViewMonitorList, 分片大小);
    try (ExecutorService executor = Executors.newFixedThreadPool(monitPartitions.size())) {
      CompletableFuture.allOf(monitPartitions.stream().map(part -> CompletableFuture.runAsync(() -> {
        part.forEach(statViewMonitor -> {
          // 5.1) 每个视图有多个聚合规则（指标），逐个算
          for (TopologyTableAggRuleMonitor statRuleMonitor : statViewMonitor.getStatRuleMonitorList()) {
            // 5.2) 生成该指标的聚合 SQL（computeSQL）
            List<String> sqlList = statRuleMonitor.computeSQL(batchNum);
            // 5.3) 增量场景：相同指标已算过 → 直接拷贝 agg_data，不重复算（processSameRuleSql）
            // 5.4) 增量宽表优化（processFilterIDWideTableSql）
            // 5.5) ★执行 SQL（带重试），见 B-4
            this.retryExecuteStatRule(tenantId, statViewMonitor, ..., sqlList, fixRetryTimes, statRuleMonitor, event);
          }
        });
      })).toArray(CompletableFuture[]::new)).join();
    }
  });
}
```

**新手解读**：
- **拓扑（Topology）是这个系统的灵魂**：`topology_table` 记录「哪些统计视图依赖哪些对象表」。数据变更后，靠它反查「谁要重算」，避免全量重算。
- `TopologyTableMonitor` = 一个待计算的统计视图（含它的目标聚合表 topologyTable）；`TopologyTableAggRuleMonitor` = 视图里的一个聚合指标规则。
- `statRuleMonitor.computeSQL(batchNum)`：**根据规则生成聚合 SQL**，典型长这样：
  `INSERT INTO agg_data (view_id, field_id, batch_num, ...) SELECT dims, SUM(value) FROM ods_table WHERE bi_sys_batch_id = N GROUP BY dims`
- `processSameRuleSql` 是优化：同一个批次里，两个视图用相同维度算同一个指标，第二个直接 `INSERT ... SELECT ... FROM agg_data` 拷贝结果，不重跑。
- 全程用 `CompletableFuture` 并行计算多个视图，注释里能看到线程名 `ch-cal-{tenantId}-{hash}`。

## B-4. 执行聚合 SQL：retryExecuteStatRule → ClickHouseService

文件：`com/fxiaoke/bi/warehouse/dws/service/DWSComputeService.java`（第 766 行）

```java
private void retryExecuteStatRule(..., List<String> sqlList, int retryTimes, TopologyTableAggRuleMonitor statRuleMonitor, DBUpdatedEvent event) {
  // 1) 按"全量/增量"组装 ClickHouse 查询参数（内存、join 算法、外部排序阈值…）
  String settings = Constants.JOIN_USE_NULLS_1_CACHE_1;
  if (全量计算) { settings += ", join_algorithm='grace_hash' ..."; }  // 防内存打爆
  else          { settings += ", max_bytes_before_external_group_by=..."; }

  // 2) 带重试地执行：失败按 10s~25s 退避重试
  for (int rt = 0; rt < retryTimes; rt++) {
    try {
      // 目标类指标走列表执行；宽表指标走单条；其他走单条 + settings
      if (是目标值指标) { sqlList.forEach(sql -> clickHouseService.executeSQL(tenantId, sql + settings, readTimeOut)); }
      else { clickHouseService.executeSQL(tenantId, sqlList.get(0) + settings, readTimeOut); }
      break;   // 成功就跳出
    } catch (Exception e) {
      if (rt < retryTimes - 1) { log.warn("begin to retry ..."); sleep(退避); }
      else { throw new RetryException(e); }
    }
  }
}
```

文件：`com/fxiaoke/bi/warehouse/dws/service/ClickHouseService.java`（第 117 行）

```java
public void executeSQL(String tenantId, String sql, int readTimeOut) {
  // 按企业路由到对应的 ClickHouse 实例，执行 SQL
  ... chdbService / 数据源执行 ...
}
```

**新手解读**：
- ClickHouse 聚合是大查询，容易吃内存，所以 `settings` 里塞了一堆优化参数（`join_algorithm`、`max_bytes_before_external_group_by`、`max_insert_threads`……），全是灰度控制。
- 执行的就是「INSERT … SELECT … GROUP BY」这类 SQL——**算完直接写进聚合表**（如 `agg_data`）。
- `readTimeOut` 是查询超时，防止大 SQL 卡死连接。

## B-5. 计算完成 → 通知下游刷新

计算完成后会发送「统计视图变更」事件，由 `StatViewEventProducer`（`dws/mq/producer/StatViewEventProducer.java`）发送：

```java
producer = new AutoConfMQProducer("fs-bi-warehouse", "DWSStatConsumer");
```

下游消费者如 `DWSViewChangeConsumer`（`dws/mq/consumer/DWSViewChangeConsumer.java`）：
```java
consumer = new AutoConfMQPushConsumer("fs-bi-warehouse", "DWSViewConsumer", this);
// 收到"视图变更"消息 → statTopologyService 刷新统计视图 → 上层 BI 报表可见新数据
```

**新手解读**：链路到此闭环：**同步 → 计算 → 视图刷新 → 报表可查**。每一步都通过 MQ 解耦，任何一步失败都有重试/报警兜底。

---

## 9. 整条链路串起来（最终版）

```
业务库 PostgreSQL 数据变化
  → ODS 同步任务（OdsController → DBTransferService → Biz2CHConsumer → ClickHouse ODS 层）
  → CalculateEventProducer 发消息
  → DWSComputeConsumer 收到消息（重试上限 20 次）
  → DWSComputeService.dbDataUpdated（分布式锁 + 状态机）
  → compute（按企业：查拓扑 → 生成聚合 SQL → 并行执行）
  → retryExecuteStatRule → ClickHouseService.executeSQL → ClickHouse 聚合表（agg_data 等）
  → StatViewEventProducer 发视图变更消息
  → DWSViewChangeConsumer → StatTopologyService 刷新统计视图
  → fs-bi / crm-report 报表查询返回新数据
```

---

## 10. 怎么验证我读懂了（实践建议）

1. **看消息流转**：日志里搜 `cal consumer bornHost`（消费日志）、`dbDataUpdated start`（计算入口日志）、`cal begin`（开始算某个视图）。
2. **看聚合 SQL**：在 `retryExecuteStatRule` 的 `clickHouseService.executeSQL` 打断点，查看生成的 `INSERT ... SELECT ... GROUP BY` SQL。
3. **查 ClickHouse**：执行完去 CH 里查 `agg_data`，看 `batch_num`、`view_id`、`field_id` 对应的新数据。
4. **验证重试**：手动把一条消息的 `cal_retry_times` 改小，看它如何被重新投递。
5. **断点跟读**：`DWSComputeConsumer.consumeMessage` → `DWSComputeService.dbDataUpdated` → `compute` → `retryExecuteStatRule`，一路 Step Into。

---

## 11. 新手 FAQ

| 问题 | 回答 |
| --- | --- |
| 为什么不用同步请求而是用 MQ？ | 数仓计算很重，用 MQ 异步 + 削峰，同步完就返回，计算排队慢慢做，失败还能重试 |
| batchNum（批次号）有什么用？ | 每次同步/计算都有批次号，聚合结果也带批次号：可以重算、对账、按批次回滚 |
| 拓扑是什么，为什么重要？ | 记录「统计视图依赖哪些表」。数据变了只重算受影响的下游，而不是全部重算 |
| 聚合 SQL 长什么样？ | 大致是 `INSERT INTO agg_data SELECT 维度, SUM(指标) FROM ods 表 WHERE 批次=... GROUP BY 维度` |
| 分布式锁会不会影响性能？ | 会有一点，但防止重复计算的收益远大于锁开销；锁超时 20 分钟，卡死会自动释放 |
| 灰度开关怎么控？ | `GrayManager.isAllowByRule("use_ch_agg", tenantId)`：按企业/库名单控制是否走新计算逻辑 |
