"""pytest 全局装配：配置、HTTP 客户端、Allure 环境信息。"""

from __future__ import annotations

import socket
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests.common.api_client import ApiClient
from tests.common.settings import Settings, load_settings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--reminder-base-url", default=None, help="覆盖被测服务地址，默认取 testenv/config.json")
    parser.addoption("--reminder-token", default=None, help="覆盖静态令牌，默认取 testenv/config.json")


@pytest.fixture(scope="session")
def settings(request: pytest.FixtureRequest) -> Settings:
    base = load_settings()
    base_url = request.config.getoption("--reminder-base-url") or base.base_url
    token = request.config.getoption("--reminder-token") or base.token
    return replace(base, base_url=str(base_url).rstrip("/"), token=str(token))


@pytest.fixture(scope="session")
def base_url(settings: Settings) -> str:
    """被测服务地址。harness 自检通过覆盖本 fixture 指向本地桩服务。"""
    return settings.base_url


@pytest.fixture(scope="session")
def api_client(settings: Settings, base_url: str) -> ApiClient:
    return ApiClient(replace(settings, base_url=base_url))


@pytest.fixture(scope="session", autouse=True)
def allure_environment(request: pytest.FixtureRequest, settings: Settings) -> None:
    results_dir = request.config.getoption("--alluredir", default=None)
    if not results_dir:
        return
    target = Path(results_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "environment.properties").write_text(
        "\n".join(
            [
                f"base_url={settings.base_url}",
                f"caller={settings.caller}",
                f"timeout_seconds={settings.timeout_seconds}",
                f"python={sys.version.split()[0]}",
                "runner=pytest+allure",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def service_reachable(url: str, timeout: float = 1.0) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
