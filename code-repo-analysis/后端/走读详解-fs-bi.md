# fs-bi 代码走读详解（新手向 · 超详细版）

> 配套文档：《fs-bi-架构分析.md》的「十、代码走读路线」。本文把其中最核心的**报表数据查询链路**逐行讲透，目标是让你能照着文件路径一步步读下来，明白每一层代码在干什么。
> 仓库根目录：`/Users/muqingji/code/serve/fs-bi`

---

## 0. 读代码前，先认识几个概念（新手速查）

| 概念 | 一句话解释 |
| --- | --- |
| HTTP 请求 | 前端网页用 URL 向服务器要数据。例：`POST /rpt/data/query` 表示「向报表查询接口发一个 POST 请求，参数是 JSON」 |
| Controller（控制器） | 请求的第一站，只负责「接收请求、把参数转给 Service、把结果返回给前端」，不写业务逻辑 |
| Service（服务） | 业务逻辑所在：校验、拼参数、调用别的服务、组装结果 |
| DAO / Mapper（数据访问） | 专门和数据库打交道的层，负责执行 SQL |
| SQL 生成 / SQL 执行 | 报表查询的特殊之处：先根据用户配置「生成」一段 SQL，再「执行」这段 SQL 取数 |
| ClickHouse（CH） | 列式分析数据库，BI 统计数据放在这里，查询非常快 |
| PostgreSQL（PG） | 传统关系数据库，元数据（报表配置等）放在这里 |
| ThreadLocal | 一个「请求私有的小盒子」，同一请求的代码都能往里存东西（如当前用户），请求结束要清空 |
| Dubbo / REST | 服务之间互相调用的方式。REST = 走 HTTP；Dubbo = 走 RPC 协议 |

**分层口诀**：请求进来 → Controller 收 → Service 算 → DAO 查库 → 结果原路返回。

---

## 1. 主链路总览（先看这张图）

```
前端点「打开报表」
   │ ① 发 HTTP 请求 POST /rpt/data/query
   ▼
RptQueryController.queryReportData()      ← 控制器：接请求
   ▼
QueryReportService.queryReportData()      ← 服务：组装上下文、调查询内核
   ▼
RootFlowServiceImpl.goForward()           ← 查询内核：8 个阶段流水线
   ├─ 基础校验 → 参数补全 → 构建模型 → 命中策略
   ├─ 生成 SQL 前置（with-as 初始化）→ 生成查询 SQL
   ├─ 执行查询（ClickHouseSQLExecutor 真正查库）
   └─ 构建结果 → 转换结果
   ▼
StatResult2RptResult.doConvert()          ← 把查询结果转成报表格式
   ▼
返回 QueryReportResult 给前端
```

---

## 2. 步骤 ①：Controller 层 —— 请求的「前台」

文件：`fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/RptQueryController.java`

```java
@Controller                                // 告诉 Spring：这是一个控制器
@RequestMapping("/rpt")                    // 这个类所有接口的 URL 前缀
public class RptQueryController {

  @Autowired
  private QueryReportService queryReportService;   // 注入业务服务

  @RequestMapping(value = "/data/query", method = RequestMethod.POST)
  @ResponseBody                              // 返回值直接写成 JSON 返回给前端
  public QueryReportResult queryReportData(@RequestBody QueryReportDataArg queryReportDataArg) {
    try {
      return queryReportService.queryReportData(queryReportDataArg);
    } catch (Exception e) {
      // 异常处理：来源不同打不同级别日志
      ...
    } finally {
      EasyStatThreadLocal.removeAll();               // 清空请求上下文（防止串号）
      RequestContextManagerBase.removeContext();
    }
  }
}
```

**新手解读**：
- `@RequestMapping("/rpt")` + `/data/query` = 完整地址 `/rpt/data/query`。
- `@RequestBody` 表示前端传来的 JSON 会被自动转成 `QueryReportDataArg` 对象（一个装满了查询参数的对象：报表 id、筛选条件、页码等）。
- `@ResponseBody` 表示返回的对象会变成 JSON 还给前端。
- `finally` 里的清理非常重要：每次请求产生的用户信息都存在 ThreadLocal 里，如果不清理，下一个请求可能读到上一个请求的用户，造成「数据串号」。
- 控制器**几乎没有业务逻辑**，只做三件事：收参、调 Service、返回。这是标准分层。

---

## 3. 步骤 ②：Service 层 —— 业务的「大脑」

文件：`fs-bi-stat/src/main/java/com/facishare/bi/stat/service/QueryReportService.java`（方法 `queryReportData` 第 74 行）

```java
public QueryReportResult queryReportData(QueryReportDataArg queryReportDataArg) {
  try {
    // 3.1 强刷判断：管理员强制刷新时忽略缓存
    if (ConfigManager.isForceRefresh(...)) { queryReportDataArg.setRefresh(1); }

    beforePivotHandle(queryReportDataArg);              // 透视表前置处理

    // 3.2 把当前请求的"谁在查"信息存进 ThreadLocal 上下文
    String tenantId = RequestContextManagerBase.getEi();    // 企业 id
    String userId   = RequestContextManagerBase.getUserId(); // 用户 id
    RequestContextManagerBase.getContext().setClearCache(queryReportDataArg.getRefresh());
    ...

    // 3.3 组装一个"全量上下文"对象，传给查询内核
    WholeContext wholeContext = WholeContext.fromOutsideForm(tenantId, userId, queryReportDataArg);

    // 3.4 核心一步：进入 easy-stat 查询工作流
    QueryChartDataResult queryChartDataResult =
        rootFlowInterface.goForward(wholeContext, CutRuleNameEnum.STAT_QUERY);

    // 3.5 结果转换：查询内核的结果 → 报表展示结果
    QueryReportResult queryReportResult =
        StatResult2RptResult.doConvert(toJarQueryResult, queryReportDataArg);

    return queryReportResult;
  } finally {
    EasyStatThreadLocal.removeAll();   // 别忘了清 ThreadLocal
  }
}
```

**新手解读**：
- `getEi()` 是「企业 id」，`getUserId()` 是「用户 id」。BI 是 SaaS 系统，每个企业数据隔离，几乎所有查询都要带企业维度。
- `WholeContext` 像一个「信封」，把这次查询需要的所有信息（谁查的、查哪个报表、什么筛选条件）打包传给查询内核。
- `CutRuleNameEnum.STAT_QUERY` 是一个枚举，告诉内核「这次走统计查询的规则」，后续还有灰度切量作用。

---

## 4. 步骤 ③：查询内核 —— 8 阶段流水线

文件：`fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/application/service/impl/RootFlowServiceImpl.java`

```java
public Pair<QueryChartDataResult, String> goForward(WholeContext wholeContext, CutRuleNameEnum cutRuleNameEnum, boolean isOnlySql) {
  // 阶段 1：基础校验
  for (List<BaseCheckFlow> ...) { baseCheckFlow.doBaseCheck(wholeContext); }
  // 阶段 2：参数补全
  for (List<CompletionParamFlow> ...) { completionParamFlow.doCompletionParam(wholeContext); }
  // 阶段 3：构建模型
  for (List<BuildModelFlow> ...) { buildModelFlow.doBuildModel(wholeContext); }
  // 阶段 4：命中策略
  for (List<HitStrategyFlow> ...) { hitStrategyFlow.doHitStrategy(wholeContext); }
  // 阶段 5：生成 SQL 前置处理（with-as 初始化）
  for (List<PreGenerateDataQuerySqlFlow> ...) { preGenerateDataQuerySqlFlow.doPreHandle(wholeContext); }
  // 阶段 6：生成查询 SQL
  for (List<GenerateDataQuerySqlFlow> ...) { generateDataQuerySqlFlow.doGenerateDataQuerySql(wholeContext); }
  // 阶段 7：执行查询
  for (List<DataQueryFlow> ...) { dataQueryFlow.doDataQuery(wholeContext); }
  // 阶段 8：构建结果 + 转换结果
  ...
}
```

**新手解读**：
- 这个类就是一个**流水线**：每个阶段都有很多「节点」（FlowNode），每个节点先问自己 `support()`（这个场景用得上我吗？），用得上就执行 `doXxx()`。
- 好处是**可插拔**：要加一种新的查询能力，就新加一个 FlowNode，不用改其他代码。这就是设计模式里的「责任链」思想。
- 每个节点执行完都会记录耗时（`nodeTimeCostList`），线上可以用这个看哪个环节慢。

---

## 5. 步骤 ④：SQL 是怎么生成的

文件：`fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/domain/pregeneratedataquerysql/flow/impl/withas/`

这一包里全是「生成 with-as 前置子查询」的节点，例如：
- `PreSqlWithAsOrgDimensionInitFlowNode`：拼组织维度子查询
- `PreSqlWithAsOrgEmployeeUserInitFlowNode`：拼员工/用户子查询
- `PreSqlWithAsSelectOptionInitFlowNode`：拼下拉选项子查询
- `PreSqlWithAsProductCategoryInitFlowNode`：拼品类子查询

**新手解读**：
- SQL 里的 `WITH ... AS (...)` 是「临时表」语法：先算好一张临时结果，后面主查询再引用它。
- 报表查询里，很多过滤条件（比如「只看我负责的客户」）需要先查组织架构算出一个人员/部门清单，再拿这个清单去过滤主表。这些前置子查询就是在这里拼出来的。
- 过滤条件最终通过 `TransformJooqConditionInterface.getConditionRemovePredicate(...)` 转成 JOOQ 的 `Condition` 对象，再拼进 SQL。

---

## 6. 步骤 ⑤：真正查数据库（ClickHouse）

文件：`fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/clickhouse/executor/ClickHouseSQLExecutor.java`

```java
public class ClickHouseSQLExecutor implements SQLExecutor<ClickHouseSQLExecutor> {
  // 入口
  public DataSet query(String sql) { return queryDirect(sql); }

  // 直接执行
  private DataSet queryDirect(String sql) throws SQLException {
    DataSet dataSet = new DataSet();
    jdbcConnection.query(sql, resultSet -> dataSet.set(transformResultSetToDataSetElement.handle(null, resultSet)));
    return dataSet;
  }
}
```

**新手解读**：
- 到这里，SQL 已经生成好，`ClickHouseSQLExecutor` 拿着这段 SQL 去 ClickHouse 执行。
- `jdbcConnection.query(sql, handler)`：JDBC 连接执行 SQL，把返回的 `ResultSet`（数据库结果集）转成统一的 `DataSet` 对象。
- `DataSet` 是统一的数据容器（行 + 列），后续所有服务都用它传数据。

---

## 7. 步骤 ⑥：结果怎么回到前端

文件：`fs-bi-stat/src/main/java/com/facishare/bi/stat/service/QueryReportService.java`（第 74 行方法尾部）

```java
QueryReportResult queryReportResult = StatResult2RptResult.doConvert(toJarQueryResult, queryReportDataArg);
```

- `JarQueryChartDataResultMapper.INSTANCE.toJarQueryResult(...)`：把查询内核的结果对象转成「公共实体包」里的对象（跨服务用的 DTO，用 MapStruct 自动生成转换代码）。
- `StatResult2RptResult.doConvert(...)`：再转成报表展示格式（表头字段、行数据、分页信息）。
- 最终 `QueryReportResult` 通过 `@ResponseBody` 变成 JSON 返回给前端。

**新手解读**：为什么要转两次？因为「查询内核内部用的对象」和「对外接口的对象」是两套，中间用 MapStruct（一个自动生成转换代码的工具）避免手写一堆 getter/setter 赋值。

---

## 8. 步骤 D：SQL 引擎 —— 其他服务也来查数据（跨服务走读）

> fs-bi 除了自己查数，还把「SQL 执行能力」做成服务给别的系统用（udf-report、dev-platform 都靠它）。

```
udf-report / dev-platform
   │ 用 SqlEngineClient（Retrofit HTTP 客户端）
   ▼
POST v1/sql_engine/{ei}/query_from_pg
   ▼
SqlEngineServiceImpl（fs-bi-sqlengine，JAX-RS 服务）
   ▼
RepositoryFacade.query("PG", sql)
   ├─ 灰度直连：QueryRepository.query(...)        ← 直接查
   └─ 默认：QueryRepository.queryCacheAble(...)   ← 带缓存查（SQL 做 key）
   ▼
PGSQLExecutor（真正执行 PG 的 SQL）
```

关键文件：
- 客户端契约：`fs-bi-client/src/main/java/com/facishare/bi/client/SqlEngineClient.java` —— 只声明接口，不写实现，Retrofit 根据注解自动生成 HTTP 调用代码。
- 服务端：`fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/service/impl/SqlEngineServiceImpl.java` —— `@Path("v1/sql_engine")`，每个方法对应一个执行类型（PG / SQL Server / 临时表 / 执行计划）。
- 门面：`fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/repository/RepositoryFacade.java` —— 判断是直连还是走缓存。
- 执行器：`fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/executor/PGSQLExecutor.java`。

**新手解读**：
- `@FRestApi("BI_SQLENGINE")` 是公司自研 REST 框架的注解，等价于「这个接口对应名叫 BI_SQLENGINE 的服务」，具体地址由注册中心/配置中心下发。
- `queryCacheAble` 会按 `企业id + SQL` 生成缓存 key，同样的 SQL 短时间重复查就直接返回缓存，省数据库压力。

---

## 9. 怎么验证我读懂了（实践建议）

1. **本地跑日志**：在 `QueryReportService.queryReportData` 和 `ClickHouseSQLExecutor.queryDirect` 各打一行日志，发一次查询，看日志顺序。
2. **断点跟读**：在 `RootFlowServiceImpl.goForward` 第 58 行打断点，用 IDE 的 Step Into 看 8 个阶段依次执行，重点观察 `support()` 返回 true 的节点。
3. **看 SQL**：日志里搜 `Preview SQL`（udf-report 会打印）或 `queryFilterChSql`，把生成的 SQL 复制到 ClickHouse 客户端里手动执行，比对结果。
4. **验证分层**：把 Controller 里的 Service 调用注释掉，会发现请求立刻报错——证明「控制器不碰数据库」是设计约束。

---

## 10. 新手 FAQ

| 问题 | 回答 |
| --- | --- |
| 为什么请求这么绕，不能直接在 Controller 里查库？ | 为了可维护：分层后每层职责单一，改数据库不影响接口，改业务逻辑不影响数据库，团队可并行开发 |
| ThreadLocal 是什么？ | 每个线程（可以理解为一个正在处理的请求）私有的存储空间，存「当前请求是谁」这类信息，用完必须清空 |
| easy-stat 是什么？ | fs-bi 自己研发的「易用统计」查询框架，把 SQL 生成过程拆成可插拔的流水线节点 |
| 为什么结果要转两次 DTO？ | 内部对象和对外对象解耦，避免外部接口变更影响内核；转换代码由 MapStruct 自动生成 |
| ClickHouse 和 PostgreSQL 各干嘛？ | PG 存配置类数据（报表、权限、元数据），CH 存统计数据（查询量大、追求快） |
