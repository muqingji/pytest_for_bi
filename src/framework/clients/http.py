"""HTTP(S) client with one reusable request entry point."""

from __future__ import annotations

import ssl
from typing import Any
from urllib.parse import urljoin

import httpx
import truststore

from .models import ApiResponse


def _resolve_tls_verify(verify: bool | str | ssl.SSLContext) -> bool | ssl.SSLContext:
    if verify == "system":
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if isinstance(verify, str):
        raise ValueError("HTTP verify must be true, false, or 'system'")
    return verify


class HttpClient:
    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
        verify: bool | str | ssl.SSLContext = True,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/" if base_url else ""
        self.default_headers = headers or {}
        self.timeout = timeout
        self.verify = verify
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout,
            verify=_resolve_tls_verify(verify),
        )

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
        response = self._client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            data=data,
            headers=merged_headers,
            timeout=timeout or self.timeout,
        )
        try:
            body = response.json()
        except ValueError:
            body = response.text
        try:
            elapsed_ms = response.elapsed.total_seconds() * 1000
        except RuntimeError:
            elapsed_ms = None
        return ApiResponse(
            status_code=response.status_code,
            body=body,
            headers=dict(response.headers),
            elapsed_ms=elapsed_ms,
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

    @property
    def cookies(self) -> httpx.Cookies:
        return self._client.cookies

    def set_cookie(self, name: str, value: str) -> None:
        """Update a session cookie while preserving its existing domain and path."""
        matches = [cookie for cookie in self._client.cookies.jar if cookie.name == name]
        if matches:
            for cookie in matches:
                cookie.value = value
            return
        self._client.cookies.set(name, value)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
