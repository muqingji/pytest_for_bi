---
name: capability-catalog-resolver
description: Resolve data intents against the frozen versioned capability catalog. Use only for D01 planning.
---

# capability-catalog-resolver

Match registered recipes deterministically. Reject ambiguous or missing capabilities with `data_capability_not_registered`. Never invent endpoints or use unpublished recipes.

## Backlog and candidate routing

- A Case that matches no recipe, or requests an unregistered variant, routes to `capability_adapter_backlog` and stays unresolved. It is never converted into a fake executable plan.
- Delegate the unresolved Case to the `bi-recipe-adapter` skill so a verified 112 contract can be turned into an evidence-gated recipe candidate.
- A candidate may only become a published recipe after every `verification_requirements` item has 112 evidence and N27 accepts the resulting plan.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
