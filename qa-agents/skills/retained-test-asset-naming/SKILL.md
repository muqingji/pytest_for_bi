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

6. Case-constructed visible names (A22/N08) must be the capability-catalog
   `display_name` for that `resource_key`, so the 112 name and the card name
   both match the case semantics. Examples: `自定义维度查看明细验证统计图`,
   `结果集筛选聚合指标`, `客户等级枚举分组自定义维度`.
   Do not use short tags (`自定义维度`, `结果集筛选`), `qa-*` prefixes,
   English case titles, `resource_key`, or `销售订单统计_副本N` as the visible
   name. After `copy_stat_view`, rename the chart to this `viewName`.
   Uniqueness belongs in the hidden idempotency key; if 112 still collides,
   append one short `HHMMSS` suffix.
   The card renderer shows this catalog name via `constructed-asset-card-display`.
   Implementation: `qa-agents/src/qa_agents/asset_scene_naming.py`.
