---
name: tapd-bug-review-gate
description: Render the human Bug registration approval table and route rejections into evidence-based retests.
version: 1.0.0
---

# TAPD Bug 准出审批门禁

## 触发时机

测试完成后，只有被归类为产品缺陷候选、且已通过 N20 去重结论的条目才能进入本审批卡。
未通过质量门禁、证据不足、环境失败、数据构造失败不得直接请求建 Bug。

## 审批卡字段

审批卡必须用表格展示：

| 字段 | 说明 |
| --- | --- |
| Case | 稳定 Case ID |
| 业务场景 | 用户可理解的真实业务动作 |
| 期望行为 | 冻结需求或 Oracle 中的预期 |
| 实际问题 | 执行证据中的实际结果 |
| Bug 解释 | 为什么判定为产品缺陷 |
| 测试数据（真实的现实名称） | 业务对象名称与 ID，不输出敏感原始值 |
| ID | Bug 候选稳定 ID |

## 状态机

1. `waiting_human`：生成审批卡，等待 QA 负责人决定。
2. `approved`：记录审批人和 Bug ID，进入 TAPD Bug Adapter。Adapter 未接入前保持
   `pending_external_bug_adapter`，不得伪造已建 Bug。
3. `rejected`：审批人必须在评论区指定 Bug/Case ID 和原因。系统生成下一轮重测计划，
   必须复核测试数据 recipe、数据可见性、Case 请求、冻结 Oracle，并重跑受影响 Case。
4. 下一轮仍使用同一审批卡契约，直到全部候选通过人工确认。

## 禁止事项

- 禁止 Agent 自批。
- 禁止审批通过前调用 TAPD 写接口。
- 禁止把驳回评论直接解释成“不是 Bug”；必须先完成数据和 Case 复核、重跑并形成新证据。
- 禁止创建缺少测试数据名称、ID 或业务 ID 的 Bug 候选。
