---
name: bi-pivot-table-builder
description: Compile a retained BI pivot table from Case semantics and current 112 object and field metadata.
---

# BI pivot table builder

Status: candidate until a newly created pivot table is queried successfully in 112.

1. Compile a `PivotTableIntent` into a new plaintext `SaveRptViewArg`. A captured successful request proves the endpoint and transport only; it is never a payload template.
2. Require the exact requirement folder, Chinese semantic view name, mainstream subject topology, at least one row dimension, at least one column dimension, at least one aggregate value field, current identity and timezone.
3. Resolve `businessObjects` and every field from current metadata. Decide each field placement from the Case: `rowGroupFields`, `colGroupFields`, `statFields` or `filterList`, and record the reason.
4. Use `tableType=1` and create semantics `isEdit=2`. Row and column dimensions use non-aggregate grouping semantics; statistic fields must use an aggregation supported by the live field capability. Do not treat ordinary `displayFields` as a substitute for pivot axes.
5. Compile pivot layout deliberately, including horizontal total/subtotal and vertical total/subtotal positions. Enable only totals required by the Case; keep display, width, row-height and wrapping settings deterministic.
6. Validate before save: exactly one main object; all object relations are live; every placed field belongs to the selected topology; row/column fields support grouping; statistic fields support their aggregation; row plus column group count respects the tenant limit; attribute dimensions respect the tenant limit; duplicate incompatible placements are rejected; requirement folder and permissions use current values.
7. Execute `POST /FHH/EM1HBIUDF/rptUdfViewCreateController/saveRptView` through controlled transport. `fx-encrypt`, dynamic body key, salt, token, cookies and trace headers are executor-owned and forbidden in Agent artifacts.
8. Extract the returned view ID, query the saved report configuration, and verify `tableType=1`, folder, name, topology, row axes, column axes, statistic fields, filters, layout, permissions and configuration hash. Execute a pivot data query and require a structurally valid header/data result before readiness.
9. Do not retry an ambiguous save until folder/name/configuration-hash discovery proves absence. Retain successful assets; do not delete them.

Never clone captured IDs or produce a pivot table by changing only `tableType` on an ordinary-report sample.
