from __future__ import annotations

import os

import pytest

from framework.clients.database import DatabaseClient
from framework.clients.http import HttpClient
from framework.clients.rpc import RpcClient
from framework.config.environment import EnvironmentConfig, load_cases
from framework.core.runner import CaseRunner


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--env", action="store", default=None, help="Environment suffix, defaults to TEST_ENV or test")


@pytest.fixture(scope="session")
def environment(pytestconfig: pytest.Config) -> EnvironmentConfig:
    return EnvironmentConfig.load(pytestconfig.getoption("--env"))


@pytest.fixture(scope="session")
def case_runner(environment: EnvironmentConfig) -> CaseRunner:
    http = HttpClient(
        base_url=environment.get("http.base_url", ""),
        headers=environment.get("http.headers", {}),
        timeout=environment.get("http.timeout", 20.0),
        verify=environment.get("http.verify", True),
    )
    rpc = RpcClient(environment.get("rpc", {}), http)
    database = DatabaseClient(environment.get("databases", {}))
    return CaseRunner(environment, http, rpc, database)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "api_case" not in metafunc.fixturenames:
        return
    environment = metafunc.config.getoption("--env") or os.getenv("TEST_ENV", "test")
    cases = load_cases(environment)
    parameters = []
    for case in cases:
        marks = [getattr(pytest.mark, tag) for tag in case.get("tags", [])]
        parameters.append(pytest.param(case, id=case["id"], marks=marks))
    metafunc.parametrize("api_case", parameters)
