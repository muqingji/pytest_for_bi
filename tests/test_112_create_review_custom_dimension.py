from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qa_agents.test_data import validate_test_data_plan


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_NAME = "统计图查看明细限制原因提示优化"
DIMENSION_NAME = "客户等级实时枚举分组自定义维度"
EVIDENCE = ROOT / "generated/112-custom-dimension-create-evidence.json"


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def test_create_review_custom_dimension_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("review custom dimension creation runs only with --env=112")

    objects = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.find_all_custom_dimension_objects",
        body={"keyword": "客户", "pageNumber": 1, "pageSize": 100},
    )
    assert objects.status_code == 200
    assert objects.body.get("Result", {}).get("FailureCode") == 0
    Path("/tmp/112-custom-dimension-objects.json").write_text(
        json.dumps(objects.body, ensure_ascii=False, indent=2)
    )
    account = next(
        item for item in _walk(objects.body) if item.get("describeApiName") == "AccountObj"
    )
    schemas = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_all_schema", body={}
    )
    assert schemas.status_code == 200
    assert schemas.body.get("Result", {}).get("FailureCode") == 0
    Path("/tmp/112-all-schema.json").write_text(
        json.dumps(schemas.body, ensure_ascii=False, indent=2)
    )
    account_schema = next(
        item for item in _walk(schemas.body)
        if item.get("schemaCnName") == account["displayName"]
        and (item.get("schemaId") or item.get("id") or item.get("topologyDescribeId"))
    )
    topology_id = str(
        account_schema.get("schemaId") or account_schema.get("id")
        or account_schema.get("topologyDescribeId")
    )

    fields = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id", body={"schemaId": topology_id}
    )
    assert fields.status_code == 200
    assert fields.body.get("Result", {}).get("FailureCode") == 0
    Path("/tmp/112-account-fields.json").write_text(
        json.dumps(fields.body, ensure_ascii=False, indent=2)
    )
    source = next(
        item for item in _walk(fields.body)
        if item.get("dbFieldName") == "account_level"
        and item.get("fieldId")
        and str(item.get("type", "")).lower().replace("-", "_") in {"select_one", "selectone"}
    )
    filter_result = case_runner.http_client.post(
        "/FHH/EM1HBIUDF/rptUdfViewEditController/getUIType",
        json_body={"fieldID": source["fieldId"], "udfFieldId": source["udfFieldId"]},
    )
    assert filter_result.status_code == 200
    assert filter_result.body.get("Result", {}).get("FailureCode") == 0
    Path("/tmp/112-account-level-ui.json").write_text(
        json.dumps(filter_result.body, ensure_ascii=False, indent=2)
    )
    options = []
    for item in _walk(filter_result.body.get("Value", {}).get("ui", {})):
        code = str(item.get("optionCode", ""))
        if code and code not in options:
            options.append(code)
    assert len(options) >= 2, "account_level live enum options are insufficient; not_ready"
    selected = options[: min(2, len(options))]
    dimension_config = {
        "groups": [
            {"name": "已选客户等级", "values": selected, "isShow": True,
             "description": "来自当前环境客户等级实时枚举"},
            {"name": "未分组", "isNotGrouped": True, "isShow": True,
             "description": "其余实时枚举", "values": [], "isDefault": True},
        ]
    }
    create_body = {
        "topologyDescribeId": topology_id,
        "describeApiName": "AccountObj",
        "dimensionName": DIMENSION_NAME,
        "description": f"需求：{REQUIREMENT_NAME}；枚举来自112实时字段元数据",
        "customType": "enum_group",
        "dimensionConfig": json.dumps(dimension_config, ensure_ascii=False),
        "sourceDimension": {
            "label": source.get("fieldName") or "客户等级",
            "value": source["dbFieldName"],
            "dimensionId": source.get("dimensionId"),
            "topologyDescribeId": topology_id,
            "dimensionField": source["dbFieldName"],
            "dimensionType": source["type"],
            "dimensionName": source.get("fieldName") or "客户等级",
            "describeApiName": "AccountObj",
            "fieldId": source["fieldId"],
        },
        "ownership": "qa-review-custom-dimension-20260812",
    }
    response_hash = _hash(filter_result.body)
    binding = {
        "field_id": str(source["fieldId"]),
        "field_api_name": str(source["dbFieldName"]),
        "option_query_operation": "fs_bi_udf_report.view_edit.get_ui_type",
        "option_response_hash": response_hash,
        "response_json_path": "$.Value.ui.data[*].optionCode",
        "queried_option_codes": options,
        "selected_option_codes": selected,
    }
    plan = {
        "schema_version": "test-data-plan/1.0", "environment": "112",
        "namespace": "qa-review-custom-dimension-20260812",
        "case_plans": [{"case_id": "REVIEW-CUSTOM-DIMENSION", "resources": [{
            "resource_key": "review_custom_dimension", "resource_type": "custom_dimension",
            "resource_id_variable": "dimension_id", "retention_mode": "retain",
            "ownership_namespace": "qa-review-custom-dimension-20260812",
            "display_name": DIMENSION_NAME, "source_field_type": str(source["type"]),
            "setup": {"request": {"api": "fs_bi_stat.custom_dimension.create_custom_dimension",
                                    "json": create_body},
                      "extract": {"dimension_id": "Value.dimensionId"},
                      "enum_option_bindings": [binding]},
            "readiness": [{"request": {"api": "fs_bi_stat.custom_dimension.get_custom_dimension",
                                         "json": {"dimensionId": "{{ dimension_id }}"}}}],
        }]}],
    }
    policy = json.loads((ROOT / "qa-agents/policies/test-data-policy.json").read_text())
    validate_test_data_plan(plan, policy)

    existing = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.find_custom_dimensions",
        body={"topologyDescribeId": topology_id, "keyWord": DIMENSION_NAME,
              "timeZone": "Asia/Shanghai"},
    )
    assert DIMENSION_NAME not in str(existing.body), "review dimension already exists"
    created = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.create_custom_dimension", body=create_body
    )
    assert created.status_code == 200
    assert created.body.get("Result", {}).get("FailureCode") == 0, created.body
    dimension_id = str(created.body.get("Value", {}).get("dimensionId", ""))
    assert dimension_id

    readback = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.get_custom_dimension", body={"dimensionId": dimension_id}
    )
    assert readback.status_code == 200
    assert readback.body.get("Result", {}).get("FailureCode") == 0
    readback_text = json.dumps(readback.body, ensure_ascii=False)
    assert DIMENSION_NAME in readback_text
    assert str(source["fieldId"]) in readback_text
    assert all(code in readback_text for code in selected)

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps({
        "requirement_name": REQUIREMENT_NAME, "resource_type": "custom_dimension",
        "display_name": DIMENSION_NAME, "resource_id": dimension_id,
        "topology_describe_id": topology_id, "source_field_id": source["fieldId"],
        "source_field_api_name": source["dbFieldName"], "source_field_type": source["type"],
        "enum_option_binding": binding, "readback_hash": _hash(readback.body),
        "retention_mode": "retain", "readiness": "active", "reusable": True,
    }, ensure_ascii=False, indent=2) + "\n")


def test_review_custom_dimension_remains_readable_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("review custom dimension readback runs only with --env=112")
    evidence = json.loads(EVIDENCE.read_text())
    response = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.get_custom_dimension",
        body={"dimensionId": evidence["resource_id"]},
    )
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") == 0
    text = json.dumps(response.body, ensure_ascii=False)
    assert evidence["display_name"] in text
    assert evidence["source_field_id"] in text
    assert all(
        code in text for code in evidence["enum_option_binding"]["selected_option_codes"]
    )
