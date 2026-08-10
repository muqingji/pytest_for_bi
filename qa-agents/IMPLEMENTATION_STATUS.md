# Implementation Status

更新时间：2026-08-11（A11/N26/N15 真实闭环，N07/N16 执行门禁已实现）

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| 阶段 0 契约与本地 Artifact | 已实现 | Envelope、状态、Schema、哈希、路径隔离 |
| N01 远端来源采集 | 已实现参考版 | 登记仓库、固定 commit、临时只读 clone、标题/行范围校验 |
| N02 ChangeSet | 已实现 | merge commit 强制 first-parent |
| N14 资产快照 | 已实现本地契约 | 当前无资产服务时明确输出空快照和 gaps |
| A02-A06 本地 Profile | 已实现保守基线 | 支持真实冻结材料；用于离线骨架与降级验证 |
| A02/A03/A05 Multica | 真实试点已通过 | Codex Runtime；真实冻结数据、消息审计、契约及来源绑定均通过 |
| A06 Multica | 后端真实试点已通过 | 最终 Artifact 为 `needs_human`；11 个对齐问题应进入 G01；A04 前端输入待接入 |
| G01 生产审核 Gate | 真实试点已批准 | 23 个问题均由 QA Owner 签署；请求与决策哈希、A06 哈希绑定有效；仅限测试设计试点，无生产发布权限 |
| G02 Multica 审核控制 | 真实放行完成 | QAA-24 由 QA Owner `muqj11262` 置 `done`，线上确认 `decision=approved`、`next_node=N25`；请求/决策/结果与 A08/A09/N04 上游哈希绑定有效；恢复点在 N25（仅测试设计试点，无生产发布权限） |
| N24/A07 | 真实 N24 已完成 | 风险为 `critical`，必测 `backend/contract/e2e`；规则优先，未知项才调用 A07 |
| A08/A09/N04/G02 | 人工恢复已闭环 | QAA-21 A08 v1.3.0 入库 `multica-stage10`（13 个父 Case）；QAA-23 A09 通过入库 `multica-stage11`；N04 `correction_attempt=3`、`valid=true`、`next_node=G02`（`multica-stage12`）；G02 QAA-24 放行至 N25 |
| QA 人工修正恢复 | 代码与协议已实现；试点恢复待重跑 | 已实现请求/决定/结果、Multica Issue、身份与哈希绑定、A08 v1.3.0 人工恢复输入和不重置预算规则；QAA-19 已 `done/authorized`；QAA-20 因缺绑定字段、附件交付和工具轨迹违规被拒，不得入库 |
| N25/A11/N26/A12/N15 | 真实闭环 | 主链 N25（stage13）→ A11（stage14，QAA-26 已入库）→ N26（stage15，无 unresolved）→ N15（stage16，3 generate_new + 11 manual_run）全部真实跑通；A12 建议折叠规则与测试就绪；N25 按 `expected[].layers` 注解做确定性分层收窄 `stage_two_nodes.py` 实现 N25/N26/N15 内容寻址驱动与绑定校验；`multica.py` 实现 A11/A12 Profile/输入准备/语义校验；A12 已实现：N26 策略强制/跳过/影响置信度规则、A12 建议折叠（只能扩大或升级、不得缩小或降级强制 Case）；CLI 与 Makefile 新增命令 |
| A14/A18-BE/N05/N06/G03 | 已实现后端参考切片 | Artifact-only pytest 候选、独立审查、安全检查、精确回流和人工 Gate |
| Oracle 离线评估 | 已实现参考版 | 路由、事实、对齐、开放问题、Gate 决策和测试义务；确定性规则、一对一义务匹配、文本/HTML 报告 |
| Multica 试点空间 | 已配置基础资源 | 独立 Workspace、Project、私有 Squad、组长和 A02/A03/A05/A06/A08/A09；无仓库绑定；A02/A03/A05/A06 已从离线 Runtime `6fa59d79` 重绑到在线 `5a1ecc9c` |
| Multica 生产编排 | 部分实现 | Stage 1→A06→G01→N24→A08→A09→N04→A08→A09→N04→人工节点→A08(v1.3.0)→A09→N04(valid)→G02(approved) 已真实跑通；恢复点 N25；N25/A11/N26/N15 驱动就绪，A11 真实审核待跑；全流程触发器仍待完成 |
| 结构化模型 Runtime | 已实现契约，默认关闭 | 固定 Provider/模型/Prompt、无工具、无留存、凭证和输出契约检查；待 Multica 生产绑定 |
| fs-qa-knowledge Provider | 消费端完成，上游阻塞 | 冻结版本缺少 capability manifest，且强制 `upload2fs`；状态为 `incompatible`，禁止进入 A08 |
| A13/A15/A16/A17-*/A18-* 自动化链路 | 已实现本地参考 Profile | 前端 Playwright、契约、E2E 与六个非功能专项的 artifact-only 生成和独立审查 Profile；共享生成/审查引擎 + 版本化 Profile，策略按层路由候选根目录与框架白名单；N05/G03 多 Manifest 汇合 |
| A01 歧义路由建议 Profile | 已实现 | N00 注册 5 个确定性模板，仅未知模式/触发不匹配时调用 A01 建议，N00 校验后生效；建议不能自行创建或执行流程 |
| N07/N16 环境与数据门禁 | 已实现 | 确定性节点 + 15 项测试：N07 环境指纹、8 类检查、指纹节流、失败即 blocked 路由 N16；N16 幂等键/无状态变化拒绝/未覆盖失败项拒绝/补偿清理；CLI 与 Makefile 命令就绪 |
| N08-N12/N17-N23 执行与门禁 | 未实现 | 按阶段 3-5 建设 |

本地保守 Profile 可以通过显式开发审批开关模拟运行到 G03；这不是生产审批，也不是当前
真实 Multica 链路的状态。真实试点已完成 G01 与 N24，也完成一轮 A08 自动修正和 A09
复审；第二轮 N04 因仍有 3 个阻塞问题且修正预算达到 2/2，升级到 QA 人工修正。QAA-19
已授权，但 QAA-20 人工恢复候选被契约与工具轨迹门禁拒绝，主链仍停在 A08 恢复重跑前，
G02 仍未启动。历史本地模拟中 24 条 Case 因 Oracle 需要人工确认而全部路由为
`manual_run`，不能
作为发布放行结论。完整离线评估仍暴露 A02/A06/A08/A09 的语义差距，下一阶段应先提升这些
核心能力，不扩展无真实闭环支撑的新 Agent。

G02 的试点审批身份已经按当前 QA Owner 决策固定为 `muqj11262 / qa_owner`。该配置只有在
新人工修正版重新通过 A09 和 N04、且 N04 输出 `valid=true` 后才生效；它不能批准当前无效
IR，也不能赋予生产发布权限。完整质量链路完成后，必须按策略迁移为其他
`qa_reviewer` 审批。

G02 不建设独立审批页面，Multica Issue 是审核状态源。进入 Gate 后系统创建并分配
`in_review` Issue；`done`、`blocked`、`cancelled` 分别编译为继续 N25、退回 A08 和终止。
请求、决定、结果与工作流检查点均内容寻址，重复状态同步不会重复恢复下游。当前 Multica
CLI 没有 Issue 状态 webhook，参考实现通过确定性轮询 Adapter 同步；原生 webhook 可用后只
替换触发 Adapter。

预算耗尽后的人工修正恢复也使用 Multica Issue。真实 `pilot-001` 已创建 QAA-19，绑定 3 个
阻塞错误和 1 个警告的四条修正指令；QA Owner 已将其改为 `done`，系统生成并保留
A08 v1.3.0 `human_directed` 修正输入。修正轮次记为 3，自动预算仍保持 2，不发生静默重置。
QAA-20 是第一次人工恢复 Multica 运行：本地 workdir 虽有 13 个 Case 的语义修正稿，但输出
缺少 `schema_version/workflow_run_id/source_snapshot_id/input_bundle_hash/status` 绑定字段，
且以附件/状态副作用交付而非最终 text JSON，工具轨迹也超出只读边界，因此被记录为
`rejected_by_contract_and_tool_trace_gate`，不得进入主链。A08 Multica 指令已发布为加固版 v1.3.0；下一步以同一授权输入重跑 A08，随后强制 A09/N04。

Multica 真实链路的 A02、A03、A05、A06、A08 和 A09 均保留完整消息审计。G01 的 23 个
问题已由 QA Owner 逐项确认，N24 输出 critical 风险策略。第一轮 A09/N04 阻断了缺少正式
Oracle 字段、不可执行负向断言和覆盖缺口；QAA-11 修正后，QAA-13 复审将问题收敛为结果集
筛选的中英文指标名参数配对、不可解析的期望引用、无键本地化集合匹配和复合 Oracle 来源
范围四项。第二轮 N04 当前明确 `next_node=human`、`g02_status=not_started`，不得继续自动
回流或进入 G02。动态关联继续遵循冻结规则：所有 what/what-list 均属于动态关联，不采用
A09 第一轮提出的工单主题限制。QAA-12 仅作为 A08 v1.2.1 协议影子候选保留，不替换主链
已经验收的 QAA-11 Artifact。


### 2026-08-10 人工恢复实跑更新
- QAA-21 A08 v1.3.0 人工恢复已接受并入库 `multica-stage10`。
- QAA-22 A09 因 `status=approved` 违约拒收；加固 A09 指令后 QAA-23 通过并入库 `multica-stage11`。
- N04 `correction_attempt=3` 输出 `valid=true`、`next_node=G02`，Artifact 在 `multica-stage12`。
- G02 Multica 审核 Issue（QAA-24）已由 QA Owner 置为 `done`，`sync-g02-after-human-pilot`
  实际查询线上确认 `decision=approved`、`next_node=N25`，决策与结果 Artifact 已写入
  `runs/pilot-001/g02/`，主链可在 N25 恢复。

### 2026-08-10 阶段 2 自动化 Profile 更新
- 按设计文档「A13-A18-* 领域差异优先通过 Profile、规则包和工具白名单表达」实现共享生成/审查
  引擎：A13 前端 Playwright、A15 契约、A16 E2E、A17-PERF/SEC/A11Y/COMPAT/RES/DATA 六个非功能
  专项的 artifact-only 生成 Profile，以及 A18-FE/CT/E2E 与六个非功能专项的独立审查 Profile。
- `policies/automation-target-policy.json` 新增 `layer_profiles`：按层声明 generator/reviewer
  Profile、候选根目录（`generated/{frontend,backend,contract,e2e,non_functional}`）和框架白名单
  （pytest/playwright），生成与审查使用不同 Runtime 身份。
- N05 增强：回流路由按 `generator_profile` 动态解析；候选路径必须位于该 Profile 在策略中声明的
  层根目录，跨层或越权写入仍按安全违规拦截。
- 本地 workflow 按执行计划中的层/非功能类型分发生成、逐层独立审查，多 Manifest 汇合到
  N05/G03；单层行为与既有 A14/A18-BE 链路完全兼容。
- 新增 `tests/test_automation_profiles.py` 覆盖各 Profile 生成、审查、N05 正负向校验与
  代码-策略一致性；新增多层级纵向测试验证 A13/A14/A15/A16/A17-PERF 全链路到 G03。
- 实现 A01 Workflow Route Advisor：N00 以 `WORKFLOW_TEMPLATES` 注册表确定性选择模板并给出
  执行深度（L1/L2/L3），未知模式支持 `route_hint`、触发类型不匹配可建议唯一匹配模板；A01
  只输出 `advice_only` 建议，最终路由仍由 N00 校验决定，无有效建议时停在 A01
  `needs_human`。新增 `tests/test_workflow_route.py` 覆盖确定性、建议、歧义升级与纵向链路。


### 2026-08-10 晚间交接更新（G02 放行与阶段二驱动就绪）

- 真实主链已推进到 N25：A08 v1.3.0 人工恢复（QAA-21）入库 `multica-stage10`，A09
  （QAA-23）入库 `multica-stage11`，N04 `valid=true`/`correction_attempt=3` 入库
  `multica-stage12`，G02（QAA-24）由 QA Owner `muqj11262` 置 `done` 后线上确认
  `approved`/`next_node=N25`，恢复点 N25。
- 阶段二真实链驱动已就绪：`run_n25_after_g02`/`run_n26_after_a11`/`run_n15_after_n26`
  （内容寻址绑定校验）、A11 Profile/输入准备/语义校验、CLI 与 Makefile 4 个新命令、
  `tests/test_stage_two_nodes.py` 与 A11 prepare/ingest 测试；全量测试 `137 passed`。
- Runtime 修复：A02/A03/A05/A06 重绑到在线 Codex Runtime `5a1ecc9c`（此前离线
  `6fa59d79`），与 A08/A09 一致；workspace-manifest 已同步。
- 未完成事项：
  1. 编写并发布 `multica/agent-instructions/a11-v1.0.0.md`，创建 A11 Multica Agent
     （`multica agent create --runtime-id 5a1ecc9c-8e48-4345-8d5e-be0efb3b9a54`）并登记
     workspace-manifest。
  2. `make run-n25-after-g02-pilot`（stage13）→ `make prepare-multica-split-review-pilot`
     （a11-input.json）→ Multica 桌面端交给 A11 Agent → `ingest-multica` 入库
     `multica-stage14` → `make run-n26-after-a11-pilot`（stage15）→
     `make run-n15-after-n26-pilot`（stage16）。
  3. 核对真实 A08 产物 `test-design-ir/1.1` 与 N25/A11 契约版本一致。
  4. 阶段 3-5（N07-N12/N16-N23 执行与门禁）未实现，按设计文档继续建设；A12 已实现并带独立评估测试。
  5. 本次改动已推送远端 `qa_agent` 分支（未 merge main）。

### 2026-08-10 深夜实跑更新（A11 真实运行与上下文超限修复）

- 主链本地产物已从 Multica 线上恢复并逐哈希核对：`multica-stage10`（A08，QAA-21，
  `edb58b4f…`）、`multica-stage11`（A09，QAA-23，`9cafab64…`）、`multica-stage12`
  （N04 `valid=true`，`35e954e5…`）、G02 请求/结果（request `f46f883b…`、outcome
  `0bc6ed31…`）全部与 QAA-24 线上绑定哈希一致；N25 已真实编译 stage13（13 父 → 14 子）。
- A11 Multica Agent 已创建（QAA-25/QAA-26，runtime 绑定在线 Codex `6fa59d79`）并登记
  `multica/workspace-manifest.json`；指令发布为 `multica/agent-instructions/a11-v1.0.0.md`。
- 真实运行发现并修复缺陷：A11 输入把完整父/子 Test Case IR 都发给 Agent（磁盘 175KB、
  每轮约 48K tokens），模型在读取全部输入后进入长时间静默生成，两次被 Codex Runtime
  `semantic_inactivity_timeout=10m` 看门狗终止（`codex_semantic_inactivity`）。修复：
  `prepare_multica_split_review_input` 改为紧凑审查范围（保留 id/expected/layer/parent
  绑定/继承一致性标志，去掉重复的 test_data/steps/cleanup/oracle 大字段），磁盘降至约
  57KB；A11 指令明确最终 JSON ≤ 10KB、rationale ≤ 60 字、只输出真实问题。新增
  `test_a11_input_is_compact_review_scope`。
- 当前进展：QAA-26 携带紧凑输入的真实 A11 审核运行中；完成后 `ingest-multica` 入库
  `multica-stage14`，再 `make run-n26-after-a11-pilot`（stage15）与
  `make run-n15-after-n26-pilot`（stage16）。


### 2026-08-11 更新（A11/N26/N15 真实闭环与 N07/N16 执行门禁）

- 主链阶段二真实闭环：`run-n25-after-g02-pilot` 产出 stage13（13 父 → 14 子，N25
  `e8505b16…`）；A11 Agent（QAA-26）真实运行 3m01s 后 `ingest-multica` 入库 stage14
  （`b6e37ba3…`，`completed_with_gaps`/`approved=true`）；`run-n26-after-a11-pilot` 产出
  stage15（`64bd7dcb…`，无 unresolved）；`run-n15-after-n26-pilot` 产出 stage16
  （`89764afd…`，执行计划 3 `generate_new` + 11 `manual_run`）。
- N25 分层收窄（A11-ISSUE-001，warning 升级为 N25 修复）：`case_compiler.py` 新增
  `_narrow_expected_for_layer`，按 `expected[].layers` 注解确定性收窄子 Case 期望，空子
  Case 保护（未注解时全量继承，向后兼容）；新增 3 项测试。真实 A08 尚未在 expected 上
  标注 `layers`，收窄对当前产物不生效，记为 A08 指令后续改进项。
- N07/N16 实现（设计文档 §17）：`env_precheck.py` 提供 `run_n07_env_precheck`（部署
  commit/依赖健康/测试账号/Flag/租户/测试数据/运行时/命名空间/资源锁 8 类检查、环境指纹
  与内容哈希、同指纹无原因重检节流、失败即 blocked 路由 N16）与 `run_n16_env_fix`
  （期望态/执行前态/结果/补偿/幂等键；幂等键不符、`performed` 而无状态变化、未覆盖全部
  失败项均拒绝；动作失败则 blocked 转人工）。修复 `ArtifactStatus` 缺失 `blocked` 成员。
- 接线：CLI 新增 `run-n07-env-precheck`/`run-n16-env-fix`，Makefile 新增
  `run-n07-env-precheck-pilot`/`run-n16-env-fix-pilot`；`tests/test_env_precheck.py`
  15 项覆盖正/负向（含节流、无状态变化拒绝、未覆盖失败项、CLI 端到端）。
- 全量回归：`pytest tests -q` → `181 passed`（上轮 163 + N25 3 项 + N07/N16 15 项）。
