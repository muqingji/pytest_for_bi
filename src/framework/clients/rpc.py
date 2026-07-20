"""Generic RPC facade. JSON-RPC is built in; native transports use an adapter."""

from __future__ import annotations

import importlib
import inspect
from typing import Any, Callable

from .http import HttpClient
from .models import ApiResponse


class RpcClient:
    def __init__(self, config: dict[str, Any], http_client: HttpClient | None = None) -> None:
        self.config = config
        self.http_client = http_client or HttpClient(
            headers=config.get("headers"), timeout=config.get("timeout", 20.0), verify=config.get("verify", True)
        )
        self._request_id = 0

    def call(
        self,
        service: str,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ApiResponse:
        adapter_path = self.config.get("adapter")
        if adapter_path:
            return self._call_adapter(adapter_path, service, method, params or {}, metadata or {}, self.config)
        return self._call_jsonrpc(service, method, params or {})

    def _call_jsonrpc(self, service: str, method: str, params: dict[str, Any] | list[Any]) -> ApiResponse:
        endpoint = self.config.get("endpoint")
        if not endpoint:
            raise ValueError("rpc.endpoint is required for the built-in JSON-RPC transport")
        self._request_id += 1
        response = self.http_client.post(
            endpoint,
            json_body={"jsonrpc": "2.0", "id": self._request_id, "method": f"{service}.{method}", "params": params},
        )
        if isinstance(response.body, dict) and "error" in response.body:
            raise RuntimeError(f"RPC {service}.{method} failed: {response.body['error']}")
        if isinstance(response.body, dict) and "result" in response.body:
            response.body = response.body["result"]
        return response

    @staticmethod
    def _call_adapter(
        adapter_path: str,
        service: str,
        method: str,
        params: dict[str, Any] | list[Any],
        metadata: dict[str, Any],
        config: dict[str, Any],
    ) -> ApiResponse:
        module_name, separator, attribute = adapter_path.partition(":")
        if not separator:
            raise ValueError("rpc.adapter must use 'module:function' format")
        adapter: Callable[..., Any] = getattr(importlib.import_module(module_name), attribute)
        arguments: dict[str, Any] = {"service": service, "method": method, "params": params, "metadata": metadata}
        signature = inspect.signature(adapter)
        if "config" in signature.parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
        ):
            arguments["config"] = config
        result = adapter(**arguments)
        if isinstance(result, ApiResponse):
            return result
        return ApiResponse(status_code=200, body=result)
