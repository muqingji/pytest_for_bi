# table-alias-map（错误/过时表名 → 真实表）

> verified_at: 2026-08-01 | platform: v5.10.0
> **用途**: 文档或历史 playbook 出现左列名称时，改用右列；禁止再写入左列作为查询目标。

## 文档假名 / 错名（三环境均不存在或不可当目标）

| 错误/过时名 | 正确表名 | 说明 |
| --- | --- | --- |
| `rocketmq_client_log_dist` | `rocketmq_client_log_dist`（platform 已登记）或 `app_log_dist` + `biz_log_dispatch_dist` | v5.10.0 tables.yaml 已收录；消费主链路仍见 mq-dispatcher.md |
| `biz_log_flow_dist` | `biz_flow_runtime_log_dist` / `fs_flow_instance_log_dist` 等 | 无此总表 |
| `hulian_log_dist` | `crm_syncfirststage_dist` + `crm_syncsecondstage_dist` | 库名 hulian_log，表已拆分 |
| `integration_log_dist` | `data_sync_log_dist` | 失败补 `sync_data_error_dist` |
| `egress_log_dist` | `egress_nginx_access_dist`；短信 `egress_sms_dist_tbl` | 无总包名 |
| `tomcat_log_dist` / `tomcat_access_log_dist` | `tomcat_access_dist` | 访问日志真名 |
| `rpc_log_dist` | `rpc_dist` | |
| `sentinel_block_log_dist` | `sentinel_block_dist` | |
| `log_sql_slow_dist` | `sql_slow_dist`（或 `slow_log_dist` 按字段） | |
| `mq_dispatcher_dist` | `biz_log_dispatch_dist` | 禁止猜测未验证表名 |
| `ai_usage_detail_log_dist` / `biz_log_ai_dist` | **不可查询** | v5.10.0 已从 tables.yaml 移除并列入 scan exclude；见 ai-log.md / known-gaps.md |

## variant-selection 废弃/替换（platform v4.37.0）

| 错误/过时名 | 正确表名 | 说明 |
| --- | --- | --- |
| `function_execute_stage_log_mv2_dist` | `function_execute_stage_log_mv_dist` | variant `function_execute_stage_log` (replace) |
| `client_upload_log` | `client_upload_log_dist` | variant `client_upload_log` (replace) |
| `biz_log_workflow_dist` | `biz_log_workflow_v2_dist` | variant `biz_log_workflow` (replace) |
| `i18n_access_miss_dist` | `i18n_access_miss` | variant `i18n_access_miss` (replace) |
| `paas_agent_detail_log_v` | `paas_agent_detail_log_dist` | variant `paas_agent_detail_log` (replace) |
| `kwq_upload_log_view` | `kwq_upload_log_dist` | variant `kwq_upload_log` (replace) |
| `network_log` | `network_log_dist` | variant `network_log` (replace) |
| `app_log_rb_local_view_v3` | `app_log_rb_local_view_v2` | variant `app_log_rb_local_view` (duplicate_suspect) |
| `app_log_dist_new` | `app_log_dist` | variant `app_log` (parallel) |
| `app_log_dist_old` | `app_log_dist` | variant `app_log` (parallel) |
| `nginx_log` | **不可查询** | variant `nginx_log` (all_inactive) |
| `nginx_log_dist` | **不可查询** | variant `nginx_log` (all_inactive) |
| `pg_error_log` | **不可查询** | variant `pg_error_log` (all_inactive) |
| `pg_error_log_dist` | **不可查询** | variant `pg_error_log` (all_inactive) |
| `modsecurity_audit_log` | **不可查询** | variant `modsecurity_audit_log` (all_inactive) |
| `modsecurity_audit_log_dist` | **不可查询** | variant `modsecurity_audit_log` (all_inactive) |
| `paas_agent_toxicity_dist` | **不可查询** | variant `paas_agent_toxicity` (all_inactive) |
| `paas_agent_toxicity_v` | **不可查询** | variant `paas_agent_toxicity` (all_inactive) |

## Profile 条件（名称对，但非全环境可查）

| 表名 | foneshare | ale/mengniu | 公有云 fallback |
| --- | --- | --- | --- |
| `xxl_job_schedule_log_dist` | **无** | 有 | `schedule_task_event_log_dist` / `job_schedule_event_log_dist` |
| `pg_error_log` | 有 | 有 | — |
| `pg_error_log_dist` | **无** | 有 | 用 `pg_error_log` |
| `rpc_daily_dist` / `service_daily_dist` | **404**（known-gaps） | 视环境 | 短窗 `rpc_dist` / `service_dist`，禁止跨天硬扛 |

## 相关

- [known-gaps.md](./known-gaps.md) — 聚合表运行时缺口  
- [index.md](./index.md) — 单表/场景文档索引  
- [rocketmq-log.md](./rocketmq-log.md) / [mq-dispatcher.md](./mq-dispatcher.md)
