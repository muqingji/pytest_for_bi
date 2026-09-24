# PromQL 生成规则

用于指导 AI 生成正确的 PromQL 查询。必须遵守以下规则，避免生成无效或过于宽泛的查询。

## 占位符约定

生成 PromQL 模板时使用以下占位符，不要使用真实名称：

| 占位符 | 含义 | 示例替换 |
| --- | --- | --- |
| `${k8s_cluster}` | K8S 集群名 | `tke70-k8s1` |
| `${app_name}` | 应用名（对应容器 `app` 标签或 JVM `app_name` 标签） | `fs-paas-app-udobj` |
| `${pod_name}` | 单个 Pod 名 | `fs-paas-app-udobj-6779db56d5-2jppf` |
| `${namespace}` | K8S namespace | `foneshare` |
| `${host_ip}` | K8S Node IP（Pod 的 `host_ip` 标签） | `10.71.240.236` |
| `${container}` | 容器名（通常等于 `${app_name}`） | `fs-paas-app-udobj` |
| `${cluster}` | 中间件集群名（如 RocketMQ `FS-MQ`） | `FS-MQ` |
| `${topic}` | RocketMQ topic 名 | `object-data` |
| `${group}` | RocketMQ consumer group 名 | `fs-sync-data-paas-object-consumer` |
| `${instance_name}` | 腾讯云实例名（如 RocketMQ `rocketmq-003`） | `rocketmq-003` |

## 标签选择

| 用途 | 标签 | 说明 |
| --- | --- | --- |
| 集群 | `k8s_cluster` | 多集群环境必须指定，避免跨集群聚合 |
| namespace | `namespace` | 优先使用；中间件也可能有 `cluster` |
| 环境 / profile | 优先按 `namespace`；只有发现 `profile` / `label_profile` 存在时才使用 |
| 应用 / 服务 | 容器指标优先用 `app`；JVM 指标用 `app_name`；Pod label 指标用 `label_app` |
| Pod IP | 常在 `kube_pod_info.pod_ip` |
| 宿主机 / 节点 IP | `host_ip`、`node`、node-exporter 的 `instance` |
| RocketMQ topic | `topic` |
| RocketMQ consumer group | `group` |

## 发现查询

PromQL 语法护栏：标签 matcher 必须写在 vector selector 的 `{}` 内；`count by (...)`、`sum by (...)` 后面只能接完整表达式，不能直接写 `label=...`。例如用 `{__name__=~".*tomcat.*",app_name="${app_name}"}`，不要写 `count by (__name__)(__name__=~".*tomcat.*", app_name="${app_name}")`。

先用小范围查询确认标签：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (k8s_cluster,namespace,app)(container_cpu_usage_seconds_total{app="${app_name}",container!="",container!="sandbox"})' \
 -j --limit-points 200
```

确认 Pod 与 Node：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'kube_pod_info{namespace="${namespace}"} * on(namespace,pod) group_left(label_app) kube_pod_labels{namespace="${namespace}",label_app="${app_name}"}' \
 -j --limit-points 100
```

确认指标存在性时优先查具体候选指标：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(container_memory_working_set_bytes{namespace="${namespace}",app="${app_name}",container!="",container!="sandbox"})' -j
```

## 常用 PromQL 模板

### Pod CPU 使用核数

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (namespace,pod)(rate(container_cpu_usage_seconds_total{namespace="${namespace}",app="${app_name}",container!="",container!="sandbox"}[1m]))' -j
```

### Pod 内存使用率

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (namespace,pod)(container_memory_working_set_bytes{namespace="${namespace}",app="${app_name}",container!="",container!="sandbox"}) / sum by (namespace,pod)(kube_pod_container_resource_limits{namespace="${namespace}",resource="memory",unit="byte",pod=~"${app_name}-.*"}) * 100' -j
```

如果分母为空，先确认资源指标命名：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)({__name__=~"kube_pod_container_resource_.*",namespace="${namespace}"})' -j
```

### TopN CPU Pod

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (namespace,pod)(rate(container_cpu_usage_seconds_total{namespace="${namespace}",container!="",container!="sandbox"}[1m])))' -j
```

### JVM heap 使用率

JVM 内存指标有两种命名方式，用 `or` 兼容查询：

```bash
# 先确认目标应用的 job
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job)(jvm_memory_used_bytes{app_name="${app_name}"} or jvm_memory_bytes_used{app_name="${app_name}"})' -j
```

```bash
# 兼容所有 exporter 类型的 heap 使用率
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (pod)(jvm_memory_used_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator",area="heap"} or jvm_memory_bytes_used{app_name="${app_name}",area="heap"}) / sum by (pod)(jvm_memory_max_bytes{app_name="${app_name}",job=~".*jvm-exporter|springboot-actuator",area="heap"} or jvm_memory_bytes_max{app_name="${app_name}",area="heap"}) * 100' -j
```

### RocketMQ 堆积 TopN

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (cluster,topic,group,countOfOnlineConsumers,msgModel)(rocketmq_group_diff{cluster="FS-MQ"}))' -j
```

## 反例

| 不要这样写 | 原因 | 改法 |
| --- | --- | --- |
| `up` 后直接全量分析 | target 太多，无法对应业务对象 | 加 `job` / `namespace` / `k8s_cluster` |
| `count by (__name__)({__name__=~".*"})` | 全局扫所有指标，容易超时或 502 | 按 exporter 和具体前缀分批 |
| `container_cpu_usage_seconds_total` 直接展示 | counter 原始值不可读 | 用 `rate(...[1m])` |
| `pod=~"${app_name}-.*"` 枚举 app | 会误匹配 `-rest`、`-02` 等前缀相近应用 | 用 `app="..."` 或 `label_app="..."` |
| 指标为空就说服务正常 | 可能是指标名、标签或 exporter 差异 | 先做存在性查询和标签发现 |

## 输出要求

回答用户时至少说明：

| 项 | 内容 |
| --- | --- |
| 查询对象 | 使用的 `k8s_cluster`、`namespace`、`app`、`pod` 等过滤条件 |
| 查询类型 | instant 或 range，range 要说明时间窗和 step |
| 执行的 PromQL | 给出关键 PromQL |
| 结果口径 | 单位、聚合维度、是否 topk/bottomk |
| 限制 | 查询为空、指标未采集、结果被截断或上游 502 |
