# BI 线上服务与 Pod 资源配置：两条 Trace 对照

> 取证日期：2026-09-23；时间均为北京时间（UTC+08:00）。数据来自生产环境 `foneshare` 的 CEP 网关日志、按 traceId 定位的应用日志，以及 `tke70-k8s1` 集群的 Prometheus / kube-state-metrics。本文是**资源配置盘点**，不是故障根因报告。

## 一、先看结论

| 对比项 | Trace A：`FSW-fktest7572.1001-01M3643C0TT5F4RQ1WPW439S6D` | Trace B：`FSW-664159.1047-01M3664VF0VV33RZ77ZF65WAPS` |
| --- | --- | --- |
| 请求时间 | 2026-09-23 11:14:12 | 2026-09-23 11:49:58—11:50:00 |
| 生产命名空间 | `foneshare-gray`（灰度） | `foneshare-vip`（VIP） |
| 集群 | `tke70-k8s1` | `tke70-k8s1` |
| 涉及服务 | `fs-bi-stat` | `fs-bi-crm-report-web`、`fs-bi-stat` |
| 实际记录该 trace 的 Pod | `fs-bi-stat-5d5759bd6c-w8zlr` | `fs-bi-crm-report-web-65995d975f-9ldvb`、`fs-bi-stat-bfc75496b-8zrtc`、`fs-bi-stat-bfc75496b-x5v4d` |
| `fs-bi-stat` 单 Pod 配额（request → limit） | CPU 1 → 4 核；内存 4482 MiB（约 4.38 GiB）→ 7 GiB | CPU 2 → 4 核；内存 7 → 7 GiB |
| CEP 状态 | 1 条网关记录，HTTP 200 | 4 条网关记录，均为 HTTP 200 |

**环境区别：**两条 trace 都在生产集群，但分别落入不同命名空间、不同 ReplicaSet 和不同资源规格。Trace B 还涉及另一个服务，不能把 Trace A 的灰度资源配置直接当作 VIP 资源配置。`FSW-fktest...` 中的 `fktest` 是请求标识的一部分；环境以 CEP 的服务地址、应用日志 `profile` 和集群指标为准。

## 二、Trace A：生产灰度 `fs-bi-stat`

### 1. 请求、服务和准确的 Pod

- 完整 traceId：`FSW-fktest7572.1001-01M3643C0TT5F4RQ1WPW439S6D`；企业 `ei=816324`，标识 `ea=fktest7572`。
- CEP 记录时间：`2026-09-23 11:14:12.366`；接口 `/FHH/EM1HBISTAT/fs-bi-stat/stat/data/query`；HTTP `200`；网关记录耗时 `2787 ms`。
- CEP 后端服务地址：`fs-bi-stat.foneshare-gray.lb-aurgynnp.tke70-k8s1.foneshare.cn:13484`。这是**服务/LB 地址**，不是直接的 Pod IP。
- 对同一 traceId 限定 `app=fs-bi-stat` 和 11:09—11:20 的应用日志，命中 Pod `fs-bi-stat-5d5759bd6c-w8zlr`，Pod IP `10.71.145.22`；日志分布于 11:14:12.370—11:14:15.150。该 Pod 位于节点 `10.71.240.146`。

### 2. 配额、副本和部署信息

| 配置项 | 单 Pod | 当次查看的 4 个副本合计 |
| --- | --- | --- |
| CPU request | 1 核 | 4 核 |
| CPU limit | 4 核 | 16 核 |
| 内存 request | 4699717632 字节 = 4482 MiB ≈ 4.38 GiB | 约 17.51 GiB |
| 内存 limit | 7516192768 字节 = 7 GiB | 28 GiB |

请求发生时 `w8zlr` Pod 的 request/limit 已用 **11:14:13 的历史指标**核对，与稍后的当前指标一致。查看时 Deployment `fs-bi-stat` 的期望副本数为 4，4 个 Pod 均 Ready，重启计数均为 0。监控显示容器基础镜像为 `harbor-cvm.foneshare.cn/base/fs-tomcat9:openjdk21-v260626`；**基础镜像标签不等于业务应用发布版本**。

| 同服务 Pod | Pod IP | 所在节点 | 在该 trace 的应用日志中命中 |
| --- | --- | --- | --- |
| `fs-bi-stat-5d5759bd6c-g8nbv` | `10.71.33.88` | `10.71.0.118` | 否 |
| `fs-bi-stat-5d5759bd6c-9s884` | `10.71.48.34` | `10.71.0.8` | 否 |
| `fs-bi-stat-5d5759bd6c-w8zlr` | `10.71.145.22` | `10.71.240.146` | **是** |
| `fs-bi-stat-5d5759bd6c-z2cp8` | `10.71.129.184` | `10.71.240.215` | 否 |

> `fs-bi-stat-transfer-*` 是名字相近的**另一应用**，不属于上述 `fs-bi-stat` 的 4 个副本，也没有计入资源合计。

### 3. 请求发生时的实际资源用量

11:14:13，命中的 `w8zlr` Pod 的 CPU **5 分钟平均使用约 0.294 核**；内存 working set **4907184128 字节，约 4.57 GiB**。内存工作集高于其内存 request（约 4.38 GiB），但低于 7 GiB limit；不能仅据此判定内存故障或推断请求耗时的原因。CPU 5 分钟平均值也不代表请求处理瞬间的峰值。

## 三、Trace B：生产 VIP 的两个 BI 服务

### 1. 网关请求与实际承载 Pod

完整 traceId：`FSW-664159.1047-01M3664VF0VV33RZ77ZF65WAPS`；企业 `ei=664159`，标识 `ea=664159`。CEP 查到 **4 条同 traceId 的网关记录**：

| CEP 时间 | 服务 / 接口 | 状态 | 耗时 |
| --- | --- | --- | --- |
| 11:49:58.204 | `fs-bi-crm-report-web`：`/FHH/EM1HBICRM/statEditController/getStatView` | 200 | 74 ms |
| 11:49:58.306 | `fs-bi-stat`：`/FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query` | 200 | 444 ms |
| 11:49:58.791 | `fs-bi-stat`：`/FHH/EM1HBISTAT/fs-bi-stat/stat/filters/getFiltersResult` | 200 | 137 ms |
| 11:49:58.976 | `fs-bi-stat`：`/FHH/EM1HBISTAT/fs-bi-stat/stat/data/query` | 200 | 1315 ms |

CEP 指向 `fs-bi-crm-report-web.foneshare-vip.lb-q3ar5jd3.tke70-k8s1.foneshare.cn:37139` 和 `fs-bi-stat.foneshare-vip.lb-q3ar5jd3.tke70-k8s1.foneshare.cn:64944`。这些也是**服务/LB 地址**；实际承载 Pod 由按服务名、traceId、11:46—11:52 窄时间窗查询的应用日志确认：

| 实际命中 Pod | 服务 | Pod IP | 所在节点 | 同 trace 日志时间段 |
| --- | --- | --- | --- | --- |
| `fs-bi-crm-report-web-65995d975f-9ldvb` | `fs-bi-crm-report-web` | `10.71.137.195` | `10.71.240.47` | 11:49:58.230—11:49:58.276 |
| `fs-bi-stat-bfc75496b-8zrtc` | `fs-bi-stat` | `10.71.139.52` | `10.71.241.83` | 11:49:58.308—11:50:00.287 |
| `fs-bi-stat-bfc75496b-x5v4d` | `fs-bi-stat` | `10.71.17.1` | `10.71.0.53` | 11:49:58.797—11:49:58.922 |

应用日志证明三个 Pod 都记录了该 trace；**不要将三条 `fs-bi-stat` 网关请求武断地逐条分配给特定 Pod**，目前的聚合证据只精确到 trace / Pod，未逐条按网关请求 ID 关联。

### 2. 单 Pod 配额与服务副本合计

| VIP 服务 | 期望副本 | 单 Pod CPU request / limit | 单 Pod 内存 request / limit | 全服务 CPU request / limit | 全服务内存 request / limit |
| --- | --- | --- | --- | --- | --- |
| `fs-bi-crm-report-web` | 2 | 1 / 4 核 | 8.875 / 8.875 GiB | 2 / 8 核 | 17.75 / 17.75 GiB |
| `fs-bi-stat` | 4 | 2 / 4 核 | 7 / 7 GiB | 8 / 16 核 | 28 / 28 GiB |
| **两服务合计** | **6** | — | — | **10 / 24 核** | **45.75 / 45.75 GiB** |

3 个实际承载 Pod 在 **11:49:59 的历史指标**中有对应的 request/limit，和稍后查询的同服务副本配置一致。上述合计是**这两个服务 Pod 的配额之和，不是集群可用容量或整机用量**。查询时 6 个 Pod 全部 Ready、重启计数均为 0；监控中的容器基础镜像均为 `harbor-cvm.foneshare.cn/base/fs-tomcat9:openjdk21`，不能据此推断业务应用的构建版本。

| VIP 服务其他副本（本 trace 未命中） | Pod IP | 所在节点 |
| --- | --- | --- |
| `fs-bi-crm-report-web-65995d975f-qwqs5` | `10.71.129.221` | `10.71.240.56` |
| `fs-bi-stat-bfc75496b-f6fq6` | `10.71.137.85` | `10.71.240.111` |
| `fs-bi-stat-bfc75496b-79hm2` | `10.71.142.234` | `10.71.241.152` |

### 3. 请求发生时的实际资源用量

以下为 11:49:59 的监控快照：CPU 是 5 分钟平均使用核数；内存是容器 working set，并非 request / limit。

| 实际承载 Pod | CPU 用量 | 内存 working set | 对应 Pod 的内存 limit |
| --- | --- | --- | --- |
| `fs-bi-crm-report-web-65995d975f-9ldvb` | 约 0.070 核 | 约 3.31 GiB | 8.875 GiB |
| `fs-bi-stat-bfc75496b-8zrtc` | 约 0.079 核 | 约 2.99 GiB | 7 GiB |
| `fs-bi-stat-bfc75496b-x5v4d` | 约 0.064 核 | 约 3.03 GiB | 7 GiB |

## 四、如何理解这些数字

1. **request / limit 与实际用量不同。**request 是 Pod 声明的资源需求，limit 是配置的资源上限；CPU 使用核数和内存 working set 来自监控采样，不能用单点采样代表高峰或整段请求的峰值。
2. **副本合计与真实请求落点不同。**资源合计覆盖同服务的所有副本；trace 到 Pod 的归属需要应用日志的 `pod` 字段，不可只凭 CEP 的服务地址或在任意副本中任选一个。
3. **请求成功不等于性能已被诊断。**这两条 trace 对应的 CEP 记录均为 HTTP 200；只盘点了服务、Pod、配额和采样用量，**没有做请求链路耗时、JVM、下游依赖或代码级根因分析**。两条请求属于不同企业/接口组合、发生时间和命名空间不同，2787 ms 与 1315 ms 不能直接用于灰度/VIP 性能优劣结论。
4. **配置范围。**当前确认了命名空间、服务、ReplicaSet/Pod、副本数、Pod IP/节点、基础镜像、CPU/内存 requests 与 limits、Ready/重启指标。未读取 Deployment 原始 YAML，因此不把 JVM 启动参数、业务镜像版本、HPA、调度约束、环境变量或节点总容量当作已核实配置。

## 五、可复查的原始证据

本报告的机器证据留存在 `bug-finder` 仓库下；路径以 `/Users/liushanshan/code/bug-finder/output/evidence/` 为根目录。`TRC-*` 为日志/历史取证，`K8S-*` 为 Pod 与配置快照，`MON-*` 为监控快照。JSON 的 Prometheus `effectiveTime` 给出求值时间，CEP 的 `stamp` / 应用日志的时间给出请求时间。

| 证据 | 路径（相对于上述证据根目录） | 可核对事项 |
| --- | --- | --- |
| 灰度 CEP | `20260923-trace-FSW-fktest7572/evidence/TRC-tracing-log-cep.json` | 网关时间、接口、状态、服务地址 |
| 灰度 trace→Pod | `20260923-trace-FSW-fktest7572/TRC-app-pod.json` | 应用日志定位 `w8zlr` |
| 灰度请求时配额 | `20260923-trace-FSW-fktest7572/TRC-pod-request-at-time.json`、`20260923-trace-FSW-fktest7572/TRC-pod-limit-at-time.json` | 11:14:13 的 request / limit |
| 灰度请求时用量 | `20260923-trace-FSW-fktest7572/TRC-pod-cpu-at-time.json`、`20260923-trace-FSW-fktest7572/TRC-pod-usage-at-time.json` | CPU / working set |
| 灰度副本、镜像、状态 | `20260923-trace-FSW-fktest7572/K8S-pod-info.json`、`20260923-trace-FSW-fktest7572/K8S-container-info.json`、`20260923-trace-FSW-fktest7572/K8S-readiness-replicas.json`、`20260923-trace-FSW-fktest7572/K8S-pod-status.json` | Pod/节点、副本、镜像、Ready、重启 |
| VIP CEP | `20260923-trace-FSW-664159-1047/evidence/TRC-tracing-log-cep.json` | 4 条网关记录和两个服务地址 |
| VIP trace→Pod | `20260923-trace-FSW-664159-1047/TRC-bi-crm-pod.json`、`20260923-trace-FSW-664159-1047/TRC-bi-stat-pod.json` | 实际命中的 3 个 Pod |
| VIP 请求时配额 | `20260923-trace-FSW-664159-1047/TRC-pod-requests-at-time.json`、`20260923-trace-FSW-664159-1047/TRC-pod-limits-at-time.json` | 11:49:59 的 request / limit |
| VIP 请求时用量 | `20260923-trace-FSW-664159-1047/TRC-pod-cpu-at-time.json`、`20260923-trace-FSW-664159-1047/TRC-pod-memory-at-time.json` | CPU / working set |
| VIP 全服务配置和状态 | `20260923-trace-FSW-664159-1047/K8S-pod-info.json`、`20260923-trace-FSW-664159-1047/K8S-container-info.json`、`20260923-trace-FSW-664159-1047/K8S-requests.json`、`20260923-trace-FSW-664159-1047/K8S-limits.json`、`20260923-trace-FSW-664159-1047/K8S-status.json` | 副本、节点、镜像、配额、Ready、重启 |

> 以上原始文件在 `bug-finder/output/evidence/`，未复制进本目录；如果原始证据目录被清理，本报告只能作为取证时点的记录，不能替代最新线上配置核查。
