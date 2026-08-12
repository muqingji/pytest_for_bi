---
name: pytest-api-test
description: Generate backend API pytest candidates from approved Cases using the registered case runner. Use only when the deterministic Router authorizes B01 for API or functional service tests.
---

# pytest-api-test

Preserve request inputs, Case identity, and response captures. Delegate execution and assertions to the approved case_runner. Emit Artifact-only Python; never call a service, shell, Git, MR, Bug, or Issue API.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
