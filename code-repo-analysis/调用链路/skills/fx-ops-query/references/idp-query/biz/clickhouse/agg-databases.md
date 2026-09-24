# agg-databases（agg_daily / agg_sla / agg_error）

> schema_verified_at: 2026-07-25 | platform: v4.37.3
> 变更摘要：`biz-app-log` 集群新增 3 个 ClickHouse 库（log_center 端点组）：`agg_daily`、`agg_sla`、`agg_error`。

**说明**: 聚合库通过 **同一 biz 参数 `biz-app-log`** 查询，SQL 中只写分布式表名，**不要**写库名前缀（如禁止 `FROM agg_sla.kpi_cep` 作为 idp 表名写法；与其它 dist 表一致：`FROM kpi_cep`）。

## 库一览

| 库 | 暴露表 | 用途 |
| --- | --- | --- |
| `agg_daily` | `rpc_daily_dist`、`service_daily_dist`（配置已登记） | RPC / 服务调用 **按天** 聚合（长周期容量与失败） |
| `agg_sla` | `kpi_cep`、`cep_*`、`tomcat_access_daily_dist`、`biz_log_bi_agg_dist` 等 8 张 | CEP SLA/KPI、Tomcat 小时聚合、BI 报表 PV |
| `agg_error` | 运行时已见 `log_error_daily_dist` | 应用错误 **按天** 聚合；明细仍用 `log_error_dist` |

> **运行时缺口与 fallback**（foneshare 实测、含 platform_gap 口径）统一见 **[known-gaps.md](./known-gaps.md)**，勿在此页重复维护状态。

## 查询入口

```bash
fx-ops idp --profile <profile> show tables biz-app-log --dialect clickhouse -j
fx-ops idp --profile <profile> show columns biz-app-log <table> --dialect clickhouse -j
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT ... FROM <table> WHERE ..."
```

## 表 → 文档

| 库 | 表名 | 单表文档 |
| --- | --- | --- |
| `agg_sla` | `kpi_cep` | [kpi-cep.md](./kpi-cep.md) |
| `agg_sla` | `cep_minute_dist` / `cep_ea_dist` / `cep_daily_dist` / `cep_ea_daily_dist` / `cep_daily_ea_uid_dist` | [cep-agg.md](./cep-agg.md) |
| `agg_sla` | `tomcat_access_daily_dist` | [tomcat-access-daily.md](./tomcat-access-daily.md) |
| `agg_sla` | `biz_log_bi_agg_dist` | [biz-log-bi-agg.md](./biz-log-bi-agg.md) |
| `agg_daily` | `rpc_daily_dist` | [rpc-log.md](./rpc-log.md)（含按天表；**foneshare 可能 404**） |
| `agg_daily` | `service_daily_dist` | [service-log.md](./service-log.md)（含按天表；**foneshare 可能 404**） |
| `agg_error` | `log_error_daily_dist` | [log-error-daily.md](./log-error-daily.md) |

## 选用原则

| 需求 | 优先 |
| --- | --- |
| 单次请求 / traceId / reqId | 明细表：`log_cep_dist`、`log_error_dist`、`tomcat_access_dist`、`rpc_dist`… |
| 故障窗口 5 分钟级趋势 | `cep_minute_dist` / `cep_ea_dist` |
| 天级 CEP SLA / 容量 / 失败率 | **`cep_daily_dist` / `cep_ea_daily_dist`**（已验证适合 7–14 天+） |
| 天级应用错误量 | **`log_error_daily_dist`**（时间列 `_time_second_`，无 `day`） |
| 天级 RPC / Service | **`rpc_daily_dist` / `service_daily_dist`**（目标路径；未就绪时勿对明细表做 7 天全量 GROUP BY，易 30s 超时） |
| 页面 PV 长周期 | 暂无 `page_daily_*`；`page_dist` 仅短窗，7 天聚合易超时 |
| CEP 异常 KPI 样本 | `kpi_cep`（与全量 `log_cep_dist` 区分） |
| 企业 PV/UV | `cep_daily_ea_uid_dist`（`countMerge` / `uniqMerge`） |

### 长周期统计（CEP / RPC / Service / Page / Error）

| 域 | 应用 daily/聚合表 | 勿用（大窗） |
| --- | --- | --- |
| CEP | `cep_daily_*`、`cep_minute_dist` | 对 `log_cep_dist` 做跨天全表聚合 |
| Error | `log_error_daily_dist` | 对 `log_error_dist` 做跨天 count 全扫 |
| RPC | `rpc_daily_dist` | `rpc_dist` 跨天硬聚合 |
| Service | `service_daily_dist` | `service_dist` 跨天硬聚合 |
| Page | 暂无 daily；短窗 `page_dist` | `page_dist` 跨 7 天汇总 |

## 平台侧变更对照（fs-developer-platform）

- `server/tenant-filters/clickhouse/connections.yml`：`biz-app-log.databases` 增加 `agg_daily, agg_sla, agg_error`
- `clickhouse-endpoint-groups.ts`：`log_center` 组映射增加上述三库
- `biz-list.json` / 各表 YAML / `tables.yaml`：登记可查询 Distributed 表（`runtimeQueryable: true`）
- `agg_error` 仅有 MV → **未**写入可查询表清单

---

## 相关文档

- [known-gaps.md](./known-gaps.md) — foneshare 运行时缺口与 platform_gap
- [biz-app-log.md](./biz-app-log.md) — 集群总览与常用表速查
- [diagnostic-scenarios.md](./diagnostic-scenarios.md) — 按场景选表
- [index.md](./index.md) — 单表文档索引
