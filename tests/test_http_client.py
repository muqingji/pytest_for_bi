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
