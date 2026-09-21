"""报告附件：把请求、响应、预期与差异写进 Allure 报告。"""

from __future__ import annotations

import json
from typing import Any

import allure

from tests.common.api_client import ApiResponse


def _dump(payload: Any, limit: int = 20000) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if len(text) > limit:
        text = text[:limit] + f"\n... 已截断 {len(text) - limit} 个字符"
    return text


def attach_case(case: dict[str, Any]) -> None:
    allure.attach(
        _dump({"request": case.get("request"), "expected": case.get("expected")}),
        name="预期请求与预期返回",
        attachment_type=allure.attachment_type.JSON,
    )


def attach_exchange(response: ApiResponse) -> None:
    allure.attach(
        _dump(response.request),
        name="实际请求",
        attachment_type=allure.attachment_type.JSON,
    )
    body = response.body if response.body is not None else response.text
    allure.attach(
        _dump({"status_code": response.status_code, "headers": response.headers, "body": body}),
        name="实际返回",
        attachment_type=allure.attachment_type.JSON,
    )


def attach_diffs(diffs: list[str]) -> None:
    allure.attach(
        "\n".join(diffs) if diffs else "预期与实际一致",
        name="预期与实际差异",
        attachment_type=allure.attachment_type.TEXT,
    )
