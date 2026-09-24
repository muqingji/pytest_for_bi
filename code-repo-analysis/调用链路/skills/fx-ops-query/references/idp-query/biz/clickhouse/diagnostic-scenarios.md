# ClickHouse 诊断场景-表映射指引

> schema_verified_at: 2026-07-25 | platform: v4.37.3

按常见诊断场景列出推荐查询的表及查询目的。

## 请求链路追踪

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| HTTP请求追踪 | `nginx_access_dist`、`nginx_access_slow_dist` | 入口Nginx日志，含URI/耗时/状态码 |
| 后端链路追踪 | `eye_trace_dist` | 后端服务间调用链 |
| 前端HTTP追踪 | `front_trace_log_http_dist` | 前端HTTP span数据 |
| 前端非HTTP追踪 | `front_trace_log_other_dist` | 小程序/WebSocket span数据 |
| CEP事件追踪 | `log_cep_dist` | CEP网关请求详情 |
| CEP KPI/异常样本 | `kpi_cep` | agg_sla 异常/KPI 明细（非全量） |
| CEP 5 分钟趋势 | `cep_minute_dist` / `cep_ea_dist` | SLA 聚合，锁故障窗与企业/URI |
| CEP 天级 SLA | `cep_daily_dist` / `cep_ea_daily_dist` | 长周期失败率与容量 |
| CEP 企业 PV/UV | `cep_daily_ea_uid_dist` | 须 `countMerge`/`uniqMerge` |
| RPC调用追踪 | `rpc_dist` | RPC 调用汇总（短窗） |
| RPC 天级容量/失败 | `rpc_daily_dist` | agg_daily 按天 |

> **rpcId 精准查询**: **traceId = 一次点击/开页**（不是单次 RPC）；其下可有多个 rpcId。仅按 traceId 查会被无关 RPC 误导。推荐先从 `log_cep_dist` 拿到 traceId + rpcId，再用 `traceId + rpcId` 精准查。rpcId 目标形态为字符串 ID（旧 `x.y.z` 层级逐步废弃）。完整语义与覆盖矩阵见 [reqId-traceId-rpcId.md](./reqId-traceId-rpcId.md)。

## 报错/异常排查

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| 应用错误 | `log_error_dist` | 应用层错误日志（最常用） |
| 应用错误天级趋势 | `log_error_daily_dist` | agg_error 按天；时间列 `_time_second_` |
| CEP错误 | `log_cep_dist` | CEP网关错误（含errorCode） |
| CEP KPI 异常明细 | `kpi_cep` | 错误/异常请求 KPI 样本（agg_sla） |
| PG数据库错误 | `pg_error_log` | PostgreSQL引擎级错误（部分环境亦有 `~~pg_error_log~~（已废弃，见 log-error.md）`） |
| 数据同步错误 | `sync_data_error_dist` | 同步失败明细 |
| Agent执行失败 | `paas_agent_execute_log_dist` | Agent调用错误 |
| 前端错误视图 | `client_customer_ava_errors_view_dist` | 客户端错误聚合 |

## 性能/慢查询

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| SQL慢查询 | `sql_slow_dist` | MySQL/PG慢SQL明细 |
| Mongo慢查询 | `mongo_slow_dist` | MongoDB慢查询 |
| CEP慢请求 | `fs_cep_slow_error_dist` | CEP网关慢请求 |
| CEP 慢/失败趋势 | `cep_minute_dist`（`slowCount`/`failCount`） | 5 分钟聚合，非明细 |
| RPC慢调用 | `rpc_slow` | RPC模块间慢调用统计 |
| 服务调用天级失败 | `service_daily_dist` | agg_daily 按 app+method |
| Tomcat慢请求 | `tomcat_access_slow_dist` | Tomcat应用层慢请求 |
| Tomcat 小时访问量 | `tomcat_access_daily_dist` | 按 app/uri/trace 小时聚合（TTL 约 30 天） |
| Nginx慢请求 | `nginx_access_slow_dist` | 入口层慢请求 |
| 中间件原始慢查询日志 | `log_center_dist` | 按 `service_name` 过滤：`mongodb`/`mysql`/`pgbouncer`，Grafana 面板数据源 |

## 数据库问题

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| PG锁等待/死锁 | `biz_log_pg_lock_dist` | PG排他锁/死锁监控 |
| PG错误 | `pg_error_log` | PG引擎报错 |
| SQL热点分析 | `biz_sql_stat_dist` | 按库/表聚合SQL操作统计 |
| SQL慢查询 | `sql_slow_dist` | 慢SQL明细 |
| DB限流事件 | `biz_db_limit_log_dist` | 数据库限流触达记录；单 trace 收敛见 `fx-ops` `report-quality-gate.md` §2d |

## 工作流/审批流

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| 流程实例追踪 | `fs_flow_instance_log_dist` | 工作流生命周期（创建→结束） |
| 流程节点执行 | `fs_flow_execution_log_dist` | 各活动节点执行结果 |
| 流程运行时轨迹 | `biz_flow_runtime_log_dist` | 节点流转轨迹与处理状态 |
| 网关分流日志 | `fs_flow_exclusive_gateway_log_dist` | 排他网关分流决策 |
| 工作流执行日志 | `~~~~biz_log_workflow_dist~~（已废弃，见 biz_log_workflow_v2_dist）~~（已废弃，见 biz_log_workflow_v2_dist）` | 底层节点状态变化 |
| 工作流V2日志 | `biz_log_workflow_v2_dist` | V2引擎复杂网关/并行分支 |

## 消息队列

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| **MQ 消费/调度（首选）** | **`biz_log_dispatch_dist`** | **fail/delay/re-dispatch、tries、delayCost**；权威文档 **mq-dispatcher.md**（路由见 rocketmq-log.md） |
| MQ 投递消费审计 | `biz_log_mq_audit_dist` | msgId 级 status/延迟/重消费 |
| RocketMQ 客户端/业务封装文本 | `app_log_dist` | logger 过滤；路由见 rocketmq-log.md |
| Kafka 客户端（无 audit/dispatch） | `app_log_dist` / `log_error_dist` | logger=`com.fxiaoke.support.*`；列名 `logger`/`msg` 与 `loggerName`；lag 走 Prometheus `kafka_consumergroup_lag` |
| RocketMQ Broker 运行日志 | `log_center_dist` | `service_name = 'rocketmq'`，查水位/堆积/Broker状态 |
| 快速广播通知 | `notifier_broadcast_ack_dist` | 消息通知投递统计；权威文档 **fast-notifier.md** |

## 定时任务

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| Job调度事件 | `job_schedule_event_log_dist` | 调度中心触发指令流水 |
| XXL-Job / 调度任务 | `schedule_task_event_log_dist`（foneshare 首选）；`xxl_job_schedule_log_dist`（ale/mengniu） | 见 xxl-job-log.md / schedule-task-log.md |
| 调度任务事件 | `schedule_task_event_log_dist` | 分片广播/状态转化流水 |
| 业务Job执行 | `biz_job_log_dist` | 后台Job启动/耗时/结果 |

## 安全审计

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| WAF拦截 | `~~~~modsecurity_audit_log_dist~~（已废弃）~~（已废弃）` | Web防火墙攻击检测 |
| 安全事件 | `security_event_tracking_dist` | 敏感查询/导出/解密追踪 |
| 业务审计 | `biz_audit_log_dist` | 业务操作审计 |
| CRM审计 | `audit_log`（crm-audit-log） | CRM专用审计 |
| 数据权限 | `data_auth_log_dist` | 数据权限鉴权日志 |
| PaaS认证 | `fs_paas_auth_log_dist` | OAuth2/飞书鉴权日志 |

## K8s/基础设施

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| K8s事件 | `k8s_events_dist` | Pod OOMKilled/驱逐/探针失败 |
| 扩缩容事件 | `fs_k8s_app_scaler_metrics_dist` | 自动扩缩容指标 |
| ES集群 | `elastic_search_log_dist` | ES慢查询/节点日志 |
| 中间件原始日志 | `log_center_dist` | 按 `service_name` 过滤：MongoDB/MySQL/PgBouncer/RocketMQ/ZooKeeper/Barman 等 |
| 系统日志 | `log_center_dist` | `service_name = 'messages'`（syslog）或 `prometheus-node-audit`（audit） |
| ClickHouse 自身：库/表是否存在、当前进程、近期 SQL | `system.tables` / `system.processes` / `system.query_log` | **默认可查**，不要当成不可访问。命令与拒绝边界见 [system-db.md](./system-db.md) |

## 数据同步/集成

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| 同步错误 | `sync_data_error_dist` | 同步失败明细 |
| 集成同步汇总 | `data_sync_log_dist` | 同步操作汇总；过滤 `_time_second_` |
| 互联同步 | `crm_syncfirststage_dist` | CRM互联一阶段同步 |
| 出站 HTTP | `egress_nginx_access_dist` | 出口 Nginx；无租户列，过滤 `host` + `_time_second_`；路径列 `request_url` |
| 入站 OpenAPI | `biz_log_openapi_dist` | `openApiUrl`/`cost`/`ei`/`ea`；过滤 `_time_second_`；无 `uri`/`method` |
| ERP 吞吐/分阶段耗时 | `biz_log_erpsyncdata_dist` | logger；过滤 `_time_second_` |
| iPaaS 2.0 结束态 | `biz_log_erp_ipaas_log_dist` | erp_sync；过滤 **`createTime`**；无 `_time_second_` |
| iPaaS probe | `biz_log_erp_ipaas_probe_log_dist` | erp_sync；过滤 **`createTime`**；无 `traceId` |
| ERP Sync 1.0 全链路 | `biz_log_erp_sync_log_dist` | erp_sync；过滤 **`createTime`** |
| ERP 通道监控 | `erp_sync_monitor_dist` | logger；过滤 `_time_second_` |

标准 SQL 见 [high-frequency-cheatsheet.md](./high-frequency-cheatsheet.md)「出站 HTTP 与集成取证」与 [erp-sync.md](./erp-sync.md)。

## 函数/APL 执行监控

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| 函数是否触发/执行成功 | `biz_log_function_dist` | 监控看板主表，含 errorCode、cost、waitingCost、totalCost |
| 函数入参和出参 | `biz_log_function_user_execute_dist` | 记录 parameters、returnValue、exception、durationTime |
| 函数内部调用了哪些 API | `biz_log_inner_function_api_dist` | 按 Fx.* API 聚合，含调用次数、耗时、请求/响应大小 |
| 函数代码日志输出/报错行号 | `biz_log_function_user_api_dist` | 记录 log.info/error 内容、lineNumber、logLevel |
| 异步队列排队延迟 | `biz_log_function_dist` | 看 waitingCost、queueId、queueType、messageId（需 queueId != 0） |
| 函数限流/超限 | `biz_log_function_dist` | 看 errorCode（OVER_LIMIT）、extra.rateLimit |

4 表关联键：`logId`（= `biz_log_function_user_execute_dist.id` = `biz_log_function_dist.id` = `biz_log_inner_function_api_dist.funcInstanceId` = `biz_log_function_user_api_dist.logId`）

详细字段定义和查询示例见 [biz-log-function.md](./biz-log-function.md)。

## 元数据/配置变更

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| 元数据变更 | `paas_metadata_changes_dist` | 对象定义变更oplog |
| 沙盒变更集 | `biz_log_sandbox_changeset_dist` | 沙盒环境变更记录 |

## 业务操作审计

| 场景 | 推荐表 | 说明 |
| --- | --- | --- |
| 对象批量操作 | `object_data_bulk_log_dist` | 批量导入/更新 |
| OpenAPI调用 | `biz_log_openapi_dist` | OpenAPI接口调用日志 |
| PaaS运维 | `paas_oplog_dist` | 运维操作日志 |
| 库存变更 | `stock_log_dist` | 库存操作日志 |
| AI 业务日志 | `biz_log_ai_dist` | Token/模型调用；**runtimeQueryable=false**（见 [ai-log.md](./ai-log.md)） |

---

## 相关文档

- ./index.md - 完整表定义索引
- ../clickhouse.md - 表-字段速查表
- ./system-db.md - `system` 库默认可查
