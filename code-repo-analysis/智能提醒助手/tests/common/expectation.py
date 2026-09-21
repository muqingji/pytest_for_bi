"""预期返回内容与实际返回体的比对。

比对模式：
- subset（默认）：只校验预期中出现的字段，允许响应新增字段（对应 IDL 的“字段只增不删”）。
- exact：连预期外字段一起校验，用于锁定完整契约。

预期值中的通配标记：
- "$any"：任意非空值都通过，用于自增 ID、时间戳等每次不同的字段。
- {"$regex": "..."}: 对字符串做正则匹配。
"""

from __future__ import annotations

import re
from typing import Any

ANY = "$any"
REGEX = "$regex"


def _describe(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)
    return repr(value)


def _compare_node(expected: Any, actual: Any, path: str, mode: str, diffs: list[str]) -> None:
    if isinstance(expected, str) and expected == ANY:
        if actual is None:
            diffs.append(f"{path} 期望任意非空值，实际为 null")
        return

    if isinstance(expected, dict) and set(expected) == {REGEX}:
        pattern = expected[REGEX]
        if not isinstance(actual, str):
            diffs.append(f"{path} 期望匹配正则 {pattern!r}，实际类型为 {type(actual).__name__}")
        elif re.search(pattern, actual) is None:
            diffs.append(f"{path} 期望匹配正则 {pattern!r}，实际为 {_describe(actual)}")
        return

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            diffs.append(f"{path} 期望 object，实际类型为 {type(actual).__name__}")
            return
        if mode == "exact":
            extra = sorted(set(actual) - set(expected))
            if extra:
                diffs.append(f"{path} 出现预期外字段：{extra}")
        for key, expected_value in expected.items():
            child_path = f"{path}.{key}"
            if key not in actual:
                diffs.append(f"{child_path} 缺失，期望 {_describe(expected_value)}")
                continue
            _compare_node(expected_value, actual[key], child_path, mode, diffs)
        return

    if isinstance(expected, list):
        if not isinstance(actual, list):
            diffs.append(f"{path} 期望 array，实际类型为 {type(actual).__name__}")
            return
        if len(expected) != len(actual):
            diffs.append(f"{path} 数组长度期望 {len(expected)}，实际 {len(actual)}")
            return
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            _compare_node(expected_item, actual_item, f"{path}[{index}]", mode, diffs)
        return

    if expected != actual or type(expected) is not type(actual):
        diffs.append(f"{path} 期望 {_describe(expected)}，实际 {_describe(actual)}")


def compare_body(expected: Any, actual: Any, mode: str = "subset") -> list[str]:
    diffs: list[str] = []
    _compare_node(expected, actual, "$", mode, diffs)
    return diffs


def compare_headers(expected: dict[str, str] | None, actual: dict[str, str]) -> list[str]:
    if not expected:
        return []
    lowered = {key.lower(): value for key, value in actual.items()}
    diffs = []
    for key, expected_value in expected.items():
        if key.lower() not in lowered:
            diffs.append(f"响应头缺失：{key}")
            continue
        if expected_value == ANY:
            continue
        if lowered[key.lower()] != expected_value:
            diffs.append(f"响应头 {key} 期望 {expected_value!r}，实际 {lowered[key.lower()]!r}")
    return diffs
