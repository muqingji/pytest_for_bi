from __future__ import annotations

from framework.clients.models import ApiResponse
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
