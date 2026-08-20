# fs-bi-crm-report 代码走读详解（新手向 · 超详细版）

> 配套文档：《fs-bi-crm-report-架构分析.md》的「十、代码走读路线」。本文把最核心的**报表数据查询链路**逐行讲透。
> 仓库根目录：`/Users/muqingji/code/serve/fs-bi-crm-report`；代码默认在 `fs-bi-crm-report-web/src/main/java` 下。

---

## 0. 读代码前，先认识几个概念（新手速查）

| 概念 | 一句话解释 |
| --- | --- |
| 门户 API | 面向外部（纷享 CRM 开放平台 FCP）的接口，前端/第三方系统通过这些接口拿数据 |
| Facade（门面） | 一个「大管家」服务，把多个小服务/小步骤组织起来完成一件事，调用方只面对它一个 |
| Repository（仓储） | 数据访问的门面：Service 不直接碰 Mapper，而是通过 Repository 拿数据 |
| HTTP RPC 客户端 | 用 HTTP 调用别的服务的接口。这里用 `@RestResource` 注解声明接口，框架自动生成调用代码 |
| @ApiUserInfo | 框架注解：自动从请求头解析出「当前用户」塞进方法参数，不用手写解析代码 |
| MyBatis | Java 的数据库访问框架，用 `@Select` 注解或 XML 写 SQL |

**这个仓库的特点**：它自己**不存统计数据的查询逻辑**，而是把「查询」转发给下游服务（udf-report / fs-bi / dev-platform），自己主要负责**报表元数据管理 + 展示层组装 + 订阅导出**。

---

## 1. 主链路总览

```
前端 / FCP 网关
   │ ① POST /api/v1/view/data/query
   ▼
ViewDataQueryApiController.query()          ← 控制器：接请求、拿用户信息
   ▼
ViewDataQueryFacadeService.query()          ← 门面：组装参数、决定走哪条路
   ├─ 先查本地库拿报表配置（RptViewRepository → RptViewMapper → PostgreSQL）
   ├─ 报表类型判断：是报表？统计图？大宽表？
   ▼
ViewDataQueryRepository.queryReportData()   ← 仓储：决定调哪个下游
   ▼
BIUDFResource.queryReportData()             ← HTTP RPC 客户端：转发到 udf-report
   ▼
udf-report /rptUdfViewDataController/queryReportData
   ▼（后续见《走读详解-fs-bi-udf-report.md》）
   ▼
结果回传 → Facade 适配成展示格式 → 返回前端
```

---

## 2. 步骤 ①：Controller —— 请求的「前台」

文件：`com/facishare/bi/portal/api/ViewDataQueryApiController.java`

```java
@Controller
@RequestMapping("/api/v1/view/data")
@ApiAccessLog                       // 切面：自动记录这次访问日志
public class ViewDataQueryApiController {

  @Autowired
  private ViewDataQueryFacadeService viewDataFacadeService;

  @ResponseBody
  @RequestMapping(value = "/query", method = RequestMethod.POST)
  public ApiResult<ViewDataQueryResult> query(
      @RequestBody ViewDataQueryArg arg,          // 前端传来的查询参数
      @ApiUserInfo UserInfo userInfo) {           // 框架自动注入当前用户
    ViewDataQueryResult viewDataQueryResult = viewDataFacadeService.query(userInfo, arg);
    return new ApiResult<>(viewDataQueryResult);  // 统一返回包装
  }
}
```

**新手解读**：
- 完整地址 = `/api/v1/view/data` + `/query` = `/api/v1/view/data/query`。
- `@ApiUserInfo UserInfo userInfo`：**不需要自己解析请求头**，框架会把当前用户（企业 id、员工 id、账号）填进这个参数。
- `ApiResult<T>` 是统一返回包装，一般长这样：`{ code: 0, msg: "success", data: {...} }`，方便前端统一处理。

---

## 3. 步骤 ②：Facade 门面 —— 业务的「大管家」

文件：`com/facishare/bi/portal/service/ViewDataQueryFacadeService.java`（方法 `query` 第 95 行）

```java
public ViewDataQueryResult query(UserInfo userInfo, ViewDataQueryArg arg) {
  // 3.1 把用户信息写进链路追踪上下文（排查问题时按用户追）
  TraceContext.get().setEa(userInfo.getEnterpriseAccount());
  TraceContext.get().setEi(String.valueOf(userInfo.getEnterpriseId()));
  TraceContext.get().setEmployeeId(String.valueOf(userInfo.getEmployeeId()));

  // 3.2 先查本地库：这个 viewId 是什么类型的报表？
  RptView rptView = viewQueryRepository.getRptView(userInfo, arg.getViewId());

  if (rptView != null) {
    // 情况一：是"报表"类型
    if (RptTypeEnum.RPT != RptTypeEnum.of(rptView.getRptType())) {
      throw new ApiUnimplementedException(...);   // 类型不对直接报错
    }
    // 3.3 把请求里的筛选条件与报表默认筛选条件合并
    List<FilterList> filterLists = bindRptFilterLists(userInfo, arg);

    // 3.4 组装查询参数对象
    QueryReportDataArg queryReportDataArg = new QueryReportDataArg();
    queryReportDataArg.setId(arg.getViewId());
    queryReportDataArg.setFilterList(filterLists);
    queryReportDataArg.setPageNumber(arg.getPageNumber());
    queryReportDataArg.setPageSize(arg.getPageSize());
    ...
    // 3.5 调用仓储，走下游查询
    QueryReportResult queryReportResult =
        viewDataQueryRepository.queryReportData(userInfo, queryReportDataArg);

    // 3.6 把下游返回的结果"翻译"成门户 API 的展示结构
    ViewDataQueryResult viewDataQueryResult = new ViewDataQueryResult();
    viewDataQueryResult.setPage(viewDataBeanMapper.toPage(queryReportResult.getPage()));
    viewDataQueryResult.setDisplayFields(viewDisplayFieldBeanMapper.toDisplayFields(...));
    viewDataQueryResult.setDataSet(viewDataBeanMapper.toDataSet(...));
    return viewDataQueryResult;
  } else {
    // 情况二：不是报表，可能是统计图 → 走另一条路（见走读路线 B）
    return queryViewData(userInfo, arg);
  }
}
```

**新手解读**：
- Facade 的职责就是**编排**：先查配置 → 拼参数 → 调下游 → 适配结果。它自己不做 SQL。
- `bindRptFilterLists`：前端可能只传了「筛选值」，但报表本身有「默认筛选器」。这段代码把两份合并：报表默认筛选项 + 前端覆盖的值。
- `viewDataBeanMapper` / `viewDisplayFieldBeanMapper` 是 MapStruct 生成的转换器，把下游返回的通用格式转成门户 API 的展示格式。

---

## 4. 步骤 ③：仓储 Repository —— 决定调哪个下游

文件：`com/facishare/bi/portal/repository/ViewDataQueryRepository.java`

```java
@Repository
public class ViewDataQueryRepository {
  @Autowired private BIDEVResource bidevResource;  // → dev-platform（拼表/大宽表）
  @Autowired private BIUDFResource biudfResource;  // → udf-report（自定义报表）
  @Autowired private FSBIResource  fsbiResource;   // → fs-bi（统计图）

  // 报表数据查询：转发给 udf-report
  public QueryReportResult queryReportData(UserInfo userInfo, QueryReportDataArg queryReportDataArg) {
    queryReportDataArg.setQuerySource(FromEnum.FUNCTION);   // 标记来源：函数调用
    return biudfResource.queryReportData(queryReportDataArg,
                                         RpcHeaderUtils.toHeaderMap(userInfo));
  }

  // 统计图查询：转发给 fs-bi
  public QueryChartDataResult queryChartData(QueryChartDataArg arg, UserInfo userInfo) {
    return fsbiResource.queryChartData(arg, RpcHeaderUtils.toHeaderMap(userInfo));
  }

  // 大宽表查询：转发给 dev-platform
  public QueryLwtResult queryLwtData(QueryLwtArg arg, UserInfo userInfo) {
    return bidevResource.queryLwtData(arg, RpcHeaderUtils.toHeaderMap(userInfo));
  }
}
```

**新手解读**：
- 这是**跨服务调用**的典型写法：本地只声明接口，真正执行在下游服务。
- `RpcHeaderUtils.toHeaderMap(userInfo)`：把用户信息转成 HTTP Header（如 `x-fs-enterprise-id`、`x-fs-employee-id`），下游服务靠这些 Header 知道「是谁在查」。
- `FromEnum.FUNCTION` 标记这次查询来源是「函数调用」，下游可以用它区分日志和统计。

---

## 5. 步骤 ④：HTTP RPC 客户端 —— 转发请求

文件：`com/facishare/bi/portal/rpc/BIUDFResource.java`

```java
@RestResource(value = "BI-UDF-REPORT", desc = "报表服务", contentType = "application/json")
public interface BIUDFResource {
  @POST(value = "/rptUdfViewDataController/queryReportData", desc = "查询自定义报表")
  QueryReportResult queryReportData(@Body QueryReportDataArg arg, @HeaderMap Map<String, String> var);
}
```

**新手解读**：
- 这个接口**没有实现类**。`@RestResource` + `@POST` 是公司自研 REST 框架的声明式写法：框架根据注解自动生成一个 HTTP 客户端 Bean。
- `@Body` = 请求体（JSON），`@HeaderMap` = 请求头。
- `value = "BI-UDF-REPORT"` 是下游服务的服务名，实际地址由注册中心/配置中心下发（所以代码里看不到 IP）。
- 你只需要记住：**调用 `biudfResource.queryReportData(...)` 等价于「向 udf-report 服务发一个 HTTP POST」**。

---

## 6. 步骤 ⑤：本地数据库访问（报表配置在 PostgreSQL）

这条是「纯本地」的例子，帮你看懂 MyBatis：

文件：`com/facishare/bi/dao/mapper/RptViewMapper.java`

```java
@Service
public interface RptViewMapper extends IBatchMapper<RptView>, ICrudPaginationMapper<RptView> {
  // 注解式 SQL：直接写在方法上
  @Select("select distinct ei from rpt_view where ei <> -1 and ei <> -2 union ...")
  List<String> getAllEi();

  @Select("select category_id from rpt_view where view_id = #{viewId} and (ei = ... or ei = #{ei}) and is_delete != 1")
  String getCategoryIdByViewId(@Param("viewId") String viewId, @Param("ei") int ei);
}
```

**新手解读**：
- MyBatis 的 Mapper 是一个**接口**，你只写方法签名 + SQL，MyBatis 在启动时自动生成实现类。
- `#{viewId}` 是参数占位符，MyBatis 会用「预编译」方式替换，**防止 SQL 注入**（永远不要用字符串拼接 SQL）。
- 还有对应的 XML 文件：`resources/mybatis/DynamicRptViewMapper.xml`，复杂 SQL 写在 XML 里（`<select>` 标签），接口方法名与 XML 的 id 对应。
- 数据源配置在 `resources/spring/spring-db-postgresql.xml`（业务库）和 `spring-db-clickhouse.xml`（统计库）。

调用链回顾：`ViewQueryRepository.getRptView()` → `RptViewRepository.getViewByID(viewId, ei)` → `RptViewMapper`（注解/XML SQL）→ PostgreSQL。

---

## 7. 走读路线 B/C/D：其他几条链路的速览

**统计图查询（B）**
```
POST /api/v1/view/data/queryMultiDimViewData
  → Facade.queryViewData()
  → viewQueryRepository.getStatView()          ← 本地查 stat_view 配置（PG）
  → viewDataQueryRepository.queryChartData()   ← FSBIResource → fs-bi 统计图内核
```

**大宽表查询（C）**
```
POST /api/v1/view/data/queryLwtViewData
  → viewDataQueryRepository.queryLwtData()     ← BIDEVResource → dev-platform /lwt/query
```

**订阅与调度（D）**
```
POST /api/v1/subscribe/...
  → SubscriptionController（portal/api/SubscriptionController.java）
  → ViewCategoryBatchSubscribeService（批量订阅）
  → SchRunService / SchRunRepository → SchRunMapper → PG
  → 推送：MailService（邮件）/ PushSessionService（Dubbo 企信）
```

**导出（E）**
```
BiRptExportController（midware/jobcenter/web/controller/）
  → ExportAllPermissionsService（导出权限校验）
  → FileService / StoneFileService（生成文件）
  → FilePackedService（Dubbo 打包）→ 下载
```

---

## 8. 怎么验证我读懂了（实践建议）

1. **看日志顺序**：发一次 `/api/v1/view/data/query`，日志里应该依次出现 Facade 进入 → 下游调用 → 结果返回。
2. **断点跟读**：在 `ViewDataQueryFacadeService.query` 第 95 行打断点，Step Into 依次看：本地查库（getRptView）→ 拼参数 → Repository → BIUDFResource。
3. **抓下游请求**：在 `BIUDFResource` 调用处打断点，看 `queryReportDataArg` 里 id、filterList 是怎么拼出来的。
4. **验证下游**：把 udf-report 服务停掉，再发请求，会发现这里报「连接失败」——证明查询确实转发到了下游。

---

## 9. 新手 FAQ

| 问题 | 回答 |
| --- | --- |
| 为什么这个服务不自己查统计数据？ | 职责划分：报表查询能力统一收口在 udf-report / fs-bi，crm-report 只做「门户层」，避免重复实现查询逻辑 |
| `@RestResource` 接口没有实现类怎么工作？ | 框架在启动时根据注解自动生成 HTTP 客户端实现（类似 Feign），所以你能直接 `@Autowired` |
| Mapper 接口也是没实现类，怎么工作？ | 同理，MyBatis 启动时动态生成实现类（基于 JDK 动态代理） |
| `@ApiUserInfo` 的用户信息从哪来？ | 网关（FCP）在请求头里放了用户信息，框架拦截器解析后注入 |
| 为什么本地也要查库？ | 因为「这个 viewId 是什么报表、它的默认筛选器是什么」这些配置存在本地 PG 里，查询前必须先知道 |
