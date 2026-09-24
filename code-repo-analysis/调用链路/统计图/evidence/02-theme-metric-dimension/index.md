# Evidence Index

## Context

- evidence_dir: `/Users/muqingji/code/study/pytest_for_bi/code-repo-analysis/调用链路/统计图/evidence/02-theme-metric-dimension`
- phase: Phase0-3
- last_updated: 2026-09-22T16:01:14+00:00
- collect_manifest_ref: `CTX-collect-manifest.json`
- playbook: trace-anchor-v1@v1
- through_phase: 3
- profile: foneshare

## Reusable Evidence

| 路径 | 说明 | 覆盖范围 | 建议消费方 |
| --- | --- | --- | --- |
| `DIA-incident-facts.json` | 诊断事实合同：确定性 observations、evidence_gaps、quality 与 evidence snapshot | Phase0-3 | fx-ops / tracing / domain |
| `evidence/CTX-app-discovery.json` | Phase2 应用发现：从 CEP、Tomcat、上下文等证据归并 app 候选和来源 | Phase0-3; task=app_discovery; ok; rows=2 | fx-ops / tracing |
| `evidence/KNO-service-owner.json` | 负责人、团队归属、历史知识或变更知识 | Phase0-3; task=lookup_context; ok; rows=3 | fx-ops / knowledge / domain |
| `evidence/ONC-service-oncalls.json` | 值班、告警或 oncall 相关上下文 | Phase0-3; task=lookup_context; ok; rows=3 | fx-ops / knowledge / domain |
| `evidence/QRY-log-cep-impact.json` | 增量查询结果，可被 query/tracing/domain skill 复用 | Phase0-3; task=cep_impact_aggregate; ok; rows=16 | query / domain |
| `evidence/QRY-log-cep-raw.json` | 增量查询结果，可被 query/tracing/domain skill 复用 | Phase0-3; task=cep_impact_aggregate; ok; rows=16 | query / domain |
| `evidence/QRY-log-cep-summary.json` | 增量查询结果，可被 query/tracing/domain skill 复用 | Phase0-3; task=cep_impact_aggregate; ok; rows=16 | query / domain |
| `evidence/TEN-tenant-cloud.json` | 租户、企业、云环境或账号上下文 | Phase0-3; task=lookup_context; ok; rows=3 | fx-ops / knowledge / domain |
| `evidence/TRC-app-log-analysis.json` | Phase3 app_log StopWatch 分析：应用侧耗时片段、过滤条件、空结果语义和查询指纹 | Phase0-3; task=app_log_stopwatch; empty; rows=0; no_app_log_stopwatch_rows | fx-ops / tracing / domain |
| `evidence/TRC-log-error-summary.json` | 后端 error 日志、异常堆栈、错误 token 与同窗报错事实 | Phase0-3; task=error_stack; empty; rows=0; no_log_error_for_trace | tracing / query / domain |
| `evidence/TRC-log-error.full.json` | 后端 error 日志、异常堆栈、错误 token 与同窗报错事实 | Phase0-3; task=error_stack; empty; rows=0; no_log_error_for_trace | tracing / query / domain |
| `evidence/TRC-log-error.json` | 后端 error 日志、异常堆栈、错误 token 与同窗报错事实 | Phase0-3; task=error_stack; empty; rows=0; no_log_error_for_trace | tracing / query / domain |
| `evidence/TRC-mongo-slow.json` | Mongo 慢查询命中或空结果 | Phase0-3; task=mongo_slow; empty; rows=0; no_mongo_slow_correlated | tracing / query / domain |
| `evidence/TRC-service-dist-pivot.json` | 采集任务 service_dist_pivot 的证据，解析说明见 evidence-parse/TRC-service-dist-pivot.md | Phase0-3; task=service_dist_pivot; empty; rows=0; no_service_dist_rows | tracing / query / domain |
| `evidence/TRC-slow-log.json` | SQL 慢查询命中或空结果 | Phase0-3; task=sql_slow; ok; rows=1 | tracing / query / domain |
| `evidence/TRC-tomcat-access-slow.json` | Tomcat access 慢请求分布 | Phase0-3; task=tomcat_access_slow; empty; rows=0; no_tomcat_access_slow | tracing / query / domain |
| `evidence/TRC-tracing-log-cep.json` | CEP 用户侧请求现场、status、uri、request_time 与 trace 锚点 | Phase0-3; task=cep_anchor; ok; rows=16 | tracing / query / domain |

## Operational Artifacts / Dispatch Audit

| 路径 | 说明 | 覆盖范围 | 建议消费方 |
| --- | --- | --- | --- |
| _none_ | 未发现 HND-* 交接合同 | 当前目录无调度审计交接文件 | fx-ops |

## Gaps / Need Incremental Evidence

- `error_stack` 空结果：no_log_error_for_trace。
- `cep_slow_body` 已跳过：signal_gate_cep_not_slow。
- `tomcat_access_slow` 空结果：no_tomcat_access_slow。
- `mongo_slow` 空结果：no_mongo_slow_correlated。
- `app_log_stopwatch` 空结果：no_app_log_stopwatch_rows。
- `service_dist_pivot` 空结果：no_service_dist_rows。

## Reuse Contract

- 子 skill 先读本索引，再按任务打开相关证据文件。
- `CTX-collect-manifest.json` 是根目录控制面文件，用于任务终态、空结果语义和门禁校验；它不是报告可见业务证据。
- 索引中同 env/time_window/source/query 语义已覆盖的证据直接复用，不做 TTL 或过期判断。
- 需要补查时只做增量查询，并在 `reuse_decision.reason` 说明缺字段、窗口不覆盖、证据冲突或门禁要求。
- 新增证据文件后立即刷新本索引，再派发下一跳。
