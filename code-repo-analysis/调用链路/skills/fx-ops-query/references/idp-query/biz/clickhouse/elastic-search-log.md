# elastic-search-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: ElasticSearch集群日志表，记录ES集群的慢查询日志和节点运行日志

**租户ID字段**: 无

**时间字段**: _time_second_

---

## 表：elastic_search_log_dist

**说明**: ElasticSearch集群日志表，记录ES集群的慢查询日志和节点运行日志

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'elastic_search_log_local', rand()) |
| PARTITION BY | `(toYYYYMM(_time_second_), toDayOfWeek(_time_second_))` |
| PRIMARY KEY | `_time_second_` |
| ORDER BY | `_time_second_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(180)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 事件写入ClickHouse的秒级时间戳 |
| `time` | Decimal(18, 3) | 日志产生时间 |
| `type` | LowCardinality(String) | 日志类型 |
| `timestamp` | Nullable(String) | 时间戳 |
| `level` | LowCardinality(String) | 日志级别 |
| `component` | Nullable(String) | 组件名称 |
| `cluster.name` | Nullable(String) | ES集群名称 |
| `node.name` | Nullable(String) | ES节点名称 |
| `message` | Nullable(String) | 日志消息 |
| `cluster.uuid` | Nullable(String) | 集群UUID |
| `node.id` | LowCardinality(String) | 节点ID |
| `source` | String |  |
| `total_shards` | String |  |
| `search_type` | String |  |
| `stats` | String |  |
| `types` | String |  |
| `total_hits` | String |  |
| `took_millis` | String |  |
| `took` | String |  |
| `log` | String |  |
| `hostname` | String | 主机名 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查询ES慢查询日志
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, `cluster.name`, `node.name`, source, took_millis, total_hits, total_shards FROM elastic_search_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND took_millis > 1000 ORDER BY took_millis DESC LIMIT 20"

# 统计各节点日志级别分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT `node.name`, level, component, COUNT(*) as cnt FROM elastic_search_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY `node.name`, level, component ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
