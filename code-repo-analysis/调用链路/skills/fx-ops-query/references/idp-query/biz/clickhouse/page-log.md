# page-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 页面访问统计汇总表，按 URI 维度聚合 PV、耗时、状态码分布等指标

**时间字段**: _time_second_, stamp

---

## 表：page_dist

**说明**: 页面访问统计汇总表，按 URI 维度聚合 PV、耗时、状态码分布等指标

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'page', rand(); Distributed('cluster01', 'logger', 'page', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime | 日志采集时间（秒级） |
| `app` | Nullable(String) | 应用名称 |
| `app2` | String |  |
| `avgCost` | Nullable(Int32) | 平均耗时(ms) |
| `failPv` | Nullable(Int32) | 失败PV |
| `hostname` | Nullable(String) | 主机名 |
| `pv20x` | Nullable(Int32) | 2xx状态码PV |
| `pv30x` | Nullable(Int32) | 3xx状态码PV |
| `pv40x` | Nullable(Int32) | 4xx状态码PV |
| `pv50x` | Nullable(Int32) | 5xx状态码PV |
| `serverIp` | Nullable(String) | 服务器IP |
| `slowPv` | Nullable(Int32) | 慢请求PV |
| `spiderPv` | Nullable(Int32) | 爬虫PV |
| `stamp` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 统计时间戳 |
| `totalCost` | Nullable(Int64) | 总耗时(ms) |
| `totalPv` | Nullable(Int32) | 总PV |
| `upstreamIp` | String |  |
| `uri` | Nullable(String) | 请求URI |
| `uri2` | Nullable(String) | 对 URI 做聚合和规范化处理后的路径；进行统计分析或筛选过滤时优先使用 uri2 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_`, `stamp` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM page_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
