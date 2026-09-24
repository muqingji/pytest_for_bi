# ClickHouse 查询

`fx-ops idp query <biz> --sql "..."` 查询 ClickHouse 日志、审计、trace、慢查询和统计数据。查询前先读 [查询规则](../../idp-query-clickhouse.md)；只知道问题类型时先读 `clickhouse/diagnostic-scenarios.md` 选表，再按目标表读取单表文档。查 `system` 库（默认可查）读 [system-db.md](./clickhouse/system-db.md)。

## 总览

| biz | 命令 | 单表文档目录 |
| --- | --- | --- |
| `biz-app-log` | `query biz-app-log` | clickhouse/ |
| `crm-audit-log` | `query crm-audit-log` | [crm-audit-log.md](./clickhouse/crm-audit-log.md)（表级筛选） |
| `bi` | `query bi-clickhouse`；`table` 须 `--dialect clickhouse`（[总览](./bi.md)） | [bi.md](./clickhouse/bi.md) |
| `semantic-eval` | `query semantic-eval` | [semantic-eval.md](./clickhouse/semantic-eval.md) |
| `semantic-log` | `query semantic-log`（表可能为空） | [semantic-log.md](./clickhouse/semantic-log.md) |
| `semantic-system` | `query semantic-system`（表可能为空） | [semantic-system.md](./clickhouse/semantic-system.md) |

## biz-app-log

### 单表文档索引

| 文档 | 租户字段 | 时间字段 |
| --- | --- | --- |
| clickhouse/log-cep.md | `ei` | `stamp` |
| clickhouse/kpi-cep.md | `ea` | `stamp` |
| clickhouse/cep-agg.md | `ea`（部分表无） | `stamp` / `day` |
| clickhouse/agg-databases.md | — | —（agg_daily/agg_sla/agg_error 总览） |
| clickhouse/biz-log-bi-agg.md | `tenantId` | `day` |
| clickhouse/tomcat-access-daily.md | 无 | `_time_hour_` |
| clickhouse/fs-cep-slow-error.md | `tenantId` | `_time_second_` |
| clickhouse/nginx-log.md | `ei` | `_time_second_` |
| clickhouse/openapi-log.md | `ei` | `createTime` |
| clickhouse/tomcat-log.md | `ei` | `_time_second_` |
| clickhouse/tomcat-access-slow.md | `ei` | `_time_second_` |
| clickhouse/page-log.md | 无 | `stamp` |
| clickhouse/app-log.md | `ea` | `_time_second_` |
| clickhouse/service-log.md | 无 | `_time_second_` |
| clickhouse/rpc-log.md | 无 | `_time_second_` |
| clickhouse/log-error.md | `ei` | `_time_second_` |
| clickhouse/log-error-daily.md | 无 | `_time_second_`（日粒度） |
| clickhouse/slow-log.md | `ei` | `_time_second_` |
| clickhouse/eye-trace.md | `tenantId` | `_time_second_` |
| clickhouse/frontend-trace-log.md | `ei` | `_time_second_` |
| clickhouse/biz-audit.md | `tenantId` | `_time_second_` |
| clickhouse/paas-op-log.md | `ei` | `_time_second_` |
| clickhouse/data-auth-log.md | `tenantId` | `_time_second_` |
| clickhouse/object-bulk-log.md | `tenantId` | `_time_second_` |
| clickhouse/stock-log.md | `tenantId` | `_time_second_` |
| clickhouse/egress-log.md | `tenantId` | `_time_second_` |
| clickhouse/integration-log.md | `tenantId` | `createTime` |
| clickhouse/api-bus-log.md | `tenant_id` | `_time_second_` |
| clickhouse/db-limit-log.md | `tenantId` | `_time_second_` |
| clickhouse/k8s-event-log.md | 无 | `_time_second_` |
| clickhouse/k8s-app-scale-log.md | 无 | `_time_second_` |
| clickhouse/sentinel-block-log.md | 无 | `_time_second_` |
| clickhouse/biz-log-function.md | `tenantId` | `createTime` |
| clickhouse/flow-log.md | `tenantId` | `_time_second_` |
| clickhouse/hulian-log.md | `tenantId` | `createTime` |
| clickhouse/ai-log.md | `tenantId` | `createTime` |
| clickhouse/erp-sync.md | `tenantId` | `createTime` |
| clickhouse/biz-log-crmfeed.md | `ea` / `ei` | `_time_second_`、`createTime` |
| clickhouse/biz-log-feeds-lifecycle.md | `tenantId` | `_time_second_`、`createTime` |
| clickhouse/fast-notifier.md | `ei` | `_time_second_` |
| clickhouse/mq-dispatcher.md | `tenantId` | `_time_second_` |
| clickhouse/metadata-changes.md | `tenantId` | `_time_second_` |
| clickhouse/sql-slow.md | 无 | `_time_second_`、`stamp` |
| clickhouse/mongo-slow.md | `tenantId` | `_time_second_`、`stamp` |
| clickhouse/rpc-slow.md | 无 | `stamp`、`_time_second_` |
| clickhouse/nginx-access.md | `ei` | `_time_second_` |
| clickhouse/nginx-access-slow.md | `ei` | `_time_second_` |
| clickhouse/front-trace-http.md | `ei` | `_time_second_` |
| clickhouse/front-trace-other.md | `ei` | `_time_second_` |
| clickhouse/pg-error-log.md | 无 | `_time_second_` |
| clickhouse/flow-instance-log.md | `tenantId` | `createTime`、`start` |
| clickhouse/flow-execution-log.md | `tenantId` | `createTime` |
| clickhouse/flow-runtime-log.md | `tenantId` | `_time_second_`、`createTime` |
| clickhouse/rocketmq-log.md | 场景路由（非单表） | 消费→mq-dispatcher；文本→app_log |
| clickhouse/job-schedule-log.md | `tenantId` | `createTime` |
| clickhouse/xxl-job-log.md | 无 | `_time_second_`、`createTime` |
| clickhouse/sync-data-error.md | `tenantId` | `createTime`、`_time_second_` |
| clickhouse/modsecurity-audit.md | 无 | `_time_second_`、`collect_time` |
| clickhouse/security-event-tracking.md | `tenantId` | `_time_second_` |
| clickhouse/workflow-log.md | `tenantId` | `_time_second_`、`createTime` |
| clickhouse/workflow-v2-log.md | `tenantId` | `_time_second_`、`createTime` |
| clickhouse/mq-audit.md | `tenantId` | `_time_second_`、`createTime` |
| clickhouse/biz-sql-stat.md | `tenantId` | `_time_second_`、`createTime` |
| clickhouse/biz-log-pg-lock.md | 无 | `_time_second_`、`createTime` |
| clickhouse/elastic-search-log.md | 无 | `_time_second_` |
| clickhouse/fs-paas-auth.md | `tenantId` | `_time_second_` |
| clickhouse/paas-agent-execute.md | `tenantId` | `_time_second_`、`createTime` |
| clickhouse/biz-job-log.md | `tenantId` | `_time_second_`、`createTime` |
| clickhouse/schedule-task-log.md | `tenantId` | `_time_second_`、`createTime` |

## crm-audit-log

| 文档 | 租户字段 | 时间字段 |
| --- | --- | --- |
| clickhouse/crm-audit-log.md | `tenantId` | `operationTime` |

## bi

| 文档 | 租户字段 | 时间字段 |
| --- | --- | --- |
| clickhouse/bi.md | `tenant_id` | `timestamp` |

## 相关文档

- [index.md](./index.md)
- [idp-query-clickhouse.md](../../idp-query-clickhouse.md)
- [clickhouse/index.md](./clickhouse/index.md)
- [clickhouse/system-db.md](./clickhouse/system-db.md) — `system` 库默认可查、允许/拒绝边界与 `query_log`/`processes` 可见性
- [clickhouse/reqId-traceId-rpcId.md](./clickhouse/reqId-traceId-rpcId.md) — reqId/traceId/rpcId 三层标识与精准诊断策略
