## 目标

确认需求口径和测试范围是否可以进入测试设计；有未确认项时，明确回流节点和责任人。

## 背景

需求、技术方案和实际变更对齐后，仍有 0 项需要处置。Agent 不能代替人工确认业务口径。

## 范围

包含：
- 提示优先级、指标名称展示、what/whatList 范围、拼表文案、多语口径。
- 需求与实现不一致或缺少证据的回流决定。

不包含：
- 不审批生产发布，不修改业务仓库，不代替研发补实现证据。

## 输入材料

- A02 需求分析
- A03 技术可测性分析
- A06 需求与实现对齐结果
- 本 Issue 的审核请求和决策模板附件

## 你需要审核什么

1. 多个限制同时命中时，是否按“自定义维度 -> 结果集筛选 -> 动态关联 -> 多关联 -> 原关系异常”只展示第一个提示。
2. 数据范围有多个结果集统计指标时，提示一个还是全部指标名，顺序如何。
3. 特殊 what/whatList 的准确对象和字段范围。
4. 拼表命中结果集筛选时，是否使用不含“统计图”的通用文案。
5. 自定义维度提示是否同时覆盖下钻字段，并冻结中英文文案。
6. Web/移动端是否只要沿用同一后端错误码和文案，无需额外规定提示组件样式。

研发需要补证，不由审核人代替确认：
- 动态关联判定是否过宽或漏判。
- 统计图与拼表是否复用同一后端判定和异常透传。
- 错误码平台中英文模板及指标名参数渲染是否已完成联调。

## 你需要怎么做

- 同意：评论“批准，按卡片中 6 项口径执行；研发补齐 3 项证据”。
- 有不同意项：按编号写明口径，例如“2：只提示第一个指标名”。
- 不继续：评论“拒绝”并说明原因。

## 验收

- 6 项业务口径都有明确结论。
- 3 项研发补证有责任人，不被当作人工已确认。
- 未批准前 N24/A08 不启动；批准后只进入测试设计。

## 待处置明细与追溯信息

- Workflow Run: `detail-drill-i18n-8card-20260817-02`
- Source Snapshot: `pilot-001-source-v1`
- Gate 状态: `completed`
- 当前决策: `not_required`
- 待处理问题: 0 条
- Request Hash: `sha256:22f981b5e4c14e6c0bfb8bccbb40bdf0dc18077af0c2689b0dcee91409377608`
- 审批模式: `qa_owner_single_signoff`
- 策略范围: `pilot_test_design_only`
- 生产发布权限: `False`
- Policy Hash: `sha256:416a8050c9c5a0733cd003dfdcc0c0661752f5d1a5dd0318ae2afd1b1e2ca191`

审批不能只选择同意或拒绝。每个问题都必须记录处置、理由和责任人；上游 Artifact 哈希变化后，本审批自动失效。
请阅读问题详情后，在本 Issue 新增一条评论，完整填写文末的审核表。只有当前绑定人员提交、请求哈希匹配且所有必填项通过校验，系统才会形成正式决策。单独修改卡片状态无效。

## 允许的决策

- `approved`: 所有问题都必须为 `confirmed` 或 `resolved_upstream`。
- `request_changes`: 指定问题回流 A02/A03/A05/A06，并填写理由和责任人。
- `rejected`: 当前范围不进入后续测试设计。

## 审核评论模板

下面已按当前证据预填非绑定的 `request_changes` 建议。请逐项核对并修改，再将整段作为一条新评论提交；只有你的评论才是正式输入。若改为 `approved`，必须把全部处置改为 `confirmed` 或 `resolved_upstream`。

G01 Decision Protocol | 1.0
Request Hash | sha256:22f981b5e4c14e6c0bfb8bccbb40bdf0dc18077af0c2689b0dcee91409377608
Decision |
Overall Reason |
Test Rules |
Issue ID | Disposition | Rationale | Owner
--- | --- | --- | ---

允许的 `Disposition`：`confirmed`、`resolved_upstream`、`return_to_a02`、`return_to_a03`、`return_to_a05`、`return_to_a06`。

Agent 不能审批 G01。审批完成前，N24 和 A08 必须保持阻塞。
