# fs-bi-dev-platform 源码架构分析报告

- 仓库地址：`git@git.firstshare.cn:bi/fs-bi-dev-platform.git`
- 分析对象：本地克隆 `/Users/muqingji/code/serve/fs-bi-dev-platform`

---

## 一、项目概况

- **项目简介**：纷享销客 BI 的 **开发平台服务**，面向 BI 应用的自助式建模/宽表能力，核心提供**大宽表（LWT, Large Wide Table）**的新建、编辑、查询、导出，以及自定义对象（Cus）相关的数据处理能力。
- **业务领域**：SaaS BI（商业智能），自助数据分析建模。
- **项目类型**：**多模块单体**。核心 `fs-bi-dev-web`（WAR）+ 共享 `fs-bi-dev-common`（JAR）+ 工具 `fs-bi-dev-toolkit`（JAR）。
- **技术栈**：
  - 语言：Java 21（`maven.compiler.source/target=21`）
  - 构建：Maven（版本 `20.26.30-SNAPSHOT`）
  - 框架：Spring MVC（传统 XML 装配，非 Spring Boot）、MyBatis + PostgreSQL、Dubbo、Sentinel（公司内部 fxiaoke 封装）、CEP 插件（`fs-cep-spring-plugin`，用户/租户注解注入）、Lombok、fastjson、opencsv、jsoup、Hessian
  - 运行环境：Tomcat（WAR）、JDK 21
- **打包/部署方式**：`fs-bi-dev-web` 以 `war` 部署；`common`/`toolkit` 为 `jar` 依赖。
- **容器化**：未发现 Dockerfile / K8s 文件，传统 Tomcat 部署。

## 二、整体系统架构

### 1. 架构模式与分层
- **控制层**：`com.facishare.bi.dev.web.controller`（`ManagerController`、`LwtController`、`CusController`、`IndexController`）
- **业务层**：`service`（`SaveLwtService`、`LargeWideTableService`、`LargeWideTableDataSourceService`、`SqlEngineService`、`ReportService`、`PivotTableService`、`StatService`、`CustomTableService`、`DfAggService`、`RoleService`、`FunctionPermissionService` 等）
- **数据层**：`mapper` + `mapper/tenantmapper`（MyBatis）
- **基础设施**：`common`（限流 `common/limit`、降级 `common/degrada`）、`log`、`mq`、`restful`（REST DTO）、`util`（含 i18n）、`repository`
- **横切**：CEP 插件注解（`@FSUserInfo` / `@FSOuterUserInfo`）注入用户上下文；GrayManager 灰度

### 2. 模块拆分
| 模块 | 职责 |
| --- | --- |
| `fs-bi-dev-web` | 大宽表/自定义对象建模与查询 Web 应用（WAR，核心） |
| `fs-bi-dev-common` | 公共 DTO/实体（`com.facishare.bi.dev.common.dto`） |
| `fs-bi-dev-toolkit` | 工具类（`com.facishare.bi.dev.toolkit.util`） |

### 3. 外部依赖服务
- 组织架构/权限：`PermissionService`（version 5.7）、企业配置 `EnterpriseConfigService`
- 数据查询：`SqlEngineService` 本地 SQL 引擎 + 依赖 fs-bi 生态（`fs-bi-common-entities`）
- 平台能力：`fs-cep-spring-plugin`（CEP 用户体系）、`fs-stone-sdk`（文件）、`fs-qixin-api`（企信）、`gray-release`（灰度）、Sentinel 规则中心
- **HTTP 下游依赖（配置中心下发 host）**：`ReportService`→`udfApiHost`（默认 `http://127.0.0.1:31745/`，调 udf-report `rptUdfViewDataController/queryReportData`）；`StatService`→fs-bi-stat 统计接口；`SqlEngineService`→`sqlengineApiHost`（默认 `http://127.0.0.1:31025/`，调 fs-bi-sqlengine `fs-bi-sqlengine/api/v1/sql_engine/{ei}/query_from_pg`）；`LwtService`→`lwtServiceHost`（默认 `http://172.31.100.247:10091`，调外部 LWT 计算服务 `/lwt/query`）
- 基础设施：PostgreSQL、Redis（缓存）、MQ、CMS 配置中心

### 4. 请求整体流转链路
```
FCP / BI 前端
   → fs-bi-dev-web（Tomcat）
   → Controller（/lwt/m、/lwt、/cus）
   → CEP 注解解析用户/企业上下文（@FSUserInfo）
   → Service（校验 ValidateService → 宽表服务 SaveLwtService/LargeWideTableService）
   → SqlEngineService / Mapper（PostgreSQL）
   → 结果 DTO 返回（restful.dto）
```

## 三、目录结构详细解析

```
fs-bi-dev-platform/
├── pom.xml                     # 聚合：dev-web / dev-common / dev-toolkit
├── AGENTS.md / CLAUDE.md / sonar-project.properties
├── docs/                       # 说明文档（superpowers 计划等）
├── specs/modules/              # 离线测试底座设计
├── scripts/
├── META-INF/
├── fs-bi-dev-web/
│   └── src/main/
│       ├── java/com/facishare/bi/dev/web/
│       │   ├── controller/     # ManagerController(/lwt/m) LwtController(/lwt) CusController IndexController
│       │   ├── service/         # 关键：LargeWideTableService.doQuery/queryLwtResult → processDataSource 按 viewType 分派
│       │   │                   #   ReportService（viewType=1 → udf-report）、PivotTableService（viewType=2）、StatService（统计图 → fs-bi-stat）
│       │   ├── service/        # 宽表、报表、SQL 引擎、权限、license、export、globalFilter、tag 等
│       │   ├── mapper/ + tenantmapper/  # MyBatis 映射（含租户版）
│       │   ├── common/limit common/degrada  # 限流与降级
│       │   ├── log/ mq/ restful/ repository/ util(i18n)
│       ├── resources/application.properties  # Sentinel 规则等
│       └── webapp/WEB-INF/web.xml
├── fs-bi-dev-common/           # 公共 DTO/实体
└── fs-bi-dev-toolkit/          # 工具类
```

## 四、代码模块详细构成

### 1. 核心业务模块
- **大宽表（LWT）**：
  - `ManagerController`（`/lwt/m`）：宽表新建、编辑
  - `LwtController`（`/lwt`）：`/query`（查询）、`/queryAndUpload`（查询并上传）、`/calcField/save`（计算字段）、`/async/sendRequest`、`/async/loadResponse`（异步查询）、`/exportToExcel`、`/innerExportLwtData`、`/exportLwtData`（导出）、`/getFiltersResult`、`/getLwtArgs`、`/validateView` 等
  - `SaveLwtService`、`LargeWideTableService`、`LargeWideTableDataSourceService`、`AsyncQueryLwtSerivce`、`CustomDimensionExpander`（自定义维度展开）
- **自定义对象（Cus）**：`CusController`、`CustomTableService`、`DataOpService`（数据操作）
- **报表/统计**：`ReportService`、`StatService`、`PivotTableService`（透视表）、`DfAggService`（聚合）
- **SQL 引擎**：`SqlEngineService`
- **权限/角色**：`PermissionUtil`、`RoleService`、`FunctionPermissionService`、`ProfileServiceFacade`
- **全局过滤器**：`service/globalFilter`（`ParseMeService`、`ParseOwnDeptService`、`ParseOwnSubEmpService`、`ParseAllService`、`AbstractParseEmpFilterService`——按本人/部门/下属/全部解析数据权限过滤）
- **导出/文件**：`service/export`、`FileService`
- **其他**：`BiUserViewHistoryService`（浏览历史）、`BiUserViewFavoriteService`（收藏）、`YkyyService`、`HengxingService`、`YinluQueryService`（业务对接）、`license`（许可证）、`tag`

### 2. 公共基础模块
- `fs-bi-dev-common`：DTO/实体定义
- `fs-bi-dev-toolkit`：工具类
- 限流/降级：`common/limit`、`common/degrada`（Sentinel）
- i18n：`util/i18n`（`I18NTransformationUtil`）
- 日志：`log` 包

### 3. 数据层设计
- **PostgreSQL**：宽表元数据、数据源配置、用户行为（MyBatis `mapper`/`tenantmapper`）
- **SQL 引擎**：`SqlEngineService` 执行宽表查询 SQL
- **缓存/消息**：Redis/MQ（`mq` 包）

### 4. 权限、认证、鉴权
- 认证：CEP 插件 `@FSUserInfo` / `@FSOuterUserInfo` 注解注入用户/外部用户上下文（`fs-cep-spring-plugin`）
- 数据权限：`PermissionUtil` + 全局过滤器（`globalFilter` 按员工/部门/下属解析）+ 组织架构 `PermissionService`
- 功能权限：`FunctionPermissionService`、`RoleService`

## 五、用到的全部框架 & 第三方组件清单

| 组件 | 作用 |
| --- | --- |
| Spring MVC / Spring | Web 层与 IoC（XML 装配） |
| MyBatis | 持久层（PostgreSQL） |
| Dubbo | 服务 RPC |
| Sentinel（fxiaoke 封装） | 限流、参数流控、降级 |
| fs-cep-spring-plugin | CEP 用户/租户上下文注入 |
| fastjson | JSON 序列化 |
| opencsv 5.5 | CSV 导出 |
| jsoup 1.10 | HTML 解析 |
| Hessian | 二进制序列化 RPC |
| GrayManager / gray-release | 灰度开关 |
| Lombok / AspectJ | 样板代码 / AOP |
| 内部 SDK | fs-bi-common-entities、fs-stone-sdk、fs-qixin-api、fs-enterprise-id-account-converter、mybatis-spring-support |

## 六、核心业务流程拆解

### 1. 大宽表查询
```
前端 POST /lwt/query
  → LwtController
  → LargeWideTableService（组装宽表元数据）
  → SqlEngineService（生成并执行 SQL，含过滤器/计算字段）
  → 全局过滤器（数据权限：本人/部门/下属/全部）
  → PostgreSQL 查询 → 结果返回
```

### 2. 大宽表导出
```
POST /lwt/exportToExcel / innerExportLwtData
  → 权限校验（FunctionPermissionService / PermissionUtil）
  → 查询数据（SqlEngineService / AsyncQueryLwtSerivce）
  → export 服务生成 Excel（opencsv / POI）→ 文件服务返回
```

### 3. 异步查询
```
POST /lwt/async/sendRequest（发起）→ 异步任务执行
  → POST /lwt/async/loadResponse（轮询取结果）
```

### 4. 宽表新建/编辑
```
POST /lwt/m/*（ManagerController）
  → ValidateService（校验）
  → SaveLwtService（保存宽表定义）
  → LargeWideTableDataSourceService（数据源处理）
```

## 七、配置与环境

- **配置类型**：`application.properties`（`process.name=fs-bi-dev-web`、Sentinel 规则开关与规则文件名）、`web.xml`
- **多环境**：CMS 配置中心下发；`fs-bi-dev-common-entities` 版本与 fs-bi 生态联动（20.26.30-SNAPSHOT 同版本族）
- **Sentinel**：参数流控启用（`sentinel-global-param-flow-rule-fs-bi-dev-platform`），流控/降级/系统规则默认关闭
- **构建**：Maven；`pom.xml.versionsBackup` 存在版本备份；sonar 扫描

## 八、项目优缺点 & 风险点

**优点**
- 面向建模场景，服务边界聚焦（宽表/自定义对象/导出），依赖面较 fs-bi 主仓小
- 全局过滤器抽象（`AbstractParseEmpFilterService` 策略化）便于数据权限扩展
- 异步查询与导出分离，降低大查询对请求线程的占用

**现存问题/技术债务**
- 控制器较重：`LwtController` 单个类承载 20+ 接口，职责可再拆分
- 存在业务直连服务（`HengxingService`、`YkyyService`、`YinluQueryService` 等）命名语义不透明，接手需逐个梳理
- `common/degrada`（降级）与 Sentinel 规则文件多为关闭状态，降级能力可能未实际生效
- README 缺失（仓库无 README.md），模块说明主要靠 specs 与代码注释
- 杂项文件（`pom.superpowers-snippets.xml`、`pom.xml.versionsBackup`、META-INF）入库

**接手改造注意事项**
- 宽表链路改动需同时回归 `/lwt` 查询、`/lwt/m` 编辑、导出与异步四条链路
- 新增接口注意 CEP 注解（`@FSUserInfo`）与数据权限过滤器
- 遵循 AGENTS.md：JUnit5 + Mockito 离线单测优先

## 九、需要补充核查的内容

- [ ] 仓库缺失 README，需向负责人确认模块/接口全貌
- [ ] `SqlEngineService` 与 fs-bi-sqlengine 的关系（本地执行还是 Dubbo 调用）
- [ ] `HengxingService` / `YkyyService` / `YinluQueryService` 对应的业务方与协议
- [ ] 生产环境数据源、Redis、MQ、Sentinel 规则中心配置（配置中心下发，仓库未见）
- [ ] 数据库 DDL 与宽表存储模型设计
- [ ] 部署拓扑与网关路由（/lwt 系列接口对外暴露面）
- [ ] 容器化 / CI 流水线配置
- [ ] `fs-bi-dev-toolkit` 实际被引用范围（是否仅测试/工具使用）

---

## 十、代码走读路线（API → 数据层 / 下游服务，最完整力度）

> 文件路径均相对仓库根 `/Users/muqingji/code/serve/fs-bi-dev-platform`（默认在 `fs-bi-dev-web/src/main/java` 下）。

### 走读路线 A：大宽表（LWT）查询（核心链路）

```
BI 前端 / crm-report（BIUDFResource? 不，crm-report 经 BIDEVResource）
  │ POST /lwt/query（QueryLwtArg）
  ▼
① Controller 层
  com/facishare/bi/dev/web/controller/LwtController.java
  └─ query()（第 109 行）
       ├─ 注解：@SentinelLimit(resource="lwtQueryData")、@TimeoutDegradation、@I18NTranslation
       ├─ @FSUserInfo / @FSOuterUserInfo 注入用户 / 外部用户（CEP 插件）
       ├─ adjustUserInfoForEM6H()（外部企业兼容）
       ├─ MyObjectConfigManager.isForceRefresh → refresh=1 强刷
       ├─ 灰度 lwtSync2async 分流：
       │    ├─ 关闭：originQuery() 同步查询
       │    └─ 开启：lwtQueryCache.getReqId() → ReqIdContext 设置 → MQ 异步（LwtQueryProducer）
       │             → LwtQueryConsumer 消费（com/facishare/bi/dev/web/mq/LwtQueryConsumer.java）
       └─ 调用 largeWideTableService.doQuery(...)

② 服务层（宽表组装 + 数据源分派）
  com/facishare/bi/dev/web/service/LargeWideTableService.java
  ├─ doQuery(queryModel, ...)（第 848 行）→ 透传参数
  ├─ doQuery(lwtArgs, fields, ei, uid, ea, ...)（第 921 行）
  │    ├─ handleSpecailFilterByFunction()：特殊筛选器执行函数（FuncService.excuteFunction）
  │    ├─ handleSpecialFilterField()：特殊过滤表达式（$dfname 表达式）
  │    └─ queryLwtResult(...)（第 1043 行）
  │         ├─ handleDownStreamFields()：下游字段处理
  │         ├─ 下钻处理（drillInfo → statService.convertToField）
  │         └─ processDataSource(...)（第 2534 行）★按数据源类型分派：
  │              viewType == "1"（报表）→ reportService.getReportDataSourceWithSimpleData(...)
  │              viewType == "2"（透视表）→ pivotTableService.getReportDataSource(...)
  │              其他（统计图）      → statService.getStatDataSource(...)
  │              （异步场景用 FutureTask + taskExecutor 并行取数）
  │         └─ 结果组装：跨表拼接（CrossJoinTable）、计算字段（CalcColumn）、小计（showSubTotalRow）、
  │              汇总（AggregationDataSetSortHandler）、多币种、格式化
  └─ 元数据读取：getLwtArgs(lwtId, ei, ea, translate)（第 5577 行，PG MyBatis）

③ 下游取数（按 viewType 分别进入不同服务）
  A) 报表数据源 → com/facishare/bi/dev/web/service/ReportService.java
     └─ getReportDataSourceWithSimpleData / queryReportData()（第 158 行）
          └─ HTTP POST udfApiHost + "rptUdfViewDataController/queryReportData"
             （udfApiHost 来自配置中心 fs-bi-dev-platform，debug 默认 http://127.0.0.1:31745/）
             → udf-report（链路见《fs-bi-udf-report-架构分析.md》走读路线 A）
  B) 统计图数据源 → com/facishare/bi/dev/web/service/StatService.java
     └─ getStatDataSource / queryChartDataResult（第 294 行附近）
          └─ HTTP POST fs-bi-stat 统计图查询接口（easy-stat 内核）
  C) 透视表数据源 → com/facishare/bi/dev/web/service/PivotTableService.java

④ 本地数据访问（宽表元数据，PostgreSQL）
  - Mapper：com/facishare/bi/dev/web/mapper/LargeWideTableConfigMapper.java
            com/facishare/bi/dev/web/mapper/LargeWideTableDataSourceMapper.java
            com/facishare/bi/dev/web/mapper/tenantmapper/LargeWideTableConfigMapperTenant.java（租户版）
  - XML：fs-bi-dev-web/src/main/resources/mybatis/（mybatis-config.xml 装配）
  - 数据源：spring/spring-db-postgresql.xml（PG 多数据源）
```

### 走读路线 B：宽表新建/编辑（ManagerController）

```
POST /lwt/m/...（ManagerController，@RequestMapping("/lwt/m")）
  → com/facishare/bi/dev/web/controller/ManagerController.java
       ├─ getDataSourceFieldsDetail / getDataSourceFiltersDetail（数据源字段/筛选器）
       └─ 保存：SaveLwtService（saveLwt/updateCallBackFunc 等）
            └─ Mapper：RptViewMapper / LargeWideTableConfigMapper / LargeWideTableDataSourceMapper（PG）
```

### 走读路线 C：宽表导出

```
POST /lwt/exportToExcel、/innerExportLwtData、/exportLwtData、/innerExportLwtDataWithNotice（LwtController）
  → 权限校验（FunctionPermissionService / PermissionUtil）
  → 数据查询（LargeWideTableReportExportService / AsyncQueryLwtSerivce / LwtQueryConsumer）
  → 导出服务生成 Excel（opencsv / POI）→ FileService 返回/上传
```

### 走读路线 D：SQL 引擎 / 外部 LWT 服务（保留备查）

```
- SqlEngineService.query()：HTTP POST sqlengineApiHost + "fs-bi-sqlengine/api/v1/sql_engine/{ei}/query_from_pg"
  （对应 fs-bi-sqlengine SqlEngineServiceImpl，见《fs-bi-架构分析.md》走读路线 D；
   注意：当前代码中该 Service 未被其他类注入使用，属于备用能力）
- LwtService.getLwtArgs()/doQuery()：HTTP POST lwtServiceHost + "/lwt/query"
  （默认 172.31.100.247:10091 / debug 127.0.0.1:31139，指向外部 LWT 计算服务）
```

### 关键文件清单（走读速查）

| 环节 | 文件 |
| --- | --- |
| 宽表查询 API | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/controller/LwtController.java` |
| 宽表服务 | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/service/LargeWideTableService.java` |
| 数据源分派 | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/service/LargeWideTableService.java`（processDataSource, 2534 行） |
| 报表数据源（→udf-report） | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/service/ReportService.java` |
| 统计图数据源（→fs-bi-stat） | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/service/StatService.java` |
| 异步消费 | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/mq/LwtQueryConsumer.java` |
| SQL 引擎（备用） | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/service/SqlEngineService.java` |
| 外部 LWT（备用） | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/service/LwtService.java` |
| 宽表元数据 Mapper | `fs-bi-dev-web/src/main/java/com/facishare/bi/dev/web/mapper/LargeWideTableConfigMapper.java` |
