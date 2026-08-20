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


class LifecycleHttpClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json_body")))
        if path == "/resources":
            return ApiResponse(
                status_code=200,
                body={"Value": {"id": "resource-1", "name": kwargs["json_body"]["name"]}},
            )
        if path == "/resources/resource-1" and method == "GET":
            return ApiResponse(status_code=200, body={"Value": {"ready": True}})
        if path == "/resources/resource-1" and method == "DELETE":
            return ApiResponse(status_code=200, body={"deleted": True})
        if path == "/verify":
            return ApiResponse(status_code=200, body={"Result": {"FailureCode": 9001}})
        raise AssertionError(f"unexpected request: {method} {path}")


def _lifecycle_case() -> dict:
    return {
        "id": "detail-integration",
        "environment": "112",
        "namespace": "qa-run-detail",
        "variables": {"namespace": "qa-run-detail"},
        "setup": [
            {
                "name": "create resource",
                "request": {
                    "method": "POST",
                    "path": "/resources",
                    "json": {"name": "{{ namespace }}-chart"},
                },
                "extract": {"resource_id": "Value.id"},
                "expect": {"status_code": 200},
            }
        ],
        "readiness": [
            {
                "name": "wait for resource",
                "request": {"method": "GET", "path": "/resources/{{ resource_id }}"},
                "expect": {"json_path": {"Value.ready": True}},
            }
        ],
        "steps": [
            {
                "name": "verify behavior",
                "request": {"method": "POST", "path": "/verify", "json": {}},
                "expect": {"json_path": {"Result.FailureCode": 9001}},
            }
        ],
        "cleanup": [
            {
                "name": "delete resource",
                "when_variable": "resource_id",
                "request": {"method": "DELETE", "path": "/resources/{{ resource_id }}"},
                "expect": {"status_code": 200},
            }
        ],
        "residue_checks": [
            {
                "name": "verify resource absent",
                "when_variable": "resource_id",
                "request": {"method": "GET", "path": "/resources/{{ resource_id }}"},
                "expect_absent": {"json_path": "Value.id", "value": "{{ resource_id }}"},
            }
        ],
    }


def test_runner_executes_setup_readiness_test_and_finally_cleanup() -> None:
    http = LifecycleHttpClient()
    runner = CaseRunner(
        EnvironmentConfig("112", {"http": {"base_url": "http://test.local", "headers": {}}}),
        http,
        FakeRpcClient(),
        FakeDatabaseClient(),
    )

    context = runner.execute(_lifecycle_case())

    assert [path for _, path, _ in http.calls] == [
        "/resources",
        "/resources/resource-1",
        "/verify",
        "/resources/resource-1",
        "/resources/resource-1",
    ]
    assert context["resource_id"] == "resource-1"
    assert context["__lifecycle__"]["cleanup"][0]["status"] == "completed"
    assert context["__lifecycle__"]["residue"][0]["status"] == "completed"
    assert "response_hash" in context["__lifecycle__"]["setup"][0]


def test_runner_cleans_up_after_test_assertion_failure() -> None:
    http = LifecycleHttpClient()
    runner = CaseRunner(
        EnvironmentConfig("112", {"http": {"base_url": "http://test.local", "headers": {}}}),
        http,
        FakeRpcClient(),
        FakeDatabaseClient(),
    )
    case = _lifecycle_case()
    case["steps"][0]["expect"]["json_path"]["Result.FailureCode"] = 0

    with pytest.raises(AssertionError, match="expected 0"):
        runner.run(case)

    assert http.calls[-1][:2] == ("GET", "/resources/resource-1")


def test_runner_blocks_when_residue_still_exists() -> None:
    class ResidualHttpClient(LifecycleHttpClient):
        def request(self, method, path, **kwargs):
            response = super().request(method, path, **kwargs)
            if path == "/resources/resource-1" and method == "GET" and any(
                call[0] == "DELETE" for call in self.calls
            ):
                return ApiResponse(status_code=200, body={"Value": {"id": "resource-1"}})
            return response

    runner = CaseRunner(
        EnvironmentConfig("112", {"http": {"base_url": "http://test.local", "headers": {}}}),
        ResidualHttpClient(), FakeRpcClient(), FakeDatabaseClient(),
    )

    with pytest.raises(RuntimeError, match="lifecycle finalization failed"):
        runner.execute(_lifecycle_case())


def test_response_rejects_residual_value_anywhere() -> None:
    from framework.core.assertions import assert_response
    from framework.clients.models import ApiResponse

    response = ApiResponse(status_code=200, body={"Value": [{"fieldID": "resource-1"}]})

    with pytest.raises(AssertionError, match="forbidden residual value"):
        assert_response(response, {"body_not_contains_values": ["resource-1"]})


def test_response_finds_runtime_value_inside_nested_json_string() -> None:
    from framework.core.assertions import assert_response
    from framework.clients.models import ApiResponse

    response = ApiResponse(
        status_code=200,
        body={"Value": '{"fields":[{"fieldID":"resource-1"}]}'},
    )

    assert_response(response, {"body_contains_values": ["resource-1"]})


def test_oracle_normalizes_detail_error_and_reports_missing_fields() -> None:
    observations = {
        "test_response": {"Error": {"Code": "s307011535", "Message": "unsupported"}}
    }
    expected = [{
        "id": "EXP-ERROR", "oracle": {
            "observation_point": "detail_api.error", "matcher": "all_fields_equal",
            "expected_value": {
                "error_code": "s307011535", "key": "RESULT_SET_FILTER_DETAIL_UNSUPPORTED"
            },
        },
    }]

    with pytest.raises(AssertionError, match=r"missing=\['key'\], mismatched=\{\}"):
        CaseRunner.assert_oracles(observations, expected)


def test_oracle_normalizes_complete_detail_error_without_weakening() -> None:
    observations = {"test_response": {"Error": {
        "Code": "s307011535", "Key": "RESULT_SET_FILTER_DETAIL_UNSUPPORTED",
        "Parameters": ["Revenue"], "Message": "unsupported",
    }}}
    expected = [{"id": "EXP-ERROR", "oracle": {
        "observation_point": "detail_api.error", "matcher": "all_fields_equal",
        "expected_value": {"error_code": "s307011535",
                           "key": "RESULT_SET_FILTER_DETAIL_UNSUPPORTED",
                           "parameters": ["Revenue"], "message": "unsupported"},
    }}]

    CaseRunner.assert_oracles(observations, expected)


def test_runner_exports_hash_only_lifecycle_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QA_LIFECYCLE_EVIDENCE_DIR", str(tmp_path))
    runner = CaseRunner(
        EnvironmentConfig("112", {"http": {"base_url": "http://test.local", "headers": {}}}),
        LifecycleHttpClient(), FakeRpcClient(), FakeDatabaseClient(),
    )

    runner.execute(_lifecycle_case())
    evidence = json.loads((tmp_path / "detail-integration.json").read_text())

    assert set(evidence["phases"]) == {"setup", "readiness", "test", "cleanup", "residue"}
    assert all(evidence["phases"][phase][0]["status"] == "completed" for phase in evidence["phases"])
    serialized = json.dumps(evidence)
    assert "response_hash" in serialized
    assert "resource-1" not in serialized


def test_runner_rejects_cross_environment_case_before_setup() -> None:
    http = LifecycleHttpClient()
    runner = CaseRunner(
        EnvironmentConfig("112", {"http": {"base_url": "http://test.local", "headers": {}}}),
        http,
        FakeRpcClient(),
        FakeDatabaseClient(),
    )
    case = _lifecycle_case()
    case["environment"] = "online"

    with pytest.raises(ValueError, match="requires environment 'online'"):
        runner.run(case)
    assert http.calls == []


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

    context = {
        "__case_name": "图表配置-报表列表-统计图",
        "__classification_values": ["reportList", "stat"],
        "__expected_keys": ["target-key"],
        "matched_folder_names": [],
    }
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
        context,
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
    assert context["matched_folder_names"] == ["统计图_区域"]
    folder_steps = [
        step for step in fake_allure.steps if step["name"] == "采集文件夹名称：统计图_区域"
    ]
    assert folder_steps[0]["attachments"][0]["name"] == "命中的文件夹名称字段"
    assert folder_steps[0]["attachments"][0]["value"] == [
        {"needTransName": "统计图_区域", "rowKey": "chart-1"}
    ]


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
    assert context["matched_translate_values"] == ["description"]
    assert context["matched_display_paths"] == ["主题描述"]
    assert [operation for operation, _ in shape_two_api.requests] == ["bi.query_optimize"]
    assert any(
        step["name"] == "形态二：queryOptimize 已返回最终词条，无需展开分组"
        for step in fake_allure.steps
    )
    assert any(step["name"] == "采集最终词条：主题描述" for step in fake_allure.steps)


def test_static_row_key_label_is_not_recorded_as_returned_folder() -> None:
    runner = CaseRunner(
        EnvironmentConfig("test", {"http": {"base_url": "http://test.local"}}),
        FakeHttpClient(),
        FakeRpcClient(),
        FakeDatabaseClient(),
    )

    class FallbackFolderApi:
        def __init__(self):
            self.responses = iter(
                [
                    ApiResponse(
                        status_code=200,
                        body={
                            "Result": {"FailureCode": 0},
                            "Value": {"dataRowsAll": []},
                        },
                    ),
                    ApiResponse(
                        status_code=200,
                        body={
                            "Result": {"FailureCode": 0},
                            "Value": {
                                "dataRowsAll": [
                                    {
                                        "needTransName": "Dashboard",
                                        "translateValue": "数据驾驶舱",
                                        "translateKey": "target-key",
                                    }
                                ]
                            },
                        },
                    ),
                ]
            )

        def call(self, operation_id, *, body):
            return next(self.responses)

    runner.http_api = FallbackFolderApi()
    context = {
        "__expected_keys": ["target-key"],
        "matched_folder_names": [],
    }

    runner._run_translation_shape_one(
        {
            "language": "zh-CN",
            "dataType": "bi",
            "objectApiName": "",
            "subType": "",
        },
        {
            "bi_objects": "dashboard",
            "rowKey": "folder-1",
            "rowKeyLabel": "静态中文文件夹",
        },
        {
            "language": "zh-CN",
            "dataType": "bi",
            "objectApiName": "",
            "subType": "",
            "bi_objects": "dashboard",
            "bi_classification_names": "dashboardName",
        },
        context,
        3,
    )

    assert context["matched_folder_name"] == "静态中文文件夹"
    assert context["matched_folder_names"] == []
    assert context["matched_display_paths"] == ["静态中文文件夹 > Dashboard"]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (
            {
                "translateValue": "top-level",
                "returnRowUdef": {"translateValue": "nested"},
            },
            "top-level",
        ),
        ({"returnRowUdef": {"translateValue": "nested"}}, "nested"),
        (
            {
                "translateValue": "",
                "returnRowUdef": {"translateValue": "nested"},
            },
            "",
        ),
        ({}, None),
    ],
)
def test_row_translate_value_supports_final_response_shapes(row, expected) -> None:
    assert CaseRunner._row_translate_value(row) == expected


def test_oracle_accepts_flattened_generated_item() -> None:
    """Generated Candidates may flatten oracle fields onto the expected item."""
    observations = {"detail_api.error.code": "s307011534",
                    "detail_api.error.message.zh_CN": "维度或数据范围中使用了自定义维度字段，暂不支持查看明细"}
    expected = [
        {"id": "EXP-BE-001-01", "matcher": "equals",
         "observation_point": "detail_api.error.code",
         "expected_value": "s307011534"},
        {"id": "EXP-BE-001-02", "matcher": "equals",
         "observation_point": "detail_api.error.message.zh_CN",
         "expected_value": "维度或数据范围中使用了自定义维度字段，暂不支持查看明细"},
    ]
    CaseRunner.assert_oracles(observations, expected)


def test_get_by_path_accepts_jsonpath_prefix_and_root() -> None:
    from framework.core.assertions import get_by_path

    payload = {"Error": {"Code": "s307011534"}, "rows": [{"id": 1}, {"id": 2}]}
    assert get_by_path(payload, "$.Error.Code") == "s307011534"
    assert get_by_path(payload, "$.rows[1].id") == 2
    assert get_by_path(payload, "$") is payload
    assert get_by_path(payload, "Error.Code") == "s307011534"
