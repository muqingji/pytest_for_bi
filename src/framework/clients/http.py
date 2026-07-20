"""HTTP(S) client with one reusable request entry point."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from .models import ApiResponse


class HttpClient:
    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
        verify: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/" if base_url else ""
        self.default_headers = headers or {}
        self.timeout = timeout
        self.verify = verify

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ApiResponse:
        url = path_or_url if path_or_url.startswith(("http://", "https://")) else urljoin(self.base_url, path_or_url.lstrip("/"))
        merged_headers = {**self.default_headers, **(headers or {})}
        with httpx.Client(timeout=timeout or self.timeout, verify=self.verify) as client:
            response = client.request(
                method=method.upper(), url=url, params=params, json=json_body, data=data, headers=merged_headers
            )
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return ApiResponse(
            status_code=response.status_code,
            body=body,
            headers=dict(response.headers),
            elapsed_ms=response.elapsed.total_seconds() * 1000,
            raw_text=response.text,
        )

    def get(self, path_or_url: str, **kwargs: Any) -> ApiResponse:
        return self.request("GET", path_or_url, **kwargs)

    def post(self, path_or_url: str, **kwargs: Any) -> ApiResponse:
        return self.request("POST", path_or_url, **kwargs)

    def put(self, path_or_url: str, **kwargs: Any) -> ApiResponse:
        return self.request("PUT", path_or_url, **kwargs)

    def delete(self, path_or_url: str, **kwargs: Any) -> ApiResponse:
        return self.request("DELETE", path_or_url, **kwargs)

