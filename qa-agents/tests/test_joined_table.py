from __future__ import annotations

import pytest
import json
from pathlib import Path

from qa_agents.joined_table import canonical_hash, compile_joined_table_save_args
from qa_agents.errors import SecurityPolicyError
from qa_agents.test_data import validate_test_data_plan


def _discovery():
    return {
        "folder": {"id": "folder-live", "name": "统计图查看明细限制原因提示优化",
                   "response_hash": "sha256:" + "1" * 64},
        "identity": {"user_id": "1002", "time_zone": "Asia/Shanghai",
                     "response_hash": "sha256:" + "2" * 64},
        "topology": {"response_hash": "sha256:" + "3" * 64,
                     "data_sources": [{"id": "source-a"}, {"id": "source-b"}],
                     "relations": [{"leftDataSourceId": "source-a", "rightDataSourceId": "source-b",
                                    "leftFieldId": "field-a", "rightFieldId": "field-b"}],
                     "display_fields": [{"fieldId": "field-a", "dataSourceId": "source-a"},
                                        {"fieldId": "field-b", "dataSourceId": "source-b"}],
                     "base_lwt_args": {"filterList": [], "rowFilter": [], "layout": {}}},
    }


def _intent():
    return {"requirement_name": "统计图查看明细限制原因提示优化", "view_name": "客户销售订单明细拼表",
            "join_type": "left", "join_reason": "保留客户并关联销售订单"}


def test_compile_joined_table_uses_only_live_discovery():
    body = compile_joined_table_save_args(_intent(), _discovery())
    assert body["categoryID"] == "folder-live"
    assert body["saveType"] == 0
    assert body["queryLwtArg"]["id"] == body["lwtArgs"]["lwtId"] == ""
    assert canonical_hash(body).startswith("sha256:")


def test_compile_joined_table_rejects_missing_provenance_and_foreign_field():
    discovery = _discovery()
    discovery["folder"]["response_hash"] = "sample"
    with pytest.raises(ValueError, match="live folder"):
        compile_joined_table_save_args(_intent(), discovery)


def _plan():
    discovery = _discovery()
    body = compile_joined_table_save_args(_intent(), discovery)
    return {"schema_version": "test-data-plan/1.0", "environment": "112",
            "namespace": "qa-joined-table-112", "case_plans": [{
                "case_id": "JOINED-TABLE", "requirement_name": _intent()["requirement_name"],
                "resources": [{"resource_key": "joined", "resource_type": "joined_table",
                    "resource_id_variable": "view_id", "retention_mode": "retain",
                    "ownership_namespace": "qa-joined-table-112", "display_name": _intent()["view_name"],
                    "source_field_type": "multi_source", "requirement_name": _intent()["requirement_name"],
                    "asset_folder_name": _intent()["requirement_name"],
                    "setup": {"request": {"api": "fs_bi_dev.lwt_manager.save", "json": body},
                              "extract": {"view_id": "Value.viewID"},
                              "live_discovery_evidence": discovery},
                    "readiness": [{"request": {"api": "fs_bi_dev.lwt_manager.query_arg_detail",
                                                 "json": {"id": "{{ view_id }}"}}}]}]}]}


def test_n27_allows_live_bound_joined_table_and_rejects_captured_id():
    policy = json.loads((Path(__file__).parents[1] / "policies/test-data-policy.json").read_text())
    assert validate_test_data_plan(_plan(), policy)["write_authorized"] is True
    plan = _plan()
    plan["case_plans"][0]["resources"][0]["setup"]["request"]["json"]["queryLwtArg"]["id"] = "captured"
    with pytest.raises(SecurityPolicyError, match="create IDs must be empty"):
        validate_test_data_plan(plan, policy)
    discovery = _discovery()
    discovery["topology"]["display_fields"][0]["dataSourceId"] = "captured-source"
    with pytest.raises(ValueError, match="does not belong"):
        compile_joined_table_save_args(_intent(), discovery)
