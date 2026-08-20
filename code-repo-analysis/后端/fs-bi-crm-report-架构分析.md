# fs-bi-crm-report 源码架构分析报告

- 仓库地址：`git@git.firstshare.cn:bi/fs-bi-crm-report.git`
- 分析对象：本地克隆 `/Users/muqingji/code/serve/fs-bi-crm-report`

---

## 一、项目概况

- **项目简介**：纷享销客 BI 的 **CRM 报表服务**，提供报表（Report）、仪表盘（Dashboard）、视图（View）的新增、编辑、查询、订阅、分享、导出等能力，对外暴露 FCP 接口（纷享 CRM 开放平台接口），同时提供报表数据查询的 Dubbo 能力。
- **业务领域**：SaaS BI（商业智能），CRM 数据报表与数据可视化。
- **项目类型**：**多模块单体**。根 POM 聚合 `fs-bi-crm-report-web`（WAR）、`fs-bi-crm-report-api`（JAR）、`fs-bi-crm-report-third-party`（JAR）；另有遗留空壳 `fs-bi-crm-report-manage`（仅 POM，未在根 POM 聚合，无源码）。
- **技术栈**：
  - 语言：Java 21（`java.version=21`、`maven.compiler.release=21`）
  - 构建：Maven，父 POM 为内部 `fxiaoke-parent-pom`
  - 框架：Spring MVC（传统 XML 装配，非 Spring Boot）、MyBatis（PG + ClickHouse 双数据源）、Dubbo、ElasticJob、Mongo（mongo-java-driver + Morphia）、Ehcache/Redis、Freemarker、Lombok
  - 运行环境：Tomcat（WAR）、JDK 21
- **打包/部署方式**：`fs-bi-crm-report-web` 以 `war` 部署到 Tomcat；`api`、`third-party` 为 `jar` 供内部依赖；Dubbo 消费内部服务。
- **容器化**：未发现 Dockerfile / K8s 文件，传统 Tomcat 部署（需向运维确认）。

## 二、整体系统架构

### 1. 架构模式与分层
传统分层：
- **控制层**：`com.facishare.bi.portal.api.*`（门户 API）、`com.facishare.bi.backstage.controller`（后台）、`com.facishare.bi.midware.jobcenter.web.controller`（任务中心导出）、`com.facishare.bi.api.rest.*`（REST）
- **业务层**：`com.facishare.bi.service.*`（`ReportService`、`RptViewService`、`ViewCategory*`、`BillBoardService`、`SchRunService` 等）
- **数据层**：`com.facishare.bi.dao`（MyBatis Mapper，`mapper` / `tenantmapper` / `dynamicmapper`）、`repository`、`entity`
- **基础设施**：`aop`、`context`、`exception`（`BiBizExceptionHandler`、`ApiExceptionHandler`）、`helper`、`util`、`common.cache`、`event`、`rpc`、`thirdparty`

### 2. 模块拆分
| 模块 | 职责 |
| --- | --- |
| `fs-bi-crm-report-web` | 报表/仪表盘/视图的门户 API、后台管理、订阅、导出、i18n、权限（WAR，核心） |
| `fs-bi-crm-report-api` | 公共接口定义与模型（JAR） |
| `fs-bi-crm-report-third-party` | 三方/内部系统集成封装（JAR） |
| `fs-bi-crm-report-manage` | 仅存 POM 的空壳模块（未聚合、无源码，疑似废弃） |

### 3. 外部依赖服务（Dubbo 消费）
- `com.facishare.bi.service.IQueryService`（**报表查询服务**，独立 Dubbo 注册中心 `queryZk`）
- 组织架构：`EmployeeService`、`PermissionService`（权限，version 5.7）、`EnterpriseConfigService`
- 消息/推送：`PushSessionService`（企信推送）、`BpmEmailService` / `SystemEmailService` / `EmailService`（邮件代理）
- 文件：`FilePackedService`（仓库文件打包）、`DataScreenService`（数据大屏）、`EnterpriseEditionService`（UC 版本）、`AccountBindService`
- 基础设施：PostgreSQL（业务库）、ClickHouse（统计明细）、Mongo、Redis、CMS 配置中心、MQ
- **跨服务 HTTP RPC（核心下游）**：`portal/rpc/BIUDFResource`（报表服务 BI-UDF-REPORT）、`BIDEVResource`（拼表服务 BI-DEV-PLATFORM）、`FSBIResource`（统计服务）—— 均为 `com.facishare.rest.core` 的 `@RestResource` 注解接口，`@POST` 指向下游服务路径

### 4. 请求整体流转链路
```
FCP 网关（纷享 CRM 开放平台）
   → fs-bi-crm-report-web（Tomcat）
   → portal.api / backstage.controller / api.rest Controller
   → service（权限：ViewPermManagerService / ExportAllPermissionsService；i18n；缓存）
   → dao（MyBatis：PostgreSQL 元数据 + ClickHouse 数据）
   → Dubbo（IQueryService 查询统计结果）
   → 结果 DTO 返回
```

## 三、目录结构详细解析

```
fs-bi-crm-report/
├── pom.xml
├── README.md / AGENTS.md / sonar-project.properties
├── docs/                      # 发布记录、设计说明
├── solution-design/           # 多语言（i18n）改造方案设计（DTO 元数据增强、AOP 方案对比等）
├── specs/modules/             # 模块离线测试底座设计
├── tools/legacy_cleanup/      # 历史清理工具
├── scripts/
├── fs-bi-crm-report-web/      # 核心 WAR
│   └── src/main/
│       ├── java/com/facishare/bi/
│       │   ├── portal/        # 门户 API 控制器（Dashboard/View/订阅/对象分析）
│       │   ├── portal/repository/  # ViewDataQueryRepository（HTTP RPC 门面）、ViewQueryRepository
│       │   ├── portal/rpc/         # BIDEVResource / BIUDFResource / FSBIResource（@RestResource HTTP 客户端）
│       │   ├── portal/plugin/      # @ApiUserInfo / @ApiAccessLog（用户注入、访问日志）
│       │   ├── backstage/     # 后台管理
│       │   ├── midware/jobcenter/  # 任务中心导出控制器
│       │   ├── api/rest/      # REST 控制器（Report/DashBoard/Stat/Permission/SchRun）
│       │   ├── service/       # 业务服务
│       │   ├── dao/           # MyBatis Mapper（mapper/tenantmapper/dynamicmapper）
│       │   ├── repository/    # 仓储
│       │   ├── clickhouse/    # ClickHouse 访问
│       │   ├── report/ dashboard/ databoard/ stat/ favorite/ downstream/ datasync/ behavioralanalysis/
│       │   ├── rpc/ thirdparty/ outenterprise/   # 外部集成
│       │   ├── aop/ context/ exception/ helper/ util/ common/ config/ dto/ entity/ model/ typehandler/
│       │   └── job/ event/ component/ permission/ i18n/
│       └── resources/
│           ├── applicationContext.xml
│           ├── spring/spring-*.xml     # dubbo/db-pg/db-clickhouse/cms/aop/idcheck/navigation
│           ├── mybatis/                # PG + ClickHouse 映射（含 Tenant 租户版）
│           ├── chmapper/ pgmapper/     # CH/PG 专用 Mapper
│           ├── i18n/                   # 多语言 properties
│           └── logback*.xml
└── fs-bi-crm-report-api / third-party
```

## 四、代码模块详细构成

### 1. 核心业务模块
- **报表（Report）**：`ReportRestController`、`ReportService`、`RptViewService`、`ReportFilterService` —— 报表定义、过滤器、版本管理
- **仪表盘（Dashboard）**：`DashBoardRestController`、`DashBoardSyncController`、`dashboard/*` —— 仪表盘 CRUD 与同步
- **视图（View）**：`ViewDataQueryApiController`、`ViewDetailDataQueryApiController`、`ViewListApiController`、`ViewQueryApiController`、`RptViewService` —— 视图数据查询/明细/列表
- **订阅/分享**：`SubscriptionController`、`ViewCategoryBatchSubscribeService`、`ViewCategoryBatchForwardService`、`ScanAndSendJobService`、`SchRunService`（调度运行）—— 定时订阅推送、邮件
- **导出**：`BiRptExportController`、`BiSchExportController`、`BiStatDetailExportController`、`BiSaleProcessExportController`（任务中心）+ `ExportAllPermissionsService`
- **权限**：`PermissionRestController`、`ViewPermManagerService`、`DynamicChartPrivatePermissionMapper`、`ExportAllPermissionsService`
- **排行榜/看板**：`BillBoardService`、`databoard/*`
- **行为分析**：`behavioralanalysis/*`、`BiUserViewHistory`（浏览历史）
- **i18n/翻译**：`I18nApiController`、`TranslationTableDataQueryApiController`（配合 solution-design 的多语言方案）

### 2. 公共基础模块
- `common`：缓存封装（`common.cache`）、常量、`ApplicationContextHolder`
- `exception`：`BiBizExceptionHandler`、`ApiExceptionHandler` 统一异常处理
- `aop`：切面（权限/日志/翻译）
- `helper` / `util`：`DateFormatUtil`、`ChineseUtil` 等
- `event`：领域事件；`rpc`：Dubbo 消费封装；`thirdparty`：三方集成

### 3. 数据层设计
- **PostgreSQL**：报表/视图/订阅/权限等业务元数据（`spring-db-postgresql.xml`、`spring-db-postgresql-system.xml`，MyBatis）
- **ClickHouse**：报表统计数据/明细数据（`spring-db-clickhouse.xml`、`mybatis-clickhouse-config.xml`、`chmapper`）
- **Mongo**：Morphia 用于部分文档数据（依赖 `mongo-java-driver`）
- **Redis/Ehcache**：缓存（`common.cache`）；`ResourceLock` 资源锁
- **MQ**：事件（`WarehouseEventProducer` 等）

### 4. 权限、认证、鉴权
- 认证：FCP 网关透传用户/企业 Header，应用层通过 `context` 读取
- 数据权限：`fs-bi-permission.xml`（`permission-context/fs-bi-permission.xml`）+ `PermissionService`（组织架构 5.7）+ `ViewPermManagerService`
- 图表私有权限：`DynamicChartPrivatePermissionMapper`；导出全量权限校验：`ExportAllPermissionsService`

## 五、用到的全部框架 & 第三方组件清单

| 组件 | 作用 |
| --- | --- |
| Spring MVC / Spring | Web 层与 IoC（XML 装配） |
| MyBatis | 持久层（PG/CH 双数据源，租户级 Mapper） |
| Dubbo | 服务 RPC（多注册中心 queryZk/commonZk） |
| ElasticJob | 分布式定时任务（elastic-job-api-core + Curator/ZooKeeper） |
| Mongo + Morphia | 文档数据存储 |
| Ehcache / Redis | 缓存 |
| jTDS | SQL Server 驱动（兼容老 CRM 数据源） |
| Freemarker | 模板渲染 |
| fastjson | JSON 序列化 |
| Druid | 连接池 |
| Lombok / CGLIB / Objenesis | 样板代码 / 代理 |
| 内部 SDK | fs-bi-cache、fs-bi-metadata-context、fs-bi-api、fs-message-api、fs-open-email-proxy-api、fs-restful-server、gray-release、core-filter |

## 六、核心业务流程拆解

### 1. 报表数据查询
```
ViewDataQueryApiController / ViewDetailDataQueryApiController
  → service（RptViewService / ViewCategory* 组装查询参数）
  → 权限校验（ViewPermManagerService）
  → Dubbo IQueryService（报表查询服务，queryZk）
  → 返回查询结果（ClickHouse 数据 + PG 元数据组装）
```

### 2. 订阅与定时推送
```
SubscriptionController（订阅配置）
  → ViewCategoryBatchSubscribeService（批量订阅）
  → SchRunService / ScanAndSendJobService（调度执行）
  → 查询快照（IQueryService）→ 邮件（EmailService 代理）/ 企信推送（PushSessionService）
  → 记录 SchRun 运行存储（SchRunStorageMapper）
```

### 3. 导出链路
```
前端 → BiRptExportController / BiSchExportController（任务中心）
  → 导出服务（ExportAllPermissionsService 校验权限）
  → 生成文件（FileService / StoneFileService）→ FilePackedService 打包 → 推送/下载
```

## 七、配置与环境

- **配置类型**：`applicationContext.xml`、`spring/spring-*.xml`（dubbo/db/cms/aop/navigation/idcheck）、MyBatis XML、`logback.xml` / `rmq.logback.xml`、i18n properties
- **多环境**：CMS 配置中心下发差异配置；`spring-cms.xml` 加载；多语言按 locale 文件
- **注册中心**：`queryZk`（报表查询服务）、`commonZk`（公共）、`queryOrgStruct`（组织架构）—— 地址由配置中心下发
- **构建**：Maven；sonar 扫描；`pom.xml.versionsBackup` 存在版本回退备份

## 八、项目优缺点 & 风险点

**优点**
- 报表域模型完整（报表/视图/仪表盘/订阅/导出），业务边界清晰
- 查询与展示解耦：数据查询下沉 Dubbo `IQueryService`，本服务专注报表管理与展示
- 租户级 MyBatis Mapper 体系成熟（`tenantmapper`/`Dynamic*TenantMapper`）
- 有 solution-design 多语言改造方案沉淀，说明团队重视设计评审

**现存问题/技术债务**
- `fs-bi-crm-report-manage` 为无源码空壳模块（POM 仍声明 war），建议清理
- `pom.xml.versionsBackup`、`pom.superpowers-snippets.xml` 等杂项文件入库，属维护噪声
- 目录存在 `java.io.tmpdir` 误入工作区
- 依赖大量内部 SNAPSHOT SDK，升级/联调成本高
- README 描述的「query 模块」与实际模块名不一致（文档与代码漂移）

**接手改造注意事项**
- 新增接口优先复用 `portal/api` 分层与统一异常处理
- 查询能力尽量走 `IQueryService`，避免直接穿透 ClickHouse
- 修改 MyBatis 租户 Mapper 需同时验证 Tenant 与系统两套映射

## 九、需要补充核查的内容

- [ ] `fs-bi-crm-report-manage` 的历史用途与是否可删除
- [ ] `IQueryService` 的实际提供方工程（fs-bi-stat 或独立查询服务）与契约
- [ ] 生产环境 PG/CH 分库分表与租户路由细节（数据源配置在配置中心）
- [ ] Mongo 具体存储的文档集合与用途
- [ ] 数据库 DDL 与索引（仓库无集中 SQL）
- [ ] 部署拓扑（Tomcat 实例数、网关路由、与 fs-bi 的部署关系）
- [ ] 容器化 / CI 流水线（仓库内未见）
- [ ] 订阅推送的 MQ 主题与 ElasticJob 分片策略配置

---

## 十、代码走读路线（API → 数据层 / 下游服务，最完整力度）

> 文件路径均相对仓库根 `/Users/muqingji/code/serve/fs-bi-crm-report`（默认在 `fs-bi-crm-report-web/src/main/java` 下）。

### 走读路线 A：报表数据查询（门户 API → 下游 HTTP RPC → 数据层）

```
前端 / FCP 网关
  │ POST /api/v1/view/data/query（ViewDataQueryArg + @ApiUserInfo）
  ▼
① Controller 层
  com/facishare/bi/portal/api/ViewDataQueryApiController.java
  └─ query()（第 43 行，另有 /default、/queryLwtViewData、/queryPivotReportData、/queryMultiDimViewData）
       ├─ @ApiAccessLog：访问日志切面
       └─ viewDataFacadeService.query(userInfo, arg)

② Facade 服务层（门户门面）
  com/facishare/bi/portal/service/ViewDataQueryFacadeService.java
  └─ query()（第 95 行）
       ├─ TraceContext 写入 ea / ei / employeeId / uid（链路追踪）
       ├─ viewQueryRepository.getRptView(userInfo, viewId)
       │    → ViewQueryRepository.getRptView（portal/repository/ViewQueryRepository.java:40）
       │       → RptViewRepository.getViewByID(viewId, ei)（本地 PG，MyBatis）
       ├─ 报表类型判断 RptTypeEnum.RPT
       ├─ bindRptFilterLists()：请求筛选器与报表默认筛选器合并（getRptFiltersResult）
       ├─ 组装 QueryReportDataArg（viewId/filterList/page/showMode/isView=1/refresh/默认筛选选项）
       ├─ viewDataQueryRepository.queryReportData(userInfo, arg)
       │    → ViewDataQueryRepository.queryReportData（portal/repository/ViewDataQueryRepository.java:55）
       │       ├─ arg.setQuerySource(FromEnum.FUNCTION)
       │       └─ biudfResource.queryReportData(arg, RpcHeaderUtils.toHeaderMap(userInfo))   ★下游 RPC
       └─ 结果适配：
            ├─ viewDataBeanMapper.toPage / toDataSet（portal/bean/copy）
            └─ viewDisplayFieldBeanMapper.toDisplayFields
       → ApiResult<ViewDataQueryResult>

③ 下游 RPC（HTTP）
  com/facishare/bi/portal/rpc/BIUDFResource.java
  └─ @RestResource(value="BI-UDF-REPORT", contentType="application/json")
       @POST(value = "/rptUdfViewDataController/queryReportData", desc="查询自定义报表")
       → udf-report 服务 /rptUdfViewDataController/queryReportData
          （后续链路见《fs-bi-udf-report-架构分析.md》走读路线 A：
           RptUdfDataController → UDFRptReportDataService → SQLEngine → QueryServiceAdapter
           → SqlEngineClient → fs-bi-sqlengine → ClickHouse/PostgreSQL）

④ 本地数据访问示例（报表定义，PostgreSQL）
  - Mapper 接口：com/facishare/bi/dao/mapper/RptViewMapper.java
    └─ @Select / @SelectProvider 注解 + 动态 SQL：
       ├─ getAllEi()：select distinct ei from rpt_view ...
       ├─ getCategoryIdByViewId(...)：rpt_view 分类
       └─ RptViewSqlBuilder.buildGetCategoryIdByFilter（mapperbuilder/RptViewSqlBuilder.java）
  - XML 映射：src/main/resources/mybatis/DynamicRptViewMapper.xml / DynamicRptViewMapperTenant.xml（租户版）
  - 数据源装配：src/main/resources/spring/spring-db-postgresql.xml（PG）+ spring-db-clickhouse.xml（CH）
```

### 走读路线 B：统计图查询（另一条下游）

```
POST /api/v1/view/data/queryMultiDimViewData / default
  → ViewDataQueryFacadeService.queryViewData()
       ├─ viewQueryRepository.getStatView()（本地 PG：stat_view）
       ├─ bindStatFilterLists()：统计图筛选器（FSBIResource.queryFiltersResult）
       └─ viewDataQueryRepository.queryChartData(arg, userInfo)
            → FSBIResource.queryChartData（portal/rpc/FSBIResource.java）
              → fs-bi-stat 统计图查询内核（easy-stat，见 fs-bi 走读路线 A/B）
```

### 走读路线 C：大宽表（LWT）查询（拼表场景）

```
POST /api/v1/view/data/queryLwtViewData
  → ViewDataQueryFacadeService.queryLwtViewData()
  → viewDataQueryRepository.queryLwtData(arg, userInfo)
       → BIDEVResource.queryLwtData（portal/rpc/BIDEVResource.java）
         @POST("/lwt/query") → dev-platform /lwt/query
         （后续链路见《fs-bi-dev-platform-架构分析.md》走读路线 A）
```

### 走读路线 D：订阅/调度运行（SchRun）

```
POST /api/v1/subscribe/...（SubscriptionController，portal/api/SubscriptionController.java）
  → 订阅配置：ViewCategoryBatchSubscribeService（批量订阅）
  → 调度运行：SchRunService / SchRunStorageRepository
       └─ Mapper：com/facishare/bi/dao/mapper/SchRunMapper.java、SchRunStorageMapper.java
          XML：resources/mybatis/DynamicSchRunMapper.xml、DynamicSchRunStorageMapper.xml（PG）
  → 推送：MailService / SchStorageMailService（邮件）、PushSessionService（Dubbo 企信推送）
  → 查询快照：复用 BIUDFResource/FSBIResource（报表/统计图查询）
```

### 走读路线 E：导出（任务中心）

```
BiRptExportController / BiSchExportController（midware/jobcenter/web/controller/）
  → ExportAllPermissionsService（全量权限校验）
  → FileService / StoneFileService（文件生成）
  → FilePackedService（Dubbo：文件打包）→ 下载/推送
```

### 关键文件清单（走读速查）

| 环节 | 文件 |
| --- | --- |
| 图表查询 API | `fs-bi-crm-report-web/src/main/java/com/facishare/bi/portal/api/ViewDataQueryApiController.java` |
| 门户门面 | `fs-bi-crm-report-web/src/main/java/com/facishare/bi/portal/service/ViewDataQueryFacadeService.java` |
| RPC 门面 | `fs-bi-crm-report-web/src/main/java/com/facishare/bi/portal/repository/ViewDataQueryRepository.java` |
| 下游 HTTP 客户端 | `fs-bi-crm-report-web/src/main/java/com/facishare/bi/portal/rpc/{BIUDFResource,BIDEVResource,FSBIResource}.java` |
| 本地报表 Mapper | `fs-bi-crm-report-web/src/main/java/com/facishare/bi/dao/mapper/RptViewMapper.java` |
| 本地报表 XML | `fs-bi-crm-report-web/src/main/resources/mybatis/DynamicRptViewMapper.xml` |
| 订阅 | `fs-bi-crm-report-web/src/main/java/com/facishare/bi/portal/api/SubscriptionController.java` |
| 调度运行存储 | `fs-bi-crm-report-web/src/main/java/com/facishare/bi/dao/mapper/SchRunStorageMapper.java` |
| 导出 | `fs-bi-crm-report-web/src/main/java/com/facishare/bi/midware/jobcenter/web/controller/BiRptExportController.java` |
