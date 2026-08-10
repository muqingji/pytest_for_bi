# Human Test Design Correction

Workflow: `multica-pilot-001`

Automatic budget: `2/2` (not reset)

Move this Issue to `done` to authorize all correction directives below and create a new A08 revision. Move it to `cancelled` to terminate the workflow. Keeping `in_review` leaves the workflow paused.

## A09-R001 - RESULT_SET_METRIC_PARAM_LOCALE

Severity: `error`

Problem: 结果集筛选的中英文指标名参数未按 locale 配对。

Required correction: 按 locale 配对 zh_CN/en 指标名参数。

## A09-R002 - UNRESOLVED_EXPECTATION_REFERENCE

Severity: `error`

Problem: 期望引用不可解析。

Required correction: 将期望引用指向冻结证据中的精确位置。

## A09-R003 - KEYLESS_LOCALIZED_SET_MATCH

Severity: `error`

Problem: 无键本地化集合匹配不可判定。

Required correction: 为本地化集合匹配补充固定 key。

## A09-R004 - COMPOSITE_ORACLE_SOURCE_SCOPE

Severity: `warning`

Problem: 复合 Oracle 来源范围过大。

Required correction: 收窄复合 Oracle 的来源范围。
