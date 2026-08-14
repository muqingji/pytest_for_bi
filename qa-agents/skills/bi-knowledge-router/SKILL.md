---
name: bi-knowledge-router
description: Deterministically route BI requirement analysis, historical lookup, test-case design, and test-data construction to verified source repositories and product documents. Use before drawing BI conclusions from code or documentation.
---

# BI Knowledge Router

Load `../../knowledge/bi-repository-knowledge-catalog.json` and call only the repository Skills selected by semantic terms. Do not route unmatched queries to every repository and do not guess ownership.

State the purpose as `requirement_analysis`, `historical_knowledge`, `test_case`, or `test_data`. Retain matched terms, source IDs and freshness. Resolve conflicts in this order: runtime evidence, current production source, frozen OpenAPI, official product documentation, historical internal documentation, historical bug knowledge. Bind conclusions to source ID, commit or snapshot hash, path and symbol/section; separate facts, inferences and unknowns.

A stale profile may locate code but cannot prove current behavior. An unavailable document is a gap, never positive evidence. `cypress-bi` is test automation and never product-route authority.
