from __future__ import annotations

import httpx
import pytest

from framework.clients import http as http_module
from framework.clients.http import HttpClient, _resolve_tls_verify


def test_system_tls_verify_uses_platform_trust_store(monkeypatch) -> None:
    marker = object()
    monkeypatch.setattr(http_module.truststore, "SSLContext", lambda protocol: marker)

    assert _resolve_tls_verify("system") is marker


def test_unknown_tls_verify_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="true, false, or 'system'"):
        _resolve_tls_verify("unknown")


def test_set_cookie_preserves_existing_domain_and_path() -> None:
    session = httpx.Client()
    session.cookies.set("lang", "en", domain="crm.ceshi112.com", path="/")
    client = HttpClient(client=session)

    client.set_cookie("lang", "zh-CN")

    cookies = [cookie for cookie in session.cookies.jar if cookie.name == "lang"]
    assert [(cookie.value, cookie.domain, cookie.path) for cookie in cookies] == [
        ("zh-CN", "crm.ceshi112.com", "/")
    ]
    session.close()


def test_set_cookie_creates_missing_session_cookie() -> None:
    session = httpx.Client()
    client = HttpClient(client=session)

    client.set_cookie("lang", "en")

    assert session.cookies.get("lang") == "en"
    session.close()


def test_fxiaoke_requests_use_platform_fsw_trace_id() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), dict(request.headers)))
        return httpx.Response(
            200,
            json={"Result": {"FailureCode": 0, "UserInfo": {"EmployeeID": 1002, "EnterpriseAccount": "91863"}}},
        )

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = HttpClient(base_url="https://crm.ceshi112.com", client=raw_client)
    client.set_trace_identity("91863")
    first = client.post("/FHH/EM1HBICRM/statCreateController/copyStatView", json_body={"ok": True})
    second = client.post("/FHH/EM1HBISTAT/fs-bi-stat/stat/dataQuery", json_body={"ok": True})
    raw_client.close()

    first_url, first_headers = seen[0]
    second_url, second_headers = seen[1]
    assert "traceId=FSW-91863.0-" in first_url
    assert first.trace_id.startswith("FSW-91863.0-")
    assert first_headers.get("x-trace-id", "").startswith("91863_0_")
    assert "traceId=FSW-91863.1002-" in second_url
    assert second.trace_id.startswith("FSW-91863.1002-")
    assert second_headers.get("x-trace-id", "").startswith("91863_1002_")
    assert not first.trace_id.startswith("QA-")
    assert first.trace_id != second.trace_id


def test_non_fxiaoke_requests_do_not_invent_qa_trace_ids() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = HttpClient(base_url="http://test.local", client=raw_client)
    response = client.get("/health")
    raw_client.close()

    assert "traceId=" not in seen[0]
    assert response.trace_id == ""
