---
name: pytest-fixture-binding
description: Bind approved test-data lifecycle variables to pytest fixtures. Use only when the B01 Router authorizes fixture binding.
---

# pytest-fixture-binding

Reference logical runtime variables supplied by the deterministic Data Executor. Never embed tenant IDs, accounts, tokens, secrets, or fixed runtime resource IDs in candidates.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
