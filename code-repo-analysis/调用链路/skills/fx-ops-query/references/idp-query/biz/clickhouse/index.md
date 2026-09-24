# ClickHouse 文档索引

> schema snapshot: 2026-08-01 | 191 张表（platform v5.10.0 tables.yaml）；字段、索引、分区、TTL 与单表 Markdown 已与 tenant-filters 同步

## 业务线筛选索引

各 biz 表级筛选与字段说明。通用拼 SQL 规则见 [idp-query-filter-hint.md](../../../idp-query-filter-hint.md)。

| biz | 文档 |
| --- | --- |
| `bi` | [bi](./bi.md) |
| `biz-app-log` | [biz-app-log](./biz-app-log.md) |
| `crm-audit-log` | [crm-audit-log](./crm-audit-log.md) |
| `semantic-eval` | [semantic-eval](./semantic-eval.md) |
| `semantic-log` | [semantic-log](./semantic-log.md)（表可能为空） |
| `semantic-system` | [semantic-system](./semantic-system.md)（表可能为空） |
| （全部已接入 CH 数据源） | [system-db](./system-db.md)（`system` 库默认可查） |

## 单表文档索引

### biz-app-log

下列文件是 `biz-app-log` 下的真实表文档。执行查询统一使用 `biz-app-log`，SQL 中指定真实表名。

**命名惯例**（双向）：表名 → 文档名：去掉 `_dist` 后缀，`_` → `-`（如 `log_cep_dist` → `log-cep.md`）；文档名 → 表名：`-` → `_`，加 `_dist` 后缀。例外见备注。

| 文档 | 对应表名 | 说明 |
| --- | --- | --- |
| app-log.md | `app_log_dist` | 应用日志 |
| api-bus-log.md | `apibus_log_dist` | API总线日志 |
| eye-trace.md | `eye_trace_dist` | 后端链路追踪 |
| biz-audit.md | `biz_audit_log_dist` | 跨业务通用审计日志 |
| biz-audit-dht.md | `biz_audit_log_dht_dist` | 业务审计 DHT 版（无 src/dest） |
| log-cep.md | `log_cep_dist` | CEP事件日志 |
| kpi-cep.md | `kpi_cep` | CEP KPI/异常明细（agg_sla，无 `_dist` 后缀） |
| cep-agg.md | `cep_minute_dist` / `cep_ea_dist` / `cep_daily_dist` / `cep_ea_daily_dist` / `cep_daily_ea_uid_dist` | CEP SLA 天/分钟聚合（agg_sla） |
| agg-databases.md | （总览） | agg_daily / agg_sla / agg_error 库说明 |
| known-gaps.md | （运行时缺口） | foneshare 实测缺口与 platform_gap 策略 |
| table-alias-map.md | （错名映射） | 错误/过时表名 → 真实表；profile 条件表 |
| high-frequency-cheatsheet.md | （时间列权威 + SQL 模板） | 强制时间列、`time_for_ckibana` 黑名单、出站 HTTP/集成取证 SQL |
| system-db.md | `system.*`（元数据路径） | 默认可查 `system` 库；`SHOW DATABASES` / `SHOW TABLES FROM system` / `query_log` / `processes` |
| biz-log-bi-agg.md | `biz_log_bi_agg_dist` | BI 报表 PV 聚合（agg_sla） |
| tomcat-access-daily.md | `tomcat_access_daily_dist` | Tomcat 小时聚合（agg_sla；表名 daily、粒度小时） |
| fs-cep-slow-error.md | `fs_cep_slow_error_dist` | CEP慢日志 |
| data-auth-log.md | `data_auth_log_dist` | 数据权限日志 |
| db-limit-log.md | `biz_db_limit_log_dist` | 数据库限流日志（表名前缀 `biz_`） |
| egress-log.md | `egress_nginx_access_dist` / `egress_sms_dist_tbl`（短信仅 foneshare） | 出口 HTTP / 短信 |
| log-error.md | `log_error_dist` | 错误日志 |
| log-error-daily.md | `log_error_daily_dist` | 应用错误按天聚合（agg_error） |
| flow-log.md | `fs_flow_exclusive_gateway_log_dist`（见正文；运行时见 flow-runtime-log） | 流程排他网关等 |
| frontend-trace-log.md | `front_trace_log_dist` | 前端链路追踪 |
| biz-log-function.md | `biz_log_function_dist` | APL函数执行日志（含 4 张函数业务表：function/function_user_execute/inner_function_api/function_user_api） |
| hulian-log.md | `crm_syncfirststage_dist` / `crm_syncsecondstage_dist` 等 | 互联同步（无 hulian_log_dist 单表） |
| integration-log.md | `data_sync_log_dist` | 数据同步汇总 |
| k8s-app-scale-log.md | `fs_k8s_app_scaler_metrics_dist` | K8s扩缩容日志（表名前缀 `fs_`） |
| k8s-event-log.md | `k8s_events_dist` | K8s事件日志 |
| nginx-log.md | ~~`nginx_log_dist`~~ | **已废弃**（all_inactive）；见 nginx-access.md |
| object-bulk-log.md | `object_data_bulk_log_dist` | 对象批量日志（表名含 `object_data_` 前缀） |
| object-data-search-log.md | `object_data_search_log_v_dist` | 对象 ES 搜索最终 DSL、执行路由与回放证据（视图名含 `_v_dist`） |
| openapi-log.md | `biz_log_openapi_dist` | 入站 OpenAPI（`openApiUrl`/`ei`/`ea`；过滤 `_time_second_`；无 `uri`/`method`） |
| paas-op-log.md | `paas_oplog_dist` | PaaS运维日志 |
| page-log.md | `page_dist` | 页面日志 |
| rpc-log.md | `rpc_dist` / `rpc_daily_dist` | RPC 汇总 + 按天聚合（agg_daily） |
| sentinel-block-log.md | `sentinel_block_dist` | 限流日志 |
| service-log.md | `service_dist` / `service_daily_dist` | 服务汇总 + 按天聚合（agg_daily） |
| slow-log.md | `slow_log_dist` | SQL慢日志 |
| stock-log.md | `stock_log_dist` | 库存日志 |
| tenant-object-stat.md | `tenant_object_stat_dist` | 租户对象记录数统计（对象粒度，去重 `status=''`，TTL 120天） |
| tenant-db-stat.md | `tenant_db_stat_dist` | 租户数据库表记录数统计（物理表粒度，去重 `status='normal'`，TTL 90天） |
| tomcat-log.md | `tomcat_access_dist` | Tomcat日志（表名 `tomcat_access_dist`） |
| tomcat-access-slow.md | `tomcat_access_slow_dist` | Tomcat慢日志 |
| ai-log.md | ~~`biz_log_ai_dist`~~ | **scan 黑名单 + 已从 tables.yaml 移除**；见 known-gaps / ai-log.md |
| erp-sync.md | `biz_log_erpsyncdata_dist` / `biz_log_erp_ipaas_log_dist` / `biz_log_erp_ipaas_probe_log_dist` / `biz_log_erp_sync_log_dist` / `erp_sync_monitor_dist` | ERP/iPaaS 集成与同步（logger + erp_sync；时间列见 high-frequency-cheatsheet） |
| biz-log-crmfeed.md | `biz_log_crmfeed_dist` | CRM 动态 Feed 操作日志；foneshare/ale 可能 platform_gap |
| biz-log-feeds-lifecycle.md | `biz_log_feeds_lifecycle_dist` | Feed 生命周期日志（截图反查 feedId）；foneshare/ale 可能 platform_gap |
| fast-notifier.md | `notifier_broadcast_ack_dist` | 快速广播 ack（失败率 / 延迟 / room·producer） |
| metadata-changes.md | `paas_metadata_changes_dist` | 元数据变更日志（表名前缀 `paas_`） |
| sql-slow.md | `sql_slow_dist` | ClickHouse/PG 慢查询明细 |
| mongo-slow.md | `mongo_slow_dist` | MongoDB慢查询日志 |
| rpc-slow.md | ~~`rpc_slow` / `rpc_slow_dist`~~ | **scan 黑名单排除**；用 rpc_dist + 耗时过滤 |
| nginx-access.md | `nginx_access_dist` | Nginx访问日志 |
| nginx-access-slow.md | ~~`nginx_access_slow_dist`~~ | **scan 黑名单排除**；优先 nginx_access_dist |
| front-trace-http.md | `front_trace_log_http_dist` | 前端HTTP链路日志 |
| front-trace-other.md | `front_trace_log_other_dist` | 前端其他链路日志 |
| pg-error-log.md | ~~`pg_error_log`~~ | **已废弃**（scan 排除）；见 log-error.md |
| flow-instance-log.md | `fs_flow_instance_log_dist` | 流程实例日志（表名前缀 `fs_`） |
| flow-execution-log.md | `fs_flow_execution_log_dist` | 流程执行节点日志（表名前缀 `fs_`） |
| flow-runtime-log.md | `biz_flow_runtime_log_dist` | 业务流程运行时日志（表名前缀 `biz_`） |
| rocketmq-log.md | （场景路由）P0=`biz_log_dispatch_dist`；P1=`app_log_dist` / mq_audit | RocketMQ/消费选表路由，非单表 schema |
| mq-dispatcher.md | `biz_log_dispatch_dist` | **MQ 调度/消费主表权威**（字段/SQL/抽样；reporter status 恒 success） |
| job-schedule-log.md | `job_schedule_event_log_dist` | Job调度事件日志（表名含 `_event`） |
| xxl-job-log.md | foneshare:`schedule_task_event_log_dist`；ale/mn:`xxl_job_schedule_log_dist` | Job/XXL 调度（按 profile） |
| sync-data-error.md | `sync_data_error_dist` | 数据同步错误日志 |
| modsecurity-audit.md | ~~`modsecurity_audit_log_dist`~~ | **已废弃**（all_inactive） |
| security-event-tracking.md | `security_event_tracking_dist` | 安全事件追踪 |
| workflow-log.md | ~~`biz_log_workflow_dist`~~ | **已废弃**；请用 [workflow-v2-log.md](./workflow-v2-log.md) |
| workflow-v2-log.md | `biz_log_workflow_v2_dist` | 工作流V2日志（表名前缀 `biz_log_`） |
| mq-audit.md | `biz_log_mq_audit_dist` | MQ审计日志（表名前缀 `biz_log_`） |
| biz-sql-stat.md | `biz_sql_stat_dist` | SQL统计日志 |
| biz-log-pg-lock.md | `biz_log_pg_lock_dist` | PG锁监控日志 |
| elastic-search-log.md | `elastic_search_log_dist` | ES集群日志 |
| fs-paas-auth.md | `fs_paas_auth_log_dist` | PaaS认证鉴权日志 |
| paas-agent-execute.md | `paas_agent_execute_log_dist` | PaaS Agent执行日志 |
| biz-job-log.md | `biz_job_log_dist` | 业务定时任务日志 |
| schedule-task-log.md | `schedule_task_event_log_dist` | 调度任务事件日志（表名含 `_event`） |
| log-center.md | `log_center_dist` | 日志中心统一入口（中间件原始日志：MongoDB/MySQL/PgBouncer/RocketMQ/ZooKeeper等） |

## platform 登记表（191 张，含有独立 playbook 的表）

> schema_verified_at: 2026-08-01 | platform: v5.10.0 | 共 191 张表；字段、alias、时间列和 local 索引以 tenant-filters YAML 为准

| 表名 | 说明（摘要） |
| --- | --- |
| `ai_payload_dist` | AI 交互负载数据分布式表，记录 AI Agent 调用过程中的消息负载、内容及元数据 |
| `alarm_log_dist` | 系统告警日志分布式表，存储基础设施或业务系统触发 the 告警详情、当前状态与通知发送历史。 |
| `android_network_upload_log_dist` | Android 端网络日志上传分布式表，记录客户端网络请求日志的上传记录 |
| `android_upload_log_dist` | Android 端上传日志分布式表，记录 Android 客户端日志上传信息 |
| `apibus_log_dist` | API 网关（API Bus）请求日志，记录经过 API 网关转发的请求信息，包括调用方、被调用方、请求路径、耗时、状态码等。用于接口调用监控和慢请求排查。 |
| `apl_code_generate_log_dist` | APL 自动代码生成日志分布式表，记录 APL 平台在自动生成业务/规则代码时的过程参数与异常信息。 |
| `app_log_dist` | 应用日志分布式表，存储后端 Java/Dubbo 应用的运行日志（按 pod 采集），包括日志级别、调用链追踪、RPC 信息等。 查询须带 _time_second_（timeGuard ≤24h，建议更短）并优先过滤 app（主键前缀，可加 profile）； msg 子串用 LIKE '%…%' 吃 ngrambf_v1，勿用 hasToken。 |
| `attacked_log_dist` | 网络安全攻击拦截日志分布式表，记录系统被恶意扫描、注入等网络攻击时的安全防御拦截详情。 |
| `bi_agg_diff_log_dist` | BI 聚合差异数据日志分布式表，记录商业智能（BI）数据在比对、校验中出现的异常差异记录。 |
| `bi_reconciliation_log_dist` | BI 业务数据对账日志分布式表，存储 BI 数据分析系统与上游核心业务系统定期对账的比对记录。 |
| `big_file_log_dist` | 大文件上传下载日志分布式表，监控平台中大文件的上传、下载、转存及分片处理细节与耗时指标。 |
| `big_front_end_generic_log_dist` | 大前端通用业务日志分布式表，存储 Web/H5/小程序等前端上报的通用业务事件、埋点及报错日志。 |
| `biz_access_stat_dist` | 业务接口访问统计分布式表，按接口/URI 维度统计系统的访问 PV、UV、平均耗时等流量指标。 |
| `biz_agg_resource_data_dist` | 业务资源数据聚合分布式表，用于汇总和聚合不同业务资源的使用状态与度量指标。 |
| `biz_audit_log_dht_dist` | 业务审计日志（DHT 分布式哈希表版本），结构与 biz_audit_log_dist 类似，但缺少 src/dest 字段。可能用于特定的审计场景或数据来源。 |
| `biz_audit_log_dist` | 跨业务通用审计日志，汇聚多个应用/模块的操作记录。按 appName、action、module、eventId 区分场景，涵盖 MQ 消费（multiPull）、i18n Redis 访问、CRM 账户规则、数据权限事件（DataEvent）、互联 OpenAPI、对象数据同步（db_union_es）等；部分记录含 objectApiNames/objectIds 及 src/dest。 |
| `biz_db_limit_log_dist` | 数据库限流日志，记录数据库访问的限流事件，包括系统负载、是否触发限流、数据库名称、方法调用等信息。用于数据库性能监控和限流策略分析。 |
| `biz_flow_runtime_log_dist` | 业务流程运行时日志分布式表，实时记录各类业务流、审批流节点的流转轨迹与处理状态。 |
| `biz_job_log_dist` | 业务定时任务执行日志分布式表，存储系统中各类后台定时 Job（如 Task/Flow）的启动、耗时与执行结果。 |
| `biz_log_bi_agg_dist` | 业务 BI 报表 PV 聚合分布式表，按租户、应用、日期、视图维度聚合 PV（页面浏览量）统计指标。 |
| `biz_log_bi_dist` | BI 报表中心业务日志分布式表，记录用户导出、浏览或生成 BI 复杂报表时的运行负载与审计日志。 |
| `biz_log_center_dist` | 业务日志中心集中存储分布式表，用于统一收集和存储平台核心业务流程的关键事件追踪。 |
| `biz_log_crm_syncdata_dist` | CRM 数据同步业务日志分布式表，记录 CRM 系统各实体数据在跨域、跨库同步过程中的日志。 |
| `biz_log_crmfeed_dist` | CRM 动态Feed操作日志分布式表，存储客户关系管理系统中动态消息、Feed 流的生成与流转详情。 |
| `biz_log_dingtalk_coolapp_dist` | 钉钉酷应用交互日志分布式表，记录企业微信/钉钉等酷应用组件运行时请求、回调及底层执行结果。 |
| `biz_log_dispatch_dist` | 消息队列聚合框架调度日志，记录事件调度的详细过程，包括调度时间、耗时、重试次数、事件ID、对象信息等。用于监控消息调度状态和排查调度延迟。 |
| `biz_log_dss_data_node_dist` | DSS 数据节点运行日志分布式表，记录数据同步系统（DSS）中数据路由节点的执行负载与报错。 |
| `biz_log_dsspollingmongo_dist` | DSS 轮询 MongoDB 数据源日志分布式表，监控 DSS 服务定期扫描、增量拉取 Mongo 数据的过程。 |
| `biz_log_erp_sync_log_dist` | ERP Sync 1.0 全链路日志（erp_sync 库）；过滤 **`createTime`**，无 `_time_second_` |
| `biz_log_erpdatamem_dist` | ERP 内存数据缓存日志分布式表，记录 ERP 系统在加载、维护内存数据结构时的日志信息。 |
| `biz_log_erpdatascreen_dist` | ERP 数据大屏查询日志分布式表，存储 ERP 可视化大屏进行数据聚合查询及性能调优的日志。 |
| `biz_log_erpsyncdata_dist` | ERP 吞吐/分阶段耗时（logger）；过滤 **`_time_second_`**；含 `sendDoDispatcherTime`/`parseTime`/`listenTime`/`allFinishTime` |
| `biz_log_feeds_lifecycle_dist` | Feed 动态生命周期日志分布式表，记录 Feed 数据从创建、流转、修改到归档销毁的完整生命轨迹。 |
| `biz_log_function_dist` | 函数执行日志，记录自定义函数/事件监听器的执行详情（耗时、队列、错误等） |
| `biz_log_function_user_api_dist` | 函数用户 API 日志，记录用户调用函数的 console.log/info 等输出内容 |
| `biz_log_function_user_execute_dist` | 函数用户执行日志，记录函数调用的入参、返回值、异常及执行耗时 |
| `biz_log_inner_function_api_dist` | 内部函数 API 日志，记录函数内部调用的平台 API（如 LogImpl.info）的请求/响应大小及耗时 |
| `biz_log_mq_audit_dist` | 业务消息队列审计日志分布式表，审计 RocketMQ/Kafka 消息的生产、发送确认与消费成功率。 |
| `biz_log_oaconnectoropendata_dist` | OA连接器开放数据日志表，记录钉钉/企业微信等OA连接器的开放数据事件日志 |
| `biz_log_openapi_dist` | 入站 OpenAPI；路径列 **`openApiUrl`**（无 `uri`/`method`）；过滤 **`_time_second_`** |
| `biz_log_paas_calculate_10min_dist` | PaaS 计算 10分钟聚合日志分布式表，记录计算任务的 10分钟级聚合耗时指标 |
| `biz_log_paas_calculate_dist` | PaaS 规则引擎计算日志分布式表，记录低代码平台在进行业务字段计算、自动化规则执行时的计算细节。 |
| `biz_log_pg_lock_dist` | PostgreSQL 数据库锁监控日志分布式表，记录后端 PostgreSQL 实例的排他锁、死锁及慢查询事件。 |
| `biz_log_sandbox_changeset_dist` | 沙箱环境变更集部署日志分布式表，记录开发者发布应用从沙箱热部署到开发/测试环境的过程。 |
| `biz_log_sfa_web_log_dist` | SFA 销售自动化 Web 访问日志分布式表，存储 SFA 业务前端的页面点击、接口调用及交互行为日志。 |
| `biz_log_version_dist` | 业务系统版本发布日志分布式表，记录各微服务及应用组件的版本部署、更新与回滚历史。 |
| `biz_log_workflow_v2_dist` | 业务工作流 V2 高级日志分布式表，记录改进版工作流引擎中复杂网关、并行任务分支的流转轨迹。 |
| `biz_rest_log_dist` | 业务 Rest 接口访问详情分布式表，记录各微服务向外暴露 the Restful API 被外部调用的入参、耗时和状态。 |
| `biz_sql_stat2_dist` | SQL 访问性能统计 V2 分布式表，聚合统计各数据库连接池、物理 SQL 的访问频度及慢 SQL 占比。 |
| `biz_sql_stat_dist` | SQL 统计日志表，按应用、数据库、表名和 SQL 操作类型聚合记录 SQL 访问次数，用于发现热点库表和读写操作突增 |
| `cep_daily_dist` | CEP 网关请求按天聚合统计表，按业务名称和 URI 维度汇总请求量、耗时、失败数及流量大小。 |
| `cep_daily_ea_uid_dist` | CEP 网关请求按天 PV/UV 聚合表，按企业账号维度统计每日的请求 PV 和独立用户 UV。 |
| `cep_ea_daily_dist` | CEP 网关请求按天企业维度聚合统计表，按业务和企业账号汇总请求量、耗时、失败数及流量大小。 |
| `cep_ea_dist` | CEP 网关请求企业维度分钟级聚合统计表，按业务和企业账号在 5 分钟粒度汇总请求量、耗时、失败数及流量大小。 |
| `cep_minute_dist` | CEP 网关请求分钟级聚合统计表，按业务和 URI 在 5 分钟粒度汇总请求量、耗时、失败数及流量大小。 |
| `cep_slow_dist` | CEP 网关慢请求分布式表，记录 CEP 网关请求中处理耗时超过限制的慢请求详情。 |
| `client_custom_bi_sdk_custom_performance_monitor_view_dist` | 自建应用 BI SDK 自定义性能监控视图，记录基于 BI SDK 的客户端页面加载性能数据 |
| `client_custom_custom_performance_monitor_view_dist` | 自建应用自定义性能监控视图，记录客户端自定义性能监控指标数据 |
| `client_custom_key_log_view_dist` | 自建应用关键日志视图，记录客户端自定义关键日志信息 |
| `client_customer_ava_errors_view_dist` | 客户 AVA 错误日志视图，记录客户环境中 AVA 应用相关的错误信息 |
| `client_customer_fs_universal_info_view_dist` | 客户通用信息日志视图，记录客户环境中的通用信息日志 |
| `client_customer_key_log_view_dist` | 客户关键日志视图，记录客户环境中的关键日志信息 |
| `client_customer_performance_view_dist` | 客户端客户视角性能监控数据表，记录APP中各业务模块页面加载和渲染的性能指标 |
| `client_upload_log_dist` | 客户端日志上传记录表，记录客户端上传的日志文件信息和内容 |
| `cmdb_mark_v2_dist` | CMDB 配置项标记 V2 分布式表，用于记录平台基础设施、集群节点及应用组件的元数据标记和标签。 |
| `crm_sync_del_event_dist` | CRM 数据同步删除事件分布式表，记录跨租户 CRM 数据同步中，源端数据删除在目标端的清理历史。 |
| `crm_sync_reconciliation_dist` | CRM 数据集成对账日志分布式表，记录 CRM 多租户间主数据复制在同步对齐时的对账及差异报告。 |
| `crm_syncdata_dist` | CRM 数据双向同步分布式表，记录多租户客户/联系人等核心业务实体的准实时增量同步日志。 |
| `crm_syncfirststage_dist` | 互联同步第一阶段日志，记录数据从源租户分发到目标租户时的匹配和分发结果 |
| `crm_syncsecondstage_dist` | 互联同步第二阶段日志，记录数据在目标租户侧的实际写入结果（包括目标数据、函数处理结果和同步状态） |
| `crm_syncstage_dist` | CRM 同步阶段状态跟踪分布式表，细粒度记录 CRM 同步管道中各阶段（读取、转换、落库）的耗时与吞吐。 |
| `data_auth_log_dist` | 数据权限查询日志，记录用户对 CRM 对象的数据权限验证结果，包含各类权限规则（CRM、部门、团队、临时授权等） |
| `data_sync_log_dist` | 数据同步日志汇总表，记录数据同步操作的统计信息（成功数、失败数、关联对象等） |
| `db_metric_operate_dist` | 数据库性能指标操作日志分布式表，用于监控运维人员对数据库做高危操作时的指令审计。 |
| `department_lifecycle_dist` | 部门组织架构变更生命周期分布式表，记录企业部门的新增、调整、合并与废弃的生命周期事件。 |
| `devops_event_dist` | DevOps运维事件记录表，记录运维平台中的配置变更、操作事件等 |
| `dimension_lifecycle_dist` | 维度定义变更生命周期分布式表，记录多维分析模型（BI）中自定义维度的生命周期变化。 |
| `doc_parse_task_metric_log_dist` | 文档解析任务度量指标日志分布式表，用于统计 pdf/doc 文件解析的成功率、处理字数和耗时。 |
| `egress_geo_v_dist` | 地理位置查询日志视图，记录 IP 地理位置查询请求的详细信息，包括查询 IP、返回的国家/省份/城市、供应商信息等。 |
| `egress_nginx_access` | 外网 Nginx 访问日志，记录通过外网出口 Nginx 的 HTTP 请求详情，包括请求方法、URI、状态码、耗时、客户端信息等。 |
| `egress_nginx_access_dist` | 出口 Nginx 代理访问日志分布式表，记录经过平台出口反向代理向外部系统发起请求的请求信息与响应。 |
| `egress_sms_dist_tbl` | 短信发送日志，记录所有通过短信网关发出的短信，包括手机号、短信内容、发送状态、供应商信息等。用于短信发送追踪和故障排查。 |
| `egress_sms_v_dist` | 短信发送日志视图，基于 egress_sms_dist_tbl 创建的 Distributed View（FINAL 查询），自动去除 ReplacingMergeTree 的重复数据。结构同 egress_sms_dist_tbl。 |
| `elastic_search_log_dist` | ElasticSearch集群日志表，记录ES集群的慢查询日志和节点运行日志 |
| `employee_access_dist` | 员工访问量统计表，按年月维度记录企业内员工的页面访问量（PV） |
| `employee_phone_dist` | 员工手机号信息表，记录企业员工绑定的手机号及其最近访问情况 |
| `enterprise_info_dist` | 企业信息表，记录注册企业的基本信息及状态变更 |
| `erp_sync_monitor_dist` | ERP 通道健康度（logger）；过滤 **`_time_second_`**；单表文档 [erp-sync.md](./erp-sync.md) |
| `erpdss_push_header_dist` | ERPDSS 数据推送头信息分布式表，记录 ERPDSS 系统发起推送事务时的头部元数据与校验参数。 |
| `event_center` | 发布系统事件中心分布式表，记录发布系统的事件信息，包括资源变更、操作日志等。 |
| `event_center_dist` | 系统事件中心分发历史分布式表，集中存储系统级发布/订阅事件在各个通道的派发详情。 |
| `eye_trace_dist` | 后端链路追踪日志，记录微服务之间的 RPC 调用和数据库访问的链路信息，包括调用方法、参数、耗时等。用于分布式链路追踪和性能分析。 |
| `fastapi_access_dist` | FastAPI 框架访问日志分布式表，监控平台中采用 FastAPI 架构的微服务接口吞吐量与耗时。 |
| `fcp_access_dist` | FCP 敏捷平台页面及 API 访问日志分布式表，用于记录平台开发套件核心功能的访问情况。 |
| `file_audit_log_dist` | 文件安全审计日志分布式表，专门审计敏感文件（如合同、导出表）的下载、分享、删除及查阅人。 |
| `fmcg_audit_log_dist` | 快消业务（FMCG）审计日志分布式表，记录业务操作（如促销创建、门店分配）的审计历史以供溯源。 |
| `front_end_performance_agg_dist` | 前端性能聚合指标表，按天聚合前端页面加载性能的统计指标（P80、均值、计数分布等） |
| `front_perf_android_daily_dist` | Android前端性能日报表，按天统计Android客户端的API调用耗时分布及质量评级 |
| `front_perf_android_opname_daily_dist` | Android前端操作性能日报表，按天统计Android客户端各操作名称的耗时P80分位及请求数 |
| `front_trace_log_dist` | 前端全链路追踪日志分布式表，存储来自客户端（移动端/小程序/H5）的 HTTP 请求链路 span 数据，包含设备信息、地理位置、请求耗时、状态码等。底层 local 表为 VIEW，UNION 了 http/other/old 三张表。 |
| `front_trace_log_http_dist` | 前端 HTTP 请求链路日志，存储移动端/H5 HTTP 请求的 span 数据 |
| `front_trace_log_other_dist` | 前端其他链路日志，存储非 HTTP 请求的 span 数据（如小程序、WebSocket 等） |
| `fs_cep_slow_error_dist` | CEP 网关慢请求与错误日志，记录通过 CEP 网关的慢请求和错误请求的详细信息，包括请求参数、响应体、耗时等。用于排查慢接口和错误请求。 查询须带时间过滤（timeGuard ≤24h，建议更短）并优先过滤 bizName（主键相关）。 |
| `fs_dataplatform_log_dist` | FS 数据平台服务日志分布式表，存储数据集成与 ETL 计算管道本身的运行状况与异常堆栈。 |
| `fs_flow_exclusive_gateway_log_dist` | 流程排他网关日志，记录工作流中排他网关（条件分支）的执行路径选择 |
| `fs_flow_execution_log_dist` | 流程执行节点日志，记录工作流中各活动节点（如自定义函数）的执行状态和结果 |
| `fs_flow_executions_log_dist` | 工作流执行日志表，记录工作流实例的执行日志和链路追踪信息 |
| `fs_flow_instance_log_dist` | 流程实例日志，记录工作流/审批流的完整生命周期（从创建到结束），含耗时和状态 |
| `fs_k8s_app_scaler_metrics_dist` | K8s 应用扩缩容指标，记录容器资源的 CPU/内存使用率及请求/限制值 |
| `fs_paas_auth_log_dist` | FS PaaS 平台认证与鉴权日志分布式表，记录 OAuth2、Feishu API 访问过程中的授权鉴权日志。 |
| `fs_qixin_stat_dist` | 企信消息统计表，记录企业微信群聊消息的发送统计和时间维度信息 |
| `fs_warehouse_statistic_dist` | 仓储出入库统计分析分布式表，存储库存变更、物料转移的汇总度量指标。 |
| `function_execute_stage_agg_dist` | 函数执行阶段聚合统计表，按租户、API、阶段和日期统计函数执行的调用次数和唯一ID数量 |
| `function_execute_stage_log_mv_dist` | 函数执行阶段日志物化视图表，记录每个函数调用在各阶段（开始/执行开始/执行结束/结束）的状态、耗时和错误信息 |
| `generic_biz_log_dist` | 通用业务流程执行日志分布式表，提供未分类的自定义业务日志的标准化格式存储。 |
| `i18n_access_req_dist` | I18n 语言包加载请求日志分布式表，监控客户端向 CDN 或后端请求多语言翻译文件时的流量与耗时。 |
| `im_stat_dist` | IM即时通讯统计表，记录消息的发送者、参与者和时间维度信息 |
| `imaginary_log_dist` | Imaginary 文档预览服务日志分布式表，记录文档转 PDF、图片生成等高负载预览任务的生命周期。 |
| `job_schedule_event_log_dist` | Job 定时任务调度事件日志分布式表，记录调度中心发出 Job 触发指令的事件流水及节点分布。 底层 job_schedule_event_log_v 视图与 Distributed 元数据在 rpcId 等列上不一致，SELECT * 暂不可用。 |
| `k8s_events_dist` | Kubernetes 事件日志分布式表，存储 K8s 集群中 Event 资源的变更事件，包括 Pod 调度、扩缩容、资源状态变化等集群级事件。 |
| `kpi_cep` | CEP 网关 KPI 明细表，记录错误/异常请求的完整链路信息，包含请求详情、客户端信息、服务端信息及分布式追踪数据。 |
| `kwq_upload_log_dist` | KWQ业务上传日志表，记录客户端上传文件的设备信息、地理位置、WiFi环境和业务参数 |
| `log_center_dist` | 日志中心统一入口日志分布式表，存储日志收集层（Fluentbit/Logstash）自身状态与传输速率。 |
| `log_cep_dist` | CEP 网关访问日志，记录经过 CEP 网关的所有 API 请求，包括客户端信息、请求路径、响应状态、地理位置、服务端信息等。是全量 API 网关访问日志的核心表。 查询须带 stamp 时间过滤（timeGuard ≤24h，建议更短）并优先过滤 bizName（主键前缀）。 |
| `log_error_5m_dist` | 应用错误日志按 5 分钟聚合统计表，按应用、集群、环境维度汇总每 5 分钟的 ERROR 级别日志条数。用于错误率细粒度监控与告警，非明细数据（明细见 log_error_dist）。 |
| `log_error_daily_dist` | 应用错误日志按天聚合统计表，按应用、集群、环境维度汇总每天的 ERROR 级别日志条数。用于错误趋势监控与告警，非明细数据（明细见 log_error_dist）。 |
| `log_error_dist` | 应用错误日志，记录各微服务运行时产生的 ERROR 级别日志，包括错误消息、异常堆栈、应用名称等。用于错误监控和故障排查。 |
| `logback_metrics_dist` | Logback 日志系统输出指标分布式表，按级别、logger 维度统计微服务产生的日志总量指标。 |
| `marketing_audit_log_dist` | 数字营销活动审计日志分布式表，记录促销码派发、短信发送、优惠券调整等关键操作审计日志。 |
| `metrics_dist` | 系统基础性能指标分布式表，包含 CPU/内存/磁盘读写/并发数等核心服务器底层性能数据。 |
| `mongo_slow_dist` | MongoDB慢查询日志表，记录慢查询的集合、操作类型、执行计划、锁信息和耗时统计 |
| `network_log_dist` | 网络连接与通信日志分布式表，捕获异常 TCP 连接、DNS 解析延迟及跨机房通信失败日志。 |
| `nginx_access_dist` | Nginx 反向代理访问日志分布式表，记录前端主入口 Nginx 代理的 HTTP 请求报文、耗时和状态码。 |
| `nginx_lua_miss_log_dist` | Nginx Lua脚本缓存未命中日志表，记录Lua脚本中缓存查询未命中的键 |
| `nomon_history_dist` | 新监控(Nomon)报警历史记录分布式表，持久化保存各指标监控项的报警触发及自动恢复历史。 |
| `notifier_broadcast_ack_dist` | 快速广播消息确认日志，记录消息通知的投递统计信息，包括生产者、耗时、成功/失败数、消息内容等。用于消息广播系统的监控和故障排查。 |
| `oa_conn_log_dist` | OA连接日志表，记录与外部OA系统（如企业微信、钉钉等）的连接事件 |
| `object_data_bulk_log_dist` | 对象数据批量操作日志，记录 ES 索引的批量操作（索引、删除等），包含操作类型、索引名、文档数等 |
| `object_data_search_log_v_dist` | 对象实体数据全文搜索日志视图分布式表，分析低代码实体搜索的检索词、分词耗时与召回率。 |
| `organization_security_dist` | 组织架构安全策略变更日志分布式表，记录多维度安全边界设置、RLS 策略及权限包更新历史。 |
| `orion_server_log_dist` | Orion/Orion-Store服务端应用日志表，记录服务的运行日志、级别和业务信息 |
| `paas_action_bus_dist` | PaaS 事件总线动作流转分布式表，记录低代码动作脚本（Action）被总线派发的执行轨迹。 |
| `paas_agent_audit_log_dist` | PaaS AI Agent 智能体审计日志分布式表，审计 AI 助手被使用时的输入 prompt、耗时与扣费情况。 |
| `paas_agent_detail_log_dist` | PaaS Agent执行详细日志表，记录每次Agent调用的输入输出、Token消耗、步骤、耗时和错误信息 |
| `paas_agent_execute_log_dist` | PaaS Agent执行日志表，记录每次Agent调用的模型、指令、回答、Token消耗和执行结果 |
| `paas_agent_request_index_dist` | PaaS Agent请求索引表，记录每次Agent请求的完整链路信息，包括状态、根因分析、失败归属和指标数据 |
| `paas_metadata_changes_dist` | 业务元数据变更 oplog，记录元数据变更事件的详细过程，包括操作类型、涉及对象、各步骤耗时等。用于追踪业务层发出的元数据变更操作。 |
| `paas_oplog_dist` | PaaS 平台操作日志分布式表，记录数据库变更操作（CDC/OpLog），包括插入、更新、删除操作的 before/after 数据快照，用于数据审计和变更追踪。 |
| `paas_pg_object_changes_dist` | PaaS 实体底层 PG 物理表变更分布式表，记录当用户在低代码界面修改字段定义时物理表的 DDL 历史。 |
| `paas_user_function_dist` | 平台用户自定义函数（云函数）分布式表，记录用户在低代码平台中定义的业务逻辑函数及其绑定对象、版本和状态信息。 |
| `paas_workflow_statistics_agg_dist` | PaaS 工作流统计数据聚合分布式表，按维度汇总工作流的流转效率、执行次数等性能统计指标。 |
| `paas_workflow_statistics_agg_max_dist` | PaaS 工作流统计聚合最大值表，用于记录工作流执行或审批耗时的最大极限值指标。 |
| `paas_workflow_statistics_dist` | PaaS 工作流统计明细分布式表，记录单个流程实例 of 耗时、效率、异常退回频次统计。 |
| `page_dist` | 页面访问统计汇总表，按 URI 维度聚合 PV、耗时、状态码分布等指标 |
| `personnel_lifecycle_dist` | 员工人事生命周期变更分布式表，记录入职、转正、调岗、离职等组织人事关系变更过程。 |
| `phone_access_dist` | 手机端访问统计分布式表，按手机号维度统计各企业用户的累计访问次数（PV）和最近访问时间。 |
| `product_fs_paas_flow_log_dist` | 流程平台日志（产品侧），记录工作流触发/匹配/执行的详细日志，含规则匹配结果和过期时间 |
| `product_workflow_queue_log_dist` | 产品工作流队列日志分布式表，存储工作流任务在队列中的入队、出队、重试及状态流转日志。 |
| `product_workflow_queue_log_v_dist` | 工作流队列日志视图（BI 版），在 product_workflow_queue_log 基础上增加 BI 平台标准字段，时间戳为 UInt64 毫秒格式 |
| `python_app_log_dist` | Python 微服务应用日志分布式表，记录平台中 Python 计算/AI 相关微服务的运行日志。 |
| `qixin_biz_event_dist` | 企信业务事件通知日志分布式表，记录协同办公中业务消息、IM 机器人卡片事件的派发。 |
| `rocketmq_client_log_dist` | RocketMQ 客户端日志分布式表，记录 RocketMQ 客户端运行时产生的日志（包括日志级别、类名、消息、堆栈等），用于排查消息收发问题。 |
| `rpc_daily_dist` | RPC 调用按天聚合统计表，按应用和模块维度汇总调用量、耗时、失败数、慢调用数及分位分布。 |
| `rpc_dist` | RPC 调用统计汇总表，按 app/module 等维度聚合调用次数、失败数、慢调用与耗时分布；无 interface 字段（接口维度用 module）；时间范围过滤请用 _time_second_ |
| `schedule_task_event_log_dist` | 调度任务事件流水日志分布式表，记录 xxl-job 等任务在集群中分片广播、状态转化的事件流水。 |
| `security_event_tracking_dist` | 安全合规事件追踪分布式表，专门追踪异常敏感查询、跨域导出、解密操作的安全合规日志。 |
| `sentinel_block` | Sentinel 限流熔断拦截日志分布式表：记录被 block 的请求（原因、规则、资源名等），用于排查接口被限流/熔断。Open/SQL 可用名：sentinel_block 与 sentinel_block_dist（孪生 Distributed，列同构）。 |
| `sentinel_block_dist` | Sentinel 限流熔断拦截日志分布式表（与 sentinel_block 孪生，列同构）。Open/SQL 可用名：sentinel_block 与 sentinel_block_dist。 |
| `sentinel_metrics_dist` | Sentinel 限流熔断器指标分布式表，统计不同资源在 Sentinel 侧的 QPS、拒绝数、异常数。 |
| `sentinel_suggest_dist` | Sentinel 自适应限流建议分布式表，根据近期负载模型，推荐的最优限流阈值建议。 |
| `service_daily_dist` | 服务调用按天聚合统计表，按应用和方法维度汇总调用量、耗时、失败数、慢调用数及分位分布。 |
| `service_dist` | 服务调用统计汇总表，按应用、模块、方法等维度聚合调用次数、失败数、耗时分布，与 rpc_dist 类似但增加了 method 字段；时间范围过滤请用 _time_second_ |
| `sfa_audit_log_dist` | 销售漏斗与合同审批审计日志分布式表，记录 SFA 核心商业逻辑的修改和审批审计。 |
| `slow_log_dist` | SQL 慢查询日志表，记录执行较慢的 SQL 语句详情，包括查询语句、耗时、数据库名、影响行数等 |
| `sms_send_history_dist` | 短信发送历史记录分布式表，记录各企业通过不同短信服务商发送短信的详情，包括发送状态、短信类型及内容。 |
| `sql_slow_dist` | ClickHouse & PG 慢 SQL 查询明细分布式表，收集平台中所有的慢查询执行计划、查询用户与消耗资源。 |
| `stock_log_dist` | 库存操作日志，记录库存变更操作（如出入库），包含操作详情、耗时、关联对象等信息 |
| `stone_transfer_dist` | Stone 平台云文件上传转移日志分布式表，存储文件在 COS/OSS 存储桶之间异步迁移的数据记录。 |
| `sync_data_error_dist` | 数据同步错误明细表，记录每次同步失败的具体错误信息 |
| `tenant_db_stat_dist` | 租户数据库表记录数统计，按租户、数据库、schema、物理表记录每次统计得到的数据行数。用于跨租户容量盘点、租户级表规模分析和异常增长排查。 |
| `tenant_object_stat_dist` | 租户对象记录数统计，按租户、对象 API 名称、物理表记录每次统计得到的数据行数。用于查看租户有哪些对象、每个对象有多少数据，以及跨租户对象规模分析。 |
| `tomcat_access_broken_dist` | Tomcat应用访问中断/异常日志分布式表，记录微服务HTTP请求中的中断、异常或不合规响应日志，包含Pod信息和原始日志内容。 |
| `tomcat_access_daily_dist` | Tomcat 访问日志按小时聚合统计表，按应用和 URI 维度汇总每小时请求量及链路追踪信息。 |
| `tomcat_access_dist` | Tomcat 访问日志分布式表，记录 HTTP 请求的完整访问日志，包括请求方法、URI、状态码、耗时、请求/响应大小、链路追踪信息等，用于接口性能分析和问题排查。 查询须带 _time_second_ 时间过滤（timeGuard ≤24h，建议更短）并优先过滤 app（主键前缀，可加 profile）。 |
| `tomcat_access_slow` | Tomcat 慢请求日志分布式表：响应超过阈值的 HTTP 请求详情，结构与 tomcat_access_dist 类似并带更多跳过索引，用于慢接口与性能分析。Open/SQL 可用名：tomcat_access_slow 与 tomcat_access_slow_dist（孪生 Distributed，列同构）。查询须带 _time_second_ 时间窗（≤24h）并优先过滤 app/profile。 |
| `tomcat_access_slow_dist` | Tomcat 慢请求日志分布式表（与 tomcat_access_slow 孪生，列同构）。Open/SQL 可用名：tomcat_access_slow 与 tomcat_access_slow_dist。查询须带 _time_second_ 时间窗（≤24h）并优先过滤 app/profile。 |
| `web_client_log_agg_dist` | Web客户端性能日志聚合分布式表，按天和企业账号维度聚合统计前端页面加载耗时（总量/UI/网络/渲染）和不同耗时区间的访问次数分布。 |
| `web_client_log_dist` | Web 客户端异常与埋点日志分布式表，收集前端浏览器的 js runtime 报错、首屏耗时及静态资源加载。 |
| `web_client_log_uipaas_agg_state_dist` | Web客户端UIPaaS性能聚合状态分布式表，按天和企业账号维度聚合前端页面JS URL的性能指标（总量/渲染/网络耗时及分位值），数据以AggregateFunction状态存储。 |
| `www_log_dist` | Web站点HTTP访问日志分布式表（Nginx/网关层），记录所有通过网关转发的HTTP请求详情，包含客户端信息、请求方法、URI、状态码、耗时、Location头及多种链路追踪标识。 |
| `xxl_job_schedule_log_dist` | XXL-Job 分布式任务调度日志，记录每次 Job 分发至具体执行器后的返回值、日志和状态。 |

## 相关文档

- [clickhouse.md](../clickhouse.md) — ClickHouse 查询入口
- [idp-query-clickhouse.md](../../../idp-query-clickhouse.md) — ClickHouse 查询规则
- [diagnostic-scenarios.md](./diagnostic-scenarios.md) — 按诊断场景选表指引
- [reqId-traceId-rpcId.md](./reqId-traceId-rpcId.md) — reqId/traceId/rpcId 三层标识语义、rpcId 覆盖矩阵、精准诊断策略
