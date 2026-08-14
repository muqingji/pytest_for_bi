from __future__ import annotations

import json
from pathlib import Path

import pytest

SCHEMA_ID = "BI_e672ff1046fb773b76bc2b56"
AMOUNT_FIELD_ID = "BI_d9d45d8381de9e094fe1973acf408d92"
COMPARISON_CHART_ID = "BI_6a7c47e808bc2c00077317be"
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("variant", "locale", "field_name"),
    [
        ("ordinary", "zh-CN", "收入"),
        ("ordinary", "en", "Revenue"),
        ("comparison", "zh-CN", "订单产品同比环比"),
        ("comparison", "en", "Order Product Comparison"),
    ],
)
def test_pc_002_contract_read_only_variants(
    environment, case_runner, variant, locale, field_name
) -> None:
    if environment.name != "112":
        pytest.skip("PC-002 contract automation runs only with --env=112")
    schema_id, field_id, aggr_type, ratio_type = _saved_measure(case_runner, variant)
    fields = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id", body={"schemaId": schema_id}
    )
    assert fields.status_code == 200
    assert field_id in str(fields.body)
    _assert_detail_error(case_runner, schema_id, field_id, field_name, locale,
                         aggr_type, ratio_type)


@pytest.mark.parametrize(
    ("variant", "locale", "field_name", "case_id"),
    [
        ("aggregate", "zh-CN", "成交额", "CASE-AUTO-RESULT-FILTER-DETAIL-112"),
        ("aggregate", "en", "Deal Amount", "CASE-AUTO-RESULT-FILTER-DETAIL-112"),
        ("calculated", "zh-CN", "利润率", "CASE-AUTO-CALCULATED-RESULT-FILTER-112"),
        ("calculated", "en", "Profit Margin", "CASE-AUTO-CALCULATED-RESULT-FILTER-112"),
    ],
)
def test_pc_002_contract_managed_variants(
    environment, case_runner, variant, locale, field_name, case_id
) -> None:
    if environment.name != "112":
        pytest.skip("PC-002 contract automation runs only with --env=112")
    del case_id
    inventory = json.loads((ROOT / "generated/112-case-asset-inventory.json").read_text())
    asset, record = next(
        (asset, metric)
        for asset in inventory["result_set_filter_assets"]
        for metric in asset["matched_metrics"]
        if metric["source_metric_type"] == variant
    )
    schema_id = asset["schema_id"]
    fields = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id", body={"schemaId": schema_id}
    )
    assert record["field_id"] in str(fields.body), record
    measure = _chart_measure(case_runner, asset["resource_id"], record["field_id"])
    _assert_detail_error(case_runner, schema_id, record["field_id"], field_name,
                         locale, str(measure.get("aggrType") or "0"),
                         str(measure.get("ratioType") or "0"))


def _saved_measure(case_runner, variant):
    if variant == "ordinary":
        return SCHEMA_ID, AMOUNT_FIELD_ID, "2", "0"
    response = case_runner.http_api.call(
        "fs_bi_stat.stat_edit.get_chart_config",
        body={"id": COMPARISON_CHART_ID, "isView": 1, "type": "edit",
              "querySource": "UNKNOWN", "cacheTime": 0, "refresh": 1},
    )
    value = response.body.get("Value") or {}
    measure = next(item for item in value.get("measureFields", [])
                   if str(item.get("ratioType") or "0") != "0")
    return (str(value["schemaId"]), str(measure.get("fieldId") or measure["fieldID"]),
            str(measure["aggrType"]), str(measure["ratioType"]))


def _chart_measure(case_runner, view_id, field_id):
    response = case_runner.http_api.call(
        "fs_bi_stat.stat_edit.get_chart_config",
        body={"id": view_id, "isView": 1, "type": "edit",
              "querySource": "UNKNOWN", "cacheTime": 0, "refresh": 1},
    )
    value = response.body.get("Value") or {}
    return next(item for item in value.get("measureFields", [])
                if str(item.get("fieldId") or item.get("fieldID")) == field_id)


def _assert_detail_error(case_runner, schema_id, field_id, field_name, locale,
                         aggr_type, ratio_type) -> None:
    response = case_runner.http_api.call(
        "fs_bi_stat.stat_base.data_query_da655ba1",
        body={
            "id": schema_id, "isView": 0, "measureFieldID": field_id,
            "measureFieldIDs": [field_id], "pageNumber": 1, "pageSize": 20,
            "filterLists": [{"filters": [{
                "displayNumber": 1, "fieldId": field_id, "fieldID": field_id,
                "fieldName": field_name, "fieldType": "Number", "operator": 1,
                "operatorLabel": "equals", "value1": "0", "value2": "",
                "aggDimType": "base_agg", "filterConfig": {
                    "showAppointLevelSwitch": 0, "switchStatus": 0,
                    "filterGroupType": 1, "aggrType": aggr_type, "ratioType": ratio_type,
                },
            }]}], "timeZone": "Asia/Shanghai", "lan": locale,
        },
    )
    assert response.status_code == 200
    body = str(response.body)
    assert "s307011535" in body
    assert field_name in body
    assert "dataSet" not in body or "s307011535" in body
