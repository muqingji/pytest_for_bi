"""HTTP(S) client with one reusable request entry point."""

from __future__ import annotations

import secrets
import ssl
import time
from typing import Any
from urllib.parse import urljoin

import httpx
import truststore

from .models import ApiResponse


def _is_fxiaoke_url(url: str) -> bool:
    lowered = str(url or "").lower()
    return "/fhh/" in lowered or "ceshi112.com" in lowered or "fxiaoke.com" in lowered


def _base36_suffix(length: int = 20) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    value = int.from_bytes(secrets.token_bytes(16), "big")
    chars: list[str] = []
    for _ in range(length):
        value, remainder = divmod(value, 36)
        chars.append(alphabet[remainder])
    return "".join(reversed(chars))


def _employee_id_from_body(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    for candidate in (
        ((body.get("Result") or {}).get("UserInfo") or {}).get("EmployeeID")
        if isinstance(body.get("Result"), dict)
        else None,
        ((body.get("Value") or {}).get("UserInfo") or {}).get("EmployeeID")
        if isinstance(body.get("Value"), dict)
        else None,
        (body.get("UserInfo") or {}).get("EmployeeID")
        if isinstance(body.get("UserInfo"), dict)
        else None,
        body.get("EmployeeID"),
    ):
        if candidate not in (None, ""):
            return str(candidate)
    return ""


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
        self.enterprise_account = ""
        self.employee_id = ""
        self._trace_seq = 0

    def set_trace_identity(self, enterprise_account: str, employee_id: str = "") -> None:
        account = str(enterprise_account or "").strip()
        if account:
            self.enterprise_account = account
        employee = str(employee_id or "").strip()
        if employee:
            self.employee_id = employee

    def _next_platform_traces(self) -> tuple[str, str]:
        account = str(self.enterprise_account or "0").strip() or "0"
        employee = str(self.employee_id or "0").strip() or "0"
        self._trace_seq += 1
        fsw = f"FSW-{account}.{employee}-{_base36_suffix()}"
        x_trace = f"{account}_{employee}_{int(time.time() * 1000)}:{self._trace_seq}"
        return fsw, x_trace

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
        request_params = dict(params or {})
        outbound_trace = ""
        if _is_fxiaoke_url(url):
            fsw, x_trace = self._next_platform_traces()
            if not any(str(key).lower() == "traceid" for key in request_params):
                request_params["traceId"] = fsw
            if not any(str(key).lower() in {"x-trace-id", "traceid", "x-request-id"} for key in merged_headers):
                merged_headers["x-trace-id"] = x_trace
            outbound_trace = next(
                (
                    str(request_params[key]).strip()
                    for key in request_params
                    if str(key).lower() == "traceid" and str(request_params[key]).strip()
                ),
                fsw,
            )
        else:
            for key, value in merged_headers.items():
                if str(key).lower() in {"x-trace-id", "traceid", "x-request-id"} and str(value).strip():
                    outbound_trace = str(value).strip()
                    break
        response = self._client.request(
            method=method.upper(),
            url=url,
            params=request_params or None,
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
        employee_id = _employee_id_from_body(body)
        if employee_id:
            self.employee_id = employee_id
        response_headers = dict(response.headers)
        if outbound_trace:
            if not any(str(key).lower() == "traceid" and str(value).strip() for key, value in response_headers.items()):
                response_headers["TraceId"] = outbound_trace
            if not any(
                str(key).lower() in {"x-trace-id", "x-request-id"} and str(value).strip()
                for key, value in response_headers.items()
            ):
                header_trace = next(
                    (
                        str(value).strip()
                        for key, value in merged_headers.items()
                        if str(key).lower() == "x-trace-id" and str(value).strip()
                    ),
                    outbound_trace,
                )
                response_headers["X-Trace-Id"] = header_trace
        return ApiResponse(
            status_code=response.status_code,
            body=body,
            headers=response_headers,
            elapsed_ms=elapsed_ms,
            raw_text=response.text,
            trace_id=outbound_trace,
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
