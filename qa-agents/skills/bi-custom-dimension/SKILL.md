---
name: bi-custom-dimension
description: Plan BI custom-dimension resources through registered catalog recipes. Use only when D01 routes a custom_dimension intent.
---

# bi-custom-dimension

Require namespace ownership, actual source field metadata, a typed Chinese semantic name, registered create/query operations, `retention_mode=retain`, and retained readability verification. Do not plan deletion unless the approved Case explicitly overrides retention. This Skill never writes the environment.

For `enum_group`, resolve the source field with `get_fields_by_schema_id`, then read its current `ui.data[].optionCode` values from `fs_bi_udf_report.view_edit.get_ui_type` using the returned `fieldId` and `udfFieldId` (or another formally approved live option operation). Compile `dimensionConfig.groups[].values` exclusively from those returned codes and attach `enum_option_bindings` with the source field ID/API name, operation, response SHA-256, JSONPath, queried codes, and selected codes. N27 must parse the JSON string inside `dimensionConfig` and reject missing, handwritten, stale, or unmatched values. Group names and descriptions may be requirement-authored labels; source enum identities may not.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
