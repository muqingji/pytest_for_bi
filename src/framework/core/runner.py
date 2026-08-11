"""Data-driven step runner shared by all interface test cases."""

from __future__ import annotations

import json
import hashlib
import re
from contextlib import nullcontext
from copy import deepcopy
from typing import Any

from framework.clients.database import DatabaseClient
from framework.clients.http import HttpClient
from framework.clients.models import ApiResponse
from framework.clients.rpc import RpcClient
from framework.api.catalog import HttpApiCatalog
from framework.api.http_api import HttpApiInvoker
from framework.config.environment import EnvironmentConfig
from framework.core.assertions import assert_response, get_by_path

try:
    import allure
except ImportError:  # Allows core unit tests without the reporting dependency.
    allure = None


_TEMPLATE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

_BI_OBJECT_LABELS = {
    "chartConfig": "图表配置",
    "schemaAndAgg": "主题指标",
    "chartName": "图表名称",
    "goal": "目标",
    "goalRule": "目标",
    "preTemplate": "预设模板",
    "subscription": "订阅",
    "category": "文件夹名称",
    "dashboard": "数据驾驶舱",
}

_BI_OBJECT_VALUES = {
    **{key: key for key in _BI_OBJECT_LABELS},
    "goal": "goalRule",
}


class CaseRunner:
    def __init__(
        self,
        environment: EnvironmentConfig,
        http_client: HttpClient,
        rpc_client: RpcClient,
        database_client: DatabaseClient,
        api_catalog: HttpApiCatalog | None = None,
    ) -> None:
        self.environment = environment
        self.http_client = http_client
        self.rpc_client = rpc_client
        self.database_client = database_client
        self.api_catalog = api_catalog or HttpApiCatalog({})
        self.http_api = HttpApiInvoker(http_client, self.api_catalog)

    def run(self, case: dict[str, Any]) -> dict[str, Any]:
        target_environment = str(case.get("environment", "") or "")
        if target_environment and target_environment != self.environment.name:
            raise ValueError(
                f"Case requires environment '{target_environment}', got '{self.environment.name}'"
            )
        context: dict[str, Any] = {
            "config": self.environment.values,
            "__case_name": case.get("name", case["id"]),
            "__classification_path": case.get("classification_path"),
            "__classification_values": case.get("classification_values"),
            "matched_folder_name": None,
            "matched_folder_names": [],
            "matched_names": [],
            "matched_translate_values": [],
            "matched_display_paths": [],
            "__lifecycle__": {
                "environment": self.environment.name,
                "namespace": case.get("namespace"),
                "setup": [],
                "readiness": [],
                "test": [],
                "cleanup": [],
            },
            **deepcopy(case.get("variables", {})),
        }
        primary_error: BaseException | None = None
        cleanup_errors: list[BaseException] = []
        try:
            self._run_steps(case.get("setup", []), context, "setup")
            self._run_steps(case.get("readiness", []), context, "readiness")
            self._run_steps(case["steps"], context, "test")
        except BaseException as error:
            primary_error = error
        finally:
            for raw_step in reversed(list(case.get("cleanup", []))):
                when_variable = str(raw_step.get("when_variable", "") or "")
                if when_variable and when_variable not in context:
                    context["__lifecycle__"]["cleanup"].append(
                        {
                            "name": raw_step.get("name", "cleanup"),
                            "status": "skipped",
                            "reason_code": "resource_not_created",
                        }
                    )
                    continue
                try:
                    self._run_steps([raw_step], context, "cleanup")
                except BaseException as error:
                    cleanup_errors.append(error)
        if primary_error is not None:
            if cleanup_errors:
                primary_error.add_note(
                    "Cleanup also failed: "
                    + "; ".join(str(error) for error in cleanup_errors)
                )
            raise primary_error
        if cleanup_errors:
            raise RuntimeError(
                "Case assertions passed but cleanup failed: "
                + "; ".join(str(error) for error in cleanup_errors)
            ) from cleanup_errors[0]
        if "test_response" in context:
            context["response"] = context["test_response"]
            context["status_code"] = context["test_status_code"]
        return context

    def execute(self, case: dict[str, Any]) -> dict[str, Any]:
        """Execute a generated Case Spec with its complete data lifecycle."""
        return self.run(case)

    def _run_steps(
        self,
        raw_steps: list[dict[str, Any]],
        context: dict[str, Any],
        phase: str,
    ) -> None:
        for index, raw_step in enumerate(raw_steps, start=1):
            step = self._resolve(raw_step, context)
            context["__expected_keys"] = step.get("expect", {}).get(
                "body_contains_keys", []
            )
            name = step.get("name", f"{phase} step {index}")
            try:
                if allure:
                    with allure.step(name):
                        self._attach_json("request", step.get("request", {}))
                        response = self._run_step(step, context)
                else:
                    response = self._run_step(step, context)
                context["response"] = response.body
                context["status_code"] = response.status_code
                if phase == "test":
                    context["test_response"] = response.body
                    context["test_status_code"] = response.status_code
                self._extract(response, step.get("extract", {}), context)
                self._attach_response(response)
                if "expect" in step:
                    assert_response(response, step["expect"])
                context["__lifecycle__"][phase].append(
                    self._lifecycle_evidence(name, step, response, "completed")
                )
            except BaseException as error:
                context["__lifecycle__"][phase].append(
                    {
                        "name": name,
                        "operation": self._operation_ref(step),
                        "status": "failed",
                        "error_type": type(error).__name__,
                    }
                )
                raise

    @staticmethod
    def _operation_ref(step: dict[str, Any]) -> str:
        request = step.get("request", {})
        if request.get("api"):
            return str(request["api"])
        return f"{request.get('method', 'GET').upper()} {request.get('path', '')}".strip()

    @classmethod
    def _lifecycle_evidence(
        cls,
        name: str,
        step: dict[str, Any],
        response: ApiResponse,
        status: str,
    ) -> dict[str, Any]:
        canonical = json.dumps(
            response.body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return {
            "name": name,
            "operation": cls._operation_ref(step),
            "status": status,
            "status_code": response.status_code,
            "response_hash": "sha256:"
            + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }

    @staticmethod
    def assert_oracles(
        observations: dict[str, Any], expected: list[dict[str, Any]]
    ) -> None:
        """Evaluate the deterministic Oracle subset used by generated Cases."""
        for item in expected:
            oracle = item.get("oracle", {})
            matcher = str(oracle.get("matcher", "equals"))
            path = str(oracle.get("observation_point", "response"))
            actual = get_by_path(observations, path)
            value = oracle.get("expected_value")
            if matcher == "equals" and actual != value:
                raise AssertionError(f"{item.get('id')}: expected {value!r}, got {actual!r}")
            if matcher == "contains" and value not in actual:
                raise AssertionError(f"{item.get('id')}: {actual!r} does not contain {value!r}")
            if matcher == "not_contains" and value in actual:
                raise AssertionError(f"{item.get('id')}: {actual!r} contains {value!r}")
            if matcher == "one_of" and actual not in oracle.get("expected_values", []):
                raise AssertionError(f"{item.get('id')}: unexpected value {actual!r}")
            if matcher == "regex" and re.search(str(value), str(actual)) is None:
                raise AssertionError(f"{item.get('id')}: {actual!r} does not match {value!r}")
            if matcher == "exists" and actual is None:
                raise AssertionError(f"{item.get('id')}: value does not exist")
            if matcher == "manual_confirmation":
                raise ValueError("manual_confirmation Oracle cannot run automatically")

    def _run_step(self, step: dict[str, Any], context: dict[str, Any]) -> ApiResponse:
        request = step.get("request", {})
        protocol = request.get("protocol", "http").lower()
        if protocol in {"http", "https"}:
            if "api" in request:
                self.environment.require("http.base_url")
                classification_response = self._run_translation_classification_preflight(request, context)
                if classification_response is not None:
                    return classification_response
                return self.http_api.call(
                    request["api"],
                    body=request.get("json", request.get("body")),
                    path_params=request.get("path_params"),
                    params=request.get("params"),
                    headers=request.get("headers"),
                    data=request.get("data"),
                    timeout=request.get("timeout"),
                )
            operation = None
            path = operation.path if operation else request["path"]
            method = operation.method if operation else request.get("method", "GET")
            params = dict(request.get("params") or {})
            headers = {**(operation.default_headers if operation else {}), **(request.get("headers") or {})}
            if not path.startswith(("http://", "https://")):
                self.environment.require("http.base_url")
            if self.environment.get("http.headers") is not None:
                self.environment.require_section("http.headers")
            return self.http_client.request(
                method,
                path,
                params=params or None,
                json_body=request.get("json", request.get("body")),
                data=request.get("data"),
                headers=headers or None,
                timeout=request.get("timeout"),
            )
        if protocol == "rpc":
            adapter = self.environment.get("rpc.adapter")
            if adapter == "framework.adapters.thrift:call":
                self.environment.require("rpc.adapter", "rpc.idl_file", "rpc.host", "rpc.port")
            elif not adapter:
                self.environment.require("rpc.endpoint")
                if self.environment.get("rpc.headers") is not None:
                    self.environment.require_section("rpc.headers")
            return self.rpc_client.call(
                request["service"], request["method"], request.get("params"), request.get("metadata")
            )
        if protocol in {"mysql", "clickhouse", "ch", "database", "db"}:
            database = request.get("database") or protocol
            self.environment.require_section(f"databases.{database}")
            rows = self.database_client.query(database, request["sql"], request.get("parameters"))
            return ApiResponse(status_code=200, body=rows)
        raise ValueError(f"Unsupported request protocol: {protocol}")

    def _run_translation_classification_preflight(
        self, request: dict[str, Any], context: dict[str, Any]
    ) -> ApiResponse | None:
        """Walk BI translation classifications before querying terms/options."""
        api = request.get("api")
        if api not in {"bi.sub_query_optimize", "bi.query_dynamic_type_info_and_options"}:
            return None
        body = request.get("json", request.get("body")) or {}
        if api == "bi.sub_query_optimize":
            arg = body.get("subArg", {})
            bi_objects = arg.get("bi_objects", "")
            classification = arg.get("bi_classification_names", "")
        else:
            arg = body.get("argMap", {})
            bi_objects = arg.get("bi_objects", "")
            classification = arg.get("bi_classification_names", "")
            if body.get("dynamicTypeKey") == "bi_objects":
                return None
        root = {"dynamicTypeKey": "bi_objects", "argMap": {
            "language": body.get("language", arg.get("language", "en")),
            "dataType": body.get("dataType", arg.get("dataType", "bi")),
            "objectApiName": body.get("objectApiName", arg.get("objectApiName", "")),
            "subType": body.get("subType", arg.get("subType", "")),
            "bi_objects": "",
        }}
        root_label = _BI_OBJECT_LABELS.get(bi_objects) if bi_objects else None
        root_value = _BI_OBJECT_VALUES.get(bi_objects) if bi_objects else None
        _, resolved_bi_objects = self._run_classification_request(
            "分类预检 1：查询业务对象" + (f"（{root_label}）" if root_label else ""),
            root,
            expected_option=root_label,
            expected_value=root_value,
        )
        if not bi_objects:
            return None
        if root_label is None:
            raise KeyError(f"Unknown BI classification value {bi_objects!r}")
        common = {
            "language": body.get("language", arg.get("language", "en")),
            "dataType": body.get("dataType", arg.get("dataType", "bi")),
            "objectApiName": body.get("objectApiName", arg.get("objectApiName", "")),
            "subType": body.get("subType", arg.get("subType", "")),
            "bi_objects": resolved_bi_objects,
        }
        configured_path = context.get("__classification_path")
        labels = (
            list(configured_path)
            if isinstance(configured_path, list)
            else str(context.get("__case_name", "")).split("-")[1:]
        )
        configured_values = context.get("__classification_values")
        if isinstance(configured_values, list):
            values = list(configured_values)
        else:
            values = [classification] if classification else []
            view_type = body.get("bi_viewType_names", arg.get("bi_viewType_names"))
            if view_type:
                values.append(view_type)
        path_length = max(len(labels), len(values))
        dynamic_type = "bi_classification_names"
        position = 0
        last_response: ApiResponse | None = None
        while position < path_length:
            level = position + 2
            label = labels[position] if position < len(labels) else str(values[position])
            expected_value = values[position] if position < len(values) else None
            child = {"dynamicTypeKey": dynamic_type, "argMap": {**common, dynamic_type: ""}}
            child_response, selected_value = self._run_classification_request(
                f"分类预检 {level}：查询{label}",
                child,
                expected_option=label,
                expected_value=expected_value,
            )
            last_response = child_response
            common[dynamic_type] = selected_value
            next_types = self._sub_dynamic_types(child_response.body)
            position += 1
            if not next_types:
                return self._run_translation_shape_one(body, arg, common, context, level + 1)
            dynamic_type = next_types[0]
        if last_response is not None:
            return self._run_translation_shape_one(body, arg, common, context, position + 2)
        if not labels and not values:
            child = {"dynamicTypeKey": dynamic_type, "argMap": {**common, dynamic_type: classification}}
            child_response, selected_value = self._run_classification_request(
                "分类预检 2：查询分类选项", child
            )
            common[dynamic_type] = selected_value or classification
            return self._run_translation_shape_one(body, arg, common, context, 3)
        return None

    def _run_translation_shape_one(
        self,
        source_body: dict[str, Any],
        source_arg: dict[str, Any],
        common: dict[str, Any],
        context: dict[str, Any],
        level: int,
    ) -> ApiResponse:
        """Query workbench rows, select the target row, then query its final terms."""
        query_arg = {
            key: value
            for key, value in common.items()
            if key.startswith("bi_") and key != "bi_viewType_names"
        }
        view_type = common.get("bi_viewType_names") or source_body.get(
            "bi_viewType_names", source_arg.get("bi_viewType_names", "")
        )
        view_type_at_top_level = "bi_viewType_names" in source_body
        if not view_type_at_top_level:
            query_arg["bi_viewType_names"] = view_type
        query_body = {
            "language": common["language"],
            "dataType": common["dataType"],
            "objectApiName": common["objectApiName"],
            "subType": common["subType"],
            "subArg": query_arg,
            "breadcrumbCode": source_body.get("breadcrumbCode", "ROOT"),
        }
        if view_type_at_top_level:
            query_body["bi_viewType_names"] = view_type
        query_response = self._run_reported_api_request(
            f"分类结果 {level}：查询文件夹或最终词条列表",
            "bi.query_optimize",
            query_body,
        )
        rows = self._data_rows(query_response.body)
        target_row_key = source_arg.get("rowKey")
        expected_keys = set(context.get("__expected_keys") or [])
        matching_rows = [
            row
            for row in rows
            if (
                (target_row_key and self._row_key(row) == target_row_key)
                or (expected_keys and row.get("translateKey") in expected_keys)
            )
        ]
        if not matching_rows:
            if target_row_key:
                context["matched_folder_name"] = source_arg.get("rowKeyLabel") or None
                sub_arg = {
                    **query_arg,
                    "rowKey": target_row_key,
                    "rowKeyLabel": source_arg.get("rowKeyLabel", ""),
                }
                return self._run_shape_one_sub_query(
                    common, view_type, view_type_at_top_level, sub_arg, context, level + 1
                )
            target = f"rowKey {target_row_key!r}" if target_row_key else f"keys {sorted(expected_keys)!r}"
            raise AssertionError(f"queryOptimize dataRowsAll did not contain target {target}")
        if len(matching_rows) > 1:
            raise AssertionError(f"queryOptimize matched multiple target rows: {len(matching_rows)}")
        row = matching_rows[0]
        row_key = self._row_key(row)
        if not row_key:
            self._capture_matched_translation_fields(query_response, context)
            assertion_context = (
                allure.step("形态二：queryOptimize 已返回最终词条，无需展开分组")
                if allure
                else nullcontext()
            )
            with assertion_context:
                translate_key = row.get("translateKey")
                if not translate_key:
                    raise AssertionError(
                        "queryOptimize matched row is neither a final term nor an expandable folder"
                    )
                self._attach_json("matched final term", row)
            return query_response
        sub_arg = {
            **query_arg,
            "rowKey": row_key,
            "rowKeyLabel": row.get("needTransName", ""),
        }
        self._capture_matched_folder(row, context)
        return self._run_shape_one_sub_query(
            common, view_type, view_type_at_top_level, sub_arg, context, level + 1
        )

    def _capture_matched_folder(
        self, row: dict[str, Any], context: dict[str, Any]
    ) -> None:
        """Record only an expandable folder row actually returned by queryOptimize."""
        folder_name = row.get("needTransName")
        context["matched_folder_name"] = folder_name or None
        context.setdefault("matched_folder_names", []).append(folder_name)
        display_name = (
            folder_name
            if isinstance(folder_name, str) and folder_name.strip()
            else "<名称缺失>"
        )
        step_context = (
            allure.step(f"采集文件夹名称：{display_name}")
            if allure
            else nullcontext()
        )
        with step_context:
            self._attach_json(
                "命中的文件夹名称字段",
                [
                    {
                        "needTransName": folder_name,
                        "rowKey": self._row_key(row),
                    }
                ],
            )

    def _run_shape_one_sub_query(
        self,
        common: dict[str, Any],
        view_type: Any,
        view_type_at_top_level: bool,
        sub_arg: dict[str, Any],
        context: dict[str, Any],
        level: int,
    ) -> ApiResponse:
        sub_query_body = {
            "language": common["language"],
            "dataType": common["dataType"],
            "objectApiName": common["objectApiName"],
            "subType": common["subType"],
            "subArg": sub_arg,
        }
        if view_type_at_top_level:
            sub_query_body["bi_viewType_names"] = view_type
        response = self._run_reported_api_request(
            f"形态一 {level}：查询最终翻译词条",
            "bi.sub_query_optimize",
            sub_query_body,
        )
        self._capture_matched_translation_fields(response, context)
        return response

    def _capture_matched_translation_fields(
        self, response: ApiResponse, context: dict[str, Any]
    ) -> None:
        expected_keys = set(context.get("__expected_keys") or [])
        rows = self._data_rows(response.body)
        matches = [
            row
            for row in rows
            if not expected_keys or row.get("translateKey") in expected_keys
        ]
        names = [row.get("needTransName") for row in matches]
        translate_values = [self._row_translate_value(row) for row in matches]
        folder_name = context.get("matched_folder_name")
        display_paths = [
            " > ".join(
                part
                for part in (
                    folder_name if isinstance(folder_name, str) and folder_name.strip() else None,
                    name if isinstance(name, str) and name.strip() else "<名称缺失>",
                )
                if part
            )
            for name in names
        ]
        context.setdefault("matched_names", []).extend(names)
        context.setdefault("matched_translate_values", []).extend(translate_values)
        context.setdefault("matched_display_paths", []).extend(display_paths)
        display_label = "；".join(display_paths) or "<未采集到最终词条>"
        matched_name_context = (
            allure.step(f"采集最终词条：{display_label}") if allure else nullcontext()
        )
        with matched_name_context:
            self._attach_json(
                "命中的名称与名称翻译字段",
                [
                    {
                        "needTransName": row.get("needTransName"),
                        "translateValue": self._row_translate_value(row),
                        "translateKey": row.get("translateKey"),
                    }
                    for row in matches
                ],
            )

    @staticmethod
    def _row_translate_value(row: dict[str, Any]) -> Any:
        if "translateValue" in row:
            return row["translateValue"]
        row_udef = row.get("returnRowUdef")
        return row_udef.get("translateValue") if isinstance(row_udef, dict) else None

    def _run_reported_api_request(
        self, name: str, operation_id: str, body: dict[str, Any]
    ) -> ApiResponse:
        step_context = allure.step(name) if allure else nullcontext()
        with step_context:
            self._attach_json("request", body)
            response = self.http_api.call(operation_id, body=body)
            self._attach_response(response)
            assertion_context = allure.step("响应断言：HTTP 200，业务状态成功") if allure else nullcontext()
            with assertion_context:
                assert_response(response, {"status_code": 200})
                result = response.body.get("Result") if isinstance(response.body, dict) else None
                if isinstance(result, dict) and result.get("FailureCode") != 0:
                    raise AssertionError(
                        f"Result.FailureCode: expected 0, got {result.get('FailureCode')!r}; "
                        f"message={result.get('FailureMessage')!r}"
                    )
        return response

    @staticmethod
    def _data_rows(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict) and "Value" in value:
            value = value["Value"]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as error:
                raise AssertionError("queryOptimize Value is not valid JSON") from error
        rows = value.get("dataRowsAll") if isinstance(value, dict) else None
        if rows is None and isinstance(value, dict):
            return []
        if not isinstance(rows, list):
            raise AssertionError("queryOptimize response is missing Value.dataRowsAll")
        return [row for row in rows if isinstance(row, dict)]

    @staticmethod
    def _row_key(row: dict[str, Any]) -> Any:
        row_udef = row.get("returnRowUdef")
        return row_udef.get("rowKey") if isinstance(row_udef, dict) else None

    def _run_classification_request(
        self,
        name: str,
        body: dict[str, Any],
        *,
        expected_option: str | None = None,
        expected_value: Any | None = None,
    ) -> tuple[ApiResponse, Any | None]:
        """Run and report one independently asserted classification request."""
        step_context = allure.step(name) if allure else nullcontext()
        with step_context:
            self._attach_json("request", body)
            response = self.http_api.call(
                "bi.query_dynamic_type_info_and_options", body=body
            )
            self._attach_response(response)
            assertion_name = "响应断言：HTTP 200"
            if expected_option is not None:
                assertion_name += f"，包含选项「{expected_option}」"
            elif expected_value is not None:
                assertion_name += f"，包含选项值「{expected_value}」"
            assertion_context = allure.step(assertion_name) if allure else nullcontext()
            with assertion_context:
                assert_response(response, {"status_code": 200})
                if expected_value is not None:
                    selected_value = self._find_option_value(response.body, expected_value)
                elif expected_option is not None:
                    selected_value = self._find_option(response.body, expected_option)
                else:
                    selected_value = None
        return response, selected_value

    @staticmethod
    def _sub_dynamic_types(value: Any) -> list[str]:
        if isinstance(value, dict):
            types = value.get("subDynamicTypes")
            if isinstance(types, list):
                return [item for item in types if isinstance(item, str)]
            for child in value.values():
                found = CaseRunner._sub_dynamic_types(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = CaseRunner._sub_dynamic_types(child)
                if found:
                    return found
        return []

    def _extract(self, response: ApiResponse, mappings: dict[str, str], context: dict[str, Any]) -> None:
        for variable, path in mappings.items():
            if path.startswith("find_option:"):
                context[variable] = self._find_option(response.body, path.removeprefix("find_option:"))
            else:
                context[variable] = get_by_path(response.body, path)

    @classmethod
    def _find_option(cls, value: Any, label: str) -> Any:
        """Find an option by display label and return its API value."""
        if isinstance(value, dict):
            # BI responses also contain metadata such as
            # {"dynamicTypeName": "目标名称"}. Search the actual option
            # collection first so that metadata keys are never selected as API
            # values when their display text happens to match an option label.
            for option_key in ("dynamicTypeOptions", "options"):
                options = value.get(option_key)
                if isinstance(options, (dict, list)):
                    try:
                        return cls._find_option(options, label)
                    except KeyError:
                        pass
            for key, child in value.items():
                if key in {"dynamicTypeName", "dynamicTypeKey"}:
                    continue
                if child == label or (
                    isinstance(child, str)
                    and "".join(child.split()) == "".join(label.split())
                ):
                    return key
            display = next((value.get(key) for key in ("label", "name", "text", "title") if value.get(key) == label), None)
            if display is not None:
                for key in ("value", "key", "apiName", "id"):
                    if key in value:
                        return value[key]
            for child in value.values():
                try:
                    return cls._find_option(child, label)
                except KeyError:
                    pass
        elif isinstance(value, list):
            for child in value:
                try:
                    return cls._find_option(child, label)
                except KeyError:
                    pass
        raise KeyError(f"Option with label {label!r} was not found in response")

    @classmethod
    def _find_option_value(cls, value: Any, expected: Any) -> Any:
        """Return a stable option value without depending on its localized label."""
        if isinstance(value, dict):
            if expected in value and isinstance(value[expected], str):
                return expected
            for option_key in ("dynamicTypeOptions", "options"):
                options = value.get(option_key)
                if isinstance(options, dict) and expected in options:
                    return expected
                if isinstance(options, list):
                    for option in options:
                        if isinstance(option, dict) and expected in option:
                            return expected
            for child in value.values():
                try:
                    return cls._find_option_value(child, expected)
                except KeyError:
                    pass
        elif isinstance(value, list):
            for child in value:
                try:
                    return cls._find_option_value(child, expected)
                except KeyError:
                    pass
        raise KeyError(f"Option value {expected!r} was not found in response")

    def _resolve(self, value: Any, context: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item, context) for item in value]
        if not isinstance(value, str):
            return value
        whole_match = _TEMPLATE.fullmatch(value)
        if whole_match:
            return self._lookup(whole_match.group(1), context)
        return _TEMPLATE.sub(lambda match: str(self._lookup(match.group(1), context)), value)

    @staticmethod
    def _lookup(path: str, context: dict[str, Any]) -> Any:
        current: Any = context
        for component in path.split("."):
            if not isinstance(current, dict) or component not in current:
                raise KeyError(f"Template variable '{{{{ {path} }}}}' was not found")
            current = current[component]
        return current

    @staticmethod
    def _attach_response(response: ApiResponse) -> None:
        CaseRunner._attach_json(
            "response",
            {"status_code": response.status_code, "body": response.body, "headers": response.headers},
        )

    @staticmethod
    def _attach_json(name: str, value: Any) -> None:
        if allure:
            allure.attach(
                json.dumps(value, ensure_ascii=False, default=str, indent=2),
                name=name,
                attachment_type=allure.attachment_type.JSON,
            )
