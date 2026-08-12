---
name: cleanup-plan
description: Plan retained test assets by default and deletion only under an explicit approved override. Use only for D01/N28 planning.
---

# cleanup-plan

Default every newly created test resource to `retention_mode=retain`. Do not generate delete operations. Register its resource ID, requirement name, resource type, Chinese semantic display name, actual field type evidence, owner and creation time, then verify the retained resource remains readable after execution.

Only generate cleanup when the approved Case explicitly sets `retention_mode=delete`. Use extracted resource identity and current-run namespace; never broaden deletion scope.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
