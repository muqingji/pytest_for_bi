"""Load HTTP operations from OpenAPI documents for data-driven tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HttpOperation:
    operation_id: str
    method: str
    path: str
    default_headers: dict[str, str] = field(default_factory=dict)
    auth_cookie_query: dict[str, str] | None = None
    path_parameters: tuple[str, ...] = ()
    query_parameters: tuple[str, ...] = ()
    request_body_required: bool = False


class HttpApiCatalog:
    def __init__(self, operations: dict[str, HttpOperation]) -> None:
        self.operations = operations

    @classmethod
    def load(cls, directory: Path) -> "HttpApiCatalog":
        operations: dict[str, HttpOperation] = {}
        if not directory.exists():
            return cls(operations)
        for path in sorted(directory.rglob("*.openapi.json")):
            with path.open(encoding="utf-8") as file:
                document = json.load(file)
            for api_path, path_item in document.get("paths", {}).items():
                for method, definition in path_item.items():
                    if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                        continue
                    operation_id = definition.get("operationId")
                    if not operation_id:
                        raise ValueError(f"{path}: {method.upper()} {api_path} is missing operationId")
                    if operation_id in operations:
                        raise ValueError(f"Duplicate OpenAPI operationId: {operation_id}")
                    operations[operation_id] = HttpOperation(
                        operation_id=operation_id,
                        method=method.upper(),
                        path=api_path,
                        default_headers=definition.get("x-default-headers", {}),
                        auth_cookie_query=definition.get("x-auth-cookie-query"),
                        path_parameters=tuple(
                            parameter["name"]
                            for parameter in definition.get("parameters", [])
                            if parameter.get("in") == "path"
                        ),
                        query_parameters=tuple(
                            parameter["name"]
                            for parameter in definition.get("parameters", [])
                            if parameter.get("in") == "query"
                        ),
                        request_body_required=definition.get("requestBody", {}).get("required", False),
                    )
        return cls(operations)

    def get(self, operation_id: str) -> HttpOperation:
        try:
            return self.operations[operation_id]
        except KeyError as error:
            raise KeyError(f"HTTP API operation '{operation_id}' is not defined in idl/http") from error
