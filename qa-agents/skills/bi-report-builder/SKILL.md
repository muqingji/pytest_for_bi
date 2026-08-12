---
name: bi-report-builder
description: Plan a retained ordinary BI report from Case semantics and verified object/field topology.
---

# BI report builder

Status: candidate until a newly created ordinary report is queried successfully in 112.

1. Use `POST /FHH/EM1HBIUDF/rptUdfViewCreateController/saveRptView` with the current UDF `SaveRptViewArg` contract.
2. Require a requirement folder, `businessObjects`, `displayFields`, optional `filterList`, Chinese semantic `viewName`, `isEdit=2`, permissions, layout and timezone. Ordinary reports use `tableType=0`; pivot reports belong to the separate pivot Skill.
3. Resolve object relations and every field from current metadata. Never copy object IDs, field IDs, user IDs, category IDs or permissions from a captured request.
4. The Agent and Skill produce a plaintext structured DTO only. `content-encoding=fx-encrypt`, `__bodykey`, `__fs_salt`, `x-fs-token`, cookies and encryption are controlled-transport responsibilities. Never persist or reproduce captured encryption material.
5. Extract the returned report/view ID, query report configuration, verify folder, name, object topology, display fields, filters, `tableType=0`, permissions and readiness, then register the retained asset.
6. Do not retry an ambiguous save until a folder/name/configuration-hash lookup proves absence.
