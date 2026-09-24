# k8s-event-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: Kubernetes 事件日志分布式表，存储 K8s 集群中 Event 资源的变更事件，包括 Pod 调度、扩缩容、资源状态变化等集群级事件。

**时间字段**: _time_second_

---

## 表：k8s_events_dist

**说明**: Kubernetes 事件日志分布式表，存储 K8s 集群中 Event 资源的变更事件，包括 Pod 调度、扩缩容、资源状态变化等集群级事件。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'k8s_events_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(involvedObject_kind, involvedObject_namespace, involvedObject_name, reason, source_host, action, type, _time_second_)` |
| ORDER BY | `(involvedObject_kind, involvedObject_namespace, involvedObject_name, reason, source_host, action, type, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3) | 采集时间（秒级精度） |
| `action` | String | 触发的动作 |
| `cluster` | String | K8s 集群标识，如 k8s1 |
| `count` | Int64 | 事件发生次数 |
| `eventTime` | String | 事件时间（microsecond 精度） |
| `firstTimestamp` | String | 首次发生时间 |
| `involvedObject_kind` | String | 关联对象类型：CronJob/Pod/Node 等 |
| `involvedObject_name` | String | 关联对象名称 |
| `involvedObject_namespace` | String | 关联对象命名空间 |
| `lastTimestamp` | String | 最近发生时间 |
| `message` | String | 事件详细消息 |
| `metadata_creationTimestamp` | String | 事件创建时间（ISO 8601） |
| `metadata_name` | String | 事件名称，格式如 {resource}.{hash} |
| `metadata_namespace` | String | 事件所属命名空间 |
| `metadata_uid` | String | 事件唯一 ID |
| `reason` | String | 事件原因，如 SuccessfulCreate |
| `reportingComponent` | String | 上报组件 |
| `reportingInstance` | String | 上报实例 |
| `source_component` | String | 事件来源组件，如 cronjob-controller |
| `source_host` | String | 事件来源主机 |
| `type` | String | 事件类型：Normal/Warning |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查最近1小时某命名空间的 Warning 事件
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT metadata_namespace, involvedObject_name, reason, message, count, _time_second_ FROM k8s_events_dist WHERE type = 'Warning' AND _time_second_ > now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20"

# 查某个 Pod 的事件
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT reason, message, count, lastTimestamp FROM k8s_events_dist WHERE involvedObject_name LIKE '%runtime-provider%' AND _time_second_ > now() - INTERVAL 6 HOUR ORDER BY _time_second_"

# 按原因聚合统计
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT reason, count() AS cnt FROM k8s_events_dist WHERE _time_second_ > now() - INTERVAL 24 HOUR GROUP BY reason ORDER BY cnt DESC"
```

### 常见事件类型

| reason（原因） | 说明 |
| --- | --- |

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
