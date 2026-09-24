# Kubernetes Pod 与容器指标

用于排查 Pod 状态、资源配额、容器 CPU/内存/网络/磁盘、CPU throttling、重启次数。典型 dashboard 变量：`namespace`、`app`、`pod`、`pod_ip`、`host_ip`、`interval`。

## 过滤模板

单 Pod 查询：

```text
{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}
```

应用级汇总（推荐）：

```text
{namespace="${namespace}",container="${app_name}",container!="sandbox"}
```

或按 Pod 前缀：

```text
{namespace="${namespace}",pod=~"${app_name}-.*",container!="",container!="sandbox"}
```

当前环境里 `container_*` 来自 `job="cadvisor"`，目标 Pod 的 `container_cpu_usage_seconds_total` 有两条容器序列：

| container | image | 说明 |
| --- | --- | --- |
| `${app_name}` | 业务镜像 | 业务容器 |
| `sandbox` | `ccr.ccs.tencentyun.com/library/pause:latest` | Pod pause 容器，业务查询通常排除 |

优先用 `container!="",container!="sandbox"` 过滤。不要照搬其他环境常见的 `container!="POD"`，当前 TKE/cAdvisor 暴露的是 `sandbox`。

## 本环境已验证指标

| 指标 | 当前规模 / 样例 | 关键标签 |
| --- | --- | --- |
| `container_cpu_usage_seconds_total` | 全局约 26517 条 | `job`、`instance`、`k8s_cluster`、`namespace`、`pod`、`container`、`image` |
| `container_memory_working_set_bytes` | 全局约 25422 条 | 同上 |
| `kube_pod_info` | 全局约 8104 条 | `pod_ip`、`host_ip`、`node`、`uid`、`created_by_kind`、`created_by_name` |
| `kube_node_info` | 全局约 470 条，跨多个集群 | `node`、`internal_ip`、`kubelet_version`、`container_runtime_version`、`os_image` |
| `kube_node_status_condition` | 全局约 7050 条 | `node`、`condition`、`status` |

## 从 Pod / container 指标发现 app 与 profile

如果只知道 namespace 或 Pod 前缀，优先从 container 指标发现业务应用：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (app)(container_cpu_usage_seconds_total{namespace="${namespace}",container!="",container!="sandbox"})' \
 -j --limit-points 300
```

也可以用 kube-state-metrics 的 Pod label 指标确认 Kubernetes 原始 label。注意这里的采集端 `app="kube-state-metrics"` 不是业务应用名，业务应用名在 `label_app` 上：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (label_app)(kube_pod_labels{namespace="${namespace}",label_app="${app_name}"})' \
 -j --limit-points 50
```

当前环境的结论：

| 指标 | app 来源 | profile 来源 |
| --- | --- | --- |
| `container_cpu_usage_seconds_total` | `app` | 未发现 `profile` |
| `container_memory_working_set_bytes` | `app` | 未发现 `profile`、`env`、`environment` |
| `kube_pod_labels` | `label_app` | 未发现 `label_profile`、`label_env` |
| `kube_pod_info` | 采集端 `app="kube-state-metrics"`，不适合发现业务 app | 未发现 profile |

全局存在性查询也未发现 `profile` 或 `label_profile`。因此当前 Prometheus 采集链路不能通过 Pod/container 指标枚举 profile；在只查询 Prometheus 的前提下，只能继续使用 `namespace` 作为 profile 口径。

## Pod 基本信息

| 目标 | PromQL 模板 |
| --- | --- |
| Pod 是否 Running | `kube_pod_status_phase{namespace="${namespace}",pod="${pod_name}",phase="Running"}` |
| Pod 启动时间 | `kube_pod_start_time{namespace="${namespace}",pod="${pod_name}"}` |
| Pod 运行时长（秒） | `time() - kube_pod_start_time{namespace="${namespace}",pod="${pod_name}"}` |
| 重启次数 | `sum by (pod)(kube_pod_container_status_restarts_total{namespace="${namespace}",pod="${pod_name}"})` |
| Pod IP / Node | `kube_pod_info{namespace="${namespace}",pod="${pod_name}"}` |

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_pod_info{namespace="${namespace}",pod="${pod_name}"}' -j
```

### 根据 Pod 查询所在宿主机节点 IP (host_ip)

当需要定位某个 Pod 被调度到了哪台宿主机节点，以排查节点级物理指标时，可以通过 `kube_pod_info` 查询。

如果知道 `namespace`：
```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_pod_info{namespace="${namespace}",pod="${pod_name}"}' -j
```
若仅知道 `pod` 名称，可以直接用其作为唯一标识符查询：
```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_pod_info{pod="${pod_name}"}' -j
```

**关键返回标签解析**：
- `host_ip`：该 Pod 运行所在的 K8S 宿主机节点 IP。
- `node`：K8S 宿主机节点的名称。
- `pod_ip`：该 Pod 的容器内网络 IP。

获取到 `host_ip`（宿主机节点 IP）后，请参考 host-node.md 了解如何查询该主机的 CPU、负载、内存、磁盘 IO 及网络等运行指标。

## Request / Limit

kube-state-metrics 版本不同，资源指标可能是两种命名之一。先确认存在的指标：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)({__name__=~"kube_pod_container_resource_.*",namespace="${namespace}"})' -j
```

| 目标 | 新版模板 | 旧版模板 |
| --- | --- | --- |
| CPU request | `sum by (pod)(kube_pod_container_resource_requests{namespace="${namespace}",resource="cpu",unit="core",pod="${pod_name}"})` | `sum by (pod)(kube_pod_container_resource_requests_cpu_cores{namespace="${namespace}",pod="${pod_name}"})` |
| CPU limit | `sum by (pod)(kube_pod_container_resource_limits{namespace="${namespace}",resource="cpu",unit="core",pod="${pod_name}"})` | `sum by (pod)(kube_pod_container_resource_limits_cpu_cores{namespace="${namespace}",pod="${pod_name}"})` |
| 内存 request | `sum by (pod)(kube_pod_container_resource_requests{namespace="${namespace}",resource="memory",unit="byte",pod="${pod_name}"})` | `sum by (pod)(kube_pod_container_resource_requests_memory_bytes{namespace="${namespace}",pod="${pod_name}"})` |
| 内存 limit | `sum by (pod)(kube_pod_container_resource_limits{namespace="${namespace}",resource="memory",unit="byte",pod="${pod_name}"})` | `sum by (pod)(kube_pod_container_resource_limits_memory_bytes{namespace="${namespace}",pod="${pod_name}"})` |

## CPU

| 目标 | PromQL 模板 |
| --- | --- |
| Pod CPU 使用核数 | `sum by (namespace,pod,container)(rate(container_cpu_usage_seconds_total{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}[1m]))` |
| 应用所有 Pod CPU | `sum by (pod)(rate(container_cpu_usage_seconds_total{namespace="${namespace}",container="${app_name}",container!="sandbox"}[1m]))` |
| CPU 使用率 / limit | `sum by (pod)(rate(container_cpu_usage_seconds_total{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}[1m])) / sum by (pod)(kube_pod_container_resource_limits{namespace="${namespace}",resource="cpu",unit="core",pod="${pod_name}"}) * 100` |
| CPU throttling 比例 | `sum by (pod)(rate(container_cpu_cfs_throttled_periods_total{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}[1m])) / sum by (pod)(rate(container_cpu_cfs_periods_total{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}[1m])) * 100` |

CPU 使用核数是 `container_cpu_usage_seconds_total` 的增长率。dashboard 中的"0.19 核"这类值通常就是 `rate(...[interval])` 后的结果。

## 内存

| 目标 | PromQL 模板 |
| --- | --- |
| 容器内存使用量 | `sum by (pod)(container_memory_usage_bytes{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"})` |
| 容器工作集内存 | `sum by (namespace,pod,container)(container_memory_working_set_bytes{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"})` |
| RSS / Java 物理内存近似 | `sum by (pod)(container_memory_rss{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"})` |
| 文件缓存 | `sum by (pod)(container_memory_cache{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"})` |
| inactive file | `sum by (pod)(container_memory_total_inactive_file{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"})` |
| kernel memory | `sum by (pod)(container_memory_kernel_usage_bytes{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"})` |
| 内存使用率 / limit | `sum by (pod)(container_memory_working_set_bytes{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}) / sum by (pod)(kube_pod_container_resource_limits{namespace="${namespace}",resource="memory",unit="byte",pod="${pod_name}"}) * 100` |

dashboard 的容器内存拆解通常是：

```text
container_memory_usage_bytes = container_memory_rss + container_memory_cache + container_memory_kernel_usage_bytes + other
container_memory_working_set_bytes = container_memory_usage_bytes - container_memory_total_inactive_file
```

排查 OOM 时优先看 `container_memory_working_set_bytes / memory limit`，再看 RSS、cache 和 JVM heap。

## 网络

| 目标 | PromQL 模板 |
| --- | --- |
| 接收流量 | `sum by (pod)(rate(container_network_receive_bytes_total{namespace="${namespace}",pod="${pod_name}"}[1m]))` |
| 发送流量 | `sum by (pod)(rate(container_network_transmit_bytes_total{namespace="${namespace}",pod="${pod_name}"}[1m]))` |
| 接收包量 | `sum by (pod)(rate(container_network_receive_packets_total{namespace="${namespace}",pod="${pod_name}"}[1m]))` |
| 发送包量 | `sum by (pod)(rate(container_network_transmit_packets_total{namespace="${namespace}",pod="${pod_name}"}[1m]))` |
| 丢包 | `sum by (pod)(rate(container_network_receive_packets_dropped_total{namespace="${namespace}",pod="${pod_name}"}[1m]) + rate(container_network_transmit_packets_dropped_total{namespace="${namespace}",pod="${pod_name}"}[1m]))` |

## 磁盘 / 文件系统 IO

| 目标 | PromQL 模板 |
| --- | --- |
| 读吞吐 | `sum by (pod)(rate(container_fs_reads_bytes_total{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}[1m]))` |
| 写吞吐 | `sum by (pod)(rate(container_fs_writes_bytes_total{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}[1m]))` |
| 读操作数 | `sum by (pod)(rate(container_fs_reads_total{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}[1m]))` |
| 写操作数 | `sum by (pod)(rate(container_fs_writes_total{namespace="${namespace}",pod="${pod_name}",container!="",container!="sandbox"}[1m]))` |

部分容器运行时或采集配置不会提供容器磁盘指标；dashboard 出现 `No data` 时，改查所在节点磁盘 IO：host-node.md。

## Range 查询模板

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (pod)(rate(container_cpu_usage_seconds_total{namespace="${namespace}",container="${app_name}",container!="sandbox"}[1m]))' \
 --start "$(date -u -v-30M +%Y-%m-%dT%H:%M:%SZ)" \
 --end "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
 --step "1m" -j
```

## 解读

| 现象 | 优先检查 |
| --- | --- |
| CPU 使用低但延迟高 | throttling、线程池、GC、下游依赖 |
| CPU throttling 高 | CPU limit 是否过低，`rate(container_cpu_cfs_throttled_periods_total)` |
| 内存接近上限 | working set、RSS、JVM heap、metaspace、cache |
| 容器 OOM | `container_memory_working_set_bytes` 是否超过 limit，重启次数是否增加 |
| 网络突增 | receive/transmit bytes 与包量、所在节点网络 |
| 容器磁盘无数据 | 查 node-exporter 磁盘指标 |
