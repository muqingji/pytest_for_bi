---
name: resource-dag-planner
description: Compile registered test-data resources into a deterministic dependency DAG. Use only for D01/N28 planning.
---

# resource-dag-planner

Detect cycles, topologically order setup, and reverse the order for cleanup. Preserve Case isolation. This Skill plans only and performs no writes.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
