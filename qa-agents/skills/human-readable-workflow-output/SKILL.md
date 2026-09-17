---
name: human-readable-workflow-output
description: "规范 qa-agents 多卡流程所有面向 multica 详情页的输出（阶段卡片、审批项、人工操作、异常处理、产出说明、人工修正 Issue 详情）必须可读、可决策。新增或修改 agent 输出、渲染逻辑时必须遵循本规范的四件套：agent 指令、契约校验、渲染管道、测试。"
---

# 面向用户的可读输出规范

适用范围：`qa-agents/` 下所有最终会展示在 multica 详情页的内容，包括阶段卡片
（`workflow_center.py` 渲染）、人工修正 Issue 详情（`human_correction.py` 渲染）、
以及各 agent 产出的 `issues`/`findings` 等证据集合。

## 目标

详情页面向产品/业务人员，必须做到：不解释也能看懂、看完就知道要做什么决定。

## 强制规则

### 0. 标题与五段式正文

所有卡片（阶段卡、节点/Agent 任务卡、人工修正卡、G01/G02 审核卡）的标题和正文必须遵循
`card-copy` skill：标题一眼可读，正文统一为 目标/背景/范围/输入材料/验收 五段式；
需人工决策的卡必须有独立的“你要操作什么”明细段落。实现一律走
`qa-agents/src/qa_agents/card_copy.py` 构建器。

### 1. Agent 输出必须自带人话字段

任何会进入详情页的问题类集合（如 A09/A11 的 `issues`）必须包含：

- `plain_summary`：一句话人话描述，禁止出现字段路径（如 `test_data.matrix.xxx`）、
  内部宏名（如 `ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE`）、JSON 结构和英文技术术语。
- `human_title`：问题类不超过 12 字。
- `message`：保留完整技术细节，供修正执行与审计。

G02 详情页审批项走 `decision_items`（`review_copy.build_g02_decision_items`），不是全部 `review_items`：

- 只投用例设计未冻结的产品口径：`human_review` 期望、本轮跳过的产品场景。
- 每条必须有中文 `human_title`、`product_scene`（产品功能场景）、`plain_summary`（设计不确定点）、`confirm_action`（请拍板）。
- 禁止把「服务端校验某某，共 N 条预期 / 请确认可直接执行」当成审批项。产品人员必须能看出：哪个功能还没定、要接受什么或补什么口径。
- 已写死错误码/文案的父用例只出现在覆盖摘要，不进审批项。没有未冻结口径时，只留一条放行确认，审批项不得为空。
- 完整中文用例必须写成 `case-cards.md` 附件；G02 任务卡要明确写出「打开 `case-cards.md` 阅读生成的 case」，禁止让审核人自己翻 JSON。

契约校验（`qa-agents/src/qa_agents/multica.py`）必须强制非空：`A09/A11 issues[*].plain_summary`
缺省或为空即入库失败。新增其他 agent 的面向用户集合时同样要求。

A22 `unresolved_requirements` 同样适用，且必须逐条中文展示，禁止出现英文原因代码或英文
`required_resolution`。卡片必须两段，禁止把 7 项混在一起让人审：

- `## 你需要处理`：仅 `review=owner`。系统造不出来的材料，例如改前老图、无权限账号。
- `## 系统要去造的数据（不用你审）`：仅 `review=system`。默认新建隔离数据，不用回评论。
- 每条字段锁定为：要测什么 / 要造什么 / 卡在哪 / 为什么出现在这张卡；人审项再加
  请提供(可空) / 请拍板 / 处置评论。不要再用「产品场景」当字段名。
- 要测什么优先用用例 `title`，再退回输入里的中文场景，再退回 token 表，最后才用兜底句。
- Agent 最少只给 `reason_code` + `affected_cases`（可选 `data`）。人话和 owner/system
  分类由 `humanize_unresolved_requirement` 补。未知 `reason_code` 当 owner。
- `provide_from_you` 仅在必须补材料时出现。skip 只表示这些用例这轮不测，不是「没有现成数据就不造」。
  禁止 recipe、SQL、接口参数、以及「现成名称或这轮不造」。
- 渲染层必须走同一套 `render_a22_approval_sections`：任务卡、阶段卡、工作流驾驶舱格式一致。
- 处置评论格式 `UR-xx: confirmed/skip/return/need_evidence` 只出现在人审项。
  `confirmed`：补了材料继续，或系统去新建。`skip`：这些用例这轮不测。`return`：计划写错，退回 A22。

### 2. 人工 Gate 必须先消费 done，再刷新卡片

节点卡被改写回 `in_review` 会同时改 Multica 和进程内共享的 issue 字典，
所以"确认"必须读到仍为 `done` 的卡片。实现走
`scripts/sync_eight_card_progress.py` 的 `settle_a22_human_review`：先
`ensure_a22_human_confirmation`，再 `_refresh_a22_waiting_card`，顺序不能反。
反了就会出现"人已点完成，卡片还显示审核中"：确认永远看不到 `done`、
计划一直 `needs_human`、C5 不再派发 A14/A15。

A22 处置评论按人话解析（`_parse_disposition_lines`），必须容忍审核人的自然写法：

- 列表编号、Markdown 反引号、全角冒号、尾缀（`UR-06 跳过就行`）都要认；
- 审核人直接给出对象 ID（`BI_...`，含 `BI\_...` 转义）视同 `confirmed`——
  卡片要求的就是"写下名称或 ID"；
- 疑问/建议句（`UR-05 还需要确认`）不得当成放行；
- Agent 评论不是审核：A22 贴回的计划 JSON 里出现别名词不得被当成处置；
- 评审 id 原样保留：计划写 `UR-DISC-01` 就展示、校验 `UR-DISC-01`，禁止重编号成
  `UR-NN`，否则计划改版后同一个 id 指向另一个需求，旧处置会被错用；
- 识别不全时卡片必须列出"还没识别到的处置"明细，禁止静默弹回。

回归测试：`tests/test_sync_eight_card_progress.py` 的
`test_settle_a22_human_review_consumes_done_before_reopening_card`、
`test_parse_disposition_lines_accepts_reviewer_formats`、
`test_parse_disposition_lines_treats_a_handed_over_object_id_as_confirmed`、
`test_unresolved_requirement_id_keeps_agent_declared_ids`。

### 3. 渲染必须走统一管道

- 审批项渲染统一走 `workflow_center._approval_lines`；A22 测试数据缺口必须改走
  `render_a22_approval_sections`。禁止在渲染函数里裸拼
  `issue_code`、`status`、`result_summary` 等内部字段。
- 标题优先级：`human_title` → `_HUMAN_ISSUE_TITLES` 映射 → 类别中文 → 原文兜底。
- 问题描述优先级：`plain_summary` → `_issue_plain_problem` 映射 → 首句截断兜底。
- 产物说明必须包含：artifact 名、中文节点名、状态、一句人话结论。
- 已构造测试数据必须按 `constructed-asset-card-display` 分类列出中文名称和 ID，禁止把 JSON 路径或规划 key 当主信息。
- N11 产出必须按 `n11-quality-result-display` 列出通过/不通过/未执行的短标题、完整中文测试场景、不通过的中文原因，以及实际请求 TraceId；Trace 必须是 `fxiaoke-platform-trace-id` 的 `FSW-...`，禁止 `QA-uuid`。
- N12 产出必须按 `n12-standard-test-report` 直接打印标准中文测试报告；每个 case 都要列出实际测试数据及名称/ID，附件不能替代报告正文。
- 人工操作必须包含：来源说明、逐条可读清单、明确的二选一操作（done 授权 / cancelled 终止）。
- 阶段卡的 `## 人工操作` 只列属于本阶段人工 Gate 的事项。节点任务卡自己承载的待审批项
  不得在阶段卡重复列出，否则一个没有人工 Gate 的阶段会被渲染成需要人来签。归属声明在
  `qa-agents/src/qa_agents/workflow_center.py` 的 `NODE_OWNED_STAGE_APPROVALS`：
  C5 阶段的 A22 测试数据计划确认归 A22 节点卡（C5 自身没有人工 Gate——G03 已按设计
  退化为 N05 通过后自动关闭）。阶段卡只保留一行指向节点卡，禁止搬运明细。
  新增阶段卡人工项前先判断它是不是节点卡的事，并补回归测试。

### 4. 修改必须四件套

新增或修改任何面向用户的 agent 输出时，必须同步改齐并一起验证：

1. Agent 指令（`qa-agents/multica/agent-instructions/*.md`）：写明 `plain_summary`/
   `human_title` 要求与反例。
2. 契约校验（`qa-agents/src/qa_agents/multica.py`）：字段存在 + 非空语义校验。
3. 渲染管道（`qa-agents/src/qa_agents/workflow_center.py`、`human_correction.py`）：
   优先读取人话字段，未命中时走统一兜底。
4. 测试：契约拒绝缺 `plain_summary` 的输出；渲染优先 `human_title`/`plain_summary`；
   人工修正详情为中文可读格式。

## 验收清单

- [ ] 详情页无裸 `issue_code`/状态码/JSON 路径作为主要信息
- [ ] G02 审批项只包含未冻结的产品口径，能看出要拍什么板；不得把全部父用例投成审批项
- [ ] 每条待办都有：通俗标题、一句话问题、明确操作
- [ ] 产出部分每个 artifact 都带中文节点名、状态和说明
- [ ] C5/C6/N08 详情能按统计图/报表/交叉表/驾驶舱/指标/自定义维度看到构造成功的数据
- [ ] N11 详情能按通过/不通过/未执行看到完整中文测试场景、中文失败原因和平台 `FSW-...` TraceId
- [ ] N12 详情的产出中能直接看到结论、统计、准出依据、逐用例明细、风险与后续动作
- [ ] 新输出缺 `plain_summary` 时契约层直接拒绝
- [ ] A22 未决数据需求的卡片正文全中文：无裸 `reason_code`、无英文 `required_resolution`
- [ ] A22 卡片两段：人审项有请拍板，系统项无处置评论；要测什么能看出具体用例场景；默认新建
- [ ] 阶段卡的 `## 人工操作` 不重复节点卡的待审批项：C5 只指向 A22 节点卡，不复述 UR-xx 明细
- [ ] 人工 Gate 先消费 `done` 再刷新卡片；A22 处置评论能识别 ID/尾缀写法，缺项在卡片上点名
- [ ] 全量测试通过（`cd qa-agents && .venv/bin/python -m pytest -q`）
