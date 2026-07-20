"""Data-driven step runner shared by all interface test cases."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from framework.clients.database import DatabaseClient
from framework.clients.http import HttpClient
from framework.clients.models import ApiResponse
from framework.clients.rpc import RpcClient
from framework.config.environment import EnvironmentConfig
from framework.core.assertions import assert_response, get_by_path

try:
    import allure
except ImportError:  # Allows core unit tests without the reporting dependency.
    allure = None


_TEMPLATE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


class CaseRunner:
    def __init__(
        self,
        environment: EnvironmentConfig,
        http_client: HttpClient,
        rpc_client: RpcClient,
        database_client: DatabaseClient,
    ) -> None:
        self.environment = environment
        self.http_client = http_client
        self.rpc_client = rpc_client
        self.database_client = database_client

    def run(self, case: dict[str, Any]) -> dict[str, Any]:
        context: dict[str, Any] = {"config": self.environment.values, **deepcopy(case.get("variables", {}))}
        last_response: ApiResponse | None = None
        for index, raw_step in enumerate(case["steps"], start=1):
            step = self._resolve(raw_step, context)
            name = step.get("name", f"step {index}")
            if allure:
                with allure.step(name):
                    last_response = self._run_step(step, context)
            else:
                last_response = self._run_step(step, context)
            context["response"] = last_response.body
            context["status_code"] = last_response.status_code
            self._extract(last_response, step.get("extract", {}), context)
            if "expect" in step:
                assert_response(last_response, step["expect"])
            self._attach_response(last_response)
        return context

    def _run_step(self, step: dict[str, Any], context: dict[str, Any]) -> ApiResponse:
        request = step.get("request", {})
        protocol = request.get("protocol", "http").lower()
        if protocol in {"http", "https"}:
            if not request["path"].startswith(("http://", "https://")):
                self.environment.require("http.base_url")
            if self.environment.get("http.headers") is not None:
                self.environment.require_section("http.headers")
            return self.http_client.request(
                request.get("method", "GET"),
                request["path"],
                params=request.get("params"),
                json_body=request.get("json", request.get("body")),
                data=request.get("data"),
                headers=request.get("headers"),
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

    def _extract(self, response: ApiResponse, mappings: dict[str, str], context: dict[str, Any]) -> None:
        for variable, path in mappings.items():
            context[variable] = get_by_path(response.body, path)

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
        if allure:
            allure.attach(
                json.dumps(
                    {"status_code": response.status_code, "body": response.body, "headers": response.headers},
                    ensure_ascii=False,
                    default=str,
                    indent=2,
                ),
                name="response",
                attachment_type=allure.attachment_type.JSON,
            )
