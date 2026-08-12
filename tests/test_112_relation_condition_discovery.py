from __future__ import annotations

import json

import pytest


SCHEMA_ID = "BI_5be1351956fc11448cdde39e"

RELATIONS = {
    "what_candidate": {
        "refObjName": "base_crmfeedrelation",
        "refObjShowName": "follow-up dynamic",
        "refJoinField": "BI_3373af989a240b0bb7f5fa71f7779cd4",
    },
    "whatlist": {
        "refObjName": "active_record",
        "refObjShowName": "sales record related business data",
        "refJoinField": "BI_6488425a35e05a4983a93ecfd1e39e77",
    },
    "non_dynamic": {
        "refObjName": "biz_refund",
        "refObjShowName": "refund",
        "refJoinField": "BI_0aa9ba25823fd3c0a736c2851da5e87a",
    },
}


@pytest.mark.parametrize("relation_name", RELATIONS)
def test_relation_conditions_are_discoverable_in_112(
    environment, case_runner, tmp_path, relation_name
) -> None:
    if environment.name != "112":
        pytest.skip("relation condition discovery runs only with --env=112")
    relation = RELATIONS[relation_name]
    response = case_runner.http_api.call(
        "fs_bi_stat.agg_rule.query_agg_conditions_by_agg_object",
        body={
            "schemaId": SCHEMA_ID,
            "schemaEnName": "biz_sales_order",
            "checkObjectApiName": relation["refObjName"],
            **relation,
        },
    )
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") == 0
    assert response.body.get("Value")
    (tmp_path / f"{relation_name}-conditions.json").write_text(
        json.dumps(response.body["Value"], ensure_ascii=False, indent=2)
    )
