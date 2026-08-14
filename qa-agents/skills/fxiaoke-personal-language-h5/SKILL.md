---
name: fxiaoke-personal-language-h5
description: Switch a Fxiaoke 112 user's personal language in the authenticated shared session and validate BI flows through the App H5 or mini-program-compatible `/hcrm/avah5` entry. Use for zh-CN/en contract or E2E Cases whose UI text, error message, chart detail behavior, or mobile H5 behavior depends on the current user's language.
---

# Fxiaoke personal language and H5

1. Establish the protected 112 session with `fxiaoke-112-auth-session` and keep the same `HttpClient` or visible browser session throughout the language subject. Never export cookies or credentials.
2. Accept only `zh-CN` and `en`. Load the existing `pass_api.set_app_language` Case from `test_data/pass_api.112.json`; do not invent another language endpoint.
3. Before calling the switch API, preserve the current `lang` Cookie and send its corresponding `Accept-Language`. Add unique trace IDs, the CRM base URL as `Origin`, and `${base_url}/XV/UI/manage` as `Referer`, matching `tests/translation_workbench/test_translation_language.py`.
4. Require HTTP 200 and `Result.FailureCode=0`. Only after success, set the shared session's `lang` Cookie to the target language and set its default `Accept-Language` using the mapping in [references/language-and-h5.md](references/language-and-h5.md).
5. Wait five seconds for account-language propagation. Do not log in again because a new login may replace the language context.
6. Run language subjects serially. The personal language is account-global and parallel zh-CN/en subjects can overwrite each other.
7. Resolve App H5 navigation from the three registered production frontend repositories in `qa-agents/knowledge/bi-knowledge-sources.json`. Read `bi-sdk` first for mini-program pages and mobile detail behavior, `fbi` for Web/resource navigation and runtime parameter generation, and `bi-xkcharts` for chart interaction behavior. Treat `cypress-bi` only as an automation implementation reference, never as the product route authority.
8. Start with `${base_url}/hcrm/avah5#/bi-sdk/pages/list/list`. Derive target resource routes and parameters from current production source plus live list/detail responses. Never reuse captured `_uid`, `_paramCode`, or `hashCode` values as constants and never require the user to supply per-resource routes.
9. Execute the saved chart or joined-table detail entry and record the target language, URL route class, resource ID, response code/message/parameters, visible prompt, and whether the detail view was blocked. Treat the backend's actual single returned reason as the result for combined-reason Cases.
10. Restore the original personal language through the same switch workflow in `finally`. If restore fails, fail the Case and report session contamination.

For backend-only requirements, first perform an entry-equivalence review. Skip duplicate H5 UI execution only when current Web and H5 source prove all of the following: the same backend endpoint or a transport wrapper mapped to the same business DTO, the same business-significant parameter semantics, the same final service and reason-selection logic, and no client-side branch that changes the expected error. Record the source anchors and decision in a machine-readable contract. If any item differs or cannot be proven, execute the H5 UI flow.

Fail closed when the language switch response, shared-session update, propagation wait, current H5 route, or restore cannot be evidenced. This Skill authorizes validation only; it does not create BI assets or inject faults.
