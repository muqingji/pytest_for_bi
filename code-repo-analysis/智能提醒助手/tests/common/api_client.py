"""HTTP 客户端：按 IDL 发送请求，原样保留响应供断言与报告附件使用。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from tests.common.settings import Settings


@dataclass
class ApiResponse:
    request: dict[str, Any]
    status_code: int
    headers: dict[str, str]
    body: Any
    text: str
    elapsed_ms: int


def _masked_headers(headers: dict[str, str]) -> dict[str, str]:
    masked = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            scheme = value.split(" ", 1)[0]
            masked[key] = f"{scheme} ***"
        else:
            masked[key] = value
    return masked


class ApiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()

    @property
    def settings(self) -> Settings:
        return self._settings

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        path_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> ApiResponse:
        resolved_path = path
        for name, value in (path_params or {}).items():
            resolved_path = resolved_path.replace("{" + name + "}", str(value))
        if "{" in resolved_path:
            raise ValueError(f"路径参数未解析完整：{resolved_path}")

        url = f"{self._settings.base_url}{resolved_path}"
        request_headers = {
            "Authorization": self._settings.authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "X-Caller": self._settings.caller,
        }
        if request_id:
            request_headers["X-Request-ID"] = request_id
        request_headers.update(headers or {})

        response = self._session.request(
            method.upper(),
            url,
            json=body,
            headers=request_headers,
            timeout=self._settings.timeout_seconds,
        )
        try:
            parsed = response.json()
        except ValueError:
            parsed = None

        return ApiResponse(
            request={
                "method": method.upper(),
                "url": url,
                "headers": _masked_headers(request_headers),
                "body": body,
            },
            status_code=response.status_code,
            headers=dict(response.headers),
            body=parsed,
            text=response.text,
            elapsed_ms=int(response.elapsed.total_seconds() * 1000),
        )
