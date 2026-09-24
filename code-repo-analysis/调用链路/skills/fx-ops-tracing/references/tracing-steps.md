# Tracing 执行流程详细步骤

## 首轮假设树

拿到请求锚点后，先在脑中建立以下四类假设，避免一上来就铺开所有数据源：

1. **代码异常首发**
- 典型信号：`biz-app-log` 数据源下的 `log_error_dist` 表中出现 NPE、类型转换、参数校验、业务断言失败，且时间上先于下游报错
2. **下游超时或错误传导**
- 典型信号：RPC/SQL/HTTP 调用耗时异常、下游返回错误码，上游只是在包装异常
3. **配置或租户环境差异**
- 典型信号：相同请求只在特定租户、环境、云区域失败，或请求命中特定配置分支
4. **资源异常导致请求失败**
- 典型信号：请求时间点附近出现 Pod 重启、GC 停顿、线程池耗尽、CPU throttling、网络超时

首轮诊断只需要判断哪一支最像，不要求一次证明全部分支。

## Tracing 执行流程

`fx-ops-tracing` 只负责**已确定 tracing 场景后的执行动作**，不负责替代 `fx-ops` 进行全局编排。

0. **HND 合同确认**：编排流下先读 `handoff_ref`，再读 `evidence_index_ref=index.md`。本轮只执行 HND `objective` / `allowed_collection` / `stop_when` 允许的增量取证；已有 manifest task 与索引证据覆盖同源同窗时直接复用，不重复查询。
1. **输入规范化**：若 HND / 索引证据已提供 `traceIdParsed`，直接复用；若输入中有明确 traceId 但缺少 `traceIdParsed`，先调用 `extract_error_anchor` / `parse_traceid` 提取 `traceIdParsed`、`service`、`timestamp`。若输入是 reqId / CEP 错误码 / 报错截图中的错误码，先调用 `extract_error_anchor` / `parse_traceid` 形成 `errorCodeParsed` 与 `traceIdLookup`；编排流下回抛主控（`route_hint=need_trace_id_lookup`、`target_capability=query`）由主控派 `fx-ops-query` 通过 `log_cep_dist.reqId` 小表反查真实 traceId，直接调用时本 skill 自行用 `has(reqId,...)` 查 `log_cep_dist` 兜底；回填 `traceId/traceIdParsed` 前，不进入后续链路查询。若 `errorCode` 是 `s311...` 旧格式，仅记录为弱线索，不追查含义。**若用户未提供 traceId 但给出了 app + 时间窗口，主动通过 `biz-app-log` 数据源下的 `eye_trace_dist` 表或 `log_cep_dist` 表反查 traceId**（反查模式见 playbooks/trace-end-to-end.md）。
2. **环境锚定**：有 `traceIdParsed.ea` 时，调用 `resolve_tenant_cloud` 确认物理云环境，避免查错日志路由；HND / 索引证据已有 `env/tenant_context` 时复用，不重复查询。若 `traceIdParsed.env_hint` 已存在（由 `parse_traceid` 在解析阶段自动产出），可直接用 `env_hint.profile` 设置查询环境，减少一次 `resolve_tenant_cloud` 调用。
3. **先锁请求，再判分支**：优先确认 `traceId`、租户、时间窗口、入口接口，不要先做大范围全局搜索；**时间窗口未知时先用 `extract_error_anchor` / `parse_traceid` 解析 traceId 时间点，解析不出就走 playbooks/traceid-time-unknown.md 用小表反查出时间范围，确定时间窗后再查——时间范围未确定前禁止查 `app_log_dist`**；随后依据"首轮假设树"判断更像代码异常、下游传导、环境差异还是资源异常。
   > [!IMPORTANT]
   > **【ClickHouse 列名】**：禁止猜列名。SELECT/WHERE 列以 `fx-ops-query` 目标单表文档的字段定义与 RCA 查询示例为准；跨表差异（`log_error_dist.loggerName` vs `app_log_dist.logger`；`slow_log_dist` 用 `query`/`dbName`/`cost`）见 query「高频表误用列名」。
   > [!IMPORTANT]
   > **【ClickHouse 时间过滤】**：WHERE 时间条件必须用显式字面量 `'YYYY-MM-DD HH:MM:SS'`（`log_cep_dist` 用 `stamp`，其它常用表用 `_time_second_`）。禁止 `toDateTime/toDateTime64/toDate` 再减 `INTERVAL`，禁止在未算出 T0/T1 时写 `now() - INTERVAL` 给 time_guard 解析失败的路径。
4. **高信号查询顺序**：
- 先查 `biz-app-log` 数据源下的 `log_cep_dist` 表或 `fs_cep_slow_error_dist` 表，确认链路锚点和失败时间
- 首轮只查能解释当前失败的高信号表组。优先锁定 CEP 目标行；若 CEP `error/errorCode` 已解释业务失败，仍需写明 `stop_reason` 与 `escalate_when`，并回抛主控决定是否继续。
- 当 HND 要求完整链路、manifest 显示 Phase1 证据不足、命中慢/超时/爆发信号、用户要求继续深挖，或质量门禁要求补证时，再并行查 `log_error_dist`、`fs_cep_slow_error_dist`、`slow_log_dist` / `sql_slow_dist`、`tomcat_access_slow_dist`。
   > [!IMPORTANT]
   > **【长轮询噪声识别】**：`tomcat_access_slow_dist` 中 `time_cost` 在 25–35s 且 URI 命中以下模式之一的请求是设计长轮询（正常业务行为），标记为 `noise: long_poll_slow` 并跳过，不进入 StopWatch 深挖：`*checkUpdatedAsyncV2*`（企信消息轮询）、`*LongPolling*`（Comet 长轮询）、`*online/consult/*/checkUpdate*`（在线客服轮询）、`*GetQRImageStatus*`（扫码登录轮询）。权威定义见 `fx-ops-patrol/references/thresholds.yaml` → `noise.long_poll_slow`。
   > [!IMPORTANT]
   > **【子代理并发度控制】**：在并行调度多个子代理（delegate）做单链路深挖与 ClickHouse 查询时，必须显式传递 `concurrency: 5`（限制并行数 ≤ 5），防止 ClickHouse 查询资源竞争与单查询超时降级。
   > [!IMPORTANT]
   > **【运行时日志级别降级检索机制】**：`log_error_dist` 空不是自动查 `app_log_dist` 的理由。只有在 CEP 目标行明确 `status >= 500` 且 CEP `errorCode/error` 不足以解释，或 HND/质量门禁要求补应用日志时，才查一轮窄窗 `app_log_dist`；查询必须带 **`_time_second_` 时间窗、app 过滤（`CTX-app-discovery.json` 候选）和关键词过滤**。检索时遵循"ERROR > WARN > INFO"的日志级别顺序，寻找 `Exception`、`at com.`、`error`、`fail`、`ClientAbort`/`broken pipe`、`querycache`、`IndexOutOfBounds` 等异常堆栈或业务拦截特征。**绝不能仅用 traceId 裸查全量 `app_log_dist`**——该表每天约百亿条，`traceId` 非分区键，裸 traceId 全分区扫描会导致集群失去响应。
- 只有首轮证据不足时，才补查 `biz-app-log` 数据源下的 `app_log_dist` 表、`eye_trace_dist` 表、配置、监控或下游数据
5. **同类报错聚合分析（条件触发）**：首轮不默认做同类聚合。只有 `log_error_dist` 命中 token、CEP 5xx 需要判断是否爆发、用户关心影响面，或 HND/质量门禁要求判断同类异常时，才扩窗检查同一企业同一用户在故障时刻前后 30 分钟内是否重复出现同类报错：
- **提取错误特征**：根据首条 trace 的报错层级确定聚合锚点：
- **应用层报错**（`log_error_dist` 有记录）：提取 `token`（简化的异常类名，可能是完整类名或缩写包名，如 `c.f.p.a.c.e.AuthException`）、`error`（错误类型）、`app`、`uid`。若 `token` 为 null，降级用 `error` 字段聚合
- **CEP 网关异常**（`log_error_dist` 无记录，但 `log_cep_dist` 的 `status >= 500`）：提取 `uri2`（简化 URI）、`errorCode`、`uid`
- **同类报错搜索**：
- **应用层**：查 `log_error_dist`，过滤 `(ei='<EI>' OR ea='<EA>')` + `uid='<UID>'` + `token='<TOKEN>'` + 故障时刻 ±15 分钟
- **网关层**：查 `log_cep_dist`，过滤 `(ei='<EI>' OR ea='<EA>')` + `uid='<UID>'` + `uri2='<URI2>'` + `status >= '500'` + 故障时刻 ±15 分钟
- 两层可并行查询，统计出现次数、traceId 列表、时间分布
- **模式判定**：若同类报错 ≥ 3 次，说明是同一用户重复遭遇的稳定性问题而非偶发——优先从多次报错中找共性模式（相同堆栈、相同服务、相同下游），结论更精准
- **落盘**：聚合结果保存到 `evidence_dir/QRY-similar-errors.json`，包含 `count`、`traceIds`、`time_range`、`common_pattern`（共性特征摘要）
- **注意**：此步骤不是"故障面分析"——目标仍是定位该用户这条报错的根因，但利用多次出现的共性来增强诊断置信度
6. **首发异常定位与结果回传**：基于 trace 拓扑、时间序 and 高信号日志，定位 **Root Error Span**，区分首发异常与次生报错，并把关键查询结果落盘到 `output/evidence/`。
  > [!IMPORTANT]
  > **【证据渐进式落盘】**：每步查询结果必须即时保存到 `evidence_dir`，不要攒到最后一次性写入。命名规则：`TRC-cep-target.json`、`TRC-app-stopwatch.json`、`TRC-app-log-analysis.json`、`SUM-tracing-conclusion.md`、`RPT-deep-investigation.html`。每保存一个文件，在输出中显式标注路径。
  > [!IMPORTANT]
  > **【累计耗时标注（Elapsed Time）】**：在构建链路时序表时，**每个服务节点必须标注距请求起始时间的累计耗时**，格式为 `+Xms`。取链路中最早的时间戳作为起始时间 `t0`，后续每个节点计算 `(当前节点时间 - t0)` 得到 elapsed。这对于超时场景极其有效：能直观看出耗时卡在哪一跳（如 `+50ms` → `+3200ms` 说明这一跳耗了 3 秒+）。在最终输出的链路时序表中，elapsed 必须作为独立列呈现。
  > [!IMPORTANT]
  > **【网关空消息提示检测器 (Gateway Header Auditor)】**：在解析 `log_cep_dist` 或是响应数据时，必须自动对比网关返回的 `X-fs-Fail-Code` 和 `X-fs-Fail-Message` 响应头。一旦发现接口返回了非零业务失败码（如 `320001401` 等拦截失败码）但 `X-fs-Fail-Message` 缺失或为空，必须在最终诊断中进行**高亮告警**，明确指出存在"因国际化/校验提示文本未回带至网关，引发网关防泄露保底 500 系统级 eXXXXX 弹窗"的配置缺失，避免盲目将其判定为系统底层崩溃。
- **若瓶颈点位于 APL Runtime**，需进一步调取函数源码进行代码级性能审计（如：检查是否穿透缓存、是否存在 N+1 查询、是否存在重聚合逻辑）。
7. **必要时升级**：若用户明确要求"继续深挖"，或首轮证据显示问题已超出单链路边界，则升级到对应 skill，而不是在 tracing 内继续堆查询。
8. **报告输出**：默认只回抛 Markdown 摘要和 evidence 文件。只有用户明确要求 HTML、主控进入报告升级路径，或 `review_required=true` 时，才生成 HTML / 人工审计相关产物。

## 扩展取证指引

当链路追踪发现的问题超出单请求边界时，通过 `need_further` 告知调用方需要的能力类型：
- 多源证据需按时间序关联 → 需要时间线聚合能力
- 出现资源体征异常（Pod 重启、GC 风暴、CPU/内存/线程池异常）→ 需要资源指标分析能力
- 堆栈已明确指向代码缺陷 → 需要代码级分析能力
- 证据更像脏数据、Schema 变更、写入延迟 → 需要数据查询验证能力
- 只有入口报错，没有足够链路锚点，且关心整体故障面 → 回抛调用方，附带已收集的证据
