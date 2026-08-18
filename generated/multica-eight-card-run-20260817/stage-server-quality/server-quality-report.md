# QA Server Quality Report

- Workflow Run: `detail-drill-i18n-8card-20260817-01`
- Decision: **inconclusive**
- Release disposition: `pending`
- Execution: `9/13`
- Passed / failed / pending: `2 / 7 / 4`

## Reasons

- 2 failure cluster(s) still require triage
- 4 required Case(s) have no completed result
- Production-isolated environment evidence is required for release

## Warnings

- code_coverage_not_collected
- environment_not_production_isolated

## Failure Clusters

- `FAIL-001` needs_triage: TC-A08-002-BACKEND, TC-A08-002-CONTRACT - accountobj.account_level has fewer than two live enum options; not_ready
- `FAIL-002` needs_triage: TC-A08-004-BACKEND, TC-A08-004-CONTRACT, TC-A08-005-BACKEND, TC-A08-005-CONTRACT, TC-A08-006-E2E - dynamic relation returned s207050405 instead of s307011537 for zh-cn and en. four-node multi-relation returned s307050002 instead of s307011536. requirement asset effect reproduced the same multi-relation restriction-code defect.
