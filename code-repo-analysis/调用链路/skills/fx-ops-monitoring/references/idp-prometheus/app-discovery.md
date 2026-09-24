# 应用视角查询流程

用于日常按应用排查：只查询 Prometheus，先确认一个 `app` 分布在哪些 profile/namespace、有哪些 Pod，再判断当前能查到哪些指标族，最后进入 Pod、JVM、Tomcat、Node 或中间件文档做趋势查询。

本流程禁止切到 ClickHouse、日志、Trace、Pyroscope、配置中心或服务注册系统。Prometheus 查不到的维度只记录为"当前 Prometheus 未采集"，不要建议改查其它数据源。

当前 Prometheus 指标里没有独立 `profile` 标签。在 Prometheus 查询口径里，先把 `profile` 当作 Kubernetes `namespace` 处理；如果 `profile` 或 `label_profile` 存在，再按真实标签改写查询。

> **namespace 与 profile 的对应**：Prometheus 中的 `namespace` 标签值即 `.agents/contracts/cloud-registry.md` 中的 `cms_profile`，也是 `biz-app-log` 等日志表的 `profile` 字段值。fx-ops profile（`--profile` 参数）与 namespace 的映射见该注册表。

## 0. 发现环境中的 Namespace 和应用

当对于一个全新的环境或排查开始时，如果需要知道该环境下存在哪些 Kubernetes Namespace，以及每个 Namespace 下部署了哪些业务应用（app），可以使用以下查询：

### 发现集群中包含的所有 Namespace

最快捷的方式是用 JVM 指标反查 namespace（JVM 指标覆盖率高，查询快）：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (namespace)(jvm_memory_used_bytes)' -j --limit-points 100
```

也可用 `kube_pod_info` 或容器指标：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (namespace)(kube_pod_info)' -j --limit-points 100
```

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (namespace)(container_cpu_usage_seconds_total)' -j --limit-points 100
```

### 发现某个 Namespace 下所有的业务应用 (app)
优先使用 container 指标提取所有活动的业务应用名称：
```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (app)(container_cpu_usage_seconds_total{namespace="${namespace}",container!="",container!="sandbox"})' -j --limit-points 200
```
或者通过 kube-state-metrics 标签提取已标记 of 业务应用：
```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (label_app)(kube_pod_labels{namespace="${namespace}"})' -j --limit-points 200
```

## 1. 查应用在哪些 profile/namespace

优先用 cAdvisor 的 container 指标查业务 `app`。这种方式可以跨 namespace 找到当前仍有容器指标的实例：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (k8s_cluster,namespace,app)(container_cpu_usage_seconds_total{app="${app_name}",container!="",container!="sandbox"})' \
 -j --limit-points 200
```

也可以用 kube-state-metrics 的 Pod label 交叉验证。注意业务应用名在 `label_app`，顶层 `app="kube-state-metrics"` 是采集端标签：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (k8s_cluster,namespace,label_app)(kube_pod_labels{label_app="${app_name}"})' \
 -j --limit-points 200
```

如果需要查是否存在真正的 profile 标签，用存在性查询确认，不要凭变量名猜：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count(container_cpu_usage_seconds_total{app="${app_name}",container!="",container!="sandbox",profile!=""})' -j

fx-ops idp --profile <profile> prometheus query --promql \
 'count(kube_pod_labels{label_app="${app_name}",label_profile!=""})' -j
```

当前环境这两类查询返回空，说明 profile 没有作为 Prometheus 标签采集；后续只按 `namespace` 继续查询。

## 2. 查某个 profile/namespace 下有哪些 Pod

确定 `k8s_cluster`、`namespace`、`app` 后，用 container 指标列出正在暴露业务容器指标的 Pod：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (namespace,pod,container)(container_cpu_usage_seconds_total{k8s_cluster="${k8s_cluster}",namespace="${namespace}",app="${app_name}",container!="",container!="sandbox"})' \
 -j --limit-points 100
```

返回示例格式：

| pod | container |
| --- | --- |
| `${pod_name}` | `${app_name}` |

不要只用 `pod=~"${app_name}-.*"` 枚举应用实例，因为它会同时匹配 `${app_name}-02`、`${app_name}-rest`、`${app_name}-rest4flow` 等前缀相近应用。枚举应用实例时优先用 `app="..."` 或 `label_app="..."`。

## 3. 查 Pod IP、host IP、node

`kube_pod_info` 本身没有业务 `label_app`，可与 `kube_pod_labels` 做向量匹配，得到准确的应用 Pod 清单和节点信息：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_pod_info{k8s_cluster="${k8s_cluster}",namespace="${namespace}"} * on(namespace,pod) group_left(label_app) kube_pod_labels{k8s_cluster="${k8s_cluster}",namespace="${namespace}",label_app="${app_name}"}' \
 -j --limit-points 100
```

这个查询会返回 `pod`、`pod_ip`、`host_ip`、`node`、`created_by_kind`、`created_by_name` 等标签，适合从应用跳到单 Pod dashboard 或 Node 监控。

单 Pod 查询：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_pod_info{namespace="${namespace}",pod="${pod_name}"}' -j
```

## 4. 查当前有哪些指标族

不要用过宽的 `__name__=~"container_.*"`、`__name__=~"jvm_.*"` 直接扫大范围；这类查询在当前上游容易返回 `502 promql.error.upstream_error`。应用视角建议按已知指标族逐个验证存在性。

### Container / cAdvisor

| 指标族 | 存在性查询 |
| --- | --- |
| CPU | `count by (__name__)(container_cpu_usage_seconds_total{k8s_cluster="${k8s_cluster}",namespace="${namespace}",app="${app_name}",container!="",container!="sandbox"})` |
| 内存 | `count by (__name__)(container_memory_working_set_bytes{k8s_cluster="${k8s_cluster}",namespace="${namespace}",app="${app_name}",container!="",container!="sandbox"})` |
| 网络 | `count by (__name__)(container_network_receive_bytes_total{k8s_cluster="${k8s_cluster}",namespace="${namespace}",pod=~"${app_name}-.*"})` |
| 文件系统 | `count by (__name__)(container_fs_reads_bytes_total{k8s_cluster="${k8s_cluster}",namespace="${namespace}",app="${app_name}",container!="",container!="sandbox"})` |

网络指标通常按 Pod 网络维度暴露，不一定带业务 `app` 标签；如果 `app="..."` 查不到，改用已确认 Pod 列表或谨慎使用 `pod=~"^${app_name}-[a-z0-9]+-[a-z0-9]+$"` 这类更窄的正则。

### JVM / Process

JVM 指标按 job 分三类，指标名差异大。先确认 job：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job)(jvm_memory_used_bytes{app_name="${app_name}"} or jvm_memory_bytes_used{app_name="${app_name}"})' -j
```

| 指标族 | 存在性查询 |
| --- | --- |
| JVM 内存（②主力 jvm-exporter） | `count by (area)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter"})` |
| JVM 内存（①springboot-actuator） | `count by (area,id)(jvm_memory_used_bytes{app_name="${app_name}",job="springboot-actuator"})` |
| JVM 内存（③旧版 JMX exporter） | `count by (area)(jvm_memory_bytes_used{app_name="${app_name}"})` |
| GC（②③） | `count by (gc)(jvm_gc_collection_seconds_count{app_name="${app_name}",job=~".*jvm-exporter"})` |
| GC（①） | `count by (gc,action,cause)(jvm_gc_pause_seconds_count{app_name="${app_name}",job="springboot-actuator"})` |
| FD（②③） | `process_open_fds{app_name="${app_name}",job=~".*jvm-exporter"}` |
| FD（①） | `process_files_open_files{app_name="${app_name}",job="springboot-actuator"}` |

某些常见 Micrometer 指标名在 ②③ 上为空，例如 `jvm_gc_pause_seconds_count`、`jvm_threads_live_threads`、`process_files_open_files`。遇到空结果时先回到 jvm.md 的发现查询，不要直接判定应用没有 GC、线程或 Tomcat 指标。

## 5. 常用下一步

| 目标 | 下一步文档 |
| --- | --- |
| 单 Pod CPU、内存、网络、磁盘、request/limit、重启 | k8s-pod.md |
| JVM heap/nonheap、GC、线程、FD | jvm.md |
| Tomcat 线程池、请求量、耗时、错误 | tomcat.md |
| Pod 所在 Node CPU/load/磁盘/网络/socket | host-node.md |
| RocketMQ topic/group/broker（自建 `rocketmq_*`） | rocketmq.md |
| foneshare 腾讯云 RocketMQ / `qce_rocketmq_*` / tenant 4.x/5.x | foneshare-tencent-rocketmq.md |
| foneshare 腾讯云公网 LB / CLB / `qce_lb_public_*` | foneshare-public-clb.md |

## 6. 查询注意事项

| 问题 | 建议 |
| --- | --- |
| 只知道应用名 | 先查 `count by (k8s_cluster,namespace,app)(container_cpu_usage_seconds_total{app="${app_name}"})` |
| 只知道 profile | 在 Prometheus 里先当作 `namespace` 使用，并用 `profile!=""` / `label_profile!=""` 确认是否存在真实标签 |
| app 前缀相近 | 用 `app="..."` 或 `label_app="..."`，避免裸 `pod=~"app-.*"` |
| 指标发现 502 | 缩小 matcher，按指标族逐个 `count by (__name__)` |
| JVM/Tomcat 指标为空 | 先做候选指标名发现，不同 exporter 命名不一致 |
| 需要 30 分钟趋势 | 定位到具体指标后再 range 查询，`--step 1m` |
