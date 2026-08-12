from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from qa_agents.asset_discovery import discover_catalog
from qa_agents.chart_builder import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
SOURCE_VIEW_ID = "BI_6a7c6421280b910007abfe94"
CATEGORY_ID = "BI_6a7c5dea280b910007abfd5d"
DIMENSION_ID = "BI_02293bb8fb184b56b0502f25cf06e3d5"
OUTPUT = ROOT / "generated/112-pc001-chart-placement-evidence.json"


def _value(response):
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") in (None, 0), response.body
    return response.body.get("Value") or {}


def _chart(case_runner, view_id):
    return case_runner.http_api.call("fs_bi_stat.stat_edit.get_chart_config", body={
        "id": view_id, "isView": 1, "type": "edit", "querySource": "UNKNOWN",
        "cacheTime": 0, "refresh": 1,
    })


def _copy(case_runner, name):
    def query(category, page, size):
        return case_runner.http_client.post(
            "/FHH/EM1HBICRM/rptCategoryController/getCategoryAndRpt",
            json_body={"categoryID": category, "keyWord": "", "type": 1,
                       "listRange": 2, "pageNumber": page, "pageSize": size,
                       "showFullPathCategory": 1, "timeZone": "Asia/Shanghai"},
        ).body
    for current in discover_catalog(query):
        if str(current.get("itemName") or current.get("viewName") or "") != name:
            continue
        candidate = str(current.get("itemID") or current.get("viewID") or "")
        if candidate and _chart(case_runner, candidate).body.get("Result", {}).get("FailureCode") == 0:
            _value(case_runner.http_api.call("fs_bi_crm.rpt_view_display.move_rpt_view", body={
                "targetCategoryID": CATEGORY_ID, "viewID": candidate, "isCategory": 2,
            }))
            return candidate
    response = case_runner.http_api.call("fs_bi_crm.stat_create.copy_stat_view", body={
        "statViewBaseInfo": {"viewID": SOURCE_VIEW_ID, "isChange": 0},
    })
    value = _value(response)
    view_id = str(value.get("viewID") or value.get("ViewID"))
    assert view_id
    name = f"{datetime.now(timezone.utc).strftime('%m%d%H%M%S%f')}-客户自定义维度轴图"
    for operation, body in [
        ("fs_bi_crm.rpt_view_display.rename_rpt_view", {
            "viewID": view_id, "viewName": name,
            "description": "需求：统计图查看明细限制原因提示优化", "isCategory": 2,
        }),
        ("fs_bi_crm.rpt_view_display.move_rpt_view", {
            "targetCategoryID": CATEGORY_ID, "viewID": view_id, "isCategory": 2,
        }),
    ]:
        changed = case_runner.http_api.call(operation, body=body)
        assert changed.body.get("Result", {}).get("FailureCode") in (None, 0), {
            "operation": operation, "body": body, "response": changed.body,
        }
    return view_id, name


def _custom_field(case_runner):
    response = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        body={"schemaId": "BI_5bcebcdc3060e20001e79977"},
    )
    _value(response)
    stack = [response.body]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if str(current.get("fieldId")) == DIMENSION_ID:
                return copy.deepcopy(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    raise AssertionError("live custom dimension field DTO is unavailable")


def _update_body(case_runner, view_id, custom_field):
    chart = _value(_chart(case_runner, view_id))
    crm = _value(case_runner.http_api.call("fs_bi_crm.stat_edit.get_stat_view", body={"id": view_id}))
    filters = _value(case_runner.http_api.call(
        "fs_bi_stat.stat_edit.get_filters_result", body={"id": view_id, "isView": 1}
    ))
    base = copy.deepcopy(crm)
    base.update({
        "viewID": view_id, "schemaID": chart["schemaId"], "chartUserDefined": chart["userDefined"],
        "templateID": chart.get("templateId", ""), "topNum": chart.get("topNum", 0),
        "isShowDimension": chart.get("isShowDimension", 0), "timeZone": chart.get("timeZone"),
        "ratioDateFieldId": chart.get("ratioDateFieldId"), "authType": chart.get("authType"),
    })
    axis = {
        "chartType": chart["chartType"], "dimensionFields": [custom_field],
        "measureFieldList": chart["measureFields"],
        "dimensionAttrFields": chart.get("dimensionAttrFields") or [],
        "schemaId": chart["schemaId"], "topNum": chart.get("topNum", 0),
        "isShowDimension": chart.get("isShowDimension", 0),
    }
    return {
        "axisData": axis, "filterLists": filters.get("filterLists") or [],
        "secondaryFilterLists": filters.get("secondaryFilterLists") or [],
        "defaultFilterOptionIDs": [], "statLayoutInfo": chart["layout"],
        "statMobileLayoutInfo": chart.get("mobileLayout"), "statViewBaseInfo": base,
        "drillRouteFieldLists": [], "drillDownPath": chart.get("drillDownPath", "-1"),
    }


def test_create_pc001_dimension_chart_in_112(environment, case_runner):
    if environment.name != "112":
        pytest.skip("112 only")
    name = "客户自定义维度轴查看明细验证统计图"
    custom_field = _custom_field(case_runner)
    copied = _copy(case_runner, name)
    if isinstance(copied, tuple):
        view_id, name = copied
    else:
        view_id = copied
    body = _update_body(case_runner, view_id, custom_field)
    updated = case_runner.http_client.post(
        "/FHH/EM1HBICRM/statEditController/updateStatView", json_body=body,
    )
    assert updated.status_code == 200
    assert updated.body.get("Result", {}).get("FailureCode") in (None, 0), updated.body
    chart_response = _chart(case_runner, view_id)
    chart = _value(chart_response)
    assert chart.get("dimensionFields")
    assert str(chart["dimensionFields"][0].get("fieldId")) == DIMENSION_ID, chart["dimensionFields"]
    crm = case_runner.http_api.call("fs_bi_crm.stat_edit.get_stat_view", body={"id": view_id})
    _value(crm)
    OUTPUT.write_text(json.dumps({
        "case_id": "PC-001", "placement": "dimension", "resource_id": view_id,
        "display_name": name, "category_id": CATEGORY_ID, "custom_dimension_id": DIMENSION_ID,
        "source_field_response_hash": canonical_hash(custom_field),
        "update_request_hash": canonical_hash(body), "readback_hash": canonical_hash(chart_response.body),
        "crm_readback_hash": canonical_hash(crm.body), "readiness": "active", "reusable": True,
    }, ensure_ascii=False, indent=2) + "\n")
