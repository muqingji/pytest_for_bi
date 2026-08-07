# Implementation Status

更新时间：2026-08-07

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
| N24/A07 | 真实 N24 已完成 | 风险为 `critical`，必测 `backend/contract/e2e`；规则优先，未知项才调用 A07 |
| A08/A09/N04/G02 | 自动回流完成，等待人工修正 | 第一版 A08 生成 10 个父 Case；QAA-11 修正版生成 13 个父 Case；A09 复审剩余 3 个阻塞错误和 1 个警告；第二轮 N04 `valid=false`、`next_node=human`，修正预算 2/2 已耗尽，G02 未启动 |
| N25/A11/N26/A12/N15 | 已实现参考链路 | 确定性编译、审查、选择和执行计划 |
| A14/A18-BE/N05/N06/G03 | 已实现后端参考切片 | Artifact-only pytest 候选、独立审查、安全检查、精确回流和人工 Gate |
| Oracle 离线评估 | 已实现参考版 | 路由、事实、对齐、开放问题、Gate 决策和测试义务；确定性规则、一对一义务匹配、文本/HTML 报告 |
| Multica 试点空间 | 已配置基础资源 | 独立 Workspace、Project、私有 Squad、组长和 A02/A03/A05/A06/A08/A09；无仓库绑定 |
| Multica 生产编排 | 部分实现 | Stage 1→A06→G01→N24→A08→A09→N04→A08→A09→N04 已真实跑通，并在预算耗尽后确定性路由人工；待接 Review Center、人工修正恢复、持久化恢复和触发器 |
| 结构化模型 Runtime | 已实现契约，默认关闭 | 固定 Provider/模型/Prompt、无工具、无留存、凭证和输出契约检查；待 Multica 生产绑定 |
| fs-qa-knowledge Provider | 消费端完成，上游阻塞 | 冻结版本缺少 capability manifest，且强制 `upload2fs`；状态为 `incompatible`，禁止进入 A08 |
| 其余 A13-A18 自动化链路 | 未实现 | A13、A15-A17-* 和对应 A18 Profile 按阶段 2 继续建设 |
| N07-N12/N16-N23 执行与门禁 | 未实现 | 按阶段 3-5 建设 |

本地保守 Profile 可以通过显式开发审批开关模拟运行到 G03；这不是生产审批，也不是当前
真实 Multica 链路的状态。真实试点已完成 G01 与 N24，也完成一轮 A08 自动修正和 A09
复审；第二轮 N04 因仍有 3 个阻塞问题且修正预算达到 2/2，当前确定性停在人工修正节点，
G02 仍未启动。历史本地模拟中 24 条 Case 因 Oracle 需要人工确认而全部路由为
`manual_run`，不能
作为发布放行结论。完整离线评估仍暴露 A02/A06/A08/A09 的语义差距，下一阶段应先提升这些
核心能力，不扩展无真实闭环支撑的新 Agent。

Multica 真实链路的 A02、A03、A05、A06、A08 和 A09 均保留完整消息审计。G01 的 23 个
问题已由 QA Owner 逐项确认，N24 输出 critical 风险策略。第一轮 A09/N04 阻断了缺少正式
Oracle 字段、不可执行负向断言和覆盖缺口；QAA-11 修正后，QAA-13 复审将问题收敛为结果集
筛选的中英文指标名参数配对、不可解析的期望引用、无键本地化集合匹配和复合 Oracle 来源
范围四项。第二轮 N04 当前明确 `next_node=human`、`g02_status=not_started`，不得继续自动
回流或进入 G02。动态关联继续遵循冻结规则：所有 what/what-list 均属于动态关联，不采用
A09 第一轮提出的工单主题限制。QAA-12 仅作为 A08 v1.2.1 协议影子候选保留，不替换主链
已经验收的 QAA-11 Artifact。
