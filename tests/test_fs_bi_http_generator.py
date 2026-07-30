from __future__ import annotations

import json

import pytest

from scripts.sync_fs_bi_http_api import JavaEndpoint, build_documents, parse_java_file, sync


def test_parser_combines_jax_rs_class_and_method_paths(tmp_path) -> None:
    module = tmp_path / "fs-bi-metadata" / "src" / "main" / "java"
    module.mkdir(parents=True)
    source = module / "MetadataService.java"
    source.write_text(
        """
        @Path("v1/metadata")
        public class MetadataService {
          @Path("query/{tenant_id}")
          @POST
          public Result query(@PathParam("tenant_id") Integer tenantId, Request body) { return null; }
        }
        """,
        encoding="utf-8",
    )

    endpoints = parse_java_file(source, tmp_path)

    assert len(endpoints) == 1
    assert endpoints[0].http_method == "POST"
    assert endpoints[0].path == "/v1/metadata/query/{tenant_id}"
    assert [(item.location, item.wire_name) for item in endpoints[0].parameters] == [
        ("path", "tenant_id"),
        ("body", "body"),
    ]


def test_sync_generates_matching_idl_and_module_methods(tmp_path) -> None:
    source_root = tmp_path / "source"
    java_dir = source_root / "fs-bi-stat" / "src" / "main" / "java"
    java_dir.mkdir(parents=True)
    (java_dir / "ChartController.java").write_text(
        """
        @Controller
            @RequestMapping({"/stat", "/fs-bi-stat/stat"})
            public class ChartController {
              /** 查询统计图配置。 */
              @PostMapping("/chart/query")
              public Result query(@RequestBody QueryArg request, @RequestParam("lang") String language) { return null; }
        }
        """,
        encoding="utf-8",
    )
    idl_output = tmp_path / "idl"
    python_output = tmp_path / "python"

    result = sync(source_root, idl_output, python_output)

    document = json.loads((idl_output / "fs-bi-stat.openapi.json").read_text())
    assert result == {"modules": 1, "endpoints": 1}
    operation = document["paths"]["/FHH/EM1HBISTAT/fs-bi-stat/stat/chart/query"]["post"]
    assert operation["operationId"] == "fs_bi_stat.chart.query"
    assert operation["x-auth-cookie-query"] == {"cookie": "fs_token", "parameter": "_fs_token"}
    generated = (python_output / "fs_bi_stat_api.py").read_text()
    assert "def chart_query(self, body: Any" in generated
    assert "language: Any" in generated
    assert '_params["lang"] = language' in generated
    assert "Purpose: 查询统计图配置。" in generated
    assert "Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/chart/query" in generated
    assert "Request body: QueryArg (required)" in generated
    assert "Response: Result" in generated
    assert "Operation ID: fs_bi_stat.chart.query" in generated
    assert '"fs_bi_stat.chart.query"' in generated


def test_duplicate_http_routes_fail_instead_of_overwriting_idl() -> None:
    endpoint = JavaEndpoint(
        module="fs-bi-stat",
        controller="ChartController",
        java_method="query",
        http_method="POST",
        path="/stat/chart/query",
        return_type="Result",
        parameters=(),
        source="ChartController.java",
        line=10,
    )

    with pytest.raises(ValueError, match="Duplicate HTTP route"):
        build_documents([endpoint, endpoint])
