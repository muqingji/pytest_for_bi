---
name: fx-ops-resource-recommend
description: 当用户要评估 Kubernetes requests/limits 是否合理、按历史 CPU/内存用量回收冗余、识别资源不足风险、做容量评估或资源使用 TopN/BottomN 时，基于已确认的 Prometheus 指标给出可追溯的资源优化建议，并在用户确认后生成 HTML 报告和分享链接。
---

# fx-ops-resource-recommend — Kubernetes 资源使用与推荐

## 定位与边界

本 skill 分析“实际资源使用是否与资源配置匹配、哪里可安全回收、哪里有短缺风险、应如何验证调整”。它是用户可直达的 L2 专项分析能力，不修改 Deployment、HPA、VPA、LimitRange、ResourceQuota 或集群配置。

它不是普通监控读数的复述：结论必须同时说明 CPU、内存、requests、limits、实例数、历史覆盖、峰值、假设和风险。单个瞬时值或均值不能单独推出资源调整或副本扩缩结论。

| 用户意图 | 首跳 |
| --- | --- |
| 看当前 CPU/内存、曲线、PromQL 或 Grafana 看板 | 监控指标分析能力 |
| requests/limits 是否合理、回收冗余、短缺风险、容量规划、TopN/BottomN、资源优化建议 | 本 skill |
| traceId/reqId/错误码、故障 RCA | 故障 RCA 主控 |
| 直接修改 Deployment/HPA/VPA 或资源配额 | Kubernetes 应用管理能力；本 skill 只可提供变更前建议 |

## 必要上下文

查询前一次性收集以下信息；没有明确授权的默认值时，不用猜测替代。

| 上下文 | 要求 |
| --- | --- |
| 环境与 Kubernetes 集群 | `profile` 和真实 `k8s_cluster` 分开记录；profile 由集群确认，不能由 namespace 推断 |
| namespace | 必填，独立于 profile |
| 服务范围 | workload/app、Deployment 或明确 Pod 集合；说明是否纳入 sidecar |
| 时间窗口 | 精确起止时间；算法默认目标是 14 天，最低可评估历史是 7 天 |
| 目标 | 回收、短缺、配置匹配、排名、容量或组合目标 |
| 约束 | 服务高峰时段、SLO、HPA/VPA、发布/配置所有权、可接受的变更窗口（未知必须记录） |

若环境、集群、namespace、服务范围或窗口缺失，返回 `blocked` 并列出缺口；不要进行宽范围 PromQL 扫描。用户只给相对时间时，确认授权后记录解析出的 UTC 起止时间。

## 范围归一与知识库优先级

自然语言中的集群、环境、命名空间和服务名必须先归一为独立字段，不能把 namespace 当作 `profile`，也不能用口语环境名直接执行查询。复用 fx-ops 的上下文归一原则与监控能力的 profile 合同，按以下优先级确定映射；每一步都将采用值、证据和未采用的冲突值写入证据信封：

1. **已确认的精确 `k8s_cluster`**：先匹配监控能力维护的已知集群前缀（如主站 `tke70-k8s*`、`tke60-k8s*`、`k8s0`、`k8s1`，以及已登记专属云前缀）；这是 metrics `profile` 的首要依据。
2. **已确认的环境锚点**：当用户提供 source ID、租户 VPC/domain、已登记 profile 或云环境口语别名时，按 fx-ops 的 cloud registry 归一为标准 `profile`；它只补全环境，不能虚构缺失的集群。
3. **显式 namespace、workload/service 和容器范围**：只作为 Prometheus matcher 与报告 scope；namespace 不反推 profile，服务名不做跨集群模糊匹配。
4. **受控的有限发现**：发现不是补收 profile 或基础范围的方式。**执行任何 discovery PromQL 前，必须已经确认 metrics `profile`，并且已确认至少一个 `k8s_cluster`、`namespace`，或已发现的 application/workload/pod selector；缺少 profile 或缺少这些 scope 时一律返回 `blocked`，即使用户授权探测也不能豁免。**只有在这些前置条件满足、用户范围可审阅且未知点仅为覆盖/标签时才可发现。只能使用已经发现的标签，不能臆造 `app` 等 matcher；例如 `count by (k8s_cluster)(up{namespace="<confirmed-namespace>"})`。发现只确认候选，不得扩大为生产集群扫描或把空结果解释为正常。

精确集群与环境映射冲突、注册表返回一对多、前缀未登记，或 profile 覆盖未确认时，立即 `blocked` 并列出候选和需要用户确认的字段。禁止为了继续分析而尝试猜测的生产 profile、默认 namespace、服务或集群路由。

## 执行路径

1. **归一与映射**：记录用户原话、标准 `k8s_cluster`/`profile`/namespace/service/container scope、知识库依据和冲突处理；必要时仅执行上述受控有限发现。
2. **发现**：在已确认 profile 与范围内小范围确认 cluster 覆盖、Pod/容器标签和 request/limit 指标命名。
3. **取证**：在同一筛选条件收集 CPU、内存、request、limit、Pod 状态/启动时间/重启、throttling、实例分布和时间序列。
4. **质量门**：计算历史有效运行时长、样本覆盖、连续缺口、部署/重启扰动和业务峰值覆盖；未通过时降级，不给确定性回收数值。
5. **计算与判定**：按 `references/right-sizing-algorithm.md` 计算分位数、可配置冗余、量化粒度和分阶段调整；CPU、内存与副本建议分别判定。
6. **输出**：分别报告冗余回收、资源不足、配置失配、使用量排名和容量边界；每条建议附证据、假设、验证与回滚条件。

详情只加载本次路径所需的本地 reference，不无差别加载其他监控面板。

## 已确认的数据与查询纪律

查询只使用已确认的 Kubernetes Prometheus 指标与只读入口；完整指标、标签、PromQL 和时间序列采集规则见 `references/prometheus-query-contract.md`。

```bash
fx-ops idp --profile <metrics_profile> prometheus query --promql '<expr>' \
  --start '<start>' --end '<end>' --step '<step>' --limit-points <n> -j
```

最小事实集：

- CPU：`rate(container_cpu_usage_seconds_total[1m])`，单位 core；
- 内存：`container_memory_working_set_bytes`，单位 byte；
- request/limit：`kube_pod_container_resource_requests` 和 `kube_pod_container_resource_limits`，分别使用 `resource` 与 `unit` 标签；
- 风险辅助：已确认的 CPU throttling、`kube_pod_info`、Pod phase/start/restart 指标；
- 容器查询排除 `container=""` 与 `container="sandbox"`；sidecar 的包含/排除必须写入证据。

request/limit 指标可能是旧版独立 CPU/内存命名。先在 namespace 范围发现指标与标签，再使用已确认的兼容模板；禁止靠记忆猜标签或指标。没有已经确认的 Node allocatable、quota 或调度容量分母时，只能做 Pod 级配置/使用分析，不能计算精确剩余集群容量。

## 历史算法与安全门

`references/right-sizing-algorithm.md` 是数值建议的唯一算法合同。核心原则：

- 默认以 **14 天**、至少两个日周期为标准分析窗；少于 **7 天**、覆盖不足或没有峰值覆盖时，只输出观察/补采计划，不输出确定性降配数值；28 天且覆盖多个周期可提高置信度。
- 使用 P50、P95、P99、受保护峰值和 Pod 离散度，不以平均值、最大单点或单一 Pod 代替历史分布。
- CPU 与内存分别计算；推荐 request/limit 使用公开的可调冗余和量化单位，默认值是保守起点而不是组织政策。
- OOM/重启风险、持续 CPU throttling、明显缺口、峰值未知、sidecar 范围不清、HPA/VPA/发布所有权不清或配置数据不完整时，阻断或降级回收建议。
- 资源使用率不足以单独推出“增加/减少副本”；该建议还需要吞吐、延迟、错误或 SLO 证据。没有这些事实时仅标记容量风险假设。

现有巡检告警阈值与本 skill 的建议冗余不是同一概念；不得把巡检黄红阈值默认为资源推荐目标。

## 缺失、失败与降级

| 情况 | 必须行为 |
| --- | --- |
| profile、标签或指标覆盖不确定 | 先确认 profile 与 cluster/namespace/已发现应用、workload 或 Pod selector；这些前置范围未齐时返回 `blocked`，齐备后才可做受控小范围发现；空结果不等同服务正常 |
| 指标缺失 | 仅尝试已确认的旧/新命名兼容路径；仍缺失则标记该维度不可用 |
| 查询失败 | 保留成功维度和简化错误原因；缩小范围后有限复核，仍失败返回 `partial`/`error` |
| 只有短期/单点数据 | 返回 observation 或 `insufficient evidence`，不产生回收或副本变更数值 |
| 没有容量分母 | 只说明 Pod 级事实与待补证据，不声称剩余容量 |

覆盖率、置信度和证据信封字段见 `references/evidence-and-confidence.md`。不得用“未发现异常”掩盖任一缺失维度。

## 输出合同

最终 Markdown 依次包含：

1. 范围与映射口径（用户原始范围、环境/profile、cluster、namespace、服务、容器/sidecar 范围、采用的知识库依据与任何受控发现）；
2. 查询与时间口径（metrics datasource、精确 UTC 起止时间、step、单位、已确认的指标/标签）；
3. 数据质量与证据（覆盖率、缺口、重启/发布扰动、成功/失败查询）；
4. CPU/内存和 requests/limits 摘要（P50/P95/P99/受保护峰值、实例分布）；
5. 冗余回收候选、资源不足风险、配置失配与使用量排名（四类不可混写）；
6. 每项建议的算法输入、可配置冗余、量化、置信度、验证和回滚；
7. 容量边界、未决项和不可得结论。

结论级别只可为 `confirmed observation`、`supported recommendation`、`validation-only recommendation` 或 `insufficient evidence`。上游回抛使用 `status: completed|partial|empty|error|blocked`、`findings`、`evidence_files`、`confidence`、`need_further`；能力名称而非兄弟 skill 内部路径写入 `need_further`。

## HTML 报告与分享门

完成 Markdown 分析后，明确询问：**“是否要根据这份分析生成 HTML 页面和分享链接？”** 默认不生成、不上传。HTML 是用户明确确认后的可选读者交付，不能因为用户最初提到“报告”或“分享”而跳过该确认。

用户确认后才由 AI 基于冻结的真实证据直接撰写一个明确命名的 HTML 到仓内 `output/` 或 `tmp/`；不得用 Python、Node、模板 renderer 或字符串拼接器生成读者可见的 HTML/Markdown 正文。HTML 必须使用 `references/report-and-share.md` 的深色表格、可访问交互、转义、评分、披露和安全合同。再将**该明确文件**委托受控分享能力完成 plan-first 扫描、授权检查和上传；不得扫描目录猜测最新文件。

上传成功才返回真实 URL、过期信息和审计结果；用户拒绝时返回 `executed: false`；上传失败时如实给出简化原因和 `executed: false`，不猜链接、不把本地路径当公网链接，也不在报告或审计中回显敏感数据。完整门禁见 `references/report-and-share.md`。

## Reference 导航

| 文档 | 何时读取 |
| --- | --- |
| `references/prometheus-query-contract.md` | 发现指标、拼接 PromQL、做范围采集或容量边界判断时 |
| `references/right-sizing-algorithm.md` | 需要历史统计、数值建议、冗余、回收/短缺判定或副本风险判断时 |
| `references/evidence-and-confidence.md` | 记录证据、评估覆盖/置信度、处理缺失或失败时 |
| `references/report-and-share.md` | 输出 Markdown、生成 HTML 或请求分享时 |

## 自检

- [ ] 已记录集群、namespace、服务范围、窗口、容器/sidecar 范围和指标单位。
- [ ] CPU、内存、request、limit、实例数分别查询或诚实标记缺失。
- [ ] 已通过历史运行、覆盖、峰值、稳定性和配置所有权门；没有将单点或平均值当调整结论。
- [ ] 已将巡检告警、推荐冗余、SLO 目标和未知约束分开。
- [ ] 每项数值建议都有算法输入、假设、量化、验证与回滚；副本建议没有脱离负载/SLO证据。
- [ ] 已执行 HTML/分享确认门，未经确认未生成或上传分享物。
