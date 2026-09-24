# known-gaps（biz-app-log 运行时缺口）

> **v5.10.0 update**: `biz_log_ai_dist`、`nginx_access_slow_dist`、`rpc_slow`/`rpc_slow_dist` 等见 `scan.yml` exclude_names；AI 表已从 tables.yaml 移除。
> **verified_at**: 2026-08-01 | platform: v5.10.0
> **profile**: 默认 `foneshare`
> **来源**: `show tables/columns/query` 实测
> **错名映射**（文档写了不存在的表名）：见 **[table-alias-map.md](./table-alias-map.md)**，勿与本页「表存在但 404/空」混淆。

**用途**: 在写长周期 SQL 前先读本页。配置仓库有表 ≠ 当前 profile 可查。缺口时结论必须标 **`platform_gap`**，禁止改扫明细表「赌」跨天聚合。

## 缺口与策略

| 表 | 状态 | 临时策略 | 结论口径 |
| --- | --- | --- | --- |
| `rpc_daily_dist` | **404** Table not found | 仅短窗（数小时内）用 `rpc_dist`（`_time_second_` + `module`） | `platform_gap` + table + fallback=短窗 rpc_dist 或 none |
| `service_daily_dist` | **404** | 仅短窗 `service_dist`（6h 汇总也可能超时） | 同上 |
| `tomcat_access_daily_dist` | 可 query，**count=0** 空表 | 短窗 `tomcat_access_dist` | `platform_gap` + 空表 |
| `log_error_daily_dist` | **可用**（`dbName=agg_error`） | 天级错误量优先本表；时间列 **`_time_second_`**（无 `day`） | 正常路径 |
| `page_daily_*` | **不存在** | 无官方长周期 page 路径；`page_dist` 仅短窗 | 长周期 page → 声明不可用 |
| `cep_daily_dist` / `cep_ea_daily_dist` / `cep_minute_dist` / `kpi_cep` | **可用** | 长周期 CEP / 故障窗 5min / KPI 样本首选 | 正常路径 |
| `cep_daily_ea_uid_dist` | **可用** | PV/UV 须 `countMerge` / `uniqMerge` | 正常路径 |
| `biz_log_bi_agg_dist` | **可用** | 报表视图 PV | 正常路径 |
| `xxl_job_schedule_log_dist` | foneshare **无**；ale/mn 有 | 用 `schedule_task_event_log_dist` | `platform_gap` + fallback=schedule_task_event_log_dist |
| `pg_error_log` / `pg_error_log_dist` | **scan 排除**（platform all_inactive） | 勿查；PostgreSQL 错误改查 `log_error_dist` 短窗 + app | `platform_gap` + fallback=log_error_dist 或 none |
| `biz_log_ai_dist` | **scan exclude + 已从 tables.yaml 移除** | 不可查询；旧名 `ai_usage_detail_log_dist` 同样不存在 | `platform_gap` + table=biz_log_ai_dist |
| `biz_log_crmfeed_dist` | foneshare/ale **404** Table not found（tenant-filters 有 YAML） | 先 `show tables/columns` 确认 profile 是否暴露；字段见 [biz-log-crmfeed.md](./biz-log-crmfeed.md) | `platform_gap` + table=biz_log_crmfeed_dist |
| `biz_log_feeds_lifecycle_dist` | foneshare/ale **404** Table not found（tenant-filters 有 YAML；截图反查 feedId 首选表） | 先 `show tables/columns`；可用时见 [biz-log-feeds-lifecycle.md](./biz-log-feeds-lifecycle.md) | `platform_gap` + table=biz_log_feeds_lifecycle_dist |
| `biz_log_openapi_dist` / `biz_log_erpsyncdata_dist` / `biz_log_erp_ipaas_log_dist` / `biz_log_erp_ipaas_probe_log_dist` | foneshare/firstshare **`show columns` 404**；`system.columns` 与 `query` **可用**（2026-08-21） | 按 [openapi-log.md](./openapi-log.md) / [erp-sync.md](./erp-sync.md) 写 SQL，不要标 platform_gap | catalog 缺口，表可查 |

## platform_gap 输出要求

当 `show columns` / `query` 返回 table not found、或确认空表且无替代 daily 时，结论至少包含：

- `status=platform_gap`（或中文「平台缺口」）
- `table=<表名>`
- `profile=<profile>`
- `fallback=<短窗表名或 none>`

**禁止**写成「系统无 RPC 数据 / 无错误」等业务结论（除非短窗明细也证明无数据）。

## 长周期强制映射（摘要）

| 意图 | 表 | 勿用 |
| --- | --- | --- |
| CEP 天/周失败与容量 | `cep_daily_dist` / `cep_ea_daily_dist` | `log_cep_dist` 跨天 GROUP BY |
| CEP 故障窗 5min | `cep_minute_dist` / `cep_ea_dist` | — |
| 应用错误天趋势 | `log_error_daily_dist` | `log_error_dist` 跨天全扫 |
| RPC / Service 天趋势 | daily 表（若 404 → platform_gap） | 明细跨天硬扛 |
| Page 天趋势 | 无 | `page_dist` ≥24h 聚合 |

库与单表字段见 [agg-databases.md](./agg-databases.md) 及各单表文档。

## 复测命令（修复后验收）

```bash
fx-ops idp --profile foneshare show columns biz-app-log rpc_daily_dist -j
fx-ops idp --profile foneshare show columns biz-app-log service_daily_dist -j
fx-ops idp --profile foneshare query biz-app-log --sql "SELECT count() FROM tomcat_access_daily_dist" -j
fx-ops idp --profile foneshare query biz-app-log --sql "SELECT toDate(_time_second_) d, sum(errorCount) e FROM log_error_daily_dist WHERE _time_second_ >= today()-3 GROUP BY d" -j
```

---

## 相关文档

- [agg-databases.md](./agg-databases.md)
- [cep-agg.md](./cep-agg.md) / [log-error-daily.md](./log-error-daily.md) / [rpc-log.md](./rpc-log.md) / [service-log.md](./service-log.md)
