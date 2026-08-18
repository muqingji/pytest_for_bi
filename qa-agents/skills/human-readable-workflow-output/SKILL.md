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

### 1. Agent 输出必须自带人话字段

任何会进入详情页的问题类集合（如 A09/A11 的 `issues`）必须包含：

- `plain_summary`：一句话人话描述，禁止出现字段路径（如 `test_data.matrix.xxx`）、
  内部宏名（如 `ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE`）、JSON 结构和英文技术术语。
- `human_title`：不超过 12 字的通俗标题。
- `message`：保留完整技术细节，供修正执行与审计。

契约校验（`qa-agents/src/qa_agents/multica.py`）必须强制非空：`A09/A11 issues[*].plain_summary`
缺省或为空即入库失败。新增其他 agent 的面向用户集合时同样要求。

### 2. 渲染必须走统一管道

- 审批项渲染统一走 `workflow_center._approval_lines`，禁止在渲染函数里裸拼
  `issue_code`、`status`、`result_summary` 等内部字段。
- 标题优先级：`human_title` → `_HUMAN_ISSUE_TITLES` 映射 → 类别中文 → 原文兜底。
- 问题描述优先级：`plain_summary` → `_issue_plain_problem` 映射 → 首句截断兜底。
- 产物说明必须包含：artifact 名、中文节点名、状态、一句人话结论。
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
- [ ] 每条待办都有：通俗标题、一句话问题、明确操作
- [ ] 产出部分每个 artifact 都带中文节点名、状态和说明
- [ ] 新输出缺 `plain_summary` 时契约层直接拒绝
- [ ] 全量测试通过（`cd qa-agents && .venv/bin/python -m pytest -q`）
