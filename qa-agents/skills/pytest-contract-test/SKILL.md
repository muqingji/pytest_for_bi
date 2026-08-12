---
name: pytest-contract-test
description: Generate pytest contract candidates bound to a frozen OpenAPI reference. Use only when the deterministic Router authorizes B01 for contract Cases.
---

# pytest-contract-test

Require a non-empty frozen contract reference and operation binding. Preserve required fields, enums, request and response constraints. Fail closed when the contract is absent; never infer an API contract.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
