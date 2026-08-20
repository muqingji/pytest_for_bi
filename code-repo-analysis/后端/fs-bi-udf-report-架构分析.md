# fs-bi-udf-report 源码架构分析报告

- 仓库地址：`git@git.firstshare.cn:dataplatform/fs-bi-udf-report.git`
- 分析对象：本地克隆 `/Users/muqingji/code/serve/fs-bi-udf-report`

---

## 一、项目概况

- **项目简介**：纷享销客 BI 的**自定义对象报表服务（UDF Report）**，围绕 CRM「自定义对象（UDF, User Defined Field/Object）」提供报表模板、视图、透视表、数据查询与校验能力，是 CRM 自定义对象场景的报表查询引擎。
- **业务领域**：SaaS BI（商业智能），CRM 自定义对象数据分析。
- **项目类型**：**多模块单体**。`fs-bi-udf-report-web`（WAR，核心）+ `fs-bi-udf-report-api`（JAR，公共接口）。
- **技术栈**：
  - 语言：Java 21（`maven.compiler.source/target=21`）
  - 构建：Maven（`fs-bi-udf-report` 根工程）
  - 框架：Spring MVC（XML 装配 + CEP 插件）、MyBatis（PostgreSQL + ClickHouse）、Dubbo、MapStruct、Lombok、fastjson、Sentinel（fxiaoke 封装）、HikariCP 连接池
  - 运行环境：Tomcat（WAR，ContextPath `/bi`，本地端口 7083）、JDK 21
- **打包/部署方式**：`web` 以 `war` 部署；`api` 为 `jar`。
- **容器化**：未发现 Dockerfile / K8s 文件，传统 Tomcat 部署（README 提到 tomcat7 插件本地调试）。

## 二、整体系统架构

### 1. 架构模式与分层
- **控制层**：`com.fxiaoke.bi.crm.api.controller.*`（核心 UDF 报表接口）+ `com.fxiaoke.bi.crm.adapter.controller.*`（从 fs-bi-crm-report-web 迁移来的适配接口）
- **业务层**：`service`（`UDFRptReportDataService`、`UDFPivotReportDataService`、`UDFRptConcurrentQueryService`、`sqlengine/*`、`rptvalidate/*` 等）
- **数据层**：`postgresql`（PG Mapper）、`clickhouse`（CH JDBC/Service）、`repository`、`sqlroute`（SQL 路由）
- **基础设施**：`cache`、`context`、`aop`、`common`（含 `globalFilter` 数据权限过滤器）、`utils`、`jsonbuilder`、`jsonresolver`、`mapstruct`、`format`、`license`、`mq`、`rpc`、`metadata`、`profile`、`rest`
- **横切**：CEP 用户上下文、License 校验（`RptQueryLicenseService`）、异常处理

### 2. 模块拆分
| 模块 | 职责 |
| --- | --- |
| `fs-bi-udf-report-web` | UDF 报表查询/透视表/模板/视图/校验/异步查询（WAR，核心） |
| `fs-bi-udf-report-api` | 公共接口（如 `CalculateValidationService` 计算校验） |

### 3. 外部依赖服务
- 权限：`PermissionService`（组织架构 5.7）、企业配置 `EnterpriseConfigService`
- 元数据：原 Dubbo 引用（`UdfObjService`/`UdfObjFieldService`/`UdfObjRelationService`）已注释，改由本地 metadata 访问
- 基础设施：PostgreSQL（业务/元数据）、ClickHouse（数据）、Redis（缓存）、MQ、CMS 配置中心、License 客户端
- **数据执行下游（关键）**：`rpc/QueryServiceAdapter.queryFromNewDw(sql, QueryContext)` → `fs-bi-client SqlEngineClient`（`@FRestApi("BI_SQLENGINE")`）→ fs-bi-sqlengine `SqlEngineServiceImpl`（PG/SQL Server 查询）；ClickHouse 另可走 `clickhouse/service/CHJDBCService.queryDataSet(sql, ei)` 直连
- 适配接口来源：SalesBriefData / SalesClueData / SaleProcessAnalysis（销售简报、线索、过程分析数据）

### 4. 请求整体流转链路
```
FCP 网关 / BI 前端
   → fs-bi-udf-report-web（Tomcat /bi）
   → Controller（RptUdfDataController / RptUdfViewCreateController / RptUdfTemplateCreateController 等）
   → CEP 用户上下文 + License 校验
   → service（UDFRptReportDataService / UDFPivotReportDataService）
   → sqlengine / sqlroute（SQL 生成与路由）
   → ClickHouse（数据查询）/ PostgreSQL（元数据）
   → 结果格式化（format / jsonbuilder）返回
```

## 三、目录结构详细解析

```
fs-bi-udf-report/
├── pom.xml / README.md / AGENTS.md / sonar-project.properties
├── scripts/ specs/
├── fs-bi-udf-report-web/
│   └── src/main/
│       ├── java/com/fxiaoke/bi/crm/
│       │   ├── api/controller/     # 核心接口：RptUdfDataController、RptUdfDataAsyncController、
│       │   │                       #   RptUdfViewCreate/Edit/Search/Validate、RptUdfTemplateCreate、
│       │   │                       #   RptUdfQueryTest、CrossObjectFiltering、UserProfile、TenantProfile、
│       │   │                       #   FunctionPermission、BackdoorController、SampleController、IndexController
│       │   ├── adapter/controller/ # 迁移自 crm-report 的适配接口（SalesBriefData、SalesClueData、SaleProcessAnalysis、ProviderForFeed）
│       │   ├── sqlengine/          # SQL 引擎：UDFObjCondService、PreObjCondService、ViewObjectRelationService、
│       │   │                       #   SQLEngine.query(GenericObject, displayFields)（第 126 行）
│       │   │                       #   SQLAssembler / NewSqlAssembler / ExtSqlAssembler（SQL 组装）
│       │   ├── rpc/               # QueryServiceAdapter（queryFromNewDw → SqlEngineClient）
│       │   │                       #   ObjTreeFieldService、df2sql（日期过滤解析）
│       │   ├── sqlroute/           # SQL 路由
│       │   ├── rptvalidate/        # 报表校验
│       │   ├── clickhouse/         # ClickHouse JDBC/服务（CHJDBCService）
│       │   ├── postgresql/ repository/ metadata/  # PG 数据访问与元数据
│       │   ├── cache/ license/ mq/ rpc/ rpc 相关   # 缓存、许可证、消息、RPC
│       │   ├── profile/            # 用户/租户画像（UserProfileService、TenantProfileService）
│       │   ├── format/             # 数值格式化（NumericFormattingService）
│       │   ├── common/globalFilter/ # 数据权限过滤器（本人/部门/下属/全部）
│       │   ├── dashboard/ downstream/ outenterprise/ auxservice/ reconciliation/ plugin/ aop/
│       │   ├── mapstruct/ jsonbuilder/ jsonresolver/ utils/ context/
│       │   └── rest/               # REST 相关
│       └── resources/
│           ├── application.properties（process.name=fs-bi-udf-report、Hikari、Sentinel）
│           ├── spring/spring-*.xml（db/db-system/cms/dubbo/cache）
│           └── webapp/WEB-INF/web.xml、spring-mvc.xml
└── fs-bi-udf-report-api/          # 公共接口（CalculateValidationService）
```

## 四、代码模块详细构成

### 1. 核心业务模块
- **UDF 报表数据查询**：`RptUdfDataController`（`/rptUdfViewDataController`）：
  - `queryReportDataMerge`（合并查询）、`queryPivotReportData`（透视表查询）、`queryPivotReportDataAndUpload`（查询并上传）、`batchUpdateFieldConfig`、`backstageQueryPivotReportData` / `backstageQueryReportData` / `backstageQueryReportDataByPage`（后台分页查询）、`innerQueryPivotReportData`（内部调用）、`getViewStopEmpMap`（停用员工映射）
  - 服务：`UDFRptReportDataService`、`UDFPivotReportDataService`、`UDFRptConcurrentQueryService`（并发查询）、`MultiCurrencyService`（多币种）、`FileService`
- **异步查询**：`RptUdfDataAsyncController`（异步提交/取结果）
- **视图/模板**：`RptUdfViewCreateController`、`RptUdfViewEditController`、`RptUdfViewSearchController`、`RptUdfViewValidateController`、`RptUdfTemplateCreateController`、`RptUdfQueryTestController`
- **跨对象过滤**：`CrossObjectFilteringController`（对象关系过滤）
- **SQL 引擎**：`UDFObjCondService` / `PreObjCondService`（UDF/预置对象条件）、`ViewObjectRelationService`（视图对象关系）、`ObjTreeFieldService`（对象树字段）、`df2sql/filter/DateFilterParserService`
- **校验**：`rptvalidate/*` + api 模块 `CalculateValidationService`
- **画像**：`UserProfileService` / `TenantProfileService`（用户/租户画像）
- **适配（迁移接口）**：`SalesBriefDataController`、`SalesClueDataController`、`SaleProcessAnalysisController`、`ProviderForFeedRestController`（Feed 提供方）
- **其他**：`dashboard`、`downstream`（下游处理）、`outenterprise`（外企数据）、`reconciliation`（对账）、`auxservice`、`format`（数值格式化）、`license`（`RptQueryLicenseService`）

### 2. 公共基础模块
- `common`：`globalFilter`（`ParseMeService`、`ParseOwnDeptService`、`ParseOwnSubEmpService`、`ParseAllService`）、`FlowStageService`、`CacheKeyService`
- `cache`：缓存键与缓存封装；`context`：请求上下文；`aop`：切面
- `mapstruct`：DTO 映射；`jsonbuilder` / `jsonresolver`：结果 JSON 构建与解析
- `utils`：通用工具；`exception` 体系

### 3. 数据层设计
- **PostgreSQL**：UDF 元数据、报表模板/视图配置（`postgresql` + `repository`，MyBatis）
- **ClickHouse**：报表数据明细/聚合（`CHJDBCService` + clickhouse Mapper）
- **Redis**：缓存（`cache`）；**MQ**：异步消息；**CMS**：配置中心
- **SQL 路由**：`sqlroute` 根据场景路由到 PG/CH

### 4. 权限、认证、鉴权
- 认证：CEP 插件注入用户/企业上下文（README 说明测试时在 Header 放 `x-fs-employee-id`、`x-fs-enterprise-account`、`x-fs-enterprise-id`）
- 数据权限：`common/globalFilter` 员工/部门/下属/全部解析 + `PermissionService`（组织架构 5.7）
- 功能权限：`FunctionPermissionController`、`FunctionPermissionService`
- License：`RptQueryLicenseService`（报表查询许可证校验）

## 五、用到的全部框架 & 第三方组件清单

| 组件 | 作用 |
| --- | --- |
| Spring MVC / Spring | Web 层与 IoC（XML 装配 + CEP 插件） |
| MyBatis | 持久层（PostgreSQL） |
| ClickHouse JDBC | 分析数据访问（CHJDBCService） |
| Dubbo | 服务 RPC（组织架构/权限等） |
| MapStruct 1.5 | DTO 转换 |
| HikariCP | 连接池（`connection-pool=hikari`） |
| Sentinel（fxiaoke 封装） | 限流/参数流控/降级 |
| fastjson | JSON 序列化 |
| Lombok | 样板代码 |
| 内部 SDK | fs-cep-spring-plugin、license-client、fs-bi-common-entities、fs-enterprise-id-account-converter、gray-release |

## 六、核心业务流程拆解

### 1. UDF 报表数据查询（核心）
```
POST /rptUdfViewDataController/queryReportDataMerge
  → RptUdfDataController
  → 上下文组装（CEP 用户/企业 + License 校验 RptQueryLicenseService）
  → UDFRptReportDataService / UDFPivotReportDataService
      → sqlengine（UDFObjCondService 条件构建 + df2sql 过滤解析）
      → sqlroute 路由（PG/CH）
      → ClickHouse/PostgreSQL 查询
  → 结果处理（format 数值格式化、多币种 MultiCurrencyService、停用员工过滤）
  → 返回/上传（FileService）
```

### 2. 透视表查询与上传
```
queryPivotReportData → 透视表 SQL（UDFPivotReportDataService）→ 数据查询
  → queryPivotReportDataAndUpload：查询结果写文件并上传（FileService）
```

### 3. 后台分页查询
```
backstageQueryReportDataByPage
  → 分页参数 → 同查询内核 → 分页结果返回（后台运营场景）
```

### 4. 视图/模板创建校验
```
RptUdfViewCreateController / RptUdfTemplateCreateController
  → ViewObjectRelationService（对象关系）→ ObjTreeFieldService（字段树）
  → RptUdfViewValidateController / rptvalidate（校验视图配置）
  → 保存元数据（PostgreSQL）
```

## 七、配置与环境

- **配置类型**：`application.properties`（`process.name=fs-bi-udf-report`、`process.profile=fstest`、`spring.profiles.active=fstest`、Hikari 参数、`slow.threshold=500`、Sentinel 规则开关）
- **多环境**：CMS 配置中心下发；`spring-cms.xml` 加载；本地 profile `fstest`
- **Sentinel**：参数流控启用（`sentinel-global-param-flow-rule-fs-bi-udf-report`），其余规则默认关闭
- **本地调试**：tomcat7 插件，ContextPath `/bi`，`http://localhost:7083/bi`；测试 Header 注入用户/企业信息
- **连接池**：HikariCP（connectionTimeout 30s、leakDetectionThreshold 30s）

## 八、项目优缺点 & 风险点

**优点**
- 与 fs-bi-crm-report 的职责切分清晰（自定义对象场景独立成服务），适配控制器机制支持接口平滑迁移
- SQL 引擎/路由/校验分层完整，支持透视表、合并查询、异步、上传等丰富查询形态
- 数据权限过滤器与 License 校验体系完善

**现存问题/技术债务**
- 原 Dubbo 元数据引用（UdfObjService 等）被注释，元数据访问方式重构后需确认兼容性
- `BackdoorController`（后门接口）存在安全风险，需确认生产是否暴露与鉴权
- `SampleController` 示例接口保留在 main 代码
- README 为历史模板（含失效百度网盘图片、示例接口命名不正式），文档老化
- 适配接口（Sales*/ProviderForFeed）与核心接口同仓共存，接口面偏宽

**接手改造注意事项**
- 查询链路改动需回归：合并查询、透视表、后台分页、异步、上传五类入口
- 修改 sqlengine/sqlroute 时注意 PG/CH 双库路由边界
- 涉及数据权限过滤器时按 AGENTS.md 补充上下文差异测试

## 九、需要补充核查的内容

- [ ] `BackdoorController` 的生产暴露情况与安全防护（重点核查）
- [ ] 元数据访问重构后的实际来源（本地 metadata 还是 fs-bi 的 Dubbo 接口）
- [ ] `MultiCurrencyService` 多币种换算的数据来源与口径
- [ ] 生产环境 PG/CH 数据源、Redis、MQ、Sentinel 规则中心配置
- [ ] 数据库 DDL 与 UDF 元数据模型
- [ ] 部署拓扑与网关路由（`/bi/rptUdfViewDataController` 对外暴露面）
- [ ] 容器化 / CI 流水线配置
- [ ] `fs-bi-udf-report-api` 中 `CalculateValidationService` 的完整契约

---

## 十、代码走读路线（API → 数据层 / 下游服务，最完整力度）

> 文件路径均相对仓库根 `/Users/muqingji/code/serve/fs-bi-udf-report`（默认在 `fs-bi-udf-report-web/src/main/java` 下）。

### 走读路线 A：自定义报表数据查询（核心链路）

```
前端 / crm-report（BIUDFResource）
  │ POST /rptUdfViewDataController/queryReportDataMerge（QueryReportDataMergeArg）
  ▼
① Controller 层
  com/fxiaoke/bi/crm/api/controller/RptUdfDataController.java
  └─ queryReportDataMerge()（第 175 行）
       ├─ 注解：@SentinelLimit(resource="queryReportDataMerge")、@TimeoutDegradation
       ├─ @FSUserInfo / @FSOuterUserInfo 注入用户
       └─ queryReportDataMergeService.queryReportDataMerge(userInfo, arg, outerUserInfo)
            └─ 内部逐视图调用 queryReportDataForMerge()（第 182 行，@I18NTranslation）
                 → queryReportData()（第 615 行）
                      ├─ 校验 UserInfo / BIObjectConfigManager.isForceRefresh 强刷
                      └─ originQueryReportData()（第 740 行）
                           → udfRptReportDataService.getReportDataResult(userInfo, arg)

② 报表数据服务层
  com/fxiaoke/bi/crm/jsonbuilder/service/UDFRptReportDataService.java
  └─ getReportDataResult()（第 1702 行）
       ├─ udfDisplayFieldService.fillOwnerDisplayField()：数据负责人字段（掩码/权限）
       ├─ 外部企业判断 OutEnterpriseUtil.isDownstreamEnterprise()
       ├─ SchemaIndependentUtils.allowSchemaIndependent()：schema 隔离企业
       ├─ multiCurrencyService.multiCurrencyHandle()：多币种（原币字段补全）
       ├─ calculateFieldService.analysisAndFillCalcSubItems()：BI 计算字段解析
       ├─ customCalcFieldService.handleCustomCalcFieldDuplicationAndSummation()：计算字段去重求和
       ├─ checkOrGetLayout()：报表布局
       ├─ json2DFHandler.cvtQRDA2GO(userInfo, arg)：QueryReportDataArg → GenericObject（jsonbuilder）
       ├─ sqlEngine.query(genericObject, displayFields)   ★进入 SQL 引擎（第 1757 行）
       ├─ 结果处理：removeDependIdFieldValue / 主键列过滤 / CustomCalcFieldUtils 求和 / encryptDataIfNeeded
       └─ I18NTransformationUtil.transformDataSet + formatDisplayFieldValues（i18n 与数值格式化）

③ SQL 引擎（SQL 组装 + 执行分派）
  com/fxiaoke/bi/crm/sqlengine/SQLEngine.java
  └─ query(GenericObject, List<DisplayField>)（第 126 行）
       ├─ 组装 SQL：SQLAssembler / NewSqlAssembler / ExtSqlAssembler（sqlengine 包）
       ├─ 元数据处理：SelectHandler / GroupByHandler / OrderByHandler（sqlengine/metadata/sqlhandler）
       ├─ 生成 QueryData 列表（含 countSql / 分页 / 明细）
       └─ 执行（按场景）：
            ├─ asyncQueryTask.query(sqls, userInfo)（第 446 行）★批量异步查询
            │    └─ AsyncQueryTask（com/fxiaoke/bi/crm/sqlroute/AsyncQueryTask.java）
            │         └─ queryService.queryFromNewDw(sql, QueryContext)（FutureTask 并发）
            │              → QueryServiceAdapter.queryFromNewDw（com/fxiaoke/bi/crm/rpc/QueryServiceAdapter.java:46）
            │                   ├─ clearCache=1 时删除 Redis 查询缓存（queryRedisCache/biCacheRedis）
            │                   └─ sqlEngineClient（com.facishare.bi.client.SqlEngineClient，@FRestApi("BI_SQLENGINE")）
            │                        → fs-bi-sqlengine SqlEngineServiceImpl（PG/MS，见《fs-bi-架构分析.md》走读路线 D）
            ├─ 直连 ClickHouse：CHJDBCService.queryDataSet(sql, ei)
            │    （com/fxiaoke/bi/crm/clickhouse/service/CHJDBCService.java:44）
            └─ queryResultHandler.handle(...)（第 253 行）→ QueryReportDataResult
```

### 走读路线 B：透视表查询

```
POST /rptUdfViewDataController/queryPivotReportData（第 222 行）
  → originQueryPivotReportData()（第 336 行）
  → udfPivotReportDataService（UDFPivotReportDataService，jsonbuilder/service）
  → 复用 SQLEngine 组装透视 SQL（pivot_detail_SQL 等）
  → asyncQueryTask / CHJDBCService 执行 → 透视结果
  （queryPivotReportDataAndUpload 第 379 行：结果写文件上传 FileService）
```

### 走读路线 C：异步查询（大结果集）

```
发起：sendQueryRequest(userInfo, arg)（UDFRptReportDataService 第 2440 行）
  → AsyncSendResult（reqId）
取结果：loadQueryResult(reqId)（第 2514 行）
  → 查询文件/缓存中的结果（FileService）→ 分页返回
```

### 走读路线 D：视图/模板创建与校验（写链路，PostgreSQL）

```
POST RptUdfViewCreateController / RptUdfTemplateCreateController / RptUdfViewEditController
  → 对象关系：ViewObjectRelationService（sqlengine/service）
  → 字段树：ObjTreeFieldService / UDFObjFieldService（sqlengine/service）
  → 校验：RptUdfViewValidateController → rptvalidate/* + api 模块 CalculateValidationService
  → 落库：postgresql/repository（MyBatis PG）
       ├─ 元数据：com/fxiaoke/bi/crm/metadata / repository
       └─ 数据源：spring/spring-db.xml（PG）、spring-db-system.xml（系统库）
```

### 走读路线 E：适配接口（自 crm-report 迁移）

```
RptUdfDataController / SalesBriefDataController / SalesClueDataController / SaleProcessAnalysisController
  → adapter/service/SalesBriefDataService、SalesClueDataService、SaleProcessAnalysisService
  → 复用 SQLEngine + fs-bi-sqlengine（说明：crm-report 的查询能力已下沉到本服务）
```

### 关键文件清单（走读速查）

| 环节 | 文件 |
| --- | --- |
| 报表查询 API | `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/api/controller/RptUdfDataController.java` |
| 报表数据服务 | `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/jsonbuilder/service/UDFRptReportDataService.java` |
| SQL 引擎 | `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/sqlengine/SQLEngine.java` |
| 批量执行 | `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/sqlroute/AsyncQueryTask.java` |
| 下游 RPC 适配 | `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/rpc/QueryServiceAdapter.java` |
| ClickHouse 直连 | `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/clickhouse/service/CHJDBCService.java` |
| 视图创建/校验 | `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/api/controller/RptUdfViewCreateController.java` |
| 透视表服务 | `fs-bi-udf-report-web/src/main/java/com/fxiaoke/bi/crm/jsonbuilder/service/UDFPivotReportDataService.java` |
| 数据源装配 | `fs-bi-udf-report-web/src/main/resources/spring/spring-db.xml`、`spring-db-system.xml`、`spring-dubbo.xml` |
