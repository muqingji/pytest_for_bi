"""业务主体通用前置：被测服务不可达时显式跳过，不产生伪通过结论。"""

from __future__ import annotations

import pytest

from tests.conftest import service_reachable


@pytest.fixture(scope="session", autouse=True)
def require_service(base_url: str) -> None:
    if not service_reachable(base_url):
        pytest.skip(
            f"被测服务不可达（{base_url}）。请先启动 reminder-service 的本地 HTTP 入口"
            "（技术方案 4.3.1），或运行 `make api-selftest` 验证测试环境本身。"
        )
