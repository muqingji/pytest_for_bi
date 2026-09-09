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

### 2. 渲染必须走统一管道

- 审批项渲染统一走 `workflow_center._approval_lines`，禁止在渲染函数里裸拼
  `issue_code`、`status`、`result_summary` 等内部字段。
- 标题优先级：`human_title` → `_HUMAN_ISSUE_TITLES` 映射 → 类别中文 → 原文兜底。
- 问题描述优先级：`plain_summary` → `_issue_plain_problem` 映射 → 首句截断兜底。
- 产物说明必须包含：artifact 名、中文节点名、状态、一句人话结论。
- 已构造测试数据必须按 `constructed-asset-card-display` 分类列出中文名称和 ID，禁止把 JSON 路径或规划 key 当主信息。
- N11 产出必须按 `n11-quality-result-display` 列出通过/不通过/未执行的短标题、完整中文测试场景、不通过的中文原因，以及实际请求 TraceId；Trace 必须是 `fxiaoke-platform-trace-id` 的 `FSW-...`，禁止 `QA-uuid`。
- N12 产出必须按 `n12-standard-test-report` 直接打印标准中文测试报告；每个 case 都要列出实际测试数据及名称/ID，附件不能替代报告正文。
- 人工操作必须包含：来源说明、逐条可读清单、明确的二选一操作（done 授权 / cancelled 终止）。

### 3. 修改必须四件套

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
- [ ] 全量测试通过（`cd qa-agents && .venv/bin/python -m pytest -q`）
