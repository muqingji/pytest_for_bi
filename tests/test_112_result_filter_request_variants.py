from __future__ import annotations

import pytest


SCHEMA_ID = "BI_e672ff1046fb773b76bc2b56"
AMOUNT_FIELD_ID = "BI_d9d45d8381de9e094fe1973acf408d92"
COMPARISON_CHART_ID = "BI_6a7c47e808bc2c00077317be"


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


@pytest.mark.parametrize(
    ("variant", "locale", "field_name"),
    [
        ("ordinary", "zh-CN", "收入"),
        ("ordinary", "en", "Revenue"),
        ("comparison", "zh-CN", "订单产品同比环比"),
        ("comparison", "en", "Order Product Comparison"),
    ],
)
def test_result_filter_request_variants_in_112(
    environment, case_runner, variant, locale, field_name
) -> None:
    if environment.name != "112":
        pytest.skip("real result-filter request variants run only with --env=112")
    schema_id, field_id, aggr_type, ratio_type = _saved_measure(case_runner, variant)
    response = case_runner.http_api.call(
        "fs_bi_stat.stat_base.data_query_da655ba1",
        body={
            "id": schema_id,
            "isView": 0,
            "measureFieldID": field_id,
            "measureFieldIDs": [field_id],
            "pageNumber": 1,
            "pageSize": 20,
            "filterLists": [{"filters": [{
                "displayNumber": 1,
                "fieldId": field_id,
                "fieldID": field_id,
                "fieldName": field_name,
                "fieldType": "Number",
                "operator": 1,
                "operatorLabel": "equals",
                "value1": "0",
                "value2": "",
                "aggDimType": "base_agg",
                "filterConfig": {
                    "showAppointLevelSwitch": 0,
                    "switchStatus": 0,
                    "filterGroupType": 1,
                    "aggrType": aggr_type,
                    "ratioType": ratio_type,
                },
            }]}],
            "timeZone": "Asia/Shanghai",
            "lan": locale,
        },
    )
    assert response.status_code == 200
    body = str(response.body)
    assert "s307011535" in body
    assert field_name in body, f"{variant}/{locale} did not preserve the metric name"
