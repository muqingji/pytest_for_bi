# REQ-DETAIL-DRILL-I18N-RERUN-20260817-02 统计图查看明细限制原因提示优化

## 目标

对 `REQ-DETAIL-DRILL-I18N-RERUN-20260817-02` 完成从范围确认到质量报告的全流程 QA 交付。

## 背景

“统计图查看明细限制原因提示优化”进入 QA 流程；下方 8 张阶段卡（C1-C8）逐步推进，本卡汇总总状态、进度和需要你处理的事项。

## 范围

包含：
- 范围确认、测试设计与审核、Case 编译与执行计划、自动化与测试数据准备、测试执行、质量决策与报告。

不包含：
- 修改业务代码、生产发布。

## 输入材料

- 需求快照：`pilot-001-source-v1`
- 技术方案与后端 ChangeSet（见 C1）
- 只读代码/OpenAPI 快照

## 验收

- 8 张阶段卡全部完成，质量报告发布并有有效审计结论。
- 需要你处理的事项能在本卡与对应阶段卡中明确看到操作入口。

## 工作流概览

- 总状态：**阻塞**
- 完成进度：`17/36`（47%）
- 当前运行：`detail-drill-i18n-8card-20260817-02`
- 流程版本：`server-requirement/1.1-eight-stage-cards`
- 来源快照：`pilot-001-source-v1`

## Autopilot

- Autopilot ID：`693f864d-87cc-40f3-85c1-5be92a4e0a0f`
- 状态：`active`
- 模式：`run_only`
- 最近执行：尚未触发

## 需要你处理

### 112 测试数据规划处理（None）

- 待处理：`1` 项
- 当前 Gate：`A22`
- 摘要：needs_human

#### 审批项（1）

1. **审批确认**（`a22-test-data-plan-approval`）
   - 问题：needs_human

## 节点进度

| 阶段 | 节点 | 状态 | 完成情况 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 需求、方案与 ChangeSet 冻结 | 已完成 | 1/1 | Artifact n01-source-extraction-manifest accepted |
| 2 | 工作流模板与深度选择 | 已完成 | 1/1 | Artifact n00-workflow-route accepted |
| 3 | [QAA-314](mention://issue/7a4a3e8d-5ac0-4c19-9b87-f7eefbd6d8d3) 需求分析 | 已完成 | 1/1 | completed_with_gaps |
| 3 | [QAA-315](mention://issue/2feedb7e-9e1c-42d3-a063-9263f7b3ddaa) 技术方案与可测性分析 | 已完成 | 1/1 | 发现待确认项，已并入 G01 汇总审批 |
| 3 | [QAA-316](mention://issue/9a0898f3-b7b4-4300-a4cd-8901f1506242) 服务端变更分析 | 已完成 | 1/1 | completed_with_gaps |
| 4 | [QAA-317](mention://issue/b5cdbef4-0bc5-4794-b2fe-f625473bdb38) 需求与变更对齐 | 已完成 | 1/1 | 发现待确认项，已并入 G01 汇总审批 |
| 5 | [QAA-318](mention://issue/ea27f34c-7a8a-41f3-8a66-33f6af0d983a) 范围与口径人工审核 | 已完成 | 1/1 | not_required |
| 6 | [QAA-332](mention://issue/2be62435-5491-4e16-9b89-21ba308ad4d3) 风险与测试策略 | 已完成 | 1/1 | Artifact n24-test-strategy accepted |
| 7 | [QAA-326](mention://issue/7f41c597-4c8c-4ea8-9c71-5cf4a6390d14) 测试设计 | 已完成 | 1/1 | completed_with_gaps |
| 8 | [QAA-327](mention://issue/674fd845-2213-48a2-9a2a-1e703a4d2be1) Oracle 与覆盖审查 | 已完成 | 1/1 | completed_with_gaps |
| 9 | [QAA-331](mention://issue/6a8c7ff8-a649-4eb4-9498-b82ebacd0b75) Test Case IR 校验 | 已完成 | 1/1 | Artifact n04-test-case-ir-validation accepted |
| 10 | [QAA-329](mention://issue/512ea879-4e33-4fc5-ae64-677d836bf5e9) Test Case IR 人工审核 | 已完成 | 1/1 | approved |
| 11 | [QAA-333](mention://issue/3329aa18-2dc1-4b23-9899-747951d4a749) 父子 Case 编译 | 已完成 | 1/1 | Artifact n25-compiled-test-cases accepted |
| 12 | [QAA-330](mention://issue/046cda0d-8ad9-435e-93fc-41b9682e007a) 拆分覆盖审查 | 已完成 | 1/1 | completed |
| 13 | [QAA-335](mention://issue/1ba8d6e5-f1d2-415a-be9d-7bc478c0e4c2) 测试选择 | 已完成 | 1/1 | Artifact n26-test-selection accepted |
| 14 | [QAA-334](mention://issue/d19009da-5ba3-481c-9053-1ddeb586566b) 执行计划编译 | 已完成 | 1/1 | Artifact n15-execution-plan accepted |
| 15 | [QAA-336](mention://issue/bd22cd54-e5ce-4e77-b829-1174f38825c6) 服务端自动化生成 | 运行中 | 0/1 | 上游节点已完成，等待调度 |
| 15 | [QAA-337](mention://issue/fceb05d9-2005-492d-a02c-178fc78a88b5) 契约自动化生成 | 已跳过 | 1/1 | not_applicable |
| 15 | [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8) 112 测试数据规划 | 等待人工 | 1/1 | needs_human |
| 16 | 服务端自动化独立复核 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（[QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 16 | 契约自动化独立复核 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（[QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 16 | [QAA-340](mention://issue/2d2b6678-2b7c-4364-92c3-8a35d64906f6) 测试数据计划安全校验 | 阻塞 | 1/1 | rejected |
| 17 | 自动化确定性代码检查 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（[QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 18 | 自动化代码人工审核 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（[QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 19 | 环境、数据与资源预检 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 20 | 受控自动化执行 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 20 | 人工与探索测试执行 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 21 | 环境失败重试预算 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 21 | 运行质量信号采集 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 22 | 执行证据标准化与失败聚类 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 23 | 跨运行缺陷去重 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 24 | 确定性质量决策 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 25 | 质量豁免审计 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 26 | 质量报告发布 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 27 | 报告反馈入口 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |
| 28 | 上线后验证授权审计 | 未开始 | 0/1 | 卡在 `A22` 112 测试数据规划 的决策（上游 C5 · [QAA-339](mention://issue/bff5ee4c-c45f-4717-b4ac-05334290a9a8)） |

## 审计绑定

- Workflow ID：`REQ-DETAIL-DRILL-I18N-RERUN-20260817-02`
- Parent Issue：`QAA-304`
- Projection：`sha256:84ca9e7b4e088d92489dcfc2fff93f3644e57dcaeb791dc6740d9ac16e3c1654`

节点任务和重跑记录保留在内部执行项目；本卡只展示需求级总体状态、进度和人工事项。