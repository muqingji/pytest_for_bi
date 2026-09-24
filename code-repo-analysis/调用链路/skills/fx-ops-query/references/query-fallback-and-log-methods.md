# SQL and Log Query Fallback Methods

This is the reusable checklist for database SQL and log query access. It is module-neutral. Business skills should keep business table templates in their own references and link back here for query mechanics.

## When To Use

Use this document when:

- `fx-ops idp query ...` needs to query MySQL, PostgreSQL, MongoDB, or ClickHouse.
- A user asks to query SQL, database rows, logs, flow records, request logs, or says a SQL cannot be queried.
- `fx-ops idp` fails with authentication errors and a verified read-only fallback is needed.
- Query evidence needs to be preserved under `output/evidence/<YYYYMMDD-topic>/`.

## Evidence Discipline

Always create or reuse:

```text
output/evidence/<YYYYMMDD-topic>/
```

Save at least:

- `context.md`: tenant, account, time window, object/module, question.
- `NN-<query-purpose>.json|md`: raw query result or summarized table.
- `summary.md`: conclusion and evidence links.

Do not save credentials, tokens, cookies, passwords, or full browser sessions.

## SQL Query Priority

### Primary: fx-ops idp

Discover data sources:

```bash
fx-ops idp query catalog -j
```

Run SQL:

```bash
fx-ops idp query <biz> --tenant-id <tenant_id> --sql "<SQL>" -j
```

Common CRM business source:

```bash
fx-ops idp query paas-crm-biz --tenant-id <tenant_id> --sql "<SQL>" -j
```

Use `--sql-file` or `--sql-from-stdin` for long SQL.

### Authentication Failure

If `fx-ops idp` returns:

```text
Authentication failed
```

Do not keep changing SQL. First verify the query channel:

```bash
fx-ops idp whoami
fx-ops config info
```

If the token/open API also fails, treat it as an access-channel problem. Use an approved read-only fallback, or clearly report the access blocker. Do not infer business conclusions from missing query results caused by auth failure.

### Fallback: Old PAAS SQL Page

Fallback page:

```text
https://oss.foneshare.cn/paas-console/metadata/sql/query
```

Actual endpoint:

```text
POST https://oss.foneshare.cn/paas-console/metadata/sql/query-result
```

Form parameters:

```text
module=CRM
resourceType=postgresql
tenantId=<tenant_id>
describeApiName=
enableNestloop=true
readOnly=true
sql=<SQL>
```

Notes:

- This is a read-only fallback for tenant SQL troubleshooting.
- Use the browser UI when practical.
- If automation is required, read credentials from local secure environment/config only.
- Never echo credentials, token, or cookie values in commands, prompts, evidence, or final answers.
- The response is JSON. The `info` field may itself be a JSON string containing the row array.

## Safe SQL Rules

- Use only `SELECT`, `WITH`, `EXPLAIN`, `SHOW`, or `DESCRIBE`.
- Always include tenant filter and a narrow condition: primary key, time window, or explicit `LIMIT`.
- For historical event checks, query the event table first, then the current snapshot table.
- Never infer historical behavior from only the current snapshot.
- Convert millisecond timestamps to human time before finalizing conclusions.

Millisecond conversion quick check:

```python
from datetime import datetime, timezone, timedelta
tz = timezone(timedelta(hours=8))
print(datetime.fromtimestamp(<ms> / 1000, tz).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
```

## Log Query Priority

### Primary: fx-ops idp ClickHouse

Use ClickHouse for logs, audit records, traceId lookup, slow SQL, and error bursts.

First estimate or narrow the time range, then query:

```bash
fx-ops idp query biz-app-log --sql "<ClickHouse SQL>" -j
```

Common fields differ by table. Confirm table docs first, especially:

- tenant fields: `ei`, `ea`, `tenantId`, `tenant_id`
- time fields: `_time_second_`, `stamp`, `operationTime`
- trace fields: `traceId`, `rpcId`, `spanId`, `requestId`

### HWS Production Log Access

For `hws-prod` incidents, use the HWS consoles first when the normal `biz-app-log` query path is empty or incomplete:

```text
PAAS console: https://hws-prod.foneshare.cn/paas-console/
ClickHouse / ClickVisual: https://hws-prod-log.foneshare.cn
```

Known HWS ClickVisual table IDs:

- `tid=41`: `log_cep_dist`
- `tid=42`: `log_error_dist`
- `tid=83`: `app_log_dist`

Important notes:

- CEP rows can be found in `log_cep_dist`, but service runtime logs for the routed app may only appear in HWS `app_log_dist`.
- For timeout cases, always check HWS `app_log_dist` by exact `traceId`; AOP or StopWatch rows often show the backend request completing after the CEP timeout.
- Avoid PowerShell backtick quoting in raw ClickVisual expressions. Prefer plain predicates such as `traceId='...' and app='fs-paas-wishful-cloud'`.
- If comparing CEP and app runtime timing, use a tight absolute window around the screenshot time, for example `2026-06-11 09:36:30` to `2026-06-11 09:38:30`.

Reusable HWS timeout checklist:

1. Query `log_cep_dist` by `has(reqId, '<error_code>')` or exact `traceId` to lock `uri`, `status`, `request_time`, `server_ip`, and CEP timeout text.
2. Query HWS `app_log_dist` by exact `traceId` to find AOP / StopWatch / service logs.
3. Compare CEP `request_time` with app AOP total cost. If CEP is around 15000ms and app completes later, classify the frontend error as a gateway timeout caused by backend latency.
4. Query the same tenant and URI for a short series before/after the failure to decide whether it is isolated or persistent.
5. Query all-tenant 5xx for the same URI in the same window before assigning impact scope.

### Fallback: query-clickvisual Local Tool

When ClickHouse IDP access is blocked but ClickVisual is available, use the local tool if present:

```text
C:\Users\wangx\Desktop\query-clickvisual\scripts\query_clickvisual.sh
```

List views:

```bash
bash scripts/query_clickvisual.sh --list-views
```

Query by field:

```bash
bash scripts/query_clickvisual.sh --tid <tid> --field traceId --value <trace_id> --date YYYY-MM-DD --output output/evidence/<topic>/clickvisual.json
```

Query raw expression:

```bash
bash scripts/query_clickvisual.sh --tid <tid> --query "ei='<tenant_id>' AND token='ExceptionClass'" --start "YYYY-MM-DD HH:mm:ss" --end "YYYY-MM-DD HH:mm:ss" --output output/evidence/<topic>/clickvisual.json
```

Useful defaults from the local tool:

- `tid=415`: `log_cep_dist`
- `tid=438`: `app_log_dist`
- `--print-url-only`: generate a ClickVisual UI URL for manual inspection
- smart trace mode can probe CEP first and narrow app logs around the same traceId

## Common Debug Pattern

For "current data says no, but history may have happened":

1. Query history/event table by tenant, time window, and action type.
2. Extract object IDs from the history rows.
3. Query full history for those IDs.
4. Query current snapshot for those IDs.
5. Explain the difference between historical event and current state.

This applies to allocation, owner changes, workflow state, import state, async calculation, reclaim/recycle, and similar issues.

## Required Final Output

When using this method, final conclusions must include:

- data source used: `fx-ops idp`, old PAAS SQL page, or ClickVisual
- safety level: L1/L2/L3 and narrowing condition
- evidence file paths
- query result summary
- access limitation, if any, such as `fx-ops idp Authentication failed`
