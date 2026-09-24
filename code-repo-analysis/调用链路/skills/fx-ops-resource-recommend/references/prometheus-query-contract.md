# Prometheus 查询合同

## 允许的证据来源

本 skill 只使用已确认的 Kubernetes Prometheus 指标和只读 `fx-ops idp ... prometheus query` 入口。每次查询都必须记录 metrics profile、cluster、namespace、目标标签、容器范围、起止时间、step、PromQL、退出状态和响应摘要。

```bash
fx-ops idp --profile <metrics_profile> prometheus query --promql '<expr>' \
  --start '<start>' --end '<end>' --step '<step>' --limit-points <n> -j
```

`profile` 由实际 Kubernetes cluster 确定，而 namespace 仅是过滤维度：

| 集群模式 | profile |
| --- | --- |
| `tke70-k8s*`、`tke60-k8s*`、`k8s0`、`k8s1` | `foneshare` |
| `hsyk-k8s*` | `hsyk` |
| `sbt-*` | `sbt` |
| `mengniu-*` | `mengniu` |

此表仅在 cluster 名称已被确认时可用；无法确认覆盖关系时必须先补齐并确认真实 cluster 与 profile，返回 `blocked`，不得以发现替代 profile 确认或猜 profile。

## 发现先于查询

发现只能在已确认 profile 和已确认查询范围内进行，不能用来补收基础 profile 或范围。**任何 discovery PromQL 执行前，必须同时满足：metrics `profile` 已确认，且至少一个 `k8s_cluster`、`namespace`，或已发现的 application/workload/pod selector 已确认。缺少任一前置条件时返回 `blocked`，请求缺口；用户授权探测不能豁免。** 前置条件满足后，才可在用户可审阅的窄范围内检查目标 Pod、标签和 request/limit 指标名：

```promql
count by (__name__) (
  {__name__=~"kube_pod_container_resource_.*", namespace="<confirmed-namespace>"}
)
```

每条 discovery PromQL 都必须保留上述至少一个有效 scope；用户授权探测也不能豁免。没有可用的已确认 selector 时返回 `blocked` 并请求 cluster、namespace 或 workload/pod 范围，禁止探测 `count by (k8s_cluster)(up)` 或任何其他无 scope 的全局指标。只追加已经发现的标签，不得猜测 `app`、`label_app` 或 `app_name`。请求/限制优先使用通用指标：

```promql
kube_pod_container_resource_requests{namespace="<namespace>", resource="cpu", unit="core"}
kube_pod_container_resource_limits{namespace="<namespace>", resource="cpu", unit="core"}
kube_pod_container_resource_requests{namespace="<namespace>", resource="memory", unit="byte"}
kube_pod_container_resource_limits{namespace="<namespace>", resource="memory", unit="byte"}
```

若发现证明通用指标不存在，才可使用已确认的旧命名：

```promql
kube_pod_container_resource_requests_cpu_cores
kube_pod_container_resource_limits_cpu_cores
kube_pod_container_resource_requests_memory_bytes
kube_pod_container_resource_limits_memory_bytes
```

禁止在未发现标签前把 `app`、`label_app`、`app_name` 等当作可互换标签。记录最终选用的 metric name 和 selector。

## 容器和服务过滤

所有容器资源表达式至少排除：

```promql
container!="", container!="sandbox"
```

追加已发现的 `namespace`、cluster 和 pod/workload/app 标签。先证明 label 存在，再将其加入 selector。sidecar 有两种合法模式：

1. **整体 workload**：应用容器与 sidecar 均计入使用、request、limit；
2. **主应用容器**：按显式容器名称排除 sidecar，且三类数据都使用相同集合。

两种模式不能混用，且报告必须说明选择和原因。

## 已确认指标表达式

以下表达式是语义模板；`<selector>` 必须替换为已发现的窄范围过滤。所有资源表逻辑行的聚合键固定为 `(pod, container)`：CPU、内存、request、limit 和 throttling 只在相同 `(pod, container)` 上对齐和比较。需要 workload 级汇总时，先得到这些容器行，再将**全部**容器行单独命名并求和；绝不能把 Pod 总使用量与单容器 request/limit 混在同一行。

### CPU 使用

```promql
sum by (pod, container) (
  rate(container_cpu_usage_seconds_total{<selector>, container!="", container!="sandbox"}[1m])
)
```

结果为 core。`container_cpu_usage_seconds_total` 是 counter，必须使用 `rate()`；不能将裸 counter 当 CPU 使用率。

### 内存使用

```promql
sum by (pod, container) (
  container_memory_working_set_bytes{<selector>, container!="", container!="sandbox"}
)
```

结果为 byte；本 skill 用 working set 做内存规格评估，不用 cache 或 RSS 的非等价替换冒充它。

### request 与 limit

```promql
sum by (pod, container) (
  kube_pod_container_resource_requests{<selector>, resource="cpu", unit="core"}
)

sum by (pod, container) (
  kube_pod_container_resource_limits{<selector>, resource="memory", unit="byte"}
)
```

对 CPU 和 memory 分开执行并保存，结果保持按 `(pod, container)` 输出。若 Pod 间或容器间数值不同，先报告配置漂移，再决定是否能够得出 workload 候选值；不得把一个 Pod 的全部容器总量与某一容器的配置相比较。

### CPU throttling

```promql
sum by (pod, container) (
  rate(container_cpu_cfs_throttled_periods_total{<selector>, container!="", container!="sandbox"}[1m])
)
/
sum by (pod, container) (
  rate(container_cpu_cfs_periods_total{<selector>, container!="", container!="sandbox"}[1m])
) * 100
```

记录分子、分母、`rate` 窗口和零分母处理。throttling 是 CPU limit 风险信号，不能代替内存或业务 SLO 证据。

### Pod 生命周期与分布

```promql
kube_pod_info{<selector>}
kube_pod_status_phase{<selector>, phase="Running"}
kube_pod_start_time{<selector>}
kube_pod_container_status_restarts_total{<selector>}
```

它们用于实例数、分布、滚动发布/重启扰动和有效运行判断。未确认 OOM 专用指标时，重启只能说明重启事实，不能被标为 OOM 原因。

## 时间序列采集

| 目的 | 推荐方式 |
| --- | --- |
| 近期症状确认 | 1–5 分钟 step，短窗，标记为 observation |
| 7–14 天分布 | 5–15 分钟 step 或按日切片的细粒度窗口；保留 coverage |
| 28 天以上 | 使用固定切片；细粒度峰值事实与分布统计分开标注 |
| 业务高峰 | 对已知高峰按更细 step 单独取证，不让粗 step 吞掉 burst |

若 `limit-points` 不足，不得静默截断或把点数过少的范围当完整历史。固定切片后，记录每片范围、step、预期点数、有效点数和错误；统计前按时间排序、去除重叠边界点，并保留原始查询证据。

## 容量与排名边界

Node 级 CPU/内存指标可能被发现，但只有在本次环境实际确认了 **allocatable、quota 或调度容量分母** 后才可计算余量。`node_cpu_seconds_total`、`node_memory_MemAvailable_bytes`、`node_memory_MemTotal_bytes` 本身不自动构成 Kubernetes 可调度容量合同；必须记录所使用分母的语义。

排名使用同一时间窗和同一聚合层级分别计算：实际 CPU、实际内存、CPU request、memory request、CPU limit、memory limit、使用率。`topk`/`bottomk` 不应把这些量混在同一表达式；CPU 使用最高也不等于最紧张。
