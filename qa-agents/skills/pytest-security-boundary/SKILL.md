---
name: pytest-security-boundary
description: Apply backend pytest generation safety constraints. Always use for B01 generation and deterministic review.
---

# pytest-security-boundary

Output is Artifact-only. Forbid business-repository writes, arbitrary shell or eval, undeclared network targets, secret values, Oracle changes, failure skipping, privilege expansion, MR/Bug/Issue mutations, and direct execution outside N08.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.
