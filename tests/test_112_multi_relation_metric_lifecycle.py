from __future__ import annotations

from datetime import datetime, timezone

import pytest


SCHEMA_ID = "BI_5be1351956fc11448cdde39e"


@pytest.mark.parametrize(("scenario", "expect_code"), [
    ("three_node", None),
    pytest.param(
        "four_node", "s307011536",
        marks=pytest.mark.xfail(
            strict=True,
            reason="confirmed PC-003: 112 returns s307050002 instead of s307011536",
        ),
    ),
])
def test_master_detail_metric_lifecycle_in_112(environment, case_runner, scenario, expect_code) -> None:
    if environment.name != "112":
        pytest.skip("multi-relation metric lifecycle runs only with --env=112")
    namespace = "qa-mr-base-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    field_id = None
    try:
        created = case_runner.http_api.call(
            "fs_bi_stat.agg_rule.add_new_agg_rule",
            body={
                "schemaId": SCHEMA_ID,
                "schemaObjectName": "biz_sales_order",
                "displayName": namespace,
                "aggObject": {
                    "refObjName": "object_sW5Pv__c",
                    "refObjShowName": "mqj-主对象",
                    "refJoinField": "BI_5274c1636ee87f0ba68f9aefa9ceb8fb",
                    "slaveObject": {
                        "refObjName": "object_1Lhg5__c",
                        "refObjShowName": "mqj-从对象",
                        "refJoinField": "BI_f59e3ce2bacf254c6e05c03eeacd9f85",
                        "key": "BI_f59e3ce2bacf254c6e05c03eeacd9f85",
                    },
                },
                "aggField": {
                    "dbFieldName": "mc_exchange_rate",
                    "fieldName": "exchange rate",
                    "fieldType": "Number",
                    "dbObjName": "object_1Lhg5__c",
                    "fieldId": "BI_a23fbc479ea07edab8c7fd5fddf90cc7",
                },
                "aggFieldTime": {
                    "dbFieldName": "create_time",
                    "fieldName": "created at",
                    "fieldType": "Date",
                    "dbObjName": "object_1Lhg5__c",
                    "fieldId": "BI_f6b5bbe13117f9e4e2f96790b31115a9",
                },
                "filterLists": [] if scenario == "three_node" else [{"filters": [{
                    "displayNumber": 1,
                    "fieldId": "BI_30a76bf349ea4cb58d7396e63622f074",
                    "fieldID": "BI_30a76bf349ea4cb58d7396e63622f074",
                    "dbFieldName": "owner",
                    "dbObjName": "object_1Lhg5__c",
                    "fieldName": "owner",
                    "fieldType": "Number",
                    "type": "employee",
                    "refObjName": "org_employee_user",
                    "operator": 22,
                    "operatorLabel": "not empty",
                    "value1": "",
                }]}],
                "checkFieldAggregateType": 2,
                "initStatus": 1,
                "timeZone": "Asia/Shanghai",
            },
        )
        assert created.status_code == 200
        assert created.body.get("Result", {}).get("FailureCode") == 0
        field_id = str(created.body["Value"]["fieldId"])
        assert field_id
        topology = case_runner.http_api.call(
            "fs_bi_stat.stat_schema.query_field_topology",
            body={"fieldList": [field_id], "id": SCHEMA_ID, "isView": 0, "haveGoalAchieve": 0},
        )
        assert topology.status_code == 200
        detail = case_runner.http_api.call(
            "fs_bi_stat.stat_base.data_query_da655ba1",
            body={
                "id": SCHEMA_ID,
                "isView": 0,
                "measureFieldID": field_id,
                "measureFieldIDs": [field_id],
                "pageNumber": 1,
                "pageSize": 1,
                "filterLists": [],
                "originalDimensionFields": [],
                "drillDimValues": [],
                "timeZone": "Asia/Shanghai",
                "lan": "zh-CN",
            },
        )
        detail_text = str(detail.body)
        if expect_code:
            assert expect_code in detail_text, detail_text
            assert "dataSet" not in detail_text
        else:
            assert "s307011536" not in detail_text
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
