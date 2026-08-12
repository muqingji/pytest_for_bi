from __future__ import annotations

import json

import pytest


PREFERRED_SUBJECTS = ("客户", "销售订单", "销售记录")


def _find_schema_list(value):
    if not isinstance(value, dict):
        return None
    for key, nested in value.items():
        if key.casefold() == "schemalist" and isinstance(nested, list):
            return nested
    for nested in value.values():
        found = _find_schema_list(nested)
        if found is not None:
            return found
    return None


def _shape(value, depth=0):
    if depth >= 4:
        return type(value).__name__
    if isinstance(value, dict):
        return {key: _shape(nested, depth + 1) for key, nested in value.items()}
    if isinstance(value, list):
        return [_shape(value[0], depth + 1)] if value else []
    return type(value).__name__


def test_mainstream_schemas_are_discoverable_in_112(environment, case_runner, tmp_path) -> None:
    if environment.name != "112":
        pytest.skip("mainstream schema probe runs only with --env=112")

    response = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.query_schema_list",
        body={
            "pageNumber": 0,
            "pageSize": 500,
            "status": [-1],
            "objectName": ["all"],
            "sortField": "",
            "sortType": 0,
            "timeZone": "Asia/Shanghai",
        },
    )
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") == 0

    schemas = _find_schema_list(response.body) or []
    assert isinstance(schemas, list) and schemas, json.dumps(_shape(response.body), ensure_ascii=False)

    selected = [
        {
            key: schema.get(key)
            for key in ("schemaId", "schemaName", "schemaEnName", "describeApiName", "status")
        }
        for schema in schemas
        if any(subject in json.dumps(schema, ensure_ascii=False) for subject in PREFERRED_SUBJECTS)
    ]
    assert selected, "112 has no discoverable customer, sales-order, or sales-record schema"
    (tmp_path / "mainstream-schemas.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2)
    )
