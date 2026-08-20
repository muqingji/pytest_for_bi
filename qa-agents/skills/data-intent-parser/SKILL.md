---
name: data-intent-parser
description: Extract semantic test-data requirements from approved Cases. Use only when the deterministic Router authorizes D01/A22.
---

# data-intent-parser

Describe resource types, desired states, constraints, and relations without choosing or calling APIs. Preserve uncertainty and emit unsupported requirements instead of guessing.

## Deterministic resource-type inference

When a Case does not declare `test_data.data_intent` or `test_data.dataset`, use the term groups below (implemented in `qa_agents.data_planning.infer_resource_intents`). Emit a data_intent only when exactly one group matches; multiple matches stay ambiguous and route to the capability catalog:

- `聚合指标`/`聚合度量`/agg metric -> `metric.aggregate.create` (aggregate_metric)
- `普通指标`/`普通度量`/`一般指标`/ordinary metric -> `metric.ordinary.create` (ordinary_metric)
- `计算指标`/`计算度量`/`公式指标`/calculated metric -> `metric.calculated.create` (calculated_metric)
- `同环比`/`同比`/`环比`/comparison metric -> `metric.comparison.create` (comparison_metric)
- `统计图`/`图表`/`图形`/chart -> `chart.create` (stat_chart)
- `报表`/`报告`/dashboard -> `report.create` (report)
- `交叉表`/`透视表`/pivot -> `pivot.create` (pivot_table)
- `拼表`/`关联表`/joined table -> `joined_table.create` (joined_table)
- `自定义维度`/`枚举维度`/custom dimension -> `custom_dimension.create` (custom_dimension)

Do not invent intents for terms outside this table. Preserve `unresolved_requirements` instead.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
