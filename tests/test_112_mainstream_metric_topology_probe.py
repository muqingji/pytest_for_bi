from __future__ import annotations

import json

import pytest


SCHEMAS = {
    "account": ("BI_5bcebcdc3060e20001e79977", "AccountObj"),
    "sales_order": ("BI_5be1351956fc11448cdde39e", "SalesOrderObj"),
    "sales_record": ("BI_55479c68f4922c26cbadda8265b2f", "ActiveRecordObj"),
}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def test_mainstream_metric_topologies_are_queryable_in_112(
    environment, case_runner, tmp_path
) -> None:
    if environment.name != "112":
        pytest.skip("mainstream metric topology probe runs only with --env=112")

    evidence = {}
    for subject, (schema_id, describe_api_name) in SCHEMAS.items():
        fields = case_runner.http_api.call(
            "fs_bi_stat.stat_schema.get_fields_by_schema_id", body={"schemaId": schema_id}
        )
        assert fields.status_code == 200
        assert fields.body.get("Result", {}).get("FailureCode") == 0
        metric_ids = []
        for item in _walk(fields.body):
            field_id = item.get("fieldId")
            agg_type = str(item.get("aggDimType", "")).lower()
            if field_id and (agg_type == "agg" or item.get("aggField")):
                metric_ids.append(str(field_id))
        metric_ids = list(dict.fromkeys(metric_ids))[:100]

        topology = case_runner.http_api.call(
            "fs_bi_stat.stat_schema.query_field_topology",
            body={"fieldList": metric_ids, "id": schema_id, "isView": 0, "haveGoalAchieve": 0},
        )
        assert topology.status_code == 200
        assert topology.body.get("Result", {}).get("FailureCode") == 0
        details = case_runner.http_api.call(
            "fs_bi_stat.stat_schema.query_field_detail",
            body={
                "aggDetailInfoList": [
                    {"fieldId": field_id, "objectDescribeApiName": describe_api_name}
                    for field_id in metric_ids
                ],
                "id": schema_id,
                "isView": 0,
                "haveGoalAchieve": 0,
            },
        )
        assert details.status_code == 200
        evidence[subject] = {
            "schema_id": schema_id,
            "metric_ids": metric_ids,
            "topology": topology.body.get("Value"),
            "details": details.body,
        }

    (tmp_path / "mainstream-metric-topologies.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2)
    )
    assert any(item["metric_ids"] for item in evidence.values())
