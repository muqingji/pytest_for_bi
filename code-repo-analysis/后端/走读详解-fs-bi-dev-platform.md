# fs-bi-dev-platform 代码走读详解（新手向 · 超详细版）

> 配套文档：《fs-bi-dev-platform-架构分析.md》的「十、代码走读路线」。本文把最核心的**大宽表（LWT）查询链路**逐行讲透。
> 仓库根目录：`/Users/muqingji/code/serve/fs-bi-dev-platform`；代码默认在 `fs-bi-dev-web/src/main/java` 下。

---

## 0. 读代码前，先认识几个概念（新手速查）

| 概念 | 一句话解释 |
| --- | --- |
| 大宽表（LWT） | 把多张报表/多张表的数据「拼」成一张宽表来展示，是 BI 自助建模的核心能力 |
| 数据源（DataSource） | 宽表里的一个「列来源」，可能是某张报表、某个统计图、某张透视表 |
| 注解注入用户 | `@FSUserInfo UserInfo`：框架从请求头解析用户直接塞进参数 |
| 灰度开关（GrayManager） | 按企业/用户百分比放量的开关，新功能先让一小部分企业用 |
| MQ 异步 | 把任务丢进消息队列，后台消费执行，请求线程先返回（用于大查询） |
| Sentinel 限流 | 保护服务：同一资源超过阈值就拒绝，防止被压垮 |

**这个仓库的特点**：dev-platform 负责「宽表怎么拼」，它自己不做底层取数，而是把每个数据源再转发给 udf-report / fs-bi 去查，最后在内存里把结果拼起来。

---

## 1. 主链路总览

```
前端 / crm-report（BIDEVResource）
   │ ① POST /lwt/query（QueryLwtArg：宽表 id、筛选、页码）
   ▼
LwtController.query()                       ← 控制器：限流/降级/用户注入
   ├─ 灰度判断：同步查 or 异步查（MQ）
   ▼
LargeWideTableService.doQuery()             ← 服务：宽表组装
   ▼
LargeWideTableService.queryLwtResult()      ← 核心：解析宽表配置
   ▼
processDataSource()                         ← 按数据源类型分派：
   ├─ viewType=1（报表）   → ReportService  → HTTP → udf-report
   ├─ viewType=2（透视表） → PivotTableService
   └─ 其他（统计图）       → StatService    → HTTP → fs-bi
   ▼
结果内存拼接（跨表 join、计算字段、小计、格式化）
   ▼
返回 QueryLwtResult
```

---

## 2. 步骤 ①：Controller —— 入口与防护

文件：`com/facishare/bi/dev/web/controller/LwtController.java`（方法 `query` 第 109 行）

```java
@Slf4j
@Controller
@RequestMapping("/lwt")
public class LwtController {

  @RequestMapping(value = "/query", method = RequestMethod.POST)
  @ResponseBody
  @SentinelLimit(resource = "lwtQueryData")          // 限流：同名资源统一计数
  @TimeoutDegradation                                 // 超时降级
  @I18NTranslation(serviceType = "query")             // 返回结果做多语言翻译
  public QueryLwtResult query(@FSUserInfo UserInfo userInfo,
                              @RequestBody QueryLwtArg queryLwtArg,
                              @FSOuterUserInfo OuterUserInfo outerUserInfo) throws Exception {
    adjustUserInfoForEM6H(userInfo, outerUserInfo);   // 外部企业兼容处理

    // 强制刷新判断
    if (MyObjectConfigManager.isForceRefresh(...)) { queryLwtArg.setRefresh(1); }

    // 灰度开关：lwtSync2async 开启的企业走"异步查询"
    if (!GrayManager.isAllow("lwtSync2async", String.valueOf(userInfo.getEnterpriseId()))) {
      return originQuery(userInfo, queryLwtArg, outerUserInfo);   // 同步老路
    }
    // 异步新路：生成 reqId → 发 MQ → 消费者查询 → 前端轮询取结果
    String reqId = lwtQueryCache.getReqId(userInfo, outerUserInfo, queryLwtArg);
    ReqIdContext.setValue(reqId);
    ...
  }
}
```

**新手解读**：
- 注解从上到下是「保护罩」：`@SentinelLimit` 限流防打爆、`@TimeoutDegradation` 超时兜底、`@I18NTranslation` 结果翻译。
- `@FSUserInfo` 和 `@FSOuterUserInfo` 是 CEP 插件注解：一个拿「内部用户」，一个拿「外部企业用户」（比如通过开放平台来的第三方）。
- **灰度**是这套系统里最常见的工程手法：新功能先给 1% 企业用，观察没问题再放量。
- 异步路径：大查询不让请求线程干等，而是发到 MQ（`LwtQueryProducer` → `LwtQueryConsumer` 消费），前端之后拿着 `reqId` 来轮询取结果。

---

## 3. 步骤 ②：Service —— 宽表组装

文件：`com/facishare/bi/dev/web/service/LargeWideTableService.java`

```java
// 第 848 行：简化版入口
public QueryLwtResult doQuery(QueryModel queryModel, ...) {
  // 从 QueryModel 里拆出：宽表参数、字段、用户、页号页大小、各种筛选器
  return doQuery(lwtArgs, fields, ei, uid, ea, outerUserInfo, opType,
                 pageNumber, pageSize, asyncQuery, myGlobalFilter, linkFilters,
                 customFilter, localFilter, queryLwtArg);
}

// 第 921 行
public QueryLwtResult doQuery(LargeWideTableArgs lwtArgs, ...) {
  handleSpecailFilterByFunction(lwtArgs, ei, uid, ea);   // 特殊筛选器（执行函数）
  handleSpecialFilterField(lwtArgs, ei, ea);             // 特殊过滤表达式
  QueryLwtResult queryLwtResult = queryLwtResult(...);   // 核心组装
  return queryLwtResult;
}
```

**新手解读**：
- 这一层主要是**参数的层层透传**（Java 里常见：方法参数很多，用对象打包传递）。
- `handleSpecailFilterByFunction`：某些企业的筛选器是「动态函数」——比如「许继」企业筛选器要先调用一个函数拿到部门列表，再拿这个列表去过滤。它通过 `funcService.excuteFunction(...)` 执行函数。
- `handleSpecialFilterField`：处理形如 `$dfname["字段A"] > $dfname["字段B"]` 的特殊表达式。

---

## 4. 步骤 ③：核心组装 queryLwtResult

文件：`com/facishare/bi/dev/web/service/LargeWideTableService.java`（第 1043 行）

```java
public QueryLwtResult queryLwtResult(LargeWideTableArgs lwtArgs, List<Header> fields, ...) {
  // 4.1 处理下游字段（宽表里有"下游数据"列时）
  handleDownStreamFields(lwtArgs, outerUserInfo);

  // 4.2 区分"普通列"和"度量列"（有聚合或计算字段的）
  for (Field field : lwtArgs.getDisplayFields()) {
    if (有聚合 || 是计算字段) { rawMeasureDisplayFields.add(field); }
    rawDisplayFields.add(field);
  }

  // 4.3 下钻处理（用户点击某个值下钻时，要替换/增加下钻字段）
  if (lwtArgs.getDrillInfo() != null) { ... statService.convertToField(...) ... }

  // 4.4 ★关键：逐个数据源去取数
  processDataSource(lwtArgs, ei, uid, ea, ..., dfValuesMaps, dfDisplayColumnsMap, ...);

  // 4.5 结果组装：跨表拼接、序号、小计、计算字段、格式化
  if (isCrossJoinTable) { handleCrossJoinTableFields(...); }
  ...
}
```

**新手解读**：
- `processDataSource` 是灵魂：一个宽表由多个「数据源」组成，每个数据源都要去查一遍数据，结果放在 `dfValuesMaps`（按数据源 key 存值）和 `dfDisplayColumnsMap`（按数据源存列头）。
- 取数可能很慢，所以用 `FutureTask` + 线程池**并行**取所有数据源，全部完成后汇总（异步场景）。

---

## 5. 步骤 ④：数据源分派 processDataSource

文件：`com/facishare/bi/dev/web/service/LargeWideTableService.java`（第 2534 行）

```java
private void processDataSource(LargeWideTableArgs lwtArgs, ...) {
  for (DataSource ds : lwtArgs.getDataSources()) {
    FutureTask<DfDataSource> futureTask = new FutureTask<>(() -> {
      if ("1".equalsIgnoreCase(ds.getViewType())) {
        // 报表数据源 → ReportService（内部 HTTP 调 udf-report）
        return reportService.getReportDataSourceWithSimpleData(ei, uid, ea, outerUserInfo, ...);
      } else if ("2".equalsIgnoreCase(ds.getViewType())) {
        // 透视表数据源 → PivotTableService
        return pivotTableService.getReportDataSource(...);
      } else {
        // 统计图数据源 → StatService（内部 HTTP 调 fs-bi）
        return statService.getStatDataSource(...);
      }
    });
    futureTaskList.add(futureTask);
    taskExecutor.submit(futureTask);   // 并行执行
  }
  // 等待所有数据源结果，按 key 放入 dfValuesMaps / dfDisplayColumnsMap
}
```

**新手解读**：
- `viewType` 是宽表配置里每个数据源的「类型」：1=报表、2=透视表、其他=统计图。
- 每个数据源**独立查询**（报表查报表、统计图查统计图），查询结果统一成 `DfDataSource` 结构后汇总。
- 这就是「宽表 = 多路取数 + 内存拼接」的直观体现。

---

## 6. 步骤 ⑤：下游 HTTP 调用（ReportService / StatService）

文件：`com/facishare/bi/dev/web/service/ReportService.java`（第 158 行）

```java
public QueryReportDataResult queryReportData(int ei, int uid, String ea, QueryReportDataArg arg) {
  // udfApiHost 由配置中心下发，默认 http://127.0.0.1:31745/
  String postUrl = udfApiHost + "rptUdfViewDataController/queryReportData";
  String jsonArg = JSON.toJSONString(arg);
  String result = httpUtils.post(postUrl, jsonArg, ei, uid, ea);   // OkHttp 发 POST
  return JSON.parseObject(result, QueryReportDataResult.class);    // JSON 反序列化
}
```

文件：`com/facishare/bi/dev/web/service/StatService.java`（第 294 行附近）——同样的模式，调用 fs-bi 的统计图查询接口。

文件：`com/facishare/bi/dev/web/util/HttpUtils.java` —— 统一发 HTTP 的地方：

```java
public static Map<String, String> constructHttpHeader(int ei, int uid, String ea, OuterUserInfo outerUserInfo) {
  headerMap.put("x-tenant-id", ...);
  headerMap.put("x-fs-ei", ...);
  headerMap.put("X-fs-Employee-Id", ...);
  headerMap.put("x-fs-locale", ...);      // 语言
  if (outerUserInfo != null) { headerMap.put("x-out-tenant-id", ...); ... }  // 外部企业
  return headerMap;
}
```

**新手解读**：
- 这里用的是**手写 HTTP 调用**（OkHttp），和 crm-report 的 `@RestResource` 声明式不同——两种风格都是常见的跨服务调用方式。
- 关键是 Header 要带全：企业 id、员工 id、语言、外部企业信息。下游服务靠这些 Header 识别「谁在查、查哪个企业、要什么语言」。

---

## 7. 走读路线 B/C/D：其他链路速览

**宽表保存（B）**
```
POST /lwt/m/...（ManagerController）
  → SaveLwtService
  → Mapper：LargeWideTableConfigMapper / LargeWideTableDataSourceMapper（PG）
  → 宽表定义落库
```

**导出（C）**
```
POST /lwt/exportToExcel、/innerExportLwtData
  → 权限校验（FunctionPermissionService / PermissionUtil）
  → LargeWideTableReportExportService / AsyncQueryLwtSerivce 取数
  → 生成 Excel（opencsv / POI）→ FileService
```

**SQL 引擎 / 外部 LWT 服务（D，备用）**
```
SqlEngineService.query()：HTTP → fs-bi-sqlengine /api/v1/sql_engine/{ei}/query_from_pg（当前未注入使用）
LwtService.doQuery()：HTTP → 外部 lwtServiceHost /lwt/query（默认 172.31.100.247:10091）
```

---

## 8. 怎么验证我读懂了（实践建议）

1. **断点跟读**：在 `LwtController.query`（第 109 行）打断点，Step Into 到 `LargeWideTableService.processDataSource`（第 2534 行），看它怎么按 `viewType` 分派。
2. **看并行取数**：在 `futureTaskList` 循环处观察线程名（`taskExecutor` 线程池），确认多个数据源是并行的。
3. **抓下游请求**：在 `ReportService.queryReportData` 的 `httpUtils.post` 打断点，看 URL 和 Header，理解「转发给 udf-report」。
4. **切灰度验证**：用测试企业关掉 `lwtSync2async` 灰度，请求会走 `originQuery` 同步路径，对比异步路径的区别。

---

## 9. 新手 FAQ

| 问题 | 回答 |
| --- | --- |
| 宽表查询为什么这么慢/复杂？ | 因为一个宽表可能要查多个数据源再拼接，天然比单报表重；所以才有异步 + 并行取数 |
| `@FSUserInfo` 和 `@ApiUserInfo` 有什么区别？ | 框架不同：`@FSUserInfo` 是 CEP 插件（纷享统一用户体系），`@ApiUserInfo` 是门户 API 框架的注解，作用类似 |
| 灰度开关怎么理解？ | 类似「开关 + 名单」：`GrayManager.isAllow(开关名, 企业id)` 返回 true 才走新逻辑 |
| 为什么有的下游用 `@RestResource`，这里用手写 HTTP？ | 两个仓库用了不同年代的集成方式；手写 HTTP 灵活但易错（Header 要自己维护） |
| 异步查询的 reqId 有什么用？ | 前端拿着 reqId 轮询 `loadResponse`，后端靠它找到对应结果，避免大查询阻塞请求线程 |
