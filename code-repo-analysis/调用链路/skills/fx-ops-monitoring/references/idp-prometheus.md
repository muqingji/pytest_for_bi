# fx-ops idp prometheus — PromQL 查询入口

Prometheus 监控指标查询能力。用于查看物理机、虚拟机、Kubernetes 节点、Pod、容器、JVM、Tomcat 等运行指标。CLI 侧通过 `fx-ops idp --profile <profile> prometheus query` 执行 PromQL，Server 侧封装认证 + 审计后透传 Prometheus HTTP API。

与 `idp query` 完全独立：无 `--tenant-id`、无 `biz`、无 `catalog`，不走 SQL/MongoDB 执行链路。

## 先选指标文档

不要把所有 Prometheus reference 一次性加载。先根据用户问题选择最小文档：

| 场景 | 先读 |
| --- | --- |
| 不确定该用哪个指标、需要对齐 Grafana 变量 | idp-prometheus/index.md |
| 根据自然语言生成 PromQL、选择时间范围、避免全量扫 | idp-prometheus/promql-rules.md |
| 按 exporter / 采集源选择指标类别 | idp-prometheus/metric-sources.md |
| 按应用查有哪些 profile/namespace、哪些 Pod、当前有哪些指标族 | idp-prometheus/app-discovery.md |
| Pod 状态、request/limit、容器 CPU/内存/网络/磁盘、CPU throttling、重启 | idp-prometheus/k8s-pod.md |
| 物理机、虚拟机、Kubernetes Node 的 CPU/load/内存/磁盘/网络/socket | idp-prometheus/host-node.md |
| JVM 内存、GC、Class loading、线程、FD，Java 8/17/21/25 差异 | idp-prometheus/jvm.md |
| Tomcat HTTP 线程池、请求量、耗时、错误、连接 | idp-prometheus/tomcat.md |
| RocketMQ topic、consumer group、堆积、TPS、延迟、broker、exporter 采集状态（自建 `rocketmq_*`） | idp-prometheus/rocketmq.md |
| foneshare 腾讯云 RocketMQ、`qce_rocketmq_*`、tenant 4.x/5.x 指标含义与单位 | idp-prometheus/foneshare-tencent-rocketmq.md |
| foneshare 腾讯云公网负载均衡、CLB、`qce_lb_public_*` 指标含义与单位 | idp-prometheus/foneshare-public-clb.md |

## Grafana dashboard 线索

常用 Pod JVM dashboard 的变量与指标集合：

| 变量 | 示例 | 用途 |
| --- | --- | --- |
| `datasource` | `foneshare-prometheus` | Prometheus 数据源 |
| `k8s_cluster` | `tke70-k8s1` | 集群过滤 |
| `namespace` | `foneshare` | namespace 过滤 |
| `app` | `fs-paas-app-udobj` | workload/app 过滤 |
| `pod` | `fs-paas-app-udobj-6779db56d5-2jppf` | Pod 过滤 |
| `pod_ip` | `10.71.132.180` | Pod IP 过滤或展示 |
| `host_ip` | `10.71.240.236` | 所在节点过滤 |
| `interval` | `1m` | `rate()` / `increase()` 窗口 |

该 dashboard 可见分组包括：Pod 基本信息、CPU 使用情况、CPU 使用率增长、内存使用情况、容器内存拆解、JVM 内存拆解、容器 CPU/内存/网络/磁盘、CPU 受限情况、JVM heap/nonheap/pool、GC、Class loading、Threads Count、Tomcat HTTP 连接线程池、Open File Descriptors、重启次数、所在节点 CPU/load/内存/网络/磁盘 IO/socket。RocketMQ 通常是独立 dashboard 或补充指标集合，按 topic / consumer group / broker 维度查询。

## 命令

```bash
fx-ops idp --profile <profile> prometheus query --promql <expr> [flags]
```

## PromQL 输入源（三选一）

| Flag | 说明 |
| --- | --- |
| `--promql <expr>` | 直接传入 PromQL 表达式（1-8192 字符） |
| `--promql-file <path>` | 从文件读取（UTF-8，去首尾空白） |
| `--promql-from-stdin` | 从标准输入读取 |

三选一互斥；零个或多个同时出现均报参数错误。

## 查询模式

### Instant 查询（默认）

```bash
# 当前时刻求值
fx-ops idp --profile <profile> prometheus query --promql "up" -j

# 指定时间点
fx-ops idp --profile <profile> prometheus query --promql "up" --time "2026-05-16T10:00:00Z" -j
```

### Range 查询

```bash
fx-ops idp --profile <profile> prometheus query --promql 'rate(http_requests_total[5m])' \
 --start "2026-05-16T09:00:00Z" \
 --end "2026-05-16T10:00:00Z" \
 --step "15s" -j
```

`--start`、`--end`、`--step` 必须同时出现或同时省略。`--time` 与 `--start/--end/--step` 互斥。

## 参数

| Flag | 说明 |
| --- | --- |
| `--time <timestamp>` | Instant 求值时间（RFC 3339 或 Unix 秒） |
| `--start <timestamp>` | Range 起始时间 |
| `--end <timestamp>` | Range 结束时间 |
| `--step <duration>` | Range 步长（如 `15s`、`1m`、`5m`） |
| `--server-timeout <ms>` | 上游 Prometheus 超时（1-600000），默认 30000 |
| `--limit-points <n>` | 返回 Sample 数上限（1-100000），默认 11000 |

时间戳支持 RFC 3339（`2026-05-16T10:00:00Z`）和 Unix 秒（`1747380000`）。

## 输出

### Text 模式

```text
TIMESTAMP | VALUE | __name__ | instance | job
------------------------------------------------------
1747380000 | 1 | up | localhost:9090 | prometheus

1 samples (42ms)
```

- `vector` / `matrix`：表格，每行一个 sample，标签展开为列。
- `scalar` / `string`：单行 `TIMESTAMP | VALUE`。
- 页脚：`<N> samples (<took>ms)`。
- 截断时显示 `Results truncated` 告警。

### JSON 模式（`-j`）

标准信封，`data.result` 直接镜像 Prometheus 原生 `{ resultType, result }`：

```json
{
 "code": 0,
 "data": {
  "mode": "instant",
  "result": { "resultType": "vector", "result": [] },
  "effectiveServerTimeoutMs": 30000,
  "effectiveLimitPoints": 11000,
  "effectiveTime": "2026-05-16T10:00:00Z"
 }
}
```

## 快速示例

```bash
# 服务状态
fx-ops idp --profile <profile> prometheus query --promql 'up' -j

# Pod CPU 使用核数
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (namespace,pod)(rate(container_cpu_usage_seconds_total{namespace="foneshare",pod="fs-paas-app-udobj-6779db56d5-2jppf",container!="",container!="sandbox"}[1m]))' -j

# JVM 堆内存使用率
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (pod)(jvm_memory_used_bytes{area="heap",pod="fs-paas-app-udobj-6779db56d5-2jppf"}) / sum by (pod)(jvm_memory_max_bytes{area="heap",pod="fs-paas-app-udobj-6779db56d5-2jppf"}) * 100' -j

# Range 查询过去 30 分钟，1 分钟步长
fx-ops idp --profile <profile> prometheus query --promql \
 'rate(container_network_receive_bytes_total{namespace="foneshare",pod="fs-paas-app-udobj-6779db56d5-2jppf"}[1m])' \
 --start "$(date -u -v-30M +%Y-%m-%dT%H:%M:%SZ)" \
 --end "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
 --step "1m" -j
```

## 错误码

| HTTP | 错误码 | 说明 |
| --- | --- | --- |
| 400 | `promql_invalid_request` | 请求体校验失败 |
| 400 | `promql_invalid_range_params` | start/end/step 不完整 |
| 400 | `promql_conflicting_query_mode` | time 与 range 同时出现 |
| 403 | `prometheus_forbidden` | 无 prometheus 资源权限 |
| 500 | `promql_internal` | 配置异常或内部错误 |
| 502 | `promql_upstream_error` | 上游 Prometheus 返回错误 |
| 502 | `promql_upstream_unreachable` | 上游不可达（网络层） |
| 503 | `prometheus_not_configured` | app-config 无 prometheus section |
| 504 | `promql_upstream_timeout` | 上游超时 |

## 告警码

| 告警码 | 说明 |
| --- | --- |
| `promql_results_truncated` | Sample 数被截断 |
| `promql_param_defaulted` | 参数使用默认值 |
| `promql_param_clamped` | 参数被夹紧到合法范围 |
| `promql_upstream_warning` | Prometheus 上游警告 |

## 注意事项

- CLI 不直接连 Prometheus；所有请求经 IDP Server 中转。
- 不接受 `--tenant-id`（`-t`），传入即报错。
- `resultType` 可能为空 vector（`[]`），表示匹配但无数据。
- Range 查询数据量大时用 `--limit-points` 控制，避免响应过大。
- 不同 exporter 和 Spring Boot / Micrometer 版本的 metric 名称可能不同；先用子文档里的发现查询确认标签和指标名，再执行高成本 range 查询。
