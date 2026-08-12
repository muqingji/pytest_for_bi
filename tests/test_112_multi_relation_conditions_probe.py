from __future__ import annotations

import json

import pytest


def test_multi_relation_conditions_are_queryable_in_112(
    environment, case_runner, tmp_path
) -> None:
    if environment.name != "112":
        pytest.skip("multi-relation condition probe runs only with --env=112")
    response = case_runner.http_api.call(
        "fs_bi_stat.agg_rule.query_agg_conditions_by_agg_object",
        body={
            "schemaId": "BI_5be1351956fc11448cdde39e",
            "schemaEnName": "biz_sales_order",
            "checkObjectApiName": "object_1Lhg5__c",
            "checkObjectApiNameSlave": "object_1Lhg5__c",
            "refObjName": "object_sW5Pv__c",
            "refJoinField": "BI_5274c1636ee87f0ba68f9aefa9ceb8fb",
            "slaveObject": {
                "refObjName": "object_1Lhg5__c",
                "refObjShowName": "mqj-从对象",
                "refJoinField": "BI_f59e3ce2bacf254c6e05c03eeacd9f85",
                "key": "BI_f59e3ce2bacf254c6e05c03eeacd9f85",
            },
        },
    )
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") == 0
    assert response.body.get("Value")
    (tmp_path / "multi-relation-conditions.json").write_text(
        json.dumps(response.body["Value"], ensure_ascii=False, indent=2)
    )
