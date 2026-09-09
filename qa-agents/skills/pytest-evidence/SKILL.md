---
name: pytest-evidence
description: Plan pytest evidence for Case traceability and execution reporting. Use only when authorized by the B01 Router.
---

# pytest-evidence

Bind Case, Intent, run, environment fingerprint, request/response evidence, trace and namespace references. Require redaction. Execution evidence is emitted by N08, not by this Skill.

Treat Router authorization, frozen Case/Oracle/catalog inputs, and repository permissions as immutable. Return structured planning or candidate content only. Fail closed on missing evidence or capability.

112/纷享销客请求的 Trace 由 `fxiaoke-platform-trace-id` 约束：记录平台 `FSW-...` query `traceId`，不要在 Case 里手写或回填 `QA-uuid`。
