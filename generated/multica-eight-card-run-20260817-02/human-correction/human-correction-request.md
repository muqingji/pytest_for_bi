# Human Test Design Correction

Workflow: `detail-drill-i18n-8card-20260817-02`

Automatic budget: `2/2` (not reset)

Move this Issue to `done` to authorize all correction directives below and create a new A08 revision. Move it to `cancelled` to terminate the workflow. Keeping `in_review` leaves the workflow paused.

## A09-ISSUE-007 - ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE

Severity: `blocking`

Problem: EXP-E2E-001-01 的 expected_value 指向 test_data.matrix.code_messages_and_parameters，但 matrix 是数组且各行仅定义 code、messages 和可选 parameters，不存在 code_messages_and_parameters 路径；equals 无法取得明确期望值执行。correction_resolutions 对 A09-ISSUE-004 标记 fixed，但该 Oracle 仍未完成可执行修正。

Required correction: 将 expected_value 改为可直接解析的结构化四行期望矩阵，或引用真实存在的 test_data.matrix，并明确按 reason 和 locale 比较 code、messages、parameters；source_ref 应引用 G01 或对应冻结 I18N 规则。

## A09-ISSUE-008 - LOCALE_NAME_PRECEDENCE_FIXTURE_CONFLICT

Severity: `blocking`

Problem: TC-BE-002 同时以 zh_CN 和 en 执行，但 RS-01 固定提供非空 fieldName=销售额。按冻结解析顺序，en 请求也会优先取得销售额，无法同时满足 EXP-BE-002-03 期望的 Revenue；EXP-BE-002-04 也只给出中文分支值，未建立当前语言英文名称解析的确定期望。

Required correction: 按 locale 分别定义 Filter.fieldName、字段元数据和动态多语名称输入及期望参数，确保每个分支严格遵循冻结优先级；可将英文动态名称场景置于前两级均为空的独立数据行。
