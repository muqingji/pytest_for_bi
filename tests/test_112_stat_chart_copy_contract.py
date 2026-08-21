from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time

import pytest

from qa_agents.chart_builder import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
CATEGORY_ID = "BI_6a7c47e1280b910007abf988"
ENTERPRISE_ID = "91863"
OUTPUT = ROOT / "generated/112-stat-chart-copy-contract-evidence.json"


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _value(response):
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") in (None, 0), response.body
    return response.body.get("Value") or {}


def _chart_config(case_runner, view_id):
    return case_runner.http_api.call(
        "fs_bi_stat.stat_edit.get_chart_config",
        body={
            "id": view_id,
            "isView": 1,
            "type": "edit",
            "querySource": "UNKNOWN",
            "cacheTime": 0,
            "refresh": 1,
        },
    )


def _category_items(case_runner):
    return case_runner.http_client.post(
        "/FHH/EM1HBICRM/rptCategoryController/getCategoryAndRpt",
        json_body={
            "categoryID": CATEGORY_ID,
            "keyWord": "",
            "type": 1,
            "listRange": 2,
            "pageNumber": 1,
            "pageSize": 500,
            "showFullPathCategory": 1,
            "timeZone": "Asia/Shanghai",
        },
    )


def _enterprise_id(case_runner):
    response = case_runner.http_api.call("fs_bi_stat.stat_schema.get_all_schema", body={})
    _value(response)
    for item in _walk(response.body):
        for key in ("EnterpriseID", "EnterpriseId", "enterpriseId", "tenantId", "ei"):
            if str(item.get(key, "")):
                return str(item[key])
    return ""


def _source_chart(case_runner, listing):
    candidates = []
    for item in _walk(listing.body):
        candidate = str(item.get("itemID") or item.get("viewID") or item.get("viewId") or "")
        if candidate.startswith("BI_") and candidate != CATEGORY_ID and candidate not in candidates:
            candidates.append(candidate)
    for candidate in sorted(candidates):
        crm = case_runner.http_api.call(
            "fs_bi_crm.stat_edit.get_stat_view", body={"id": candidate}
        )
        if crm.body.get("Result", {}).get("FailureCode") not in (None, 0):
            continue
        crm_value = crm.body.get("Value") or {}
        source_category = str(crm_value.get("categoryID") or crm_value.get("categoryId") or "")
        if source_category != CATEGORY_ID:
            continue
        chart = _chart_config(case_runner, candidate)
        if chart.body.get("Result", {}).get("FailureCode") == 0 and chart.body.get("Value"):
            return candidate, crm, chart
    raise AssertionError(f"no readable statistical chart found in approved category {CATEGORY_ID}")


def _await_readback(case_runner, view_id, attempts=10):
    crm = chart = None
    for _ in range(attempts):
        crm = case_runner.http_api.call(
            "fs_bi_crm.stat_edit.get_stat_view", body={"id": view_id}
        )
        chart = _chart_config(case_runner, view_id)
        if (
            crm.body.get("Result", {}).get("FailureCode") in (None, 0)
            and crm.body.get("Value")
            and chart.body.get("Result", {}).get("FailureCode") == 0
            and chart.body.get("Value")
        ):
            return crm, chart
        time.sleep(1)
    raise AssertionError(
        {"reason": "copied chart did not become readable", "view_id": view_id,
         "crm": crm.body if crm else None, "chart": chart.body if chart else None}
    )


def test_copy_stat_view_retained_contract_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("112 only")
    assert environment.get("test_data.retention_mode") == "retain"
    assert environment.get("test_data.cleanup_required") is False
    assert _enterprise_id(case_runner) == ENTERPRISE_ID

    listing = _category_items(case_runner)
    _value(listing)
    source_view_id, source_crm, source_chart = _source_chart(case_runner, listing)
    request_body = {"statViewBaseInfo": {"viewID": source_view_id, "isChange": 0}}
    copied = case_runner.http_api.call(
        "fs_bi_crm.stat_create.copy_stat_view", body=request_body
    )
    value = _value(copied)
    view_id = str(value.get("viewID") or "")
    assert view_id, {"reason": "Value.viewID is required", "response": copied.body}
    assert view_id != source_view_id

    timestamp = datetime.now(timezone.utc).astimezone()
    view_name = f"qa-copy-contract-{timestamp.strftime('%Y%m%d-%H%M%S')}"
    renamed = case_runner.http_api.call(
        "fs_bi_crm.rpt_view_display.rename_rpt_view",
        body={
            "viewID": view_id,
            "viewName": view_name,
            "description": "统计图复制契约验证；测试数据长期保留",
            "isCategory": 2,
        },
    )
    _value(renamed)

    copied_crm, _ = _await_readback(case_runner, view_id)
    copied_crm_value = _value(copied_crm)
    origin_category_id = str(
        copied_crm_value.get("categoryID") or copied_crm_value.get("categoryId") or ""
    )
    moved = None
    if origin_category_id != CATEGORY_ID:
        moved = case_runner.http_api.call(
            "fs_bi_crm.rpt_view_display.move_rpt_view",
            body={
                "targetCategoryID": CATEGORY_ID,
                "originCategoryID": origin_category_id,
                "viewID": view_id,
                "isCategory": 2,
            },
        )
        _value(moved)

    crm_readback, chart_readback = _await_readback(case_runner, view_id)
    crm_value = _value(crm_readback)
    chart_value = _value(chart_readback)
    assert crm_value.get("viewName") == view_name
    assert str(crm_value.get("categoryID") or crm_value.get("categoryId") or "") == CATEGORY_ID
    assert str(chart_value.get("viewId") or chart_value.get("viewID") or view_id) == view_id

    final_listing = _category_items(case_runner)
    _value(final_listing)
    listed_ids = {
        str(item.get("itemID") or item.get("viewID") or item.get("viewId") or "")
        for item in _walk(final_listing.body)
    }
    assert view_id in listed_ids

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "schema_version": "stat-chart-copy-contract-evidence/1.0",
                "verified_at": timestamp.isoformat(),
                "environment": "112",
                "enterprise_id": ENTERPRISE_ID,
                "operation_id": "fs_bi_crm.stat_create.copy_stat_view",
                "request_body": request_body,
                "required_body_keys": ["statViewBaseInfo"],
                "response_id_path": "Value.viewID",
                "copy_response_hash": canonical_hash(copied.body),
                "copy_response_top_level_keys": sorted(copied.body),
                "resource_id": view_id,
                "display_name": view_name,
                "category_id": CATEGORY_ID,
                "source_view_id": source_view_id,
                "source_crm_hash": canonical_hash(source_crm.body),
                "source_config_hash": canonical_hash(source_chart.body),
                "folder_listing_hash": canonical_hash(listing.body),
                "rename_response_hash": canonical_hash(renamed.body),
                "move_response_hash": canonical_hash(moved.body) if moved else None,
                "crm_readback_hash": canonical_hash(crm_readback.body),
                "chart_readback_hash": canonical_hash(chart_readback.body),
                "final_folder_listing_hash": canonical_hash(final_listing.body),
                "readback_operations": [
                    "fs_bi_crm.stat_edit.get_stat_view",
                    "fs_bi_stat.stat_edit.get_chart_config",
                ],
                "retention_mode": "retain",
                "cleanup_performed": False,
                "readiness": "active",
                "reusable": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
