"""Reusable response and data assertions for JSON-like results."""

from __future__ import annotations

import re
from typing import Any

from framework.clients.models import ApiResponse


_PATH_PART = re.compile(r"([^.[\]]+)|\[([0-9]+)\]")


def get_by_path(value: Any, path: str) -> Any:
    """Read ``a.b[0].c`` from a dict/list result."""
    current = value
    for name, index in _PATH_PART.findall(path.removeprefix("body.")):
        if name:
            if not isinstance(current, dict) or name not in current:
                raise AssertionError(f"Path '{path}' does not exist at '{name}'")
            current = current[name]
        else:
            if not isinstance(current, list) or int(index) >= len(current):
                raise AssertionError(f"Path '{path}' does not exist at index {index}")
            current = current[int(index)]
    return current


def assert_contains(actual: Any, expected: Any, path: str = "body") -> None:
    """Assert expected is a recursive subset of actual."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise AssertionError(f"{path}: expected an object, got {type(actual).__name__}")
        for key, expected_value in expected.items():
            if key not in actual:
                raise AssertionError(f"{path}: missing key '{key}'")
            assert_contains(actual[key], expected_value, f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list):
            raise AssertionError(f"{path}: expected a list, got {type(actual).__name__}")
        if len(actual) < len(expected):
            raise AssertionError(f"{path}: expected at least {len(expected)} items, got {len(actual)}")
        for index, expected_value in enumerate(expected):
            assert_contains(actual[index], expected_value, f"{path}[{index}]")
    elif actual != expected:
        raise AssertionError(f"{path}: expected {expected!r}, got {actual!r}")


def assert_schema(value: Any, schema: Any, path: str = "body") -> None:
    """Small JSON schema subset: type, required, properties, items, nullable."""
    if not isinstance(schema, dict):
        raise ValueError(f"{path}: schema must be an object")
    if value is None and schema.get("nullable"):
        return
    expected_type = schema.get("type")
    type_map = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}
    if expected_type:
        python_type = type_map.get(expected_type)
        if python_type is None:
            raise ValueError(f"{path}: unsupported schema type '{expected_type}'")
        if not isinstance(value, python_type) or (expected_type == "integer" and isinstance(value, bool)):
            raise AssertionError(f"{path}: expected {expected_type}, got {type(value).__name__}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise AssertionError(f"{path}: missing required key '{key}'")
        for key, child_schema in schema.get("properties", {}).items():
            if key in value:
                assert_schema(value[key], child_schema, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            assert_schema(item, schema["items"], f"{path}[{index}]")


def assert_response(response: ApiResponse, expected: dict[str, Any]) -> None:
    """Validate an ApiResponse with a consistent case-file contract."""
    if "status_code" in expected and response.status_code != expected["status_code"]:
        raise AssertionError(f"status_code: expected {expected['status_code']}, got {response.status_code}")
    if "body" in expected:
        assert_contains(response.body, expected["body"])
    if "body_exact" in expected and response.body != expected["body_exact"]:
        raise AssertionError(f"body: expected exactly {expected['body_exact']!r}, got {response.body!r}")
    for path, value in expected.get("json_path", {}).items():
        actual = get_by_path(response.body, path)
        if actual != value:
            raise AssertionError(f"{path}: expected {value!r}, got {actual!r}")
    if "schema" in expected:
        assert_schema(response.body, expected["schema"])
    for header, value in expected.get("headers", {}).items():
        actual = response.headers.get(header.lower()) or response.headers.get(header)
        if actual != value:
            raise AssertionError(f"header '{header}': expected {value!r}, got {actual!r}")

