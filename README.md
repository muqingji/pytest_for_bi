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

Select an environment by suffix:

```bash
TEST_ENV=prod python3 -m pytest --alluredir=allure-results
python3 -m pytest --env=hk --alluredir=allure-results
```

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
