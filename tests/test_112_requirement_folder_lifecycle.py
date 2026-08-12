from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


REQUIREMENT = "统计图查看明细限制原因提示优化"


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _query(case_runner):
    return case_runner.http_client.post(
        "/FHH/EM1HBICRM/rptCategoryController/getCategoryAndRpt",
        json_body={"categoryID": "0", "categoryName": REQUIREMENT,
                   "keyWord": REQUIREMENT, "type": 1, "listRange": 2,
                   "pageNumber": 1, "pageSize": 100, "showFullPathCategory": 1,
                   "timeZone": "Asia/Shanghai"},
    )


def test_resolve_or_create_requirement_folder(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("112 only")
    queried = _query(case_runner)
    assert queried.status_code == 200
    matches = [item for item in _walk(queried.body)
               if str(item.get("itemName") or item.get("categoryName") or "") == REQUIREMENT
               and int(item.get("itemType", 1)) == 1]
    if not matches:
        created = case_runner.http_client.post(
            "/FHH/EM1HBICRM/rptCategoryController/saveCategory",
            json_body={"categoryID": "", "categoryName": REQUIREMENT,
                       "description": "需求测试数据专用目录", "isEdit": 2,
                       "originCategoryName": "", "parentID": "0"},
        )
        assert created.status_code == 200
        created_text = json.dumps(created.body, ensure_ascii=False)
        assert "categoryID" in created_text
        queried = _query(case_runner)
        matches = [item for item in _walk(queried.body)
                   if str(item.get("itemName") or item.get("categoryName") or "") == REQUIREMENT
                   and int(item.get("itemType", 1)) == 1]
    assert len(matches) == 1
    category_id = str(matches[0].get("categoryID") or matches[0].get("categoryId")
                      or matches[0].get("itemID") or "")
    assert category_id
    digest = hashlib.sha256(
        json.dumps(matches[0], ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode()
    ).hexdigest()
    assert len(digest) == 64
    evidence = Path(__file__).resolve().parents[1] / "generated/112-requirement-folder-evidence.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps({
        "environment": "112",
        "requirement_name": REQUIREMENT,
        "category_id": category_id,
        "query_operation": "bi_crm_report.rpt_category.get_category_and_rpt",
        "query_response_item_hash": "sha256:" + digest,
        "live_readback_status": "succeeded",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
