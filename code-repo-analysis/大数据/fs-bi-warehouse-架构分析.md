# fs-bi-warehouse 源码架构分析报告

- 仓库地址：`git@git.firstshare.cn:bi/fs-bi-warehouse.git`
- 分析对象：本地克隆 `/Users/muqingji/code/Data/fs-bi-warehouse`

---

## 一、项目概况

- **项目简介**：纷享销客 BI 系统的**底层数仓项目**，负责业务数据的采集、同步、转换、聚合与存储，支撑 PostgreSQL → ClickHouse 的数仓数据链路，是 BI 报表/统计的算力底座（ODS/DWD/DWS 分层计算框架）。
- **业务领域**：数据仓库 / BI 大数据计算。
- **项目类型**：**多模块单体（Spring Boot 应用）**。`warehouse-dws`（WAR，主服务）+ `warehouse-common`（JAR，公共能力）。
- **技术栈**：
  - 语言：Java 21（`java.version=21`）
  - 构建：Maven，父 POM 为公司内部 `fxiaoke-spring-cloud-parent:2.7.0-SNAPSHOT`（Spring Cloud 体系）
  - 框架：**Spring Boot 2.7.x**（starter-web/aop/actuator/data-redis/cache/test）、MyBatis（PG + ClickHouse 双数据源）、ClickHouse JDBC 0.7.1、RocketMQ、Redis/Jedis、Caffeine/EHCache、Quartz、pagehelper
  - 运行环境：Tomcat（`spring-boot-starter-tomcat`，WAR 可外置）、JDK 21（JVM 参数 `--add-opens`）
- **打包/部署方式**：`warehouse-dws` 以 `war` 打包（`ServerApplication` 继承 `SpringBootServletInitializer`，支持外置 Tomcat），也可 jar 内嵌启动。
- **容器化**：未发现 Dockerfile / K8s 文件（需向运维确认实际部署形态）。

## 二、整体系统架构

### 1. 架构模式与分层
按数仓分层 + 应用分层：
- **数仓分层**：`ods`（原始数据同步层）、`dwd`（明细层）、`dws`（汇总/计算层）、`core`（底层能力）、`hamster`（内部工具）
- **应用分层**（每层内）：`controller` → `service` → `dao/mapper` → DB；`mq`（生产/消费）、`task`（定时）、`args`/`arg`（参数模型）、`model`/`bean`/`entity`（模型）
- **事件驱动**：RocketMQ 串联同步完成 → DWS 计算 → 统计视图刷新

### 2. 模块拆分
| 模块/包 | 职责 |
| --- | --- |
| `warehouse-dws`（主服务） | 数据同步、集成、聚合计算、拓扑管理、消息消费、任务调度、运维接口 |
| `warehouse-common` | 公共 DTO、工具、DAG 模型、数据库抽象（CH/PG）、消息定义、目标/指标模型 |

`warehouse-dws` 内部核心包：
- `ods`：ODS 同步层（`service` 同步服务、`integrate` 集成、`mq`、`task`、`rout` 路由、`compare` 数据比对、`etl`）
- `dwd`：明细层（`util`、`model`、`service`）
- `dws`：汇总计算层（`agg` 聚合、`service` 计算服务、`transform`、`strategy`、`interceptor`、`listener`、`mq`、`task`、`db`、`sqlgenerator`）
- `core`：基础设施（`chdb` ClickHouse、`paasdb` PostgreSQL、`db`、`config`、`enums`）
- `hamster`：仓鼠工具（`mq`、`util`）

### 3. 外部依赖服务
- 业务源库：PostgreSQL（ODS 源数据，多租户路由：`MybatisTenantPolicy` / `MybatisPaasTenantPolicy` / `BIPgDataSource` / `PgDataSource`）
- 分析库：ClickHouse（`clickhouse-jdbc:0.7.1`，Replicated*MergeTree 引擎，INC/STOCK/CAL 分区，TTL 过期）
- 消息：RocketMQ（`fs-bi-warehouse` 消费组：`DWSConsumer` 等，AutoConfMQPushConsumer）
- 缓存/锁：Redis + Jedis、Caffeine、EHCache
- 调度：Quartz；监控：Actuator
- 内部平台：`fs-pod-client`（容器/pod）、`fs-enterprise-id-account-converter`（企业 ID/账号转换）、`fxiaoke-helper`、`metrics-spring-boot-starter`

### 4. 请求整体流转链路
```
源业务库（PostgreSQL 各租户）
  → ODS 同步（DBTransferService / APgDBTransferService / BiDBTransferService）
  → 写入 ClickHouse ODS 层（分区/TTL 管理）
  → 发送计算事件（CalculateEventProducer）
  → DWSComputeConsumer 消费 → DWSComputeService / DWSRefreshService
  → 聚合计算（AggRuleService / CHAggDataService）写入 ClickHouse DWS 层
  → 统计视图/报表刷新（StatTopologyService / StatViewPreCalcCheckService）
  → 供上层 BI 报表/统计查询
```

## 三、目录结构详细解析

```
fs-bi-warehouse/
├── pom.xml                     # 聚合：warehouse-common / warehouse-dws；clickhouse-jdbc 0.7.1
├── README.md / AGENTS.md / CLAUDE.md
├── docs/                       # 技术栈说明、需求文档（stat-topology-batch-create 等）
├── openspec/                   # 开放规格
├── http/ test.http             # HTTP 调试
├── scripts/ style-checks.xml   # 脚本与代码风格
├── .cursor/skills/             # 团队共享 Codex 技能（多币种报表、SQL 解释、单测生成）
├── warehouse-common/
│   └── src/main/java/com/fxiaoke/bi/warehouse/common/
│       ├── util/               # 通用工具（CommonUtils、GrayManager、WarehouseConfig）
│       ├── entity/ bean/ arg/  # 公共模型
│       ├── dag/                # DAG 依赖模型
│       ├── constants/          # 常量/枚举
│       ├── provider/ component/ http/
│       ├── db/                 # 数据库抽象：entity、ch（ClickHouse）、dao、er
│       ├── mq/message/         # 消息体定义（DBUpdateMessage 等）
│       └── goal/               # 目标/指标模型
└── warehouse-dws/
    └── src/main/java/com/fxiaoke/bi/warehouse/
        ├── ServerApplication.java   # Spring Boot 入口
        ├── ods/               # ODS 同步层（service/integrate/mq/task/rout/compare/etl/controller）
        │                   #   service：DBTransferService/APgDBTransferService（PG→CH 同步）、DbSyncInfoService（同步配置）
        │                   #   entity：Biz2CHConsumer（批量写 CH 消费者）
        │                   #   mq：CalculateEventProducer（计算事件）、TransferEventConsumer、RouterChangeConsumer
        ├── dwd/               # 明细层
        ├── dws/               # 汇总计算层（agg/service/transform/strategy/interceptor/mq/task）
        ├── core/              # chdb/paasdb/db/config
        └── hamster/           # 内部工具（mq/util）
```

## 四、代码模块详细构成

### 1. 核心业务模块（warehouse-dws）
- **ODS 同步**：
  - `DBTransferService` / `APgDBTransferService` / `BiDBTransferService`：PostgreSQL → ClickHouse 数据同步
  - `IntegrateServiceImpl` / `CHDataToCHServiceImpl`：数据集成（含 CH→CH 同构迁移）
  - `DbSyncInfoService` / `DbTableSyncInfoService` / `AggDataSyncInfoService`：同步任务元数据
  - `BiDataSyncPolicyService`：同步策略；`DataSyncLicenseService`：同步许可证
  - `CHNodeService`（CH 节点）、`ClickhouseDbCommonService`、`ExecutePgSqlService`、`PGMetadataService`
  - `compare/ComparePgToChService`：PG/CH 数据比对
- **DWS 计算**：
  - `DWSComputeService`、`DWSRefreshService`（刷新）、`CHAggDataService`（聚合数据）、`AggRuleService`（聚合规则）、`WideTableService`（宽表）、`BillboardService`（排行榜）、`MappingService`、`CompareService`
  - `TopologyTableService` / `BiMtTopologyTableService` / `StatTopologyService`：**拓扑表管理**（下游依赖关系）
  - `StatViewPreCalcCheckService`：统计视图预计算校验；`BackgroundTaskService`：后台任务
- **任务/调度**：`ods/task`、`dws/task`（MergeTask、同步调度）
- **消息**：
  - 生产：`CalculateEventProducer`、`StatViewEventProducer`
  - 消费：`DWSComputeConsumer`（DWS 计算）、`DWSViewChangeConsumer`、`DWSCustomDimConsumer`、`DWSDelayEventConsumer`、`DWSStateEventConsumer`、`DWSMultiCurrencyConsumer`（多币种）、`RouterChangeConsumer`、`ChangedObjectAndFieldConsumer`、`TransferEventConsumer`、`HamsterEventConsumer`
- **运维/管理接口**：
  - `OdsController`：同步库/表状态管理、ClickHouse 建库建表、DDL 批量操作、分区/TTL 维护、数据比对、PG SQL 执行
  - `DwsController`：聚合规则启停、拓扑表批量操作、统计视图状态、`dbChangeEvent`、预览 SQL 生成

### 2. 公共基础模块（warehouse-common）
- `util`：`CommonUtils`、`GrayManager`（灰度）、`WarehouseConfig`（配置）
- `dag`：DAG 依赖模型（数仓链路编排）
- `db`：CH/PG 数据源抽象、ER 模型、DAO 基础
- `mq/message`：消息体（`DBUpdateMessage` 等）
- `goal`：目标/指标模型；`constants`：常量与枚举

### 3. 数据层设计
- **PostgreSQL**：多租户源库（`paasdb` 抽象：`BIPgDataSource` / `PgDataSource` / `MybatisTenantPolicy` / `MybatisPaasTenantPolicy`），承载同步任务元数据与业务源数据
- **ClickHouse**：核心分析库（`chdb` 抽象，`clickhouse-jdbc 0.7.1`），表引擎 ReplicatedReplacingMergeTree / ReplicatedMergeTree / ReplicatedAggregatingMergeTree，分区策略 INC/STOCK/CAL，TTL 过期清理，跨租户多实例路由
- **Redis**：分布式锁与元数据缓存（Jedis + starter-data-redis）
- **本地缓存**：Caffeine / EHCache（`ehcache.xml`）
- **RocketMQ**：事件驱动（计算事件、视图变更、多币种、状态事件等）
  - 消费组/消费者：`AutoConfMQPushConsumer` 自动装配；核心消费者 `DWSComputeConsumer`（DWSConsumer，失败重试 `cal_retry_times` 上限 20 次）、`DWSViewChangeConsumer`、`DWSCustomDimConsumer`、`DWSDelayEventConsumer`、`DWSStateEventConsumer`、`DWSMultiCurrencyConsumer`

### 4. 权限、认证、鉴权
- 服务为内部数仓服务：认证依赖部署环境（内网/网关），仓库内未见应用层用户认证框架（Spring Security）
- 企业隔离通过租户路由（`ei` 企业标识在接口路径/参数中出现，如 `/chJdbcUrl/{ei}`、`/statView/{tenantId}/{viewId}`）与多租户数据源策略实现
- License：`DataSyncLicenseService`、`LicenseService`（数据同步/计算许可证校验）

## 五、用到的全部框架 & 第三方组件清单

| 组件 | 作用 |
| --- | --- |
| Spring Boot 2.7.x | 应用框架（web/aop/actuator/data-redis/cache） |
| MyBatis | 持久层（PG/CH 双数据源、多租户路由） |
| ClickHouse JDBC 0.7.1 | 分析数据库访问 |
| PostgreSQL JDBC | 源业务库访问 |
| RocketMQ | 事件消息（生产/消费） |
| Redis + Jedis | 分布式锁、缓存 |
| Caffeine / EHCache | 本地缓存 |
| Quartz | 定时调度 |
| pagehelper | 分页 |
| Spring Boot Actuator | 健康检查与指标 |
| metrics-spring-boot-starter | 指标上报 |
| TOML4J | TOML 配置解析 |
| Guava | 集合/工具 |
| Lombok | 样板代码 |
| 内部 SDK | fxiaoke-helper、fs-pod-client、fs-enterprise-id-account-converter、test-spring-boot-starter |

## 六、核心业务流程拆解

### 1. PostgreSQL → ClickHouse 增量同步（ODS）
```
同步任务（定时/MQ/手工触发）
  → DbSyncInfoService 获取同步配置（目标库/表/分区策略）
  → APgDBTransferService / DBTransferService 读取 PostgreSQL 增量（时间戳/分区）
  → 字段映射与类型转换（IntegrateService）
  → 写入 ClickHouse（按 INC/STOCK/CAL 分区，Replicated*MergeTree）
  → 更新同步状态（updateSyncDbStatus）→ 发送计算事件（CalculateEventProducer）
```

### 2. DWS 聚合计算（事件驱动）
```
RocketMQ 计算事件（DBUpdateMessage）
  → DWSComputeConsumer（AutoConfMQPushConsumer，fs-bi-warehouse/DWSConsumer）
  → DWSComputeService（聚合计算）
  → AggRuleService / CHAggDataService（聚合规则 → ClickHouse 聚合表）
  → TopologyTableService（下游拓扑依赖）→ 级联刷新下游表
  → 发送统计视图刷新事件（StatViewEventProducer）
```

### 3. 统计视图刷新
```
StatViewEvent → DWSViewChangeConsumer / DWSCustomDimConsumer
  → StatViewPreCalcCheckService（预计算校验）
  → DWSRefreshService / StatTopologyService（刷新统计视图）
  → 上层 BI（fs-bi-stat / fs-bi-crm-report）查询结果就绪
```

### 4. 数据比对与修复
```
OdsController /compareChToPg、/comparePgToChSampleArg、/compareAndMarkDeletedData
  → ComparePgToChService（采样比对）
  → 差异定位 → 修复/重建（createChTable、repairPartition、modifyChTableTTL）
```

## 七、配置与环境

- **配置类型**：`application.properties`（`server.port=8080`、`process.name=warehouse-dws`、Hikari（maxActive 800、connectionTimeout 300s）、`spring.cache.jcache.config=classpath:ehcache.xml`、上传大小限制、JVM `--add-opens` 参数、Actuator 健康项配置）
- **多环境**：CMS/Apollo 类配置中心下发（`WarehouseConfig`、`ConfigHelper`），仓库内无多环境 profile 文件
- **MQ**：`AutoConfMQPushConsumer` 自动配置消费者（消费组/主题来自配置中心）
- **调度**：Quartz 任务定义在配置中心或代码注解（`dws/task`、`ods/task`）
- **构建**：Maven + Checkstyle（`style-checks.xml`）+ Sonar；测试 JUnit + Mockito

## 八、项目优缺点 & 风险点

**优点**
- 数仓分层清晰（ODS/DWD/DWS + core/hamster），事件驱动解耦同步与计算
- 多租户数据源与路由策略完善（PG/CH 双库多策略）
- ClickHouse 表引擎/分区/TTL 体系成熟，支撑大规模分析查询
- 有团队共享 Codex 技能与文档沉淀（多币种、SQL 解释、单测生成）

**现存问题/技术债务**
- `OdsController` / `DwsController` 暴露大量运维操作接口（建表、删表、执行 SQL），安全边界需严格管控
- 单一 WAR 承载同步+计算+调度+运维，模块内部包依赖较重（470+ Java 文件集中于 dws）
- 存在 `src/test` 中的演示/图算法代码（`dws/graph/Stack`、`Digraph`、`DirectedCycle` 等）疑似未完成迁移
- 依赖内部 SNAPSHOT 父 POM 与 SDK，升级受平台版本牵制
- 部分接口以 `{tenantId}` / `{id}` 路径传参，缺少统一参数校验/审计框架

**接手改造注意事项**
- 数据链路改动（同步/聚合）需回归 MQ 事件全链路（生产者 → 消费者 → 下游刷新）
- 修改 ClickHouse DDL 相关代码时先确认多租户实例与分区策略
- 遵循 AGENTS.md：优先使用 graphify 图谱定位架构/影响面，再读具体源码

## 九、需要补充核查的内容

- [ ] 生产环境 ClickHouse/PostgreSQL 集群拓扑与租户路由配置（配置中心下发，仓库未见）
- [ ] RocketMQ 主题/消费组/分片配置清单（`AutoConfMQPushConsumer` 参数来源）
- [ ] OdsController / DwsController 的网络暴露面与安全鉴权（重点核查）
- [ ] 数据库 DDL、表引擎与分区策略的集中定义（分散在代码/运维脚本）
- [ ] 部署拓扑（war 外置 Tomcat 还是 jar 内嵌、实例数、与上层 BI 服务调用关系）
- [ ] 容器化 / K8s / CI 流水线配置
- [ ] `src/test` 中 graph 算法代码与演示代码的去留
- [ ] fs-bi-warehouse 与 fs-bi / fs-bi-crm-report / fs-bi-udf-report 之间的同步与查询契约
- [ ] 多币种（DWSMultiCurrencyConsumer）与目标值（goal）模块的完整业务口径

---

## 十、代码走读路线（API → 数据层 / 下游服务，最完整力度）

> 文件路径均相对仓库根 `/Users/muqingji/code/Data/fs-bi-warehouse`（默认在 `warehouse-dws/src/main/java` 下）。

### 走读路线 A：ODS 增量同步（运维接口 → PostgreSQL → ClickHouse）

```
运维/调度/BI 平台
  │ POST /ods/syncDataByTable（{ids, tableName, tenantId, primaryKey, partition}）
  ▼
① Controller 层
  com/fxiaoke/bi/warehouse/ods/controller/OdsController.java
  └─ syncDataByTable()（第 328 行）
       ├─ 参数：ids（db_sync_info.id 列表）、tableName、tenantId、primaryKey、partition
       ├─ 有主键：dbTransferService.syncDataByTenantIdPrimaryKey(ids, tableName, tenantId, pks, true, partitionValue)
       └─ 无主键：dbTransferService.syncDataByTenantId(idList, tableName, [tenantId], partitionValue)

② 同步服务层
  com/fxiaoke/bi/warehouse/ods/service/DBTransferService.java
  ├─ syncDataByTenantId()（第 1111 行）
  │    ├─ pgCommonDao.queryDBSyncInfoById(dbSyncIds)                    ★PG：读取同步配置（db_sync_info）
  │    ├─ GrayManager.query_table_from_chdb：BizEnum.BI / CRM 分流（mt_data → object_data 表名映射）
  │    ├─ biPgDataSource.getConnectionByJdbcURL(pgDBUrl, pgSchemaName)  ★PG：建立源库连接
  │    ├─ pgMetadataService.loadSchemaIfInCache(...)                    ★PG：加载表结构 schema
  │    ├─ chMetadataService.loadTable(chSchemaName, chProxyUrl, chTableName) ★CH：校验/加载目标表结构
  │    ├─ Biz2CHConsumer.getInstance(chClientService, clickhouseTable, savePointSize, batchNum, ...)
  │    ├─ syncByTenantIdOffline(tenantIds, jdbcConnection, pgSchema, biz2CHConsumer, ...)
  │    └─ biz2CHConsumer.save()                                         落盘保存点
  └─ syncDataByTenantIdPrimaryKey()（第 1167 行）：按主键同步（resolveSourcePg → transfer2CHByTenantIdPrimaryKey）

③ 数据搬运（分页读取 → 批量写入）
  - DBTransferService.transfer2CHByTenantId()（第 1209 行）
       → BiDBTransferService.transfer2CHByTenantId(...)（ods/service/BiDBTransferService.java）
            ├─ 按 order by 分页拉取 PG 数据（batchQueryBeforeSize 预取）
            └─ 逐批交给 Biz2CHConsumer
  - 消费者：com/fxiaoke/bi/warehouse/ods/entity/Biz2CHConsumer.java
       ├─ add()：行缓存（bizLogCache，达到 batchQueryBeforeSize 触发 batchWrite）
       ├─ batchWrite()：批量写入 CH（writer.batchWrite）
       ├─ insertBeforeDataPlus(clickhouseTable, batchNum, orderByFields, ...)（第 134 行，分区预写）
       └─ save()：保存点/批量落库
  - CH 底层：core/chdb（chdbService）、chNodeService（CH 节点路由）、chClientService（CH 客户端）
  - 分区策略：INC（增量）/ STOCK（存量）/ CAL（计算），TTL 清理（modifyChTableTTL / checkChTableTTL）

④ 同步后事件
  - MergeTaskService.merge()（OdsController /doMergeAgg、/scheduleMergeByDb）
  - CalculateEventProducer（ods/mq/CalculateEventProducer.java）发送计算事件 → 进入走读路线 B
```

### 走读路线 B：DWS 聚合计算（RocketMQ 事件 → ClickHouse 聚合）

```
ODS 同步完成 / db 变更
  │ RocketMQ 消息（DBUpdateMessage，topic：BI_WAREHOUSE_EVENT / BI_WAREHOUSE_EVENT_GRAY 灰度）
  ▼
① MQ 消费者
  com/fxiaoke/bi/warehouse/dws/mq/consumer/DWSComputeConsumer.java
  └─ consumeMessage()（第 55 行）
       ├─ DBUpdateMessage.parseFromMsg(msg)：解析事件（pgDB/schema/表变更）
       ├─ 灰度规则：use_gray_topic_ei / use_gray_topic_pgdb → 转发灰度 topic
       ├─ dwsComputeService.dbDataUpdated(dbUpdateMessage)
       └─ 失败重试：cal_retry_times 属性 +1，重新投递（>20 次丢弃）；异常返回 RECONSUME_LATER
  （启动：@PostConstruct init() 创建 AutoConfMQPushConsumer("fs-bi-warehouse", "DWSConsumer", this)；
    onApplicationEvent 中 consumer.start()）

② DWS 计算服务
  com/fxiaoke/bi/warehouse/dws/service/DWSComputeService.java
  ├─ dbDataUpdated()（第 210 行）：入口，幂等/去重（calculatePgDB / copyInc2CalAfterIng 等静态集合）
  ├─ computeData()（第 372 行）：计算分发
  ├─ compute()（第 520 行）：主计算流程
  │    ├─ 聚合规则：AggRuleService / CHAggDataService（dws/service）→ ClickHouse 聚合表写入
  │    ├─ 宽表：WideTableService / processFilterIDWideTableSql（第 456 行）
  │    ├─ 拓扑级联：TopologyTableService / StatTopologyService（下游依赖表刷新）
  │    ├─ 目标值：selectChangeGoals()（第 885 行，goal 模块）
  │    └─ copyBefore / copyAfter / copyInc2CalAfterIng / copyCal2StockAfterIng（第 941 行）：层间拷贝
  └─ 完成后发送下游事件：StatViewEventProducer（dws/mq/producer/StatViewEventProducer.java）
       → DWSViewChangeConsumer / DWSCustomDimConsumer / DWSStateEventConsumer / DWSMultiCurrencyConsumer（dws/mq/consumer/）
```

### 走读路线 C：统计视图刷新（管理接口 → 预计算 SQL → CH）

```
POST /dws/dbChangeEvent、/dws/createPreViewSQL、/dws/createBatchPreViewSQL、/dws/createDetailViewSQL
  → com/fxiaoke/bi/warehouse/dws/controller/DwsController.java
       ├─ StatViewPreCalcCheckService（dws/service）：统计视图预计算校验
       ├─ DWSRefreshService / StatTopologyService：刷新统计视图
       └─ 结果写 ClickHouse，供上层 BI（fs-bi-stat / fs-bi-crm-report）查询
```

### 走读路线 D：数据比对与修复

```
POST /ods/compareChToPg、/ods/comparePgToChSampleArg、/ods/compareAndMarkDeletedData
  → com/fxiaoke/bi/warehouse/ods/compare/ComparePgToChService（ods/compare）
       → ComparePgToChServiceImpl（采样比对 PG vs CH）
  → 修复：/ods/repairPartition、/ods/modifyChTableTTL、/ods/createChTable、/ods/batchDDLOnCh
```

### 关键文件清单（走读速查）

| 环节 | 文件 |
| --- | --- |
| ODS 同步入口 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/ods/controller/OdsController.java` |
| ODS 同步服务 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/ods/service/DBTransferService.java` |
| 数据搬运 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/ods/service/BiDBTransferService.java` |
| CH 批量消费者 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/ods/entity/Biz2CHConsumer.java` |
| 同步配置（PG） | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/ods/dao/`（pgCommonDao） |
| 计算事件生产 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/ods/mq/CalculateEventProducer.java` |
| DWS 计算消费 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/dws/mq/consumer/DWSComputeConsumer.java` |
| DWS 计算服务 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/dws/service/DWSComputeService.java` |
| 聚合规则 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/dws/service/AggRuleService.java` |
| 拓扑管理 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/dws/service/TopologyTableService.java` |
| DWS 管理接口 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/dws/controller/DwsController.java` |
| CH/PAAS 底层 | `warehouse-dws/src/main/java/com/fxiaoke/bi/warehouse/core/chdb/`、`core/paasdb/` |
