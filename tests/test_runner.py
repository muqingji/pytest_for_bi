from __future__ import annotations

from contextlib import contextmanager
import json

import pytest

from framework.clients.models import ApiResponse
from framework.api.catalog import HttpApiCatalog, HttpOperation
from framework.config.environment import EnvironmentConfig
from framework.core.runner import CaseRunner
import framework.core.runner as runner_module


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


class FakeAllure:
    class attachment_type:
        JSON = "json"

    def __init__(self) -> None:
        self.steps = []
        self.current_step = None

    @contextmanager
    def step(self, name):
        record = {"name": name, "attachments": []}
        self.steps.append(record)
        previous = self.current_step
        self.current_step = record
        try:
            yield
        finally:
            self.current_step = previous

    def attach(self, value, *, name, attachment_type):
        assert self.current_step is not None
        self.current_step["attachments"].append(
            {"name": name, "value": json.loads(value), "type": attachment_type}
        )


class ClassificationApi:
    def __init__(self) -> None:
        self.requests = []
        self.responses = iter(
            [
                ApiResponse(status_code=200, body={"chartConfig": "图表配置"}),
                ApiResponse(
                    status_code=200,
                    body={
                        "options": {"reportList": "报表列表"},
                        "subDynamicTypes": ["bi_viewType_names"],
                    },
                ),
                ApiResponse(status_code=200, body={"options": {"stat": "统计图"}}),
                ApiResponse(
                    status_code=200,
                    body={
                        "Result": {"FailureCode": 0},
                        "Value": {
                            "dataRowsAll": [
                                {
                                    "needTransName": "统计图_区域",
                                    "translateKey": "target-key",
                                    "returnRowUdef": {"rowKey": "chart-1"},
                                }
                            ]
                        },
                    },
                ),
                ApiResponse(
                    status_code=200,
                    body={"Result": {"FailureCode": 0}, "Value": '{"target-key":"value"}'},
                ),
            ]
        )

    def call(self, operation_id, *, body):
        self.requests.append((operation_id, body))
        return next(self.responses)


@pytest.mark.parametrize("translation_language", ["zh-CN", "en"])
def test_translation_preflight_reports_each_classification_request(
    monkeypatch, translation_language: str
) -> None:
    fake_allure = FakeAllure()
    monkeypatch.setattr(runner_module, "allure", fake_allure)
    runner = CaseRunner(
        EnvironmentConfig("test", {"http": {"base_url": "http://test.local"}}),
        FakeHttpClient(),
        FakeRpcClient(),
        FakeDatabaseClient(),
    )
    classification_api = ClassificationApi()
    runner.http_api = classification_api

    result = runner._run_translation_classification_preflight(
        {
            "api": "bi.sub_query_optimize",
            "body": {
                "language": translation_language,
                "dataType": "bi",
                "subArg": {
                    "bi_objects": "chartConfig",
                    "bi_classification_names": "stat",
                },
            },
        },
        {
            "__case_name": "图表配置-报表列表-统计图",
            "__classification_values": ["reportList", "stat"],
            "__expected_keys": ["target-key"],
        },
    )

    assert result.body["Value"] == '{"target-key":"value"}'
    request_steps = [
        step for step in fake_allure.steps if step["name"].startswith("分类预检")
    ]
    assert [step["name"] for step in request_steps] == [
        "分类预检 1：查询业务对象（图表配置）",
        "分类预检 2：查询报表列表",
        "分类预检 3：查询统计图",
    ]
    assert all(
        [attachment["name"] for attachment in step["attachments"]]
        == ["request", "response"]
        for step in request_steps
    )
    assert [
        step["name"]
        for step in fake_allure.steps
        if step["name"].startswith("响应断言") and "包含选项" in step["name"]
    ] == [
        "响应断言：HTTP 200，包含选项「图表配置」",
        "响应断言：HTTP 200，包含选项「报表列表」",
        "响应断言：HTTP 200，包含选项「统计图」",
    ]
    assert request_steps[1]["attachments"][0]["value"]["argMap"] == {
        "language": translation_language,
        "dataType": "bi",
        "objectApiName": "",
        "subType": "",
        "bi_objects": "chartConfig",
        "bi_classification_names": "",
    }
    assert request_steps[2]["attachments"][1]["value"]["status_code"] == 200
    assert request_steps[2]["attachments"][0]["value"] == {
        "dynamicTypeKey": "bi_viewType_names",
        "argMap": {
            "language": translation_language,
            "dataType": "bi",
            "objectApiName": "",
            "subType": "",
            "bi_objects": "chartConfig",
            "bi_classification_names": "reportList",
            "bi_viewType_names": "",
        },
    }
    assert [operation for operation, _ in classification_api.requests] == [
        "bi.query_dynamic_type_info_and_options",
        "bi.query_dynamic_type_info_and_options",
        "bi.query_dynamic_type_info_and_options",
        "bi.query_optimize",
        "bi.sub_query_optimize",
    ]
    request_languages = []
    for _, body in classification_api.requests:
        request_languages.append(body.get("language", body.get("argMap", {}).get("language")))
    assert request_languages == [translation_language] * 5


def test_find_option_ignores_whitespace_in_folder_names() -> None:
    assert CaseRunner._find_option(
        [{"folder-1": "不区分大小写Single Choice"}],
        "不区分大小写 Single Choice",
    ) == "folder-1"


def test_find_option_does_not_select_dynamic_type_metadata() -> None:
    assert CaseRunner._find_option(
        {
            "Value": {
                "dynamicTypeKey": "bi_classification_names",
                "dynamicTypeName": "目标名称",
                "dynamicTypeOptions": [
                    {"goalRuleName": "目标名称"},
                    {"goalRuleDescription": "目标描述"},
                ],
            }
        },
        "目标名称",
    ) == "goalRuleName"


def test_shape_two_returns_query_optimize_terms_without_sub_query(monkeypatch) -> None:
    fake_allure = FakeAllure()
    monkeypatch.setattr(runner_module, "allure", fake_allure)
    runner = CaseRunner(
        EnvironmentConfig("test", {"http": {"base_url": "http://test.local"}}),
        FakeHttpClient(),
        FakeRpcClient(),
        FakeDatabaseClient(),
    )

    class ShapeTwoApi:
        def __init__(self):
            self.requests = []

        def call(self, operation_id, *, body):
            self.requests.append((operation_id, body))
            return ApiResponse(
                status_code=200,
                body={
                    "Result": {"FailureCode": 0},
                    "Value": {
                        "dataRowsAll": [
                            {
                                "needTransName": "主题描述",
                                "translateKey": "schema-description-key",
                                "returnRowUdef": {"translateValue": "description"},
                            }
                        ]
                    },
                },
            )

    shape_two_api = ShapeTwoApi()
    runner.http_api = shape_two_api
    context = {"__expected_keys": ["schema-description-key"]}
    response = runner._run_translation_shape_one(
        {
            "language": "en",
            "dataType": "bi",
            "objectApiName": "",
            "subType": "",
        },
        {"bi_objects": "schemaAndAgg"},
        {
            "language": "en",
            "dataType": "bi",
            "objectApiName": "",
            "subType": "",
            "bi_objects": "schemaAndAgg",
            "bi_classification_names": "schemaDescription",
        },
        context,
        3,
    )

    assert response.body["Value"]["dataRowsAll"][0]["translateKey"] == "schema-description-key"
    assert context["matched_names"] == ["主题描述"]
    assert [operation for operation, _ in shape_two_api.requests] == ["bi.query_optimize"]
    assert any(
        step["name"] == "形态二：queryOptimize 已返回最终词条，无需展开分组"
        for step in fake_allure.steps
    )
