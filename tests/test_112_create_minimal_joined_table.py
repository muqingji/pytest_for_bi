from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qa_agents.joined_table import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT = "统计图查看明细限制原因提示优化"
VIEW_NAME = "客户销售订单查看明细验证拼表"


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _query_views(case_runner, keyword=""):
    return case_runner.http_client.post(
        "/FHH/EM1HBICRM/rptCategoryController/getCategoryAndRpt",
        json_body={"categoryID": "0", "categoryName": keyword, "keyWord": keyword,
                   "type": 1, "listRange": 2, "pageNumber": 1, "pageSize": 500,
                   "showFullPathCategory": 1, "timeZone": "Asia/Shanghai"},
    )


def _lwt_ids(body):
    values = []
    for item in _walk(body):
        item_id = str(item.get("itemID") or item.get("viewID") or item.get("viewId") or "")
        if item_id.startswith("BI_lwt_") and item_id not in values:
            values.append(item_id)
    return values


def test_create_minimal_joined_table_from_live_readback(environment, case_runner):
    if environment.name != "112":
        pytest.skip("112 only")
    folder = json.loads((ROOT / "generated/112-requirement-folder-evidence.json").read_text())
    assert folder["live_readback_status"] == "succeeded"
    listing = _query_views(case_runner, "拼表")
    assert listing.status_code == 200
    candidates = _lwt_ids(listing.body)
    assert candidates, "no live joined-table candidates returned"

    source_response = source_args = None
    for view_id in candidates:
        response = case_runner.http_api.call(
            "fs_bi_dev.lwt_manager.query_arg_detail", body={"id": view_id, "updateViewTime": 0}
        )
        body = response.body
        lwt = body.get("Value", body).get("lwtArgs", {}) if isinstance(body, dict) else {}
        if (isinstance(lwt.get("dataSources"), list) and len(lwt["dataSources"]) >= 2
                and lwt.get("relations") and lwt.get("displayFields")):
            source_response, source_args = response, body.get("Value", body)
            break
    assert source_args is not None, "no live multi-source joined-table topology is available"

    save_body = json.loads(json.dumps(source_args, ensure_ascii=False))
    save_body.update({"categoryID": folder["category_id"], "viewName": VIEW_NAME,
                      "description": f"需求：{REQUIREMENT}；拓扑来自112实时拼表回查",
                      "saveType": 0, "queryLwtArg": {"id": "", "lwtArgs": None}})
    save_body["lwtArgs"]["lwtId"] = ""
    # Permission ownership is resolved by SaveLwtService from the authenticated current user.
    save_body["userOwnerList"] = []
    for key in ("editableList", "deletableList", "exportableList", "subscribeableList",
                "shareableList", "forwardableList"):
        save_body[key] = None

    existing = _query_views(case_runner, VIEW_NAME)
    assert VIEW_NAME not in json.dumps(existing.body, ensure_ascii=False), "joined table already exists"
    created = case_runner.http_api.call("fs_bi_dev.lwt_manager.save", body=save_body)
    assert created.status_code == 200
    created_body = created.body.get("Value", created.body)
    view_id = str(created_body.get("viewID") or created_body.get("viewId") or "")
    assert view_id.startswith("BI_lwt_")

    readback = case_runner.http_api.call(
        "fs_bi_dev.lwt_manager.query_arg_detail", body={"id": view_id, "updateViewTime": 0}
    )
    assert readback.status_code == 200
    value = readback.body.get("Value", readback.body)
    assert value["viewName"] == VIEW_NAME
    assert value["categoryID"] == folder["category_id"]
    assert len(value["lwtArgs"]["dataSources"]) >= 2
    assert value["lwtArgs"]["relations"] and value["lwtArgs"]["displayFields"]
    evidence = {
        "environment": "112", "requirement_name": REQUIREMENT,
        "resource_type": "joined_table", "display_name": VIEW_NAME,
        "resource_id": view_id, "category_id": folder["category_id"],
        "folder_response_hash": folder["query_response_item_hash"],
        "topology_response_hash": canonical_hash(source_response.body),
        "readback_hash": canonical_hash(readback.body),
        "data_source_count": len(value["lwtArgs"]["dataSources"]),
        "relation_count": len(value["lwtArgs"]["relations"]),
        "display_field_count": len(value["lwtArgs"]["displayFields"]),
        "join_type": value["lwtArgs"].get("joinType"),
        "retention_mode": "retain", "readiness": "active", "reusable": True,
        "credentials_persisted": False,
    }
    (ROOT / "generated/112-joined-table-create-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
