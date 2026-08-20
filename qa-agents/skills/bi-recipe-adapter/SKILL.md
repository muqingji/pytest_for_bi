---
name: bi-recipe-adapter
description: Turn unresolved data capabilities and verified BI create contracts into evidence-gated recipe candidates. Use when A22/D01 planning routes a Case to capability_adapter_backlog, or when a new BI create contract is verified in 112.
---

# bi-recipe-adapter

Routine: verified contract -> recipe candidate -> human validation -> published recipe.

1. Load `knowledge/verified-setup-contracts.json` and `knowledge/bi-*-create-contract.json` via `qa_agents.recipe_adapter.load_verified_contracts`.
2. Build the candidate set with `build_candidate_catalog`. Every candidate must declare `verification_requirements`; a candidate without evidence gaps would fake completion and is invalid.
3. Match backlog Cases to candidates with `select_candidates_for_cases` using the same deterministic terms as A22 intent extraction.
4. Never invent endpoints, request bodies, hashes or enum codes. Copy bodies only from verified contracts; leave runtime evidence (enum bindings, folder hashes, configuration hashes, cleanup pairs) as declared requirements.
5. After 112 verification closes every requirement, convert the candidate into a catalog recipe (see `skills/capability-catalog-resolver`) and re-run N27 validation.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
