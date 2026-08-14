# Verified language and H5 references

## Language mapping

| Personal language | `lang` Cookie | `Accept-Language` |
| --- | --- | --- |
| Chinese | `zh-CN` | `zh-CN,zh;q=0.9,en;q=0.8` |
| English | `en` | `en,zh-CN;q=0.9,zh-TW;q=0.8` |

Repository sources:

- `test_data/pass_api.112.json`: `pass_api.set_app_language` request and assertions.
- `tests/translation_workbench/test_translation_language.py`: current-cookie request semantics, trace headers, shared-session update, five-second propagation wait, and serial execution.
- `tests/test_text_language.py`: offline contract tests for the switch request.

## H5 routes

Production frontend sources, in lookup order:

- `bi-sdk`: `/Users/liushanshan/code/web/bi-sdk`, remote `git@git.firstshare.cn:fe-bi/bi-sdk.git`. Owns App H5 pages, mobile chart detail, joined-table detail and route declarations.
- `fbi`: `.cache/frontend-sources/fbi`, remote `git@git.firstshare.cn:fe/fbi.git`. Owns BI Web/resource navigation and runtime route-parameter generation.
- `bi-xkcharts`: `.cache/frontend-sources/bi-xkcharts`, remote `git@git.firstshare.cn:fe/bi-xkcharts.git`. Owns chart interaction, drill and detail behavior.

The persistent machine-readable registry is `qa-agents/knowledge/bi-knowledge-sources.json`. If a cached checkout is missing, clone its registered remote read-only before route discovery. Do not edit, commit, reset, clean or push these product repositories.

`/Users/liushanshan/code/QA/cypress-bi` is a frontend automation repository. Use it only for Cypress harness patterns; do not cite it as the product route authority.

- BI list: `/hcrm/avah5#/bi-sdk/pages/list/list`
- BI dashboard: `/hcrm/avah5?bi-sdk/pages/bi-dashboard/dashboard`
- Ava root: `/hcrm/avah5`

Runtime parameters such as `fsAppId`, `_menuType`, `beforeHash`, `hash`, `_uid`, `_paramCode`, and `hashCode` must be resolved from the current frontend implementation and live session responses. Treat captured values as protocol examples only.

## Backend-only equivalence

For the detail-message requirement, the frozen decision artifact is `generated/pc007-web-h5-detail-equivalence.json`.

- Web and H5 chart detail both call `/EM1HBISTAT/fs-bi-stat/stat/detail/data/query` with the same business parameter semantics.
- H5 joined-table detail may call `/EM1HBISTAT/fs-bi-stat/async/detail/data/query`; this is an asynchronous transport wrapper. `AsyncQueryStatDetailInfoArg` maps to `QueryStatDetailInfoArg`, and `AsyncQueryDetailExecuteServiceImpl` calls the same `StatDetailQueryService.queryStatDetail` used by the synchronous path.
- Do not duplicate backend-message assertions through mobile UI while these anchors remain true. Re-enable H5 UI validation when the endpoint, DTO mapping, final service, business parameters, or client-side error handling diverges.
