---
name: requirement-case-render
description: "把紧凑需求卡（TC-*/EXP-* oracle 规格）确定性渲染为统一测试场景/测试步骤/预期结果 case，并保证后续所有需求卡都必须遵循该格式。需求作者与 A08/A09 生成或评审用例时必须遵循本规范。"
---

# 需求卡渲染规范（requirement-case-render）

## 目标

一个需求只允许用一种卡片格式进入用例管道：`### `ID` 标题 · layer / risk / priority` +
预期结果以 `EXP-*` oracle 规格表达。渲染必须走确定性代码
`qa-agents/src/qa_agents/requirement_case_renderer.py`，不允许 Agent 自由改格式。

## 强制规则

### 1. 卡片头部

```text
### `TC-BE-001` 自定义维度三类位置的专用错误与双语提示 · backend / critical / P0
```

- `layer`：backend / frontend / contract / e2e / scenario / non_functional。
- `risk`：low / medium / high / critical。
- `priority`：P0 / P1 / P2 / P3。
- 缺少头部属性、风险/优先级不在枚举内，渲染器直接拒绝。

### 2. 预期结果逐字保留

```text
- `EXP-BE-001-01`：三个变体均拒绝查看明细并返回错误码 s307011534。
   - deterministic · equals @ `detail_api.error.code` → `s307011534`
```

- 每条 `EXP-*` 恰好一条 oracle 行：`类型 · 匹配器 @ `观测点` → `期望值``。
- 期望值（错误码、zh_CN/en 消息）是已批准模板：**逐字保留，禁止改写、翻译、
  去标点、去空格**。en 消息的句点、空格、大小写必须与批准模板完全一致。
- 观测点默认语义：`detail_api.error.code`、`detail_api.error.message.zh_CN`、
  `detail_api.error.message.en` 分别指向查看明细接口错误对象的 code 与双语 message 字段。
- **审核卡只展示人读预期结果**：EXP 描述逐字保留；描述没写明的批准值必须用人话
  补全（zh_CN 消息 `：「值」`、en 消息 `：`值``、错误码 `（错误码 `值`）`、
  多选错误码 `（允许错误码：a、b）`、不得包含 `（不得包含：`值`）`）。
- **机读 oracle 规格（类型/匹配器/观测点/期望值）只进入 JSON**（
  `g02-review-request.json` / `case-ir.json`），禁止出现在审核卡上；审核卡出现
  `deterministic · equals @ ...` 或 JSONPath 视为格式违规。

### 3. 场景与步骤

```text
## 测试场景
自定义维度字段位于维度、数据范围、下钻三类位置时，通过保存资产的查看明细入口触发查看明细，均被拒绝进入明细视图。

## 变体
- dimension：自定义维度字段位于统计图维度位置
- data_range：自定义维度字段位于数据范围位置
- drill_field：自定义维度字段位于下钻字段位置

## 前置条件
- 已构造并保存含自定义维度字段的资产，配置回查中精确出现自定义维度 ID

## 测试步骤
1. 构造并保存 dimension 变体资产，配置回查确认自定义维度 ID 出现在维度位置
2. 依次通过各变体资产的查看明细入口实际触发查看明细，记录 detail_api 响应
3. 比对 detail_api.error 的 code、message.zh_CN、message.en 实际值
```

- 多个变体必须用 `## 变体` 显式声明（`- id：名称`），不允许用“三个变体”这类
  未枚举的表述代替。
- 标题、`测试场景`、`测试步骤`、预期结果描述必须用中文写给人看，让审核人不用翻译就能判断这条用例在验什么。
  错误码、批准英文模板、观测点保持原文，禁止把整条场景/步骤写成英文。
- G02 不逐条审全部用例。只有期望未冻结（`human_review`）或本轮明确跳过的产品场景才会变成审批项；
  这些条目必须能让产品人员看出：哪个功能场景还没定、要拍什么板。
- 测试步骤必须来自领域 skill（bi-custom-dimension / bi-chart-detail-scene /
  bi-result-set-filter 等）或已验证的资产证据，禁止凭空编造接口、payload 或资产。
- 未写 `## 测试场景` / `## 测试步骤` 时，渲染器会从标题 + 第一条 EXP 描述与变体
  确定性合成骨架；但正式交付给 G02 的需求卡必须显式写明场景与步骤。
- 允许的区块只有：`测试场景`、`变体`、`前置条件`、`测试步骤`、`预期结果`；
  其他区块一律拒绝。

### 4. 渲染产出

对同一张需求卡，确定性渲染器一次产出四件：

1. `requirement-case.json`：`requirement-case/1.0` 规范化契约（schema 见
   `qa-agents/contracts/requirement-case.schema.json`）。
2. `case-card.md` / `case-cards.md`：测试场景 / 测试步骤 / 预期结果 审核卡；卡内段落标题
   渲染为加粗正文（`**测试场景**`、`**前置条件**`、`**测试步骤**`、
   `**预期结果**`），字号小于 `##` 标题且保留加粗，禁止再改回 `##`；
   **预期结果** 只含人读语句，机读 oracle 规格不进本文件。
3. `g02-review-items.json`：`g02_review.py` 直接消费的 review_items。
4. `case-ir.json`：`test-case-ir/1.0` 兼容父用例，供 N25 编译与 G02 审核。

A08 生成并经 N04 校验后，G02 准备阶段必须额外写出同一份人读文件
`g02-auto/case-cards.md`，并把它作为 G02 任务卡附件。G02 任务卡「输入材料」
必须第一行引导打开该文件；禁止只给 JSON 路径。审批对象是这份中文用例卡，
不是 `a08-test-design-ir.json` 或自动化代码。

CLI：`PYTHONPATH=src ../.venv/bin/python -m qa_agents render-requirement-case
--input <card.md> --output-dir <dir>`。

## 反例

- 头部缺少 `· backend / critical / P0`，或风险写成 `严重`。
- 期望值被“润色”：`Custom dimension fields are used in the dimension or data range. Details view is not supported.` 改写为去句点或换词版本。
- 一条 EXP 配两条 oracle 行，或 oracle 行没有 `→`。
- 用 `## 变体` 之外的方式表达变体（例如正文里写“三个位置”却不枚举）。
- 测试步骤写死未经验证的接口路径或请求体。
- 审核卡 **预期结果** 出现 `deterministic · equals @ ...` 机读 oracle 行；
  该规格只允许出现在 JSON 附件中。

## 验收

- [ ] 需求卡可被 `parse_requirement_cards` 解析且 `validate_requirement_case` 通过
- [ ] 渲染出的预期结果与批准模板逐字一致
- [ ] 变体全部显式枚举，步骤可追溯到领域 skill 或资产证据
