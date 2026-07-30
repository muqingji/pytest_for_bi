from __future__ import annotations

import os
from pathlib import Path

import pytest

from framework.clients.database import DatabaseClient
from framework.clients.http import HttpClient
from framework.clients.rpc import RpcClient
from framework.auth import authenticate_fxiaoke
from framework.api.catalog import HttpApiCatalog
from framework.config.environment import EnvironmentConfig, load_cases
from framework.core.runner import CaseRunner


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--env", action="store", default=None, help="Environment suffix, defaults to TEST_ENV or test")
    parser.addoption(
        "--priority",
        action="store",
        default=None,
        help="Comma-separated case priorities, for example P0,P1; defaults to TEST_PRIORITIES or all",
    )


@pytest.fixture(scope="session")
def environment(pytestconfig: pytest.Config) -> EnvironmentConfig:
    return EnvironmentConfig.load(pytestconfig.getoption("--env"))


@pytest.fixture(scope="session")
def case_runner(environment: EnvironmentConfig):
    http = HttpClient(
        base_url=environment.get("http.base_url", ""),
        headers=environment.get("http.headers", {}),
        timeout=environment.get("http.timeout", 20.0),
        verify=environment.get("http.verify", True),
    )
    authenticate_fxiaoke(environment, http)
    rpc = RpcClient(environment.get("rpc", {}), http)
    database = DatabaseClient(environment.get("databases", {}))
    api_catalog = HttpApiCatalog.load(Path(__file__).resolve().parents[1] / "idl" / "http")
    yield CaseRunner(environment, http, rpc, database, api_catalog)
    http.close()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "api_case" not in metafunc.fixturenames:
        return
    environment = metafunc.config.getoption("--env") or os.getenv("TEST_ENV", "test")
    priority_option = metafunc.config.getoption("--priority") or os.getenv("TEST_PRIORITIES")
    priorities = {item.strip().upper() for item in priority_option.split(",") if item.strip()} if priority_option else None
    cases = load_cases(environment, priorities=priorities)
    parameters = []
    for case in cases:
        marks = [getattr(pytest.mark, tag) for tag in case.get("tags", [])]
        parameters.append(pytest.param(case, id=f"{case['id']}[{case.get('priority', 'unranked')}]", marks=marks))
    metafunc.parametrize("api_case", parameters)
