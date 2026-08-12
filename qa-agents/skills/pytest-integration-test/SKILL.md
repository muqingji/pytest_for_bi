---
name: pytest-integration-test
description: Generate multi-step backend integration pytest candidates with bounded state propagation. Use only when the deterministic Router authorizes B01 for integration tests.
---

# pytest-integration-test

Preserve step order and runtime variable bindings. Use bounded polling instructions for asynchronous state. Never add fixed sleeps, arbitrary retries, or direct environment calls.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
