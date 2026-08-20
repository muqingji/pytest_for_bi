# fs-bi-udf-report 代码走读详解（新手向 · 超详细版）

> 配套文档：《fs-bi-udf-report-架构分析.md》的「十、代码走读路线」。本文把最核心的**自定义报表（UDF Report）数据查询链路**逐行讲透——这也是 crm-report / dev-platform 查询链路的最终落点之一。
> 仓库根目录：`/Users/muqingji/code/serve/fs-bi-udf-report`；代码默认在 `fs-bi-udf-report-web/src/main/java` 下。

---

## 0. 读代码前，先认识几个概念（新手速查）

| 概念 | 一句话解释 |
| --- | --- |
| UDF / 自定义对象 | CRM 里用户自己建的「对象」（相当于自己建表），报表基于这些对象做查询 |
| GenericObject | 本仓库内部的中转对象：把「查询参数 + 元数据」统一包装，喂给 SQL 引擎 |
| SQL 引擎（SQLEngine） | 把 GenericObject 翻译成 SQL，并负责执行和把结果转成报表结构 |
| SQLAssembler | 专门拼 SQL 的组件（有老版/新版/扩展版三个实现） |
| QueryData | 一条「待执行 SQL + 它的元信息」的记录 |
| 下游查询服务 | 本服务把最终 SQL 通过 `SqlEngineClient` 发给 fs-bi-sqlengine 执行（PG / SQL Server），ClickHouse 也可直连 |
| Redis 查询缓存 | 相同的 SQL 在短时间内重复查询，直接返回缓存结果 |

**这个仓库的特点**：它是「报表查询的执行核心」——负责把用户的报表配置翻译成 SQL，然后让 fs-bi-sqlengine 去执行。

---

## 1. 主链路总览

```
前端 / crm-report（BIUDFResource）/ dev-platform（ReportService）
   │ ① POST /rptUdfViewDataController/queryReportDataMerge
   ▼
RptUdfDataController.queryReportDataMerge()      ← 控制器：限流/降级/用户注入
   ▼
QueryReportDataMergeService（合并查询，逐视图）
   ▼
RptUdfDataController.queryReportData()           ← 单报表查询入口
   ▼
UDFRptReportDataService.getReportDataResult()    ← 业务核心：多币种/计算字段/权限字段
   ▼
SQLEngine.query(genericObject, displayFields)    ← SQL 引擎：组装 SQL + 执行
   ├─ SQLAssembler / NewSqlAssembler / ExtSqlAssembler（拼 SQL）
   ▼
AsyncQueryTask.query()                           ← 批量执行（FutureTask 并发）
   ▼
QueryServiceAdapter.queryFromNewDw()             ← 适配层：Redis 缓存判断 + 调用下游
   ▼
SqlEngineClient（fs-bi-client，HTTP）→ fs-bi-sqlengine → PostgreSQL / ClickHouse
   ▼
QueryResultHandler.handle() → QueryReportDataResult（返回报表结果）
```

---

## 2. 步骤 ①：Controller —— 入口

文件：`com/fxiaoke/bi/crm/api/controller/RptUdfDataController.java`

```java
@RequestMapping(value = "/queryReportDataMerge", method = RequestMethod.POST)
@ResponseBody
@SentinelLimit(resource = "queryReportDataMerge", blockHandler = QueryReportDataMergeStrategy.class)
@TimeoutDegradation(degradationStrategy = QueryReportDataMergeStrategy.class)
public QueryReportDataMergeResult queryReportDataMerge(
    @FSUserInfo UserInfo userInfo,
    @RequestBody QueryReportDataMergeArg queryReportDataMergeArg,
    @FSOuterUserInfo OuterUserInfo outerUserInfo) {
  return queryReportDataMergeService.queryReportDataMerge(userInfo, queryReportDataMergeArg, outerUserInfo);
}
```

**新手解读**：
- `/queryReportDataMerge`：一次请求查多个报表再合并结果（Dashboard 场景常用）。
- `@SentinelLimit` 带了 `blockHandler`：被限流时执行一个兜底策略（返回友好提示而不是直接 500）。
- `@TimeoutDegradation` 带 `degradationStrategy`：超时时降级（比如返回部分数据或提示重试）。

---

## 3. 步骤 ②：单报表查询入口

文件：`com/fxiaoke/bi/crm/api/controller/RptUdfDataController.java`（第 615 行 `queryReportData`）

```java
public QueryReportDataResult queryReportData(@FSUserInfo UserInfo userInfo,
                                             @RequestBody QueryReportDataArg queryReportDataArg,
                                             @FSOuterUserInfo OuterUserInfo outerUserInfo) {
  try {
    // 校验 UserInfo 合法性、强刷判断（BIObjectConfigManager.isForceRefresh）
    ...
    // 真正的查询逻辑在"原始查询"方法里（第 740 行）
    return originQueryReportData(userInfo, queryReportDataArg, outerUserInfo, isPrintBizLog);
  } finally {
    ...
  }
}
```

**新手解读**：Controller 里方法很多（透视表、后台分页、异步、字节流返回……），但**殊途同归**，最终都进 `UDFRptReportDataService.getReportDataResult`。先只跟一条主路即可。

---

## 4. 步骤 ③：业务核心 —— getReportDataResult

文件：`com/fxiaoke/bi/crm/jsonbuilder/service/UDFRptReportDataService.java`（第 1702 行）

```java
public QueryReportDataResult getReportDataResult(UserInfo userInfo, QueryReportDataArg queryReportDataArg) {
  // 4.1 填充"数据负责人"字段（掩码/权限需要）
  udfDisplayFieldService.fillOwnerDisplayField(userInfo.getEnterpriseId(), queryReportDataArg);

  // 4.2 判断是否是"外部企业"（下游企业场景）
  if (OutEnterpriseUtil.isDownstreamEnterprise()) { ... }

  // 4.3 schema 隔离判断（某些企业一套独立 schema）
  boolean flag = SchemaIndependentUtils.allowSchemaIndependent(tenantId);

  // 4.4 多币种处理：报表含原币字段时，补充币种换算字段
  if (multiCurrencyService.isOpenMultiCurrencyStatus() && ...) {
    originalCurrency2currencyMap = multiCurrencyService.multiCurrencyHandle(queryReportDataArg);
  }

  // 4.5 解析 BI 计算字段（用户自定义的公式列）
  calculateFieldService.analysisAndFillCalcSubItems(userInfo, ..., queryReportDataArg, flag);

  // 4.6 把"查询参数"转成"GenericObject"（内部统一对象）
  GenericObject genericObject = json2DFHandler.cvtQRDA2GO(userInfo, queryReportDataArg);

  // 4.7 ★核心：交给 SQL 引擎
  QueryReportDataResult queryReportDataResult = sqlEngine.query(genericObject, displayFields);

  // 4.8 结果后处理：去掉隐藏主键列、计算字段求和、加密、i18n 翻译、格式化
  ...
  return queryReportDataResult;
}
```

**新手解读**：
- 这一步展示了「真实业务查询」要处理多少杂事：多币种、计算字段、数据权限掩码、i18n、schema 隔离。
- `json2DFHandler.cvtQRDA2GO`：把接口参数（QueryReportDataArg）翻译成引擎认识的 GenericObject，这是「接口对象」和「引擎对象」的桥。
- `sqlEngine.query(...)` 之后，剩下的都是对结果的「装修」。

---

## 5. 步骤 ④：SQL 引擎 —— 组装 SQL

文件：`com/fxiaoke/bi/crm/sqlengine/SQLEngine.java`（第 126 行 `query`）

```java
public QueryReportDataResult query(GenericObject genericObject, List<DisplayField> displayFields) {
  ViewInfo viewInfo = genericObject.getViewInfo();
  QueryMode mode = new QueryMode(viewInfo, genericObject.getTableFields(), genericObject.isDrillToDetail());

  // 5.1 分组校验：有分组必须有明细或聚合
  if (mode.hasGroupBy() && !(mode.hasDetail() || mode.hasGroupAggregation())) { ... }

  // 5.2 按场景分派：预览 or 正式跑；有分组/无分组
  return isPreview ? preview(...) : run(genericObject, displayFields, mode);
}

private QueryReportDataResult run(GenericObject genericObject, List<DisplayField> displayFields, QueryMode mode) {
  // 5.3 处理层级/下钻字段
  tableFieldsPostHandle(tableFields);
  hierarchyGroupRunProcessing(...);
  handleLTreeHierarchyGroupLevel(...);

  // 5.4 组装 FROM 子句（表引用）
  TableReferenceBuilder builder = getFromBuilder(genericObject);

  // 5.5 报表新查询路径：扩展版组装器
  if (!genericObject.getIsPivotTable()) {
    List<QueryData> queryData2 = extSqlAssembler.assemble(genericObject, builder, mode);
    getDataSetFromDB(queryData2, genericObject.getUserInfo());   // ★执行 SQL
    return extQueryResultHandler.handle(queryData2, mode, displayFields, tableFields, genericObject);
  }

  // 5.6 统计列排序路径（新版组装器）
  if (isAggOrder(mode)) {
    queryDataList = newSqlAssembler.assemble(genericObject, builder, mode, isExport);
    ...
    return aggOrderResult;
  }

  // 5.7 老版组装器（默认路径）
  queryDataList = sqlAssembler.assemble(genericObject, builder, mode, isExport);
  reBuildQueryDataList(queryDataList);
  // 每个 SQL 打日志：Preview SQL1 / SQL2 ...
  queryDataList.forEach(q -> log.info("Preview SQL: {}", q.getSql()));

  getDataSetFromDB(queryDataList, genericObject.getUserInfo());   // ★执行 SQL
  ...
  // 5.8 结果转换：DataSet → QueryReportDataResult
  return queryResultHandler.handle(queryDataList, mode, viewInfo, displayFields, tableFields, ...);
}
```

**新手解读**：
- `QueryMode`：一个「模式」对象，记录这次查询要不要分组、要不要明细、要不要聚合，后面所有组装都看它。
- 三个 Assembler 是「三代」拼 SQL 的实现：老版 `sqlAssembler`、新版 `newSqlAssembler`（统计列排序）、扩展版 `extSqlAssembler`（报表新查询/透视表明细）。新功能优先用扩展版。
- `QueryData`：一条 SQL + 分组字段等信息。日志里 `Preview SQL` 就是最终发给数据库的 SQL——**调试时直接在日志里搜这个词**。

---

## 6. 步骤 ⑤：执行 SQL（AsyncQueryTask → QueryServiceAdapter → 下游）

文件：`com/fxiaoke/bi/crm/sqlroute/AsyncQueryTask.java`

```java
public void query(List<QueryData> dataList, UserInfo userInfo) {
  QueryContext queryContext = QueryContext.builder()
      .tenantId(ei).userId(userId).clearCache(clearCache).version(version).build();

  List<FutureTask<DataSet>> futureTaskList = new ArrayList<>();
  for (QueryData data : dataList) {
    String sql = data.getSql();
    // 每条 SQL 一个任务，并行执行
    FutureTask<DataSet> futureTask = new FutureTask<>(() ->
        queryService.queryFromNewDw(sql, queryContext));
    futureTaskList.add(futureTask);
    taskExecutor.submit(futureTask);
  }
  // 逐个取结果；取到 null 说明下游异常，抛 SqlQueryException
  for (FutureTask<DataSet> task : futureTaskList) {
    DataSet dataSet = task.get();
    if (dataSet == null) throw new SqlQueryException("Query result is null, sql: " + sql);
    data.setDataSet(dataSet);
  }
}
```

文件：`com/fxiaoke/bi/crm/rpc/QueryServiceAdapter.java`（第 46 行）

```java
public DataSet queryFromNewDw(String sql, QueryContext queryContext) {
  // 6.1 强刷（clearCache=1）时，先删 Redis 里的查询缓存
  if (queryContext.getClearCache() == 1) {
    String redisKey = profile + ":QueryCache:" + md5(tenantId + sql);
    queryRedisCache.del(redisKey);
    biCacheRedis.del(redisKey);
  }
  return queryFromNewDw(sql, tenantId, userId, version);
}
```

**新手解读**：
- `AsyncQueryTask` 用线程池并行执行多条 SQL，`FutureTask.get()` 会阻塞等待结果。
- `QueryServiceAdapter` 是「适配器」：把内部调用转成对 `SqlEngineClient` 的调用，同时处理 Redis 缓存失效。
- 缓存 key = `环境 + QueryCache + md5(企业id + SQL)`：同样的 SQL 短时间内重复查会命中 Redis，不用每次都打数据库。

---

## 7. 步骤 ⑥：最终落点 —— SqlEngineClient → fs-bi-sqlengine

```
QueryServiceAdapter
   → SqlEngineClient（com.facishare.bi.client.SqlEngineClient，fs-bi 仓库的 fs-bi-client 模块）
        @FRestApi("BI_SQLENGINE")   ← 服务名
        @POST("v1/sql_engine/{ei}/query_from_pg")  ← 执行 PG
        @POST("v1/sql_engine/{ei}/query_from_sql") ← 执行 SQL Server
   → fs-bi-sqlengine SqlEngineServiceImpl（JAX-RS）
   → RepositoryFacade.query(DBType.PG|MS, sql)
   → PGSQLExecutor（真正查库）
```

> 这条下游链路的详细解读见《走读详解-fs-bi.md》第 8 节。ClickHouse 场景则在本服务内用 `CHJDBCService.queryDataSet(sql, ei)` 直连。

**新手解读**：本服务（udf-report）自己**不直接连 PG/SQL Server 执行报表 SQL**，而是把 SQL 交给 fs-bi-sqlengine 这个「统一执行服务」。好处是执行逻辑（缓存、灰度、超时、SQL 重写）只维护一份。

---

## 8. 其他走读路线速览

**透视表（B）**
```
POST /rptUdfViewDataController/queryPivotReportData（第 222 行）
  → originQueryPivotReportData（第 336 行）
  → UDFPivotReportDataService
  → 复用 SQLEngine（pivot_detail_SQL 路径）+ asyncQueryTask → 结果
```

**异步查询（C）**
```
sendQueryRequest(userInfo, arg) → AsyncSendResult（reqId）   ← 发起
loadQueryResult(reqId) → 查文件/缓存结果 → 分页返回          ← 取结果
```

**视图/模板创建（D，写链路）**
```
RptUdfViewCreateController / RptUdfTemplateCreateController
  → ViewObjectRelationService（对象关系）
  → ObjTreeFieldService / UDFObjFieldService（字段树）
  → RptUdfViewValidateController → rptvalidate（校验）
  → repository（PG 落库）
```

**适配接口（E）**
```
SalesBriefDataController / SalesClueDataController / SaleProcessAnalysisController
  → adapter/service/*Service → 复用 SQLEngine（crm-report 查询能力下沉到这里）
```

---

## 9. 怎么验证我读懂了（实践建议）

1. **抓 Preview SQL**：日志里搜 `Preview SQL`，这是最终 SQL；复制到 ClickHouse/PG 客户端执行，和接口返回结果对比。
2. **断点跟读**：在 `SQLEngine.query`（第 126 行）打断点，Step Into 看 `run()` → `sqlAssembler.assemble` → `getDataSetFromDB`。
3. **看缓存命中**：在 `QueryServiceAdapter.queryFromNewDw` 打断点，连发两次相同请求，第二次注意观察 Redis 缓存 key。
4. **验证下游**：把 fs-bi-sqlengine 停掉再查询，会在这里抛异常——证明 SQL 执行确实在下游。

---

## 10. 新手 FAQ

| 问题 | 回答 |
| --- | --- |
| 为什么有三套 SQLAssembler？ | 历史演进：老版 → 新版（统计列排序）→ 扩展版（新报表查询）；新功能优先用扩展版 |
| GenericObject 是什么？ | 查询引擎的「万能入参」：包含视图信息、表字段、筛选、分页、币种等，避免方法参数爆炸 |
| 为什么 SQL 不在本服务执行？ | 执行能力统一收口到 fs-bi-sqlengine（缓存/灰度/重写一份维护），本服务专注报表语义翻译 |
| `Preview SQL` 日志有什么用？ | 这是调试核心：看到它 = SQL 已生成；对比执行结果 = 验证组装是否正确 |
| 查询结果为什么还要 formatDisplayFieldValues？ | 数据库返回的是原始值，展示层要按字段配置格式化（数字千分位、百分比、日期格式等） |
