"""Stable pytest fixtures used by repository tests and controlled N08 runs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from framework.api.catalog import HttpApiCatalog
from framework.auth import authenticate_fxiaoke, validate_credential_source
from framework.clients.database import DatabaseClient
from framework.clients.http import HttpClient
from framework.clients.rpc import RpcClient
from framework.config.environment import EnvironmentConfig, load_cases, project_root
from framework.core.runner import CaseRunner


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--env", action="store", default=None)
    parser.addoption("--priority", action="store", default=None)


@pytest.fixture(scope="session")
def environment(pytestconfig: pytest.Config) -> EnvironmentConfig:
    name = pytestconfig.getoption("--env") or os.getenv("TEST_ENV", "test")
    if name == "112":
        validate_credential_source(name)
    return EnvironmentConfig.load(name)


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
    api_catalog = HttpApiCatalog.load(project_root() / "idl" / "http")
    yield CaseRunner(environment, http, rpc, database, api_catalog)
    http.close()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "api_case" not in metafunc.fixturenames:
        return
    environment = metafunc.config.getoption("--env") or os.getenv("TEST_ENV", "test")
    priority_option = metafunc.config.getoption("--priority") or os.getenv("TEST_PRIORITIES")
    priorities = (
        {item.strip().upper() for item in priority_option.split(",") if item.strip()}
        if priority_option else None
    )
    cases = [case for case in load_cases(environment, priorities=priorities) if not case.get("workflow")]
    parameters = [
        pytest.param(
            case, id=f"{case['id']}[{case.get('priority', 'unranked')}]",
            marks=[getattr(pytest.mark, tag) for tag in case.get("tags", [])],
        )
        for case in cases
    ]
    metafunc.parametrize("api_case", parameters)
