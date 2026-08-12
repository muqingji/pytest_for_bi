from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

from qa_agents.chart_builder import canonical_hash, compile_chart_clone_resource
from qa_agents.test_data import validate_test_data_plan


REQUIREMENT = "统计图查看明细限制原因提示优化"
VIEW_NAME = "客户指标完整配置查看明细验证统计图"
ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "generated/112-minimal-stat-chart-evidence.json"


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first_runtime_value(value, keys):
    for item in _walk(value):
        for key in keys:
            if str(item.get(key, "")):
                return str(item[key])
    return ""


def _folder_query(case_runner):
    return case_runner.http_client.post(
        "/FHH/EM1HBICRM/rptCategoryController/getCategoryAndRpt",
        json_body={"categoryID": "0", "categoryName": REQUIREMENT, "keyWord": REQUIREMENT,
                   "type": 1, "listRange": 2, "pageNumber": 1, "pageSize": 100,
                   "showFullPathCategory": 1, "timeZone": "Asia/Shanghai"},
    )


def _all_chart_query(case_runner):
    return case_runner.http_client.post(
        "/FHH/EM1HBICRM/rptCategoryController/getCategoryAndRpt",
        json_body={"categoryID": "0", "keyWord": "", "type": 1, "listRange": 2,
                   "pageNumber": 1, "pageSize": 500, "showFullPathCategory": 1,
                   "timeZone": "Asia/Shanghai"},
    )


def _category_items_query(case_runner, category_id):
    return case_runner.http_client.post(
        "/FHH/EM1HBICRM/rptCategoryController/getCategoryAndRpt",
        json_body={"categoryID": category_id, "keyWord": "", "type": 1, "listRange": 2,
                   "pageNumber": 1, "pageSize": 100, "showFullPathCategory": 1,
                   "timeZone": "Asia/Shanghai"},
    )


def _readback(case_runner, view_id):
    return case_runner.http_api.call(
        "fs_bi_stat.stat_edit.get_chart_config",
        body={"id": view_id, "isView": 1, "type": "edit", "querySource": "UNKNOWN",
              "cacheTime": 0, "refresh": 1})


def _crm_readback(case_runner, view_id):
    return case_runner.http_api.call(
        "fs_bi_crm.stat_edit.get_stat_view",
        body={"id": view_id},
    )


def _await_readback(case_runner, view_id, attempts=10):
    response = None
    for _ in range(attempts):
        response = _readback(case_runner, view_id)
        if response.body.get("Result", {}).get("FailureCode") == 0:
            return response
        time.sleep(1)
    return response


def _discover_chart_measure(case_runner, schema_id):
    listing = _all_chart_query(case_runner)
    for item in _walk(listing.body):
        candidate_id = str(item.get("itemID") or item.get("viewID") or item.get("viewId") or "")
        if not candidate_id.startswith("BI_") or candidate_id.startswith("BI_lwt"):
            continue
        response = _readback(case_runner, candidate_id)
        value = response.body.get("Value") or {}
        if value.get("schemaId") == schema_id and value.get("measureFields"):
            return candidate_id, dict(value["measureFields"][0]), value, response.body
    raise AssertionError("no live readable chart measure found for current schema")


def test_create_or_reuse_minimal_stat_chart_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("112 only")
    folders = _folder_query(case_runner)
    matches = [item for item in _walk(folders.body)
               if str(item.get("itemName") or item.get("categoryName") or "") == REQUIREMENT
               and int(item.get("itemType", 1)) == 1]
    assert len(matches) == 1
    folder = matches[0]
    category_id = str(folder.get("categoryID") or folder.get("categoryId") or folder.get("itemID") or "")
    assert category_id

    schemas = case_runner.http_api.call("fs_bi_stat.stat_schema.get_all_schema", body={})
    current_user_id = str(schemas.body.get("Result", {}).get("UserInfo", {}).get("EmployeeID", ""))
    enterprise_id = _first_runtime_value(
        schemas.body, ("EnterpriseID", "EnterpriseId", "enterpriseId", "tenantId", "ei")
    )
    assert current_user_id
    assert enterprise_id
    account_schema = next(item for item in _walk(schemas.body)
                          if str(item.get("schemaCnName", "")) == "客户"
                          and (item.get("schemaId") or item.get("id") or item.get("topologyDescribeId")))
    schema_id = str(account_schema.get("schemaId") or account_schema.get("id") or account_schema.get("topologyDescribeId"))
    fields = case_runner.http_api.call("fs_bi_stat.stat_schema.get_fields_by_schema_id",
                                       body={"schemaId": schema_id})
    source_view_id, measure_dto, reference_base, reference_body = _discover_chart_measure(case_runner, schema_id)
    resource = compile_chart_clone_resource(
        requirement_name=REQUIREMENT, view_name=VIEW_NAME,
        namespace="qa-minimal-stat-chart-20260812", category_id=category_id,
        folder_query_operation="fs_bi_crm.rpt_category.get_category_and_rpt",
        folder_response_hash=canonical_hash(folder), source_view_id=source_view_id,
        source_config_hash=canonical_hash(reference_body),
    )
    policy = json.loads((ROOT / "qa-agents/policies/test-data-policy.json").read_text())
    plan = {"schema_version": "test-data-plan/1.0", "environment": "112",
            "namespace": "qa-minimal-stat-chart-20260812", "case_plans": [{
                "case_id": "MINIMAL-STAT-CHART", "requirement_name": REQUIREMENT,
                "resources": [resource]}]}
    assert validate_test_data_plan(plan, policy)["write_authorized"] is True
    measure_id = str(measure_dto.get("fieldId") or measure_dto["fieldID"])

    refreshed_folders = _category_items_query(case_runner, category_id)
    existing = [item for item in _walk(refreshed_folders.body)
                if str(item.get("itemName") or item.get("viewName") or "") == VIEW_NAME]
    view_id = ""
    readback = None
    for candidate in existing:
        candidate_id = str(candidate.get("itemID") or candidate.get("viewID") or candidate.get("viewId") or "")
        if not candidate_id:
            continue
        candidate_readback = _await_readback(case_runner, candidate_id, attempts=3)
        candidate_text = json.dumps(candidate_readback.body, ensure_ascii=False)
        candidate_value = candidate_readback.body.get("Value") or {}
        if (candidate_readback.body.get("Result", {}).get("FailureCode") == 0
                and candidate_value.get("schemaId") == schema_id
                and candidate_value.get("measureFields")):
            view_id, readback = candidate_id, candidate_readback
            break
    if not view_id:
        created = case_runner.http_api.call(
            resource["setup"]["request"]["api"],
            body=resource["setup"]["request"]["json"],
        )
        assert created.status_code == 200
        failure_code = created.body.get("Result", {}).get("FailureCode")
        assert failure_code in (None, 0), created.body
        value = created.body.get("Value") or created.body.get("value") or created.body
        view_id = str(value.get("viewID") or value.get("ViewID") or "")
        if not view_id:
            pytest.fail({"reason": "create returned no viewID; exact-name candidate exists or save was rejected",
                         "response": created.body})
        for operation in resource["post_setup"]:
            body = json.loads(json.dumps(operation["request"]["json"]).replace(
                "{{ chart_view_id }}", view_id
            ))
            changed = case_runner.http_api.call(operation["request"]["api"], body=body)
            assert changed.body.get("Result", {}).get("FailureCode") == 0, changed.body
    assert view_id
    if readback is None:
        readback = _await_readback(case_runner, view_id)
    if readback.body.get("Result", {}).get("FailureCode") == 701:
        cleared = case_runner.http_client.get(
            f"/FHH/EM1HBISTAT/fs-bi-stat/api/v1/stat/clearCache/{enterprise_id}/{view_id}"
        )
        assert cleared.status_code == 200
        readback = _await_readback(case_runner, view_id, attempts=5)
    assert readback.status_code == 200
    text = json.dumps(readback.body, ensure_ascii=False)
    readback_value = readback.body.get("Value") or {}
    assert (readback_value.get("viewName") == VIEW_NAME
            and readback_value.get("schemaId") == schema_id
            and readback_value.get("measureFields")), {"view_id": view_id, "body": readback.body}
    crm_readback = _crm_readback(case_runner, view_id)
    assert crm_readback.status_code == 200
    assert VIEW_NAME in json.dumps(crm_readback.body, ensure_ascii=False), crm_readback.body
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps({
        "requirement_name": REQUIREMENT, "resource_type": "stat_chart",
        "display_name": VIEW_NAME, "resource_id": view_id, "category_id": category_id,
        "folder_response_hash": canonical_hash(folder), "schema_id": schema_id,
        "measure_field_id": (readback_value["measureFields"][0].get("fieldId")
                             or readback_value["measureFields"][0].get("fieldID")),
        "measure_source_response_hash": canonical_hash(reference_body),
        "source_view_id": source_view_id,
        "configuration_hash": resource["configuration_hash"],
        "readback_hash": canonical_hash(readback.body), "retention_mode": "retain",
        "readiness": "active", "reusable": True,
    }, ensure_ascii=False, indent=2) + "\n")
