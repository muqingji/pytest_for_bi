from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.api.catalog import HttpApiCatalog


def test_openapi_catalog_loads_runtime_operation(tmp_path) -> None:
    definition = {
        "openapi": "3.1.0",
        "paths": {
            "/query": {
                "post": {
                    "operationId": "bi.query",
                    "x-default-headers": {"X-Requested-With": "XMLHttpRequest"},
                    "x-auth-cookie-query": {"cookie": "fs_token", "parameter": "_fs_token"},
                }
            }
        },
    }
    (tmp_path / "bi.openapi.json").write_text(json.dumps(definition), encoding="utf-8")

    operation = HttpApiCatalog.load(tmp_path).get("bi.query")

    assert operation.method == "POST"
    assert operation.path == "/query"
    assert operation.default_headers == {"X-Requested-With": "XMLHttpRequest"}
    assert operation.auth_cookie_query == {"cookie": "fs_token", "parameter": "_fs_token"}


def test_openapi_catalog_rejects_unknown_operation(tmp_path) -> None:
    with pytest.raises(KeyError, match="not defined"):
        HttpApiCatalog.load(tmp_path).get("bi.missing")


def test_repository_openapi_contracts_are_loadable() -> None:
    http_contract_dir = Path(__file__).resolve().parents[1] / "idl" / "http"
    catalog = HttpApiCatalog.load(http_contract_dir)

    operation = catalog.get("bi.query_dynamic_type_info_and_options")
    assert operation.method == "POST"
    query_optimize = catalog.get("bi.query_optimize")
    assert query_optimize.method == "POST"
    assert query_optimize.path.endswith("/trans_workbench/service/queryOptimize")
    set_language = catalog.get("pass_api.set_app_language")
    assert set_language.method == "POST"
    assert set_language.path == "/FHH/EM1HLGN/General/SetAppLanguage"
    assert set_language.auth_cookie_query == {"cookie": "fs_token", "parameter": "_fs_token"}
    assert set_language.query_parameters == ("traceId",)
    assert set_language.request_body_required is True

    pass_api_document = json.loads((http_contract_dir / "pass_api.openapi.json").read_text(encoding="utf-8"))
    language_schema = pass_api_document["components"]["schemas"]["SetAppLanguageRequest"]["properties"]["language"]
    assert language_schema == {"type": "string", "enum": ["zh-CN", "en"]}
