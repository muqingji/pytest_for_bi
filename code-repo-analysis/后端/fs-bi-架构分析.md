# fs-bi 源码架构分析报告

- 仓库地址：`git@git.firstshare.cn:bi/fs-bi.git`
- 分析对象：本地克隆 `/Users/muqingji/code/serve/fs-bi`（master/主分支）

---

## 一、项目概况

- **项目简介**：Facishare（纷享销客）BI 系统的**应用层服务**，承载报表、统计图、仪表盘、指标、元数据管理等 BI 应用能力，是 BI 体系的核心服务端工程。仓库 README 自述定位为「BI 应用层服务」，数据服务由数仓工程（fs-bi-warehouse）承担。
- **业务领域**：SaaS BI（商业智能），围绕 CRM 业务数据的统计分析与可视化。
- **项目类型**：**多模块单体聚合工程**。由 5+ 个可独立部署的 WAR 应用模块 + 大量共享 JAR 模块组成，属于「大仓多应用」形态。
- **技术栈**：
  - 语言：Java 21（`maven.compiler.source/target=21`，`jdk.version=21`）
  - 构建：Maven 聚合工程，父 POM 为公司内部 `fxiaoke-parent-pom:1.0.0-SNAPSHOT`
  - 框架：Spring MVC + Spring 传统 XML 装配（**非 Spring Boot 启动方式**），MyBatis，Dubbo（RPC），JOOQ、jSQLParser、Kryo、Freemarker、EasyExcel/POI、MapStruct、Lombok、Quartz
  - 运行环境：Tomcat（WAR 部署）、JDK 21；依赖公司内部 fs-paas-*、fs-metadata-*、fs-plat-privilege-* 等 SDK
- **打包/部署方式**：运行模块以 `war` 打包（`fs-bi-metadata`、`fs-bi-stat`、`fs-bi-task`、`fs-bi-transfer`、`fs-bi-devops`、`fs-bi-metadata-ant` 等），共享模块以 `jar` 打包；传统 Tomcat 部署 + Dubbo 服务注册（ZooKeeper）。
- **容器化**：仓库内未发现 Dockerfile / K8s 编排文件，推测仍为传统 Tomcat 部署（需向运维确认 CI 实际形态）。

## 二、整体系统架构

### 1. 架构模式与分层
典型分层架构（每个 WAR 模块内部）：
- **控制层**：`controller` / `resource`（如 `com.facishare.bi.stat.controller.*`、`com.facishare.bi.metadata.*.resource`）
- **业务层**：`service` + `service.impl`
- **数据层**：`dao` / `mapper` / `repository`（MyBatis XML 映射，PostgreSQL / ClickHouse 双数据源）
- **领域模型**：`model.bo`（BO）、`model.entity`（DO）、`dto`
- 横切：`aop`、`exception`、`context`（ThreadLocal 上下文）、`cache`

模块间通过 Dubbo 接口（`fs-bi-api` 定义）或直接 JAR 依赖协作。

### 2. 服务（模块）拆分
| 模块 | 职责 |
| --- | --- |
| `fs-bi-metadata` | 元数据服务（WAR）：报表、指标、维度的元数据管理 |
| `fs-bi-stat` | 统计分析服务（WAR）：报表数据查询、统计图、指标、目标规则、AI 可见性 |
| `fs-bi-task` | 任务服务（WAR）：订阅、定时任务（Sundial/Quartz）、i18n 管理 |
| `fs-bi-transfer` | 数据迁移/传输服务（WAR）：对象、元数据迁移 |
| `fs-bi-devops` | 运维服务（WAR）：DB 运维、缓存运维、健康检查 |
| `fs-bi-metadata-ant` | 元数据自动化运维（WAR）：对象转换、表差异、i18n 自动生成 |
| `fs-bi-api` | 服务接口定义（JAR）：Dubbo/内部接口与公共模型 |
| `fs-bi-common` / `fs-bi-util` | 公共常量、工具类、上下文 |
| `fs-bi-common-config` | 公共配置装配 |
| `fs-bi-cache` / `fs-bi-mq` | 缓存封装、MQ 封装 |
| `fs-bi-sqlgenerator` / `fs-bi-sqlengine` | SQL 生成器、SQL 执行器 |
| `fs-bi-privilege` / `fs-bi-permission-context` | 数据权限 / 权限上下文 |
| `fs-bi-license` | 许可证（License）校验 |
| `fs-bi-i18n` | 国际化 |
| `fs-bi-client` / `fs-bi-thirdparty` | 内部 RPC Client / 三方接入 |
| `fs-bi-organization-context` / `fs-bi-metadata-context` | 组织架构上下文 / 元数据上下文 |

### 3. 外部依赖服务
- CRM 侧：`fs-crm-rest-api`（CRM REST 接口）、组织架构 `EmployeeService` / `DepartmentService` / `EnterpriseConfigService`（Dubbo）
- 平台侧：`fs-plat-privilege-api`、`fs-paas-bizconf-api`、`fs-metadata-option-api`、UC `EnterpriseEditionService`
- 基础设施：PostgreSQL、ClickHouse、Redis、ZooKeeper、CMS 配置中心、Mongo、MQ、I18N 平台、灰度开关
- **对外 SQL 引擎 REST 契约（本仓库提供、被 udf-report/dev-platform 依赖）**：`fs-bi-client/SqlEngineClient`（`@FRestApi("BI_SQLENGINE")`，Retrofit）→ `POST v1/sql_engine/{ei}/query_from_pg|query_from_sql|...` → `fs-bi-sqlengine/SqlEngineServiceImpl`（JAX-RS `@Path("v1/sql_engine")`）→ `RepositoryFacade.query(DBType.PG|MS, sql)`（灰度直连 or 缓存）→ `QueryRepository` → `PGSQLExecutor`（SQL Server 走 `MS`）

### 4. 请求整体流转链路
```
前端 / FCP 网关
   → Tomcat（fs-bi-stat / fs-bi-metadata 等 WAR）
   → Controller/Resource（参数校验、格式化）
   → Service（权限校验：fs-bi-privilege；灰度：GrayManager；上下文：RequestContextManager）
   → SQL 生成（fs-bi-sqlgenerator / easy-stat 流程节点）
   → SQL 执行（fs-bi-sqlengine → MyBatis/JDBC）
   → PostgreSQL（元数据/配置）/ ClickHouse（统计数据）
   → 结果 DTO（Kryo/JSON 序列化）回传
```

## 三、目录结构详细解析

```
fs-bi/
├── pom.xml                      # 聚合 POM：25 个 module、版本管理
├── README.md / CONTEXT.md       # 开发规范、BI 领域术语
├── AGENTS.md                    # 仓库级编码/测试规范
├── specs/                       # 规格：features（需求特性）、modules（模块说明）、governance（覆盖率治理）、templates（模板）
- `fs-bi-stat` 关键类分布（核心查询链路）：
  - 控制器：`controller/RptQueryController`（报表查询）、`controller/ViewDataQueryApiController`（统计图）、`controller/StatEditController`、`controller/BillBoardController`、`controller/AggRuleController`
  - 查询内核：`easy/stat/application/service/impl/RootFlowServiceImpl`（8 阶段流程编排）、`easy/stat/core/flow/service/*Flow`（BaseCheck/CompletionParam/BuildModel/HitStrategy/PreGenerateDataQuerySql/GenerateDataQuerySql/DataQuery/GenerateResult/HandleResult）
  - SQL 生成：`easy/stat/domain/generatedataquerysql/design/*`、`easy/stat/domain/pregeneratedataquerysql/flow/impl/withas/*`（PreSqlWithAs 系列 FlowNode）
  - 执行器：`easy/stat/clickhouse/executor/ClickHouseSQLExecutor`（JDBC 直查 ClickHouse）
├── docs/                        # ADR 架构决策记录、agents 说明
├── scripts/                     # 构建/校验脚本（quick-scan.sh、verify-cycle.sh）
├── fs-bi-{api,common,util,...}  # 各业务/公共模块（见四）
└── lombok.config / sonar-project.properties / facishare-codestyle.xml
```

各业务模块统一布局（以 fs-bi-metadata 为例）：
- `src/main/java/com/facishare/bi/metadata/`：`aop`（切面）、`exception`（异常）、`model/bo|entity`（BO/DO）、`dao`（持久层接口+impl）、`service`（业务接口+impl）、`resource`（REST 层）
- `src/main/resources/`：`applicationContext.xml`、`application.properties`、`spring/spring-*.xml`（数据源、缓存、AOP、Dubbo、调度）
- `src/main/webapp/WEB-INF/`：`web.xml`、`springmvc-restful.xml`

## 四、代码模块详细构成

### 1. 核心业务模块
- **fs-bi-metadata（元数据）**：报表/指标/维度的元数据维护、查询与生命周期管理（`ReportMetadataServiceImpl` 等）。
- **fs-bi-stat（统计分析，核心）**：
  - `controller`：`RptQueryController`（报表数据查询 `/rpt/data/query`、`queryWithKryo`）、`ViewDataQueryApiController`（统计图/图表查询 `/api/v1/stat/`）、`StatEditController`、`BillBoardController`（排行榜）、`AggRuleController`、`GoalRuleController`、`MetricLifecycleController`、`MetricAiVisibilityController` 等
  - `easy.stat`：易用统计核心（RootFlowInterface 流程式 SQL 生成，含 with-as 初始化、过滤、分组、join、having 等 FlowNode）
  - `service`：`QueryReportService`、`StatServiceFacade`、`AggRuleService`、`LicenseService` 等
- **fs-bi-sqlgenerator / fs-bi-sqlengine**：报表 SQL 的生成（基于元数据与过滤器）与执行（多方言/多数据源、SQL 重写 `SqlReWriteByAsWith`）。
- **fs-bi-task（任务）**：`SubscriptionController`（订阅）、`SchduleTaskController`、Sundial 定时任务消费、i18n 管理接口。
- **fs-bi-transfer（迁移）**：对象/元数据跨环境迁移、DTO 转换。
- **fs-bi-devops（运维）**：`DBOperatorController`、`CacheDevOpsController`、`Paas2BiTableDataController`、健康检查（Quartz 定时）。
- **fs-bi-metadata-ant**：`MetadataConvertController`、`PhysicalTableDiffController`、`Paas2BiMetadataAlignmentController` 等自动化工具。

### 2. 公共基础模块
- `fs-bi-common`：常量（`FieldTypeEnum`、`DateRangeEnum`）、`ApplicationContextHolder`、`GrayManager`、`ParallelUtils`、公共实体 `common.entities`（`QueryReportDataArg`、`QueryReportResult`、`KryoResult` 等）
- `fs-bi-util`：日期、字符串、分页、序列化等工具
- `fs-bi-api`：对外服务接口定义与契约模型
- `fs-bi-cache`：Redis/多级缓存封装（`spring-multi-level-cache.xml`）
- `fs-bi-mq`：消息封装
- `fs-bi-common-config`：公共配置装配（含 `com.facishare.App`）
- 异常/拦截：各模块 `exception` 包 + `BiBizExceptionHandler`；日志 logback + `fs-paas-logging-support`
- 上下文：`RequestContextManagerBase`、`EasyStatThreadLocal`（请求级 ThreadLocal，接口 finally 清理）

### 3. 数据层设计
- **PostgreSQL**：元数据、报表配置、订阅、权限等业务库（`spring-db-postgresql.xml`、`spring-bi-postgresql.xml`）
- **ClickHouse**：统计数据查询（`fs-bi-stat` 的 `spring-db-clickhouse.xml`）
- **Redis**：缓存（`spring-cache.xml`、`fs-bi-cache`，Spring Data Redis 1.8）
- **CMS 配置中心**：环境配置、灰度开关
- **Mongo**：部分场景（i18n/日志等，需进一步核实）

### 4. 权限、认证、鉴权
- 认证在网关层（FCP/纷享网关透传用户与租户 Header）；应用层通过 `RequestContextManager`/ThreadLocal 读取用户、企业上下文
- 数据权限：`fs-bi-privilege`（`spring-privilege.xml`）+ `fs-bi-permission-context`，对接 `fs-plat-privilege-api` 与组织架构 `PermissionService`
- 功能权限与许可证：`fs-bi-license`（License 校验）

## 五、用到的全部框架 & 第三方组件清单

| 组件 | 作用 |
| --- | --- |
| Spring MVC / Spring | Web 层与 IoC 容器（XML 装配） |
| MyBatis | 持久层 ORM（PG/CH 双数据源） |
| Dubbo | 服务间 RPC（ZooKeeper 注册） |
| JOOQ 3.14 | 类型安全 SQL 构建（统计查询） |
| jSQLParser / sql-formatter | SQL 解析与格式化 |
| Kryo 5.3 | 二进制序列化（查询结果 `KryoResult`） |
| Freemarker 2.3 | 模板渲染 |
| EasyExcel / POI 5.2 | 报表导入导出 |
| MapStruct 1.5 | DTO 转换 |
| Lombok | 样板代码生成 |
| Quartz 2.2 | 定时任务 |
| Spring Data Redis 1.8 | Redis 缓存 |
| CGLIB / ByteBuddy / Objenesis | 代理与增强 |
| Vavr | 函数式工具 |
| commons-math3 | 数学计算 |
| fastjson | JSON 序列化 |
| 内部 SDK | fs-paas-*、fs-metadata-*、fs-crm-rest-api、fs-plat-privilege-api、fs-paas-bizconf-api 等 |

## 六、核心业务流程拆解

### 1. 报表数据查询（核心链路）
```
前端请求 POST /rpt/data/query (QueryReportDataArg)
  → RptQueryController.queryReportData
  → QueryReportService.queryReportData
      → 初始化请求上下文（EasyStatThreadLocal / RequestContextManager）
      → RootFlowInterface（easy-stat 流程）：
          预生成 SQL（with-as：组织维度/部门/人员/筛选等 FlowNode）
          → 生成查询 SQL（AGenerateDataQuerySqlTemplateNode）
          → 过滤条件解析（JudgeFilterInterface / TransformJooqConditionInterface）
          → 库路由（DbRouterService：PG / ClickHouse）
      → fs-bi-sqlengine 执行 SQL
      → 结果转换（StatResult2RptResult、Kryo/JSON 序列化）
  → finally：清理 ThreadLocal
```

### 2. 统计图/视图查询
```
GET/POST /api/v1/stat/chart/query、data/query
  → ViewDataQueryApiController → IStatDataServiceManager / IStatServiceFacade
  → 复用 easy-stat 查询内核 + 图表配置（ChartPropertyService）
  → 权限过滤（perm/query）→ 缓存（clearCache/noticeChange 失效）
```

### 3. 订阅与定时任务
```
SubscriptionController / SchduleTaskController
  → fs-bi-task service → Sundial（公司调度平台）/ Quartz 触发
  → 生成订阅快照 → 推送（依赖 fs-bi-mq / 消息）
```

## 七、配置与环境

- **配置文件类型**：`application.properties`（每模块 `process.name`、`process.profile`）、Spring XML（`applicationContext.xml` + `spring/*.xml`）、MyBatis XML、`logback.xml`、`web.xml`
- **多环境策略**：通过 CMS 配置中心下发环境差异配置；本地 profile 标识（如 `fstest`）；`process.profile` 区分环境；灰度开关 `GrayManager`
- **环境变量/启动参数**：ZooKeeper 地址（`dubbo-common.zookeeper`）、数据源地址等均来自配置中心占位符（`${...}`）
- **构建**：`mvn clean verify jacoco:report`；提交规范通过 `.githooks`（Conventional Commits + `Agent:` 标记 + TAPD 关联）

## 八、项目优缺点 & 风险点

**优点**
- 模块化程度高，领域边界清晰（元数据/统计/SQL/任务/迁移/运维分离），便于团队分工
- SQL 生成器与执行器解耦，easy-stat 流程节点化设计，扩展查询语义（with-as、下钻、联表）能力强
- 上下文管理与 ThreadLocal 清理规范（finally 清理），异常处理统一
- 有 specs/ADR/覆盖率治理等工程化沉淀

**现存问题/技术债务**
- 传统 Spring XML 装配 + 多 WAR 大仓，启动/构建链路重，局部改动回归成本高
- 依赖大量内部 SNAPSHOT SDK（fs-paas-*、fs-metadata-* 等），版本升级受平台牵制
- 部分模块仍存在 JUnit4/TestNG 与 JUnit5 并存（仓库规范要求迁移 JUnit5）
- `fs-bi-stat` 中 `zdemo` 演示代码留在 `src/main`（如 `ForceecrmCompareMain`），属于历史遗留
- ThreadLocal 上下文靠人工清理，遗漏存在上下文串染风险

**接手改造注意事项**
- 先按模块边界定位，用 `mvn -pl <module> -am test` 做模块级验证
- 改动公共模块（common/api/cache）前先分析直接依赖链
- 遵循 AGENTS.md 测试规范：JUnit5 + Mockito，离线优先，不做低价值补测

## 九、需要补充核查的内容

- [ ] 各 WAR 在 Tomcat 中的实际部署拓扑与域名/网关路由（仓库内无部署清单）
- [ ] 生产环境数据源、ZooKeeper、CMS 配置中心的真实地址（仓库内仅有占位符）
- [ ] `fs-bi-stat` 之外是否还有独立部署实例（如 `fs-bi-organization-context` 是否单独成应用）
- [ ] 数据库表结构 DDL 脚本（仓库内未见集中 SQL 目录）
- [ ] Docker/K8s/CI 流水线配置（仅见 sonar/Jenkins 外链，未见容器化文件）
- [ ] 部分内部 SDK（fs-bi-mapperserver、fs-paas-*、fs-metadata-*）的源码与版本基线
- [ ] `fs-bi-metadata-ant` 与 `fs-bi-devops` 的对外暴露面（疑似内部运维接口，需确认鉴权）
- [ ] fs-bi 与 fs-bi-crm-report / fs-bi-udf-report / fs-bi-warehouse 之间的 Dubbo 接口契约清单

---

## 十、代码走读路线（API → 数据层 / 下游服务，最完整力度）

> 本节给出可直接按文件路径逐步跟读的走读路线，覆盖「API 层 → 服务层 → SQL 生成/执行 → 数据层 / 下游调用」。
> 文件路径均相对仓库根 `/Users/muqingji/code/serve/fs-bi`。

### 走读路线 A：报表数据查询（核心链路，fs-bi-stat → ClickHouse）

```
前端 / FCP 网关
  │ POST /rpt/data/query（QueryReportDataArg）
  ▼
① Controller 层
  fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/RptQueryController.java
  └─ queryReportData()  @RequestMapping("/rpt/data/query", POST)
       ├─ 捕获异常（FUNCTION 来源打 warn，其余 error），finally 清理 EasyStatThreadLocal / RequestContextManagerBase
       └─ 调用 queryReportService.queryReportData(arg)

② Service 层
  fs-bi-stat/src/main/java/com/facishare/bi/stat/service/QueryReportService.java
  └─ queryReportData()（第 74 行）
       ├─ ConfigManager.isForceRefresh → 强刷 refresh=1
       ├─ beforePivotHandle()：透视表前置处理
       ├─ RequestContextManagerBase.getContext() 写入 ei/userId/from/fromId/lwtFrom/lwtFromId/lwtId
       ├─ EasyStatThreadLocal.setExportFormattedType（导出格式化类型）
       ├─ WholeContext.fromOutsideForm(tenantId, userId, arg)：组装全量上下文
       ├─ stopEmpUtils.setViewStopEmpMap(viewId)：停用员工映射（权限/隐藏）
       ├─ rootFlowInterface.goForward(wholeContext, CutRuleNameEnum.STAT_QUERY)
       ├─ 结果转换：JarQueryChartDataResultMapper.INSTANCE.toJarQueryResult
       │             → StatResult2RptResult.doConvert(...) → QueryReportResult
       ├─ constructCurrencyDisplayFieldIcon()：多币种金额字段 icon
       ├─ DataResultCardRptCountUtil.convertToSalesBriefRptDataCountResult()：卡片计数
       └─ afterPivotHandle() / 灰度日志 reportChPrintBody

③ 查询内核（easy-stat 工作流）
  fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/application/interfaces/impl/RootFlowInterfaceImpl.java
  └─ goForward() → RootFlowServiceImpl.goForward()
     fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/application/service/impl/RootFlowServiceImpl.java（第 58 行）
     按 8 组 Flow 依次执行（每组支持多 List，可插拔）：
       1) baseCheckFlowListList       基础校验
       2) completionParamFlowListList 参数补全
       3) buildModelFlowListList      构建模型（EasyModel）
       4) hitStrategyFlowListList     命中策略
       5) preGenerateDataQuerySqlFlowListList  生成 SQL 前置（with-as 初始化）
       6) generateDataQuerySqlListList         生成查询 SQL
       7) dataQueryFlowListList                执行查询
       8) generateResultFlowListList / handleResultFlowFlowListList  构建/转换结果

④ SQL 生成（关键节点示例）
  - with-as 初始化节点：
    fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/domain/pregeneratedataquerysql/flow/impl/withas/
      ├─ PreSqlWithAsOrgDimensionInitFlowNode（组织维度）
      ├─ PreSqlWithAsOrgEmployeeUserInitFlowNode（员工/用户）
      ├─ PreSqlWithAsOwnDepartmentInitFlowNode / PreSqlWithAsOutDeptInitFlowNode（本部门/外部部门）
      ├─ PreSqlWithAsSelectOptionInitFlowNode（选项）
      └─ PreSqlWithAsProductCategoryInitFlowNode（品类）
  - 过滤条件：TransformJooqConditionInterface.getConditionRemovePredicate(...)（JOOQ Condition）
  - 库路由：DbRouterService.checkIsSchemaTenant()（schema 隔离企业 vs 普通企业）

⑤ 数据执行层
  - ClickHouse 路径：
    fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/clickhouse/executor/ClickHouseSQLExecutor.java
    └─ query() / queryDirect()（第 44/94 行）
         ├─ 灰度 query_table_from_chdb 等规则
         ├─ jdbcConnection.query(sql, ...)（CH JDBC 直查）
         └─ transformResultSetToDataSetElement.handle(...) → DataSet
  - PostgreSQL 路径：经 fs-bi-sqlengine（见走读路线 D）

⑥ 结果返回
  QueryReportResult（含 displayFields / dataSet / page / cardRptDataCountResult / rptQueryLimit）
```

**跟读建议**：先看 ①→② 建立整体感觉；再在 ③ 的 `RootFlowServiceImpl.goForward` 打断点看每个 Flow 的注入列表；最后在 `ClickHouseSQLExecutor.queryDirect` 打印 SQL 观察生成结果。

### 走读路线 B：统计图/视图查询（stat 模块另一入口）

```
POST /api/v1/stat/chart/query、data/query、chartConfig/query、perm/query
  → fs-bi-stat/.../stat/controller/ViewDataQueryApiController.java（@RequestMapping("/api/v1/stat/")）
  → IStatDataServiceManager / IStatServiceFacade（service 门面）
  → 复用 easy-stat 查询内核（同走读路线 A 的 ③④⑤）
  → 缓存失效：/clearCache/{ei}/{viewId}、/noticeChange/{ei}/{viewId}
```

### 走读路线 C：订阅定时触发（task 模块）

```
POST /schedule/single/trigger/{schId}/{ei}、/api/v1/subscribe/...
  → fs-bi-task/.../task/controller/SubscriptionController.java
  └─ runSingleSch()
       ├─ ApplicationContextHolder.getContext() 取 SchRunService / SchRunStorageService / ReportService / ScanAndSendJobService
       ├─ SchRunService：调度运行记录（PG，SchRunStorage）
       ├─ ReportService.queryReportData(arg, ei, ea, userId)（task 侧复用报表查询）
       ├─ 推送：SendMailTestService / SendQiXinMessageService / QixinService
       └─ SchRunStorageService：结果快照存储
```

### 走读路线 D：SQL 引擎（下游服务实际执行 SQL 的地方，本仓库对外提供）

```
调用方（udf-report / dev-platform / 其他内部服务）
  │ @FRestApi("BI_SQLENGINE") Retrofit 客户端
  ▼
① 客户端契约：fs-bi-client/src/main/java/com/facishare/bi/client/SqlEngineClient.java
   POST v1/sql_engine/{ei}/query_from_pg / query_from_sql / query_from_pg_for_pre_refresh
   POST v1/sql_engine/{ei}/query_from_pg/custom_temptable
   POST v1/sql_engine/{ei}/explain_from_pg（执行计划）

② 服务端实现：fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/service/impl/SqlEngineServiceImpl.java
   @Path("v1/sql_engine")（JAX-RS）
   └─ queryFromPg(sql, ei, userId)
        ├─ RequestContextManagerBase.setContext(ei, userId)
        └─ repositoryFacade.query(DBType.PG, sql)

③ 仓储门面：fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/repository/RepositoryFacade.java
   ├─ GrayManager.isDirectConnectionDB → 直连：queryRepository.query(dbType, sql)
   └─ 否则：queryRepository.queryCacheAble(dbType, sql, createExecQueryKey(ei, sql))（带缓存）

④ 执行器：fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/executor/
   ├─ PGSQLExecutor.java（PG 查询）
   ├─ AbstractSqlExecutor.java（基类）
   ├─ SqlReWrite.java / SqlReWriteByAsWith.java（SQL 重写，with-as 改写）
   └─ InSqlHandler.java / InWithAnyHandler.java（IN / ANY 优化）
   DBType 仅 PG / MS（MS=SQL Server），ClickHouse 查询走 fs-bi-stat 的 ClickHouseSQLExecutor
```

### 走读路线 E：元数据读取（metadata 模块，供 stat 等模块 Dubbo/JAX-RS 调用）

```
服务提供方：fs-bi-metadata/src/main/java/com/facishare/bi/metadata/report/service/impl/ReportMetadataServiceImpl.java
  └─ 实现 MetadataService 接口（JAX-RS @PathParam 风格）
       ├─ getDescribeMetadata(tenantId)（对象元数据）
       ├─ getObjectMasterFieldByObjectName(...)（主对象字段）
       ├─ getDescribeObjectRelationTree(...)（对象关系树）
       └─ queryObjectList(ei) / querySlaveObjectList(ei)（对象清单）
  └─ 数据落地：fs-bi-metadata/src/main/resources/mybatis/mapper/*.xml + report/dao/entity/*DO
       （PostgreSQL，spring-db-postgresql.xml）
```

### 关键文件清单（走读速查）

| 环节 | 文件 |
| --- | --- |
| 报表查询入口 | `fs-bi-stat/src/main/java/com/facishare/bi/stat/controller/RptQueryController.java` |
| 报表查询服务 | `fs-bi-stat/src/main/java/com/facishare/bi/stat/service/QueryReportService.java` |
| 流程编排 | `fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/application/service/impl/RootFlowServiceImpl.java` |
| SQL 生成节点 | `fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/domain/pregeneratedataquerysql/flow/impl/withas/` |
| ClickHouse 执行 | `fs-bi-stat/src/main/java/com/facishare/bi/easy/stat/clickhouse/executor/ClickHouseSQLExecutor.java` |
| SQL 引擎客户端 | `fs-bi-client/src/main/java/com/facishare/bi/client/SqlEngineClient.java` |
| SQL 引擎服务 | `fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/service/impl/SqlEngineServiceImpl.java` |
| SQL 执行器 | `fs-bi-sqlengine/src/main/java/com/facishare/bi/sqlengine/executor/PGSQLExecutor.java` |
| 订阅触发 | `fs-bi-task/src/main/java/com/facishare/bi/task/controller/SubscriptionController.java` |
| 元数据服务 | `fs-bi-metadata/src/main/java/com/facishare/bi/metadata/report/service/impl/ReportMetadataServiceImpl.java` |
