"""Shared OpenAPI-backed HTTP invocation used by generated APIs and JSON cases."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from framework.api.catalog import HttpApiCatalog
from framework.clients.http import HttpClient
from framework.clients.models import ApiResponse


class HttpApiInvoker:
    def __init__(self, http_client: HttpClient, catalog: HttpApiCatalog) -> None:
        self.http_client = http_client
        self.catalog = catalog

    def call(
        self,
        operation_id: str,
        *,
        body: Any = None,
        path_params: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: Any = None,
        timeout: float | None = None,
    ) -> ApiResponse:
        operation = self.catalog.get(operation_id)
        resolved_path = operation.path
        supplied_path_params = path_params or {}
        for name in operation.path_parameters:
            if name not in supplied_path_params:
                raise ValueError(f"HTTP API '{operation_id}' requires path parameter '{name}'")
            resolved_path = resolved_path.replace(f"{{{name}}}", quote(str(supplied_path_params[name]), safe=""))
        if operation.request_body_required and body is None:
            raise ValueError(f"HTTP API '{operation_id}' requires a request body")

        request_params = dict(params or {})
        if operation.auth_cookie_query:
            cookie_name = operation.auth_cookie_query["cookie"]
            parameter = operation.auth_cookie_query["parameter"]
            token = self.http_client.cookies.get(cookie_name)
            if not token:
                raise ValueError(f"HTTP API '{operation_id}' requires login cookie '{cookie_name}'")
            request_params.setdefault(parameter, token)
        request_headers = {**operation.default_headers, **(headers or {})}
        return self.http_client.request(
            operation.method,
            resolved_path,
            params=request_params or None,
            json_body=body,
            data=data,
            headers=request_headers or None,
            timeout=timeout,
        )
