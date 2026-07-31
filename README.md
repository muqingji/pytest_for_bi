# pytest interface automation framework

This project is a data-driven interface test framework based on `pytest` and
`Allure`. It supports HTTP(S), RPC, MySQL, and ClickHouse test steps. Tests
contain only one universal case executor; cases, request parameters, expected
results, and environment differences live in JSON files.

Read [LEARNING_GUIDE.md](LEARNING_GUIDE.md) to rebuild this framework from
scratch in a recommended order.

For CI setup, read [docs/JENKINS.md](docs/JENKINS.md). The root `Jenkinsfile`
publishes pytest JUnit output and the Allure report.

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
make test
make allure
```

Open the report with `allure open allure-report`, or run `make serve-allure`.

BI interface automation reports use one dedicated directory instead of writing
multiple `allure-results-*` directories at the repository root:

```bash
make interface-test       # reports/interface-automation/allure-results
make interface-report     # prints details and saves reports/interface-automation/report.txt
make print-interface-report  # reprints the latest results without rerunning cases
make interface-html-report   # optionally generates the local Allure HTML report
```

The text report includes every case and step, request/response attachments,
assertion results, duration, failure traces, and an execution summary. Sensitive
fields are redacted. Each attachment is limited to 6000 characters by default;
set `INTERFACE_REPORT_MAX_CHARS=0` for full output or another number to change
the limit. `interface-report` still prints and saves the report when pytest
fails, then returns pytest's original exit code.

The 112 translation report contains four pytest subjects, covering the complete
matrix of personal language (Chinese or English) and translation language
(Chinese or English). The translation language is independent of the personal
language and is propagated to classification, folder/group, and final-term
requests. Each case still validates its HTTP response, business result, and
target `translateKey`; validation of the returned name's language is deferred.
The two English personal-language subjects run last so a complete workflow
restores the personal language to English.

To publish the generated static report under `oss.firstshare.cn`, configure the
server-side rsync/SSH destination outside the repository and run:

```bash
OSS_REPORT_DEPLOY_TARGET='user@host:/var/www/reports/interface-automation/current/' \
  make publish-interface-report  # explicitly generates HTML and publishes it
```

The published URL defaults to
`https://oss.firstshare.cn/reports/interface-automation/current/`. Override it
with `INTERFACE_REPORT_URL` when the nginx directory mapping differs. The
machine running `interface-html-report` or `publish-interface-report` must have
the Allure CLI installed.

Select an environment by suffix:

```bash
TEST_ENV=prod python3 -m pytest --alluredir=allure-results
python3 -m pytest --env=hk --alluredir=allure-results
```

Fxiaoke CRM cases use dedicated `112` and `online` environments. Generated BI
cases should use the `.112.json` suffix and run with:

```bash
export FXIAOKE_112_ENTERPRISE_ACCOUNT=your-enterprise-account
export FXIAOKE_112_USERNAME=your-username
export FXIAOKE_112_PASSWORD=your-password
python3 -m pytest --env=112 --alluredir=allure-results
```

The 112 environment authenticates through `www.ceshi112.com` and sends BI API
requests to `crm.ceshi112.com`. The online environment uses `www.fxiaoke.com`
for both. Login cookies are retained by the shared HTTP session. Keep all
credentials in environment variables, CI secrets, or an ignored
`config/environment.112.local.json` file.

`--env` overrides `TEST_ENV`; `test` is the default. Each selected environment
requires `config/environment.<env>.json`. `test`, `hk`, and `prod` templates
are included. Case files are recursively loaded only when their names end in
`.<env>.json`, for example:

```text
test_data/user/create.test.json
test_data/user/create.prod.json
test_data/user/create.hk.json
```

The checked-in demo cases are disabled so a fresh clone has no network or
database dependency. Add real values through shell/CI environment variables,
or create the ignored local override file below. Unresolved values fail with a
clear error only when a case uses that protocol.

`config/environment.test.local.json` (never commit this file):

```json
{
  "http": {
    "base_url": "https://test-api.company.internal",
    "headers": {"Authorization": "Bearer real-token"}
  },
  "rpc": {"endpoint": "https://test-rpc.company.internal/jsonrpc"},
  "databases": {
    "mysql": {"host": "mysql.internal", "user": "tester", "password": "secret", "database": "app"}
  }
}
```

`.env.example` lists all supported environment-variable names. Keep actual
secrets in CI secrets, an exported shell environment, or the ignored local
override file.

## API contracts and test subjects

HTTP interfaces are maintained as OpenAPI contracts under `idl/http`. Test
data refers to an interface by `operationId`, so endpoint paths, methods and
authentication token rules are not duplicated in case files. The complete
case model is documented in [docs/API_CASE_MODEL.md](docs/API_CASE_MODEL.md).

BI HTTP contracts and Python callers are generated from the local `fs-bi`
Java repository. Run:

```bash
make sync-fs-bi-http
```

Only routes with a CRM gateway mapping verified in repository code are emitted
as callable APIs. Currently `fs-bi-stat` is verified by its own dialing scripts
as `/FHH/EM1HBISTAT/fs-bi-stat/...`. Other BI modules are not exposed through
the CRM client until their real `/FHH/<application>` mapping is found in code.
The OpenAPI output is written to `idl/http/generated/fs-bi/`, and `FsBiApi` is
the aggregate entry point:

```python
from framework.api.catalog import HttpApiCatalog
from framework.api.generated.fs_bi import FsBiApi
from framework.config.environment import project_root

catalog = HttpApiCatalog.load(project_root() / "idl" / "http")
bi_api = FsBiApi(http_client, catalog)
response = bi_api.stat.view_data_query_api_get_chart_config(body=request_body)
```

Generated method signatures expose path parameters explicitly and accept
request bodies, query parameters, and headers through `body`, `params`, and
`headers`. Generated files should not be edited by hand; update `fs-bi` and
run the sync command again.

A test-data document contains one `test_case` subject and multiple concrete
`cases`. Every concrete case owns its `req`, expected `resp`, and `priority`.
Select priorities during pytest collection with `--priority=P0,P1` or the
`TEST_PRIORITIES` environment variable.

## Case format

Every case has `id` and `steps`. A step can `request`, `extract` output to a
variable, and `expect` a common response contract. Values support
`{{ variable }}` and `{{ config.http.base_url }}` templates. A complete
HTTP/database example is in `test_data/demo.test.json`.
Copy `test_data/templates/http_case.template.json` to a name ending in your
environment suffix, such as `test_data/user/get_user.test.json`, then replace
the sample request and assertion. Set `enabled` to `true` when it is ready.

```json
{
  "id": "get_user",
  "variables": {"user_id": "10001"},
  "steps": [
    {
      "name": "get user",
      "request": {
        "protocol": "http",
        "method": "GET",
        "path": "/v1/users/{{ user_id }}"
      },
      "extract": {"email": "data.email"},
      "expect": {
        "status_code": 200,
        "body": {"code": 0},
        "json_path": {"data.id": "10001"},
        "schema": {
          "type": "object",
          "required": ["code", "data"]
        }
      }
    }
  ]
}
```

`expect.body` is a recursive partial match. Use `body_exact` when the full
response must be equal. `expect.json_path` accepts paths such as
`data.users[0].name`. `expect.schema` supports `type`, `required`,
`properties`, `items`, and `nullable`.

Set `protocol` to `mysql`, `clickhouse`, or `db` for a query step. Database
connections are named under `databases` in the environment configuration.
MySQL parameters use PyMySQL placeholders (`%s`); ClickHouse uses named
parameters supported by `clickhouse-connect`.

## RPC and IDL

`RpcClient.call(service, method, params)` is the only RPC transport entry
point. The default implementation sends JSON-RPC 2.0 to `rpc.endpoint`.
For a native Thrift/Kitex/gRPC stack, set `rpc.adapter` to `module:function`.
That function receives keyword arguments `service`, `method`, `params`, and
`metadata`, plus `config` when its function signature accepts it, and returns
either a value or `ApiResponse`.

The built-in native Thrift adapter can be configured without writing an
adapter. Add this to an ignored local environment override, then generate the
IDL facade as usual:

```json
{
  "rpc": {
    "adapter": "framework.adapters.thrift:call",
    "idl_file": "idl/user.thrift",
    "host": "thrift.test.internal",
    "port": 9090,
    "timeout": 20
  }
}
```

It dynamically loads the Thrift IDL and dispatches `Service.method`. Kitex or
gRPC projects should supply their own generated-client adapter with the same
configuration contract.

Sync IDL-created facades with:

```bash
python3 scripts/sync_idl.py --idl-dir idl
```

Both `.thrift` service definitions and `.proto` service definitions are
supported. One service produces one `*Api` class, with one method per IDL RPC.
Output is written to `src/framework/api/generated/`. It is incremental: an
unchanged generated file is not written; a changed service is regenerated; an
IDL-removed service is intentionally not deleted. Use `--dry-run` to inspect
changes first. Do not hand-edit generated methods; place project-specific API
helpers in a separate non-generated module.
