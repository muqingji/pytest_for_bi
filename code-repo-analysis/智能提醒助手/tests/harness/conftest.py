"""测试环境自检装配：起本地桩服务，并让自检报告不冒用业务服务地址。

注意：本目录下的用例只验证测试环境本身，不代表任何业务结论。
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tests.common.api_client import ApiClient
from tests.common.settings import Settings
from tests.harness.stub_service import start_stub


@pytest.fixture(scope="session")
def stub_service():
    """本地桩服务，绑定 127.0.0.1 的随机端口。"""
    with start_stub() as service:
        yield service


@pytest.fixture(scope="session")
def stub_base_url(stub_service) -> str:
    return stub_service.base_url


@pytest.fixture(scope="session")
def stub_client(settings: Settings, stub_base_url: str) -> ApiClient:
    """自检专用客户端。不复用业务 api_client，避免 session 级缓存串地址。"""
    return ApiClient(replace(settings, base_url=stub_base_url))


@pytest.fixture(scope="session", autouse=True)
def allure_environment(request: pytest.FixtureRequest, settings: Settings, stub_base_url: str) -> None:
    """覆盖父级同名 fixture：自检报告的 base_url 必须指向桩服务，而不是业务地址。"""
    results_dir = request.config.getoption("--alluredir", default=None)
    if not results_dir:
        return
    target = Path(results_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "environment.properties").write_text(
        "\n".join(
            [
                f"base_url={stub_base_url}",
                "scope=测试环境自检（本地桩服务，非业务结论）",
                f"caller={settings.caller}",
                f"timeout_seconds={settings.timeout_seconds}",
                f"python={sys.version.split()[0]}",
                "runner=pytest+allure",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
