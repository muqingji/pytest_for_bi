from __future__ import annotations

from datetime import datetime, timezone

import pytest


SCHEMA_ID = "BI_5be1351956fc11448cdde39e"

SCENARIOS = {
    "what": {
        "agg_object": {
            "refObjName": "base_crmfeedrelation",
            "refObjShowName": "follow-up dynamic",
            "refJoinField": "BI_3373af989a240b0bb7f5fa71f7779cd4",
        },
        "agg_field": {
            "dbFieldName": "feed_id", "fieldName": "feed id", "fieldType": "Number",
            "dbObjName": "base_crmfeedrelation", "fieldId": "BI_ffe575aa25f8d92833ee2244cfffd7c3",
        },
        "time_field": {
            "dbFieldName": "create_time", "fieldName": "created at", "fieldType": "Date",
            "dbObjName": "base_crmfeedrelation", "fieldId": "BI_b0faa29fe1a12873720e1f2b756e7e2b",
        },
        "expected_code": "s307011537",
    },
    "whatlist": {
        "agg_object": {
            "refObjName": "active_record", "refObjShowName": "sales record dynamic relation",
            "refJoinField": "BI_d7cf7c3f0e12367c1d6acff274853d9f",
        },
        "agg_field": {
            "dbFieldName": "related_object", "fieldName": "related object", "fieldType": "String",
            "dbObjName": "active_record", "fieldId": "BI_6488425a35e05a4983a93ecfd1e39e77",
        },
        "time_field": {
            "dbFieldName": "create_time", "fieldName": "created at", "fieldType": "Date",
            "dbObjName": "active_record", "fieldId": "BI_b72c4449ec884caf17f67795bd71c72c",
        },
        "expected_code": "s307011537",
    },
    "non_dynamic": {
        "agg_object": {
            "refObjName": "biz_refund", "refObjShowName": "refund",
            "refJoinField": "BI_0aa9ba25823fd3c0a736c2851da5e87a",
        },
        "agg_field": {
            "dbFieldName": "refunded_amount", "fieldName": "refunded amount", "fieldType": "Number",
            "dbObjName": "biz_refund", "fieldId": "BI_dee958f43f3fec268fdc41b8203b1a6b",
        },
        "time_field": {
            "dbFieldName": "refunded_time", "fieldName": "refunded at", "fieldType": "Date",
            "dbObjName": "biz_refund", "fieldId": "BI_ea8d0c37c44510bc922d20774f771b10",
        },
        "expected_code": None,
    },
}


@pytest.mark.parametrize("scenario", [
    pytest.param(
        "what",
        marks=pytest.mark.xfail(
            strict=True,
            reason="confirmed PC-004: 112 returns s207050405 instead of s307011537",
        ),
    ),
    "whatlist",
    "non_dynamic",
])
@pytest.mark.parametrize("locale", ["zh-CN", "en"])
def test_dynamic_relation_metric_lifecycle_in_112(
    environment, case_runner, locale, scenario
) -> None:
    if environment.name != "112":
        pytest.skip("dynamic-relation lifecycle runs only with --env=112")
    config = SCENARIOS[scenario]
    namespace = f"qa-{scenario}-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    field_id = None
    try:
        created = case_runner.http_api.call(
            "fs_bi_stat.agg_rule.add_new_agg_rule",
            body={
                "schemaId": SCHEMA_ID,
                "schemaObjectName": "biz_sales_order",
                "displayName": namespace,
                "aggObject": config["agg_object"],
                "aggField": config["agg_field"],
                "aggFieldTime": config["time_field"],
                "filterLists": [] if scenario != "whatlist" else [{"filters": [{
                    "fieldId": "BI_d7cf7c3f0e12367c1d6acff274853d9f",
                    "fieldID": "BI_d7cf7c3f0e12367c1d6acff274853d9f",
                    "dbFieldName": "related_api_names",
                    "dbObjName": "active_record",
                    "fieldName": "related business objects",
                    "fieldType": "String",
                    "fieldRelationType": "whatList",
                    "type": "select_many",
                    "operator": 26,
                    "value1": '[{"optionCode":"SalesOrderObj"}]',
                }]}],
                "checkFieldAggregateType": 6,
                "initStatus": 1,
                "timeZone": "Asia/Shanghai",
            },
        )
        assert created.status_code == 200
        assert created.body.get("Result", {}).get("FailureCode") == 0
        field_id = str(created.body["Value"]["fieldId"])
        detail = case_runner.http_api.call(
            "fs_bi_stat.stat_base.data_query_da655ba1",
            body={
                "id": SCHEMA_ID, "isView": 0, "measureFieldID": field_id,
                "measureFieldIDs": [field_id], "pageNumber": 1, "pageSize": 1,
                "filterLists": [], "originalDimensionFields": [], "drillDimValues": [],
                "timeZone": "Asia/Shanghai", "lan": locale,
            },
        )
        text = str(detail.body)
        if config["expected_code"]:
            assert config["expected_code"] in text, text
            assert "dataSet" not in text
        else:
            assert "s307011537" not in text, text
    finally:
        if field_id:
            deleted = case_runner.http_api.call(
                "fs_bi_stat.agg_rule.delete_agg_rule",
                body={"schemaId": SCHEMA_ID, "fieldId": field_id, "fieldName": namespace},
            )
            assert deleted.status_code == 200
            assert deleted.body.get("Result", {}).get("FailureCode") == 0
            fields = case_runner.http_api.call(
                "fs_bi_stat.stat_schema.get_fields_by_schema_id", body={"schemaId": SCHEMA_ID}
            )
            assert field_id not in str(fields.body)
            assert namespace not in str(fields.body)
