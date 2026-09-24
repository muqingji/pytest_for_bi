# biz-log-bi-agg

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 业务 BI 报表 PV 聚合分布式表，按租户、应用、日期、视图维度聚合 PV（页面浏览量）统计指标。

**租户ID字段**: `tenantId`

**时间字段**: day

---

## 表：biz_log_bi_agg_dist

**说明**: 业务 BI 报表 PV 聚合分布式表，按租户、应用、日期、视图维度聚合 PV（页面浏览量）统计指标。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_sla', 'biz_log_bi_agg_local', rand()) |
| PARTITION BY | — |
| PRIMARY KEY | `tenantId, appName, day, viewId` |
| ORDER BY | `tenantId, appName, day, viewId` |
| TTL | `day + toIntervalDay(740)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `day` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `appName` | String | 应用名称 |
| `day` | Date | 统计日期 |
| `tenantId` | String | 租户/企业 ID |
| `viewId` | String | 视图 ID |
| `viewPV` | Int64 | 视图 PV（页面浏览量） |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 时间 | `day` |

### 查询示例

```bash
# 租户近 7 天视图 PV
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT day, appName, viewId, viewPV FROM biz_log_bi_agg_dist WHERE tenantId = '<TENANT_ID>' AND day >= today() - 7 ORDER BY day DESC, viewPV DESC LIMIT 50"

# 按视图汇总 PV
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT viewId, sum(viewPV) AS pv FROM biz_log_bi_agg_dist WHERE tenantId = '<TENANT_ID>' AND day >= today() - 30 GROUP BY viewId ORDER BY pv DESC LIMIT 20"
```

> BI 报表定义/数仓指标请走 `bi` biz（见 [bi.md](./bi.md)），不要与本表混淆。

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
