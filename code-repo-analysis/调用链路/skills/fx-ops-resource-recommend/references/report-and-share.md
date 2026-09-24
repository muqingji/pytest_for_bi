# 资源建议报告与受控分享

本合同约束 AI 基于本次已冻结的资源证据撰写 Markdown 和可选 HTML。它不授权新的数据查询、资源变更、目录扫描、上传或生产路由猜测。Python、Node、Jinja、模板 renderer 和字符串拼接器不得生成读者可见的 Markdown/HTML 正文；AI 必须直接撰写正文，程序只能采集、统计结构化证据或只读校验成品。

## Markdown 报告

AI 依据本次结构化证据按以下顺序组织 Markdown：

1. **范围、映射与查询口径**：用户原始范围、标准 profile、真实 `k8s_cluster`、namespace、workload/service、container/sidecar scope、metrics datasource、映射知识库依据、受控发现是否执行；同时记录精确 UTC 起止时间、step 和单位。
2. **数据质量**：历史/有效运行天数、各维度覆盖、最大缺口、峰值覆盖、发布或 churn、成功/失败查询及其对结论的限制。
3. **资源事实**：CPU 与内存各自的 P50/P95/P99/受保护峰值、request、limit、使用率与 Pod 离散。
4. **四类结论**：冗余回收、资源不足、配置失配、使用量排名必须分别写，不能混成“资源正常”。
5. **建议与风险**：参数来源、算法输入、推荐值/首阶段值、预期账面回收、置信度、安全门、验证和回滚。
6. **容量与副本边界**：说明是否具备 allocatable/quota 分母和负载/SLO 证据。
7. **未决项**：缺失指标、HPA/VPA/配置所有权、需要补采的高峰或负载事实。

一切数字须回指查询或统计证据。未通过历史质量门时，明确写“不建议下调/扩缩副本”，而不是给出无前提数值。瞬时读数只能是 `confirmed observation`，不得被表述为确定性的配置、容量或副本结论。

## HTML 与分享确认

HTML 仅是已完成 Markdown 分析后的可选读者交付。必须先逐字询问：

```text
是否要根据这份分析生成 HTML 页面和分享链接？
```

在用户明确确认前：

- 不生成 HTML；
- 不调用分享能力；
- 不扫描 `output/` 或 `tmp/` 猜测最新文件；
- 不提供、虚构或暗示链接。

确认后才可执行：

1. 冻结本次真实证据、映射和报告事实；渲染阶段不重查 Prometheus，也不改变排名、评分或建议。
2. AI 直接撰写一个明确命名的自包含 HTML 文件到 `output/` 或 `tmp/`。
3. AI 对照本合同检查结构、披露、转义与交互；校验器可只读检查，但不得生成、修改或补齐正文。
4. 仅将这个明确路径交给受控分享能力，执行 plan-first 扫描、路径/类型/大小/敏感命中/过期检查和授权检查。
5. 只有没有硬阻断且授权满足时才上传；成功后返回真实 URL、过期信息和最小审计摘要。

用户拒绝时保留 Markdown 并返回 `executed: false`，不生成或上传分享物。上传失败时只报告简化失败原因和 `executed: false`，不编造 URL，不把本地路径伪装成公网链接，也不回显认证材料或敏感扫描原文。

## HTML 信息架构与评分

HTML 是单页、离线可读、无外部字体/CSS/图片/运行时数据请求的深色资源审阅表。生成时把 `generated_at`、scope、datasource 和 UTC window 复用自已冻结证据，禁止渲染时新造时间。

首屏按以下顺序组织：

1. 标题：`Scan result (<score>/100 points)`；分数必须同时有文字评分口径，不能把它表述为服务健康度或生产安全保证。
2. 范围条：cluster、namespace、service/workload、container/sidecar scope、metrics profile、datasource、UTC interval、映射依据。
3. 数据质量条：history、coverage、peak coverage、最长缺口、扰动、缺失维度和总体结论级别。
4. 搜索和展开控制条：literal search、结果状态、逐项展开/收起、全部展开/收起。
5. 固定资源表：可局部横向滚动；算法说明必须在最右侧。
6. 末尾证据与限制：以原生 `details` 收纳证据标识、算法版本、数据缺口和未决项。

### 可审计评分

`score` 仅用于说明本次建议的**证据可审阅度**，范围固定在 `0..100`，不是资源利用率、成本节省、SLO、健康状态或是否可直接发布的分数。每个扣分必须展示数值与原因：

```text
score = clamp(0, 100
  - 20 × required_dimension_missing_ratio
  - 15 × coverage_penalty
  - 15 × peak_penalty
  - 10 × stability_penalty
  - 10 × mapping_or_scope_penalty
  - 10 × ownership_or_autoscaling_penalty
  - 20 × query_error_ratio)
```

- `required_dimension_missing_ratio`：分母固定为六个命名资源字段 `{cpu_usage, memory_usage, cpu_request, cpu_limit, memory_request, memory_limit}`；分子是这六个字段中状态为 `missing`、`empty`、`error` 或 `scope-mismatch` 的字段数。因此 `required_dimension_missing_ratio = missing_required_resource_field_count / 6`。Pod count/replica 不是该分数维度，另作为范围、稳定性或证据质量条件单独披露。
- `coverage_penalty`：全部关键维度覆盖 `>=90%` 为 `0`；`80–89%` 为 `1`；`<80%` 为 `2`。
- `peak_penalty`：`covered=0`、`partial=1`、`unknown=2`。
- `stability_penalty`：无未解释发布/churn/OOM/restart/throttling 安全门为 `0`；存在但能隔离为 `1`；影响当前样本解释为 `2`。
- `mapping_or_scope_penalty`：profile/cluster/namespace/service/container 范围均有可审计依据为 `0`；存在待确认项为 `1`；任一映射或范围不一致为 `2`。
- `ownership_or_autoscaling_penalty`：HPA/VPA、所有权和变更窗口已确认且无阻断为 `0`；未知或待确认是 `1`；其配置可能改变建议含义是 `2`。
- `query_error_ratio`：所有计划查询中 `error` 状态的比例；不把 `missing` 悄悄合并为零。

报告必须显示各项惩罚、公式版本 `resource-evidence-score/v1` 和评分输入；任何安全门仍可将建议降级，即使 score 较高。

## 固定深色资源表

参考图的高密度深色语义必须保留：近黑页面背景、深灰表头、等宽或具备 tabular numerals 的表格、细 1px 网格、低对比斑马行、约 6–8px 单元格内边距，以及局部表格滚动而非页面横滚。不得把表格改为卡片墙、图表或省略固定字段。

表头列**顺序、拼写和数量必须完全如下**：

```text
Number | Cluster | Namespace | Name | Pods | Type | Container | CPU Requests | CPU Limits | Memory Requests | Memory Limits | Recommendation / Algorithm
```

- `Number` 是 workload 编号；多容器的后续行重复同一个编号并通过 `scope=rowgroup` 或等价结构说明同一 workload。
- `Cluster`、`Namespace`、`Name`、`Container` 使用真实字符串；仅长 cluster 和 name 可视觉省略。必须保留 leading text、使用 CSS `text-overflow: ellipsis`，并用正确转义的完整值写入 `title`，让鼠标与辅助技术可取得完整文本。不得把截断值当作搜索文本。
- `Pods` 是本次观察到或已确认的实例数；无事实时 `?`，没有配置字段时 `none`。
- `Type` 仅在证据确认时写 `Deployment`、`StatefulSet` 或 `DaemonSet`；未确认写 `?`，不按名称猜测。
- 每个容器一条逻辑行；同一 workload 的 CPU/Memory 使用、request、limit 必须使用同一 `(pod, container)` 和 container/sidecar scope。多容器不得把全 Pod 的使用量与单容器配置混写；workload 级汇总须另命名为全部容器行的 sum，不能复用为任一容器行。
- 四个资源列只使用 `old -> new`；配置不存在为 `none`，无法由本次证据确定为 `?`。保留 `none -> none` 以表达经证据确认的无配置变化。
- 默认排序必须在范围条中写明。无用户排序时：先按 recommendation category 的风险优先级，再按 workload 名、container 名的稳定字典序；不得把 score 当作单个工作负载的风险排序。

### 颜色和可访问性

颜色是补充语义，不是唯一语义：

- 中性标签/固定标识用高对比浅色文字。
- 常规数值差异可用琥珀色，但必须同时呈现完整 `old -> new` 文字。
- 风险、阻断或证据缺失可用红色，且同时给出屏幕可读标签，例如 `risk: throttling`、`blocked: peak coverage unknown` 或 `unknown`。
- 可验证、仅建议和不可得结论分别显式写出 `supported recommendation`、`validation-only recommendation`、`insufficient evidence`，不能只依赖绿/黄/红。
- 文本与背景至少满足正常文本 4.5:1 的对比度；焦点状态必须可见；不要使用纯红/纯绿区分相反结论。

## Recommendation / Algorithm 说明

最右列是每行必填的审阅入口，不能只写“建议增加/减少”。单元格先显示下列可搜索摘要，再提供原生 `details` 的完整说明；短说明也可直接展开，但不得删减必填事实：

```text
<category> · <conclusion level> · <rule/algorithm version>
```

`category` 必须是 `redundancy reclaim`、`shortage risk`、`configuration drift`、`usage ranking` 或 `insufficient evidence` 之一。展开内容必须逐项包含：

1. **Sources and scope**：metrics datasource、profile、cluster、namespace、workload、container/sidecar scope，以及查询/证据标识。
2. **UTC window and sample quality**：start/end/step、expected/valid samples、coverage、longest gap、history/effective runtime、peak coverage、release/churn。
3. **Statistics and thresholds**：P50/P95/P99、protected peak、Pod dispersion、throttling/restart/OOM 事实，以及使用的门槛和是否命中。
4. **Request/limit comparison**：CPU 与 memory 分开写当前值、候选值、first stage 值、量化单位、old -> new 差异与相应 request/limit 比较。
5. **Peak headroom**：request/limit headroom 的输入、结果和来源；没有真实业务高峰证据必须写 `peak coverage: unknown`，不得把观测峰值伪称业务峰值。
6. **Uncertainty, risk and assumptions**：缺失维度、sidecar、HPA/VPA、所有权、SLO/负载、容量分母和变更窗口的已知/未知状态；瞬时或短历史读取必须明确不确定性。
7. **Rule version and action boundary**：例如 `right-sizing-algorithm/v1`、参数来自用户/项目/默认合同的来源、验证条件、回滚值，以及“未执行 Kubernetes 变更”。

建议的计算文字必须能复算，例如：`candidate_cpu_request = ceil_10m(P95_cpu × 1.20)`；默认参数必须标为合同保守起点，不能称为组织政策。只有证据满足历史和安全门时，才显示数值降配候选；否则显示观察、补采或验证计划。

## 安全交互合同

报告只有在用户已确认生成 HTML 后可包含内联脚本；脚本只处理该静态页面中的搜索和折叠，不获取网络数据、不改写证据事实、不上传、不执行变更。

### Literal 搜索

- 搜索框有可见 `<label>`，placeholder 仅作补充；使用 `type="search"`。
- 输入即时、大小写不敏感、逐字面量匹配；**不是正则**，不得把用户输入传给 `RegExp`。
- 每个 workload/container 逻辑行有预先构建的搜索文本，覆盖完整 cluster、namespace、name、container、type 和 recommendation category；搜索要使用完整未截断文本。
- 搜索使用统一函数 `normalizeSearchText(value) = value.toLocaleLowerCase(REPORT_LOCALE)`，其中 `REPORT_LOCALE` 是报告生成时固定配置的 locale，不能由用户输入控制。构建每个完整 workload/container searchable text 时先规约字段和拼接后的完整字符串；输入变化时也用同一函数规约 query，再以 `normalizedSearchText.includes(normalizedQuery)` 匹配。空 query 显示所有行。不得把可搜索值解释为 HTML。
- 始终更新 `role="status" aria-live="polite"` 的状态，例如 `Showing 3 of 12 workloads for “payments”` 或 `Showing all 12 workloads`。结果数按可见 workload 计算，不能因多容器被重复计数。
- 搜索命中一条工作负载时显示该 workload 的所有容器行；不让多容器同组因仅一个容器匹配而残缺显示。

### 折叠和展开

- 每项算法说明使用语义 `<details>`/`<summary>`，或等价的 `<button aria-expanded aria-controls>`；不得以不可访问的 `<div>` 伪造按钮。
- `details`、证据和长算法说明默认折叠。默认折叠基于确定且可审阅的阈值：当 workload 数 **大于 8**，或任何说明正文 **大于 320 个可见字符** 时折叠；不超过阈值时可默认展开。页面必须显示这两个阈值。
- 提供每项展开/收起和 `Expand all` / `Collapse all`。全局控件须更新自身和每项的 `open` 或 `aria-expanded` 状态；筛选后只展开/收起当前可见项目。
- 搜索不会擅自改变 open 状态；清除搜索恢复先前的用户展开状态，而非重置页面。

### 动态内容与事件安全

- 所有来自用户、Prometheus 标签、证据、算法说明或搜索 query 的动态文字都必须通过 DOM `textContent` 或等价安全文本节点插入。
- 属性值（包括 `title`、`aria-label`、`data-*`）必须使用正确的属性转义；不得把未转义动态值连接到 HTML、属性、URL、CSS 或事件代码。
- 禁止 `innerHTML`、`outerHTML`、`insertAdjacentHTML`、动态 `on*` 属性、字符串形式的 `setAttribute("onclick", ...)`、`eval`、`Function` 和 `javascript:` URL。
- 使用 `addEventListener` 绑定静态元素，或对一个稳定容器使用事件委托；事件处理器不得由动态字符串生成。
- 搜索状态、完整 tooltip 和展开详情均用文本 API 输出。服务名如 `<img src=x onerror=...>` 必须以纯文本呈现，永不变成标签或可执行事件。

## HTML 交付前检查

在向用户交付或调用分享能力前，AI 逐项检查：

- [ ] 用户明确确认了 HTML 与分享；若拒绝或未确认，`executed: false`，没有文件生成/上传。
- [ ] 报告范围记录 mapping、knowledge basis、profile、datasource、scope 和 UTC interval；冲突/不确定映射没有被静默路由。
- [ ] 标题显示 `Scan result (<score>/100 points)`，评分公式、版本、输入和扣分均可审计。
- [ ] 表头精确为 12 列，`Recommendation / Algorithm` 位于最右；资源列为 `old -> new`，`none` 和 `?` 的语义正确。
- [ ] Deployment、StatefulSet、DaemonSet 和多容器多行结构不会丢失 scope、编号或资源对齐；长 cluster/name 有完整转义 tooltip。
- [ ] 每条 recommendation 有 category、sources、UTC window、sample quality、statistics/thresholds/percentiles、request/limit comparison、peak headroom、uncertainty/risk/assumptions、rule/algorithm version、验证和回滚边界。
- [ ] 搜索是即时、不区分大小写、多字段的 literal match；固定报告 locale 的同一 `normalizeSearchText` 已用于完整预构建 searchable text **和** query（在 `includes` 前完成），显示结果状态，且不会拆散同一 workload 的容器行。
- [ ] 默认折叠阈值、单项与全部展开/收起存在且可用；无 `innerHTML`、动态事件属性或未经转义的动态内容。
- [ ] HTML 无外部依赖、无渲染时查询、无敏感数据、无对瞬时读数的确定性结论；分享仅返回真实上传结果。
