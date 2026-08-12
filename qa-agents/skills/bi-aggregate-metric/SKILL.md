---
name: bi-aggregate-metric
description: Plan BI aggregate-metric test resources through registered catalog recipes. Use only when D01 routes an aggregate_metric intent.
---

# bi-aggregate-metric

Compile `MetricIntent + live schema + live aggregate-object conditions + live filter options + current identity/timezone` into `AddAggRuleArg`. Never execute APIs or use fixed resource IDs as created data.

Required sequence:

1. Resolve the live schema and aggregate object.
2. Call `query_agg_conditions_by_agg_object` and select aggregate, time, and filter fields only from that response.
3. For every enum/business-option filter, call `get_filters_result` (or its approved batch form). Select only returned `optionCode` values.
4. Attach `enum_option_bindings` containing field identity, query operation, response SHA-256, response JSON path, queried option codes, and selected option codes.
5. Compile `AddAggRuleArg`, then require N27 enum-provenance validation before controlled encrypted submission.
6. Extract `fieldId`, call `query_agg_rule_by_field_id`, and compare the returned configuration with the intent.

Labels are presentation data and must never be submitted as invented identities. If any live lookup, field match, response hash, or option-code binding is missing, return `not_ready`; never guess or fall back to a historical sample.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
