# 指标源与类别

用于按 exporter / 采集源选择指标文档和发现查询。本文件只查询 Prometheus，不引用其它数据源。

## 总览

| 指标源 | 主要对象 | 常见前缀 / 指标 | 读取 |
| --- | --- | --- | --- |
| cAdvisor | container、Pod 资源 | `container_cpu_*`、`container_memory_*`、`container_network_*`、`container_fs_*` | k8s-pod.md |
| kube-state-metrics | Kubernetes 对象状态 | `kube_pod_*`、`kube_node_*`、`kube_deployment_*`、`kube_pod_container_resource_*` | k8s-pod.md |
| node-exporter | 物理机、虚拟机、Kubernetes Node | `node_cpu_*`、`node_memory_*`、`node_filesystem_*`、`node_disk_*`、`node_network_*`、`node_sockstat_*` | host-node.md |
| JMX / Micrometer | Java 进程、JVM | `jvm_*`、`process_*`、`system_*` | jvm.md |
| Tomcat / HTTP | Tomcat 线程池、请求、连接 | `tomcat_*`、`http_server_requests_*` | tomcat.md |
| RocketMQ exporter | 自建 RocketMQ topic、group、broker | `rocketmq_*` | rocketmq.md |
| Kafka exporter | 集群侧消费组 lag、topic 位点 | `kafka_consumergroup_lag`、`kafka_brokers` | kafka.md（勿与 `ClickHouseMetrics_Kafka*` 混淆） |
| 腾讯云 RocketMQ（foneshare） | 腾讯云 4.x/5.x 集群，主键 `tenant` | `qce_rocketmq_*` | foneshare-tencent-rocketmq.md |
| 腾讯云公网 CLB（foneshare） | 公网负载均衡客户端/RS/丢包/健康检查 | `qce_lb_public_*` | foneshare-public-clb.md |
| 中间件 exporter | PostgreSQL、MongoDB、Redis、Elasticsearch、ClickHouse | `pg_*`、`mongodb_*`、`redis_*`、`elasticsearch_*`、`ClickHouseMetrics_*` | middleware.md |
| Kubernetes 组件 | apiserver、CoreDNS、scheduler、controller-manager、kubelet、etcd | `apiserver_*`、`coredns_*`、`scheduler_*`、`workqueue_*`、`kubelet_*`、`etcd_*` | 本文先做发现，确认后再补专门文档 |

## 通用发现

先看 target 分组，确认有哪些 exporter：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job)(up)' -j --limit-points 300
```

如果结果过大，按关键词缩小：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,instance)(up{job=~".*(cadvisor|kube-state|node-exporter|jmx|tomcat|rocketmq|redis|mongo|mysql|postgres|kubelet|apiserver|coredns|etcd).*"})' \
 -j --limit-points 300
```

## cAdvisor

用于回答容器 CPU、内存、网络、磁盘、throttling。

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,namespace,pod,container)(container_cpu_usage_seconds_total{namespace="${namespace}",container="${app_name}"})' -j
```

已验证当前环境 pause 容器是 `container="sandbox"`。业务查询优先过滤：

```text
container!="",container!="sandbox"
```

## kube-state-metrics

用于回答 Kubernetes 对象"声明状态"和"当前状态"，例如 Pod IP、Node、Ready、request/limit、重启次数。

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)({__name__=~"kube_pod_.*",namespace="${namespace}"})' \
 -j --limit-points 100
```

如果宽前缀查询触发 502，改查具体候选指标：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(kube_pod_info{namespace="${namespace}"} or kube_pod_labels{namespace="${namespace}"} or kube_pod_status_phase{namespace="${namespace}"} or kube_pod_container_status_restarts_total{namespace="${namespace}"})' -j
```

## node-exporter

用于回答节点 CPU、load、内存、磁盘、网络、socket。Pod dashboard 的 `host_ip` 可以映射到 node-exporter 的 `instance` 或 kube-state-metrics 的 `node`。

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,instance)(node_uname_info{instance=~".*${host_ip}.*"})' -j
```

node-exporter 的 `job` 可能按机器池区分。先发现 job，再决定是否看 Kubernetes Node、RocketMQ 节点、MongoDB 节点、PostgreSQL 节点或其它机器池：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job)(node_uname_info)' -j --limit-points 200
```

## JMX / Micrometer

用于回答 Java 进程和 JVM 指标。当前环境存在三类 JVM exporter 配置，指标命名差异大，必须先确认 job：

```bash
# 先确认目标应用的 job
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job)(jvm_memory_used_bytes{app_name="${app_name}"} or jvm_memory_bytes_used{app_name="${app_name}"})' -j
```

| job | 占比 | 内存指标名 | GC 指标名 | 线程 | FD |
| --- | --- | --- | --- | --- | --- |
| `tke70-k8s1-jvm-exporter` / `k8s*-jvm-exporter` | ~90% | `jvm_memory_used_bytes`（只有 `area`） | `jvm_gc_collection_seconds_count` | ❌ | `process_open_fds` |
| `springboot-actuator` | ~5% | `jvm_memory_used_bytes`（有 `area`+`id`） | `jvm_gc_pause_seconds_count` | ✅ | `process_files_open_files` |
| `k8s1-jvm-exporter`(旧) / `vm-jvm-exporter` | ~5% | `jvm_memory_bytes_used`（只有 `area`） | `jvm_gc_collection_seconds_count` | ❌ | `process_open_fds` |

如果常见指标为空，不要直接判断没有 JVM 监控；按 jvm.md 的发现查询继续确认。

## Tomcat / HTTP

当前环境 `tomcat_*` 指标不存在。Spring Boot 应用使用 `http_server_requests_seconds_*` 系列指标。先确认可用指标：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(http_server_requests_seconds_count{app_name="${app_name}",job="springboot-actuator"})' -j
```

## RocketMQ exporter

当前环境 **自建采集**已验证为 RocketMQ 4.x exporter 风格，优先查具体指标，不做宽泛全量扫描：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(rocketmq_producer_tps or rocketmq_consumer_tps or rocketmq_group_diff or rocketmq_broker_tps or rocketmq_group_retrydiff or rocketmq_client_consume_fail_msg_tps)' -j
```

## 腾讯云 RocketMQ（foneshare）

`qce_rocketmq_*` 由 `qcloud-exporter` 采集，集群主键是 `tenant`。4.x tenant 形如 `rocketmq-*`（附加 `cluster_name`），5.x tenant 形如 `rmq-*`（附加 `instance_name`）。不要与自建 `rocketmq_*` 混查。指标说明见 foneshare-tencent-rocketmq.md。

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (tenant)(qce_rocketmq_rocketmqexpensepulltps_sum or qce_rocketmq_rocketmqgroupdiff_sum)' -j --limit-points 50
```

## 中间件 exporter

如果用户问 PostgreSQL、MongoDB、Redis、MySQL 等中间件，只能从 Prometheus 指标判断 exporter 暴露的聚合状态。先发现 target：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,instance)(up{job=~".*(postgres|pg|mongo|redis|mysql).*"})' \
 -j --limit-points 200
```

再按具体 exporter 前缀查指标是否存在。前缀因 exporter 版本可能不同，必须先发现：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__,job)({__name__=~"(pg|postgres|mongodb|redis|mysql)_.*"})' \
 -j --limit-points 300
```

如果该查询过大或 502，改为按 job 和具体候选指标拆开查询。

## Kubernetes 组件

用于判断集群控制面和基础组件状态。先发现 target：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,instance)(up{job=~".*(apiserver|coredns|scheduler|controller|kubelet|etcd).*"})' \
 -j --limit-points 200
```

常见指标族：

| 组件 | 常见指标前缀 |
| --- | --- |
| apiserver | `apiserver_*` |
| CoreDNS | `coredns_*` |
| scheduler | `scheduler_*` |
| controller-manager | `workqueue_*`、`rest_client_*` |
| kubelet | `kubelet_*`、`container_runtime_*` |
| etcd | `etcd_*` |

不要在未确认 target 和指标存在前直接生成大范围控制面查询。
