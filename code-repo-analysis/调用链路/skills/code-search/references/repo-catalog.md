# 业务仓库索引（repo catalog）

本表是 `code-search` 的入口索引：把「业务 / 服务 / 模块名」落到「仓库 → sourcebot `--repo` → ai-wiki 领域知识路径」。

> 本文件由 `scripts/gen-repo-catalog.py` 生成，**请勿手工编辑**。
> 重新生成：`uv run --no-sync python scripts/gen-repo-catalog.py`；
> 校验漂移：`uv run --no-sync python scripts/gen-repo-catalog.py --check`。

## 怎么用

| 你要做的事 | 怎么做 |
| --- | --- |
| 读某仓领域知识 | 打开 `<ai-wiki-root>/domains/<仓库 name>/README.md`，按页内「按任务路由 / 按读者场景导航」进具体页 |
| 找术语 / 类名对应代码 | 该仓根目录 `glossary.md`（如有），条目自带 `path#Lx-Ly` 行锚，可直接喂 `read-file --path --offset` |
| 搜真源码 | `uv run --no-sync python scripts/sourcebot-cli.py grep --repo "<name>" --pattern ... --compact` |
| 只有 app / bizName | 按下方「怎么定位仓库」的规则解析；解析不出即**停**，用 `list-repos --query` 兜底，禁止猜 |

## 怎么定位仓库与知识页

- **仓库 name = ai-wiki 目录**：`<ai-wiki-root>/domains/<name>/`，`name` 同时就是 sourcebot `--repo` 的值。
- ai-wiki 域目录 = gitUrl 最后两段 `<group>/<project>`（项目段去 `.git`）；
  `projects.json` 的 `aiWikiDomain` 只是声明式别名，**不参与路径推导**，不要用它拼路径。
- **app / bizName ≠ 仓库名**：部署单元名常带 `-service` / `-provider` / `-wq` / `-job` / `-web` / `-server` 后缀；
  解析顺序 ① 精确匹配下表 name → ② 匹配 project 段 → ③ 去上述后缀再匹配 project 段。
  命中 **0 个或多个即停**（多命中 = 猜）；解析不出时用 `sourcebot-cli.py list-repos --query <name> --compact` 兜底。

## 主索引

| 仓库 name（= ai-wiki 目录 = sourcebot `--repo`） | 这是做什么的 |
| --- | --- |
| `AppServer/auditlog` | 全平台通用审计日志的写入入口、异步削峰、多介质存储路由与跨租户审计检索。 |
| `AppServer/checkins` | checkins 是外勤统计的读侧服务（Java WAR，消费品业务技术外勤组维护，服务等级 L2）：对签到/外勤明细做统计、报表、导出与企业数据大屏聚合。它不负责打卡写入（MobileLogic.createCheckins 已废弃），… |
| `AppServer/fs-ai-detector` | fs-ai-detector 是消费品业务线的图像 AI 检测编排服务：端侧 SDK 与内部业务发来检测/分类请求，服务按模型配置（ModelPo.platform）路由到外部算法平台，统一返回识别框并落库缓存。war 形态部署，单进程同… |
| `AppServer/fs-ai-hub-wq` | fs-ai-hub-wq 是「FS AI Hub」的工作副本：纷享官方 AI 开发工具生态中心（README.md#L1-L9），交付 Agent Skills 制品（72 个 skills/<name>/ 目录）与仓级治理工具链（boo… |
| `AppServer/fs-appserver-checkins-office-v2` | 5.4新版考勤代码 (End of file - 1 lines total) |
| `AppServer/fs-appserver-checkins-v2` | 本仓库是纷享销客 CRM 的"外勤打卡"子域后端，核心职责是：接收移动端/Web 端的打卡计划创建、路线排程、外勤规则查询等同步 RPC 请求（由 checkins-v2-server 通过 Dubbo 协议发布 5 个 provider… |
| `AppServer/fs-appserver-common-tools` | 本仓定位总览：纯静态工具 JAR（无服务入口/无 MQ/无 HTTP 出口）寄生于宿主 FCP 请求线程，提供 FCP 上下文取值与埋点组装、环境与专属云路由、日期时区灰度等能力。给出推荐阅读顺序、主干速记与无测试仓库的验证入口。 |
| `AppServer/fs-appserver-holiday-v2` | fs-appserver-holiday-v2（假期助手重构）是消费品外勤场景的假期领域服务：管理请假/加班字典与企业规则、执行时长校验与自动计算、按审批事件维护年假/调休余额账本，并向考勤侧提供请假明细 Dubbo 回查。审批流引擎、组… |
| `AppServer/fs-appserver-schedule` | 本仓是日程领域的唯一所有者：日程增删改与循环展开、参与人与提醒变更、日历/小日历视图聚合、冲突检测、共享日历规则与人员时区解析。单 WAR 三入口（Dubbo / HTTP 双 Servlet / 异步 MQ），Mongo + Redis… |
| `AppServer/fs-crm-fmcg` | 快消 CRM 主服务（Java 21 / Spring MVC WAR）。事实以源码为准；Pod/PV 数字是 2026-09-13 运行期背景。 |
| `AppServer/fs-crm-fmcg-sales` | 快消销售域 PaaS 插件：对账单 / 条码 / 稽查。同 JVM 前台 WAR 同时承载 RESTEasy /API、MVC /FMCGSales/API/ 与两个 RocketMQ consumer。 |
| `AppServer/fs-crm-fmcg-wq` | FMCG 外勤服务端扩展包知识入口。 |
| `AppServer/fs-fmcg` | fs-fmcg 承担“快消行业 AI 能力中台 + TPM/计费业务后端”：对外编排门头识别、活体检测、通用与批量识别 fs-fmcg-service/src/main/java/com/facishare/fmcg/service/co… |
| `AppServer/fs-fmcg-ai` | FMCG（快消）销售助手的 AI 场景编排服务：聚合 CRM 上下文 → 调用外部 AI → 渲染卡片。单模块 Maven 工程 fs-fmcg-ai-server。 |
| `AppServer/fs-fmcg-business-platform` | 负责什么：这是纷享销客快消行业的单体 Spring Boot 后端（Java 21，pom 聚合七个子模块，可 WAR 外置 Tomcat）。 |
| `AppServer/fs-fmcg-efficiency` | 本仓库是纷享 FMCG 的「终端拜访效率与稽核」单体服务，以 Tomcat WAR 运行（Spring MVC 3.x + 纯 XML 装配 + Dubbo，明确非 Spring Boot）（pom.xml#L11-L15）。 |
| `AppServer/fs-fmcg-framework` | 本仓是快消 / FMCG 业务线的调用侧 HTTP（+ 少量 Dubbo）SDK：把远端 PaaS、业务服务与公网能力收敛成可注入的代理接口，供宿主应用在进程内同步调用。它不负责部署、鉴权决策、持久化或消息总线。 |
| `AppServer/fs-fmcg-public-abutment` | fs-fmcg-public-abutment 是快消订货对外适配/客开集成层（Abutment），打 WAR 包，不持有主数据，所有读写经 PaaS 代理回写到对方系统。 |
| `AppServer/fs-fmcg-sales` | 快消销售订单系统，基于纷享销客 PaaS 平台构建，管理快消行业的销售订单、出库配送、库存、支付、促销、TPM 费用等业务（见 README.md）。三模块单 war 服务：api 定契约、provider 做业务、cgi 装配并暴露 f… |
| `AppServer/fs-fmcg-sdk` | 本仓库是嵌入式二方包而非独立服务：根 pom.xml#L7-L13 聚合唯一子模块 fs-fmcg-sdk-ai（fs-fmcg-sdk-ai/pom.xml#L12-L15 为 jar），宿主应用 import fs-fmcg-sdk-… |
| `AppServer/fs-fmcg-vision` | fs-fmcg-vision（纷享销客 FMCG 视觉 AI 识别中台）是面向快消、能源、零售等场景的视觉识别服务，从图片 / PDF / Excel / 视频中提取结构化业务数据。 |
| `BaseService/er-manager-all` | 本仓是互连（Open API）平台的管理控制面（非网关本身）。 |
| `BaseService/fs-enterprise-relation` | 企业互联关系服务（GitLab 517，L0）：跨云企业关系主数据、互联登录鉴权（authForCep）、通用对象 REST 接入面与跨云数据同步的 owner。本知识包回答「这段代码在互联域里负责什么、边界在哪、失败时调用方看到什么」。 |
| `BaseService/fs-organization` | fs-organization 是微客（FXiaoKe/Facishare）SaaS 平台的组织架构主数据服务，负责部门树 CRUD、员工（人员）生命周期、上下级汇报链、部门负责人/成员关系、星标、拼音关键字搜索及版本增量同步；它不负责身… |
| `BaseService/hospital-spider` | 本页是检索入口：先按你的问题类型找行，再跳到对应页。每页都自带「必须守住的不变量」与「未知与边界」两节，跳转后建议先看这两节。 |
| `BaseService/sync-data` | sync-data 是一个跨租户数据同步中间件，运行在纷享销 CRM 体系内，负责在不同租户（source → destination）之间同步业务对象数据。核心场景是 CRM 的"互联"功能：一个租户的业务对象变更后，自动同步到另一个租… |
| `BizCommon/async-job-center` | async-job-center 是异步导入/导出任务中心：多模块 Maven 服务，承接高 PV 的任务创建、分发、心跳与完成回调。 |
| `BizCommon/client-action-router` | client-action-router 是移动端灰度路由系统，支持按终端类型、版本号、企业 ID 等多维条件进行路由匹配。 |
| `BizCommon/egress-api-service` | egress-api-service：公司业务生态的出口能力聚合层（短信/邮件/查询/地图/AI/短链），统一密钥、限流配额与记账。3 个部署单元（API 35 Pods / Gateway 19 Pods / 通知推送 7 Pods），… |
| `BizCommon/fast-notifier` | fast-notifier 提供 room 粒度的实时消息推送：业务方用 notifier-support SDK 发消息（只搬运 Message.content 不透明字符串），服务端 notifier-server 经 Socket.… |
| `BizCommon/feature-flag` | 三模块（common/client/service）组成的功能开关平台：业务进程内 SDK 本地评估（热路径零 RPC）、feature-service 管理面+数据面、PostgreSQL/企业 Mongo/RocketMQ 支撑跨集群… |
| `BizCommon/fs-biz-log` | 负责：本仓库只承担"日志契约 + 发送薄壳"。 |
| `BizCommon/fs-crawl-provider` | .wiki/references/ 下 architecture/contracts/invariants/configuration 为 Agent 策展背景，claims 仍以源码为准。 |
| `BizCommon/fs-desensitization-service` | 本仓库只有一个可部署产物：根 pom.xml（packaging=pom）聚合 fs-desensitization-console，后者打 WAR、contextPath 为 desensitization-console，跑在 Spr… |
| `BizCommon/fs-disconf` | 1. overview.md — 做什么与双入口 |
| `BizCommon/fs-egress-proxy` | 本仓库（egress-proxy-service）用一个 Spring Boot 进程 EgressProxyApplication.java:12-18(src/main/java/com/fxiaoke/egress/EgressPr… |
| `BizCommon/fs-file-datax` | 改备份消费 / 停车场 / BatchInsert 前先读增量与停车场两页；改回填开关前读 configuration；动 GC 删除条件前读 domain-gc。不要把 references 原文搬进业务代码注释当事实源——以源码行锚为… |
| `BizCommon/fs-file-preview` | 本仓库是统一文件预览网关：只做身份解析、按扩展名路由、拼第三方预览 URL 和给预览引擎回源字节；不渲染文档、也不长期持有文件（转换/渲染归 Office Online Server、OnlyOffice DS、PDF.js 静态资源、腾… |
| `BizCommon/fs-file-process` | fs-file-process |
| `BizCommon/fs-file-server` | 面向接手多租户文件接入链路的后端与排查签名/ATS/分片问题的 SRE。 |
| `BizCommon/fs-gray-release` | 本库（com.fxiaoke.common:fs-common-gray-release）是纯 Java 灰度放量库：无入口、无 Spring 依赖，FsGrayReleaseBiz 单例提供 isAllow(rule, euid) 主线… |
| `BizCommon/fs-hubble` | BizCommon/fs-hubble 是全局搜索中台，包含两个核心 Java 服务： |
| `BizCommon/fs-i18n` | 该 fs-i18n 是企业多语基础设施 monorepo。 |
| `BizCommon/fs-mq-router` | 把「发送前」的 RocketMQ 目标选择收口成一个可嵌入宿主进程的纯 Java 库：显式 routingKey 选 TopicGroup、显式 flowKey 做 Topic 分级降级、声明序选可用 producer、queueHash… |
| `BizCommon/fs-stone` | 职责边界：fs-stone 是 FaciShare 文件服务的多模块 Maven 聚合工程（pom.xml#L17-L39），只管"对象字节存取、元数据、图像/音频派生"。 |
| `BizCommon/fs-stone-common` | fs-stone-common 为业务仓提供进程内文件签名 URL、上传删除与 ASK/配额客户端能力。它是 Maven 双模块库（lib 契约 + client I/O），不是可部署服务：无 Controller、无独立运行时指标面。 |
| `BizCommon/jdbc-sql-stat` | 该库是旁路式 JDBC SQL 统计采集库。 |
| `Infrastructure/fs-active-session-manage` | fs-active-session-manage（ASM）是公司统一的会话校验服务，为 31+ 业务仓提供 Cookie → 身份校验、会话生命周期管理与跨进程缓存失效广播。 |
| `Infrastructure/fs-app-view` | （暂无 ai-wiki 领域知识） |
| `Infrastructure/fs-document-converter` | 文档转换服务，含两个独立部署的 war 模块：同步预览（fs-document-convert-web）与大文件异步解析（fs-document-convert-web-big）。 |
| `Infrastructure/fs-dubbo-rest` | fs-dubbo-rest 把 Spring 容器里的 dubbo 接口（或 @RestProvider bean）自动注册成 Spring MVC URL，用 JSON over HTTP 完成 RPC。唯一交付物是 fs-dubbo-… |
| `Infrastructure/fs-experience-account` | 服务：fs-plat-sandbox-provider（L2，PaaS 业务平台开发平台组，负责人 王亚豪） |
| `Infrastructure/fs-fcp` | fs-fcp：嵌入宿主的 FCP 协议 SDK（服务端 + 客户端 + 可选文件会话）。 |
| `Infrastructure/fs-mq-bus` | fs-mq-bus（com.facishare:fs-mq-bus）是多租户消息总线，负责将来自源头 RocketMQ topic 的消息按租户路由到不同目标环境 producer。 |
| `Infrastructure/fs-plat-service` | 基于 pom.xml 的领域分析。 |
| `Infrastructure/fs-user-extension` | 本仓是 UI PaaS 用户侧扩展后端（Java 多模块：api/biz/provider），负责个人菜单、页面模板 CRUD、应用导航、启动页、用户组、客户端页面数据组装与变更通知。 |
| `Infrastructure/fs-user-login` | fs-user-login 是公司 PaaS 业务平台的用户登录与鉴权服务聚合仓，包含 5 个 Maven 模块，覆盖传统 CGI 遗留链路和新业务链路。 |
| `JavaCommon/core-filter` | Servlet Filter 观测库：TraceContext、编码纠正、可选 GZip、PV/慢请求、灰度染色。不承载认证鉴权。 |
| `JavaCommon/dubbof` | dubbof（GitLab Project ID 95）是内部长期维护的 Apache Dubbo 2.9.5 源码分支发行版，属于框架/底层基础设施库（layer: lib，category: java-lib）。全公司微服务通过 fx… |
| `JavaCommon/fs-circuit-breaker` | fs-circuit-breaker 是 JavaCommon 仓库下的纯 Java 熔断器库（v4.0.1），groupId com.fxiaoke.circuit.breaker。它同时承担两个职能： - 失败熔断：连续失败数或失败率… |
| `JavaCommon/fs-es-support` | fs-es-support 是面向内部业务服务的 Elasticsearch 客户端 SDK：用配置中心驱动 RestClient/HLRC（及 es8 Java API Client）装配，并提供可选的同步读写封装与多租户工厂。它不是 … |
| `JavaCommon/fs-file-system` | 单模块 Spring Boot 文件中台：Protostuff + REST 双协议入口，按 clusterEnv 条件装配 S3/FastDFS/Mongo，覆盖上传下载、秒传、图片派生与 GC。 |
| `JavaCommon/fs-grpc-support` | fs-grpc-support（com.fxiaoke.common:fs-grpc-support:2.0.0）是 gRPC 调用链埋点支撑库：六个主类把 rpc-trace 的 TraceContext 织进 grpc-java 的服… |
| `JavaCommon/fs-idempotent-util` | 本仓是 Spring AOP 二方库，提供 JVM 进程内幂等调用与进程内方法级限流两大能力，以 Redis 为唯一外部协调存储。 |
| `JavaCommon/fs-kafka-support` | fs-kafka-support 是进程内 Kafka 客户端支撑库（发送队列 + 消费线程 + 配置驱动重建）。下面是全部页面与最短阅读路径。 |
| `JavaCommon/fs-mq-dispatcher` | fs-mq-dispatcher 知识页面索引 |
| `JavaCommon/fs-redisson-support` | 本库把「配置中心（AutoConf/CMS）驱动的 Redisson 客户端」收口成一个 Spring FactoryBean jar 交给宿主装配：XML 声明 RedissonFactoryBean 并设 p:configName，业… |
| `JavaCommon/fs-rocketmq-support` | 该仓库是 RocketMQ 5 的 AutoConf 封装库（见 pom.xml 描述与 src/main/java/com/fxiaoke/rocketmq/producer/AutoConfMQProducer.java#L56-L7… |
| `JavaCommon/fs-sentinel-support` | 本仓库只做 Alibaba Sentinel 的"公司内接入层适配"，不实现任何限流算法。 |
| `JavaCommon/fs-sql2esdsl` | 本仓库是一个嵌入宿主进程使用的 jar 库（pom.xml#L10-L19：packaging=jar、ES 7.3.2），不是独立服务：全仓无启动类、无 HTTP 层、无 Spring 注解，能力经 IDataService 暴露，由宿… |
| `JavaCommon/gray-release` | 一句话：进程内 JVM 灰度判定库——给一个业务集 bid、规则名和实体 id，回答「这个实体现在进灰度了吗」；配置的产出与下发在库外（autoconf），本库只做读侧判定与热更新缓存。 |
| `JavaCommon/http-spring-support` | 本库是 OkHttp 的 Spring 出站 HTTP 客户端支撑库（jar，无服务端、无自动装配），叠加配置中心、熔断/限流、链路追踪与内外网治理。 |
| `JavaCommon/jdbc-support` | jdbc-support 是纷享销客平台的 JDBC 门面组件：按次取连接、回调式 SQL、自动释放，并叠加熔断、Trace 与慢 SQL 统计。它是嵌入宿主的 jar，不是独立服务。 |
| `JavaCommon/jedis-spring-support` | 面向接入排障的阅读地图：先 overview 与 quickstart，再 architecture，后进入装配、拓扑、命令流、路由、Cache/锁与测试页。 |
| `JavaCommon/jutil` | jutil 是编译期以 com.fxiaoke.common:java-utils 被业务服务以 Maven 依赖引入的纯工具库：AGENT.md 明确"library project, so there is no main appli… |
| `JavaCommon/mongo-spring-support` | 本库是 CMS 驱动的 Mongo 与 Morphia 访问支撑知识入口，统一出口为 DatastoreExt 动态代理；建议按接入排障、库边界、装配热更分片熔断与一次 CRUD 主路径顺序阅读。 |
| `JavaCommon/mybatis-spring-support` | 本库是公司级 MyBatis 访问层封装（JavaCommon），在 MyBatis-Spring 之上提供动态数据源路由（主从/分片/多租户）、读写分离、通用 CRUD、慢查询审计与错误熔断，被全公司 161 个仓引用。本页回答"从哪读… |
| `JavaCommon/oss-metrics` | 公司级公共度量与日志收集底座，内嵌业务 JVM 运行（非可运行服务），提供四类能力：Dropwizard 指标采集与 Prometheus /metrics 端点、每分钟定时上报（J4Log + Kafka）、Logback 日志 Kaf… |
| `JavaCommon/parent-pom` | 本仓库是纷享销客 Java 体系的 Maven 父 POM 版本治理中心，只负责通过 dependencyManagement 与 pluginManagement 锁定约 180 项第三方及内部组件版本、统一编译/测试/静态分析插件配置… |
| `JavaCommon/rabbit-support` | rabbitmq-support 把 CMS 远程 Spring XML 与 spring-rabbit 封装成宿主可声明的 FactoryBean 动态代理，并提供消费 SPI。本仓无对外 HTTP/RPC 服务。 |
| `JavaCommon/rpc-trace` | rpc-trace（com.github.colin-lee:rpc-trace:5.7.2）是被全公司 183 个业务仓内嵌的服务调用监控 SDK（Java 8，单 Maven 模块）。它在业务应用 JVM 内以 AOP 环绕拦截服务方… |
| `JavaCommon/shiro-spring-support` | 面向业务仓开发者与平台工程师的 Shiro-CAS 整合库知识导航。本库为嵌入式 JAR，无独立对外 HTTP 服务。 |
| `Qixin/JavaServiceConsole` | JavaServiceConsole 是纷享销客内部研发快捷控制台：把 40+ 业务系统的 REST 接口聚合成一组 AngularJS 页面；服务端只做 CAS/Shiro 鉴权壳 + /proxy.do 透明 HTTP 代理 + 灰度… |
| `Qixin/fs-cep` | fs-cep 只做终端与后端之间的认证、鉴权、限流、加解密、路由与协议转换，不承载业务语义、不落库——fs-cep-provider/src/main/resources/META-INF/spring/dubbo.xml#L9-L18 … |
| `Qixin/fs-common` | 本仓库是 Java 8 的纯依赖库聚合工程（pom 打包、revision 5.3.2），六个 jar 由 CI 的 mvn deploy 推内网 Artifactory，供各业务服务在自己的进程内引用；它不提供可运行单元——全仓没有 *… |
| `Qixin/fs-cross-enterprise-sharedisk` | 本页为 repo-wiki 知识页（index）：知识导航入口。所有行锚可回源码复核。 |
| `Qixin/fs-customer-component` | PaaS 客户侧组件库（PWC）仓库知识入口。 |
| `Qixin/fs-fsc` | fs-fsc 是文件域的 HTTP 与 Dubbo 门面：把销客/百川用户文件、全局文件、CDN 文件、共享文件、头像、富文本与验证码收敛成 /FSC/{area}/{servlet}/{action} 的三级路由与三个 Dubbo 服务… |
| `Qixin/fs-fsi-proxy` | fs-fsi-proxy 是 FSI（protobuf over HTTP）远程调用的客户端存根库。接入方在 Spring 容器里 import 一份 Bean 定义文件，@Autowired 到的接口实例就是本仓生成的 JDK 动态代理… |
| `Qixin/fs-netdisk` | fs-netdisk（飞书网盘）是企业网盘的元数据 + 权限控制面微服务，核心职责： |
| `Qixin/fs-paas-wishful` | fs-paas-wishful：多 WAR PaaS 能力仓（记录 / OCR / 问卷支持 / 电子签 / 函数模板）。 |
| `Qixin/fs-qixin` | fs-qixin（纷享企信）是纷享销客生态的 IM 服务端：会话/消息/群组的核心存储与推送， |
| `Qixin/fs-qixin-bot-crm-helper` | 本仓是企信 CRM 助手的事件—消息中转层：把 CRM / 审批 / 阶段 / Feed 的事件， |
| `Qixin/fs-qixin-extension` | 首轮萃取产物，锚点回源码核验。 |
| `Qixin/fs-scheduler-task` | 本仓库是纷享 PaaS 侧的任务调度控制面（传统 WAR + Spring XML，无 Spring Boot 启动类）：fs-scheduler-task-provider 负责定时/周期任务与数据迁移（Migration）的登记、启停… |
| `Qixin/fs-uc` | 职责边界：fs-uc 是「用户中心」域服务，权威持有企业/员工版本(套餐)、账号与密码、登录属性、验证码、user token 这些数据；它不负责登录编排、权限、短信、会话——这些在 fs-uc-biz 里通过 organization-… |
| `Qixin/fs-warehouse-batch` | 本索引覆盖当前 run 已完成页面（pom.xml 工程 fs-warehouse-batch）。Steering 深文档见 references/，不重复列入下表。 |
| `Qixin/fs-webpage-customer` | 本知识包按「先定域、再看机制」的顺序组织。不要顺序通读——按下面的路由表直接跳到你需要的页。 |
| `ai/fs-ai-hub` | fs-ai-hub 解决什么问题：把纷享的 AI 开发能力沉淀为可分发的 Agent Skills——75 个技能（方法论 + 可执行脚本）以 Git 仓库为唯一分发中心，经 npx skills add 装进各 AI 编码客户端，在调用… |
| `ai/fs-ai-infra` | fs-ai-infra 是 AI 平台部署交付仓：Dify、Higress、OpenSandbox 三类核心加 OpenTelemetry 与 Langfuse 扩展入口，经 GitLab manual job 变量三元组走 Helm a… |
| `ai/fs-codeless-platform` | AI 驱动的零代码应用生成平台——当前仓库是规格/调研库，不是可运行服务。 |
| `ai/fs-llm-deploy` | fs-llm-deploy 维护 LLM 推理服务的部署配置与流量入口：GPU 宿主 compose 单元 + Nginx 网关清单 + 手工 CI。无业务主流程代码；唯一应用实现是 mxbai Flask rerank。 |
| `ai/fs-paas-n2ql` | 本仓是 NL2SQL 服务：把中文数据问题翻译成纷享销客 apiName SQL。以下按「你想解决什么问题」组织入口，每条给出该页能回答的核心问题。 |
| `ai/mcp-api-proxy` | 本仓库是「单进程双平面」的 MiniMax API 多凭证代理：数据面把 minimax-coding-plan-mcp 客户端发出的普通 HTTP 请求替换 Authorization 后转发上游，管理面提供配置后台。 |
| `appcenter-h5/h5-notification` | h5-notification（wechat connect notification）是微信互联通知公告的移动端 H5 详情页，承载两类页面应用： |
| `appcenter-h5/h5-wechatconnect` | 纷享销客「企业互联 → 通知公告」的移动端 H5 子应用（构建产物名 h5-mpadmin）。通过 open.wechatconnect 路由挂入主站，提供下游企业接收、上游发布管理、回复互动、催办提醒等全链路前端界面。 |
| `bi/crm-bi-custom-statistic` | bi/crm-bi-custom-statistic 是 CRM BI 自定义统计的结果生产端与核心计算引擎：消费 PaaS 对象变更（PG oplog），按聚合规则折算生成聚合指标与维度数据；同时维护一条面向 ClickHouse 的地… |
| `bi/fs-bi` | 数据源：bi/fs-bi develop 分支（5c2e73d）；Profile 为宿主只读背景，不作正文引用依据。 |
| `bi/fs-bi-ai-hub` | fs-bi-ai-hub 是 BI 团队的 Agent Skill 能力中心：11 个团队级 skill（Markdown 契约 + 少量可执行辅助）是一等交付物；仓内附带两个性质不同的应用树——自研的 product-learning-… |
| `bi/fs-bi-ai-native-workspace` | 本仓库是 BI 部门的「AI 原生协作工作区」，只承载文档正文与一个可执行 skill：需求/反讲/技术评审/开发计划/测试用例的 Markdown 产物存放在 iterations/{迭代}/stories/{需求}/{product,… |
| `bi/fs-bi-common-entities` | 本仓是 BI 报表/统计图域的纯契约 jar（com.facishare:fs-bi-common-entities）：定义入参、出参、枚举与常量，被 20+ 业务仓编译期依赖；不负责 Spring 装配、取数执行、SQL 编译和消息收发… |
| `bi/fs-bi-common-utilities` | 本仓库是 BI 报表链路中的纯静态工具 jar：把报表结果集降维为七槽 int 矩阵，并用 Kryo/GZIP（或 Java 原生）压缩编解码，供导出等下游消费。无 HTTP/RPC、无 Spring 启动。降维结果同时透传 snapsh… |
| `bi/fs-bi-crm-report` | 本仓库是 CRM BI 的报表接口层＋订阅/导出 Worker 宿主：负责报表、看板、统计图的新增、编辑、查询编排、订阅推送、分享、导出与权限装配（README.md#L1-L4、AGENTS.md#L4-L7）。 |
| `bi/fs-bi-dev-platform` | 本仓库是 BI「拼表/大宽表(LWT)」的开发态与运行态 Web 服务：以 war 形式挂在 Servlet 容器里（web.xml 只装配 DispatcherServlet，全仓无 *Application/*Bootstrap 主类… |
| `bi/fs-bi-export` | fs-bi-export 是一个无 Spring Boot 入口的单模块 WAR（pom.xml#L14-L16），靠 DispatcherServlet 装配（src/main/webapp/WEB-INF/web.xml#L28-L4… |
| `bi/fs-bi-goal` | 本仓库只做 BI「目标」域：目标规则与目标值的建模、多维校验、权限过滤、导入导出、启用前校验，以及组织架构变动后的目标值联动。 |
| `bi/fs-bi-industry` | 工商数据域双进程：interface 提供查询 REST，ods 做 CH→ES 清洗，api 模块是外部客户端 jar。 |
| `bi/fs-bi-pivot` | Python Flask 无状态 BI 透视/聚合计算旁路：吃上游明细，吐 JSON 结果。 |
| `bi/fs-bi-scheduler` | BI 调度 WAR：xxl-job/RocketMQ 驱动预刷，HTTP + Nomon 驱动数据稽核，失败以异步吞没为主。 |
| `bi/fs-bi-semantic` | fs-bi-semantic 是面向 BI 分析域的语义资产与查询适配单体服务（Java 21 + Spring Boot 2.7，打成 WAR 部署），负责 BI 语义初始化与构建、维度值召回补充、统一查数 API 与 NL→DSL→A… |
| `bi/fs-bi-stat-transfer` | 本仓库是 war 型传统 Servlet 应用，没有 Spring Boot 启动类（pom.xml#L15），进程由 web.xml 中 load-on-startup=1、映射 / 的 DispatcherServlet 拉起，上下文… |
| `bi/fs-bi-uitype` | fs-bi-uitype：BI UI 类型解析 WAR。从这里进入： |
| `bi/fs-bi-warehouse` | 按任务选择页面。总览见 overview，结构见 architecture。 |
| `bigfe/plugins` | 本仓库是 CRM 销售/CPQ 域「对象表单插件」的扩展集合，负责字段映射、表单渲染钩子与交互副作用：Web 侧 bom/attribute/priceservice/price_policy/mc_currency 各自独立发布 npm… |
| `bpm/fs-bpm` | 本页回答：fs-bpm 解决什么业务问题，由哪些运行单元组成，读者应按什么顺序查阅和验证各主题页。 |
| `bpm/fs-bpm-after-action` | BPM「后动作」执行服务，负责在流程节点完成后执行取值、回写、函数执行、触发新流程、触发操作、触发阶段推进等后动作。 |
| `bpm/fs-bpm-script` | 本仓库是纷享销客 BPM 体系的运维脚本集，专职一次性数据修复、过期清理、跨存储同步与诊断查询；它不负责流程引擎的运行时业务逻辑（那些属于 Java 服务 fs-paas-workflow-console、fs-flow-biz 等），也… |
| `bpm/fs-flow` | 本页是 .wiki 知识包的目录入口。fs-flow 提供业务流程 / 审批 / 阶段 / OneFlow 的入口与编排；执行核在远端 paas-workflow，本仓经 REST 代理与 MQ 协作。叙事细节以 overview.md … |
| `bpm/fs-flow-ai-hub` | fs-flow-ai-hub 是纷享销客流程团队的 AI 开发工具生态中心，聚合流程域的 AI 能力为可复用 Skills。 |
| `bpm/fs-flow-public` | fs-flow-public 知识库页面索引与导航 |
| `bpm/fs-flow-session` | fs-flow-session 是纷享销客 BPM 侧的流程运营服务号指令与消息聚合网关：接收开放平台/Grafana/乐享等入站，经命令路由或消息代理出站到企信，并提供嵌入式 sender SDK 与 Quartz 定时面。 |
| `bpm/fs-stage-propeller` | （暂无 ai-wiki 领域知识） |
| `bpm/fs-workflow` | 本仓库是 PaaS 平台的「工作流触发与配置编排层」，负责流程定义 CRUD、触发规则/元数据落库（Mongo，经 workflowTriggerDao）以及向外部 BPM 引擎发起部署与启动；不负责流程实例的解析与执行本身——引擎通过 … |
| `crm/fs-crm` | 本仓 wiki 覆盖 fs-crm（CRM/SFA 业务前台，PaaS 元数据驱动）的架构、核心机制、领域模型与配置运维知识。 |
| `crm/fs-crm-all` | 把 appframework、social、SFA、快消外勤、制造、任务等已发布制品 装配成单个可部署 WAR（CRM 前台 all-in-one）。本仓零业务 Java；知识页聚焦装配、入口、配置与版本风险。 |
| `crm/fs-crm-recycling-task` | 按任务定位 fs-crm-recycling-task 知识页。 |
| `crm/fs-crm-task` | 1. overview / architecture |
| `crm/fs-crm-task-sfa` | SFA 后台异步任务仓知识入口。事实以源码为准；本索引只给导航。 |
| `crm/fs-sfa-online-script` | 本仓库是 SFA 线上库表变更脚本仓库，只做"结构定义"：按发布号（720…995）与需求目录（feature/、SCRM/、合同 Agent/、返利优惠券/）归档 DDL，README.md#L1-L1 只有一行工程名。 |
| `crm_java/fs-crm-smartform` | fs-crm-smartform 是「智能表单」后台服务，对外提供访客填表，对内提供表单设计与卡片分享。本知识包覆盖系统架构、核心业务流程和关键机制。 |
| `crm_java/fs-crm-template` | fs-crm-template（CRM 模板能力服务）是一个 Java Maven 多模块 WAR 应用，负责打印模板和邮件模板的全生命周期管理，包括模板内容的 CRUD、渲染（PDF/HTML/Word/Excel）以及与下游文件服务（… |
| `crm_java/fs-crm-workflow` | 如何按任务在 wiki 中定位完成任务、触发、查询、MQ 边界与配置？ |
| `dataplatform/datafactory` | datafactory 是数据平台的上层任务调度与数据运维控制台（WAR，单 Pod fs-bi-custom-statistic-schedule）：DAG 编排、触发、状态回收、告警，外加 BI 工具台与 Agent 查询接口；ETL… |
| `dataplatform/fs-bi-udf-report` | 面向维护 fs-bi-udf-report 的工程师：先读概览与架构，再按任务进入领域/流程页。 |
| `dataplatform/fs-dataplatform-paas2gp-transfer` | PaaS oplog → BI/GP/埋点旁路同步与排行榜聚合的仓库知识入口。 |
| `e-service/fs-e-service` | fs-e-service 是客服服务系统（服务通/设备通后端）：Java 8 多模块 Maven 单仓，war + Spring XML + Dubbo 装配，呼叫中心与工单双域。首轮完整萃取，13 页。 |
| `e-service/stock-plugin` | 本仓库的职责边界很清楚：把进销存单据（备件消耗、个人盘点、出库单、盘点单等）在表单页里的字段联动、批量添加回填、批次序列号、扫码与多单位换算规则，沉淀为可下发的「业务中台化插件」package.json#L4-L28。 |
| `eip/miniprogram-login` | 互联平台统一登录小程序组件（npm 包 miniprogram-login，微信自定义组件 + CJS API 面）。本索引导读者按任务取用知识页；本仓无服务端、无持久层，登录协议的云端实现在公司登录服务，本仓只覆盖小程序侧。 |
| `fe/bi` | 该仓库是纷享销客 CRM 平台的 BI 前端子系统（"老bi工程"，README 明确标注新项目为 fbi），负责图表、看板、主题模型管理、指标字段管理、目标规则、报表设计与导出等可视化功能，不负责后端服务（调用 /EM1HBICRM、/… |
| `fe/bi-xkcharts` | BI 统计图表组件库（UMD 全局脚本交付） |
| `fe/crm` | fe/crm 是纷享销客 WEB 端的业务子应用库，在宿主分发入口后提供 CRM 频道内的落地页与对象操作。npm 包名 crm。 |
| `fe/crm-setting` | 部分业务模块已补充模块级 README： |
| `fe/fbi` | FBI BI 前端组件库的总体介绍与快速索引 |
| `fe/fs` | 按任务选页，全部结论可沿 claims 回 fs/app.js、fs/connect/feed.js 等源码锚点。 |
| `fe/fx-ui` | 先读 架构总览 建立全景，再按下方任务路由进入专题页。所有行锚结论须回源码核验。 |
| `fe/icmanage` | icmanage 是互联管理后台前端项目（package.json#L2），基于 Gulp 3（package.json#L6 devDependencies）+ SeaJS (CMD) + Vue 技术栈，代码位于 icmanage/ … |
| `fe/manage` | manage 仓库 wiki 页面索引与领域概览 |
| `fe/mp` | mp 是微信公众号（服务号）管理后台，寄生于纷享销客主站 Web 宿主（app-manage 模块体系）。前端形态为 jQuery + Angular + Vue 混合的多页 hash 路由应用，不自带服务端、不做独立部署壳。 |
| `fe/npaas` | 按「装配主轴 / PWC 链路 / 详情页 / 兼容债」组织知识包页面导航与读者入口路由 |
| `fe/portal` | 本仓库是「厂商/渠道业务门户」的前端框架层（shell），负责把宿主主站里的一块 DOM 变成带导航、菜单、待办、模板切换的门户运行时；它明确不负责业务模块实现、身份认证与静态资源托管。 |
| `fe/qx` | 本知识包共 25 篇正文（含本页）。建议的进入顺序：先读 overview 与 architecture 建立心智模型，再按下面的「我想…」表跳到具体页面。 |
| `fe/remind` | 双交付面与宿主装配拓扑 — webpack 双入口、app/sdk 启动链、三层库结构、宿主全局量边界 |
| `fe/vcrm` | vcrm 是嵌入 FS 平台的 CRM 前端 SDK，通过 VCRM 库默认导出聚合注册表，提供对象详情、Widget、组件、列表、插件五类 SDK 能力。 |
| `fe-app/apperlogin` | apperlogin 是嵌入厂商门户与 C 端站点的互联登录弹框组件集（Vue 2 + Webpack），由 SeaJS 适配器被宿主按需加载；它提供切换企业/语言/时区/币种、改密、个人设置、账号注销、草稿箱与退出登录，不负责登录注册本… |
| `fe-app/callcenter` | 本知识库描述纷享销客客服前端工作台（UMD 子应用 app-callcenter）的职责边界、装配顺序、运行时机制与失败语义。建议按「概览 → 架构与嵌入 → 核心功能 → 请求与排障 → 扩展」的顺序阅读。 |
| `fe-app/checkin` | 外勤签到前端功能包（app-checkin）知识入口。先读 总览 与 架构，再按任务走 quickstart。 |
| `fe-app/email` | fe-app/email 是主站内嵌的「企业邮箱」纯前端模块，以 CRM 主应用的 hash 路由页面形式提供服务： |
| `fe-app/erpdss` | ERP DSS front-end application: policy management, alarm monitoring, and integrations with external systems |
| `fe-app/fmcg-ai` | fmcg-ai（FaciShareWeb）是嵌入 CRM 宿主的 AI 订单数据分析前端微应用，以 React SPA 形态在 src/App.jsx 为主入口。 |
| `fe-app/icfiles` | icfiles 是销客 SaaS 宿主内的跨企业文件共享前端：把"我方共享出去的文件夹"和"共享给我方的文件夹"两个视图做出来，走跨企业网关访问互联盘后端。它不做存储、不做鉴权、不独立部署——产物是一个 19 行入口 + 页面模板 + 1… |
| `fe-app/knowledge` | 本仓库是「服务通」主站的知识库子应用，从服务通中抽离为独立模块（README.md#L1-L4），只负责知识库相关的 Vue 页面、paas 卡片组件与前端网络封装；它不负责后端接口与鉴权逻辑（依赖 eservice/* 远程 API，R… |
| `fe-app/marketing` | fe-app/marketing（营销通 Web 前端）知识包。首轮 24 页，基线 master b2734c5（2026-09-17）。写作契约见 .wiki/AGENTS.md，背景工作台见 .wiki/references/con… |
| `fe-app/onlineservice` | 索引页，导航到所有知识页面 |
| `fe-app/shuttles` | shuttles 是纷享销客（fxiaoke）CRM 平台内嵌子应用「数据同步」控制台前端，无独立部署形态，全部业务请求经宿主 FS.util.FHHApi 转发至 EM1/EM6 后端。 |
| `fe-app/sponge` | sponge（fe-app/sponge）是互联组织架构应用：Vue 2 + webpack 4 纯前端应用，内嵌宿主主站（FSDP/FS 主站 + SeaJS AMD 装载）运行。负责互联组织树展示与节点维护、互联企业关系、隔离设置、互… |
| `fe-app/standalone` | standalone 是纷享销客 CRM Web 端的 app-standalone 前端分包。它不独立部署，而是由宿主 CRM Web 应用在运行时装载，为 CRM 提供 32 个外围业务模块（工单快捷操作、企微外部联系人详情、ifra… |
| `fe-app/wechatconnect` | wechatconnect（构建产物名 app-wechatconnect）是纷享销客CRM宿主下的互联通知公告前端子应用，负责发通知、通知管理、评论管理、设置、下游接收等路由页与UI组件装配。 |
| `fe-app/wechatsender` | 本页是 wechatsender 知识包的入口与阅读路由。 |
| `fe-app/workorder` | workorder 是服务通业务的前端仓：覆盖工单、派工与抢单、备件与库存、设备与巡检、现场服务履约、服务报告、费用结算与系统设置等场景。仓库根有 2049 个跟踪文件、约 19.8 万行代码（git ls-files | wc -l 与… |
| `fe-bi/ava-echarts` | BI 移动端小程序需要图表能力，但 ECharts 官方面向浏览器 DOM 设计、小程序 canvas 又分新旧两套接口。本仓把 ECharts 以分包形式交付给宿主小程序（subproject.config.json 导出 ava-ec… |
| `fe-bi/bi-icon` | bi-icon = iconfont.cn 图标项目 4734195「BI前端」的本地打包与分发仓。它把在线图标素材下载进仓、 |
| `fe-bi/bi-sdk` | 必须守住的不变量：(1) 颜色格式：#RRGGBBAA 在 Canvas/Heimerdinger 环境会被旧原生 Canvas 当成 #AARRGGBB，必须在渲染边界转为 rgba(r,g,b,a)（见 AGENTS.md 明确踩坑记… |
| `fe-bi/doesburg` | doesburg Vue 2 拖拽栅格布局设计器库：模块地图、核心概念与页面导航 |
| `fe-bi/fmt-value` | fmt-value 是一个零依赖的纯函数工具包，专责将数值、百分数、时长格式化为用户可读字符串。它提供三个方法： - fmtNum(value, conf) — 核心格式化函数，支持单位档位、千分位、前缀、百分数等组合配置 - forma… |
| `fe-bi/fs-gulp-vue` | fs-gulp-vue（package.json#L2-L5）是 Gulp 3 时代的 .vue → CMD 单文件转换器。它不是 Vue 应用，也不是图表引擎：唯一生产源码是 index.js，在宿主 gulp 流里把 SFC 文本改写… |
| `fe-bi/heimerdinger` | 源码事实源：README.md · package.json |
| `fe-checkin/checkin-hera` | 本仓库是「外勤/签到」微信小程序 checkin-hera，双重角色：一是可独立启动的 app（app.js#L9-L16 兜底注册 App() 并做 mock 与 Form 缓存清理），二是以同名 npm 包向外输出组件与模型的库（pa… |
| `fe-connect/erlogin` | erlogin 不是一个网站，而是一个被宿主 CMS 模板以 <script> 挂载的企业互联登录前端工程。 它对外提供登录 SDK 与一组登录页面脚本，产物是纯 JS 包，宿主模板（/qd/、/proj/page/erlogin/）决定… |
| `fe-connect/marketplace-sdk` | 职责边界：本仓库把"智能广场"业务能力以 UMD 组件库形式交付给前台主框架——产物 libraryExport:'default' 导出宿主约定的 app 对象，对外唯一契约是 components 注册表，调用方经 Fx.getBiz… |
| `fe-h5/applink` | 纷享销客 CRM 的移动端 H5 落地页工程，通过 App Scheme 在移动端拉起 CRM App。 |
| `fe-h5/avapedestal` | H5 微应用运行时基座（fe-h5/avapedestal）。不是业务页，也不是 ava_ui UI 库。 |
| `fe-h5/sfa` | fe-h5/sfa 是 CRM 在 Office（Outlook 加载项）、Teams、腾讯会议与普通浏览器四类宿主里的登录与授权入口层：9 个静态页面 + 两份加载项清单模板 + 一套 Node 装配脚本。没有服务端、没有自建 API、… |
| `fe-manual/ui-paas` | ui-paas 是「纷享销客开发者手册 · UI PaaS（PWC）」这条线的文档站仓库：它在同一个 Git 仓里放了一份面向平台二次开发者的手册（约 718 篇正文）和一个配套的移动端组件演示站，由 VuePress 与 vue-cli… |
| `fe-paas/agent-chat` | agent-chat 是智能体聊天纯展示组件库，交付双端产物： |
| `fe-paas/appcustomization` | appcustomization 是 UI PaaS 的「应用自定义」前端仓，提供 CRM 首页、PaaS 应用页、对象页、渠道/互联等场景的设计器与前台渲染能力。 |
| `fe-paas/approvalflow` | fe-paas/approvalflow 是审批流程可视化设计器前端模块，基于 Backbone.js 构建。 |
| `fe-paas/bpm` | 本仓库是 PaaS 的 BPM 前端资产包（package.json#L1-L12），只承担浏览器侧的流程设计器画布、节点属性面板、待办任务处理、审批卡片、催办与实例日志；流程推进与任务生成留在 /EM1HBPM、/EM1AFLOW 后端… |
| `fe-paas/function` | 采集自 README.md；锚点均附行号，可回源核验。 |
| `fe-paas/login-ai` | 本索引覆盖 .wiki/ 已规划页面。上手顺序见 overview 与 quickstart。 |
| `fe-paas/newx6` | newx6 是 BPM 流程画布的 X6 图编辑器内核（UMD NewX6），由宿主远程装载；仓内 src/editor 只是调试台。README 为 GitLab 默认模板，以本知识包为准。 |
| `fe-paas/object` | paas-object（亦称 object）是 CRM 自定义对象的前端设计器与详情页。 |
| `fe-paas/paasapp` | paasapp（PAAS应用）是 PaaS 平台前端应用运行壳，以 CMD 模块形态被宿主 Fx 装载，提供应用渲染、应用管理、应用市场三大功能面。 |
| `fe-paas/paasbiz` | 纷享销客 PaaS 业务协同前端 UMD 库：向宿主暴露 actions 与 components（含 pages）。 |
| `fe-paas/paasdev` | paasdev 是 PaaS 宿主上的 Vue 2 UMD 模块库，提供 AI 管理后台、ShareAgent 外链、平台运维组件与 widgets；事实源是本仓源码。 |
| `fe-paas/paasflow` | paasflow 是 fe-paas 平台上的业务组件注册壳（UMD 包），负责把已存在于 paas-workflow、crm-modules、paas-paasui 三个外部包的审批与提醒能力，按架构组协议以命名导出登记成查找表，供宿主… |
| `fe-paas/paasui` | paas-paasui 是 BPM / 审批流前端配置 UI 组件库，而非独立应用。宿主（fs-online-consult 等业务应用）通过 seajs CMD 协议加载组件，组件在宿主页面中渲染流程配置界面。 |
| `fe-paas/paasxt` | 源码事实源：路径均附行锚，claims 必须回源码核验。 |
| `fe-paas/rocket` | rocket（package.json 名 paas-rocket）是宿主 PaaS/CRM 环境里的阶段推进器：设计器定义阶段与任务，运行时处理卡推进阶段并处理任务，流程详情页负责查看、启停与复制定义。仓库 README 只记录两条构建… |
| `fe-paas/template` | template 是 fe-paas 组的前端工程化产物仓：CRM 打印/邮件模板设计器。它以 seajs 模块 paas-template/sdk 的形态被宿主（CRM/PaaS 前端基座）装配，自身不独立起服务、不独立发布页面。 |
| `fe-paas/tpm` | TPM（Trade Promotion Management）是宿主 PaaS 平台的内嵌前端 SDK 模块，提供活动管理、预算管理、任务体系等业务页面和可嵌入弹窗。 |
| `fe-paas/vui` | 本文档由 repo-wiki 自动生成，claims 必须回源码核验。 |
| `fe-paas/workflow` | 本仓库是 CRM PaaS 平台的审批流设计器前端，负责流程定义的可视化编辑、部署提交及审批卡片渲染，不负责流程引擎的运行时执行（实际执行由 /EM1HAPPROVAL/ 后端完成）。 |
| `fe-paas/workprocess` | 本仓是纯前端工作流设计器 SDK（不是流程引擎），以 UMD → CMD 被宿主 seajs 页面加载。 |
| `fe-xx/xxvui` | 销售协同产品线基于 Vue 2 的 UI 组件库，提供 Feed 流、富文本编辑器、发布组件、语言设置等异步组件，使用 FxUI 基础框架和 seajs 模块加载。 |
| `feeds/fs-feeds` | fs-feeds（纷享逍客工作圈）是企业级 Feed 流系统主仓，覆盖 Feed 发布、搜索、审批、通知四类能力，采用 Maven 微服务多模块架构（22 个模块、10 亿+ 数据规模）docs/架构总览.md#L5-L10。 |
| `feeds/fs-new-schedule` | 本仓是纷享销客 PaaS 平台上 ScheduleObj / ScheduleRepeatObj 两个预定义对象的业务实现层。它没有自建 RPC provider，而是编译进 PaaS AppFramework 体系，经预定义对象通道对外… |
| `feeds/fs-social-feeds` | overview |
| `feeds/grafana` | 本仓库是「AI 治理中枢」而非服务代码库：沉淀跨项目事实（~/.ai-governance/registry.yaml 与被治理项目的 .ai-governance/project.yaml）、可安装的 Agent/Skill/Comma… |
| `fs-eye/fs-eye-consumer` | claims 与行为描述以源码为准；.wiki/references/ 与 profile 仅为背景线索。运行中勿改 AGENTS.md。 |
| `fs-eye/fs-eye-manager` | fs-eye-manager：可观测配置 GitOps + Prometheus HTTP SD。 |
| `fs-hera/ava-fs-common` | ava-fs-common 是 Avatar 宿主小程序的通用能力供给仓（选人/地图/支付/预览/邮件/ER 账号/离线调度），无独立后端。本 wiki 覆盖供给边界、启动装配、页面契约、离线状态机、各页面族与配置默认，共 17 个主题页。 |
| `fs-hera/ava-jenkins` | ava-jenkins 是 Ava 跨端（小程序 + H5）产物的 Jenkins 编排仓：不含业务源码，以「壳 + 双脚本」（avaui_build → load Jenkinsfile + docs_script）把参数解析、浅克隆、… |
| `fs-hera/ava-markdown` | fs-hera/ava-markdown 交付一个微信/纷享小程序自定义 Markdown 渲染组件：业务页面传入 Markdown 原文（text 属性），组件解析为 HTML 并按宿主环境选择 rich-text / mp-html … |
| `fs-hera/ava_ui` | 流程：flows/startup-and-static-init.md、flows/dialogcenter-imperative.md |
| `fs-hera/bi_business_query` | bi_business_query 是纷享销客 CRM 微信小程序的工商查询分包：提供工商查询/详情、智能推荐与评分、医院科室、招商局列表四类页面编排，核心价值是把查询结果回填回宿主 CRM 表单。60 个 JS 代码文件、约 8.7k … |
| `fs-hera/business-cmpt-paas` | CRM 端上共享 PaaS 能力层：对象列表/详情/表单的入口、协议、组件、动作与离线对象包。三包交付（main/sub/offline），运行于微信小程序、纷享 Hera App 与 H5。 |
| `fs-hera/dhtbiz-components` | dhtbiz-components 是订货通（DHT）移动站点的业务组件包：为 UIPaaS 低代码站点提供 home、product_list、product_detail、shopping_card 四个业务容器与配套渲染组件，覆盖商… |
| `fs-hera/fs-hera-api` | fs-hera-api 是小程序通用 API 基础组件库（npm 包），为 Avatar 小程序体系提供微信小程序 / H5 / Hera 三端的统一 API。 |
| `fs-hera/metadata-lib` | 本库是纷享 CRM 小程序前端元数据基础库，提供描述缓存、布局规则引擎和展示值转换三大能力。 |
| `fs-hera/object_detail` | 本仓是微信小程序“对象详情”集成工程：详情容器加扩展宿主形态， |
| `fs-hera/object_flow` | L2 移动端流程域聚合前端：导出 objct_flow_main / object_flow / objflowplugin-*，提供 BPM 链接路由、三端 API 门面与流程域插件宿主。 |
| `fs-hera/object_form_pass` | fs-hera/object_form_pass 提供 CRM 对象新建/编辑表单的小程序运行时与对象插件扩展面。 |
| `fs-hera/object_list` | 本知识包由 19 篇 leaf 页与 3 篇综合页组成，全部结论以目标仓源码为唯一事实源，行锚采用 path#L12-40 记法（相对本仓根）。 |
| `fs-hera/paas-dev` | 按 你要完成的任务 选入口；机制细节在域页与 references，合成页给出地图与术语。 |
| `fs-hera/uipaas_custom` | 按总览、主路径与配置装配三块索引本仓 wiki：从四入口薄壳、出站契约、layout 渲染到云控与分包多语，便于按任务跳转。 |
| `fs-hera/uipaas_site` | 本仓库是飞书销帮帮（FS Hera）平台下的微信小程序独立站点渲染工程，职责限于两件事：（1）uipaascustom-siteengin 提供布局协议到小程序组件树的递归渲染引擎；（2）uipaascustom-sitepackage … |
| `fs-hera-framework/avatar-toolkit` | 职责范围：本仓库是 avatar-toolkit（ava CLI）工具链，负责将微信小程序源码（WXML/WXSS/JS）同时编译为小程序 zip 分发包和 H5 Web 应用，实现同一份源码跨小程序与 Web 双端部署。 |
| `fs-hera-framework/fs-hera` | 为宿主 App 提供可嵌入的小程序运行时：加载资源包、执行业务 JS、渲染 UI、桥接原生 API，并在 iOS / Android / H5 三端对齐行为。 |
| `fs-intelligent-operation/fio-admin-client` | 构建期入口是 webpack 的 entry.app = './src/main.js'（build/webpack.base.conf.js#L35-L37），publicPath 按 NODE_ENV 走 production/dev… |
| `fs-intelligent-operation/fio-admin-server` | fio-admin-server 是运营平台中台后端服务，为前端 fio-admin-client 提供： |
| `fs-intelligent-operation/fio-business-server` | 本仓库是销售 BI「运营平台」业务侧只读聚合服务：README 仅一句「运营平台（BI业务侧）」（README.md#L1-L3）；以 war + DispatcherServlet 暴露 HTTP（src/main/webapp/WEB… |
| `fs-marketing/fs-marketing` | fs-marketing（营销通）是 Servlet WAR 多模块工程：1 个 Dubbo/Dubbo-REST 服务提供者 + 4 个 HTTP 前台 + 1 个定时任务容器 + 1 个企微回调容器，共享 common/api/out… |
| `fs-marketing/fs-marketing-statistic` | 本仓库负责营销统计数据的采集、聚合与查询：订阅 RocketMQ 中的营销行为事件（action record / user behavior），经实时消费者链处理落库，同时通过 Hadoop MR 离线作业全量重算 UV（HyperLo… |
| `fs-open/fs-ai-open` | 仓库本质是单一 Spring Boot 模块 sharecrm-im-gateway：根 pom.xml#L10-L16 只聚合这一个 module，自身以 packaging=war、Java 21 构建（sharecrm-im-gat… |
| `fs-open/fs-broker` | fs-broker = 开放平台 API 网关（经纪人）：对外承接 ISV/集成方的 /cgi/ HTTP 调用（CRM 数据读写、令牌发放、组织/团队、具名业务 API），对内做鉴权、多租户归因、开通白名单、限流熔断、三态灰度路由，再把… |
| `fs-open/fs-erp-ipaas` | fs-erp-ipaas 是纷享销客企业级 iPaaS 后端引擎：集成流定义/部署/执行、连接器与 NodeHandler 扩展、多通道触发（CRM MQ / Webhook / 轮询定时）、租户限流与失败重试，以及对 /cep/*、/c… |
| `fs-open/fs-erp-sync-data` | Bootstrap baseline stub. Full content deferred to incremental extract phase. |
| `fs-open/fs-livingroom` | 本仓库是「客脉（mankeep）」运营/运维后台的单体 WAR（fs-livingroom-mankeep/pom.xml#L12-L18，contextPath=start），唯一调用方是同包自带的 jQuery 静态页：index.h… |
| `fs-open/fs-mankeep` | fs-mankeep（客脉）是一个多端营销管理平台（B2C 营销工具）：企业管理员（Web 端）配置营销内容，C 端用户（小程序/H5）参与活动、交换名片、提交线索。核心能力包括活动管理、名片交换、客户线索、统计分析、会议管理、动态发布等。 |
| `fs-open/fs-online-consult` | 1. overview.md — 负责边界 |
| `fs-open/fs-open-app-center` | 本仓是"应用中心域"的编排者：负责应用/组件/服务号/自定义菜单/运营事件的域内真相与三类协议出口，不负责 oauth、组织架构、消息、素材等中台能力的实现。模块划分见 README.md，运行时全景见 系统边界与运行时结构，第一周动手路… |
| `fs-open/fs-open-materail` | fs-open-materail 是开放平台的素材/图文/微信链接通知公告服务。仓名 materail 是历史拼写错误，Maven 坐标和部署名都是正确的 material。 |
| `fs-open/fs-outer-oa-all` | 外部 OA 连接器网关知识页索引 |
| `fs-open/oauth` | fs-oauth-base（fs-open/oauth，gitlab id 23）是纷享开放平台 OAuth 域的纯契约仓：Maven 三模块聚合，交付 api 与 inner-api 两个 jar，只含服务接口、数据对象、枚举与异常类型… |
| `fs-open-email-proxy/fs-open-email-proxy` | 一句话：fs-open-email-proxy 是 FaciShare 平台的第三方邮箱代理层——替业务方保管邮箱凭据、跑发信/同步状态机、把邮件搬进自己的库与检索索引，但不实现邮件协议（vendored fork）、不拥有业务主数据（在… |
| `fs-open-platform/fs-agent-connecter` | fs-agent-connecter 是三平台（飞书/钉钉/企业微信）入站机器人的适配层，接收平台回调、解析身份、转发给 AI Agent、并通过 SSE 流式回写平台。 |
| `fs-open-platform/fs-ai-marketplace` | 本仓是纷享销客官网 AI 智能广场的后端实现，核心职责： 1. 平台运营侧：能力（Agent/Skill）上架审核、供应商/标签/计费方式管理、视频/图片素材管理。 |
| `fs-open-platform/fs-mcpserver` | 本页面基于源码生成，知识内容以运行时实际代码为准。 |
| `fs-open-platform/open-api-all` | open-api-all（纷享销客开放平台）是企业级 API 网关的核心仓库，为第三方应用提供统一的 OAuth 鉴权、接口权限管理、限流控制、事件回调等能力。 |
| `fs-open-si/erpdss-outer-connector` | Knowledge hub index for the erpdss-outer-connector iPaaS connector runtime |
| `fs-open-si/fs-k3cloud` | 本仓 fs-k3cloud（命名空间 fs-open-si，GitLab 项目 2341）是纷享销客 CRM 与金蝶云星空（K3 Cloud）之间的集成连接器：负责企业连接配置与连通性校验、对象/字段映射绑定、主数据与单据的双向同步，以及… |
| `fs-pay-all/fs-pay` | fs-pay（纷享支付）是纷享平台的核心支付服务，支持企业账户（EA）和个人账户的充值、提现、支付、对账等能力。 |
| `fs-sail/dhtbiz` | dhtbiz 是订货通（DHT）暴露给主站 PaaS 运行时的电商业务包：一个需本地构建的 Vue + webpack 前端 UMD 包，向宿主交付组件 / API / 插件三类注册表与一个 app 对象。它不启动应用、不持有路由与状态容… |
| `fs-sail/fe-sail-v2` | 本仓库是芬客「订货通 2.0」的前端接入壳层：负责把 @sail/core 内核 bootstrap 成全局 $dht 并挂上业务方法（src/context/global.ts#L139-L203）、覆写 CRM 底层请求与详情入口（s… |
| `fs-sail/fs-crm-reconciliation` | 客户资金账户对账后台服务的仓库知识导航。先读 overview 与 architecture，术语对齐见 glossary。 |
| `fs-sail/fs-sail-order` | 订货业务（订货通 / DHT）在 PaaS appframework 之上的业务扩展层。本知识包按「读者问题」组织，共 17 页，全部结论以目标仓源码为唯一事实源， claims 可回溯到文件与行区间。 |
| `fs_crm_implementation/open-trace-extension` | open-trace-extension 是一个面向内部研发/排障人员的 Chrome 浏览器效率工具，围绕 traceId、objectId 与日志字段，在 ClickVisual、Kibana、Grafana、DB 控制台、i18n … |
| `fsdroid/fs-android` | 目标：核心域约 80% 代码可导航，机制页规模约 150 页。覆盖总表见 references/coverage-roadmap.md。 |
| `fsdroid/fs-harmony` | 本仓是 FaciShare 移动工作台的 HarmonyOS 宿主容器：以原生壳（products/phone）承载 H5 工作台（ava:// 协议进 WebViewPage），通过 JSBridge（50 个 JSAPI handle… |
| `fx/appcenter` | appcenter 是纷享销客 PaaS 应用市场的前端分发模块，负责 ISV 三方应用的浏览、筛选、详情和安装向导。 |
| `fx/base-biz` | base-biz 是架构组 Vue 2 业务组件库（package.json#L1-4），定位为 CRM 管理端/宿主页面的模块化组件供应商： |
| `fx/configcenter` | configcenter 是配置中心与灰度开关的浏览器端操作台（Vue 3 + TypeScript + Vite + Arco Design，交付静态文件），负责「界面、门禁、请求契约与失败语义」，不负责后端的配置存储、下发协议与生效链… |
| `fx/fx` | fx-core（npm fx，GitLab fx/fx）是公司 WEB 主站的底层运行时架构库：把 util / http / router / store / i18n / contacts / eventsBus / file / p… |
| `fx/fx-components` | overview → architecture → domains → glossary |
| `fx/fx-cross` | fx-cross: portal shell for ER channel. Vue 2.7. iframe. |
| `fx/fx-libs` | 纷享销客前端依赖库底座：Gulp 双主包、Sea.js CMD 模块、SparkUI/asynclibs 按需资产与 i18n 工具链。 |
| `fx/fx-paas-components` | 本仓库是 UIpaaS 的"组件供给层"：把 src/asynccomponents 下的业务组件打成一个 UMD 全局 Cmpt，对外只有 get_paas / get_paas_lists / get_paas_bytype 三个查询… |
| `fx/fx-whatsapp-assistant` | fx-whatsapp-assistant 是一个 Chrome MV3 浏览器扩展（内部名 fx-assistant）：把 WhatsApp 个人号网页端（web.whatsapp.com）的会话、联系人、群组、群成员与聊天消息抓取后同… |
| `fx/sfa-sidebar` | sfa-sidebar 是 Fx 运行时下的一个脚手架模板，用于快速拉起新的侧边栏子应用。初始仓库本身是一个已改名完毕的空壳，包含 Vue 2 + Webpack 5 的基础构建链、样式隔离机制和 hash 路由骨架，但无任何业务逻辑。 … |
| `fx-admin/erp-ipaas` | 一句话：fx-admin 内的集成流 2.0 前端子应用；编排与连接器配置 UI，不执行集成流。 |
| `fx-admin/marketplace-manage` | 本仓是 fx-admin 宿主中的一个 UMD 子工程，当前只承载一件事： |
| `fx-admin/marketplace-platform` | 本仓是 AI 智能广场（marketplace）的运营侧与供应商侧管理后台：纯前端 Vue 2 独立 SPA（src 实测 114 文件、9 个业务域页面目录、15 个 API 模块），无服务端运行时、无测试目录。全部业务读写经宿主注入的… |
| `h5/e-service-crm` | e-service-crm 是纷享销客（ShareCRM）服务通H5应用，基于crm-core框架定制开发，提供售后服务、设备管理、工单处理等移动端业务功能。 |
| `h5/kemaitong` | 本页面回答：这个仓库解决什么问题，如何运行和验证？ |
| `h5/marketplace` | 本仓知识包索引与主题导览 |
| `hexagon/h5-landing` | 营销通微页面 H5 渲染端——基于 Vue 2.6 的纯客户端应用，支持多入口装配、40+ 可视化组件、表单收集、直播播放、文件预览、支付、会员系统与 22 种语言国际化。 |
| `manufacturing/dev_tools` | dev_tools（java_mcp_server）是一个面向 AI 编码助手的单进程 stdio MCP 服务器（Java 21 + Spring Boot 3.5 + Spring AI 1.0）：把研发侧高频取数与执行动作封装为 M… |
| `manufacturing/fs-crm-manufacturing` | 制造业 CRM 服务仓：Maven 多模块、单一 WAR、PaaS predefine 双入口（service + action）。 |
| `marketing/official-website` | official-website 是纷享销客国内官网的 WordPress 主题源码 + 本地 Node 构建脚本集（交付文件，不交付服务）。它负责「静态页正文、主题模板与函数库、浏览器脚本、构建期域名/站点段改写、一份断链的自动上传工具… |
| `marketing-fe-project/i18n-helper` | @tools/i18n-helper 是营销前端团队的工程工具包（npm 包），职责是把业务前端项目源码中的中文字符串批量转成多语词条与 $t('key') 调用，并导出可导入多语平台的 xlsx 文件。 |
| `marketing-fe-project/marketing-taro` | 本知识包描述 marketing-taro（catalog name = marketing-fe-project/marketing-taro）：营销通的 Taro 3.4.2 + React 跨端前端，一套 src/ 源码编译出纷享小… |
| `metadata-qa/fs-metadata-core-suite` | fs-metadata-core-suite 是 fs-metadata 元数据服务的 QA 自动化测试套件，基于 TestNG + REST-assured，覆盖元数据 API 的全部功能域。 |
| `metadata-qa/i18n-client-test` | 仓库定位、读者任务与推荐的查阅顺序。 |
| `ops/dba` | 本知识包共 11 页，按「总览 → 拓扑 → 契约 → 机制 → 方言 → 通道 → 不变量 → 入口」组织，针对同一个仓库（DBA 刷库脚本集中仓）的不同读者任务。 |
| `paas/fs-effektif-master` | 本仓库是一个可嵌入的 BPMN 工作流引擎内核（README.md#L36-L41），不是一套可独立部署的服务：全仓无 *Application.java/*Bootstrap.java，调用方是宿主业务应用，通过 Configurati… |
| `paas/fs-message` | fs-message 是企业消息投递中心，负责通用消息、待办、CRM 提醒的统一入口与通道编排。 |
| `paas/fs-metadata` | fs-metadata 是 PaaS 元数据核心：Describe 定义对象/字段/布局，ObjectData 在 Describe 约束下完成实例数据 CRUD，支撑数据权限、结构化查询、引用追踪与 ES/CH 异步副本。10 个 Ma… |
| `paas/fs-metadata-semantic` | 本仓库是 CRM 元数据之上的“AI 语义索引”后端：消费 Describe/对象/流程等元数据，用 LLM 提炼出字段、指标、规则、语义帧等语义，落库到 ES、ClickHouse、TuGraph，再向上层 BI 与问答开放检索。 |
| `paas/fs-paas-action-centre` | 本仓库是 PaaS「动作中心」，只负责 Action 定义的装配与执行编排，明确不负责动作自身的业务逻辑——真实计算转调 Function 平台、APL bizAPI 或远端 AI（fs-paas-action-bus/src/main/… |
| `paas/fs-paas-ai` | fs-paas-ai 是公司 AI 能力的平台底座仓：模型调用网关、RAG 知识库与向量检索、Agent 编排与执行、提示词、技能、动作总线、会话前端接口、用量度量与评测。它不负责模型推理（转发给厂商）、业务对象元数据的权威定义（来自元数… |
| `paas/fs-paas-app-task` | fs-paas-app-task 是 PaaS 平台的异步任务处理服务，负责消费 RocketMQ 消息与 dispatcher 事件来编排批量按钮、Enrichment 刷新、离线打包、元数据联动等后台任务；不承担 HTTP API 暴… |
| `paas/fs-paas-appframework` | 知识问题：读者如何从总览到达架构、高频接口、域与排障页？ |
| `paas/fs-paas-auth` | 按仓库整体解读：它实现 RBAC 多维权限（菜单/操作/字段/视图/License）配置、角色分配、审批与"系统库→租户库"同步及两级缓存失效；不做用户登录认证（用户来自 fs-uc-api），也不提供前端页面。 |
| `paas/fs-paas-bizconf` | PaaS 业务配置服务：system/tenant/user 三级 rank，Redis + 可选客户端 Ehcache，NotifierClient 失效。 |
| `paas/fs-paas-calculate-task` | fs-paas-calculate-task 是 PaaS 计算域的纯异步 worker：接收 RocketMQ 消息，批量计算公式字段、统计字段、关联引用字段，产出落在对象数据表、事件缓冲与出向 REST 回写。 |
| `paas/fs-paas-data-auth` | 本仓库是数据权限系统的 Maven 多模块工程，根 pom.xml（第 20–27 行 <modules>）聚合 common/db/base/service/syncer-mq2db/worker 六个模块。 |
| `paas/fs-paas-data-tools` | 本仓库是纷享销客 PaaS 的两套数据工具集合：hamster 三件套负责 schema 隔离迁移的编排与状态机，tenant-sandbox 负责实际的数据拷贝执行，两者在同一 pom 聚合下但互不依赖 pom.xml#L15-L20、… |
| `paas/fs-paas-function-engine` | fs-paas-function-engine 是 PaaS APL 低代码函数引擎：编译并按租户隔离执行 Groovy/Java 函数。对外主契约是内部 HTTP /v1/function/* 与 RocketMQ 异步队列。 |
| `paas/fs-paas-gnomon` | 日晷（Gnomon）是公司的延时与定时回调中心：业务方登记任务 → 到期扫描 → 按模板回调。触发时刻由 XXL-Job 调度中心决定，本仓只负责「到期后怎么执行」。 |
| `paas/fs-paas-job-schedule` | 作业中心（fs-paas-job-schedule）是分布式批量作业调度服务，提供 REST API 提交作业、RocketMQ 异步派发、Quartz 扫描循环驱动、状态回收的完整生命周期管理。 |
| `paas/fs-paas-license` | 职责与边界：本仓库是 PaaS 的授权中心，唯一持有并解释"主版本/协同版、模块开通、配额 para、下发对象"四类事实，对上层只回答"能不能用、有多少"。 |
| `paas/fs-paas-metadata-dataloader` | fs-paas-metadata-dataloader 是 PaaS/CRM 平台上的 Excel 批量导入导出编排器：它接收上游传来的文件与参数，做后缀与配额闸门、Excel 流式解析、按批提交下游、逐行回写结果文件，并把终态经回调和消… |
| `paas/fs-paas-org` | 组织架构组件，按租户隔离对外提供部门层级、部门员工关系、员工上下级、用户组与企业组的查询维护；本身不存部门详情，通过 fs-organization-api/adapter、fs-uc-api 等下游取数（README 明确部门详情事实源… |
| `paas/fs-paas-refresh` | fs-paas-refresh 是一个「刷库／数据订正执行器」：发布或数据迁移窗口里，由运维脚本、DBA、RocketMQ 事件或 xxl-job 调度触发，对 CRM 各租户库按 version 幂等地执行元数据订正 SQL。它不承载在… |
| `paas/fs-paas-rule` | 本仓是 PaaS 规则域的 L0 前台服务：规则资产（规则组 / 宏组 / 聚合规则）服务化 + 仓内 fork Aviator 2.1.1 的表达式求值。4 个 Maven 模块、单一 WAR 交付（contextPath /fs-pa… |
| `paas/fs-paas-score` | fs-paas-score（com.facishare:fs-paas-score 2.0.0-SNAPSHOT）是 PaaS 评分规则服务，负责规则编排与算分。 |
| `paas/fs-paas-workflow` | 这段实现是 PaaS 流程引擎，负责审批流/工作流的定义部署、版本管理、条件网关流转、实例执行、任务中心与事件广播（见 README.md#L10-L17）。 |
| `paas/fs-pod` | fs-pod 是租户 → 物理数据库资源（PostgreSQL / ClickHouse / MongoDB / Elasticsearch）的元数据路由中枢，负责四元组路由的登记、分发与失效广播。它不提供迁移脚本，不代业务执行迁移与实例… |
| `paas/fs-semantic-runtime` | fs-semantic-runtime 是一个包含两个 Python 部署单元的 AI 语义运行时仓库： |
| `paas/i18n-setting` | i18n-setting 是翻译工作台的后台服务，提供词条管理与 AI 翻译能力。核心场景： |
| `paas/paas-console` | paas-console 是纷享销客 PaaS 的内部运维管理控制台，打包为 war 由 DispatcherServlet 托管，同时渲染 Freemarker 页面和 JSON 接口（pom.xml#L9-L11、src/main/w… |
| `paas/paas-db-operator` | paas-db-operator 是 PaaS 平台的数据库结构操作服务，通过 REST API 与 MQ 事件驱动，执行跨多数据库（PaaS/MySQL、BI/PostgreSQL、ClickHouse）的 DDL 变更。 |
| `paas/paas-db-scanner` | 本仓库是围绕 PostgreSQL 的 DBA 工具集与 CDC 变更生产者，明确不做业务应用的持久层：db-metric、db-statistic 启动时显式排除 DataSource 与 Mongo 自动装配，只以 JDBC 直连被管… |
| `paas/product-knowledge-base` | 当前：尚未解决业务问题。 product-knowledge-base 仍是空壳占位仓——默认分支业务内容只有 GitLab 自动生成的 README.md 模板（README.md#L1-L49），无产品知识正文、无服务实现。仓库名表达… |
| `prometheus/prometheus-deployment` | 本仓是声明式监控交付仓，通过 GitLab CI 将 Prometheus / Alertmanager / Thanos / Grafana / exporter 族装配进公司自建集群与客户集群。 |
| `sfa/fs-crm-sfa` | fs-crm-sfa 是 PaaS 平台之上的 CRM/SFA 售前售中业务前台：14 个 Maven 模块聚合为唯一部署单元 fs-crm-web（WAR），承载线索、客户、商机、订单、公海、CPQ 价策、支付与审批联动主链路，服务全公… |
| `sfa/fs-crm-sfa-agent` | fs-crm-sfa-agent 是面向 CRM/SFA 场景的 AI Agent 中台平台，将业务 Agent 能力标准化为流式 SSE 服务。 |
| `springboot/cms-spring-cloud` | 本仓是 CMS 的 Spring ConfigData starter：业务仓用 cms: import 加载远端配置，并获得热刷新与 ENC/LENC 解密。 |
| `springboot/elasticsearch-spring-boot` | elasticsearch-spring-boot 是一个 Spring Boot Starter，为公司业务应用提供开箱即用的 Elasticsearch 客户端与服务层。 |
| `springboot/fxiaoke-spring-cloud-parent` | 本仓库为纷享 Spring Boot 2.7 / Spring Cloud 2021 线的公司级 Parent POM：只做版本裁决与发布门禁，不做业务运行时。 |
| `springboot/mongo-spring-boot` | 本仓库只是"装配层"：把外部库 com.github.colin-lee:mongo-spring-support 的 MongoDataStoreFactoryBean 以自动配置方式暴露给业务应用；连接解析、Datastore 构建与… |
| `springboot/redis-spring-boot` | redis-spring-boot 是基础设施通用 Spring Boot Starter，为宿主 JVM 提供 Redis 连接能力。它以 JAR 形式嵌入宿主进程，无独立部署形态。 |
| `wechat-union/fs-wechat-union` | graph TD |
