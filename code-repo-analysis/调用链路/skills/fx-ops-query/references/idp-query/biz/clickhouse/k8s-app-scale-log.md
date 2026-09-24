# k8s-app-scale-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: K8s 应用扩缩容指标，记录容器资源的 CPU/内存使用率及请求/限制值

**时间字段**: _time_second_

---

## 表：fs_k8s_app_scaler_metrics_dist

**说明**: K8s 应用扩缩容指标，记录容器资源的 CPU/内存使用率及请求/限制值

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'fs_k8s_app_scaler_metrics_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(app, namespace, _time_second_)` |
| ORDER BY | `(app, namespace, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(5)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 记录时间 |
| `app` | String | 应用名 |
| `cluster` | String | K8s 集群 |
| `cpuPercentage` | Int16 | CPU 使用百分比 |
| `cpuUsage` | Int32 | CPU 使用量（m） |
| `level` | String | 级别 |
| `limitCPU` | Int32 | CPU 限制值 |
| `limitMem` | Int32 | 内存限制值 |
| `logger` | String | 日志记录器 |
| `memPercentage` | Int16 | 内存使用百分比 |
| `memUsage` | Int32 | 内存使用量（Mi） |
| `message` | String | 消息 |
| `namespace` | String | 命名空间 |
| `podMetrics` | String | Pod 级指标（JSON） |
| `requestCPU` | Int32 | CPU 请求值 |
| `requestMem` | Int32 | 内存请求值 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查某应用过去1小时的资源使用
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, app, namespace, cpuPercentage, memPercentage FROM fs_k8s_app_scaler_metrics_dist WHERE app = 'fs-paas-function-service-runtime-provider' AND _time_second_ > now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20"

# 查内存使用率高的应用
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT app, namespace, avg(memPercentage) AS avgMem, max(memPercentage) AS maxMem FROM fs_k8s_app_scaler_metrics_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR GROUP BY app, namespace ORDER BY maxMem DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
