from __future__ import annotations

import pytest


SCHEMAS = (
    "BI_5bcebcdc3060e20001e79977",
    "BI_5be1351956fc11448cdde39e",
    "BI_55479c68f4922c26cbadda8265b2f",
)


def _qa_items(value):
    if isinstance(value, dict):
        if any(
            str(value.get(key, "")).lower().startswith("qa-")
            for key in ("dimensionName", "displayName", "fieldName", "name")
        ):
            yield value
        for nested in value.values():
            yield from _qa_items(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _qa_items(nested)


def test_no_active_qa_namespace_resources_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("QA namespace residue audit runs only with --env=112")
    residue = []
    dimensions = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.find_custom_dimensions",
        body={"keyWord": "qa-", "timeZone": "Asia/Shanghai"},
    )
    assert dimensions.status_code == 200
    residue.extend(_qa_items(dimensions.body))
    for schema_id in SCHEMAS:
        metrics = case_runner.http_api.call(
            "fs_bi_stat.agg_rule.query_agg_rule_list",
            body={
                "schemaId": schema_id,
                "keyWord": "qa-",
                "pageNumber": 1,
                "pageSize": 1000,
                "timeZone": "Asia/Shanghai",
            },
        )
        assert metrics.status_code == 200
        residue.extend(_qa_items(metrics.body))
    assert not residue, [
        {
            key: item.get(key)
            for key in ("dimensionId", "fieldId", "dimensionName", "displayName", "fieldName")
        }
        for item in residue
    ]
