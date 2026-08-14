from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DIMENSION_ID = "BI_02293bb8fb184b56b0502f25cf06e3d5"


def run_retained_custom_dimension_case(case_runner, placement, locale,
                                       combine_result_set_filter=False):
    evidence = json.loads((ROOT / "generated/112-pc001-chart-placement-evidence.json").read_text())
    view_id = evidence["resource_id"]
    chart_response = case_runner.http_api.call(
        "fs_bi_stat.stat_edit.get_chart_config",
        body={"id": view_id, "isView": 1, "type": "edit",
              "querySource": "UNKNOWN", "cacheTime": 0, "refresh": 1},
    )
    chart = chart_response.body.get("Value") or {}
    assert any(str(item.get("fieldId") or item.get("fieldID")) == DIMENSION_ID
               for item in chart.get("dimensionFields", []))
    measure = chart["measureFields"][0]
    field_id = str(measure.get("fieldId") or measure.get("fieldID"))
    request = {
        "id": chart["schemaId"], "isView": 0, "measureFieldID": field_id,
        "measureFieldIDs": [field_id], "pageNumber": 1, "pageSize": 20,
        "filterLists": [], "originalDimensionFields": [], "drillDimValues": [],
        "timeZone": "Asia/Shanghai", "lan": locale,
    }
    custom = {"fieldId": DIMENSION_ID, "fieldID": DIMENSION_ID,
              "fieldName": "retained custom dimension"}
    if placement == "dimension":
        request["originalDimensionFields"] = [custom]
    elif placement == "data_range":
        request["filterLists"] = [{"filters": [{**custom, "operator": 1,
                                                   "value1": "Group A"}]}]
    elif placement == "drill_field":
        request["drillDimValues"] = [{**custom, "value": "Group A"}]
    else:
        raise AssertionError(f"unsupported placement: {placement}")
    if combine_result_set_filter:
        request["filterLists"].append({"filters": [{
            "fieldId": field_id, "fieldID": field_id, "fieldName": "result metric",
            "fieldType": "Number", "operator": 1, "value1": "0",
            "filterConfig": {"filterGroupType": 1,
                             "aggrType": str(measure.get("aggrType") or "0"),
                             "ratioType": str(measure.get("ratioType") or "0")},
        }]})
    detail = case_runner.http_api.call(
        "fs_bi_stat.stat_base.data_query_da655ba1", body=request
    )
    text = str(detail.body)
    assert detail.status_code == 200
    assert "s307011534" in text, text
    if combine_result_set_filter:
        assert "s307011535" not in text
    assert "dataSet" not in text


@pytest.mark.parametrize("placement", ["dimension", "data_range", "drill_field"])
@pytest.mark.parametrize("locale", ["zh-CN", "en"])
def test_pc_001_contract_custom_dimension(environment, case_runner, placement, locale):
    if environment.name != "112":
        pytest.skip("PC-001 contract automation runs only with --env=112")
    run_retained_custom_dimension_case(case_runner, placement, locale)
