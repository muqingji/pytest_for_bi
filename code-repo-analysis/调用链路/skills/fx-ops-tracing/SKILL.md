---
name: fx-ops-tracing
description: 单请求级链路追踪与错误定位能力：从 CEP 网关日志到应用错误日志、慢 SQL、RPC 调用、APL 执行耗时做端到端诊断，输出 Root Error Span 与带累计耗时的链路时序表。适用「追一下这条链路/这条报错」「这个请求/接口为什么失败或超时」类单点问题、StopWatch 分段耗时分析、窄窗 app_log 取证、CEP 分段归因；支持仅有服务名+时间窗时反查 traceId、traceId 时间未知时分天小表反查、J-E. 前缀（集成平台，不走 CEP 网关）特殊路径。红线：app_log_dist 禁止裸 traceId 全分区扫描。
---

# fx-ops-tracing — 单请求级链路诊断器

## 全局约定

遵从 fx-ops 总控的全局约定。本地额外约定:
- 子代理（delegate）并行调度的并发度控制：通过 `runs.all` 并行启动多个子代理执行根因分析时，必须显式限制并发数 `concurrency: 5`（或更小），防止 ClickHouse 查询资源竞争与超时降级
- ClickHouse：**禁止猜列名**。拼 SQL 前读目标表在 `fx-ops-query` 单表文档中的字段定义与查询示例；跨表易错（如 error 表 `loggerName` vs app_log 表 `logger`、slow 表 `query`/`dbName`/`cost`）以 query 的「高频表误用列名」为准。报 `column_not_found` 时 `show columns` 校验，禁止盲改重试
- ClickHouse 时间过滤：统一用显式时间字面量 `'YYYY-MM-DD HH:MM:SS'`（如 `stamp >= '<T0>' AND stamp <= '<T1>'` / `_time_second_ BETWEEN '<T0>' AND '<T1>'`）。**禁止** `toDateTime(...) - INTERVAL …`、`toDateTime64`、`toDate` 及对已是 DateTime 列再包函数再减 `INTERVAL`（易触发 `time_guard_unrecognized`）。Agent 先算出 T0/T1 再写入 SQL
- ClickHouse 查询的租户过滤必须写进 SQL `WHERE`，不靠 `--tenant-id`
- 时间窗口按入口类型确定：ULID 精确 trace 默认前后 10 分钟；CEP 错误码 / 截图时间（traceIdLookup 反查）默认前后 5 分钟且最多仅允许扩窗 1 轮（到 30m，ambiguous不扩），普通空结果再按 10m -> 1h -> 6h -> 24h 阶梯扩窗；不要无限扩窗（统一扩窗阶梯见 fx-ops 主控「扩窗阶梯权威声明」）
- 应用日志、CEP、错误、慢请求、慢 SQL 查询统一使用 `biz-app-log` 作为命令行数据源参数，SQL 中直接写真实表名（如 `FROM log_cep_dist`），禁止在 SQL 中将 `biz-app-log` 作为 dbName 前缀。

 **`app_log_dist` 红线**（每天约百亿条）：① 必须带 `_time_second_` 时间戳过滤（该表无 `stamp`）；② 窗口跨度默认≤6 小时、最大≤24 小时；③ **必须带 app 过滤**（`CTX-app-discovery.json` 候选，`AND app IN (...)`）；④ **绝对禁止仅用 `traceId` 不带时间范围查找**——`traceId` 非分区键，裸 traceId 会全分区扫描导致集群失去响应。
- 查询 `log_cep_dist` 时默认选择问题发生时间点附近 1 小时（前后各 30 分钟）；如果问题就是当前时间，默认取当前时间向前 1 小时。CEP 报错 = `log_cep_dist` 的 `status >= 500`（用户侧真实失败）；`status < 500` 为正常或重定向流量。
- `s311…` 等非标准旧码已逐步废弃：**禁止向用户解释该码「是什么意思」**；仅作 `reqId`/截图弱线索反查 traceId，结论只写本次请求的 `error`/堆栈/URI/状态，不写码表释义。

## 必做门禁：入口类型、租户与云环境识别

正常由 `fx-ops` 主控在分发本 skill 前完成锚点取证，并通过 `handoff_ref=handoffs/HND-*` 与 `evidence_index_ref=index.md` 交接。本 skill 第一动作是读取 HND，再读取 `index.md`，从 HND 的 `anchor_context` / `request_anchor` 和索引列出的 `TRC-*` / `QRY-*` 证据中获取 `traceIdParsed` 或 `traceIdLookup`、`env`、`tenant_context`、`time_window`。已有同源同窗证据时消费证据继续深挖，不重复等价 CEP traceIdLookup。

**编排流 vs 直接调用的路由判断**：

- 若 prompt 包含 `handoff_ref`：按编排流处理；当 HND / index 显示 `traceIdLookup.status=pending` 或 `ambiguous` 时，**回抛主控**（`status=partial`、`route_hint=need_trace_id_lookup`、`target_capability=query`），不自行补齐。
- 若没有 `handoff_ref`：视为直接调用，自行兜底解析。

**直接调用时**，本 skill 需自行补齐缺失上下文后才开始日志查询。

收到 traceId / reqId / CEP 错误码 / 截图后，**必须立即完成以下链路，禁止跳过**：

1. **确认入口类型**：优先使用主控传入的 `traceIdParsed`、`errorCodeParsed`、`traceIdLookup`；没有则调用 `extract_error_anchor` / `parse_traceid` 解析输入。明确 traceId 才进入 traceId 查询路径；CEP 错误码 / reqId 必须先按 CEP 错误码查询流程反查真实 traceId，不得伪造成 `traceIdParsed`。
2. **reqId / 错误码转 traceId**：入口为 CEP 错误码 / reqId 时，优先复用主控或 `fx-ops-query` 已解析的 `traceIdLookup.status=resolved` 上下文。

  **编排流下尚未 resolved**：本 skill 不自行派发兄弟 skill，按回抛协议返回主控（`route_hint=need_trace_id_lookup`，`target_capability=query`，`need_further` 仅作人类摘要），由主控派 `fx-ops-query` 用 `log_cep_dist` 的 `has(reqId, '<code>')` 锁定真实报错行、回填 `traceId/traceIdParsed/tenant_context/time_window` 后再回到本 skill。

  **仅直接调用（无主控编排）时**：自行用 `has(reqId, '<code>')` 查 `log_cep_dist` 兜底解析。查不到或多候选无法裁决时返回 `partial` 并列出候选，不继续后续链路查询。
3. **ea 反查租户与环境**：有 `traceIdParsed.ea` 时调用 `resolve_tenant_cloud`，传入 `ea`，获取 `ei/tenantId` 和云环境（`env`，如 foneshare/firstshare/sbt 等）。若 `traceIdParsed.env_hint` 已存在（由 `parse_traceid` 自动产出），可先用 `env_hint.profile` 设置查询环境，再用 `resolve_tenant_cloud` 验证。CEP 错误码只有在转出真实 traceId 后才进入后续链路追踪。
4. **写入上下文**：将 `ei`、`ea` 写入 `tenant_context`，将云环境写入 `env`，将 `traceIdParsed.time` 写入 `time_window` 锚点。这是后续 SQL 查询租户过滤、时间分区和选择 `--profile` 的前提。
5. **ea 为空时的降级**：若 `userAgent` 为 `OS` / `S`（服务端内部调用）导致无 ea 段，或 CEP 错误码只有 source ID，需从 SQL 查询结果的 `ea` 字段反推，或直接问用户。

**没有 `traceId/traceIdParsed`、env 和 time_window，无法确定查哪个企业、哪个环境、哪个时间分区的数据——不要进入后续链路 SQL。CEP 错误码没有 `traceIdParsed` 只允许停留在 `traceIdLookup` 阶段，必须先通过 `fx-ops-query` 的 `log_cep_dist.reqId` 小表反查能力解析出 traceId。**

## 证据优先与取证规范 (Evidence-First)

1. **证据落盘**：所有关键查询结果必须保存至主控分配的 evidence_dir；独立调用时使用 `output/evidence/<YYYYMMDD-HHMMSS>-<short-topic>-<channel_value>/` 格式。
2. **强制引用**：给出最终排查结论时，必须显式引用已保存的证据文件路径。
3. **原始数据优先**：不要仅凭 AI 总结作为结论，必须以原始日志（Trace/Log Snippet）作为判定依据。

## 适用边界

`fx-ops-tracing` 只处理**单请求、单报错、单链路**的诊断问题。同类报错聚合分析（同一企业同一用户故障时刻前后 30 分钟内同类报错）属于单请求诊断的增强手段，不算故障面分析。

被 `fx-ops` 主控调度时，必须服从 HND 中的 `objective`、`allowed_collection` 和 `stop_when`。主控已完成的 Phase0-1 锚点取证不重复；是否继续补 StopWatch / APL 执行日志 / 代码级证据，由 HND、`index.md` 和回抛 `route_hint` 驱动。

适合进入本 skill 的场景：
- 已提供 `traceId`、CEP 错误码、前端报错截图、明确的单次失败时间点
- 用户要追"这一次请求为什么失败""这条链路卡在哪里""这条报错是谁先抛的"
- 需要从 CEP 网关、应用报错、慢 SQL、RPC 调用、APL 函数执行耗时中定位 Root Error Span
- 有服务名和时间窗口但无 traceId：可通过 ClickHouse 反查 traceId

## 不适用边界

以下场景应立即升级或回抛：
- 同类异常批量爆发，目标已变成"故障面"分析
- 主要是 CPU、内存、GC、线程池、Pod 重启等资源体征
- 主要是脏数据、字段缺失、Schema 变化、租户分片或路由异常
- 用户要的是"这段时间发生了什么""做一个统一时间线"
- 没有任何请求锚点，只给了宏观现象

## 不适用时的回传格式

- 当前判断：不适用本 skill，原因 <具体原因>
- 归一化上下文：原样带回主控传入的上下文
- 已执行的查询（如有）：<列出>
- 建议下一跳：<推荐哪个 skill/playbook>

## Tracing 执行流程

首轮假设树、高信号查询顺序、运行时日志级别降级检索机制、累计耗时标注、网关空消息提示检测器、扩展取证指引详见 references/tracing-steps.md。不要主动生成 HTML、负责人或跨 skill 深挖；需要其它能力时按回抛合同交给主控裁决。

## 场景路由

| 用户意图 | 进入 |
| --- | --- |
| 给一个 traceId，追完整调用链 | [playbooks/trace-end-to-end.md](references/playbooks/trace-end-to-end.md) |
| 有 traceId 但不知道时间 | [playbooks/traceid-time-unknown.md](references/playbooks/traceid-time-unknown.md) |
| CEP 错误码（如 15-84f875）或前端报错截图 | [playbooks/cep-error-code.md](references/playbooks/cep-error-code.md) |
| 有服务名和时间但无 traceId，需反查 | [playbooks/trace-end-to-end.md](references/playbooks/trace-end-to-end.md)（反查模式） |
| bizName → app 映射（四表全空时需要） | **fx-ops-knowledge** skill |

## 共同原则

详细原则见 [playbooks/index.md](references/playbooks/index.md)。核心规则：
- 每次构造/执行 ClickHouse/SQL 前，必须静默校验参考文档、列名类型、单引号字符串、时间过滤、租户/服务过滤与 LIMIT；低风险通过时不输出 Checklist。仅在缺少时间窗/范围过滤、schema 不确定、可能全表扫描或降级执行时显式报告风险，禁止盲目拼写。
- 价值密度优先，时间窗口先小后大
- CEP 错误码默认走首轮诊断（锚点 + 高信号表），详见 references/playbooks/cep-error-code.md
- traceId 精确等值查询可省略租户过滤（例外）
- `tomcat_access_slow_dist` 的 traceId 字段名是 `trace_id`（snake_case），其他表为 `traceId`（camelCase）
- 日志字段 `profile` 与 k8s `namespace` 是同义词：Pod 在 `foneshare` ns 中运行时，日志中 `profile=foneshare`
- `J-E.` 开头的 traceId 代表集成平台发起的请求，不走 CEP 网关，不需要查 `log_cep_dist` 和 `fs_cep_slow_error_dist`，直接从 `log_error_dist`、`app_log_dist` 入手

## 输出要求

最终输出必须明确回答：
- 这是不是单请求问题，还是已经观测到批量故障征兆
- 首发异常出现在什么时间、哪一层、哪个 span / 服务 / SQL / RPC
- 当前更符合哪条假设分支，排除掉了哪些可能性
- 是否需要升级到时间线、监控、查询或源码检索能力（**仅**在 `log_error_dist` 等已给出堆栈/类.方法后；**禁止**为 CEP/`s311…` 错误码本身做 Sourcebot grep）

输出门禁：
- 请求锚点、直接证据、证据文件、置信度、`stop_reason`、`escalate_when` 必须明确。
- 若 HND 要求完整链路，链路时序表必须包含累计耗时列，标准格式和证据文件说明详见 references/output-template.md。
- 不主动补 HTML、负责人、源码正文或人工审计；需要这些能力时通过 `route_hint` / `target_capability` 回抛主控。

证据至少应包含：一个链路锚点文件（如 `log_cep_dist` 查询结果）和一个结论摘要文件；若 HND 要求完整链路，另需包含对应首发异常或慢点证据文件。

## 输出回抛

完成链路追踪后，按 fx-ops 总控回抛协议返回:
- status: completed / partial / empty / error
- findings: Root Error Span 定位结果、异常传播路径
- evidence_files: 已落盘的证据文件列表
- confidence: high / medium / low
- stop_reason: `direct_evidence_enough` / `needs_standard` / `needs_deep` / `blocked_ambiguous` 等机器可读短码
- escalate_when: 触发下一层的具体证据条件；不得只写"建议继续看看"
- need_further: 人类摘要（可选）；编排流须回抛 `route_hint`+`target_capability` JSON，`need_further` 不驱动主控下一跳

## 被调度时的约定

当 fx-ops 主控以 sub-agent 方式调度本 skill 时，约定如下：

- **主控传入参数**：prompt 只包含 `handoff_ref=handoffs/HND-*`、`evidence_index_ref=index.md` 和短执行约束；完整派发上下文从 HND 读取，已有证据从 `index.md` 按需打开。
- **执行方式**：本 skill 必须以 sub-agent 模式运行（上下文权重较高，需要完整日志数据）
- **必须产出**：Root Error Span 定位、带累计耗时的调用链时序表、已落盘的证据文件列表
- **不适用时**：若场景不属于单请求级追踪，立即按"不适用时的回传格式"输出并返回主控
