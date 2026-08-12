from __future__ import annotations

import json

import pytest


def test_custom_dimension_metadata_is_queryable_in_112(environment, case_runner, tmp_path) -> None:
    if environment.name != "112":
        pytest.skip("custom-dimension metadata probe runs only with --env=112")
    response = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.find_all_custom_dimension_objects",
        body={"keyword": "", "pageNumber": 1, "pageSize": 100},
    )
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") == 0
    output = tmp_path / "custom-dimension-objects.json"
    output.write_text(json.dumps(response.body, ensure_ascii=False, indent=2))
    assert response.body.get("Value") is not None


def test_region_schema_custom_dimensions_are_queryable_in_112(
    environment, case_runner, tmp_path
) -> None:
    if environment.name != "112":
        pytest.skip("custom-dimension metadata probe runs only with --env=112")
    response = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.find_custom_dimensions",
        body={
            "topologyDescribeId": "BI_e672ff1046fb773b76bc2b56",
            "pageNumber": 1,
            "pageSize": 100,
            "timeZone": "Asia/Shanghai",
        },
    )
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") == 0
    (tmp_path / "region-custom-dimensions.json").write_text(
        json.dumps(response.body, ensure_ascii=False, indent=2)
    )
