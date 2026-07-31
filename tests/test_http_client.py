from __future__ import annotations

import httpx

from framework.clients.http import HttpClient


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
