from __future__ import annotations

import base64

import httpx
import pytest

from framework.auth.fxiaoke import PUBLIC_KEY_DER, FxiaokeAuthenticationError, _encrypt_password, authenticate_fxiaoke
from framework.clients.http import HttpClient
from framework.clients.models import ApiResponse
from framework.config.environment import EnvironmentConfig


class FakeHttpClient:
    def __init__(self, response: ApiResponse) -> None:
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def _environment(login_base_url: str = "https://www.ceshi112.com") -> EnvironmentConfig:
    return EnvironmentConfig(
        "112",
        {
            "auth": {
                "enabled": True,
                "type": "fxiaoke_crm",
                "login_base_url": login_base_url,
                "login_path": "/FHH/EM0HUL/Authorize/EnterpriseAccountLogin",
                "enterprise_account": "94041",
                "username": "tester",
                "password": "secret",
            }
        },
    )


def test_authentication_matches_cypress_login_contract(monkeypatch) -> None:
    monkeypatch.setattr("framework.auth.fxiaoke._encrypt_password", lambda value: "encrypted-password")
    client = FakeHttpClient(ApiResponse(status_code=200, body={"Value": {"LoginResult": True}}))

    authenticate_fxiaoke(_environment(), client)

    url, kwargs = client.calls[0]
    assert url == "https://www.ceshi112.com/FHH/EM0HUL/Authorize/EnterpriseAccountLogin"
    assert kwargs["json_body"] == {
        "publickKey": PUBLIC_KEY_DER,
        "userAccount": "tester",
        "enterpriseAccount": "94041",
        "rsaPassword": "encrypted-password",
        "persistenceHint": True,
    }
    assert kwargs["headers"]["Origin"] == "https://www.ceshi112.com"
    assert kwargs["headers"]["Referer"] == "https://www.ceshi112.com/XV/UI/Home"


def test_password_encryption_matches_1024_bit_rsa_ciphertext_size() -> None:
    ciphertext = base64.b64decode(_encrypt_password("secret"))

    assert len(ciphertext) == 128
    assert ciphertext != base64.b64decode(_encrypt_password("secret"))


def test_authentication_rejects_business_error(monkeypatch) -> None:
    monkeypatch.setattr("framework.auth.fxiaoke._encrypt_password", lambda value: "encrypted-password")
    client = FakeHttpClient(ApiResponse(status_code=200, body={"Error": {"Code": 1001, "Message": "bad login"}}))

    with pytest.raises(FxiaokeAuthenticationError, match="bad login"):
        authenticate_fxiaoke(_environment(), client)


def test_http_client_reuses_login_cookie() -> None:
    seen_cookies = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_cookies.append(request.headers.get("cookie", ""))
        if request.url.path == "/login":
            return httpx.Response(200, json={"ok": True}, headers={"set-cookie": "fs_token=session-1; Domain=.ceshi112.com; Path=/"})
        return httpx.Response(200, json={"ok": True})

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = HttpClient(base_url="https://crm.ceshi112.com", client=raw_client)
    client.post("https://www.ceshi112.com/login")
    client.get("/bi/resource")

    assert seen_cookies == ["", "fs_token=session-1"]
    raw_client.close()


def test_checked_in_environment_domains_are_separated() -> None:
    env_112 = EnvironmentConfig.load("112")
    online = EnvironmentConfig.load("online")

    assert env_112.get("auth.login_base_url") == "https://www.ceshi112.com"
    assert env_112.get("http.base_url") == "https://crm.ceshi112.com"
    assert online.get("auth.login_base_url") == "https://www.fxiaoke.com"
    assert online.get("http.base_url") == "https://www.fxiaoke.com"
