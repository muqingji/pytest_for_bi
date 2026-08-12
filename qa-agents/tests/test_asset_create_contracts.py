from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> dict:
    return json.loads((ROOT / "knowledge" / name).read_text(encoding="utf-8"))


def test_chart_contract_separates_case_metadata_identity_and_executor_fields() -> None:
    value = _load("bi-chart-create-contract.json")
    assert value["status"] == "candidate_until_112_create_and_readback"
    assert value["operation_id"] == "fs_bi_stat.stat_edit.creat_stat_view"
    assert value["readback_operation_id"] == "fs_bi_stat.stat_edit.get_chart_config"
    assert value["folder_provenance"]["on_missing_or_ambiguous"] == "not_ready"
    assert value["folder_provenance"]["query_operation"] == "fs_bi_crm.rpt_category.get_category_and_rpt"
    assert value["idempotency"]["server_key"] is False
    assert "axisData.measureFieldList" in value["case_derived"]
    assert "statViewBaseInfo.categoryID" in value["metadata_discovered"]
    assert "cookies" in value["executor_owned"]
    assert "configuration_hash_matches" in value["readiness"]


def test_report_contract_keeps_transport_encryption_out_of_agent_plan() -> None:
    value = _load("bi-report-create-contract.json")
    assert value["fixed_create_values"] == {"isEdit": 2, "tableType": 0}
    assert "businessObjects" in value["required_for_create"]
    assert "transport encryption" in value["executor_owned"]
    assert "tableType_is_zero" in value["readiness"]


def test_joined_table_contract_compiles_case_intent_from_live_topology() -> None:
    value = _load("bi-joined-table-create-contract.json")
    assert value["status"] == "verified_112"
    assert value["verification_evidence"] == "generated/112-joined-table-create-evidence.json"
    assert value["operation_id"] == "fs_bi_dev.lwt_manager.save"
    assert value["fixed_create_values"]["saveType"] == 0
    assert value["fixed_create_values"]["queryLwtArg.id"] == ""
    assert "lwtArgs.relations" in value["metadata_discovered"]
    assert "relation_graph_is_connected_or_vertical" in value["preflight_validation"]
    assert "configuration_hash_matches" in value["readiness"]


def test_joined_table_contract_keeps_encrypted_transport_out_of_agent_plan() -> None:
    value = _load("bi-joined-table-create-contract.json")
    assert "transport encryption" in value["executor_owned"]
    assert "__bodykey" in value["executor_owned"]
    assert "x-fs-token" in value["executor_owned"]


def test_pivot_contract_has_distinct_axis_and_measure_roles() -> None:
    value = _load("bi-pivot-table-create-contract.json")
    assert value["status"] == "candidate"
    assert value["fixed_create_values"] == {"isEdit": 2, "tableType": 1}
    assert value["field_roles"]["rowGroupFields"] == {"groupType": 1, "aggrType": "0"}
    assert value["field_roles"]["colGroupFields"] == {"groupType": 2, "aggrType": "0"}
    assert value["field_roles"]["statFields"]["groupType"] == 3
    assert "group_field_count_within_tenant_limit" in value["preflight_validation"]
    assert "pivot_data_query_succeeds" in value["readiness"]


def test_pivot_contract_keeps_encrypted_transport_out_of_agent_plan() -> None:
    value = _load("bi-pivot-table-create-contract.json")
    assert "transport encryption" in value["executor_owned"]
    assert "__bodykey" in value["executor_owned"]
    assert "cookies" in value["executor_owned"]


def test_create_contracts_do_not_contain_captured_secret_material() -> None:
    forbidden = ("FSAuthX=", "FSAuthXC=", "JSESSIONID=", "Op8nDJ")
    for name in (
        "bi-chart-create-contract.json",
        "bi-report-create-contract.json",
        "bi-joined-table-create-contract.json",
        "bi-pivot-table-create-contract.json",
    ):
        text = (ROOT / "knowledge" / name).read_text(encoding="utf-8")
        assert not any(secret in text for secret in forbidden)
