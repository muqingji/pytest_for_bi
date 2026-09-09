# Implementation Status

更新时间：2026-09-08（本地质量链路和报告可读性已按 20260901 运行刷新；N08 仍是
0/7 通过，N11 结论为 `blocked/pending`。这不是生产准出通过，生产隔离 Runner 与外部
发布/缺陷/MR Adapter 仍未接入。）

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| 阶段 0 契约与本地 Artifact | 已实现 | Envelope、状态、Schema、哈希、路径隔离 |
| N01 远端来源采集 | 已实现参考版 | 登记仓库、固定 commit、临时只读 clone、标题/行范围校验 |
| N02 ChangeSet | 已实现 | merge commit 强制 first-parent |
| N14 资产快照 | 已实现本地契约 | 当前无资产服务时明确输出空快照和 gaps |
| A02-A06 本地 Profile | 已实现保守基线 | 支持真实冻结材料；用于离线骨架与降级验证 |
| A02/A03/A05 Multica | 真实试点已通过 | Codex Runtime；真实冻结数据、消息审计、契约及来源绑定均通过 |
| A06 Multica | 后端真实试点已通过 | 最终 Artifact 为 `needs_human`；11 个对齐问题应进入 G01；A04 前端输入待接入 |
| G01 生产审核 Gate | 适配器已实跑；置信运行已签署放行 | `pilot-001` 的 23 项旧审批保留。置信运行 QAA-32 已由 QA Owner `muqj11262` 结构化评论签署 `approved`（request `90b67080...` / decision `8f0393d7...` / outcome `d91f9bc2...`），`policy_scope=pilot_test_design_only`，无生产发布权限；Issue 状态不能单独批准 |
| G02 Multica 审核控制 | 真实放行完成 | QAA-24 由 QA Owner `muqj11262` 置 `done`，线上确认 `decision=approved`、`next_node=N25`；请求/决策/结果与 A08/A09/N04 上游哈希绑定有效；恢复点在 N25（仅测试设计试点，无生产发布权限） |
| N24/A07 | 真实 N24 已完成 | 风险为 `critical`，必测 `backend/contract/e2e`；规则优先，未知项才调用 A07 |
| A08/A09/N04/G02 | 人工恢复已闭环 | QAA-21 A08 v1.3.0 入库 `multica-stage10`（13 个父 Case）；QAA-23 A09 通过入库 `multica-stage11`；N04 `correction_attempt=3`、`valid=true`、`next_node=G02`（`multica-stage12`）；G02 QAA-24 放行至 N25 |
| QA 人工修正恢复 | 真实闭环 | QAA-19 `done/authorized`；QAA-20 因契约和工具轨迹违规被拒；QAA-21 合法恢复后重新经过 A09/N04/G02，不重置自动预算 |
| N25/A11/N26/A12/N15 | 真实闭环 | 主链 N25（stage13）→ A11（stage14，QAA-26 已入库）→ N26（stage15，无 unresolved）→ N15（stage16，3 generate_new + 11 manual_run）全部真实跑通；A12 建议折叠规则与测试就绪；N25 按 `expected[].layers` 注解做确定性分层收窄 `stage_two_nodes.py` 实现 N25/N26/N15 内容寻址驱动与绑定校验；`multica.py` 实现 A11/A12 Profile/输入准备/语义校验；A12 已实现：N26 策略强制/跳过/影响置信度规则、A12 建议折叠（只能扩大或升级、不得缩小或降级强制 Case）；CLI 与 Makefile 新增命令 |
| Case 可执行性分类 | 已实现确定性门禁 | 所有输入 Case 均分类为 `machine_executable`、`capability_missing`、`manual_only` 或 `invalid_case`；不猜测缺失操作、断言、响应路径或数据证据 |
| A14/A18-BE/N05/N06/G03 | 已实现后端参考切片 | Artifact-only pytest 候选、独立审查、安全检查、精确回流和人工 Gate；网络候选必须绑定 IDL 注册操作，setup 请求/资源 ID 提取必须匹配已验证契约，A18-BE 接收同一份契约独立复核 |
| N29 候选落盘 | 已实现参考版 | 仅在工作流 Artifact 输出目录落地 hash 绑定候选；`mr_disposition=not_requested`；禁止业务仓写入与外部 landing root |
| N08 受控环境 Runner | 已实现参考版 | `local_process_reference` 仍拒绝网络/Secret；注册环境类（如 `staging_112`/`112`）可走 `controlled_env_reference`，仍非生产隔离，Secret 仅按 env 名从宿主注入且不入 Artifact |
| A19/N18/Flaky | 已实现参考版 | A19 本地保守归因；N18 读取 N08 coverage_summary；`flaky-quarantine/1.0` 计入覆盖缺口，P0/P1 或高风险隔离阻塞发布 |
| 单元测试生成策略 | 已暂停 | `test_level=unit` 在 N15 以 `paused_existing_developer_unit_coverage` 跳过；A14 仅生成服务端 API、集成和功能测试 |
| A22/N28/N27 自主测试数据构造 | 已实现首个 112 纵向切片 | A22 从 Case 语义输出 `test-data-intent/1.0`；N28 用可追溯 BI 能力目录生成资源 DAG；N27 允许 setup/cleanup 写入并强制 namespace、操作配对、资源 ID、只读 readiness 和 Secret 边界 |
| A22 确定性意图推断 | 已实现 | `infer_resource_intents`/`infer_data_intent` 覆盖 9 类资源（聚合/普通/计算/同环比指标、统计图、报表、交叉表、拼表、自定义维度），唯一命中才给 `data_intent`，歧义保持 unresolved |
| 已验证契约 → recipe 注册 | 部分落地 | `ordinary-metric-create` 已入目录（add_new_agg_rule filterLists=[]，N27 全量校验通过）；custom_dimension/joined_table/stat_chart/pivot/report 以候选形式登记，证据闭合前不可执行 |
| 环境清单变量解析 | 已实现参考版 | `env_inventory.enrich_plan_with_inventory` 在 N28/N27 之间解析字段 id/枚举/目录变量，`runtime_required` 不猜测；CLI `--inventory` 接入 |
| backlog 自适应候选生成 | 已实现参考版 | `recipe_adapter` + `prepare-recipe-candidates` 从已验证契约产出 `bi-recipe-candidates.json`（含组合明细场景），`verification_requirements` 强制证据门禁；`bi-recipe-adapter` skill 注册 D01/A22 |
| 112 数据生命周期执行 | 真实通过 | `CASE-FUNC-RESULT-FILTER-DETAIL-112` 创建带结果集筛选的隔离指标、回查、调用真实查看明细接口断言 `s307011535` 和动态指标名、finally 删除；独立回查无 namespace 残留 |
| 可追溯 fs-bi 契约 | 已冻结 | OpenAPI `info.version` 和 `x-contract-source.ref` 固定为 MR commit `c6b785344c6973b6d6fc5bb108c45b3971f36c64`，165 个真实 gateway 路由，生成器测试通过 |
| Oracle 离线评估 | 已实现参考版 | 路由、事实、对齐、开放问题、Gate 决策和测试义务；确定性规则、一对一义务匹配、文本/HTML 报告 |
| Multica 试点空间 | 已配置基础资源 | 独立 Workspace、Project、私有 Squad、组长及 A02/A03/A05/A06/A08/A09/A11；无仓库绑定；A11 于 2026-08-11 从离线 `6fa59d79` 重绑到在线 `5a1ecc9c` |
| 需求工作流中心 | 已实现并真实同步 | 一需求一稳定父卡、一触发一 Run；QAA-1 展示 35 个节点、5/35 和唯一 G01 人工事项。QAA-1=`in_review`、内部 Run QAA-27=`in_progress`、人工 Gate QAA-32=`in_review`；Run 与 Gate 使用不同状态映射，避免 Multica stage 自动推进误把 Gate 置为 done。Projection 内容寻址并同步状态、正文、Autopilot 审计、metadata、自定义属性、节点分类及历史 Run 结论 |
| Multica 生产编排 | 部分实现 | 已创建并实跑一需求一 Autopilot `8f26a3bf...`；失效 Claude Runtime 的首次运行 401 被保留，切换在线 Codex Runtime 后连续两次完成只读对账。Stage 1→A06→G01 和旧试点 Stage 2/质量尾链均有真实证据；原生事件触发器及外部系统 Adapter 仍待接入 |
| 结构化模型 Runtime | 已实现契约，默认关闭 | 固定 Provider/模型/Prompt、无工具、无留存、凭证和输出契约检查；待 Multica 生产绑定 |
| fs-qa-knowledge Provider | 消费端完成，上游阻塞 | 冻结版本缺少 capability manifest，且强制 `upload2fs`；状态为 `incompatible`，禁止进入 A08 |
| A13/A15/A16/A17-*/A18-* 自动化链路 | 已实现本地参考 Profile | 前端 Playwright、契约、E2E 与六个非功能专项的 artifact-only 生成和独立审查 Profile；共享生成/审查引擎 + 版本化 Profile，策略按层路由候选根目录与框架白名单；N05/G03 多 Manifest 汇合 |
| A01 歧义路由建议 Profile | 已实现 | N00 注册 5 个确定性模板，仅未知模式/触发不匹配时调用 A01 建议，N00 校验后生效；建议不能自行创建或执行流程 |
| N07/N16 环境与数据门禁 | 已实现 | 确定性节点 + 15 项测试：N07 环境指纹、8 类检查、指纹节流、失败即 blocked 路由 N16；N16 幂等键/无状态变化拒绝/未覆盖失败项拒绝/补偿清理；CLI 与 Makefile 命令就绪 |
| N08 自动化执行 | 已实现参考切片 | 认证 N07/A18/N05 producer/contract，绑定 generation/manifest/candidate 哈希；响应断言和 Oracle matcher 严格白名单，生命周期失败区分 setup/readiness/assertion-or-product/cleanup/residue；本地 Runner 非生产隔离，生产 Adapter 待接入 |
| N09-N12/N17-N23 归因与门禁 | 已实现确定性参考链并实跑 | N10 重试预算、N17 未执行用例收口、N18 信号、N09 证据/指纹聚类、N20 缺陷去重、N11 决策、N12 JSON/Markdown/HTML 报告及 N13/N19/N23 审计已实现。`ContractError`/`AssertionError` 会解析为结构化失败详情，并透出到 Markdown/HTML；缺执行证据时仍严格输出 `inconclusive`/`blocked`。生产发布/MR/Bug 写入 Adapter 仍未接入 |
| 服务端全链实跑 | 已到最终报告；无待执行项 | `multica-pilot-001` 历史尾链为 `inconclusive/pending`：可执行 1、实际执行 1、延期 13、pending 0。CASE-BE-002-BACKEND 的四类指标错误码和实际名称已在 112 复跑，但精确中英文文案及移除筛选后的正常响应未完整覆盖，因此结果为 blocked，不伪装为通过 |


### TODO: 8 卡服务端流程接入 E2E 生成器（A16）

- 当前 8 卡 / 服务端质量尾链**跳过 e2e 层**：N15 `skip_layers={"e2e"}`，N17/N11 不把 e2e 当必测。
- 准出以服务端（backend/contract）执行结果为准。
- 原因：A16 端到端生成器尚未接入 8 卡 C5，不能自动点页面。
- 后续：接入 A16 后，从 `SERVER_QUALITY_SKIPPED_LAYERS` 和 `ensure_n15_execution_plan` 的 skip 中移除 e2e，重新纳入执行与准出。

### 2026-08-21 任意 Case 自动化能力门禁更新

### 2026-09-08 本地质量链路刷新

- 以 `generated/multica-eight-card-run-20260901/current/workflow-center-spec.json` 为准；
  N11/N12 已重新计算为 `blocked/pending`，执行结果是 7 执行、0 通过、7 失败、4 按策略跳过。
- 官方测试入口恢复：`make -C qa-agents test` 可收集 `scripts`，当前基线为 `727 passed`。
- 统计图编译器输出补齐 `validity_contract`、`integrity_probes` 和 `asset_folder_name`；
  已有资产发现候选保留目录元数据，避免保留型统计图被 N27 误拒。
- Multica 有 usage 时记录最后调用的 provider/model；没有 usage 时记录 `unknown/unknown`，
  不再把本机 `~/.codex/config.toml` 伪造成远端运行来源。
- N09 支持 Oracle 字段差异、`ContractError` 和 `AssertionError`；20260901 的 7 个失败簇
  detail 均非空。报告新增 Failure Details，保留 `blocked`，不把产品缺陷或造数失败洗成通过。

### 2026-08-21 任意 Case 自动化能力门禁更新

- 新增 `case-executability/1.0` 分类契约。结构化生命周期、注册 `operationId`、有效响应断言、
  可求值 Oracle、setup/readiness 配对和 cleanup guard 全部满足时才允许
  `machine_executable`；能力或证据不完整时 fail-closed，不生成看似可运行的候选。
- A14/N05 对网络候选加载真实 `idl/http` 操作目录；setup body 必须包含已验证契约要求字段，
  资源 ID 只能从契约 `response_id_paths` 提取。A18-BE 复核输入透传并绑定同一份
  `verified_setup_contracts`，可以独立核对生成结果。
- Runner 拒绝空或未知 `expect`、未知自动 Oracle matcher；仅有效断言可将生命周期证据标为
  `verified=true`。N08 shard 和汇总产物输出 setup、readiness、产品/断言、cleanup、residue
  失败类别，便于区分环境建数问题与产品失败。
- 当前完成的是“任意 Case 都有确定性去向”，不是“任意 Case 都必然自动执行成功”。
  PC-001–PC-007 的全部能力 Adapter、双语/动态 Oracle、清理契约和 112 实况验证仍为
  `in_progress`；未执行新的 112 写操作或以模拟证据替代实况结果。

### 2026-08-11 晚间更新（候选落盘 / 受控 Runner / 质量尾链增强）

- N29 `land-automation-candidates`：在 A18 批准且 N05 通过后，将候选物化到运行目录下的
  `automation-workspace/`，输出内容寻址 `n29-candidate-landing` 与 receipt；默认不创建 MR。
- N08 增加 `controlled_env_reference`：仅当执行策略 `controlled_environment` 与 N07
  `environment_class` 同时授权时允许网络和 Secret env 名；生产 / production_isolation 强制拒绝。
- 质量尾链增强：A19 本地保守失败归因；N18 汇总 shard coverage；Flaky 隔离清单使关键 Case
  隔离时 N11 直接 `blocked`。
- CLI：`land-automation-candidates`、`run-server-quality --flaky-quarantine`；Makefile
  `land-automation-candidates-pilot`。
- 全量回归：`pytest tests -q` → `270 passed`。

### 2026-08-11 112 数据构造 Agent 与真实集成执行

- A14 收窄为服务端 API/集成/功能生成；显式 unit Case 不再进入生成 Agent。
- 新增 A22 `TestDataPlannerAgent`、`test-data-plan/1.0`、N27 校验、
  `policies/test-data-policy.json` 和 `prepare-test-data` CLI。
- 新增自主路径：A22 数据意图、N28 确定性 DAG 编译、官方资料/代码/契约/112 探针来源清单
  和 BI 能力目录。Case 不再需要手写 setup/cleanup；旧显式资源计划只作为兼容输入。
- 数据计划不是全只读：A22 只生成计划，Runner 被明确授权在 112 的 setup/cleanup 阶段
  创建和删除隔离测试资源；readiness 仅做只读回查。
- `CaseRunner.execute` 支持 setup/readiness/test/finally cleanup；失败时仍回收，证据只记录操作、
  状态、HTTP 状态和响应哈希，不落 Secret 或完整响应。
- 112 真实执行 `CASE-FUNC-RESULT-FILTER-DETAIL-112`：隔离指标创建和回查成功；真实查看明细
  返回 `s307011535` 且包含 namespace 指标名；删除返回成功，独立字段回查确认无残留。
- `CASE-AUTO-RESULT-FILTER-DETAIL-112` 仅提供结果集筛选数据意图和测试步骤，由能力目录自动
  补齐聚合指标创建、回查及清理。14 个真实 N25 Case 的规划审计解析 1 个聚合指标部分，其他
  未支持数据集进入 `capability_adapter_backlog`，不生成用户人工链路填写任务。
- 当前数据写白名单先覆盖 fs-bi 主题、聚合指标、计算指标和自定义维度的成对接口。对象/字段、
  报表、统计图、拼表、交叉表、驾驶舱、目标和首页布局允许在 112 构造，但对应 Adapter 仍需
  找到并冻结创建/删除契约后才能自动执行。

本地保守 Profile 可以通过显式开发审批开关模拟运行到 G03；这不是生产审批。真实试点已经
完成 G01、人工恢复、G02 和阶段二 N15，并已用明确标识的本地 reference 环境把服务端尾链
运行到最终报告。该运行不是 staging 或生产隔离，不能作为发布放行结论。完整离线评估仍暴露
A02/A06/A08/A09 的语义差距；生产隔离 Runner、真实环境/人工执行证据及外部发布 Adapter
仍是阻塞项。

新的 `multica-confidence-20260811-01` 与旧试点独立：A02/A03/A05/A06 已验收；QAA-32 绑定
`g01-comment-table/1.0` 并由 QA Owner 结构化签署 `approved` 后，N24 → A08 → A09 → N04
自动修正回流已真实推进到 `correction_attempt=2/2`。当前 N04 `valid=false`、`next_node=human`
（3 个阻塞），G02 对本置信运行尚未打开。`sync-g01-multica` 对无评论、部分填写、非授权成员、
旧请求哈希和仅状态变更全部 fail-closed。

Multica 日常视图已拆成两个项目：`QA 需求工作流中心` 只保留需求级父卡，
`QA 内部执行与审计` 保留 31 张运行、节点、人工 Gate 与历史审计卡。需求父卡通过
`qa_item_type=workflow` 筛选；“我的待处理”再叠加字符串 metadata `qa_action_required=true`
（或自定义属性 `需要我处理=true`）。Multica CLI 的 StringSlice/JSON 双层解析要求将后者写成
`--metadata '"qa_action_required=""true"""'`。内部卡不能进入这两个用户视图。

G02 的试点审批身份已经按当前 QA Owner 决策固定为 `muqj11262 / qa_owner`。该配置只有在
新人工修正版重新通过 A09 和 N04、且 N04 输出 `valid=true` 后才生效；它不能批准当前无效
IR，也不能赋予生产发布权限。完整质量链路完成后，必须按策略迁移为其他
`qa_reviewer` 审批。

G02 不建设独立审批页面，Multica Issue 是审核状态源。进入 Gate 后系统创建并分配
`in_review` Issue；`done`、`blocked`、`cancelled` 分别编译为继续 N25、退回 A08 和终止。
请求、决定、结果与工作流检查点均内容寻址，重复状态同步不会重复恢复下游。当前 Multica
CLI 没有 Issue 状态 webhook，参考实现通过确定性轮询 Adapter 同步；原生 webhook 可用后只
替换触发 Adapter。

预算耗尽后的人工修正恢复也使用 Multica Issue。真实 `pilot-001` 的 QAA-19 授权后，QAA-20
因契约和工具轨迹违规被拒收；QAA-21 的 A08 v1.3.0 合法恢复已入库，并重新经过 QAA-23
A09、N04 和 QAA-24 G02 后进入 N25。自动预算始终保持 2，没有静默重置。

Multica 真实链路的 A02、A03、A05、A06、A08 和 A09 均保留完整消息审计。旧试点 G01 的
23 个问题已由 QA Owner 逐项确认，N24 输出 critical 风险策略；后续人工恢复、G02 和阶段二
已闭环。QAA-12 仍仅作为 A08 v1.2.1 协议影子候选保留，不替换主链 Artifact。


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
- 后续结果见下一节：QAA-26 已完成并入库，N26/N15 已闭环。


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

### 2026-08-11 更新（N08、审计恢复与 Multica 影子复跑）

- 从 QAA-26 真实消息流重建 stage13-16，哈希逐项匹配 `e8505b16…`、`b6e37ba3…`、
  `64bd7dcb…`、`89764afd…`；修复运行清单仍停 G02 的问题，并为 N25/N26/N15 增加原子
  checkpoint 更新。
- N08 已实现：认证 N07/A18/N05 producer 与 payload contract，并绑定
  generation/manifest/candidate 哈希；无 shell 并行分片，
  最小环境、超时、脱敏日志、JUnit 校验与原始证据持久化，业务失败进入 N09，基础设施失败
  进入 N10。当前 `local_process_reference` 明确不是生产隔离，且拒绝网络与 Secret。
- A18/N05 增加内容绑定；修复空 `secrets: []` 被脱敏破坏类型及 Envelope Schema 缺少
  `blocked`。新增 N08 和安全/语义回归测试。
- A11 从离线 `6fa59d79` 重绑在线 `5a1ecc9c` 后实跑 task
  `2cdb00fd-c20d-482c-a626-9d62a2b1c611`，2 分 05 秒完成。影子输出漏报
  `CASE-CT-005` 跨层责任未收窄；新增确定性 A11 门禁后拒收，未覆盖主链 Artifact。
- 全量回归：`pytest tests -q` → `197 passed`。

### 2026-08-11 独立 Multica 置信实跑

- 建立 `multica-confidence-20260811-01`（父 Issue QAA-27），从冻结输入重新运行
  A02/A03/A05。A02 首次接受；A03 首次因 `input_bundle_hash=null` 被契约门禁拒绝；A05
  首次因 comment/metadata、写文件工具和 comment 交付被权限门禁拒绝。
- A03/A05 指令加固并发布 v1.1.1 后，第二次 Task 均正式 ingest 通过。接受 Artifact 哈希：
  A02 `b6ca118b...`、A03 `366c185c...`、A05 `03e7cfe7...`。
- A06 在 QAA-31 真实运行并通过完整消息审计和 ingest，Artifact `6da70bda...`，状态
  `needs_human`，9 个 finding。新 G01 请求含 15 项，request hash `90b67080...`。
- **G01 已签署放行**：QAA-32 由 QA Owner `muqj11262` 提交结构化评论（含 request/policy 哈希、
  15 项 disposition/rationale/owner 与冻结 `test_rules`），decision
  `sha256:8f0393d7b10ea5aa84499dd3ee6b270ee6136bdfc0b0a0594b2a64c1fbbb8997`，outcome
  `sha256:d91f9bc2e30094ab38b29bea7ce5ab1691f31c5ce709cb754f2de22d1b0999d1`，
  `next_node=N24`，`policy_scope=pilot_test_design_only`（无生产发布权限）。产品口径冻结要点：
  多限制任意一条提示；多指标展示全部名称；文案跨端点一致且不写“统计图”；仅四类不支持场景；
  中英文案冻结；错误码平台证据、稳定动态关联 ID、空字段加固本轮延后。
- **N24 已完成**（`multica-stage3`）：`sha256:052204851f780c290abdf204902b4c6e3aa232bfb75af8e16610f2f24c04b703`，
  `risk_level=critical`，`required_layers=[backend, contract, e2e]`。
- **A08/A09/N04 自动修正主链**（自动预算 max=2，不复用 `pilot-001` 审批/恢复）：
  - A08 first-pass QAA-33：多次契约拒收后指令加固 `a08-v1.1.1`（`allowed_modes`、
    `test_data` 对象、oracle `type`+`source_ref`），最终接受
    `sha256:c1ae5fc90a065287d33899695cfc715d9d470e65e3caffa0fe6f8c07f7fff6aa`（7 父 Case）→
    `multica-stage4`。
  - A09 QAA-34：`needs_human`，4 blocking，`sha256:3834bbdf...` → `multica-stage5`。
  - N04 stage6：`valid=false`，`next=A08`，attempt **0/2**，blocking=4，
    `sha256:7acdd7c135f71695aeb6daca461c3e955e632ed23c869fde027ad6f8ed4a3297`。
  - A08 corr#1 QAA-35：缺 top-level `status` 拒收后指令 `a08-v1.2.1`；接受
    `sha256:fab2c2fcefd11c2b8381ec48c1f1d87de598b0467165d819726f16e16063dfb0` →
    `multica-stage7`。
  - A09 QAA-36：5 blocking，`sha256:cda51041...` → `multica-stage8`。
  - N04 stage9：`valid=false`，`next=A08`，attempt **1/2**，blocking=5，
    `sha256:0295cdb360773cea97553b5df8f0941b71578d250987ff8b03f1f1929dc56186`。
  - A08 corr#2 QAA-37：`correction_resolutions` 必须**恰好**覆盖当前 A09 反馈 id
    （005–009，不得混入旧 001–004）；接受
    `sha256:bccd074cc7e88b5752124c2ad5bd6dbb2bb125994f5e96be9c10a9ff50604fa2` →
    `multica-stage10`。
  - A09 QAA-38：接受 `sha256:7885579dab8e6de90fe7bad6c69c7c22c0e5f9966b1fdfc142c45334f6d07b76`
    → `multica-stage11`（剩余 A09-ISSUE-010/011/012）。
  - N04 stage12：**预算耗尽** `valid=false`，`next_node=human`，attempt **2/2**，blocking=3，
    `sha256:c61f8f1aa7de5de5eada2034f408a286b47c9859c2a6f7c688656519737c85e3`。
- **当前边界（本置信运行）**：停在人工修正升级路径，**未**打开本运行的 G02，也**未**进入
  N25。不得把 `pilot-001` 已闭环的 G02/N25 尾链冒充为本运行进度。剩余阻塞语义：
  PC-002 四类指标实际名称 Oracle 不全、PC-003-E02 多关联成功路径与冻结“>3 不支持”冲突、
  PC-004-E02 动态关联成功路径与冻结“What/WhatList 均不支持明细”冲突。
- **下一步**：准备 human correction Issue（展示最新 A08/A09/N04 哈希与 3 个阻塞），授权后
  生成人工定向 A08 恢复输入 → 再经 A09/N04；仅当 N04 `valid=true` 才可打开本运行 G02。
- 审计清单位于 `runs/confidence-20260811-01/audit-summary.json` 与 `audit-summary.md`。
- 已清理 Multica 历史看板状态；人工 Gate 仍以独立决策契约为准，Issue 列状态不能单独作为
  放行证据。`sync-multica-issue-card` 仅在正式 Artifact/运行/输入哈希/工具审计一致时置
  Agent 卡 `done`。
- 全量回归基线：`pytest tests -q` → `200 passed`（本轮文档同步不改代码）。
