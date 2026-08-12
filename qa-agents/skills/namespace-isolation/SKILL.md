---
name: namespace-isolation
description: Plan run-scoped test-data ownership and isolation. Use only for D01 planning.
---

# namespace-isolation

Use an approved ownership/idempotency namespace, but do not expose `qa-*` as the visible business name. Retained resources use Chinese semantic display names and are registered by requirement. Never target resources outside the current requirement.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
