---
name: readiness-plan
description: Plan read-only readiness checks for constructed test data. Use only for D01/N28 planning.
---

# readiness-plan

Use allowlisted query operations, bounded polling, timeout, and stable expectations. Never write state, use fixed sleeps, or turn business failures into retries.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
