# 生产级 QA 多 Agent 质量系统设计规范

## 1. 文档定位

本文档是 QA 多 Agent 质量系统的顶层设计规范，也是后续设计、实现和验收每个 Agent
及 Multica 流程节点时的共同参照。

系统目标不是生成一批看起来完整的测试 Case，而是进入真实研发流程，建立一套能够：

- 理解需求、技术方案和前后端代码变更；
- 识别需求与实现之间的偏差；
- 基于风险生成可追踪的测试策略和 Test IR；
- 拆分前端、后端、契约、E2E 和非功能测试；
- 生成、审查并执行自动化测试；
- 管理测试环境、测试数据和共享资源；
- 对失败进行证据化聚类和归因；
- 给出确定性的质量门禁结论；
- 将人工修正沉淀为离线评估集；

的生产级质量系统。

本文档当前定义架构、职责、数据契约、门禁和验收标准，不包含具体 Agent 代码。

## 2. 设计状态与使用规则

- 当前状态：方案设计阶段。
- 编排平台：Multica。
- Agent 之间的主契约：版本化 JSON Artifact。
- 测试设计主契约：Test IR。
- 默认执行环境：隔离测试环境或临时环境。
- 默认权限：最小权限、只读优先、禁止生产写操作。
- 默认决策原则：证据优先，模型自报置信度不能单独作为放行条件。

后续创建任何 Agent 前，必须从本文档中明确以下内容：

1. Agent ID 和单一职责。
2. 允许读取的输入 Artifact。
3. 必须输出的 JSON Schema。
4. 可以使用的工具和权限。
5. 阻塞条件、重试条件和人工升级条件。
6. 离线评估样本和验收指标。

## 3. 核心架构原则

### 3.1 Agent 负责判断，程序负责执行

大模型适合需求理解、风险识别、Case 设计、代码生成和失败归因；下载、Schema 校验、
测试执行、统计和质量规则计算必须由确定性程序完成。

### 3.2 每个 Agent 只负责一个稳定职责

Agent 不得同时承担需求理解、代码生成、执行和自我审查。生成 Agent 与审查 Agent
必须分离，避免同一个模型为自己的输出背书。

### 3.3 Agent 之间不共享聊天历史

Multica 节点之间传递结构化 Artifact。下游 Agent 可以根据证据引用回查原始材料，
不能依赖上游自由文本结论或隐含上下文。

### 3.4 Test IR 是唯一测试主模型

需求分析结果不能直接生成 pytest 或 Playwright。必须先生成框架无关的 Test IR，
审核通过后再拆分和生成自动化代码。

### 3.5 测试结果必须可复现

每次工作流必须冻结需求版本、MR commit、OpenAPI、环境部署版本、Agent 版本、模型版本
和 Prompt 版本。输入发生变化时创建新运行，不能悄悄污染当前结果。

### 3.6 不允许为了通过而修改测试

业务断言失败默认不可重试。元素自愈、字段替换和断言调整只能生成候选修改，必须保留
原始失败证据并经过审核。

### 3.7 风险决定流程深度

低风险变更不应强制运行全部 Agent；高风险变更必须增加契约、E2E、非功能测试和人工
门禁。Multica 根据任务模式和风险策略动态构建执行分支。

## 4. 工作流模式

系统至少支持五种工作流模式，不能用同一条固定长链路处理所有任务。

| 模式 | 触发输入 | 主要输出 |
| --- | --- | --- |
| 新需求测试设计 | 需求、技术方案、前后端 MR | 完整 Test IR、覆盖矩阵和自动化计划 |
| MR 增量测试 | 一个或多个 MR | 变更影响、增量 Case 和本次测试执行集合 |
| 发布回归 | 发布版本、变更清单 | 回归集合、执行结果和质量门禁结论 |
| Bug 复现与固化 | Bug、日志、修复 MR | 最小复现 Case、自动化回归和修复验证 |
| 上线后验证 | 已批准发布单、部署版本和监控范围 | 只读冒烟、SLO 信号和线上缺陷反馈 |

`A01 Workflow Router Agent` 根据输入类型和目标选择工作流模板。路由结果必须经过
Schema 和策略校验，Agent 不能自行创建未授权流程。

## 5. 优化后的总体流程

### 5.1 简版流程图

```text
任务触发
  -> 工作流路由 Agent
  -> 输入采集、解析质量校验和版本冻结
  -> 测试资产目录与影响关系图快照
  -> 需求/方案/可测性/前端 MR/后端 MR 并行分析
  -> 需求与变更对齐 Agent
  -> 风险与测试策略 Agent
  -> 测试设计 Agent
  -> Oracle 与测试防范覆盖审查 Agent
  -> 人工 Test IR Gate
  -> Case 拆分 Agent
  -> 拆分后覆盖回查 Agent
  -> 测试选择 Agent
  -> 执行计划编译：生成、更新、直接执行、人工执行或跳过
  -> 需要生成或更新的自动化并行生成
  -> 对应领域的自动化代码审查 Agent
  -> 格式化、lint、编译和安全扫描
  -> 人工或风险分级 Gate
  -> 环境、数据、Feature Flag 和资源锁预检及修复
  -> 自动化测试与人工/探索测试并行执行
  -> 代码覆盖率、运行质量信号和证据标准化
  -> 失败聚类、跨运行去重和归因
  -> 确定性质量决策节点
  -> 可选、限时且不篡改原结论的质量豁免
  -> 报告、MR 评论和 Bug 草稿
  -> 经授权的上线后只读验证
  -> 人工修正进入离线评估集
```

### 5.2 Multica 详细流程图

```mermaid
flowchart TD
    START([任务触发]) --> ROUTER[A01 工作流路由 Agent]
    ROUTER --> COLLECT[N01 输入采集、标准化与解析质量校验]
    COLLECT --> SNAPSHOT[N02 输入版本冻结]

    SNAPSHOT --> ASSET[N14 测试资产目录与影响关系图快照]
    SNAPSHOT --> REQ[A02 需求分析 Agent]
    SNAPSHOT --> TECH[A03 技术方案分析 Agent]
    REQ --> TESTABILITY[A21 可测性评审 Agent]
    TECH --> TESTABILITY
    ASSET --> FE_MR[A04 前端 MR 分析 Agent]
    ASSET --> BE_MR[A05 后端 MR 分析 Agent]

    REQ --> ALIGN[A06 需求与变更对齐 Agent]
    TECH --> ALIGN
    TESTABILITY --> ALIGN
    FE_MR --> ALIGN
    BE_MR --> ALIGN

    ALIGN --> ALIGN_CHECK{N03 Schema 与证据校验}
    ALIGN_CHECK -->|输入缺失或高风险冲突| SCOPE_GATE{{G01 范围确认 Gate}}
    SCOPE_GATE -->|补充输入| COLLECT
    SCOPE_GATE -->|确认继续| RISK
    ALIGN_CHECK -->|通过| RISK[A07 风险与测试策略 Agent]

    RISK --> DESIGN[A08 测试设计 Agent]
    DESIGN --> ORACLE[A09 Oracle 与测试防范覆盖审查 Agent]
    ORACLE --> IR_CHECK{N04 Test IR 校验}
    IR_CHECK -->|Test IR、Oracle 或覆盖问题| DESIGN
    IR_CHECK -->|风险策略或测试层级缺失| RISK
    IR_CHECK -->|上游冲突或需求无法定义预期| ALIGN
    IR_CHECK -->|通过| IR_GATE{{G02 Test IR 审核 Gate}}

    IR_GATE -->|退回| DESIGN
    IR_GATE -->|通过| SPLIT[A10 Case 拆分 Agent]
    SPLIT --> COVERAGE[A11 拆分覆盖回查 Agent]
    COVERAGE -->|有遗漏或无效重复| SPLIT
    COVERAGE -->|通过| SELECT[A12 测试选择 Agent]

    ASSET --> SELECT
    SELECT --> PLAN[N15 执行计划编译与路由]
    PLAN -->|generate_new 或 update_existing| GEN_ROUTE{按测试类型生成}
    PLAN -->|run_existing| READY[待执行集合汇合]
    PLAN -->|manual_run| MANUAL_READY[人工测试任务集合]
    PLAN -->|skip| SKIP_RECORD[记录跳过原因]
    SKIP_RECORD --> READY

    GEN_ROUTE --> FE_AUTO[A13 前端自动化 Agent]
    GEN_ROUTE --> BE_AUTO[A14 后端自动化 Agent]
    GEN_ROUTE --> CONTRACT[A15 契约自动化 Agent]
    GEN_ROUTE --> E2E[A16 E2E 自动化 Agent]
    GEN_ROUTE --> NF_AUTO[A17-* 非功能专项 Agent]

    FE_AUTO --> FE_REVIEW[A18-FE 前端自动化审查 Agent]
    BE_AUTO --> BE_REVIEW[A18-BE 后端自动化审查 Agent]
    CONTRACT --> CONTRACT_REVIEW[A18-CT 契约自动化审查 Agent]
    E2E --> E2E_REVIEW[A18-E2E E2E 审查 Agent]
    NF_AUTO --> NF_REVIEW[A18 对应非功能专项审查 Agent]

    FE_REVIEW --> CODE_CHECK[N05 代码检查与安全扫描]
    BE_REVIEW --> CODE_CHECK
    CONTRACT_REVIEW --> CODE_CHECK
    E2E_REVIEW --> CODE_CHECK
    NF_REVIEW --> CODE_CHECK

    CODE_CHECK -->|不通过且可修复| REPAIR{N06 修复路由与重试预算}
    CODE_CHECK -->|不可修复| QUALITY[N11 确定性质量决策]
    CODE_CHECK -->|通过| CODE_GATE{{G03 自动化 MR Gate}}

    CODE_GATE -->|退回并附问题类型| REPAIR
    CODE_GATE -->|通过| READY
    REPAIR -->|对应测试代码问题| GEN_ROUTE
    REPAIR -->|Case 拆分问题| SPLIT
    REPAIR -->|Test IR 问题| DESIGN
    REPAIR -->|预算耗尽| QUALITY

    READY --> PREFLIGHT[N07 环境、数据和资源预检]
    MANUAL_READY --> PREFLIGHT
    PREFLIGHT -->|失败| PREFLIGHT_DECISION{可恢复性判断}
    PREFLIGHT_DECISION -->|可恢复| REMEDIATE[N16 环境与测试数据修复动作]
    REMEDIATE --> RETRY{N10 环境重试预算}
    RETRY -->|允许| PREFLIGHT
    RETRY -->|不允许| QUALITY
    PREFLIGHT_DECISION -->|不可恢复| TRIAGE[A19 失败聚类与归因 Agent]

    PREFLIGHT -->|通过| EXECUTE[N08 自动化测试并行执行]
    PREFLIGHT -->|存在人工任务| MANUAL[N17 人工与探索测试编排]
    EXECUTE --> SIGNALS[N18 代码覆盖率与运行质量信号采集]
    SIGNALS --> EVIDENCE[N09 证据标准化与汇合]
    MANUAL --> EVIDENCE
    EVIDENCE --> RESULT{执行结果}
    RESULT -->|存在失败| TRIAGE
    RESULT -->|全部通过| QUALITY

    TRIAGE -->|自动化缺陷| FIX_GATE{{G04 测试修复 Gate}}
    FIX_GATE -->|批准| REPAIR
    FIX_GATE -->|拒绝或无法修复| QUALITY
    TRIAGE -->|环境或数据问题| REMEDIATE
    TRIAGE -->|产品缺陷| DEDUP[N20 跨运行缺陷去重]
    DEDUP --> QUALITY
    TRIAGE -->|需求歧义或待确认| QUALITY

    QUALITY -->|无需豁免| REPORT[A20 报告与覆盖分析 Agent]
    QUALITY -->|申请豁免| WAIVER_GATE{{G05 质量豁免 Gate}}
    WAIVER_GATE -->|批准| WAIVER[N19 质量豁免登记]
    WAIVER_GATE -->|拒绝| REPORT
    WAIVER --> REPORT
    REPORT --> PUBLISH[N12 发布报告、MR 评论或 Bug 草稿]
    PUBLISH -->|普通流程| FEEDBACK[N13 人工反馈入评估集]
    PUBLISH -->|已授权上线后验证| POST_RELEASE[N23 只读上线后验证与线上信号采集]
    POST_RELEASE --> FEEDBACK
    FEEDBACK --> END([流程结束])
```

图中的多入边只表达依赖关系，不代表“任意一个上游完成即可继续”。落地到 Multica 时，
`A06`、`N05`、`N09` 等汇合节点必须显式配置为：等待本次路由选中的全部必需分支完成，
再校验 Artifact 完整性后继续。未被路由选中的分支记为 `skipped_by_policy`，不能记为成功，
也不能导致汇合节点永久等待。

`N21 Schema Registry` 和 `N22 Agent 版本发布控制` 属于控制平面，不作为普通业务分支
出现在主 DAG 中。N21 校验每次 Artifact 交接，N22 在工作流启动前决定允许使用的 Agent、
模型、Prompt 和工具版本。

## 6. Agent 和确定性节点清单

### 6.1 Agent 清单

| ID | Agent | 核心职责 | 主要输出 |
| --- | --- | --- | --- |
| A01 | Workflow Router | 选择工作流模板和必要分支 | `workflow_route.json` |
| A02 | Requirement Analyzer | 提取需求、验收标准和歧义 | `requirement_analysis.json` |
| A03 | Technical Design Analyzer | 提取架构、依赖和技术风险 | `technical_analysis.json` |
| A04 | Frontend MR Analyzer | 分析前端变更和影响 | `frontend_change_analysis.json` |
| A05 | Backend MR Analyzer | 分析后端变更和影响 | `backend_change_analysis.json` |
| A06 | Change Alignment | 对齐需求、方案和实现 | `alignment_result.json` |
| A07 | Risk Strategy | 风险分级并制定测试策略 | `test_strategy.json` |
| A08 | Test Designer | 生成父级 Test IR | `test_plan_ir.json` |
| A09 | Oracle 与测试防范覆盖审查 Agent | 审查预期可判定性和测试防范覆盖 | `oracle_review.json` |
| A10 | Case Splitter | 拆分不同测试层级 | `split_test_ir.json` |
| A11 | Split Coverage Auditor | 回查遗漏、重复和层级错误 | `split_coverage_review.json` |
| A12 | Test Selector | 选择本次需要执行的新 Case、存量 Case 和强制 Case | `test_selection.json` |
| A13 | Frontend Automation | 生成前端单元、组件或 UI 自动化 | 代码变更和 Manifest |
| A14 | Backend Automation | 生成后端单元、服务、API 或数据自动化 | 代码变更和 Manifest |
| A15 | Contract Automation | 生成接口契约测试 | 代码变更和 Manifest |
| A16 | E2E Automation | 生成关键链路测试 | 代码变更和 Manifest |
| A17-PERF | Performance Automation | 生成性能测试 | 性能测试代码或执行计划 |
| A17-SEC | Security Automation | 生成安全测试 | 安全测试代码或执行计划 |
| A17-A11Y | Accessibility Automation | 生成可访问性测试 | 可访问性测试代码或执行计划 |
| A17-COMPAT | Compatibility Automation | 生成兼容性测试 | 兼容性测试代码或执行计划 |
| A17-RES | Resilience Automation | 生成稳定性和容错测试 | 韧性测试代码或执行计划 |
| A17-DATA | Data Consistency Automation | 生成数据一致性测试 | 数据测试代码或执行计划 |
| A18-FE | Frontend Automation Reviewer | 审查前端自动化 | `automation_review.json` |
| A18-BE | Backend Automation Reviewer | 审查后端自动化 | `automation_review.json` |
| A18-CT | Contract Automation Reviewer | 审查契约自动化 | `automation_review.json` |
| A18-E2E | E2E Automation Reviewer | 审查 E2E 自动化 | `automation_review.json` |
| A18-PERF | Performance Reviewer | 审查性能测试和阈值 | `automation_review.json` |
| A18-SEC | Security Reviewer | 审查安全测试和权限边界 | `automation_review.json` |
| A18-A11Y | Accessibility Reviewer | 审查可访问性测试 | `automation_review.json` |
| A18-COMPAT | Compatibility Reviewer | 审查兼容性测试 | `automation_review.json` |
| A18-RES | Resilience Reviewer | 审查稳定性和容错测试 | `automation_review.json` |
| A18-DATA | Data Consistency Reviewer | 审查数据一致性测试 | `automation_review.json` |
| A19 | Failure Triage | 聚类并归因失败 | `failure_triage.json` |
| A20 | Report Analyzer | 解释覆盖、风险和结果 | `quality_report.md/json` |
| A21 | Testability Reviewer | 审查方案和实现是否具备可测性 | `testability_review.json` |

### 6.2 确定性节点清单

| ID | 节点 | 职责 |
| --- | --- | --- |
| N01 | 输入采集、标准化与解析质量校验 | 下载并解析文档、MR、OpenAPI，校验附件、表格、图片和权限完整性 |
| N02 | 输入版本冻结 | 记录文档版本、commit、环境和 Agent 版本 |
| N03 | Schema 与证据校验 | 校验 Agent 输出结构、引用完整性和来源存在性 |
| N04 | Test IR 校验 | 校验字段、唯一 ID、Oracle 和来源引用，并按问题类型路由回流 |
| N05 | 代码检查与安全扫描 | 格式化、lint、编译、依赖和敏感信息检查 |
| N06 | 修复路由与重试预算 | 按问题根因返回对应 Agent，并控制修复次数和成本 |
| N07 | 环境、数据和资源预检 | 校验部署版本、依赖、账号、数据、Flag 和锁 |
| N08 | 自动化测试并行执行 | 运行审核后的固定命令和自动化测试代码 |
| N09 | 证据标准化与汇合 | 汇合自动化、人工测试、日志、请求响应、截图、视频和 trace |
| N10 | 环境重试预算 | 仅对明确的环境类失败有限重试 |
| N11 | 确定性质量决策 | 按发布策略计算 pass/warn/block |
| N12 | 结果发布 | 发布报告、MR 评论和 Bug 草稿 |
| N13 | 反馈入评估集 | 保存人工修正，不在线自动改 Prompt |
| N14 | 测试资产目录与影响关系图快照 | 同步并冻结需求、Case、代码、接口、Bug 和结果之间的映射 |
| N15 | 执行计划编译与路由 | 将 Case 编译为生成、更新、直接执行、人工执行或跳过动作 |
| N16 | 环境与测试数据修复动作 | 执行白名单内的数据准备、环境部署、Flag 配置和账号初始化 |
| N17 | 人工与探索测试编排 | 创建人工任务、收集证据并等待结果 |
| N18 | 代码覆盖率与运行质量信号采集 | 确定性采集代码覆盖率、性能和运行质量信号 |
| N19 | 质量豁免登记 | 记录限时、限范围且不修改原质量结论的风险接受 |
| N20 | 跨运行缺陷去重 | 根据失败指纹和历史 Bug 判断新增、关联或重新打开 |
| N21 | Schema Registry 与迁移校验 | 管理 Artifact Schema 兼容、迁移和消费者版本 |
| N22 | Agent 版本发布控制 | 执行影子运行、灰度、回滚和版本冻结 |
| N23 | 只读上线后验证与线上信号采集 | 在单独授权下运行只读冒烟并采集 SLO 和逃逸缺陷 |

### 6.3 Agent 输入输出依赖

下表是后续拆建各 Agent 的最小依赖基线。实现时可以减少不需要的字段，但不得绕过指定
上游 Artifact 直接依赖聊天记录，也不得自行读取表中未授权的数据源。

| Agent | 必需输入 | 核心输出 | 直接消费者 |
| --- | --- | --- | --- |
| A01 | 任务目标、触发类型、可用输入清单、组织策略 | 工作流模式、启用分支、必需 Gate | N01、Multica |
| A02 | 冻结后的需求正文和附件 | 验收标准、业务规则、角色、场景、歧义和证据引用 | A06、A08、A21 |
| A03 | 冻结后的技术方案、架构图和接口说明 | 组件关系、数据流、依赖、约束和技术风险 | A06、A07、A21 |
| A04 | 前端 MR diff、目标 commit 和 N14 资产快照 | 页面与组件变更、交互影响、接口消费变化 | A06、A12 |
| A05 | 后端 MR diff、目标 commit 和 N14 影响关系图 | 接口、业务逻辑、数据、消息和权限影响 | A06、A12 |
| A06 | A02 至 A05 及 A21 的有效 Artifact | 需求、方案和实现映射，遗漏、冲突及未实现项 | A07、A08、G01 |
| A07 | 对齐结果、可测性结论、组织风险规则、历史缺陷和影响面 | 风险等级、必测层级、非功能要求和 Gate 策略 | A08、A12、Multica |
| A08 | 需求分析、技术分析、对齐结果和测试策略 | 父级 Test IR、需求覆盖矩阵 | A09 |
| A09 | 父级 Test IR、原始证据和 Oracle 规则库 | Oracle 审查、测试防范覆盖缺口、阻塞问题和修正建议 | N04、A08、G02 |
| A10 | 审核通过的父级 Test IR、测试层级规则 | 前端、后端、契约、E2E 和非功能子 Case | A11 |
| A11 | 父子 Test IR、覆盖矩阵和拆分规则 | 遗漏、重复、层级错误及拆分审查结论 | A10、A12 |
| A12 | 审核通过的 Test IR、MR 影响、N14 资产快照和强制策略 | 本次新增、受影响存量和策略强制 Case 集合及选择理由 | N15 |
| A13 | 前端 Test IR、前端仓库快照、测试框架约定 | Playwright 代码、Case 映射和执行 Manifest | A18-FE |
| A14 | 后端 Test IR、后端测试仓库快照、API 契约和框架约定 | API/数据测试代码、Case 映射和执行 Manifest | A18-BE |
| A15 | 契约 Test IR、OpenAPI 和消费者契约 | 契约测试代码、兼容性基线和执行 Manifest | A18-CT |
| A16 | E2E Test IR、关键链路、环境能力和跨服务证据点 | E2E 代码、链路映射和执行 Manifest | A18-E2E |
| A17-* | 对应非功能 Test IR、已批准阈值、环境容量和专用工具约束 | 对应专项测试代码或执行计划、执行 Manifest | 对应的 A18 专项审查 Agent |
| A18-* | 对应 Test IR、生成代码、仓库规范和安全规则 | 审查结论、缺陷清单、问题类型和可审查修复建议 | N05、G03、N06 |
| A19 | 预检结果、标准化执行证据、环境、数据和历史失败指纹 | 失败聚类、归因、证据充分度和建议动作 | G04、N16、N20、N11、A20 |
| A20 | Test IR、执行计划、覆盖数据、自动化/人工结果、归因与去重结果、豁免记录和质量决策 | 面向人的质量报告及机器可读报告 | N12 |
| A21 | 需求分析、技术方案、可观测性和测试工具能力 | 可测性缺口、阻塞项和改进建议 | A06、A07、G01 |

## 7. Agent 统一实现规范

每个 Agent 必须有独立规范文件，并按以下模板定义：

```yaml
agent_id: A00
name: example-agent
objective: 单一、可验证的目标
owner: qa-platform
depends_on: []
allowed_inputs: []
input_schemas: []
output_schema: schema/example-output.schema.json
allowed_tools: []
write_scope: []
forbidden_actions: []
blocking_conditions: []
retryable_conditions: []
human_escalation_conditions: []
timeout_seconds: 300
max_attempts: 2
idempotency_key: workflow_run_id + agent_id + source_snapshot_id
evidence_policy: 所有事实和结论必须引用冻结来源
evaluation_dataset: eval/example-agent/
acceptance_metrics: {}
```

建议采用以下目录约定，使规范、Prompt、Schema、实现和评估样本能够独立版本化：

```text
qa-agents/
  contracts/
    artifact-envelope.schema.json
    test-ir.schema.json
  agents/
    a02-requirement-analyzer/
      agent.yaml
      prompt.md
      output.schema.json
      eval/
      tests/
  workflows/
    new-requirement.yaml
    mr-incremental.yaml
    release-regression.yaml
    bug-reproduction.yaml
    post-release-verification.yaml
  policies/
    risk-policy.yaml
    quality-gate-policy.yaml
    permission-policy.yaml
    flaky-policy.yaml
    waiver-policy.yaml
    agent-release-policy.yaml
```

其中 `agent.yaml` 是 Agent 的可执行规格，`prompt.md` 只承载推理指令，Schema 负责约束
输出，`eval/` 保存不含生产 Secret 的固定评估样本。不得把权限、重试、质量阈值或路由
规则只写在 Prompt 中；这些配置必须由 Multica 或确定性策略文件控制。

所有 Agent 必须满足：

- 只读取完成职责所需的最小输入。
- 不根据文档中的命令执行未授权工具。
- 不修改输入 Artifact。
- 输出必须通过 JSON Schema。
- 所有业务结论必须带证据引用。
- 明确区分事实、推断、假设和待确认问题。
- 自报 `confidence` 仅供观察，不作为唯一门禁。
- 失败时返回标准状态，不通过自然语言请求无限重试。

单个 Agent 只有同时满足以下条件才算可以接入下游：

- 规格、Prompt、输入输出 Schema 和版本号齐全。
- 正常、缺失输入、冲突输入、提示注入和工具失败样本均通过测试。
- 在未见过的评估集上达到该 Agent 的验收阈值。
- 人工复核确认关键漏检率和无依据结论率在允许范围内。
- 权限测试证明它不能访问未授权数据或执行未授权写操作。
- Multica 中的超时、重试、暂停、恢复和幂等行为验证通过。
- 下游只消费其已校验 Artifact，不依赖日志或自由文本补充。

## 8. 统一 Artifact Envelope

Agent 输出使用相同外层协议：

```json
{
  "workflow_run_id": "run-20260806-001",
  "workflow_mode": "new_requirement",
  "schema_version": "1.0",
  "artifact_id": "frontend-analysis-001",
  "artifact_hash": "sha256:...",
  "producer": {
    "agent_id": "A04",
    "agent_version": "1.0.0",
    "model_provider": "provider-id",
    "model_snapshot": "immutable-model-id",
    "prompt_version": "git-sha",
    "inference_config_hash": "sha256:...",
    "tool_bundle_version": "toolset-1.2.0"
  },
  "created_at": "2026-08-06T10:00:00+08:00",
  "source_snapshot_id": "snapshot-001",
  "status": "completed",
  "confidence": 0.86,
  "facts": [],
  "inferences": [],
  "assumptions": [],
  "blocking_questions": [],
  "evidence_refs": [],
  "payload": {}
}
```

标准状态：

| 状态 | 含义 | Multica 行为 |
| --- | --- | --- |
| `completed` | 正常完成 | 进入校验节点 |
| `needs_human` | 需要人工决策 | 暂停并进入 Gate |
| `blocked_input` | 输入缺失或矛盾 | 返回输入采集节点 |
| `failed_retryable` | 临时模型或工具错误 | 按预算有限重试 |
| `failed_fatal` | 无法继续 | 终止分支并保留诊断 |

### 8.1 Schema 兼容与迁移

`N21 Schema Registry` 管理所有 Artifact Schema。每个消费者必须声明支持的 Schema
版本范围，Multica 在调用前完成兼容性检查：

- 向后兼容字段使用 minor 版本升级；删除字段、改变语义或类型使用 major 版本升级。
- 迁移必须由确定性转换器完成，不允许 Agent 临时猜测字段含义。
- 迁移后同时保留原始 Artifact、迁移结果、转换器版本和差异。
- 找不到受支持的迁移路径时状态为 `blocked_input`，禁止把未知字段静默丢弃。
- 长流程恢复时使用运行开始时冻结的 Schema 和 Agent 版本，不能自动切换到最新版。

## 9. 输入版本冻结与失效规则

`N01` 必须先生成 `source_extraction_manifest.json`，记录每个输入的来源权限、附件数量、
文本块、表格、图片、OCR、解析器版本、内容哈希、解析置信度和已知遗漏。需求正文、关键
附件、接口定义或架构图无法读取时必须进入 `blocked_input`，不能基于残缺输入继续推理。

`N02` 必须生成不可变 `source_snapshot.json`：

```yaml
snapshot_id: snapshot-001
requirement:
  id: REQ-102
  version: v3
  content_hash: sha256:...
technical_design:
  id: TECH-88
  version: v2
frontend:
  repository: frontend-repo
  commit: abc123
backend:
  repository: backend-repo
  commit: def456
contracts:
  openapi_hash: sha256:...
test_assets:
  catalog_snapshot_id: asset-snapshot-001
  dependency_graph_hash: sha256:...
environment:
  target: qa-112
  frontend_commit: abc123
  backend_commit: def456
```

失效规则：

- MR 出现新 commit 时，基于旧 commit 的分析仍保留，但标记为 stale。
- 需求或方案版本变化时，相关下游 Artifact 全部失效。
- OpenAPI 变化时，契约、后端和相关前端 Case 失效。
- 测试资产目录或影响关系图变化时，A12 选择结果和执行计划失效。
- 测试环境部署版本与目标 commit 不一致时，禁止生成正式质量结论。
- Agent、模型或 Prompt 升级不自动使历史结果失效，但必须可追溯。

## 10. 来源优先级和冲突规则

不同来源不是同等含义：

1. 已批准需求和验收标准定义业务期望。
2. 已批准技术方案定义设计约束和实现路径。
3. OpenAPI 或消费者契约定义接口协议。
4. MR 和当前代码表示实际实现，不自动等于正确期望。
5. 历史 Case 和历史行为只能作为兼容证据，不能覆盖新需求。

当需求、技术方案、契约和代码冲突时，Agent 必须输出冲突并进入人工确认，不能自行
选择一个来源作为真相。

### 10.1 测试资产目录与影响关系图

`N14` 不是 Agent，而是持续维护的确定性索引服务。它至少维护以下关系：

```text
需求/验收点
  <-> Test IR/人工 Case
  <-> 自动化测试函数和代码位置
  <-> 前端组件、后端模块、API、表、消息主题和 Feature Flag
  <-> 历史 Bug、执行结果、Flaky 记录和负责人
```

每次工作流冻结一个只读资产快照供 A04、A05 和 A12 使用。索引必须记录来源和更新时间；
无法建立影响关系时标记 `unknown_impact`，由确定性策略扩大测试范围。

Case 生命周期至少支持：`draft`、`approved`、`active`、`quarantined`、`deprecated` 和
`superseded`。每个 Case 必须有稳定 ID、版本、负责人、来源、自动化映射和替代关系。
Agent 不得覆盖人工维护的 Case；重复 Case 只能提出合并建议，由审核或规则节点处理。

## 11. 风险与测试策略

`A07` 根据以下维度评估风险：

- 业务影响和用户规模。
- 代码改动范围和依赖扩散。
- 公共组件、公共服务和公共数据结构。
- 权限、审批、资金、删除和敏感数据。
- 数据迁移、状态机、异步和最终一致性。
- 历史缺陷密度和线上事故。
- 是否缺少可观测性或回滚能力。

输出示例：

```yaml
risk_level: high
risk_reasons:
  - 修改公共语言服务
required_layers:
  - backend
  - contract
  - e2e
required_non_functional:
  - compatibility
regression_policy:
  impacted_regression: true
  mandatory_suites:
    - authentication-smoke
human_gates:
  test_ir_review: required
  automation_review: required
```

风险规则必须有确定性策略兜底。例如认证、权限、数据删除和核心 P0 冒烟不能被 Agent
标记为“无需执行”。

### 11.1 可测性评审

`A21` 在测试设计前审查需求和技术方案是否具备可验证条件，至少检查：

- 关键状态是否有稳定的查询接口、日志、指标和 trace。
- 异步任务是否能查询进度、终态和失败原因。
- Feature Flag、灰度和租户配置是否可在测试环境受控设置。
- 测试数据是否可创建、隔离、重置和清理。
- 外部依赖是否可 Mock，故障和超时是否可安全注入。
- 时间、随机数、消息和最终一致性是否有可控测试机制。
- 权限和审计结果是否有独立证据，而不是只依赖页面文案。

缺少可测性但不影响需求正确性时输出改进项；关键预期没有任何可靠观测点时输出阻塞项，
进入 G01。可测性问题不能等到自动化代码生成后才暴露。

## 12. Test IR 规范

Test IR 是框架无关的测试主模型：

```yaml
id: REQ-12-BE-01
parent_case_id: REQ-12-SCENE-01
title: 英文个人环境下查询中文翻译
layer: backend
test_level: api
risk: high
priority: P1
source_refs:
  - type: requirement
    id: REQ-12
    location: section-3.2
  - type: backend_mr
    id: "!302"
    location: UserLanguageService.java:85
preconditions:
  - 使用专用测试账号登录
test_data:
  personal_language: en
  translation_language: zh-CN
steps:
  - 切换个人语言为英文
  - 等待语言配置生效
  - 查询中文翻译词条
expected:
  - id: EXP-01
    description: needTransName 为英文
    oracle:
      type: deterministic
      assertion: contains_latin_and_no_han
      source_ref: REQ-12:section-3.2
  - id: EXP-02
    description: translateValue 为中文
    oracle:
      type: deterministic
      assertion: contains_han
      source_ref: REQ-12:section-3.2
cleanup: []
execution:
  allowed_modes:
    - automated
    - manual
  required_evidence:
    - request_response
automation:
  candidate: true
  framework: pytest
  repository: pytest_for_bi
```

强制字段：

- 唯一 Case ID、父 Case ID、责任层、测试级别、风险和优先级。
- 需求、方案、契约或代码证据引用。
- 前置条件、测试数据、步骤、预期和清理策略。
- 每个预期结果的 Oracle 类型、断言和来源。
- 允许的执行方式、必需证据和人工未执行处理策略。
- 自动化候选、框架、仓库和执行环境。

## 13. Oracle 与测试防范覆盖审查

`A09` 负责阻止无法确定判定的 Case 进入自动化。

这里的“测试防范覆盖”指需求、验收标准、业务规则、风险、异常、边界、权限、状态变化和
数据一致性等测试设计覆盖，不是语句、分支或函数代码覆盖率。代码覆盖率只能在自动化
执行后由确定性工具采集。

以下预期不合格：

- 页面展示正常。
- 接口返回合理。
- 性能符合预期。
- 翻译结果正确。

必须改写成可执行断言或标记为人工确认。例如：

- `Result.FailureCode == 0`。
- 无权限用户看不到提交按钮。
- P95 小于已批准的性能阈值。
- `needTransName` 符合个人语言规则。

审查结果必须包含：

- 需求覆盖缺口。
- 无证据预期。
- 不可自动判定预期。
- 相互冲突预期。
- 缺失测试数据或清理策略。
- 建议转人工测试的 Case。

### 13.1 N04 校验失败后的分类回流

`N04` 是确定性校验和路由节点，不负责重新设计 Case。校验不通过时，必须生成结构化
问题清单，并按问题根因返回对应上游继续分析和细化：

| 失败类型 | 回流节点 | 修正动作 |
| --- | --- | --- |
| Schema、必填字段、唯一 ID 或来源引用错误 | A08 | 定向修正 Test IR 的结构和引用 |
| Oracle 不可执行、测试防范覆盖不足、测试数据或清理策略缺失 | A08 | 根据 A09 问题清单补充 Case、断言和数据，再重新经过 A09 |
| 风险等级、必测层级或非功能测试策略缺失 | A07 | 重新分析测试策略，再由 A08 补充 Test IR |
| 需求、技术方案、契约或代码存在上游冲突 | A06/G01 | 重新对齐并人工确认事实，再经过 A07、A08 和 A09 |
| 连续修正超过重试预算 | 人工处理 | 暂停流程并保留全部版本和问题，不允许带病进入 G02 |

每条问题至少包含：`issue_code`、`case_id`、`expected_id`、`source_refs`、问题描述和
`route_to`。回流修正必须遵守以下规则：

- 保留原 Test IR，不覆盖历史版本。
- 只修改问题涉及的 Case，记录修正前后差异。
- 修正后重新执行所有受影响的 A09 审查和 N04 校验。
- 上游事实或策略发生变化时，使相关下游 Artifact 失效并重新生成。
- 限制自动修正次数；超过预算后暂停并请求人工处理。
- 只有 N04 全部通过，才允许进入 G02 Test IR 审核 Gate。

## 14. Case 拆分与覆盖回查

测试层级：

| 层级 | 主要验证内容 |
| --- | --- |
| frontend | 前端单元/组件、页面、交互、路由、权限可见性和异常展示 |
| backend | 后端单元/服务/API、参数、业务规则、权限、状态、幂等、数据和异步处理 |
| contract | 字段、类型、必填、枚举、错误码和消费者兼容性 |
| e2e | 必须跨前后端验证的关键用户链路 |
| non_functional | 性能、安全、可访问性、兼容性、韧性和数据一致性 |

拆分后，`A11` 必须验证：

- 父 Case 每个预期至少被一个子 Case 覆盖。
- 同一个边界组合没有跨层无意义重复。
- 高风险预期有明确自动化或人工执行责任。
- 子 Case 没有丢失来源、数据、Oracle 和清理要求。
- 前端、后端和契约责任边界正确。

## 15. 测试选择

`A12` 负责形成本次工作流最终需要生成或执行的测试集合，不只选择存量回归。测试集合
由三部分组成：本次需求或变更新增的 Case、受影响的存量 Case，以及组织策略强制执行的
冒烟、权限、认证等 Case。

`A12` 根据以下证据进行选择：

- MR Diff 和代码调用关系。
- API、数据库、消息和公共组件依赖。
- Case 与代码、需求和历史 Bug 的映射。
- Case 风险、耗时、稳定性和最近执行结果。
- 变更模块所有者和历史缺陷密度。

每条候选 Case 输出：`must_run`、`recommended`、`skip` 或 `needs_human`，并附原因。

`N15` 再把选择结果和测试资产目录编译成确定性的执行计划。每条 Case 必须且只能选择
一个动作：

| 动作 | 含义 | 后续路由 |
| --- | --- | --- |
| `generate_new` | 没有自动化资产，需要新建 | A13-A17-* 对应生成 Agent |
| `update_existing` | 已有自动化受变更影响，需要修改 | 对应生成 Agent，且保留旧代码差异 |
| `run_existing` | 已有自动化仍然有效 | 跳过生成，直接进入预检和 N08 |
| `manual_run` | 当前不适合自动化或属于探索性测试 | N17 人工与探索测试编排 |
| `skip` | 策略允许本次不执行 | 记录证据、原因和批准策略，不进入执行 |

同一个 Case 不得既重新生成又直接执行。`run_existing` 必须引用已经审核的测试代码 commit；
`skip` 不能等价为 `passed`，并且需要进入 N11 的覆盖和风险计算。

确定性兜底规则：

- P0 冒烟不可跳过。
- 认证、权限和公共基础能力按策略强制执行。
- 无法解析影响范围时宁可扩大测试范围，不可静默缩小。
- Agent 只能提出选择，最终集合由策略节点合并计算。

## 16. 自动化生成与专项审查

### 16.1 前端自动化

- 使用确定性的 Playwright 测试作为正式回归资产。
- 根据 Test IR 的 `test_level` 使用仓库已有的单元、组件或 UI 测试框架，不强制所有前端
  Case 都通过浏览器 E2E 验证。
- 优先使用 role、label、test id 等稳定定位器。
- 只在有真实复用时创建页面或组件封装。
- 明确等待业务状态，不使用任意固定 sleep 替代条件等待。
- AI 浏览器可以探索，但探索结果必须固化为可审查代码。

### 16.2 后端自动化

- 优先复用仓库已有 fixture、认证、客户端和数据工厂。
- 优先在单元或服务层验证组合逻辑，只把必须经过 HTTP、数据库或跨服务的行为放到 API
  或集成测试层。
- 断言业务结果，不能只检查 HTTP 200。
- 数据库默认只读并受表、语句和环境白名单限制。
- 异步流程必须使用明确超时和轮询策略。
- Case 必须可以重复运行并清理自己的数据。

### 16.3 契约和 E2E

- 契约测试覆盖 OpenAPI、消费者协议和兼容性。
- E2E 只覆盖关键链路，不重复后端的全部参数组合。
- 关键跨服务状态必须有可观测证据。

### 16.4 非功能测试

由风险策略按需启用独立专项 Agent：

| Agent | 范围 |
| --- | --- |
| A17-PERF | 性能、容量和资源消耗 |
| A17-SEC | 认证、授权、输入安全和敏感数据 |
| A17-A11Y | 可访问性标准和辅助技术 |
| A17-COMPAT | 浏览器、设备、版本和协议兼容性 |
| A17-RES | 稳定性、容错、降级和恢复 |
| A17-DATA | 迁移、异步、对账和数据一致性 |

每个专项 Agent 使用独立工具、权限、Schema、评估集和审查 Agent。非功能阈值必须来自
已批准标准，不能由模型自行生成。

### 16.5 专项代码审查

前端、后端、契约、E2E 和非功能测试分别使用对应审查 Agent，再进入统一的代码检查
和安全扫描节点。审查至少覆盖：

- 是否忠实实现 Test IR。
- 是否缺少关键断言。
- 是否使用稳定定位、正确等待和可靠数据隔离。
- 是否硬编码账号、Token、Cookie、密码或生产地址。
- 是否可重复执行、可清理和可诊断。
- 是否复用现有框架而非重复造轮子。

### 16.6 自动化修复路由

N05、G03 或执行结果发现自动化问题后，由 `N06` 根据标准问题码回流：

| 问题类型 | 回流节点 |
| --- | --- |
| 前端、后端、契约、E2E 或非功能代码问题 | 对应 A13-A17-* 生成 Agent |
| Case 层级、职责边界或拆分问题 | A10 |
| Test IR、Oracle 或测试数据定义问题 | A08，随后重新经过 A09/N04 |
| 风险策略问题 | A07 |
| 上游事实冲突 | A06/G01 |

修复必须基于上一版本做定向补丁，保留代码和 Artifact 差异。超过预算时输出未解决问题并
进入 N11，结论只能是 `blocked` 或 `inconclusive`，不能把失败代码送入执行。

## 17. 环境、数据和资源预检

`N07` 在正式执行前记录环境指纹并检查：

- 前后端部署 commit 与目标快照一致。
- 服务、数据库、缓存和消息依赖健康。
- 测试账号存在且权限正确。
- Feature Flag、灰度配置和租户配置正确。
- 测试数据满足前置条件。
- 浏览器、时区、语言和系统时间符合要求。
- 测试命名空间可用且清理策略存在。
- 共享资源锁已经获取。

资源锁示例：

```yaml
locks:
  - resource: test-account-1002
    reason: 个人语言是账号级全局状态
    mode: exclusive
  - resource: tenant-91863-language-config
    mode: exclusive
```

预检失败不能进入正式 Case 执行，否则会制造批量无效失败。

### 17.1 环境与数据修复

可恢复的预检失败必须先进入 `N16` 执行明确动作，例如部署指定 commit、初始化测试账号、
准备或重置数据、设置 Feature Flag、等待资源锁。每个动作必须记录期望状态、执行前状态、
执行结果、补偿清理和幂等键。没有状态变化时禁止原地重复预检。

测试数据必须按敏感级别分类。默认使用合成数据；使用脱敏数据需要审批、用途限制、访问
审计和自动过期。数据租约必须包含负责人、命名空间、TTL 和清理状态，工作流取消或超时
也必须执行补偿清理。

## 18. 执行、证据和失败归因

前端、后端、契约、E2E 和非功能测试尽量并行，但必须遵守资源锁和环境容量。

`N17` 将 `manual_run` Case 创建为人工或探索测试任务，要求执行人提交结构化步骤、实际
结果、截图或日志、结论和未执行原因。人工结果与自动化结果在 N09 汇合；必测人工 Case
未完成时，N11 不能给出 `passed`。

`N18` 使用语言和框架对应的确定性工具采集语句、分支、函数覆盖率及性能等运行信号。
代码覆盖率只用于发现未执行区域，不能替代需求覆盖和 Oracle 审查；阈值必须按仓库和
模块配置。建议在离线评估或受控 CI 中增加 mutation testing，验证测试是否能发现注入缺陷。

每个失败至少保留：

- Test IR ID、测试代码 commit 和环境快照。
- 请求、响应、错误堆栈和 trace ID。
- 前端截图、DOM、视频和控制台日志。
- 数据准备、清理和依赖健康结果。
- 首次失败及允许重试后的全部结果。

`A19` 先聚类再归因。一个登录服务异常导致 200 条失败时，应形成一个根因组，而不是
创建 200 个 Bug。

标准分类：

| 分类 | 示例 | 默认处理 |
| --- | --- | --- |
| 产品缺陷 | 返回值违反明确需求 | 生成 Bug 草稿 |
| 自动化缺陷 | 字段路径或定位器错误 | 生成测试修复建议 |
| 测试数据问题 | ID 失效或数据未初始化 | 数据修复流程 |
| 环境问题 | 登录服务或依赖不可用 | 按预算有限重试 |
| 需求歧义 | 文档没有定义预期 | 人工确认 |
| 待确认 | 证据不足或多个原因可能 | 不自动建正式 Bug |

产品缺陷进入发布前，`N20` 必须根据错误指纹、接口、堆栈、Test IR、环境版本和历史 Bug
进行跨运行去重，输出 `create_new`、`link_existing`、`reopen` 或 `needs_human`。A19 的单次
运行聚类不能替代跨版本、跨工作流去重。

### 18.1 Flaky Case 治理

Flaky 不能通过无限重试隐藏。测试资产目录必须记录失败指纹、最近执行历史和负责人：

- 只有环境抖动等已分类原因允许有限重试，业务断言失败不重试。
- 进入 `quarantined` 必须有证据、负责人、影响范围和到期时间。
- 隔离 Case 仍计入覆盖缺口；关键 Case 被隔离时质量结论按策略阻塞。
- 到期前必须修复并通过连续稳定运行才能恢复为 `active`。
- 报告分别展示首次结果、重试结果和最终分类，不能只展示重试后的通过。

## 19. 确定性质量决策

`N11` 使用版本化策略规则计算结论，不能由 Agent 自由决定是否发布。

N11 必须同时读取 Test IR、N15 执行计划、自动化与人工结果、跳过原因、Flaky 隔离、环境
状态和覆盖缺口。没有失败不等于通过：没有 Case 实际执行、必测人工 Case 未完成、关键
Case 被跳过或隔离时，必须按策略输出 `blocked` 或 `inconclusive`。

```yaml
decision: blocked
release_disposition: pending
policy_version: quality-gate-v1
reasons:
  - P0 Case 失败 1 条
  - 高风险需求 REQ-102 未覆盖
  - 测试环境版本与目标 MR 不一致
warnings:
  - 2 条低风险 Case 因环境问题未执行
```

建议结论：

| 结论 | 含义 |
| --- | --- |
| `passed` | 满足所有强制质量规则 |
| `passed_with_warning` | 无阻塞问题，但存在明确风险提示 |
| `blocked` | 存在强制失败、环境不一致或高风险未覆盖 |
| `inconclusive` | 证据不足，无法形成可靠结论 |

### 19.1 质量豁免

真实发布流程允许经授权的风险接受，但豁免不能修改 N11 的原始质量结论。例如原结论仍为
`blocked`，另行记录 `release_disposition: approved_exception`。

`G05/N19` 必须记录豁免范围、失败 Case、风险说明、审批人、责任人、补偿措施、有效期和
关联发布版本。豁免只对指定版本有效，到期自动失效；权限、资金、数据破坏和未授权生产
操作等红线问题不可豁免。

## 20. 人工 Gate 与风险分级

| 风险 | Test IR | 自动化代码 | 执行结论 |
| --- | --- | --- | --- |
| 高风险 | 必须审核 | 必须审核 | 必须审核 |
| 中风险 | 必须审核 | 审核或高比例抽样 | 失败时审核 |
| 低风险 | 初期审核，成熟后自动 | 抽样审核 | 异常时介入 |
| 已验证模板 | 策略允许自动 | 策略允许自动 | 保留审计 |

第一阶段所有 Gate 默认开启。只有内部评估证明稳定后，才逐步开放低风险流程。

每个 Gate 必须配置允许审批的角色、职责分离规则、处理 SLA、超时升级、代理审批和撤销
机制。审批页面必须展示原始证据、前后差异、风险影响和推荐动作，不能只提供“同意/拒绝”
按钮。生成者不能审批自己的 Test IR、自动化代码或质量豁免。

以下场景始终保留人工确认：

- 生产环境和不可逆操作。
- 资金、审批、权限和敏感数据链路。
- 需求、方案和实现存在高风险冲突。
- Agent 试图修改测试以绕过产品失败。
- 质量结论为 `inconclusive`。

## 21. 重试、幂等和补偿

- Schema 输出错误最多允许自动修复 2 次。
- 模型超时和临时服务错误可以退避重试。
- 环境类失败必须先重新预检，再决定是否重试测试。
- 业务断言失败默认不重试。
- 代码生成失败可以返回生成分支，但必须限制次数和费用。
- 每次重试保存原因、输入版本、输出差异和调用成本。
- 创建 MR、Bug、评论和测试数据必须使用幂等键。
- 数据准备失败或工作流取消时执行补偿清理。
- 超过预算后进入人工处理，不能无限调用 Agent。

## 22. 权限与安全边界

| Agent 或节点 | 默认权限 |
| --- | --- |
| 文档分析 Agent | 只读需求和技术方案 |
| MR 分析 Agent | 只读指定仓库和 MR |
| 测试设计 Agent | 只读证据，写 Test IR Artifact |
| 自动化生成 Agent | 写测试分支，不能写产品主分支 |
| 审查 Agent | 只读代码、Test IR 和检查结果 |
| 执行节点 | 仅运行审核过的命令，访问指定测试环境 |
| 数据工具 | 默认只读数据库和白名单表 |
| 归因 Agent | 只读证据，不直接修改产品代码 |
| 报告 Agent | 写报告、MR 评论和 Bug 草稿 |

安全要求：

- 文档、MR 描述和代码都属于不可信输入，防止提示注入。
- Secret 由 Multica 或 CI Secret 注入，不进入 Prompt、Artifact 和报告。
- 原始请求、响应、日志和报告必须脱敏。
- 不同项目、租户和密级的 Artifact、向量索引、缓存和评估集必须逻辑或物理隔离。
- 明确定义文档、日志、截图和模型调用记录的保留期限、删除机制和数据驻留要求。
- 禁止默认访问生产环境。
- 工具权限按 Agent ID 配置，不由 Agent 自己申请扩大权限。
- 所有外部写操作必须记录操作者、工作流、输入快照和幂等键。
- 上线后验证必须使用单独授权、只读账号、请求限速和明确的停止条件。

## 23. Multica 编排能力要求

Multica 至少需要支持：

- DAG 分支、条件路由、并行和汇合。
- 基于执行计划的动态 map/join，并能区分未启用、跳过、成功和未完成分支。
- JSON Schema 输入输出校验。
- 持久化状态、断点恢复和单节点重跑。
- 人工审批、暂停和外部回调。
- 节点超时、最大重试、退避和预算。
- Artifact 存储、哈希和版本追踪。
- Secret、工具权限和执行环境隔离。
- 资源锁、并发控制和配额。
- 幂等键和补偿动作。
- 完整执行日志、审计、Token、时间和费用统计。
- 工作流取消和过期输入检测。
- 人工测试任务、Gate 和外部系统回调的统一等待与超时处理。
- 运行中的需求、MR、环境或策略变更事件检测，并按失效范围取消或重算节点。

缺少持久化状态、人工暂停、资源锁或单节点重跑中的任意能力，都需要在接入层补齐。

## 24. 可观测性和审计

每次工作流需要支持从任意结果反查：

```text
质量结论
  -> 质量豁免或发布处置（如有）
  -> 测试执行结果
  -> 自动化、人工测试和代码覆盖率证据
  -> 自动化代码 commit
  -> 子 Case 和父 Case
  -> 风险策略
  -> 需求、方案、MR 和 OpenAPI 快照
  -> 测试资产目录与影响关系图快照
  -> Agent、模型、Prompt 和工具版本
```

需要记录：

- 每个节点输入输出哈希、开始结束时间和状态。
- Agent Token、费用、重试和人工等待时间。
- Artifact 下载、读取和外部写操作。
- 人工审批人、审批结论和修正内容。
- 测试环境、账号、数据和资源锁占用。
- 质量豁免、Flaky 隔离、人工测试和上线后验证记录。

## 25. 评估体系

### 25.1 固定评估集

- 历史需求和人工审核后的标准 Case。
- 历史 Bug、修复 MR 和回归 Case。
- 前端、后端、契约和跨服务 MR 样本。
- 故意注入的代码缺陷和契约不兼容。
- 缺失、矛盾和模糊需求。
- 环境、数据和自动化失败样本。

### 25.2 核心指标

- 关键需求覆盖率和关键 Case 漏检率。
- 无效、重复和无法执行 Case 比例。
- Oracle 无证据率和不可判定率。
- 前后端、契约和 E2E 层级拆分准确率。
- 人工修改比例及修改原因。
- 自动化首次 lint、编译和试跑成功率。
- 测试选择的缺陷召回率和执行缩减比例。
- 输入解析完整率和关键附件漏解析率。
- 人工必测 Case 完成率和证据合格率。
- 代码覆盖变化、mutation score 和关键变更未覆盖率。
- 失败聚类和归因准确率。
- 误报、漏报和 Flaky 比例。
- Flaky 隔离存量、超期率和恢复周期。
- 质量豁免数量、超期率和豁免后缺陷逃逸率。
- 历史 Bug 重发现率。
- 单次工作流耗时、Token 和费用。

不能使用供应商宣传的通用准确率作为上线依据。每个 Agent 都必须用公司真实样本独立
评估，并保留未见过的前向测试集。

## 26. 人工反馈和学习闭环

人工修改不能直接在线改变生产 Agent。正确流程为：

```text
人工修正
  -> 保存原始输出和修正结果
  -> 标注错误类型
  -> 加入候选评估集
  -> 离线更新规则、示例、Prompt 或脚本
  -> 回归评估
  -> 版本化发布 Agent
```

这样可以避免一次错误修正污染其他业务场景，也能评估改动是否造成能力回退。

### 26.1 Agent 版本发布

`N22` 管理 Agent、模型、Prompt、工具和规则的组合版本。新版本必须依次经过固定评估集、
未见前向集、历史运行重放、影子运行和低风险灰度；达到验收阈值后才能扩大流量。发布时
冻结模型快照和推理参数，持续比较新旧版本的漏检、无依据结论、人工修改、耗时和费用。

任一关键指标恶化超过阈值时自动停止灰度并回滚。供应商模型别名、线上 Prompt 或工具
依赖变化不能绕过 N22 直接进入生产工作流。

### 26.2 上线后反馈

`N23` 只在发布单明确授权后运行只读冒烟并采集 SLO、错误率、trace 和线上缺陷。线上
缺陷必须映射回需求、Test IR、测试选择和质量决策，标注为 Oracle 缺失、覆盖缺口、选择
遗漏、环境差异或已知豁免，进入离线评估和规则修正流程。

上线后信号不能直接触发生产写操作，也不能在线自动修改 Case、Prompt 或质量策略。

## 27. 分阶段实施路线

### 阶段 0：契约、平台和评估基础

- 完成 Envelope、Test IR 和各 Agent JSON Schema。
- 打通 Multica 的 Artifact、Schema Registry、状态、Gate、Secret、锁和审计。
- 建设测试资产目录、Case 生命周期和影响关系图的最小版本。
- 建立第一批需求、MR、Case 和 Bug 评估集。
- 暂不追求自动化代码生成。

### 阶段 1：测试设计质量闭环

- 使用固定流程实现 A02 至 A11 和 A21 可测性评审。
- 生成功能测试策略、Test IR 和覆盖矩阵。
- 全量人工审核并记录修正。
- 验证需求理解、Oracle 和拆分准确性。

### 阶段 2：测试选择和代码生成

- 实现 A12 至 A18-*。
- 实现 N15 执行计划编译，区分生成、更新、直接执行、人工执行和跳过。
- 在各模式稳定后实现 A01 路由 Agent，组合多种工作流。
- 生成 pytest、Playwright 和契约测试 MR。
- 自动执行代码检查和隔离试跑。
- 代码必须人工审核后合入。

### 阶段 3：测试环境自主执行

- 实现环境、数据、资源锁和证据标准化节点。
- 实现环境修复动作、人工/探索测试、代码覆盖率和 Flaky 治理。
- 实现失败聚类与归因。
- 接入跨运行 Bug 去重。
- 自动运行低风险测试，高风险仍保留 Gate。

### 阶段 4：确定性质量门禁

- 接入版本化质量策略。
- 输出 pass、warning、blocked 或 inconclusive。
- 接入限时、限范围且不修改原结论的质量豁免。
- 与 MR、发布流程和 Bug 系统集成。

### 阶段 5：有限自治闭环

- 低风险、已验证模板逐步减少人工 Gate。
- 高置信度产品问题自动创建 Bug 草稿。
- 人工反馈进入离线评估和版本升级流程。
- 通过影子运行、灰度和回滚管理 Agent 版本。
- 按审批启用只读上线后验证和线上缺陷回流。
- 不开放静默自愈、自动放宽断言和未审批生产操作。

## 28. 第一阶段建议实现顺序

后续实现各 Agent 时，建议严格按以下顺序：

1. 定义 Artifact Envelope、证据引用和 Schema 兼容策略。
2. 定义 Test IR、Oracle、Case 生命周期和执行动作 Schema。
3. 实现输入解析质量校验与版本冻结节点。
4. 建设 N14 测试资产目录和影响关系图最小版本。
5. 实现 A02 需求分析 Agent，并建立评估集。
6. 实现 A04/A05 MR 分析 Agent。
7. 实现 A03 技术方案分析和 A21 可测性评审 Agent。
8. 实现 A06 需求与变更对齐 Agent。
9. 实现 A07 风险与测试策略 Agent。
10. 实现 A08 测试设计 Agent。
11. 实现 A09 Oracle 与测试防范覆盖审查 Agent。
12. 实现 A10 Case 拆分和 A11 覆盖回查 Agent。
13. 实现 A12 测试选择和 N15 执行计划编译节点。
14. 最后补充 A01 路由 Agent，组合多种工作流模式。

不要同时实现所有 Agent。每完成一个 Agent，都必须：

- 用独立评估集验证；
- 记录人工修正；
- 验证输出 Schema；
- 验证证据引用；
- 使用未泄漏预期答案的样本做前向测试；
- 达到验收标准后再作为下游 Agent 的稳定输入。

## 29. 系统级完成标准

系统进入真实研发流程前，至少满足：

- 任意质量结论可以追溯到冻结的需求、方案、MR 和环境版本。
- 测试资产目录能追踪需求、Case、自动化代码、变更模块、Bug 和执行结果。
- 高风险需求没有无证据或不可判定 Oracle。
- Agent 输出经过 Schema、证据和权限校验。
- 自动化代码由独立 Agent 和人工 Gate 审查。
- 新建、更新、直接执行、人工执行和跳过 Case 具有明确且唯一的路由。
- 必测人工 Case 未完成时不会产生通过结论。
- 测试环境不一致时不会产生正式发布结论。
- 共享账号和全局配置有资源锁，不会并发污染。
- 产品失败不会被自动重试、自愈或放宽断言掩盖。
- 批量失败能够聚类为根因，不会制造大量重复 Bug。
- 发布结论由版本化规则计算，不由模型自由决定。
- 质量豁免不修改原质量结论，并具有范围、责任人和到期时间。
- 人工反馈经过离线评估后才发布为新 Agent 版本。
- Schema 和 Agent 版本具备兼容校验、影子运行、灰度和回滚能力。
- 全流程具备超时、预算、幂等、补偿、审计和恢复能力。

## 30. 架构决策摘要

- 采用多 Agent，而不是一个全能 Agent。
- 采用 Multica 编排，而不是让 Agent 自由控制流程。
- 采用结构化 Artifact，而不是自然语言接力。
- 采用 Test IR 和 Oracle，而不是直接从需求生成代码。
- 采用风险驱动和条件分支，而不是每次全量运行。
- 采用测试资产目录和影响关系图，而不是让 Agent 临时猜测存量 Case。
- 采用确定性执行计划区分生成、更新、直接执行、人工执行和跳过。
- 采用专项审查，而不是一个通用 Agent 审查所有自动化。
- 非功能测试和审查按性能、安全、可访问性、兼容性、韧性和数据一致性拆分。
- 采用环境预检、数据隔离和资源锁，减少无效失败。
- 采用失败聚类和证据化归因，而不是仅输出通过/失败。
- 采用确定性质量策略，而不是让模型决定是否发布。
- 采用独立质量豁免记录，而不是把带风险发布伪装成通过。
- 采用离线评估闭环，而不是在线自动学习和静默自愈。
