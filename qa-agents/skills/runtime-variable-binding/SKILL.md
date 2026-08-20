---
name: runtime-variable-binding
description: Define logical variable flow across setup, readiness, pytest fixtures, cleanup, and residue checks. Use only for D01 planning.
---

# runtime-variable-binding

Validate producers and consumers. Sensitive values may appear only as secret names resolved by the executor; never place secret values in Artifacts.

## Environment inventory resolution

- Static profile/recipe variables are resolved first by N28 (`_resolve_variables`).
- Values that cannot be static (live field ids, enum option codes, folder ids) are resolved from a 112 environment inventory snapshot via `qa_agents.env_inventory.enrich_plan_with_inventory` before N27 validation.
- A variable the snapshot cannot prove is reported as `runtime_required` and must never be guessed or synthesized.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
