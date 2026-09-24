# idp prometheus 指标选择与发现

用于在不知道具体 metric 名称时，先对齐 Grafana 变量、Prometheus 标签和指标集合。确认指标后，再读取 Pod、Node、JVM、Tomcat、RocketMQ、Kafka、foneshare 腾讯云 RocketMQ、foneshare 公网 LB 对应子文档。

如果日常问题是“看一个应用有哪些 profile/namespace、哪些 Pod、当前有哪些指标”，先读 app-discovery.md。

如果用户用自然语言描述监控目标，需要先生成 PromQL，先读 promql-rules.md。如果不确定指标来自哪个 exporter，先读 metric-sources.md。

## 变量与标签

常用 Grafana 变量通常映射到 Prometheus 标签：

| Grafana 变量 | 常见 Prometheus 标签 | 说明 |
| --- | --- | --- |
| `k8s_cluster` | `cluster` / `k8s_cluster` | 集群，不同采集链路命名可能不同 |
| `namespace` | `namespace` | Kubernetes namespace |
| `app` | `app` / `application` / `job` | 应用或 workload 名称 |
| `pod` | `pod` | Pod 名称 |
| `pod_ip` | `pod_ip` / `pod` 关联标签 | Pod IP 有时只在 kube-state-metrics info 指标中存在 |
| `host_ip` | `instance` / `node` / `host_ip` | 节点或 node-exporter instance |
| `interval` | 无标签 | `rate()`、`increase()`、`irate()` 的窗口 |
| `topic` | `topic` / `topic_name` | RocketMQ / Kafka topic |
| `consumer_group` | `group` / `consumer_group` / `consumerGroup` / `consumergroup` | RocketMQ group；Kafka 用 `consumergroup` |
| `broker` | `broker` / `broker_ip` / `brokerName` | RocketMQ broker |
| `cluster` | `cluster` / `cluster_name` / `rocketmq_cluster` | RocketMQ 集群 |

先不要假设标签名完全一致。优先用低成本 instant 查询确认标签：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,instance,namespace,pod,container,app)(up)' -j
```

如果返回过大，逐步加过滤条件：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,instance,pod)(up{namespace="${namespace}"})' -j
```

## 指标发现

按前缀发现指标是否存在：

```bash
# Kubernetes / cAdvisor 容器指标
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)({__name__=~"container_.*",namespace="${namespace}"})' -j

# 目标 Pod 的 cAdvisor 标签
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,instance,k8s_cluster,namespace,pod,container,image)(container_cpu_usage_seconds_total{namespace="${namespace}",pod="${pod_name}"})' -j

# 从 container 指标发现业务 app
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (app)(container_cpu_usage_seconds_total{k8s_cluster="${k8s_cluster}",namespace="${namespace}",container!="",container!="sandbox"})' -j

# 从 kube-state-metrics 的 Pod labels 发现业务 app
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (label_app)(kube_pod_labels{k8s_cluster="${k8s_cluster}",namespace="${namespace}",label_app!=""})' -j

# 验证 profile 是否被采集
fx-ops idp --profile <profile> prometheus query --promql \
 'count(kube_pod_labels{k8s_cluster="${k8s_cluster}",namespace="${namespace}",label_profile!=""})' -j

# kube-state-metrics 指标
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)({__name__=~"kube_.*",namespace="${namespace}"})' -j

# Pod 到 Node / Pod IP 映射
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_pod_info{namespace="${namespace}",pod="${pod_name}"}' -j

# Node 元数据与状态
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_node_info{k8s_cluster="${k8s_cluster}",node="${host_ip}"}' -j
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_node_status_condition{k8s_cluster="${k8s_cluster}",node="${host_ip}",status="true"}' -j

# node-exporter 指标
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)({__name__=~"node_.*",instance=~".*${host_ip}.*"})' -j

# JVM / Micrometer 指标
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(jvm_memory_used_bytes{app_name="${app_name}"} or jvm_memory_bytes_used{app_name="${app_name}"})' -j

# Tomcat 指标
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(http_server_requests_seconds_count{app_name="${app_name}",job="springboot-actuator"})' -j

# RocketMQ 指标（自建 exporter）
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)({__name__=~"rocketmq_.*"})' -j

# 腾讯云 RocketMQ（foneshare，qce_rocketmq_*）
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (tenant)(qce_rocketmq_rocketmqexpensepulltps_sum or qce_rocketmq_rocketmqgroupdiff_sum)' -j --limit-points 50

# Kafka 消费组 lag（kafka-exporter）
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (job, k8s_cluster)(kafka_consumergroup_lag)' -j
```

宽泛前缀查询可能触发上游 502。遇到 502 时，按 promql-rules.md 缩小 matcher，或按 metric-sources.md 的具体候选指标拆开查询。

## Dashboard 分组到文档

| Dashboard 分组 | 读取 |
| --- | --- |
| 自然语言生成 PromQL、默认时间范围、topk/bottomk、避免全量扫 | promql-rules.md |
| 按 exporter / 采集源发现指标：cAdvisor、kube-state-metrics、node-exporter、JMX、Tomcat、RocketMQ、中间件、Kubernetes 组件 | metric-sources.md |
| 按应用发现 profile/namespace、Pod、Pod IP、host IP、当前指标族 | app-discovery.md |
| Pod 表格、CPU 请求/上限、内存请求/上限、重启、Pod IP、节点 IP | k8s-pod.md |
| CPU 使用情况、CPU 使用率增长、容器 CPU 使用情况、CPU 受限情况 | k8s-pod.md |
| 内存使用情况、容器工作集内存、mem-cache、mem-rss、total_inactive_file、kernel memory | k8s-pod.md |
| 容器网络流量、容器磁盘流量 | k8s-pod.md |
| 从 Pod/container 指标发现 app、确认 profile 标签是否存在 | k8s-pod.md |
| `container_cpu_usage_seconds_total`、`container_memory_working_set_bytes`、`kube_pod_info`、`kube_node_info`、`kube_node_status_condition` | k8s-pod.md / host-node.md |
| JVM 内存使用/提交、Heap、Non-Heap、内存分区、GC、Class loading、Threads Count、Open File Descriptors | jvm.md |
| Tomcat HTTP 连接线程池 | tomcat.md |
| RocketMQ topic 生产/消费 TPS、堆积、消费延迟、broker、exporter 采集状态（自建 `rocketmq_*`） | rocketmq.md |
| Kafka 消费组 lag（`kafka_consumergroup_lag`，job `kafka-log-exporter` / `kafka-audit-log-exporter`） | kafka.md |
| foneshare 腾讯云 RocketMQ / `qce_rocketmq_*` / tenant 4.x/5.x 指标含义与单位 | foneshare-tencent-rocketmq.md |
| foneshare 腾讯云公网 LB / CLB / `qce_lb_public_*` 指标含义与单位 | foneshare-public-clb.md |
| 所在节点 CPU/load/内存/网络/磁盘 IO/socket | host-node.md |
| 下游中间件健康度 (PostgreSQL/MongoDB/Redis/ES/CH) | middleware.md |

## 查询策略

| 目标 | 建议 |
| --- | --- |
| 看当前状态 | Instant 查询，先用 `-j` 观察 labels |
| 看 30 分钟趋势 | Range 查询，`--step 1m`，`rate(...[1m])` 或 `rate(...[5m])` |
| 看 24 小时趋势 | Range 查询，`--step 5m` 或更大，避免 sample 过多 |
| 排查 spike | 先用 `rate(...[1m])`，必要时改 `irate(...[1m])` |
| 排查累计次数 | 对 counter 用 `increase(...[window])` 或 `rate(...[window])` |
| 对比 request/limit | 用 kube-state-metrics 指标作为分母，容器实际使用作为分子 |
| 多实例 / 多 Pod / 多 topic 排行 | 用 `topk()` / `bottomk()`，并设置合理 `--limit-points` |

## 标签过滤模板

```text
{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}
```

如果 dashboard 是按 app 展示所有实例，把 `pod="..."` 改为 `container="${app_name}"` 或 `pod=~"${app_name}-.*"`：

```text
{namespace="${namespace}",container="${app_name}",container!="sandbox"}
```

## 常见单位

| 指标 | Prometheus 原始单位 | 展示换算 |
| --- | --- | --- |
| CPU usage | seconds counter | `rate()` 后为 core |
| CPU request/limit | core | 直接展示 core |
| Memory | bytes | GiB/MiB |
| Network | bytes counter | `rate()` 后为 B/s |
| Disk IO | bytes / seconds counter | B/s、seconds/op、util% |
| JVM GC | seconds/count counter | `rate()` 或 `increase()` |
| RocketMQ TPS | counter / gauge | `rate()`、直接值或 exporter 已算好 TPS |
| RocketMQ lag | message count / offset diff | 直接展示条数 |
| RocketMQ latency | milliseconds / seconds | 按指标单位展示或转换 |
| foneshare 公网 LB | 以文档单位为准 | 不换算：`ClientNewConn` 个/秒，`NewConn` 个/分钟，`InDropBits`/`OutDropBits` Byte |
