from __future__ import annotations

import pytest


SCHEMA_ID = "BI_e672ff1046fb773b76bc2b56"
AMOUNT_FIELD_ID = "BI_d9d45d8381de9e094fe1973acf408d92"


@pytest.mark.parametrize(
    ("variant", "locale", "field_name", "ratio_type"),
    [
        ("ordinary", "zh-CN", "收入", "0"),
        ("ordinary", "en", "Revenue", "0"),
        ("comparison", "zh-CN", "收入同比", "1"),
        ("comparison", "en", "Revenue YoY", "1"),
    ],
)
def test_result_filter_request_variants_in_112(
    environment, case_runner, variant, locale, field_name, ratio_type
) -> None:
    if environment.name != "112":
        pytest.skip("real result-filter request variants run only with --env=112")
    response = case_runner.http_api.call(
        "fs_bi_stat.stat_base.data_query_da655ba1",
        body={
            "id": SCHEMA_ID,
            "isView": 0,
            "measureFieldID": AMOUNT_FIELD_ID,
            "measureFieldIDs": [AMOUNT_FIELD_ID],
            "pageNumber": 1,
            "pageSize": 20,
            "filterLists": [{"filters": [{
                "displayNumber": 1,
                "fieldId": AMOUNT_FIELD_ID,
                "fieldID": AMOUNT_FIELD_ID,
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
                    "aggrType": "2",
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
