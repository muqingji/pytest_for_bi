# fs-bi 全链路走读手册（10 条主链路）

> 用法：每一条链路都从「API 接口文件 → 方法 → 服务 → 数据层/RPC」完整串联。你只需要按顺序打开文件、找到方法，一行行看。
> 仓库根：`/Users/muqingji/code/serve/fs-bi`；行号为当前代码实际行号，找不到就按类名/方法名搜索。
> 标注「跨服务」的地方，请继续跳到对应仓库的文档（crm-report / udf-report / dev-platform / warehouse）走完整条链路。

---

## 链路速览表（先看这个：10 秒知道每个链路是干啥的）

| 链路 | 一句话说明（大白话） |
| --- | --- |
| 1 报表数据查询 | 打开一张「分组报表」点查询，把表格数据查出来返回前端（最核心入口） |
| 2 报表查询 Kryo 版 | 和链路 1 查一样的数据，但用二进制压缩返回，数据量大/内部接口用 |
| 3 统计图 chart/query | 打开一张统计图（柱状图/折线图），一次性返回配置+筛选+数据，还带缓存 |
| 4 统计图 data/query | 只查统计图的数据（不含配置），被 crm-report 等下游转发调用 |
| 5 排行榜查询 | 查「销售额 Top10」这类按指标排序的排行数据 |
| 6 聚合规则启停 | 停用/启用某统计图的计算规则，并通知 warehouse 停止/恢复底层计算 |
| 7 目标规则查询 | 查企业给员工定的业绩目标配置（目标值/考核维度） |
| 8 指标生命周期启停 | 启用/停用某个 BI 指标（AI 指标治理），如把「客单价」下线 |
| 9 订阅定时触发 | 定时任务把报表数据查好，通过邮件/企信推给订阅人 |
| 10 SQL 引擎接口 | 对外提供「帮别人执行 SQL」的服务，连 PG 查询并返回数据集 |
| 11 元数据服务 | 提供「对象/字段/关系」字典，报表设计器列字段就靠它 |

---

## 链路 1：报表数据查询（核心链路）

> **这条链路是干什么的（大白话）**：**场景**：用户在 PC/移动端 BI 门户打开一张「分组报表」（比如《本月销售报表》），点查询按钮，前端就会调这个接口。**它做的事**：把用户选的筛选条件、分页、显示模式打包成查询参数，走 easy-stat 框架的 8 个阶段（校验→补参数→建模型→选策略→生成 SQL→执行→转结果），最终从 ClickHouse 把表格数据查出来。**输入**：报表 id + 筛选条件 + 页码；**输出**：列头 + 行数据（QueryReportResult）。


**API 文件**：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/RptQueryController.java`
**接口方法**：`POST /rpt/data/query` → `RptQueryController.queryReportData()`（第 37 行）

```
RptQueryController.queryReportData()                    ← Controller：接参、异常兜底、finally 清 ThreadLocal
  → QueryReportService.queryReportData()                ← Service：装上下文（第 74 行）
      ├─ RequestContextManagerBase.getContext() 写入 ei/userId/from/...
      ├─ WholeContext.fromOutsideForm(tenantId, userId, arg)  打包查询上下文
      └─ rootFlowInterface.goForward(wholeContext, CutRuleNameEnum.STAT_QUERY)
          → RootFlowInterfaceImpl.goForward()（application/interfaces/impl，第 26 行）
          → RootFlowServiceImpl.goForward()（application/service/impl，第 58 行）
              ├─ 阶段1 BaseCheckFlow（基础校验）
              ├─ 阶段2 CompletionParamFlow（参数补全）
              ├─ 阶段3 BuildModelFlow（构建模型）
              ├─ 阶段4 HitStrategyFlow（命中策略）
              ├─ 阶段5 PreGenerateDataQuerySqlFlow（with-as 前置，pregeneratedataquerysql/flow/impl/withas/*）
              ├─ 阶段6 GenerateDataQuerySqlFlow（生成查询 SQL）
              ├─ 阶段7 DataQueryFlow（执行查询）
              └─ 阶段8 GenerateResultFlow / HandleResultFlow（构建+转换结果）
  → 结果转换：JarQueryChartDataResultMapper → StatResult2RptResult.doConvert()
  → 返回 QueryReportResult
```

**底层落点**：
- ClickHouse：`easy/stat/clickhouse/executor/ClickHouseSQLExecutor.queryDirect()`（第 94 行）→ `jdbcConnection.query(sql)` → ClickHouse 统计库
- 元数据/筛选配置：PostgreSQL（经 `fs-bi-metadata` 的 Dubbo/JAX-RS 服务）

**新手要点**：这条链路是 fs-bi 的「心脏」，看懂它 = 看懂 easy-stat 框架。在 `RootFlowServiceImpl.goForward` 打断点，看 8 个阶段依次执行。

---

## 链路 2：报表数据查询（Kryo 二进制版）

> **这条链路是干什么的（大白话）**：**场景**：数据量特别大的报表（比如几万行），或者内部系统之间传数据。**它做的事**：和链路 1 查的东西一模一样，唯一区别是返回前用 Kryo 把结果压成二进制字节流，省流量、省 JSON 序列化时间。前端/调用方收到字节后再解压。**怎么区分**：链路 1 接口是 `/rpt/data/query`，这条是 `/rpt/data/queryWithKryo`。


**API 文件**：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/RptQueryController.java`
**接口方法**：`POST /rpt/data/queryWithKryo` → `queryReportDataByteArray()`（第 58 行）

```
RptQueryController.queryReportDataByteArray()
  → QueryReportService.queryReportData()（同链路 1）
  → KryoResult 包装：BytesUtils.writeCompressObjectWithKryo(result)   ← Kryo 二进制序列化（省流量）
  → 返回 KryoResult（字节数组）
```

**底层落点**：同链路 1（ClickHouse）。

**新手要点**：和链路 1 的唯一区别在「返回格式」——大结果集用 Kryo 压缩成字节返回，前端再反序列化。业务链路完全一样。

---

## 链路 3：统计图查询（chart/query，含缓存与 warehouse 调用）

> **这条链路是干什么的（大白话）**：**场景**：用户在 BI 门户打开一张统计图（柱状图、折线图、饼图等）。**它做的事**：一个接口把三样东西一次返回：①图表配置（X 轴/Y 轴/指标）②筛选器（可选的筛选条件）③图表数据。查完会把结果按 reqId 缓存到 Redis，下次同样参数直接命中。**特别之处**：它还会反向调 warehouse（HTTP）问「这个图的数据算到几点了」，前端用它显示「数据更新于 xx 点」。


**API 文件**：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/ViewDataQueryApiController.java`
**接口方法**：`POST /api/v1/stat/chart/query` → `syncChartQuery()`（第 86 行）

```
ViewDataQueryApiController.syncChartQuery()             ← Controller
  ├─ statBaseController.generateSyncChartQueryReqId()   生成 reqId
  ├─ statCacheService.cacheAsyncReqIfAbsent(reqId, 0)   缓存状态登记
  ├─ statEditController.getFiltersResult()              ① 筛选器查询（StatEditController 第 191 行）
  ├─ statEditController.getChartConfigNoCache()         ② 图表配置查询（StatEditController 第 597 行）
  ├─ statBaseController.preFillQueryDataArg()           ③ 填充查询参数
  ├─ statBaseController.originDataQueryNoCache()        ④ 数据查询（StatBaseController 第 357 行）
  │    → statMergeViewService.uniteDataQuery()          合并查询（多视图）
  │        → 内部复用 easy-stat 工作流（RootFlowInterface，同链路 1 阶段 3~8）
  │        → ClickHouseSQLExecutor.queryDirect() → ClickHouse
  ├─ asyncStatQueryCache.cacheAsyncReqResultWithBinary() ⑤ 结果按 reqId 缓存（Kryo 二进制）
  └─ 返回 ApiResult<QueryChartResult>
```

**调用 warehouse（跨服务）**：查询结果处理阶段，`HandleResultDataChGoalAggLatestTimeFlowNode`（`easy/stat/domain/handleresult/flow/impl/`）会调 `CallWareHouseDws.queryDBLatestSyncTimeByEI()` 拿「数据最近计算时间」；`AbstractStatSqlQueryService`（`service/base/`，第 688 行）会调 `callWareHouseDws.getViewUpdateTime()` 设置 `statUpdateTime`。

```
fs-bi-stat CallWareHouseDws（stat/call/CallWareHouseDws.java）
  ├─ getViewUpdateTime() / queryDBLatestSyncTimeByEI()
  │    └─ HTTP POST warehouseDwsUrl + /getLatestCalTime        ← 调 warehouse！
  └─ batchCompareViewField()
       └─ HTTP POST warehouseDwsUrl + /batchCompareViewField   ← 调 warehouse！
→ 对应 warehouse 侧链路见《[全链路走读-fs-bi-warehouse.md](../大数据/全链路走读-fs-bi-warehouse.md)》链路 9/10
```

**底层落点**：ClickHouse（数据）+ Redis（reqId 缓存）+ warehouse HTTP（更新时间）。

**新手要点**：这是「先查缓存状态 → 未完成则现查 → 完成后写缓存」的典型异步缓存模式；注意它还会反向调 warehouse 拿数据更新时间。

---

## 链路 4：统计图数据查询（data/query）

> **这条链路是干什么的（大白话）**：**场景**：crm-report 门户转发统计图查询、或其他服务只要「纯数据」时。**它做的事**：和链路 3 共用查询内核，但只查数据，不返回配置和筛选器，接口更轻。**对比**：链路 3 = 配置+筛选+数据+缓存（给前端页面用）；链路 4 = 只要数据（给后端服务转发用）。


**API 文件**：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/ViewDataQueryApiController.java`
**接口方法**：`POST /api/v1/stat/data/query` → `query()`（第 165 行）

```
ViewDataQueryApiController.query()
  → statBaseController（复用链路 3 的 ①②③④）
  → statMergeViewService.uniteDataQuery()
  → easy-stat 工作流 → ClickHouseSQLExecutor → ClickHouse
  → 返回 ApiResult<QueryChartDataResult>
```

**底层落点**：ClickHouse 统计库。

**新手要点**：链路 3 是「全量」（含配置+筛选+缓存），链路 4 是「纯数据」查询，crm-report 的统计图查询最终就打到这里（见 crm-report 链路 2）。

---

## 链路 5：排行榜查询

> **这条链路是干什么的（大白话）**：**场景**：BI 里的排行榜组件，比如「销售额 Top10 业务员」「回款排行」。**它做的事**：接收排行维度、指标、排序方向、取前 N 名，翻译成查询条件，复用统计查询内核从 ClickHouse 聚合数据里查出来，返回排行列表（含名次和明细）。


**API 文件**：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/BillBoardController.java`
**接口方法**：`POST /stat/billBoard/measureData/query` → `queryBillMeasureData()`（第 34 行）；`POST /stat/billBoard/detail/query` → 明细查询（第 59 行）

```
BillBoardController.queryBillMeasureData()
  → BillBoardService.queryBillMeasureData()（service/BillBoardService.java，第 143 行）
      ├─ 组装排行榜查询条件（维度/指标/排序）
      └─ 内部复用统计查询内核（easy-stat / ClickHouse 查询）
  → QueryBillMeasureDataResult
```

**底层落点**：ClickHouse 聚合数据（billboard 排行统计）。

**新手要点**：排行榜 = 「按指标排序的统计图」，先看 BillBoardService 怎么把排行参数翻译成查询条件。

---

## 链路 6：聚合规则启停（对接数仓计算开关）

> **这条链路是干什么的（大白话）**：**场景**：管理员在后台停用/启用某个统计图（比如某图算得太慢、暂时下线）。**它做的事**：fs-bi 只负责更新聚合规则的状态（PostgreSQL），然后发 MQ 通知 warehouse：这个图不用算了/可以恢复算了。warehouse 收到后停止/恢复底层 ClickHouse 聚合计算，省钱省资源。


**API 文件**：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/AggRuleController.java`
**接口方法**：`POST /stat/aggRule/aggRuleList/batchStopAggRule` → `batchStopAggRule()`（第 28 行）；`batchEnableAggRule`（第 38 行）

```
AggRuleController.batchStopAggRule()
  → AggRuleService.batchStopAggRule()（service/AggRuleService.java）
      └─ 更新聚合规则状态 → 发 MQ 通知 warehouse 停止/开启计算
          （AggRuleService 里 sendMessage → 消息队列 → warehouse 消费）
  → UpdateAggRuleStatusResult
```

**底层落点**：PostgreSQL（聚合规则表）+ MQ（`BI2BI_OFFLINE_TOPIC` 等）。

**新手要点**：这是「BI 配置层 → 数仓计算层」的联动接口：fs-bi 只改规则状态，真正停止计算靠 MQ 通知 warehouse。

---

## 链路 7：目标规则查询

> **这条链路是干什么的（大白话）**：**场景**：目标管理模块查询「企业给员工定的业绩目标」配置，比如销售 A 的月度目标 10 万。**它做的事**：只查配置清单（目标对象、考核维度、规则），数据存在 PostgreSQL。真正的目标「计算」（实际完成多少）在 warehouse 的 `/goalRule/*` 接口做，这条链路只是读配置。


**API 文件**：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/GoalRuleController.java`
**接口方法**：`POST /stat/goalRule/goalObjectListBySchemaObjectName/query` → `queryGoalObjectListBySchemaObjectName()`（第 33 行）；`aggConditionsByAggObject/query`（第 55 行）

```
GoalRuleController.queryGoalObjectListBySchemaObjectName()
  → StatGoalRuleService（stat 服务）
      └─ 查询目标规则对象清单（按 schema 过滤）
          → MyBatis Mapper → PostgreSQL（目标规则表）
  → QueryAggObjectListResult
```

**底层落点**：PostgreSQL 目标规则表（fs-bi-stat resources/mybatis/postgresql/mapper/*.xml）。

**新手要点**：目标规则 = 企业给员工定的业绩目标，这里只做配置查询；目标的「计算」在 warehouse（DwsController /goalRule/*）。

---

## 链路 8：指标生命周期启停（AI 指标治理）

> **这条链路是干什么的（大白话）**：**场景**：AI 指标治理后台，管理员把某个指标启用/停用（比如「客单价」这个指标暂时不用了）。**它做的事**：更新指标生命周期状态（启用/停用），带配额校验（不能无限启用），状态存 PostgreSQL。配合「AI 可见性」策略控制指标在智能分析里是否展示。


**API 文件**：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/MetricLifecycleController.java`
**接口方法**：`POST /stat/metricLifecycle/batchEnable` → `batchEnable()`（第 21 行）；`batchDisable`（第 27 行）

```
MetricLifecycleController.batchEnable()
  → MetricLifecycleCommandService.batchEnable()（service/，命令模式）
      → MetricLifecyclePersistenceService（持久化）
          → MyBatis Mapper → PostgreSQL（指标生命周期表）
      → MetricLifecycleEnableQuotaService（配额校验）
  → MetricLifecycleBatchResult
```

**底层落点**：PostgreSQL 指标表 + 配额配置。

**新手要点**：这是「指标生命周期管理」命令（启用/停用指标），配合 `MetricAiVisibilityController`（`POST /stat/metricAiVisibility/update`，第 21 行）做 AI 可见性策略。

---

## 链路 9：订阅定时触发（task 模块）

> **这条链路是干什么的（大白话）**：**场景**：订阅功能——用户订阅了某张报表，系统每天 9 点自动把数据查出来发到他邮箱/企信。**它做的事**：定时任务触发这个接口：查订阅配置 → 复用报表查询能力（链路 1）把数据查出来 → 存运行快照（PG）→ 通过邮件/企信服务推送给订阅人。


**API 文件**：`fs-bi-task/src/main/java/com/facishare/bi/task/controller/SubscriptionController.java`
**接口方法**：`POST /schedule/single/trigger/{schId}/{ei}` → `runSingleSch()`（第 53 行）；`POST /schedule/batch/trigger/{schId}/{ei}` → `runBatchSubSch()`（第 126 行）

```
SubscriptionController.runSingleSch()
  → ApplicationContextHolder.getContext() 取 Bean：SchRunService / SchRunStorageService / ReportService / ScanAndSendJobService
  ├─ SchRunService：调度运行记录（task/dao 实体 SchRunStorage → PostgreSQL）
  ├─ ReportService.queryReportData(arg, ei, ea, userId)   ← 复用报表查询（内部走 easy-stat）
  ├─ 推送：SendMailTestService（邮件）/ SendQiXinMessageService（企信）/ QixinService
  └─ SchRunStorageService：存储运行结果快照
  → ApiResult<String>
```

**底层落点**：PostgreSQL（SchRunStorage 调度运行存储）+ 邮件/企信推送（内部 Dubbo）。

**新手要点**：订阅 = 「定时把报表数据查出来，通过邮件/企信推给订阅人」。入口在 task 模块，查询复用 stat 模块能力。

---

## 链路 10：SQL 引擎执行接口（被 udf-report / dev-platform 调用）

> **这条链路是干什么的（大白话）**：**场景**：udf-report 生成好 SQL 后不想自己连库，dev-platform 也要查数——它们统一调这个服务。**它做的事**：接收「SQL 文本 + 企业 id + 用户 id」，连 PostgreSQL（或 SQL Server）执行，返回数据集；相同 SQL 会用 Redis 缓存（key = 企业 + SQL）。相当于一个「公共的 SQL 执行器」。


**API 文件**：`fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/service/impl/SqlEngineServiceImpl.java`
**接口方法**：`POST v1/sql_engine/{ei}/query_from_pg` → `queryFromPg()`；`query_from_sql` → `queryFromSql()`；`query_from_pg_for_pre_refresh` → `queryFromPgForPreRefresh()`

```
调用方（udf-report / dev-platform）
  → SqlEngineClient（fs-bi-client，@FRestApi("BI_SQLENGINE")）   ← HTTP 客户端
      → SqlEngineServiceImpl.queryFromPg(sql, ei, userId)
          ├─ RequestContextManagerBase.setContext(ei, userId)
          └─ repositoryFacade.query(DBType.PG, sql)
              → RepositoryFacade.query()（repository/RepositoryFacade.java）
                  ├─ 灰度直连：queryRepository.query(dbType, sql)
                  └─ 默认：queryRepository.queryCacheAble(dbType, sql, key)   ← Redis 缓存（key=ei+sql）
                      → QueryRepository → PGSQLExecutor（executor/PGSQLExecutor.java）
                          → PostgreSQL / SQL Server（MS）
  → DataSet
```

**底层落点**：PostgreSQL（PG）/ SQL Server（MS）+ Redis 查询缓存。

**新手要点**：这是 fs-bi 对外提供的「统一 SQL 执行服务」。udf-report 的报表查询最终打到这里（见 udf-report 链路 1/2）。

---

## 链路 11：元数据服务（Dubbo/JAX-RS 提供，被 stat 等消费）

> **这条链路是干什么的（大白话）**：**场景**：报表/统计图设计器里选对象、拖字段时，需要知道「客户这个对象有哪些字段、字段是什么类型」。**它做的事**：提供元数据查询（对象列表、字段列表、对象关系树），数据存在 PostgreSQL 元数据库。它是被调用方，报表查询（链路 1）也会拿它来理解模型。


**API 文件**：`fs-bi-metadata/src/main/java/com/facishare/bi/metadata/report/service/impl/ReportMetadataServiceImpl.java`
**接口方法**：实现 `MetadataService`（JAX-RS `@PathParam` 风格）：`getDescribeMetadata()`（第 154 行）、`getDescribeObjectRelationTree()`（第 235 行）、`queryObjectList()`（第 355 行）

```
调用方（stat 模块 / 其他服务，经 Dubbo 或 JAX-RS）
  → ReportMetadataServiceImpl.getDescribeMetadata(tenantId)
      ├─ metadata/report/dao（entity 层：UdfObjDO、FieldInfoDO 等）
      └─ MyBatis Mapper（resources/mybatis/mapper/*.xml）→ PostgreSQL（元数据库）
  → DescribeMetadata
```

**底层落点**：PostgreSQL 元数据库（对象、字段、关系表）。

**新手要点**：元数据是「对象/字段/关系」的字典，报表查询（链路 1）要拿它来理解「这个对象有哪些字段」。fs-bi-metadata 主要是被调方。
