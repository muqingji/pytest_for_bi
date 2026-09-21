"""用例执行：把一个 case（单请求或组合场景）跑成可断言的步骤结果。

组合场景支持从上一步的响应中取值：
- `{step<序号>.body.<字段路径>}`，例如 `{step1.body.decision_id}`
- `{step<序号>.headers.<响应头名>}`
可出现在后续 step 的 `path`、`path_params` 和 `body` 中。序号从 1 开始。
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from tests.common.api_client import ApiClient, ApiResponse
from tests.common.case_loader import Endpoint
from tests.common.expectation import compare_body, compare_headers

_PLACEHOLDER = re.compile(r"\{step(\d+)\.(body|headers)\.([A-Za-z0-9_.\-]+)\}")


@dataclass
class StepResult:
    name: str
    request: dict[str, Any]
    response: ApiResponse
    expected: dict[str, Any]
    diffs: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.diffs


def _extract(response: ApiResponse, source: str, key_path: str) -> Any:
    current: Any = response.body if source == "body" else response.headers
    for part in key_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(f"上一步响应中取不到 {{step*.{source}.{key_path}}}：缺少 {part!r}")
    return current


def _substitute(value: Any, previous: list[ApiResponse]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            index = int(match.group(1))
            if index < 1 or index > len(previous):
                raise KeyError(f"占位符引用了尚未执行的第 {index} 步")
            return str(_extract(previous[index - 1], match.group(2), match.group(3)))

        return _PLACEHOLDER.sub(replace, value)
    if isinstance(value, dict):
        return {key: _substitute(item, previous) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute(item, previous) for item in value]
    return value


def _steps_of(case: dict[str, Any]) -> list[dict[str, Any]]:
    if "steps" in case:
        return case["steps"]
    return [{"name": case["name"], "request": case["request"], "expected": case["expected"]}]


def run_case(api_client: ApiClient, subject_endpoint: Endpoint, case: dict[str, Any]) -> list[StepResult]:
    mode = case.get("match", "subset")
    previous: list[ApiResponse] = []
    results: list[StepResult] = []

    for step in _steps_of(case):
        request = step["request"]
        expected = step["expected"]
        body = _substitute(request["body"], previous)
        if isinstance(body, dict) and not body.get("request_id"):
            body["request_id"] = str(uuid.uuid4())

        response = api_client.request(
            step.get("method", subject_endpoint.method),
            _substitute(step.get("path", subject_endpoint.path), previous),
            body=body,
            path_params=_substitute(request.get("path_params", {}), previous),
            headers=_substitute(request.get("headers", {}), previous),
        )

        diffs: list[str] = []
        if response.status_code != expected["status_code"]:
            diffs.append(f"HTTP 状态码期望 {expected['status_code']}，实际 {response.status_code}")
        diffs.extend(compare_headers(expected.get("headers"), response.headers))
        if response.body is None:
            diffs.append(f"响应体不是合法 JSON，原始内容：{response.text[:200]!r}")
        else:
            diffs.extend(compare_body(expected["body"], response.body, expected.get("match", mode)))

        results.append(
            StepResult(
                name=step["name"],
                request={"method": step.get("method", subject_endpoint.method), "body": body},
                response=response,
                expected=expected,
                diffs=diffs,
            )
        )
        previous.append(response)

    return results


def render_diff(case: dict[str, Any], results: list[StepResult]) -> str:
    lines = [f"用例 {case['id']} {case['name']}"]
    for index, result in enumerate(results, start=1):
        lines.append(f"步骤 {index} {result.name}：{'通过' if result.passed else '未通过'}")
        for diff in result.diffs:
            lines.append(f"  - {diff}")
    return "\n".join(lines)


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
