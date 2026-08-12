---
name: capability-catalog-resolver
description: Resolve data intents against the frozen versioned capability catalog. Use only for D01 planning.
---

# capability-catalog-resolver

Match registered recipes deterministically. Reject ambiguous or missing capabilities with data_capability_not_registered. Never invent endpoints or use unpublished recipes.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
