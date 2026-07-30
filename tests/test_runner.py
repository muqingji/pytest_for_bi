from __future__ import annotations

from framework.clients.models import ApiResponse
from framework.api.catalog import HttpApiCatalog, HttpOperation
from framework.config.environment import EnvironmentConfig
from framework.core.runner import CaseRunner


class FakeHttpClient:
    def request(self, method, path, **kwargs):
        assert method == "POST"
        assert path == "/login"
        assert kwargs["json_body"] == {"user": "demo"}
        return ApiResponse(status_code=200, body={"code": 0, "data": {"token": "token-1"}})


class FakeRpcClient:
    def call(self, service, method, params, metadata=None):
        assert (service, method, params) == ("UserService", "get_user", {"token": "token-1"})
        return ApiResponse(status_code=200, body={"id": "10001", "active": True})


class FakeDatabaseClient:
    def query(self, name, sql, parameters=None):
        raise AssertionError("This test does not use a database")


def test_runner_resolves_variables_extracts_values_and_runs_rpc() -> None:
    runner = CaseRunner(
        EnvironmentConfig(
            "test", {"http": {"base_url": "http://test.local", "headers": {}}, "rpc": {"endpoint": "http://test.local/rpc"}}
        ),
        FakeHttpClient(),
        FakeRpcClient(),
        FakeDatabaseClient(),
    )
    context = runner.run(
        {
            "id": "login_then_rpc",
            "variables": {"username": "demo"},
            "steps": [
                {
                    "request": {"protocol": "http", "method": "POST", "path": "/login", "json": {"user": "{{ username }}"}},
                    "extract": {"token": "data.token"},
                    "expect": {"status_code": 200, "json_path": {"data.token": "token-1"}},
                },
                {
                    "request": {
                        "protocol": "rpc",
                        "service": "UserService",
                        "method": "get_user",
                        "params": {"token": "{{ token }}"},
                    },
                    "expect": {"body": {"active": True}, "schema": {"type": "object", "required": ["id"]}},
                },
            ],
        }
    )
    assert context["token"] == "token-1"
    assert context["response"] == {"id": "10001", "active": True}


class FakeAuthenticatedHttpClient:
    def __init__(self) -> None:
        self.cookies = {"fs_token": "session-token"}
        self.request_args = None

    def request(self, method, path, **kwargs):
        self.request_args = (method, path, kwargs)
        return ApiResponse(status_code=200, body={"code": 0})


def test_runner_resolves_openapi_operation_and_injects_session_token() -> None:
    http = FakeAuthenticatedHttpClient()
    catalog = HttpApiCatalog(
        {
            "bi.query": HttpOperation(
                operation_id="bi.query",
                method="POST",
                path="/query",
                default_headers={"X-Requested-With": "XMLHttpRequest"},
                auth_cookie_query={"cookie": "fs_token", "parameter": "_fs_token"},
            )
        }
    )
    runner = CaseRunner(
        EnvironmentConfig("112", {"http": {"base_url": "https://crm.ceshi112.com", "headers": {}}}),
        http,
        FakeRpcClient(),
        FakeDatabaseClient(),
        catalog,
    )

    runner.run(
        {
            "id": "bi_category::english",
            "steps": [
                {
                    "request": {"protocol": "http", "api": "bi.query", "json": {"language": "en"}},
                    "expect": {"status_code": 200},
                }
            ],
        }
    )

    assert http.request_args == (
        "POST",
        "/query",
        {
            "params": {"_fs_token": "session-token"},
            "json_body": {"language": "en"},
            "data": None,
            "headers": {"X-Requested-With": "XMLHttpRequest"},
            "timeout": None,
        },
    )
