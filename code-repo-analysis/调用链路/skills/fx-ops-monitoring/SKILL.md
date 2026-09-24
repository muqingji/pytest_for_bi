---
name: fx-ops-monitoring
description: 通过 fx-ops 查询 Prometheus/PromQL 指标解释资源与运行时体征（无故障语境可直达）。典型触发：CPU 高/飙升/throttling、内存高/OOM/容器重启、磁盘满/IO 高、网络延迟/丢包/流量异常、foneshare 公网 LB/CLB 连接数/限速/VIP 使用率、Node 负载高、JVM GC 频繁/Heap 持续上涨/线程泄漏/FD 泄漏、Tomcat 线程池满/请求慢/错误率高、RocketMQ 堆积/消费延迟/TPS 异常、Kafka 消费组 lag/kafka_consumergroup_lag/kafka-exporter、foneshare 腾讯云 RocketMQ/qce_rocketmq/tenant 4.x/5.x、PostgreSQL/MongoDB/Redis/ES/ClickHouse 等中间件健康度异常、QPS 突增突降/流量波动对比、吵闹邻居排查、按应用发现 Pod/namespace/指标族；亦触发于无故障语境的 Grafana URL（/d/<uid>）、dashboard UID、查看板/搜看板、datasource/folder 只读、按看板分析运行时体征。按 Pod→JVM→Tomcat→节点→中间件顺序做 RED+USE 分析；本层只做指标/看板与体征解释，MQ 消费链路归因与批量健康巡检判定不在本层。
---

# fx-ops-monitoring — 运行时体征解释器

## 全局约定

遵从 fx-ops 总控的全局约定。本地额外约定:
- 命令：`fx-ops idp --profile <profile> prometheus query --promql <expr> [flags] -j`
- 与 `idp query` 完全独立：无 `--tenant-id`、无 `biz`、无 `catalog`

### Profile 选择规则（必读）

Prometheus 查询的 `--profile` 由目标 K8S 集群决定，**不可默认省略**。不同 `--profile` 连接不同的 IDP Server，每个 Server 背后是不同的 Prometheus 实例，采集不同的集群。

| 集群名前缀 | profile | 说明 |
|-----------|---------|------|
| `tke70-k8s*`、`tke60-k8s*`、`k8s0`、`k8s1` | `foneshare`（默认） | 主站（纷享-腾讯云） |
| `hsyk-k8s*` | `hsyk` | 专属云-何氏眼科 |
| `sbt-*` | `sbt` | 专属云-双胞胎 |
| `mengniu-*` | `mengniu` | 专属云-蒙牛 |
| 其它专属云 | `cloud-registry.md` 中对应的 profile | 见 [cloud-registry.md](../../contracts/cloud-registry.md) |

**强制流程**：
1. 根据已知的 K8S 集群名/namespace 查上表确定 `--profile`
2. 若不确定集群属于哪个 profile，先用默认 profile 执行 `count by (k8s_cluster)(up)` 探测
3. 若默认 profile 返回空或未覆盖目标集群，按集群名前缀切换 profile 重试
4. **禁止**在未确认 profile 覆盖目标集群的情况下直接跑 PromQL——不同 profile 的 Prometheus 数据完全隔离，查错 profile 会返回空结果导致误判"无数据"

典型错误：用户告警来自 `hsyk-k8s1/hsyk-public-prod`，但 PromQL 用了默认 `--profile foneshare` → 返回空 → 误判为"Prometheus 不覆盖此集群"。正确做法：`--profile hsyk`。

## 核心定位

`fx-ops-monitoring` 不只是 Prometheus 导航器，而是用运行时指标解释“系统当时处于什么状态、这些体征是否足以解释故障”的诊断器。

适合本 skill 的问题：
- CPU、内存、GC、线程、Pod 重启、网络、磁盘、Tomcat 线程池、中间件健康度异常
- 用户明确要看指标、波动、拐点、资源耗尽、运行时瓶颈

不适合本 skill 单独闭环的问题：
- 只有单次请求失败，需要定位首发异常或调用链
- 主要怀疑脏数据、Schema 变更、分片路由、下游写入延迟
- 需要把变更、错误、资源、流量放进统一时间线做因果分析

## 观察框架：RED + USE

监控分析时默认同时带着两套视角：

- **RED**：Rate、Errors、Duration
- 看请求量是否异常
- 看错误率是否抬升
- 看延迟是否恶化
- **USE**：Utilization、Saturation、Errors
- 看资源是否被打满
- 看排队/堆积/线程池是否饱和
- 看底层组件是否直接报错

结论不能只说“CPU 高”，而要说明它是在 RED 还是 USE 视角下如何影响业务。

## 路由

| 场景 | 先读 |
| --- | --- |
| 不确定该用哪个指标、需要对齐 Prometheus 变量 | [idp-prometheus/index.md](references/idp-prometheus/index.md) |
| 根据自然语言生成 PromQL、选择时间范围 | [idp-prometheus/promql-rules.md](references/idp-prometheus/promql-rules.md) |
| 按 exporter / 采集源选择指标类别 | [idp-prometheus/metric-sources.md](references/idp-prometheus/metric-sources.md) |
| 按应用查有哪些 profile/namespace、哪些 Pod | [idp-prometheus/app-discovery.md](references/idp-prometheus/app-discovery.md) |
| Pod CPU/内存/网络/磁盘、CPU throttling、重启 | [idp-prometheus/k8s-pod.md](references/idp-prometheus/k8s-pod.md) |
| 物理机、虚拟机、Node 的 CPU/load/内存/磁盘 | [idp-prometheus/host-node.md](references/idp-prometheus/host-node.md) |
| JVM 内存、GC、线程、FD | [idp-prometheus/jvm.md](references/idp-prometheus/jvm.md) |
| Tomcat HTTP 线程池、请求量、耗时 | [idp-prometheus/tomcat.md](references/idp-prometheus/tomcat.md) |
| RocketMQ topic/consumer/堆积/TPS（自建 exporter `rocketmq_*`） | [idp-prometheus/rocketmq.md](references/idp-prometheus/rocketmq.md) |
| Kafka 消费组 lag（`kafka_consumergroup_lag` / kafka-exporter） | [idp-prometheus/kafka.md](references/idp-prometheus/kafka.md) |
| foneshare 腾讯云 RocketMQ / `qce_rocketmq_*` / tenant 4.x/5.x | [idp-prometheus/foneshare-tencent-rocketmq.md](references/idp-prometheus/foneshare-tencent-rocketmq.md) |
| foneshare 腾讯云公网 LB / CLB / `qce_lb_public_*` | [idp-prometheus/foneshare-public-clb.md](references/idp-prometheus/foneshare-public-clb.md) |
| PostgreSQL/MongoDB/Redis/ES/CH 健康度 | [idp-prometheus/middleware.md](references/idp-prometheus/middleware.md) |
| Grafana URL / UID / 搜看板 / datasource / folder | [idp-grafana/index.md](references/idp-grafana/index.md)（场景实测见 [scenarios.md](references/idp-grafana/scenarios.md)） |

## Grafana URL 编排（摘要）

用户贴 Grafana 看板链接（`/d/<uid>`）、给 UID、要搜/列看板，或只读查 datasource/folder 时：先读 [idp-grafana/index.md](references/idp-grafana/index.md) 走编排。要点：

- **环境约束（对齐 oncall）**：Grafana **IDP 代理**仅 `firstshare` / `foneshare`；专属云 profile 禁止调 `idp grafana`。但 **foneshare 看板常带 `env` 等变量可选专属云**，经主站 DS 查专属云数据——出数用 `foneshare` + 展开 `var-env=…`（选项见 [env-var-options.md](references/idp-grafana/env-var-options.md)）
- **两类 profile**：`grafana_profile`（仅 firstshare/foneshare）取定义/grafana query；直连 `idp prometheus` 时 `metrics_profile` 仍可专属云；二者可以不同
- **焦点面板**：首轮只取 5–8 个相关面板（`viewPanel` 优先；否则按 Pod→JVM→Tomcat→Node→中间件）
- **按 DS 分流**：优先 `grafana query --dashboard-uid --panel-id --var …`；失败时 prometheus 面板降级 `idp prometheus`，ClickHouse/ES 再委托 query（见 `references/idp-grafana/scenarios.md`）
- **可降级**：专属云误调 grafana → 改走 foneshare/firstshare 取定义；变量未展开 → 读 `grafana_template_vars_unresolved`；firstshare/foneshare 真故障或 CLI 不可用 → 声明「未加载看板定义」，用 `idp-prometheus/*` 模板按 `metrics_profile` 查数
- **无客户端 token**：地址与只读凭据仅在 IDP；不引导用户配置本机 Grafana 凭据
- **查数**：优先 `fx-ops idp --profile <grafana_profile> grafana query …`；降级 `prometheus query`（可用 `metrics_profile`）或委托 fx-ops-query

细节、CLI、URL 解析与错误降级见同目录 `cli.md` / `url-parse.md` / `errors-and-degrade.md`。

## 查询流程

> **同一层复用原则**：同一次诊断会话中，对同一观察层（Pod / JVM / Tomcat / K8S 节点 / 中间件）的参考文档只需在**首次查询或查询返回空/报错时**读取，后续查询直接复用已获取的指标名、标签和 PromQL 模板，无需重复读文档。

1. **先读参考文档**：根据场景从路由表找到对应文档并读取，文档中已包含指标名、标签过滤、PromQL 模板，可直接用于编写查询。**禁止凭记忆猜指标名**（不同 exporter / 版本差异大）。
2. **查询返回空或报错时回退发现**：指标查不到数据或报 unknown metric 时，回到路由表找到对应场景重新确认指标名和标签；仍找不到时读 `index.md` 或 `metric-sources.md` 做更广泛的指标发现。
3. **静默查询确认**：发送 PromQL 前内部确认指标文档、观察层、标签过滤、时间窗和 step；低风险通过时不输出确认。只有查询范围过大、标签缺失、指标不确定或降级发现时，才输出单行风险说明（禁止多行输出）：
  ```
  [promql-risk] 文档: <doc_name.md> | 观察层: <layer> | 指标/标签: <metric_or_tag> | 时间窗: --start <start> --end <end> --step <step> | reason: <risk_or_degrade>
  ```
4. **执行查询**：确认后执行 PromQL。

## 固定观察顺序

标签过滤约定：
- 容器指标（CPU/内存/网络/磁盘）用 `app="${app_name}"` 或 `container="${app_name}"`
- JVM 指标用 `app_name="${app_name}"`，job 为 `=~".*jvm-exporter|springboot-actuator"`
- `host_ip` 是 Pod 所在 K8S 节点的 IP，用于跳转到 node-exporter 指标
- JVM 指标按 job 分三类，指标名和标签差异大，排查前必须先确认 job，详见 references/idp-prometheus/jvm.md

1. **Pod**
- 先确认对象和范围：应用名、namespace、profile、Pod 列表是否正确；信息不全时先读 [idp-prometheus/app-discovery.md](references/idp-prometheus/app-discovery.md)
- 看 `up`、重启次数、CPU throttling、内存趋势、磁盘/网络异常，先判断是不是基础资源层问题
2. **JVM**
- 看 Heap、GC、线程、FD、类加载等，判断是否有泄漏、频繁 Full GC、线程耗尽
3. **Tomcat**
- 看请求量、错误率、线程池占用、活跃线程、耗时分位，判断是否为应用入口层拥塞或超时
4. **K8S 节点**
- 先确认目标 Pod 所在 Node：通过 `host_ip` 或 `node` 标签定位
- 看 Node CPU 使用率 / iowait / steal、load / CPU 核数比、内存压力、磁盘 IO util 和耗时、网络丢包
- 核心目的：排除 **吵闹邻居**
- 典型场景：一个节点上部署 10+ 应用，某个应用的批量写入或大查询把磁盘 IO util 打满，同节点其他应用的响应时间集体恶化
5. **中间件**
- 只有怀疑数据库、缓存、消息队列、搜索组件时，再看 PostgreSQL/MongoDB/Redis/ES/CH、RocketMQ 等指标

这五层顺序默认不要颠倒。除非用户已经明确指出某个中间件故障，否则不要一开始就钻数据库或 MQ 指标。

## 首轮观察目标

首轮只需要回答三件事：
- 指标异常是否真实存在，还是感知偏差
- 异常主要落在 Pod / JVM / Tomcat / K8S 节点 / 中间件 哪一层
- 这些体征能否直接解释用户看到的业务现象

如果只能证明“系统有点吃紧”，但解释不了“为什么这次请求失败”，就不算闭环。

## CPU 根因闭环门禁

CPU throttling 是资源层症状，不等于业务代码或某一次查询就是根因。看到高日志量、某个函数名或单次慢查询时，只能登记为候选假设，不能直接提交代码改动或根因结论。

CPU 归因至少需要将以下信号在同一故障窗口对齐，并保留排除项：

- **资源**：每个 Pod 的 CPU 使用/limit、throttling、GC、线程数，并与同 Deployment 其它 Pod 对比。
- **负载**：RocketMQ/HTTP 消费 TPS、并发线程、消息对象或请求类型分布，确认是否存在流量/消费尖峰。
- **耗时机制**：慢调用或 profiler/线程 dump 能指出具体热点（例如 `findByQueryWithContext`、`findObject`、公式计算或 ES 查询）及其耗时占比；单纯日志条数不具备该证明力。
- **依赖排除**：数据库、ES、节点 iowait/磁盘 IO、网络和 K8s 事件，区分业务计算饱和、下游等待和节点争用。

只有当热点耗时/并发与 CPU 拐点在时间和量级上吻合，且替代假设已有反证时，才允许输出“服务自身计算负载导致 CPU 饱和”的机制级结论。否则输出 `partial`/`hypothesis`，明确下一跳（通常是 `fx-ops-query`、`fx-ops-tracing` 或 `fx-ops-pyroscope`），禁止把缓存、日志降级等优化建议表述为已验证根因。

## 命令

```bash
# Instant 查询（必须带过滤标签，避免裸查 up 等全量指标导致返回数据爆炸）
fx-ops idp --profile <profile> prometheus query --promql 'up{job=~".*my-app.*"}' -j

# Range 查询
fx-ops idp --profile <profile> prometheus query --promql '<expr>' \
 --start "2026-05-16T09:00:00Z" --end "2026-05-16T10:00:00Z" --step "1m" -j
```

详细参数和输出格式见 references/idp-prometheus.md。

## 注意事项

- `--start`、`--end`、`--step` 必须同时出现或同时省略
- Range 查询数据量大时用 `--limit-points` 控制
- 不同 exporter 和 Spring Boot 版本的 metric 名称可能不同；先用子文档的发现查询确认

## 输出回抛

完成本领域查询后，按 fx-ops 总控回抛协议返回:
- status: completed / partial / empty / error
- findings: 运行时体征分析结果（RED+USE）；Grafana 路径须写明是否已加载看板定义、`grafana_profile` / `metrics_profile`、焦点面板数
- evidence_files: 已落盘的证据文件列表
- confidence: high / medium / low
- need_further: 是否需要总控继续分发（如需要单链路追踪、需要时间线聚合、需要代码级分析等，仅说明能力类型）

## 输出要求

最终输出必须包含：
- 观察时间窗口、目标应用/Pod/namespace
- 若走 Grafana URL/看板路径：是否已加载看板定义、`grafana_profile` / `metrics_profile`、焦点面板数量
- RED 视角结论：请求量、错误率、时延是否异常
- USE 视角结论：哪类资源被打满、哪里出现饱和、是否伴随系统级错误
- 按 Pod → JVM → Tomcat → K8S 节点 → 中间件 的观察结果摘要
- 是否足以解释业务现象；如果不足，下一跳应该去 `fx-ops-tracing`、`fx-ops-query` 还是 `fx-ops-timeline`

证据至少应落盘：
- 关键 PromQL 查询结果 → `evidence_dir/MON-prometheus-metrics.json`，格式：`{"meta":{"source":"fx-ops-monitoring","app":"<APP>","time_window":"<START>~<END>","time":"<ISO_TIMESTAMP>"},"data":{"queries":[{"promql":"...","series":[...]}]}}`
- Grafana 路径（按需）：`MON-grafana-url-parsed`、`MON-grafana-dashboard`、`MON-grafana-datasource`、`MON-grafana-folder`（前缀约定见 [idp-grafana/index.md](references/idp-grafana/index.md)）
- 关键拐点截图或导出的时序数据
- 一份监控结论摘要，说明异常层级和升级建议

## 被调度时的约定

当本 skill 被 fx-ops 编排主控以 sub-agent 方式调度时，遵循以下输入/输出契约：

### 调用方传入

| 参数 | 说明 |
| --- | --- |
| `app` | 目标应用名（必填） |
| `env` | 环境标识，如 prod / staging（必填） |
| `time_window` | 观察时间窗口，含 start / end（必填） |
| `symptom_hints` | 症状提示，如 "CPU 飙升"、"请求变慢"、"OOM 重启" 等（可选，用于缩小首轮观察范围） |
| `grafana_url` | 可选；用户或主控传入的 Grafana 看板 URL |

### 本 skill 输出

- **RED + USE 分析**：按 Rate/Errors/Duration 和 Utilization/Saturation/Errors 双视角给出结构化结论
- **资源异常摘要**：异常落在哪一层（Pod / JVM / Tomcat / K8S 节点 / 中间件）、严重程度、是否足以解释业务现象
- **Grafana 路径附加**：是否已加载看板定义、`grafana_profile` / `metrics_profile`、焦点面板数（未走看板路径可省略）

### 证据落盘

- 被调度时：证据保存到调用方指定的 `evidence_dir`，文件命名遵循调用方约定
- 独立使用时：证据保存到 `output/evidence/<YYYYMMDD-HHMMSS>-<short-topic>-monitoring/`
