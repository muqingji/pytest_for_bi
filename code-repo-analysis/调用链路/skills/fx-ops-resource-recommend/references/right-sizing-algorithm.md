# 历史资源规格建议算法

## 适用范围与非目标

本合同将**已确认可用**的 Kubernetes Prometheus 时间序列转换为可复核的 CPU/内存配置建议。它用于说明数据、计算、冗余、风险门和置信度，不能替代服务 SLO、容量审批或 Kubernetes 变更流程。

- Python（若调用）只能标准化查询结果、计算统计量和写 JSON 证据；AI 决定是否查询、如何解释、是否给出建议并撰写 Markdown/HTML。
- 本合同不把当前瞬时值、简单平均值、巡检告警阈值或 request 总和当成确定性的资源调整依据。
- 所有数值都先是**建议参数**；HPA/VPA、服务所有权或变更策略未知时，只能给 `validation-only recommendation`，不能把数值包装成可直接执行的变更。

## 1. 输入与统一粒度

每个分析对象至少要有：目标容器集合、服务/workload、Pod、namespace、cluster、时间窗口、采样 step、sidecar 范围、CPU/内存使用序列、CPU/内存 request/limit、运行 Pod 数，以及重启/throttling 事实。

同一建议不得混合不同过滤条件、不同 container 范围或不同采样粒度。所有输入和比较都必须先从 `(pod, container)` 行开始；使用量、request、limit 及 sidecar 纳入范围必须在同一行集合中保持一致，再按建议对象聚合：

```text
U_cpu[pod,container](t) = sum(rate(container_cpu_usage_seconds_total[5m]))
U_mem[pod,container](t) = sum(container_memory_working_set_bytes)
R_resource[pod,container] = effective request for the same row
L_resource[pod,container] = effective limit for the same row

U_resource[workload,all-containers](t) =
  sum over the workload's (pod, container) rows U_resource[pod,container](t)
```

最后一项是单独命名的 workload 全容器汇总，只能在 `(pod, container)` 行已经建立并完成对齐后计算；它不得回填或复用为任何 per-container 报告行。CPU 单位为 core，内存单位为 byte；展示可以换成 mCPU、MiB/GiB，但计算和证据必须保留原始单位。聚合时排除空容器和 `sandbox`；是否包含 sidecar 是固定输入，不能在使用量和 request/limit 之间改变。

`R_resource[pod,container]`、`L_resource[pod,container]` 分别是同一 `(pod, container)` 行的有效 request 与 limit。若容器没有 request/limit、不同 Pod 的配置不一致或配置序列无法按行对齐，先报告配置不一致；不产生“workload 统一规格”数值。

## 2. 历史有效性与峰值覆盖

### 2.1 默认窗口和证据层级

默认目标窗口是 **14 个自然日**。它不是业务规律，而是保守、可替换的起点；用户/项目已有峰谷周期、账期、促销期或 SLO 时，应优先采用该事实并记录来源。

| 级别 | 最短观察 | 质量条件 | 可交付结论 |
| --- | --- | --- | --- |
| `insufficient` | 少于 7 天，或工作负载有效运行少于 7 天 | 任意关键指标缺失、覆盖低于 80%、峰值未知 | 当前观察、补采计划；禁止数值降配/回收结论 |
| `provisional` | 7–13 天 | 每项关键序列覆盖至少 80%，无长缺口，至少覆盖已知高峰或完整日周期 | 配置风险和验证型建议；不做确定性回收数值 |
| `standard` | 14–27 天 | 每项关键序列覆盖至少 90%，至少两个日周期，已知高峰覆盖；无未解释重大变更 | 支持性的 request/limit 建议和分阶段回收候选 |
| `high` | 28 天或更长 | 每项关键序列覆盖至少 90%，至少两个完整周周期，峰值/低谷均覆盖 | 高置信建议，但仍须变更验证与回滚 |

“工作负载有效运行”不是单个 Pod 存活时间。根据已确认的 Pod start/restart/phase 证据，记录版本切换、滚动发布和 Pod churn；若完整窗口都处于首次启动、扩容试验或频繁重建，不能把它视为稳定历史。

### 2.2 覆盖和缺口

对于每条关键序列：

```text
expected_samples = ceil((window_end - window_start) / step)
coverage = valid_samples / expected_samples
```

有效样本必须是成功查询、数值可解析且属于当前过滤范围的点。单容器/单 Pod 覆盖不达标时，不能由其他容器的高覆盖替代。记录最长连续缺口；默认把超过 **12 个采样间隔** 的缺口标记为长缺口。窗口切片时，切片边界和拼接后覆盖必须可复核。

历史窗口较长且接口有 `limit-points` 限制时，按固定子窗采集并保留每片的 start/end/step/点数；不得静默增大 step 使短时峰值消失。可分别采集细粒度峰值事实与较粗粒度分布统计，但须在报告标明各自时间分辨率。

### 2.3 峰值覆盖

优先级为：用户标明的业务高峰 > 已知业务日历/活动 > 每日/每周窗口最大值扫描 > 未知。

当不存在外部负载或 SLO 证据时，不能声称捕捉到了“真实业务峰值”；最多说明“观测窗口中的受保护峰值”。对 14 天以上窗口，比较每个自然日和每个 weekday 的 P95/最大值；漏掉某个已知高峰时段、周末模式或账期时，降低为 `provisional`。峰值未知是**下调资源的阻断条件**，不是偷偷提高冗余后继续下调的理由。

## 3. 统计量与异常处理

对通过质量门的有效样本计算：

```text
P50 = percentile(U, 50)
P95 = percentile(U, 95)
P99 = percentile(U, 99)
observed_max = max(U)
protected_peak = max(P99, peak_window_P95)
```

`peak_window_P95` 是每个已覆盖业务高峰窗口的 P95 中最大者；无可识别峰值时该项为 `unknown`，不允许数值降配。`observed_max` 用于发现尖峰、核对异常和解释风险，不直接作为容量目标：单个采样点可能是采集误差，也可能是未覆盖突发的警讯，必须结合重启、throttling、发布和业务事实解释。

对同一 workload 还要计算每个运行 Pod 的 `P95` 与 `P99`，报告最大/最小比或分位数离散。一个总和的平稳曲线不能掩盖单个热点 Pod。

以下样本不应与稳态统计混为一谈：指标缺失、Pod 不在 Running、标签/容器范围改变、已知发布切换、无效/负值速率、或 API 错误。剔除规则、原因、时间段和剔除后的覆盖必须进入证据；不能静默删掉高值来制造冗余。

## 4. 可配置冗余与规格公式

以下是没有用户/项目政策时的**保守默认参数**。它们是显式、可审计的起点，而非组织统一标准；用户、SLO、容量策略或性能测试的参数优先级更高。

| 参数 | 默认 | 用途 |
| --- | --- | --- |
| `cpu_request_headroom` | 20% | CPU P95 之上的 request 冗余 |
| `cpu_limit_headroom` | 30% | CPU 受保护峰值之上的 limit 冗余 |
| `memory_request_headroom` | 25% | 内存 P95 之上的 request 冗余 |
| `memory_limit_headroom` | 20% | 内存受保护峰值之上的 limit 冗余 |
| `cpu_quantum` | 10m（0.01 core） | 向上取整粒度 |
| `memory_quantum` | 64MiB | 向上取整粒度 |
| `max_first_reduction` | 20% | 单次变更最大下调比例 |
| `throttle_reclaim_block` | 5% | 已覆盖高峰内持续 throttling 的下调阻断线 |

`5%` 是已存在巡检配置中的黄色观察线，只在这里作为保守的**回收阻断参数**；它不是 CPU 利用率目标，也不是自动扩容阈值。所有参数都要在报告中逐项列出来源（项目政策、用户指定或本合同默认）。

定义 `ceil_q(x)` 为向上取整到资源量化单位，`H(x,h) = x × (1+h)`。在数据完整、峰值覆盖且没有安全阻断时：

```text
candidate_cpu_request = ceil_cpu(max(H(P95_cpu, cpu_request_headroom), configured_min_cpu))
candidate_cpu_limit   = ceil_cpu(max(H(protected_peak_cpu, cpu_limit_headroom), candidate_cpu_request))

candidate_mem_request = ceil_mem(max(H(P95_mem, memory_request_headroom), configured_min_memory))
candidate_mem_limit   = ceil_mem(max(H(protected_peak_mem, memory_limit_headroom), candidate_mem_request))
```

`configured_min_*` 仅指用户/项目明确的最小规格、LimitRange 或已确认的服务硬约束；没有这个事实时为零，**不是当前 request**。这允许算法识别过配，但不等于允许一次性降到候选值。

若 `candidate < current`，第一阶段可建议值为：

```text
first_stage = max(candidate, ceil_q(current × (1 - max_first_reduction)))
```

这是一项分阶段验证护栏。后续降配需要至少覆盖一个完整、已确认的业务高峰并通过第 6 节回归检查，才可进入下一阶段。若 `candidate >= current`，报告增加/保持建议及其证据；不把“当前配置较高”视为必须调整。

### CPU 与内存的不同解释

- **CPU request**：按 P95 的稳态调度需求加冗余；CPU limit 按受保护峰值加 burst 冗余。持续 throttling、P99 接近/超过 limit 或热点 Pod 离散会阻止下调，并形成短缺风险。
- **内存 request**：按 P95 working set 加冗余；memory limit 按受保护峰值加冗余，且绝不低于 candidate request。任何已确认的 OOM 事实、无法解释的重启、持续上升趋势或接近 limit 的峰值都会阻止下调。
- **CPU limit 策略**：本合同不自动建议移除 CPU limit；是否设置或移除 limit 取决于明确的项目策略。没有该策略时，只分析现状与候选数值。

## 5. 四类结论的决策表

| 类别 | 所需证据 | 可输出 | 禁止输出 |
| --- | --- | --- | --- |
| 冗余回收 | `standard`/`high` 历史、峰值覆盖、CPU/内存/配置完整、无安全阻断 | 分阶段 request/limit 下调候选、预期回收量、验证/回滚 | 单点/均值低使用直接降配；无峰值覆盖的数值回收 |
| 资源不足 | P95/P99/受保护峰值、request/limit 利用、throttling/重启、Pod 离散 | CPU/内存分别的短缺风险，建议验证加资源或排查热点 | 用 CPU 代替内存；高利用率单独断言需加副本 |
| 配置失配 | 使用分布与 request/limit 对齐、配置一致性、sidecar 范围 | request 低于长期 P95、limit 压制峰值、配置缺失/不一致的事实 | 把不完整指标说成配置正确 |
| 使用量排名 | 固定窗口、相同聚合层级、单位、样本覆盖 | CPU/内存实际使用、request、limit、使用率的独立 TopN/BottomN | 将实际量、配置量和使用率混为一张榜单 |

计算“潜在回收”只对通过回收门的对象做算术表达：

```text
potential_request_reclaim = max(0, current_request - first_stage_request) × stable_replica_count
potential_limit_reclaim   = max(0, current_limit - first_stage_limit) × stable_replica_count
```

它表示配置账面差额，不等于可立即释放的 Node 资源，更不等于集群可用容量。若没有确认的 Node allocatable、quota 或调度分母，报告不得把这个差额换算成集群余量。

## 6. 安全门、变更验证与回滚

任一条件为真时，禁止给出数值**下调**结论，改为风险观察、补证或保持配置：

1. 不满足 `standard` 历史层级，或峰值覆盖未知/缺失；
2. CPU、内存、request/limit、实例数任一关键维度缺失或配置范围不一致；
3. 已覆盖高峰内持续 CPU throttling 达到 `throttle_reclaim_block`，或 P99/受保护峰值接近现有 limit；
4. 已确认 OOM、无法解释的重启增量、内存持续上升，或不稳定 Pod；
5. 侧车是否计入不明确；
6. HPA/VPA 是否存在、发布状态、配置所有权或变更窗口未知；
7. 最近发布、扩缩容试验或 Pod churn 使观测不再代表稳态。

第 6 项可由用户/已确认只读配置事实解除。若始终未知，AI 可以给出“按此候选做隔离环境验证”的计算结果，但结论必须是 `validation-only recommendation`，不得写成生产变更指令。

建议的验证顺序：

1. 记录当前 request/limit、稳定副本数、时间窗和回滚值；
2. 先在可控环境或单一 workload 做不超过 `max_first_reduction` 的变更；
3. 覆盖至少一个明确业务高峰，比较变更前后 P95/P99、throttling、重启和用户/服务 SLO；
4. 任一明确的 SLO 恶化、OOM/异常重启、持续 throttling 或超过约束即回滚到记录值；
5. 验证通过后才评估下一阶段，且重新计算最近窗口的统计量。

本 skill 只写出此验证和回滚方案；真正的 Kubernetes 变更要交给受控的应用管理流程并取得所需确认。

## 7. 副本与容量边界

资源利用仅反映单实例配置与使用，不足以证明增加或减少副本。副本建议还要有至少一种可关联的需求/服务质量事实：吞吐、队列积压、延迟、错误率、SLO、并发或明确的业务负载预测。缺少这些事实时，可输出：

```text
Pod 级资源风险：supported
副本扩缩建议：insufficient evidence；需要补充负载/SLO与当前 HPA 行为
```

容量计算必须以已确认的 Node allocatable、namespace quota 或调度容量分母为基础，并将排除的系统预留、其他工作负载和可调度约束写清。request 总和、limit 总和或 Pod 用量总和都不能代替该分母。
