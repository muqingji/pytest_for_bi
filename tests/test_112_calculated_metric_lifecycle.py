from __future__ import annotations

from datetime import datetime, timezone

import pytest


SCHEMA_ID = "BI_e672ff1046fb773b76bc2b56"


def test_calculated_metric_create_delete_and_residue_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("real calculated-metric lifecycle runs only with --env=112")

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    namespace = f"qa-calc-probe-{suffix}"
    aggregate_id: str | None = None
    calculated_id: str | None = None
    deleted_calculated_id: str | None = None
    try:
        aggregate = case_runner.http_api.call(
            "fs_bi_stat.agg_rule.add_new_agg_rule",
            body={
                "schemaId": SCHEMA_ID,
                "schemaObjectName": "object_fwtes__c",
                "displayName": f"{namespace}-aggregate",
                "aggObject": {
                    "refObjName": "object_fwtes__c",
                    "refObjShowName": "区域测试",
                    "refJoinField": "BI_3162840e81468715b0ec6b5aea414582",
                },
                "aggField": {
                    "dbFieldName": "field_shS2y__c",
                    "fieldName": "金额",
                    "fieldType": "Number",
                    "dbObjName": "object_fwtes__c",
                    "fieldId": "BI_d9d45d8381de9e094fe1973acf408d92",
                },
                "aggFieldTime": {
                    "dbFieldName": "field_3913t__c",
                    "fieldName": "日期",
                    "fieldType": "Date",
                    "dbObjName": "object_fwtes__c",
                    "fieldId": "BI_9b4d74a9fd193cc9b75e51db2dc2c67f",
                },
                "filterLists": [],
                "checkFieldAggregateType": 2,
                "initStatus": 1,
                "timeZone": "Asia/Shanghai",
            },
        )
        assert aggregate.status_code == 200
        assert aggregate.body["Result"]["FailureCode"] == 0
        aggregate_id = str(aggregate.body["Value"]["fieldId"])

        calculated = case_runner.http_api.call(
            "fs_bi_stat.stat_calc_field.save_calc_field",
            body={
                "calcFieldId": "",
                "fieldName": f"{namespace}-calculated",
                "formula": f"[{aggregate_id}_2]",
                "formatStr": "0.00",
                "ratioType": 0,
            },
        )
        assert calculated.status_code == 200
        assert calculated.body["Result"]["FailureCode"] == 0
        calculated_id = str(calculated.body["Value"]["fieldID"])
        assert calculated_id.startswith("BI_")

        ready = case_runner.http_api.call(
            "fs_bi_stat.stat_base.get_calc_agg_sub_fields",
            body={"viewId": "", "measureFieldId": calculated_id},
        )
        assert ready.status_code == 200
        assert ready.body["Result"]["FailureCode"] == 0
        assert calculated_id in str(ready.body)

        deleted_calc = case_runner.http_api.call(
            "fs_bi_stat.stat_calc_field.delete_calc_field",
            body={"viewId": "", "calcFieldId": [calculated_id]},
        )
        assert deleted_calc.status_code == 200
        assert deleted_calc.body["Result"]["FailureCode"] == 0
        deleted_calculated_id = calculated_id
        calculated_id = None

        absent = case_runner.http_api.call(
            "fs_bi_stat.stat_base.get_calc_agg_sub_fields",
            body={"viewId": "", "measureFieldId": deleted_calculated_id},
        )
        assert absent.status_code == 200
        assert deleted_calculated_id not in str(absent.body)
        assert f"{namespace}-calculated" not in str(absent.body)
    finally:
        if calculated_id:
            deleted_calc = case_runner.http_api.call(
                "fs_bi_stat.stat_calc_field.delete_calc_field",
                body={"viewId": "", "calcFieldId": [calculated_id]},
            )
            assert deleted_calc.status_code == 200
            assert deleted_calc.body["Result"]["FailureCode"] == 0
        if aggregate_id:
            deleted_aggregate = case_runner.http_api.call(
                "fs_bi_stat.agg_rule.delete_agg_rule",
                body={
                    "schemaId": SCHEMA_ID,
                    "fieldId": aggregate_id,
                    "fieldName": f"{namespace}-aggregate",
                },
            )
            assert deleted_aggregate.status_code == 200
            assert deleted_aggregate.body["Result"]["FailureCode"] == 0

    remaining = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        body={"schemaId": SCHEMA_ID},
    )
    assert remaining.status_code == 200
    assert deleted_calculated_id not in str(remaining.body)
    assert aggregate_id not in str(remaining.body)
    assert namespace not in str(remaining.body)
