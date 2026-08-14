---
name: retained-test-asset-naming
description: Name and organize retained BI test assets. Use when D01/N28 plans charts, metrics, schemas, fields, or custom dimensions that remain in the test environment.
---

# Retained test asset naming

1. Read the approved requirement title and use it verbatim as the chart folder name. Create or resolve that folder before creating any chart, pivot table, or joined report. Never place a created chart at the root or in a generic QA folder.
2. Discover the source field metadata before naming a metric, schema, field, or custom dimension. Record `fieldId`, API name, actual field type, and business label as naming evidence.
3. Use a concise Chinese business name that exposes both semantic meaning and type where useful. Examples: `销售订单退款金额聚合指标`, `客户等级枚举自定义维度`, `销售记录创建时间日期字段`. Do not use `qa-*`, random suffixes, English-only labels, `测试1`, or opaque IDs as the visible name.
4. Uniqueness normally belongs in the hidden idempotency key or asset registry. Reuse the retained asset when requirement name, resource type, source field ID, and configuration hash match. If the CRM copy flow still reports a visible-name collision after exact-folder discovery, append one short `HHMMSS` suffix to the approved business name, record the resolved name, and do not retry that write with another suffix after an ambiguous response.
5. Emit `requirement_name`, `asset_folder_name`, `display_name`, `source_field_id`, `source_field_type`, `semantic_basis`, `retention_mode=retain`, and the resulting resource ID into the retained asset registry.

Fail closed when the requirement name or real field metadata cannot be established. This Skill plans only; the deterministic executor performs approved writes.
