# fs-bi-udf-report 全链路走读手册（10 条主链路）

> 用法：每一条链路都从「API 接口文件 → 方法 → 服务 → 数据层/RPC」完整串联。你只需要按顺序打开文件、找到方法，一行行看。
> 仓库根：`/Users/muqingji/code/serve/fs-bi-udf-report`；主代码模块是 `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/`，下文路径都省略这个前缀。
> 行号为当前代码实际行号，找不到就按类名/方法名搜索。
> **跨服务跳转指引**：udf-report 是「自定义报表（UDF）计算服务」，是真正的 SQL 生成 + 执行引擎。它被 crm-report 和 dev-platform 调用；SQL 执行又分两条路：
> - 默认：调 fs-bi 的 SQL 引擎服务（fs-bi-sqlengine，见《全链路走读-fs-bi.md》链路 10）
> - 直连：CHJDBCService 直连 ClickHouse
> - 报表保存/变更 → 发 MQ 给 warehouse（见《[全链路走读-fs-bi-warehouse.md](../大数据/全链路走读-fs-bi-warehouse.md)》DWSViewChangeConsumer）
> 上游入口见《全链路走读-fs-bi-crm-report.md》链路 1/4/5 和《全链路走读-fs-bi-dev-platform.md》链路 1。

---

## 链路速览表（先看这个：10 秒知道每个链路是干啥的）

| 链路 | 一句话说明（大白话） |
| --- | --- |
| 1 报表数据查询核心 | 真正的「报表计算引擎」：读配置 → 生成 SQL → 执行 → 返回数据（被 crm-report/dev-platform 调） |
| 2 报表查询异步缓存 | 相同参数重复查时用 reqId+Redis 缓存，第二次直接返回，快 |
| 3 交叉表查询 | 透视表（行列都有维度）的计算，SQL 组装逻辑和分组表不同 |
| 4 订阅查询+上传 | 订阅场景先把全量结果算好存文件服务器，前端按页读，避免重复查库 |
| 5 保存/编辑报表 | 写 5 张配置表（定义/关系/筛选/字段/交叉字段）+ 发 MQ 让 warehouse 预建表 |
| 6 查询时同步 DW 数据 | CH 直查模式下，查询前先确保 warehouse 算好聚合表，再直接查 ClickHouse |
| 7 筛选器范围查询 | 报表筛选下拉选项（静态配置 or 动态从数据里查） |
| 8 报表校验 | 保存报表前检查：对象在不在、字段在不在、公式对不对 |
| 9 报表模板创建 | 新建报表第一步：列出可选对象和对象间关系，供设计器拖拽建模 |
| 10 用户/租户配置 | 用户级/租户级个性化设置（每页多少行、导出偏好等） |

---

## 链路 1：报表数据查询核心链路（被 crm-report / dev-platform 调用）

> **这条链路是干什么的（大白话）**：**场景**：这是 udf-report 的「主菜」。crm-report（门户报表查询）和 dev-platform（拼表中的报表数据源）最终都会调它。**它做的事**：①校验参数、处理多币种/筛选器/时区 ②把报表参数转换成内部模型 GenericObject ③用 SQL 引擎（SQLEngine）按模型生成 SQL ④执行 SQL：默认调 fs-bi 的 SQL 引擎服务连 PostgreSQL，灰度企业直连 ClickHouse ⑤把结果转成统一格式返回。**理解**：整条 BI 链路的「算数」就在这一步。


**API 文件**：`api/controller/RptUdfDataController.java`
**接口方法**：`POST /rptUdfViewDataController/queryReportData` → `queryReportData()`（第 615 行）

```
RptUdfDataController.queryReportData()（第 615 行）    ← 入口：crm-report BIUDFResource / dev-platform ReportService 都是调它
  ├─ 校验用户/参数：queryReportDataArgValidator.checkUserInfo / checkQueryReportDataArg
  ├─ 多币种转换：multiCurrencyService.multiCurrencyView(viewId)
  ├─ 灰度判断：命中合并查询或非异步 → originQueryReportData()
  ├─ 否则走异步缓存流程（见链路 2）
  └─ originQueryReportData()（第 740 行）★同步查询核心★
      ├─ ThreadLocalHolder 写入 ei/uid/querySource/时区
      └─ udfRptReportDataService.getUDFReportResults(userInfo, arg)
          → UDFRptReportDataService.getUDFReportResults()（jsonbuilder/service/UDFRptReportDataService.java，第 188 行）
              ├─ 1. 回调函数处理：funcHandleService.handlePreCallBackFunc（取数前自定义函数）
              ├─ 2. 筛选器转换：filterConvertHandle.paas2biFilter（外部筛选格式 → 内部格式）
              ├─ 3. preProcessQueryReportDataArg() 预处理参数（默认值/日期范围/时区）
              ├─ 4. 灰度 cutChGrayService.cutCh() 判断：
              │     ├─ 命中 CH → getReportDataResultByCH()（ClickHouse 直查，见链路 1 后半段）
              │     └─ 默认 → getReportDataResult()（第 1702 行）★PG 查询核心★
              │           ├─ 多币种：multiCurrencyService.multiCurrencyHandle
              │           ├─ 计算字段解析：calculateFieldService.analysisAndFillCalcSubItems
              │           ├─ 参数转模型：json2DFHandler.cvtQRDA2GO()（QueryReportDataArg → GenericObject）
              │           └─ 生成 SQL 并执行：sqlEngine.query(genericObject, displayFields)
              │                 → SQLEngine.query()（sqlengine/SQLEngine.java，第 126 行）
              │                     ├─ 构造 QueryMode（明细/分组/聚合模式）
              │                     └─ run()（第 157 行）
              │                         ├─ TableReferenceBuilder 构建表引用（from 子句）
              │                         ├─ extSqlAssembler.assemble(genericObject, builder, mode)  ★生成 SQL★
              │                         │     → SQLAssembler 系列（sqlAssembler/newSqlAssembler/extSqlAssembler 三套）
              │                         │         → 输出 List<QueryData>{sql, groupByFields, ...}
              │                         ├─ getDataSetFromDB(queryDataList, userInfo)  ★执行 SQL★
              │                         │     → AsyncQueryTask.queryDataSets(sqls, userInfo)（sqlroute/AsyncQueryTask.java，第 115 行）
              │                         │         → queryServiceAdapter.queryFromNewDw(sql, queryContext)（rpc/QueryServiceAdapter.java，第 46 行）
              │                         │             ├─ 清缓存：clearCache=1 时删 Redis（QueryCache key）
              │                         │             └─ sqlEngineClient.queryFromPg(sql, tenantId, userId)
              │                         │                 → fs-bi SqlEngineClient（@FRestApi("BI_SQLENGLE")）
              │                         │                     → 跨服务 HTTP → fs-bi-sqlengine query_from_pg（见 fs-bi 链路 10）
              │                         │                 → fs-bi PGSQLExecutor → PostgreSQL
              │                         │             （若灰度直连 CH：chjdbcService.queryDataSet(sql, ei)
              │                         │                 → CHJDBCService.queryDataSet()（clickhouse/service/CHJDBCService.java，第 44 行）
              │                         │                     → JdbcConnection.query() → ClickHouse）
              │                         ├─ queryResultHandler.handle(...) 结果转 QueryReportDataResult
              │                         └─ handlePageUp() 真分页处理
              └─ 5. 结果后处理：handleFixedField 冻结列 / funcHandleService.handleCallBackFunc / 分页
```

**底层落点**：PostgreSQL（经 fs-bi-sqlengine 的 PGSQLExecutor）或 ClickHouse（CHJDBCService 直连）+ Redis（查询缓存）。

**新手要点**：这是 udf-report 的「心脏链路」，建议按四步读：`getUDFReportResults`（预处理）→ `getReportDataResult`（组装模型）→ `SQLEngine.run`（生成 SQL）→ `AsyncQueryTask`（执行 SQL）。SQL 文本会在日志里打印（`Preview SQL: ...`），这是调试利器。

---

## 链路 2：报表查询异步缓存版（reqId + Redis）

> **这条链路是干什么的（大白话）**：**场景**：用户反复查看同一张报表（同样的筛选条件），或者图表切换页签。**它做的事**：把「报表参数」算出一个唯一 id（reqId），先查 Redis 缓存状态：没查过→标记处理中→现查（就是链路 1 的全套）→结果写缓存；查过→直接返回缓存。**好处**：相同查询第二次起不用再生成 SQL 跑库，秒开。


**API 文件**：`api/controller/RptUdfDataController.java`
**接口方法**：`POST /rptUdfViewDataController/queryReportData` → `queryReportData()`（第 615 行，异步分支）

```
RptUdfDataController.queryReportData()（异步分支，第 653 行起）
  ├─ 1. 生成 reqId：AsyncComponentFactory.getKeyGenerator(QueryReportDataArg.class).generate(arg)
  ├─ 2. 强刷：refresh=1 → asyncReportQueryCache.removeReportCache(reqId)
  ├─ 3. 查缓存状态：asyncReportQueryCache.getStatusByReqId(reqId)
  │     ├─ 空 → cacheStatus(reqId, ASYNC_TASK_PROCESSING) 标记处理中
  │     │     → queryReportDataSynchronously()（内部就是链路 1 的完整查询）
  │     │     → 结果写缓存：asyncReportQueryCache.cacheResult / cacheDataSet
  │     └─ 已有结果 → asyncReportQueryCache.getResultByReqId() 直接返回
  └─ processQueryReportDataResult() 结果后处理（过滤/提示/超限检查）
```

**底层落点**：Redis（按 reqId 缓存查询结果）+ PostgreSQL/ClickHouse（真实数据）。

**新手要点**：同一个报表参数（hash 成 reqId）短时间内重复查，直接命中缓存，避免重复算 SQL。`refresh=1` 强制绕过缓存。

---

## 链路 3：交叉表（透视表）查询

> **这条链路是干什么的（大白话）**：**场景**：用户打开交叉表（透视表）报表——行是维度、列也是维度、中间是指标值。**它做的事**：和链路 1 共用 SQL 引擎，但 SQL 组装逻辑不同：交叉表要把「列维度」也变成聚合维度（行转列），多一层行列头处理，最后返回带行/列头的数据结构。


**API 文件**：`api/controller/RptUdfDataController.java`
**接口方法**：`POST /rptUdfViewDataController/queryPivotReportData` → `queryPivotReportData()`（第 222 行）

```
RptUdfDataController.queryPivotReportData()
  → udfPivotReportDataService.getPivotReportData(userInfo, arg, outerUserInfo)
      → UDFPivotReportDataService（jsonbuilder/service/UDFPivotReportDataService.java）
          ├─ 1. 参数预处理（同链路 1：筛选器/时区/回调）
          ├─ 2. 灰度判断 CH：
          │     ├─ 命中 → udfRptReportDataService.getReportDataResultByCH()（第 900 行）
          │     └─ 默认 → udfRptReportDataService.getReportDataResult()（第 907 行）
          │           → 同链路 1 → SQLEngine.run()
          │               ├─ 交叉表分支：genericObject.getIsPivotTable()=true
          │               ├─ 行列维度 SQL 组装（pivot 逻辑：行分组 + 列分组 + 指标）
          │               └─ getDataSetFromDB → AsyncQueryTask → fs-bi-sqlengine / CHJDBCService
          └─ 3. 结果转 PivotReportDataResult（行/列头 + 单元格值）
```

**底层落点**：PostgreSQL（经 fs-bi-sqlengine）/ ClickHouse。

**新手要点**：交叉表和分组表的区别只在 SQL 组装：交叉表把「列分组」也变成聚合维度（行转列）。入口链路与链路 1 共用 SQL 引擎。

---

## 链路 4：报表订阅查询 + 上传（inner 接口）

> **这条链路是干什么的（大白话）**：**场景**：订阅任务要推送全量数据（可能几万行）。**它做的事**：①查全量数据（复用链路 1）②把结果用 Kryo 压缩后上传到文件服务器 ③返回文件地址和总行数；上游（crm-report 订阅执行）按页从文件读数据推送，而不是反复查库。**理解**：先算好存文件，再按页取。


**API 文件**：`api/controller/RptUdfDataController.java`
**接口方法**：`POST /rptUdfViewDataController/innerUdfQueryReportDataAndUpload`（第 1019 行）；`.../innerUdfQueryReportDataAndUploadByPage`（第 1069 行）

```
RptUdfDataController.innerUdfQueryReportDataAndUploadByPage()
  ├─ 1. 复用链路 1 的查询（getUDFReportResults）
  ├─ 2. 结果序列化：Kryo（BytesUtils.writeCompressObjectWithKryo）
  ├─ 3. 上传文件服务器：fileService.uploadFile(...) → 返回 FileModelExt{filePath, totalCount}
  └─ 4. 供上游分页读取：crm-report 的 loopQueryByPage 按页从文件读
```

**底层落点**：PostgreSQL/ClickHouse（查询）+ 文件服务器（结果文件）。

**新手要点**：订阅场景数据量大，先查全量数据存成文件，前端/推送按页读文件而不是重复查库。crm-report 的 `SchRunScanThread`（订阅执行）就是调这两个接口。

---

## 链路 5：保存/编辑报表（含发 warehouse 消息）

> **这条链路是干什么的（大白话）**：**场景**：用户在报表设计器里保存一张新报表，或编辑/另存/复制。**它做的事**：①把报表配置拆开写进 5 张 PG 表（rpt_view 定义、对象关系、筛选器、字段、交叉字段）②清相关缓存 ③如果企业开了 ClickHouse 聚合灰度，发 MQ（bi-warehouse-event/dws_view_event）通知 warehouse 预建 ClickHouse 聚合表（sourceType=3 表示报表）。


**API 文件**：`api/controller/RptUdfViewCreateController.java`
**接口方法**：`POST /rptUdfViewCreateController/saveRptView` → `saveRptView()`（第 59 行）；`/copyRptView` → `copyRptView()`（第 85 行）；`/createAndSaveRptView` → `createAndSaveRptView()`（第 102 行）

```
RptUdfViewCreateController.saveRptView()
  ├─ 清缓存：asyncReportQueryCache.removeRptViewCache / removeRptDataCache
  └─ saveViewAsyncService.saveViewAsync(args, ei, uid)
      → SaveViewAsyncService.saveViewAsync()（jsonresolver/service/SaveViewAsyncService.java，第 32 行）
          ├─ 异步线程：CompletableFuture → saveViewService.saveView()
          └─ SaveViewService.saveView()（jsonresolver/service/SaveViewService.java）
              → saveData()（第 281 行附近）★保存核心★
                  ├─ 灰度 reportChGray 命中且非交叉表 → dwViewService.saveDwContext() 保存 DW 上下文
                  │     → warehouseEventProducer.sendMessage(ei, viewId, 3)   ★跨服务：发 MQ 给 warehouse★
                  │         → WarehouseEventProducer（mq/WarehouseEventProducer.java）TOPIC "bi-warehouse-event" TAG "dws_view_event" sourceType=3（报表）
                  │             → warehouse DWSViewChangeConsumer.consumeMessage() → statTopologyService.doCreateTopology
                  │               （见《[全链路走读-fs-bi-warehouse.md](../大数据/全链路走读-fs-bi-warehouse.md)》）
                  ├─ 1. saveRptView()：写 rpt_view 报表定义表 → MyBatis → PostgreSQL
                  ├─ 2. saveViewObjRelation()：写 udf_view_obj_relation 对象关系表 → PostgreSQL
                  ├─ 3. saveViewFilter()：写 udf_rpt_filter 筛选器表 → PostgreSQL
                  ├─ 4. saveViewField()：写 udf_rpt_view_field 字段表 → PostgreSQL
                  └─ 5. 交叉表额外 savePivotViewField()：写 pivot_rpt_view_field → PostgreSQL
```

**跨服务落点（必看）**：PostgreSQL（4~5 张配置表）+ RocketMQ（bi-warehouse-event/dws_view_event）→ warehouse 建 ClickHouse 拓扑。

**新手要点**：保存报表 = 写 5 张配置表（定义/关系/筛选/字段/交叉字段）+ 发消息让 warehouse 预建表。复制报表走 `CopyViewService.copyView()`（jsonresolver/service/CopyViewService.java）→ 深拷贝配置 + 也发 warehouse 消息（sourceType=3）。

---

## 链路 6：查询时同步 DW 历史数据（CH 处理器）

> **这条链路是干什么的（大白话）**：**场景**：ClickHouse 直查（CH 灰度）模式下，用户查一张报表，但 warehouse 那边的聚合表可能还没算好。**它做的事**：查询前先检查报表是否满足「同步 DW 数据」条件（如更新时间超过 1 分钟）→ 把报表的字段/筛选上下文保存起来 → 发 MQ 让 warehouse 算这张报表的 DW 表 → 然后再从 ClickHouse 查数据。**理解**：先触发计算，再等数据。


**API 文件**：`jsonbuilder/service/QueryReportDataArgCHProcessor.java`（被链路 1 的 CH 查询分支调用）
**触发点**：`getReportDataResultByCH()` 内部 → `QueryReportDataArgCHProcessor.process()`

```
QueryReportDataArgCHProcessor.process()
  ├─ 1. 判断报表是否满足「DW 同步条件」（灰度 + 更新时间 > 1 分钟，见 saveOneMinuteLater）
  ├─ 2. handleSaveOrUpdateHisDw()（第 121 行）
  │     ├─ dwViewService.buildDwContext(arg) 构建报表的 DW 上下文
  │     ├─ fillViewFilterDwFieldId / fillViewFieldDwFieldId 填充筛选/字段的 dw_field_id
  │     ├─ dwViewService.saveDwContext() 保存上下文 → PostgreSQL
  │     └─ warehouseEventProducer.sendMessage(ei, viewId, 3)   ★发 MQ 给 warehouse（sourceType=3 报表）★
  ├─ 3. 走 ClickHouse 查询：查询 warehouse 已算好的 DW 表数据
  └─ 4. 返回 QueryReportDataResult
```

**底层落点**：PostgreSQL（DW 上下文）+ RocketMQ → warehouse + ClickHouse（DW 表）。

**新手要点**：这是「CH 直查」模式：先确保 warehouse 把报表的聚合表算好（发消息触发），再直接查 ClickHouse 拿数，比每次都现算快。

---

## 链路 7：筛选器范围查询

> **这条链路是干什么的（大白话）**：**场景**：报表上的筛选器（日期、枚举、人员、部门）下拉框要显示可选范围。**它做的事**：读报表筛选器配置（PG），静态选项直接返回；动态选项（比如「去重后的区域列表」）构造子查询去执行拿值（走 SQL 引擎/ClickHouse）。返回分组筛选器列表。


**API 文件**：`api/controller/RptUdfViewEditController.java`
**接口方法**：`POST /rptUdfViewEditController/getFiltersResult` → `getFiltersResult()`（第 230 行）；`/getObjRelationResult` → `getObjRelationResult()`（第 136 行）

```
RptUdfViewEditController.getFiltersResult()
  → udfRptViewFilterService.getFilterResult / filter 相关 service
      ├─ 1. 查报表配置（rpt_view + udf_rpt_filter）→ PostgreSQL
      ├─ 2. 对每个筛选器计算可选范围：
      │     ├─ 日期/枚举：直接读配置/字典 → PostgreSQL
      │     └─ 数据驱动（取字段去重值）：构造子查询 SQL → AsyncQueryTask → fs-bi-sqlengine / ClickHouse
      └─ 3. 组装 FilterResult（分组筛选器列表）

RptUdfViewEditController.getObjRelationResult()
  → 查询对象间关系（udf_view_obj_relation）→ PostgreSQL
```

**底层落点**：PostgreSQL（筛选器配置）+ 可选 ClickHouse（动态取值范围）。

**新手要点**：报表筛选器下拉选项分两种：配置写死的、从数据里查出来的。动态选项就是跑一条「SELECT DISTINCT 字段」的 SQL。

---

## 链路 8：报表校验（保存前检查）

> **这条链路是干什么的（大白话）**：**场景**：用户点「保存报表」按钮前，系统先做体检。**它做的事**：校验主题对象是否存在、字段是否有效、筛选器和计算字段公式是否合法，返回校验结果（成功 or 错误列表）。**理解**：防止把「有问题的报表」存进库里，前端保存前先调它。


**API 文件**：`api/controller/RptUdfViewValidateController.java`
**接口方法**：`POST /rptUdfViewValidateController/validateView` → `validateView()`（第 46 行）

```
RptUdfViewValidateController.validateView()
  → udfRptViewValidateService.validateView(arg, userInfo)
      ├─ 1. 校验主题对象（business object）是否存在/可用 → PostgreSQL（元数据）
      ├─ 2. 校验字段是否有效（displayFields 逐个检查）→ 元数据 + fs-bi-metadata
      ├─ 3. 校验筛选器/排序/计算字段表达式合法性
      └─ 4. 返回 ValidateViewResult{status, errorList}
```

**底层落点**：PostgreSQL（元数据表）+ 可能调 fs-bi-metadata。

**新手要点**：保存报表前先「体检」：对象在不在、字段在不在、公式对不对。前端保存按钮点击后先调这个接口。

---

## 链路 9：报表模板创建（模型关系构建）

> **这条链路是干什么的（大白话）**：**场景**：用户点「新建报表」，设计器第一步要选「主业务对象」（比如选「客户」作为主表）。**它做的事**：列出可用的模板对象、以及对象之间的关联关系（比如客户↔订单），返回对象-关系树给设计器，用户选完就能拖字段建模。


**API 文件**：`api/controller/RptUdfTemplateCreateController.java`
**接口方法**：`POST /rptUdfTemplateCreateController/getMainBusinessObjectList`（第 60 行）；`/buildModelRelation`（第 134 行）

```
RptUdfTemplateCreateController.getMainBusinessObjectList()
  → templateService.getMainBusinessObjectList(...)
      → 查可用的主业务对象（模板）→ PostgreSQL（模板/对象表）

RptUdfTemplateCreateController.buildModelRelation()
  → templateService.buildModelRelation(...)
      ├─ 按模板配置的对象 + 关联关系
      ├─ 查字段/关系元数据（fs-bi-metadata 或本地 PG）
      └─ 返回可拖拽建模的「对象-关系」树（给报表设计器用）
```

**底层落点**：PostgreSQL（模板配置 + 元数据）。

**新手要点**：报表设计器「新建报表」第一步：选主对象 → 选关联对象 → 拖字段。这个接口就是提供「可选对象和关系」的。

---

## 链路 10：用户/租户个性化配置（分页大小等）

> **这条链路是干什么的（大白话）**：**场景**：用户设置「我每页看 50 行」、企业管理员设置「全公司默认每页 100 行」、导出位置等偏好。**它做的事**：读写用户级/租户级的个性化配置（存 PG 的 user_profile / tenant_profile 表）。查询时（链路 1 的预处理）会读分页大小配置决定每页返回多少行。


**API 文件**：`api/controller/UserProfileController.java`（第 29 行）；`api/controller/TenantProfileController.java`（第 59 行）
**接口方法**：`POST /userProfileController/{tag}/save`（第 45 行）、`/{tag}/load`（第 66 行）；`POST /tenantProfileController/savePageSizeConfig`（第 257 行）、`/queryPageSizeConfig`（第 303 行）

```
UserProfileController.save()（第 45 行）
  └─ profileServiceFacade.saveUserProfile(userInfo, tag, items)
      → 用户级 KV 配置（ui 偏好/导出位置等）→ MyBatis → PostgreSQL（user_profile 表）

TenantProfileController.savePageSizeConfig()（第 257 行）
  └─ profileServiceFacade.savePageSizeConfig(...)
      → 租户级分页大小配置 → PostgreSQL（tenant_profile / 分页配置表）
      → 查询时（链路 1 的 preProcessQueryReportDataArg）会读它决定每页条数
```

**底层落点**：PostgreSQL（user_profile / tenant_profile 配置表）。

**新手要点**：这些是「个性化配置」接口：用户级（自己看多少行、导出的列位置）和租户级（全公司默认分页大小）。dev-platform 的 `ReportService.queryPageSize` 也调了 `tenantProfileController/queryPageSizeConfig`。

---

## 附录：udf-report 关键调用清单（速查）

| 角色 | 位置 | 说明 |
| --- | --- | --- |
| SQL 引擎（被调） | `sqlengine/SQLEngine.java` 第 126 行 `query()` | 报表/交叉表查询的统一 SQL 生成 + 执行入口 |
| SQL 执行（下游 1） | `sqlroute/AsyncQueryTask.java` 第 115 行 → `rpc/QueryServiceAdapter.java` 第 46 行 → `sqlEngineClient.queryFromPg` | 走 fs-bi-sqlengine（见 fs-bi 链路 10） |
| SQL 执行（下游 2） | `clickhouse/service/CHJDBCService.java` 第 44 行 `queryDataSet()` | 灰度直连 ClickHouse（jdbc:clickhouse://10.112.4.253:9090/...） |
| 数据查询（被调） | `jsonbuilder/service/UDFRptReportDataService.java` 第 188 行 | crm-report/dev-platform 查询的真正入口 |
| 交叉表（被调） | `jsonbuilder/service/UDFPivotReportDataService.java` | `/queryPivotReportData` 的实现 |
| warehouse 联动（MQ） | `mq/WarehouseEventProducer.java`（TOPIC `bi-warehouse-event` / TAG `dws_view_event`） | SaveViewService / CopyViewService / QueryReportDataArgCHProcessor / HandleDwHistoryDataService 发消息 |
| 适配接口（老 crm-report 迁移） | `adapter/controller/SalesBriefDataController.java`、`SalesClueDataController.java`、`SaleProcessAnalysisController.java`、`ProviderForFeedRestController.java` | 兼容旧调用方 |
| 测试查询 | `api/controller/RptUdfQueryTestController.java` 第 53 行 `/query` | 调试用临时 SQL 查询 |
