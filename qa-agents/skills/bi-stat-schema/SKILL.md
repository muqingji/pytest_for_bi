---
name: bi-stat-schema
description: Plan BI statistical-schema test resources through registered catalog recipes. Use only when D01 routes a stat_schema intent.
---

# bi-stat-schema

Provide match and lifecycle planning metadata only. Require registered setup, readiness, cleanup, and residue operations; otherwise mark planning_only. Never call BI APIs directly.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
