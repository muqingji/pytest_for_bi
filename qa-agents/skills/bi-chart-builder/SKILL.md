---
name: bi-chart-builder
description: Plan a retained BI statistical chart from Case semantics and verified 112 schema metadata.
---

# BI chart builder

Status: candidate. Planning is allowed, but remote creation is forbidden until the
create, folder-discovery and saved-config readback operations are all registered in
N27 and a newly created chart is queried successfully in 112.

1. Require a resolved requirement folder, mainstream schema, verified dimension/measure metadata, chart type, Chinese semantic chart name, and current-user permission context.
2. Build `CreateStatViewArg` for `fs_bi_stat.stat_edit.creat_stat_view`. The top-level contract contains `axisData`, `filterLists`, `defaultFilterOptionIDs`, `statLayoutInfo`, `statViewBaseInfo`, `drillRouteFieldLists`, `drillDownPath`, optional `statMobileLayoutInfo`, optional `secondaryFilterLists`, and optional `requestId`.
3. Build axis fields from live schema metadata. Never copy stale `fieldId`, `fieldLocation`, `dbObjName`, topology, timezone, owner ID, permission list, category ID, or default-filter ID from an example request.
4. Derive `chartType`, dimensions, measures, filters, data-range placement, and drill placement from the Case. Use `table` only when the Case requires a table chart or no visualization semantics exist.
5. Set `statViewBaseInfo.categoryID` to the requirement folder, `schemaID` to the resolved subject, `viewName` to a typed Chinese semantic name, and permission fields from the current authorized test identity.
6. Before create, query the requirement folder for a matching hidden idempotency/configuration hash. After create, extract `viewId`, query chart configuration, verify folder, schema, name, axes, filters and drill configuration, then register the retained asset.
7. Do not retry create after an ambiguous transport failure until idempotency and folder lookup prove the asset is absent.
8. For historical compatibility, discover an existing chart first. Record the live
detail operation, normalized configuration SHA-256, observed creation evidence,
requirement baseline and evidence level. Never create a chart and label it historical.

Authentication query parameters, cookies, trace IDs and browser headers are executor-owned and forbidden in plans or artifacts.
