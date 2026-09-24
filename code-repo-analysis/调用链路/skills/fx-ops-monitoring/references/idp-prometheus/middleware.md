> 中间件部署在虚拟机上，非 K8s 环境，不使用 `k8s_cluster` / `namespace` 筛选。如需限定实例，用 `instance` 或 `host` label。

## 中间件 Exporter 发现

执行以下查询确认环境中是否部署了对应 exporter（已验证 job 名称）：

```bash
# 检查是否有 PostgreSQL exporter（job 名 pg-exporter）
fx-ops idp --profile <profile> prometheus query --promql 'count(up{job=~"pg.*"})' -j

# 检查是否有 MongoDB exporter（job 名 mongodb-exporter / mongo-exporter）
fx-ops idp --profile <profile> prometheus query --promql 'count(up{job=~"mongo.*"})' -j

# 检查是否有 Redis exporter（job 名 redis-exporter）
fx-ops idp --profile <profile> prometheus query --promql 'count(up{job=~"redis.*"})' -j

# 检查是否有 Elasticsearch exporter（job 名 es-exporter）
fx-ops idp --profile <profile> prometheus query --promql 'count(up{job=~"es.*"})' -j

# 检查是否有 ClickHouse exporter（job 名 clickhouse-exporter）
fx-ops idp --profile <profile> prometheus query --promql 'count(up{job=~"clickhouse.*"})' -j
```

如果返回 0，说明该中间件未部署 exporter，相关 PromQL 查询将无数据。

# Prometheus Middleware Monitoring

针对常用存储和中间件的健康度监控，主要关注：连接数、吞吐量（IOPS/QPS）及延迟/慢查询。

## 场景映射

| 中间件 | 核心指标类别 | 实际 job 名称 |
| --- | --- | --- |
| **PostgreSQL** | 连接池、事务量、慢查询 | `pg-exporter` |
| **MongoDB** | 活动连接、读写吞吐、锁等待 | `mongodb-exporter` / `mongo-exporter` |
| **Redis** | 客户端连接、命令吞吐、内存压力 | `redis-exporter` |
| **Elasticsearch** | 索引吞吐、搜索延迟、集群健康 | `es-exporter` |
| **ClickHouse** | 查询数、合并压力、线程池 | `clickhouse-exporter` |

## 常用 PromQL 示例

按需使用 `instance` 或 `host` 过滤特定实例，不传则返回所有实例。

### 1. PostgreSQL
- **活跃连接数**：`sum(pg_stat_activity_count{state="active", job="pg-exporter"}) by (instance)`
- **事务吞吐量 (TPS)**：`sum(rate(pg_stat_database_xact_commit{job="pg-exporter"}[5m]) + rate(pg_stat_database_xact_rollback{job="pg-exporter"}[5m])) by (instance)`
- **慢查询堆积**：`max(pg_stat_activity_max_tx_duration{datname="xxx", job="pg-exporter"})`
- **从 DB 名称反查虚拟机节点 IP**：使用 `pg_stat_database_active_time` 指标，传入具体的数据库名 `datname`。
 ```bash
 fx-ops idp --profile <profile> prometheus query --promql \
  'pg_stat_database_active_time{datname="${db_name}"}' -j
 ```
 执行该查询后，返回结果中的 `host`（或 `instance`）标签即为该数据库实例所在的**虚拟机节点 IP**。获得该 IP 后，可将其作为 `host_ip` 替换并传入 host-node.md 中的 PromQL 模板，以查询该虚拟机的 CPU、负载、内存、磁盘 IO 等指标。

### 2. MongoDB
- **当前连接数**：`mongodb_connections{state="current", job="mongodb-exporter"}`
- **每秒操作数**：`sum(rate(mongodb_op_counters_total{job="mongodb-exporter"}[5m])) by (instance)`
- **读写延迟**：`sum(rate(mongodb_mongod_op_latencies_latency_total{job="mongodb-exporter"}[5m])) by (instance,type)`（注意：指标名为 `mongodb_mongod_op_latencies_latency_total`，非 `mongodb_op_latencies_latency_total`；`type` 标签区分读写）

### 3. Redis
- **连接数**：`redis_connected_clients{job="redis-exporter"}`
- **每秒处理命令数**：`sum(rate(redis_commands_processed_total{job="redis-exporter"}[5m])) by (instance)`
- **命中率**：`sum(redis_keyspace_hits_total{job="redis-exporter"}) / (sum(redis_keyspace_hits_total{job="redis-exporter"}) + sum(redis_keyspace_misses_total{job="redis-exporter"}))`

### 4. Elasticsearch
- **索引写入速率**：`sum(rate(elasticsearch_indices_indexing_index_total{job="es-exporter"}[5m])) by (instance)`
- **搜索请求速率**：`sum(rate(elasticsearch_indices_search_query_total{job="es-exporter"}[5m])) by (instance)`
- **集群状态**：`elasticsearch_cluster_health_status{color="red"}==1 or (elasticsearch_cluster_health_status{color="green"}==1)+4 or (elasticsearch_cluster_health_status{color="yellow"}==1)+22`（color=red 时值为 1，green 时为 5，yellow 时为 23）
- **节点 Load**：`elasticsearch_os_load1{job="es-exporter"}`

### 5. ClickHouse
- **活动查询数**：`ClickHouseMetrics_Query{job="clickhouse-exporter"}`
- **合并压力**：`ClickHouseMetrics_Merge{job="clickhouse-exporter"}`
- **TCP 连接数**：`ClickHouseMetrics_TCPConnection{job="clickhouse-exporter"}`
- **后台合并线程活跃数**：`ClickHouseMetrics_BackgroundMergesAndMutationsPoolTask{job="clickhouse-exporter"}`

> **注意**：ClickHouse 指标前缀为 `ClickHouseMetrics_`（PascalCase），非 `clickhouse_metrics_`（snake_case）。环境中未采集 histogram bucket 指标，无法使用 `histogram_quantile` 计算延迟分位数，建议通过 ClickHouse system.query_log 表查询延迟分布。

## 诊断思路
1. **连接数爆满**：观察 `_connections` 指标是否达到配置上限，对比应用侧连接池泄露或并发陡增。
2. **IOPS/TPS 异常**：对比 `rate(...)` 的波形，判断是业务量激增还是底层磁盘/网络抖动。
3. **慢查询相关性**：当应用侧 `traceId` 报错超时，立即联动 Prometheus 检查对应时间段存储层是否有长事务或高延迟指标。
