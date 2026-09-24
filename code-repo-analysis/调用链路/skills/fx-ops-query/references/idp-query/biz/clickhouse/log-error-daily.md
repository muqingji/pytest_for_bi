# log-error-daily

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 应用错误日志按天聚合统计表，按应用、集群、环境维度汇总每天的 ERROR 级别日志条数，用于错误趋势监控与告警。为跨租户聚合表，不含租户/用户维度；错误明细见 log_error_dist。

**租户ID字段**: 无

**时间字段**: _time_second_

---

## 表：log_error_daily_dist

**说明**: 应用错误日志按天聚合统计表，按应用、集群、环境维度汇总每天的 ERROR 级别日志条数，用于错误趋势监控与告警。为跨租户聚合表，不含租户/用户维度；错误明细见 log_error_dist。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_error', 'log_error_daily_local', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(_time_second_, cluster, profile, app)` |
| ORDER BY | `(_time_second_, cluster, profile, app)` |
| TTL | `_time_second_ + toIntervalDay(740)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime('Asia/Shanghai') | 聚合时间桶（按天对齐，取当天 00:00:00） |
| `app` | LowCardinality(String) | 应用名称 |
| `cluster` | LowCardinality(String) | K8s 集群 |
| `errorCount` | Int64 | 该时间桶（当天）内的 ERROR 级别日志条数 |
| `profile` | LowCardinality(String) | 环境标识 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 近 14 天全局错误量
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT toDate(_time_second_) AS d, sum(errorCount) AS errors FROM log_error_daily_dist WHERE _time_second_ >= today() - 14 GROUP BY d ORDER BY d DESC"

# 某日错误应用 Top
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT app, cluster, profile, sum(errorCount) AS errors FROM log_error_daily_dist WHERE _time_second_ >= today() - 1 AND _time_second_ < today() GROUP BY app, cluster, profile ORDER BY errors DESC LIMIT 20"
```

> 禁止 `SELECT day ...`（列不存在）。需要明细堆栈时改查 `log_error_dist` 并收窄时间窗与 `app`。

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
