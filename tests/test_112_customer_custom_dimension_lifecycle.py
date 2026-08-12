from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest


ACCOUNT_SCHEMA_ID = "BI_5bcebcdc3060e20001e79977"
ACCOUNT_DESCRIBE_API_NAME = "AccountObj"
ACCOUNT_LEVEL_API_NAME = "account_level"


def _walk(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _live_option_codes(source_field: dict) -> list[str]:
    codes = []
    for item in _walk(source_field.get("ui", {})):
        code = str(item.get("optionCode", ""))
        if code and code not in codes:
            codes.append(code)
    return codes


def run_customer_custom_dimension_case(
    case_runner, placements_to_test=None, *, combine_result_set_filter=False
) -> None:
    fields_response = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        body={"schemaId": ACCOUNT_SCHEMA_ID},
    )
    assert fields_response.status_code == 200
    assert fields_response.body.get("Result", {}).get("FailureCode") == 0
    source_field = next(
        (
            item
            for item in _walk(fields_response.body)
            if item.get("dbFieldName") == ACCOUNT_LEVEL_API_NAME
            and str(item.get("type", "")).lower().replace("-", "_")
            in {"select_one", "selectone"}
            and item.get("fieldId")
        ),
        None,
    )
    field_shapes = sorted(
        {
            tuple(sorted(item.keys()))
            for item in _walk(fields_response.body)
            if any("field" in str(key).lower() or "api" in str(key).lower() for key in item)
        }
    )
    assert source_field is not None, f"AccountObj.account_level select_one field is unavailable; shapes={field_shapes[:8]}"
    option_codes = _live_option_codes(source_field)
    if len(option_codes) < 2:
        pytest.skip("AccountObj.account_level has fewer than two live enum options; not_ready")
    split = max(1, len(option_codes) // 2)
    dimension_config = json.dumps({
        "groups": [
            {"name": "实时枚举组一", "values": option_codes[:split]},
            {"name": "实时枚举组二", "values": option_codes[split:]},
        ],
        "default_name": "未分组",
    }, ensure_ascii=False)

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    namespace = f"qa-account-enum-{suffix}"
    dimension_id: str | None = None
    deleted_dimension_id: str | None = None
    try:
        created = case_runner.http_api.call(
            "fs_bi_stat.custom_dimension.create_custom_dimension",
            body={
                "topologyDescribeId": ACCOUNT_SCHEMA_ID,
                "customType": "enum_group",
                "dimensionName": namespace,
                "description": "pytest autonomous customer dimension",
                "dimensionConfig": dimension_config,
                "describeApiName": ACCOUNT_DESCRIBE_API_NAME,
                "sourceField": {
                    "fieldId": source_field["fieldId"],
                    "apiName": source_field["dbFieldName"],
                    "type": source_field["type"],
                    "describeApiName": ACCOUNT_DESCRIBE_API_NAME,
                },
            },
        )
        assert created.status_code == 200
        assert created.body.get("Result", {}).get("FailureCode") == 0
        dimension_id = str(created.body["Value"]["dimensionId"])
        assert dimension_id

        ready = case_runner.http_api.call(
            "fs_bi_stat.custom_dimension.get_custom_dimension",
            body={"dimensionId": dimension_id},
        )
        assert ready.status_code == 200
        assert ready.body.get("Result", {}).get("FailureCode") == 0
        assert dimension_id in str(ready.body)
        assert namespace in str(ready.body)

        base_request = {
            "id": ACCOUNT_SCHEMA_ID,
            "isView": 0,
            "measureFieldID": source_field["fieldId"],
            "measureFieldIDs": [source_field["fieldId"]],
            "pageNumber": 1,
            "pageSize": 20,
            "filterLists": [],
            "originalDimensionFields": [],
            "drillDimValues": [],
            "timeZone": "Asia/Shanghai",
            "lan": "zh-CN",
        }
        placements = {
            "dimension": {
                "originalDimensionFields": [
                    {"fieldId": dimension_id, "fieldID": dimension_id, "fieldName": namespace}
                ]
            },
            "data_range": {
                "filterLists": [
                    {
                        "filters": [
                            {
                                "fieldId": dimension_id,
                                "fieldID": dimension_id,
                                "fieldName": namespace,
                                "operator": 1,
                                "value1": "Group A",
                            }
                        ]
                    }
                ]
            },
            "drill_field": {
                "drillDimValues": [
                    {"fieldID": dimension_id, "fieldName": namespace, "value": "Group A"}
                ]
            },
        }
        requested = placements_to_test or [(name, "zh-CN") for name in placements]
        for placement, locale in requested:
            override = placements[placement]
            request = {**base_request, **override}
            request["lan"] = locale
            if combine_result_set_filter:
                request["filterLists"][0]["filters"].append(
                    {
                        "fieldId": source_field["fieldId"],
                        "fieldID": source_field["fieldId"],
                        "fieldName": "result metric",
                        "fieldType": "Number",
                        "operator": 1,
                        "value1": "0",
                        "filterConfig": {"filterGroupType": 1, "aggrType": "2"},
                    }
                )
            detail = case_runner.http_api.call(
                "fs_bi_stat.stat_base.data_query_da655ba1", body=request
            )
            assert detail.status_code == 200, placement
            detail_text = str(detail.body)
            assert "s307011534" in detail_text, f"{placement}: {detail_text}"
            if combine_result_set_filter:
                assert "s307011535" not in detail_text
            assert "dataSet" not in detail_text, placement

        deleted = case_runner.http_api.call(
            "fs_bi_stat.custom_dimension.delete_custom_dimension",
            body={"dimensionId": dimension_id},
        )
        assert deleted.status_code == 200
        assert deleted.body.get("Result", {}).get("FailureCode") == 0
        deleted_dimension_id = dimension_id
        dimension_id = None
    finally:
        if dimension_id:
            cleanup = case_runner.http_api.call(
                "fs_bi_stat.custom_dimension.delete_custom_dimension",
                body={"dimensionId": dimension_id},
            )
            assert cleanup.status_code == 200
            assert cleanup.body.get("Result", {}).get("FailureCode") == 0

    residue = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.find_custom_dimensions",
        body={
            "topologyDescribeId": ACCOUNT_SCHEMA_ID,
            "keyWord": namespace,
            "timeZone": "Asia/Shanghai",
        },
    )
    assert residue.status_code == 200
    assert residue.body.get("Result", {}).get("FailureCode") == 0
    assert deleted_dimension_id not in str(residue.body)
    assert namespace not in str(residue.body)


def test_customer_enum_custom_dimension_lifecycle_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("customer custom-dimension lifecycle runs only with --env=112")
    run_customer_custom_dimension_case(case_runner)
