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
- 完成进度：`33/36`（92%）
- 当前运行：`detail-drill-i18n-8card-20260817-02`
- 流程版本：`server-requirement/1.1-eight-stage-cards`
- 来源快照：`pilot-001-source-v1`

## Autopilot

- Autopilot ID：`693f864d-87cc-40f3-85c1-5be92a4e0a0f`
- 状态：`active`
- 模式：`run_only`
- 最近执行：尚未触发

## 需要你处理

### 自动化确定性代码检查处理（None）

- 待处理：`1` 项
- 当前 Gate：`N05`
- 摘要：Artifact n05-automation-code-check accepted

#### 审批项（1）

1. **审批确认**（`n05-automation-code-check-approval`）
   - 问题：Artifact n05-automation-code-check accepted

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
| 15 | [QAA-380](mention://issue/01a02425-939d-7b22-8123-3b33231f4f30) 服务端自动化生成 | 已完成 | 1/1 | completed_with_gaps |
| 15 | [QAA-337](mention://issue/fceb05d9-2005-492d-a02c-178fc78a88b5) 契约自动化生成 | 已跳过 | 1/1 | not_applicable |
| 15 | [QAA-374](mention://issue/01a023b5-267f-7515-955d-048bbbdb811b) 112 测试数据规划 | 已完成 | 1/1 | 人工已确认未决数据需求，节点进入完成态 |
| 16 | [QAA-383](mention://issue/01a03dda-8765-758e-bde5-6abf52a60e73) 服务端自动化独立复核 | 阻塞 | 1/1 | 发现 11 个阻塞问题需人工定向修正（A18BE-001、A18BE-002、A18BE-003、A18BE-004 等 11 项） |
| 16 | 契约自动化独立复核 | 已跳过 | 1/1 | not_applicable |
| 16 | [QAA-340](mention://issue/2d2b6678-2b7c-4364-92c3-8a35d64906f6) 测试数据计划安全校验 | 已完成 | 1/1 | Artifact n27-test-data-plan-validation accepted |
| 17 | [QAA-344](mention://issue/bfc83d05-c77c-4d90-9b9f-b178a9937d2e) 自动化确定性代码检查 | 等待人工 | 1/1 | Artifact n05-automation-code-check accepted |
| 18 | [QAA-369](mention://issue/d98febc0-36e2-4845-b9d7-e840e09a4bc9) 自动化代码人工审核 | 已跳过 | 1/1 | not_applicable |
| 19 | [QAA-348](mention://issue/77a1ad3e-e571-4fae-9d8c-d377d92dedd4) 环境、数据与资源预检 | 已完成 | 1/1 | passed |
| 20 | [QAA-349](mention://issue/a687539c-5719-40bd-abfd-38c37a572a6f) 受控自动化执行 | 已完成 | 1/1 | passed |
| 20 | [QAA-355](mention://issue/b2f1a0b8-c59b-4d28-828a-01b1902b9488) 人工与探索测试执行 | 已完成 | 1/1 | Artifact n17-manual-execution accepted |
| 21 | [QAA-351](mention://issue/0b66bfb2-7e5d-4fd3-a742-3a48a495a1c5) 环境失败重试预算 | 已完成 | 1/1 | not_required |
| 21 | [QAA-356](mention://issue/2e8d9465-207d-420e-b572-3de9a76c0d75) 运行质量信号采集 | 已完成 | 1/1 | Artifact n18-quality-signals accepted |
| 22 | [QAA-350](mention://issue/2cefe723-be64-41ae-8123-b8bb3a804eed) 执行证据标准化与失败聚类 | 已完成 | 1/1 | cluster_count=1, failure_count=1, pending_manual=0, result_count=1 |
| 23 | [QAA-358](mention://issue/fe8a28b6-8ab7-4b0b-a390-b337151cb678) 跨运行缺陷去重 | 已完成 | 1/1 | Artifact n20-defect-dedup accepted |
| 24 | [QAA-352](mention://issue/8deef00c-bf3b-4b07-a322-cee8be51281d) 确定性质量决策 | 等待人工 | 1/1 | inconclusive |
| 25 | [QAA-357](mention://issue/4a380207-085b-4e67-9625-a5de660d5e1d) 质量豁免审计 | 已跳过 | 1/1 | not_requested |
| 26 | [QAA-353](mention://issue/4223f55d-762b-496e-bfed-550f0f0acdb4) 质量报告发布 | 已完成 | 1/1 | inconclusive |
| 27 | [QAA-354](mention://issue/50d6e20a-39b0-41ad-a16b-3e336e4fd76b) 报告反馈入口 | 已完成 | 1/1 | ready_for_feedback |
| 28 | [QAA-359](mention://issue/b1ba2663-f7f6-4793-a02a-09a7614462ab) 上线后验证授权审计 | 已跳过 | 1/1 | not_authorized |

## 审计绑定

- Workflow ID：`REQ-DETAIL-DRILL-I18N-RERUN-20260817-02`
- Parent Issue：`QAA-304`
- Projection：`sha256:db0bbe4f75e8954d838b713bac0a4a7d2938ac17a8ad64f7b8a8c2b639ff1cb4`

节点任务和重跑记录保留在内部执行项目；本卡只展示需求级总体状态、进度和人工事项。