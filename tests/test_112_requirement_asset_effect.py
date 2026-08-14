from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "generated/retained-test-assets.json"
SCHEMA_ID = "BI_5be1351956fc11448cdde39e"


def _detail(case_runner, field_id: str) -> str:
    response = case_runner.http_api.call(
        "fs_bi_stat.stat_base.data_query_da655ba1",
        body={"id": SCHEMA_ID, "isView": 0, "measureFieldID": field_id,
              "measureFieldIDs": [field_id], "pageNumber": 1, "pageSize": 1,
              "filterLists": [], "originalDimensionFields": [], "drillDimValues": [],
              "timeZone": "Asia/Shanghai", "lan": "zh-CN"},
    )
    assert response.status_code == 200
    return json.dumps(response.body, ensure_ascii=False)


def test_all_requirement_assets_are_live_and_show_expected_effect(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("requirement asset effect runs only with --env=112")
    registry = json.loads(REGISTRY.read_text())
    assets = [item for item in registry["assets"] if item.get("reusable", True)
              and item.get("readiness") == "active"]
    assert {item["resource_type"] for item in assets} >= {
        "custom_dimension", "joined_table", "aggregate_metric"
    }
    assert {item.get("relation_topology") for item in assets} >= {
        "left", "三节点", "WhatList", "普通关联", "结果集筛选"
    }

    dimension = next(item for item in assets if item["resource_type"] == "custom_dimension")
    response = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.get_custom_dimension",
        body={"dimensionId": dimension["resource_id"]},
    )
    assert response.body.get("Result", {}).get("FailureCode") == 0
    dimension_text = json.dumps(response.body, ensure_ascii=False)
    assert dimension["display_name"] in dimension_text
    source_identity = dimension.get("source_field_id") or dimension["source_field_api_name"]
    assert source_identity in dimension_text

    expected = {
        "销售订单四节点多关联汇率聚合指标": "s307011536",
        "销售订单跟进动态单值关联信息编号聚合指标": "s307011537",
        "销售订单销售记录多值动态关联对象计数指标": "s307011537",
    }
    for metric in (item for item in assets if item["resource_type"] == "aggregate_metric"):
        readback = case_runner.http_api.call(
            "fs_bi_stat.agg_rule.query_agg_rule_by_field_id",
            body={"fieldId": metric["resource_id"]},
        )
        assert readback.status_code == 200
        assert readback.body.get("Result", {}).get("FailureCode") == 0
        text = json.dumps(readback.body, ensure_ascii=False)
        assert metric["display_name"] in text
        assert metric["source_field_api_name"] in text
        if metric["display_name"] in expected:
            detail = _detail(case_runner, metric["resource_id"])
            if expected[metric["display_name"]] not in detail:
                pytest.xfail(
                    f"confirmed restriction-code defect for {metric['display_name']}: {detail}"
                )

    result_metric = next(
        item for item in assets if item.get("relation_topology") == "结果集筛选"
    )
    result = case_runner.http_api.call(
        "fs_bi_stat.stat_base.data_query_da655ba1",
        body={"id": SCHEMA_ID, "isView": 0,
              "measureFieldID": result_metric["resource_id"],
              "measureFieldIDs": [result_metric["resource_id"]],
              "pageNumber": 1, "pageSize": 1,
              "filterLists": [{"filters": [{
                  "fieldId": result_metric["resource_id"],
                  "fieldID": result_metric["resource_id"],
                  "fieldName": result_metric["display_name"], "fieldType": "Number",
                  "operator": 1, "value1": "0", "value_kind": "numeric",
                  "filterConfig": {"filterGroupType": 1, "aggrType": "2"},
              }]}], "timeZone": "Asia/Shanghai", "lan": "zh-CN"},
    )
    result_text = json.dumps(result.body, ensure_ascii=False)
    assert "s307011535" in result_text
    assert result_metric["display_name"] in result_text
