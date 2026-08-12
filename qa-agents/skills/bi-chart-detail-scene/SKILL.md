---
name: bi-chart-detail-scene
description: Build and validate the complete retained BI scene for Cases that execute 查看明细 from a chart, pivot table, or joined report.
---

# BI chart detail scene

1. Mark a Case `required_scene=chart_detail` when its steps or expected result mention 查看明细, 统计图, 拼表, 交叉表, or the equivalent detail-entry behavior.
2. Resolve a mainstream subject and real source-field metadata first. Do not use 区域测试 unless the Case explicitly requires it.
3. Build one dependency DAG containing all roles: `source_field`, `metric_or_dimension`, `requirement_folder`, `chart_or_pivot`, `view_readiness`, and `detail_entry_execution`.
4. Create or idempotently resolve the folder before the chart. Its visible name must exactly equal the approved requirement name.
5. Create the chart or pivot with the tested metric/custom dimension in the exact axis, data-range, or drill position required by the Case. Persist the returned `viewId`, `categoryID`, configuration hash, and dependent asset IDs.
6. Prove readiness through the saved chart configuration and folder listing. Calling a data-query endpoint without a saved `viewId` is not chart readiness.
7. Execute 查看明细 through the saved chart/pivot entry and capture the request, response contract, error code, restriction reason, and affected field name as evidence.
8. Retain all created assets and register them. Do not schedule cleanup unless the Case explicitly overrides retention with approved `delete` mode.

Fail closed in N27 when any DAG role is absent. A metric or custom dimension alone never satisfies a chart-detail Case.
