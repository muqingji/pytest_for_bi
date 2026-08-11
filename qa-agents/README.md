# QA Multi-Agent System

该目录是 [QA_AGENT_DESIGN.md](../QA_AGENT_DESIGN.md) 的可运行参考实现。目前完成阶段 0
基础能力、阶段 1/2 真实试点链路，以及阶段 3 的环境门禁和受控执行参考切片。不声称已经
完成生产隔离 Runner、失败归因、完整质量门禁或发布集成。

## 当前已实现

- Artifact Envelope、完整状态枚举、内容哈希和路径受限的 Artifact Store。
- A14 仅生成服务端 API、集成和功能自动化；显式单元测试 Case 按
  `paused_existing_developer_unit_coverage` 暂停，不与研发单测重复建设。
- A22 从 Case 提取数据意图，N28 根据版本化 BI 能力目录编译资源 DAG，N27 做确定性安全校验；CaseRunner 以
  `setup -> readiness -> test -> finally cleanup` 执行，并记录响应哈希证据。
- 测试数据并非全程只读：Runner 可在 112 的 `setup` 创建隔离资源，并在 `cleanup` 删除；
  只有创建后的 `readiness` 回查被限制为只读。A22 自身只负责出计划，不直接持有环境凭证。
- `CASE-FUNC-RESULT-FILTER-DETAIL-112` 已在真实 112 完成指标创建、查看明细验证、删除和无残留回查。
- `CASE-AUTO-RESULT-FILTER-DETAIL-112` 不含手写 setup/cleanup，由 A22/N28 自主生成相同生命周期。
- N00 确定性模板路由（5 个模板 + L1/L2/L3 执行深度）与 A01 建议 Profile；仅规则无法判定的
  输入才调用 A01，最终路由仍由 N00 校验决定。
- N01 只读输入采集、N02 ChangeSet 和 first-parent 基线。
- A02、A03、A04、A05、A06、A08、A09、A11 的本地保守 Profile。
- N24 风险策略、A07 未知项兜底、N25 Case 编译、N26 测试选择（策略强制/跳过/影响置信度）和 A12 测试选择建议（仅 N26 无法判定时触发，建议经 N26 校验折叠，只能扩大或升级范围）。
- N03/N04 契约校验、G02 人工停顿和 N15 Execution Plan。
- `fs-qa-knowledge` Case Provider 的固定版本能力探测、契约校验和无副作用消费端 Adapter；
  当前冻结版本不兼容，未实际调用其生成流程。
- Agent 与 Oracle 评估进程分离。
- JSON Artifact、文本报告和 HTML 报告。
- 结构化模型 Runtime 安全边界；策略默认关闭，尚未绑定生产模型。
- 路由、需求事实、实现事实、对齐问题、开放问题和测试义务的离线评估，以及可读的
  `evaluation.txt`、`evaluation.html`。
- Automation Manifest 契约和 A14 后端 pytest 候选生成；候选只写 Artifact。
- A13 前端 Playwright、A15 契约、A16 E2E、A17-PERF/SEC/A11Y/COMPAT/RES/DATA 六个非功能专项
  生成 Profile，以及 A18-FE/CT/E2E 与六个非功能专项的独立审查 Profile；共享生成/审查引擎，
  领域差异由版本化 Profile 与策略表达。
- A18-* 独立审查、N05 语法/哈希/命令/权限/凭证/层根目录安全检查、N06 回流和 G03 人工 Gate；
  多层级执行计划按层分发生成与审查后汇合到 N05/G03。
- N07/N16 环境、数据和资源门禁；N08 认证 N07、A18、N05 的 producer/contract，并对上游
  Artifact 及候选哈希做完整绑定校验后，使用
  无 shell、最小环境、分片并行、超时和日志脱敏的受控 Runner 执行，业务失败进入 N09，
  只有超时或基础设施错误进入 N10。A18/N05 结果绑定 generation、manifest 和候选文件哈希。
- 服务端质量尾链：N10 重试预算、N17 人工结果汇合、N18 质量信号、N09 证据标准化与失败
  指纹聚类、N20 跨运行缺陷去重、N11 确定性决策、N12 JSON/Markdown/HTML 报告，以及
  N13/N19/N23 反馈、豁免和上线后验证授权审计。缺少结果时输出 `inconclusive`，不伪造通过。
- 独立 Multica 试点 Workspace、Project、私有 Squad 和首批 7 个 Agent；远端 ID 固化在
  `multica/workspace-manifest.json`，当前未绑定任何业务仓库。
- Multica A02/A03/A05 真实 Stage 1 已使用 `pilot-001` 冻结数据运行并通过本地确定性入库
  Gate；A06 支持从三份已验收 Artifact 编译最小权限输入并执行真实对齐。
- Multica 消息流工具审计：绑定 Task、Issue 和唯一附件，只允许读取当前 Issue、批准附件和
  输入 JSON；拒绝仓库、网络、环境、写文件、命令组合和非批准工具调用。
- G01 生产化审核请求、审批哈希、逐问题角色签名和确定性回流路由。当前试点按用户决策临时
  使用 QA Owner 单签；该策略仅用于测试设计试点，不具备生产发布审批权限。审批绑定的上游
  哈希变化后自动失效。
- G01 获批后才能运行真实 N24；N24 再次校验审批哈希、运行/快照身份和 A06 Artifact 哈希，
  受控阻塞以结构化 JSON 和稳定退出码返回，供 Multica 编排判断。
- A08/A09/N04 真实回流：A09 独立审查正式 Oracle 和 14 个测试防范维度，N04 合并确定性
  Schema 问题并按根因回流；修正版保留旧 IR、绑定三份上游 Artifact、限制重试预算，只有
  N04 `valid=true` 才允许进入 G02。真实试点已验证第二轮仍失败时会以
  `test_case_ir_correction_budget_exhausted` 路由人工，不会无限自动修正或绕过 Gate。

内置语义 Profile 是无外部模型依赖的保守基线：证据不足时生成需要人工确认的 Oracle，
不会把模糊预期伪装成自动化断言。生产环境接入模型后仍必须返回相同契约并经过 N03/N04。

## 自主测试数据构造

Case 只声明语义数据集、前置状态或 `data_intent`，不提供创建接口和资源顺序。A22 使用
`knowledge/bi-knowledge-sources.json` 中登记的官方 BI 手册、只读代码仓库、冻结契约和 112
探针证据提取目标状态；N28 使用 `knowledge/bi-data-capability-catalog.json` 生成拓扑有序的
setup/readiness/cleanup。资源创建顺序按 DAG，Runner 的 cleanup 逆序执行。

```bash
PYTHONPATH=src ../.venv/bin/python -m qa_agents prepare-test-data \
  --compiled-cases runs/<run-id>/stage/artifacts/n25-compiled-test-cases.json \
  --policy policies/test-data-policy.json \
  --knowledge-sources knowledge/bi-knowledge-sources.json \
  --capability-catalog knowledge/bi-data-capability-catalog.json \
  --environment 112 --namespace qa-<run-id> --output runs/<run-id>/test-data
```

当前真实能力模板覆盖“聚合指标 + 结果集筛选 + 查看明细”纵向链路。现有 14 个试点 Case
审计可自主解析 1 个 Case 的聚合指标部分；普通指标、计算指标、同环比指标以及其余 13 个
数据集会进入 `capability_adapter_backlog`，不会转成要求用户手写链路的人工事项。产品白皮书
当前需要 WPS 企业登录，来源状态记录为 `authentication_required`，未被当作已采集证据。

## 目录

```text
qa-agents/
├── contracts/     # Artifact、ChangeSet、Test Case IR Schema
├── policies/      # 仓库白名单、权限和风险规则
├── profiles/      # 每个语义 Agent 的版本化 Profile
├── src/qa_agents/ # Runtime、确定性节点、Agent、CLI 和报告
├── tests/         # 单元、安全和纵向工作流测试
└── eval/          # Agent 输入与 Oracle 分离的评估样本
```

## 执行

在仓库根目录执行：

```bash
make -C qa-agents test
make -C qa-agents pilot
```

报告生成到：

```text
qa-agents/runs/pilot-001/report.txt
qa-agents/runs/pilot-001/report.html
qa-agents/runs/pilot-001/run-summary.json
qa-agents/runs/pilot-001/artifacts/
```

试点默认在 N04 停止，不会绕过 G02。要验证批准后的 N25/N26/N15 链路：

```bash
make -C qa-agents pilot-full
```

`--approve-g01` 和 `--approve-g02` 只用于本地开发验证，生产必须由 Multica 的 QA Review
Center 提供带身份和审计记录的审批结果。

要继续验证到后端自动化路由和 G03：

```bash
make -C qa-agents pilot-automation
```

该本地模拟运行的 24 条 Case 都是人工 Oracle，因此该命令会把 A14/A18-BE 标记为
`skipped_by_policy`，把 N05/G03 标记为 `not_applicable`。这证明路由不会为模糊预期伪造
自动化代码；具有确定性 Oracle 的后端正向链路由自动化测试样本覆盖。

## 需求工作流中心

用户侧采用“一需求一工作流”：一个稳定的需求父 Issue 对应一个 Autopilot 工作流，需求的
每次触发产生新的 `workflow_run_id`，但不会再创建第二张用户侧需求卡。并行需求在
`QA 需求工作流中心` 中各占一张卡；Agent 运行、节点执行、重跑、影子候选和人工 Gate 技术卡
统一留在 `QA 内部执行与审计` 项目。

需求父卡汇总总体状态、完成节点数、当前节点、全部节点结果、历史运行和当前人工事项。
总体状态固定按 `阻塞 > 待我处理 > 系统运行中 > 排队中 > 已完成 > 已取消` 归并；只有开放的
人工 Action 才进入“待我处理”，Agent 审查和内部节点不会制造用户待办。父卡状态、正文、
metadata 和自定义属性由同一份内容寻址 Projection 幂等同步。

```bash
make -C qa-agents compile-workflow-center \
  WORKFLOW_CENTER_SPEC=runs/<run-id>/workflow-center-spec.json \
  WORKFLOW_CENTER_OUTPUT=runs/<run-id>/workflow-center

make -C qa-agents sync-workflow-center \
  WORKFLOW_CENTER_SPEC=runs/<run-id>/workflow-center-spec.json \
  WORKFLOW_CENTER_OUTPUT=runs/<run-id>/workflow-center
```

当前真实工作流 `REQ-DETAIL-DRILL-I18N` 使用 QAA-1 作为稳定父卡；
`multica-confidence-20260811-01` 是当前运行，`multica-pilot-001` 作为历史运行。QAA-27～QAA-32
属于内部执行，其中 QAA-32 仍是独立的 G01 审核入口；父卡只负责告诉用户当前有 15 项待处理，
不能代替逐项审批。

当前状态映射固定为：需求父卡 QAA-1=`in_review`，内部 Run QAA-27=`in_progress`，开放人工
Gate QAA-32=`in_review`。不能把 Run 也设为 `in_review`，否则 Multica 的 stage 联动会把
Gate 子卡错误推进为 `done`。同步器在更新 Run 后最后校正开放 Gate，并将 Autopilot ID、运行
成功/失败历史和 112 历史质量结论写入 QAA-1 正文。

## Multica 真实试点

Stage 1 的最小输入由冻结来源材料生成；A06 输入只能由已经通过入库 Gate 的 Stage 1
Artifact 生成：

```bash
make -C qa-agents prepare-multica-pilot
make -C qa-agents prepare-multica-alignment-pilot
make -C qa-agents report-multica-alignment-pilot
```

远端消息必须先用 `fetch-multica` 保存完整审计流，再用 `ingest-multica` 入库。入库命令
必须同时提供 `--task-id`、`--issue-id` 和 `--attachment-id`，任一身份或工具轨迹不匹配都
会失败。入库成功后必须用正式 Artifact 同步对应 Issue 卡片；该命令会再次核对 Profile、
运行、输入哈希和工具审计中的 Issue ID，只允许把已接受结果的绑定卡片更新为 `done`，并把
结构化结果摘要写入卡片正文：

```bash
PYTHONPATH=src ../.venv/bin/python -m qa_agents sync-multica-issue-card \
  --bundle runs/<run-id>/multica-inputs/<agent>-input.json \
  --artifact runs/<run-id>/<stage>/artifacts/<artifact>.json \
  --issue-id <bound-multica-issue-id>
```

自动编排应直接给 `ingest-multica` 增加 `--sync-issue-card`，把“验收成功后回写绑定卡片”表达为
同一次显式操作；不带该参数时入库仍没有网络副作用。同步失败会返回非零，Artifact 保留为已
验收结果，重试同一命令只会按相同绑定再次同步，不得改投其他 Issue。

失败、影子或未入库候选不得调用该命令。G01/G02 等人工 Gate 不使用 Agent 完成卡模板；
卡片 description 必须直接包含完整审核项、允许的处置和提交方式，哈希只作为审计绑定，
不能作为给审核人的主要内容。真实产物位于：

```text
qa-agents/runs/pilot-001/multica-outputs/
qa-agents/runs/pilot-001/multica-stage1/artifacts/
qa-agents/runs/pilot-001/multica-stage2/artifacts/
qa-agents/runs/pilot-001/multica-alignment-report.md
```

对齐报告由已验收的 A06 Artifact 和对应输入 bundle 确定性生成；两者哈希不匹配时拒绝出
报告。当前真实试点报告显示 6 条需求映射、11 个对齐问题，结论为 `needs_human`，下一步
必须进入 G01。

当前有效 Runtime 是 Codex `gpt-5.6-sol`。旧 Claude Runtime 因认证 401 不可用，具体远端
绑定状态记录在 `multica/workspace-manifest.json`，编排器不得自动回退到失效 Runtime。

## G01 审核与 N24

真实试点已生成内容寻址的 G01 审核包：

```text
qa-agents/runs/pilot-001/g01/g01-review-request.md
qa-agents/runs/pilot-001/g01/g01-review-request.json
qa-agents/runs/pilot-001/g01/g01-decision-template.json
qa-agents/runs/pilot-001/g01/g01-qa-clarifications.md
```

G01 共 23 个问题：A02 需求问题 8 条、A03 技术与可测性问题 6 条、A06 对齐问题 9 条。
QA Owner 已逐项签署并批准测试设计试点；审批请求和决策均使用内容哈希绑定。空白模板仍是
刻意无效的表单，不能当作审批记录。QA 合并口径记录在 `g01-qa-clarifications.md`。

试点审批策略为 QA Owner 单签，适用范围仅为 `pilot_test_design_only`。它允许测试设计链路
先运行，不代表研发、产品已确认，也不能用于生产发布放行；接入发布流程前必须恢复职责分离。

生成审核包、记录外部人工决策并在获批后运行 N24：

```bash
make -C qa-agents prepare-g01-pilot
make -C qa-agents record-g01-pilot G01_DECISION_INPUT=/absolute/path/to/decision.json
make -C qa-agents run-n24-pilot
```

`record-g01-pilot` 会同时生成带哈希的决策记录和编排结果。`request_changes` 会明确回流到
A02/A03/A05/A06，并以 A06 为根递归使全部下游 Artifact 失效；修正后从 A06 重新对齐。
`approved` 才允许进入 N24。Agent、非 QA 审批者、缺少 QA 签名、旧请求、篡改决策和未绑定
当前 A06 的审批都会被拒绝。

G01 的 Multica 适配器不把 Issue 状态当作审批。`open-g01-multica` 创建或绑定唯一审核卡，
把完整问题和可复制评论表写入正文；`sync-g01-multica` 只接受指定成员提交、绑定当前
`request_hash` 的 `g01-comment-table/1.0` 评论。逐项处置、理由、负责人或必填测试规则缺失时
不会生成决策；单独把卡片改为 `done` 会被忽略并恢复为 `in_review`。

```bash
PYTHONPATH=src ../.venv/bin/python -m qa_agents open-g01-multica \
  --request runs/<run-id>/g01/g01-review-request.json \
  --policy policies/g01-review-policy.json \
  --adapter-policy policies/g01-multica-policy.json \
  --output runs/<run-id>/g01 [--issue-id <existing-issue-id>]

PYTHONPATH=src ../.venv/bin/python -m qa_agents sync-g01-multica \
  --request runs/<run-id>/g01/g01-review-request.json \
  --policy policies/g01-review-policy.json \
  --adapter-policy policies/g01-multica-policy.json \
  --output runs/<run-id>/g01
```

本次置信运行的 QAA-32 已绑定到该状态机，15 项审核仍为 `pending/in_review`，当前没有正式
`g01-review-decision.json` 或 `g01-review-outcome.json`，不会复用 `pilot-001` 的旧审批。

## A08/A09/N04 回流

真实第一版 A08 生成 10 个父 Case。A09 审查识别 22 个问题，第一轮 N04 将逐字段 Schema
问题与 A09 语义问题合并，结果为 `valid=false`、`next_node=A08`、
`g02_status=not_started`。生成内容寻址修正输入：

```bash
make -C qa-agents prepare-multica-test-design-correction-pilot
```

修正输入保留全部 22 条 A09 问题，并把重复的 N04 字段问题归并为带完整受影响位置的 4 个
问题组。A08 修正版必须逐条记录 `fixed`、`not_applicable` 或
`rejected_conflict_with_frozen_evidence`，无法从冻结证据得到精确基线时转人工 Oracle，
不得编造断言。修正后必须重新运行 A09 和 N04，第二次仍不通过则耗尽自动修正预算并转人工。

当前主链已接受 QAA-11 的 A08 修正版，共 13 个父 Case；QAA-13 的 A09 复审剩余 3 个阻塞
错误和 1 个警告。问题集中在：结果集筛选参数没有按 `zh_CN/en` 与当前语言指标名配对、
`CASE-CT-001/E3` 引用了不存在的 `test_data.matrix.zh_CN_and_en`、`CASE-CT-002` 使用
`exact_set` 导致不同原因之间互换文案仍可能通过，以及复合 Oracle 的单值来源不能支撑全部
模板。第二轮 N04 输出 `valid=false`、`correction_attempt=2`、
`max_correction_attempts=2`、`next_node=human`；G02 仍为 `not_started`，必须先完成人工修正
和重新校验。

## G02 Multica 审核控制

G02 使用 Multica Issue 作为唯一人工审核入口，不单独建设审批页面。只有 N04 输出
`valid=true`、`blocking_issue_count=0`、`next_node=G02` 后才能生成内容寻址审核请求并创建
分配给指定 QA Owner 的 `in_review` Issue。Multica 状态确定性映射为：

- `in_review`：流程保持暂停；
- `done`：审核通过，恢复到 N25；
- `blocked`：退回 A08，并使其下游失效；
- `cancelled`：拒绝并终止本次流程。

审核 Issue 的 metadata 绑定 request、policy、workflow 和上游 Artifact 哈希。同步节点同时
校验审批 member ID 和当前 N04 哈希；上游变化会使旧审批失效。决定和结果分别保存为
`g02-review-decision.json` 与 `g02-review-outcome.json`，重复同步使用同一幂等结果，不重复
启动下游节点。

```bash
make -C qa-agents prepare-g02-pilot
make -C qa-agents open-g02-pilot
make -C qa-agents sync-g02-pilot
```

G02 放行后的阶段二真实链（N25 -> A11 审核 -> N26 -> N15）：

```bash
make -C qa-agents run-n25-after-g02-pilot            # multica-stage13
make -C qa-agents prepare-multica-split-review-pilot # multica-inputs/a11-01/a11-input.json
# 把 a11-input.json 作为唯一附件分配给 A11 Agent（QAA-26），接受后：
#   fetch-multica 保存消息流 -> ingest-multica 校验并入库 multica-stage14
make -C qa-agents run-n26-after-a11-pilot            # multica-stage15
make -C qa-agents run-n15-after-n26-pilot            # multica-stage16
```

阶段 3 执行门禁（设计文档 §17）：N07 在正式 Case 执行前记录环境指纹并检查部署/依赖/
账号/Flag/租户/数据/运行时/命名空间/资源锁；失败即 `blocked` 路由 N16，N16 修复计划必须
覆盖全部失败项且动作满足幂等键、有状态变化并记录补偿清理：

```bash
make -C qa-agents run-n07-env-precheck-pilot        # multica-stage17（需 env/target.json 与 observed.json）
make -C qa-agents run-n16-env-fix-pilot             # multica-stage18（需 env/fix-plan.json）
make -C qa-agents run-n08-automation-pilot \
  N08_GENERATION=/path/to/generation.json \
  N08_REVIEW=/path/to/review.json \
  N08_CODE_CHECK=/path/to/n05.json                   # multica-stage19
make -C qa-agents prepare-server-automation-pilot   # A14/A15 -> A18 -> N05
make -C qa-agents run-server-quality-pilot          # N10/N17/N18/N09/N20/N11/N12
make -C qa-agents run-server-full-pilot             # 当前已批准 pilot 的服务端尾链
```

`run-server-full-pilot` 的内置环境是 `local-reference-not-staging`。当前真实 N15 的三个
`generate_new` 契约 Case 缺少冻结 `contract_ref`，A15 按契约拒绝生成，因此不会调用 N08；
N17 仍输出 11 个完整人工任务，N11/N12 最终给出 `inconclusive/pending` 报告。

当前 `execution-policy.json` 使用 `local_process_reference`，只用于无网络、无 Secret 的本地
验证，Artifact 会明确记录 `production_isolated=false`。生产接入必须替换为容器或远端隔离
Runner，并把 `require_production_isolation` 设为 `true`；不能把本地进程执行冒充生产隔离。

A11 输入是紧凑审查范围而不是完整 Test Case IR：N25 子 Case 与父 Case 内容相同，完整
重复载荷会把 Agent 上下文推到 Codex Runtime `semantic_inactivity_timeout=10m` 的生成
窗口之外（真实运行曾连续两次 `codex_semantic_inactivity` 超时）。`prepare-multica-split-review`
只下发审查必需字段（id/expected/layer/parent 绑定/继承一致性标志等），并保留 `inherits_parent`
确定性核对结果；A11 指令要求最终 JSON ≤ 10KB、rationale ≤ 60 字。

`pilot-001` 的 G02 已真实放行：QAA-24 由 QA Owner `muqj11262` 置为 `done` 后线上确认
`approved`/`next_node=N25`，恢复点在 N25。Multica CLI 暂未提供 Issue 状态变化 webhook，
当前 Adapter 使用 `sync-g02-multica` 轮询；未来有原生 webhook 时只替换触发方式，不改变
G02 契约和路由。

## 人工修正恢复

N04 在自动预算耗尽后生成内容寻址人工修正请求，并在 Multica 创建分配给 QA Owner 的
`in_review` Issue。`done` 授权请求中全部定向修正并恢复到 A08；`cancelled` 终止流程；其他
状态保持暂停。人工恢复不会重置自动预算，A08 输入使用 Profile v1.3.0，并在生成后强制重新
经过 A09 和 N04。

```bash
make -C qa-agents prepare-human-correction-pilot
make -C qa-agents open-human-correction-pilot
make -C qa-agents sync-human-correction-pilot
make -C qa-agents prepare-multica-human-correction-pilot
```

真实试点 `QAA-19` 已由 QA Owner 改为 `done` 并生成 A08 v1.3.0 人工恢复输入。`QAA-20`
第一次恢复运行因缺少绑定字段、附件交付和工具轨迹违规被拒收，不能入库；需要先把 Multica
A08 指令发布为 `a08-v1.3.0.md`，再重跑 A08，然后走 A09/N04（`correction_attempt=3`）。

```bash
make -C qa-agents validate-human-a08-candidate-pilot
# 重跑并接受合法 A08 后：
make -C qa-agents prepare-multica-oracle-review-human-pilot
make -C qa-agents run-n04-human-correction-pilot
make -C qa-agents prepare-g02-after-human-pilot
```

QAA-12 是 A08 v1.2.1 的并行协议影子候选。其完整消息流已归档并在运行清单标记为
`shadow_protocol_candidate_not_current`；它不替换已经进入主链并被 QAA-13 审查的 QAA-11，
也不能用来绕过第二轮 N04 的人工路由。

A09 第一轮的 `A09-018` 要求把动态关联限制为工单主题，与 G01 冻结规则冲突。正式规则是
所有 what/what-list 均属于动态关联，因此该问题在修正中按冻结证据拒绝，不能反向污染 Case。

## 远端只读采集

以下命令从登记的文档仓库和业务仓库读取固定 commit，将证据写入 Agent 输入目录：

```bash
make -C qa-agents collect-pilot
```

采集器只在临时目录执行 `git clone --no-checkout`、`git show` 和 `git diff`，完成后销毁临时
目录。仓库必须存在于 `policies/repository-registry.json`，业务凭证必须只有
`read_repository` 权限。采集器不执行 checkout、add、commit、push、MR、评论或流水线操作。

## 离线评估

Agent 运行完成后，使用独立命令读取 Oracle：

```bash
make -C qa-agents evaluate-pilot
```

评估同时生成 `evaluation.json`、`evaluation.txt` 和 `evaluation.html`。当前试点的 G01
路由已修复，路由评估为 `17/17`。完整语义评估仍会返回非零退出码：需求事实 `4/7`、
实现事实 `7/7`、对齐问题 `0/7`、开放问题 `4/4`、最小 Gate 决策 `1/1`、测试义务
`1/26`。这说明本地保守 Profile 只能验证工程骨架，尚不能替代生产语义模型。失败项不能
通过修改 Oracle、放宽匹配或跳过 Gate 掩盖。

`expected-safety.json` 属于权限攻击和越权写入负向测试套件，不与单次正常工作流的语义
召回混算。评估结果会将其标为 `separate_negative_test_suite_required`；相关控制由安全、
采集器和自动化检查测试验证，生产阶段还需接入运行时审计证据。

生产部署必须给运行器和评估器使用不同身份与挂载点。本地目录隔离只是开发约定，不能替代
Oracle Registry 的 ACL。

## 尚未实现

- Multica `pilot-001` 已真实打通到 N15；新置信运行已完成 A02/A03/A05→A06，当前在 QAA-32
  等待 15 项 G01 人工审核。生产职责分离、DAG 和全流程事件触发器尚未完成。
- Multica 模型网关的生产 Provider 绑定、Prompt 发布、影子流量和模型灰度；Runtime 契约已实现。
- 候选代码已可落到运行目录隔离工作区（N29）；创建正式 MR、生产隔离 Runner 和发布系统写入
  Adapter 仍未接通。
- `controlled_env_reference` 可为注册非生产环境开放网络/Secret env 名，但仍不是生产隔离
  Runner；契约场景的真实请求载荷与完整 112 端到端 N08 证据仍待主链审批后补齐。
- 生产 Oracle Registry、Secret 服务和测试资产服务。

这些能力按设计方案分阶段接入，不能用本地参考实现的 `completed_with_gaps` 代替正式质量
结论。

## 候选落盘与受控执行

```bash
# 在 A14/A18/N05 通过后，把候选落到运行目录隔离工作区（不写业务仓、不建 MR）
make -C qa-agents land-automation-candidates-pilot \
  N08_GENERATION=... N08_REVIEW=... N08_CODE_CHECK=...

# N08：默认 local_process_reference 禁止网络/Secret；
# 若 Manifest 申请网络且 N07 environment_class 属于策略白名单，则走 controlled_env_reference
make -C qa-agents run-n08-automation-pilot \
  N08_GENERATION=... N08_REVIEW=... N08_CODE_CHECK=...
```
