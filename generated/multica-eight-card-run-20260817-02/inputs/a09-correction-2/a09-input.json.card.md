# A09 Oracle 与覆盖审查修正

## 目标

审查 Oracle 期望值与测试覆盖，输出可执行结论或需要修正的问题清单。

## 背景

A08 测试设计入库后，由 A09 Agent 独立审查 Oracle 与覆盖。 本卡为修正轮，绑定上一版输入参数包与校验结论。

## 范围

包含：
- Oracle 期望值审查
- 覆盖缺口识别与修正建议

不包含：
- 修改测试设计本身
- 代签人工决策

## 输入材料

- 输入参数包（附件：`a09-input.json`）
- A08 Test Case IR

## 验收

- 产出 a09-oracle-coverage-review Artifact 并入库
- 阻塞问题有明确修正方案与来源引用

## 你需要处理

本卡阻塞问题已路由人工处置，需要你决定下一步。

待审批：`2` 项

1. **预期结果无法解析**（`A09-ISSUE-007` · blocking）
   - 问题：EXP-E2E-001-01 的 expected_value 指向 test_data.matrix.code_messages_and_parameters，但 matrix 是数组且各行仅定义 code、messages 和可选 parameters，不存在 code_messages_and_parameters 路径；equals 无法取得明确期望值执行。correction_resolutions 对 A09-ISSUE-004 标记 fixed，但该 Oracle 仍未完成可执行修正。
   - 建议修正：将 expected_value 改为可直接解析的结构化四行期望矩阵，或引用真实存在的 test_data.matrix，并明确按 reason 和 locale 比较 code、messages、parameters；source_ref 应引用 G01 或对应冻结 I18N 规则。
   - 涉及用例：`TC-E2E-001`
   - 期望项：`EXP-E2E-001-01`
   - 来源：`REQ-006`、`RULE-ENTRY-CONSISTENCY`、`A09-ISSUE-004`

2. **中英文测试数据冲突**（`A09-ISSUE-008` · blocking）
   - 问题：TC-BE-002 同时以 zh_CN 和 en 执行，但 RS-01 固定提供非空 fieldName=销售额。按冻结解析顺序，en 请求也会优先取得销售额，无法同时满足 EXP-BE-002-03 期望的 Revenue；EXP-BE-002-04 也只给出中文分支值，未建立当前语言英文名称解析的确定期望。
   - 建议修正：按 locale 分别定义 Filter.fieldName、字段元数据和动态多语名称输入及期望参数，确保每个分支严格遵循冻结优先级；可将英文动态名称场景置于前两级均为空的独立数据行。
   - 涉及用例：`TC-BE-002`
   - 期望项：`EXP-BE-002-03`
   - 来源：`REQ-003`、`RULE-SINGLE-METRIC`、`RULE-I18N-RESULT-SET`

操作选项：
- 置 **done**：授权按上述建议定向修正，系统重新入库并重跑 A09/N04 校验。
- 置 **cancelled**：终止当前流程。
- 置 **blocked**：暂不处理，保持等待。
