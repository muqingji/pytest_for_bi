---
name: fxiaoke-112-auth-session
description: Establish and validate the protected 112 CRM session before A15 executes any read or write Case.
---

# Fxiaoke 112 authentication session

1. Resolve exactly one complete credential source: all three `FXIAOKE_112_*` environment variables, or the Git-ignored `config/environment.112.local.json` with mode `0600`.
2. Reject missing credentials, partial environment variables, unsafe local-file permissions, unresolved placeholders, and mixed credential sources before Case execution.
3. Run `scripts/preflight_112_auth.py` before any 112 write phase. Record only source type, authentication status, and session-cookie count. Never expose accounts, passwords, tokens, cookie names, or cookie values.
4. Use the authenticated shared `HttpClient` session for all subsequent API calls in one execution. Do not export browser cookies or copy credentials into artifacts.
5. Authentication failure blocks N07/A15. Do not retry a non-idempotent chart, report, schema, metric, or dimension write merely because the session response was lost. Recover through the resource idempotency key and readiness lookup first.
6. CI and Multica must inject credentials through their Secret provider. Temporary local config files must be installed with mode `0600` and removed after execution.

This Skill defines and validates the contract only. The controlled executor owns Secret access, network authentication, and the shared session. Fail closed whenever session readiness cannot be proven.
