from __future__ import annotations

import json

import pytest


def test_sales_order_agg_object_tree_is_queryable_in_112(
    environment, case_runner, tmp_path
) -> None:
    if environment.name != "112":
        pytest.skip("sales-order aggregate object probe runs only with --env=112")
    response = case_runner.http_api.call(
        "fs_bi_stat.agg_rule.query_agg_object_list_by_schema_object_name",
        body={
            "schemaId": "BI_5be1351956fc11448cdde39e",
            "schemaEnName": "biz_sales_order",
        },
    )
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") == 0
    value = response.body.get("Value")
    assert value
    (tmp_path / "sales-order-agg-objects.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2)
    )
