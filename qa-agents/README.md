# QA Multi-Agent System

该目录是 [QA_AGENT_DESIGN.md](../QA_AGENT_DESIGN.md) 的可运行参考实现。目前完成阶段 0
基础能力、阶段 1 测试设计纵向链路，以及阶段 2 的后端自动化参考切片。不声称已经完成
全部自动化类型、真实环境执行或发布门禁。

## 当前已实现

- Artifact Envelope、完整状态枚举、内容哈希和路径受限的 Artifact Store。
- N00 确定性路由、N01 只读输入采集、N02 ChangeSet 和 first-parent 基线。
- A02、A03、A04、A05、A06、A08、A09、A11 的本地保守 Profile。
- N24 风险策略、A07 未知项兜底、N25 Case 编译、N26 测试选择和 A12 未知影响兜底。
- N03/N04 契约校验、G02 人工停顿和 N15 Execution Plan。
- `fs-qa-knowledge` Case Provider 的固定版本能力探测、契约校验和无副作用消费端 Adapter；
  当前冻结版本不兼容，未实际调用其生成流程。
- Agent 与 Oracle 评估进程分离。
- JSON Artifact、文本报告和 HTML 报告。
- 结构化模型 Runtime 安全边界；策略默认关闭，尚未绑定生产模型。
- 路由、需求事实、实现事实、对齐问题、开放问题和测试义务的离线评估，以及可读的
  `evaluation.txt`、`evaluation.html`。
- Automation Manifest 契约和 A14 后端 pytest 候选生成；候选只写 Artifact。
- A18-BE 独立审查、N05 语法/哈希/命令/权限/凭证安全检查、N06 回流和 G03 人工 Gate。
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
会失败。真实产物位于：

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

- Multica 试点已打通 A02/A03/A05→A06→G01→N24→A08→A09→N04→A08→A09→N04，
  并验证修正预算耗尽后路由人工；真实审批已用试点 QA Owner 单签完成，生产 Review Center、
  人工修正后的受控恢复、职责分离、DAG 和持久化恢复尚未完成。
- Multica 模型网关的生产 Provider 绑定、Prompt 发布、影子流量和模型灰度；Runtime 契约已实现。
- A13 前端、A15 契约、A16 E2E、A17-* 非功能生成及其对应 A18 审查 Profile。
- 获批自动化仓库的候选代码落盘、创建 MR 和隔离试跑；当前只生成 Artifact 草稿。
- N07-N12、N16-N23 的真实环境执行、失败归因、质量决策和发布集成。
- 生产 Oracle Registry、Secret 服务和测试资产服务。

这些能力按设计方案分阶段接入，不能用本地参考实现的 `completed_with_gaps` 代替正式质量
结论。
