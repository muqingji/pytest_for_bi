from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.agents.base import AgentContext
from qa_agents.contracts import ArtifactStatus
from qa_agents.errors import SecurityPolicyError
from qa_agents.security import SecurityPolicy
from qa_agents.test_data import (
    TestDataPlannerAgent,
    bind_plan_to_case,
    prepare_test_data_plan,
    validate_test_data_plan,
)
from qa_agents.contracts import ArtifactEnvelope, Producer


ROOT = Path(__file__).resolve().parents[1]


def _resource() -> dict:
    return {
        "resource_key": "metric",
        "resource_type": "aggregate_metric",
        "retention_mode": "delete",
        "resource_id_variable": "metric_field_id",
        "setup": {
            "name": "create namespaced metric",
            "request": {
                "api": "fs_bi_stat.agg_rule.add_new_agg_rule",
                "json": {"displayName": "{{ namespace }}-metric"},
            },
            "extract": {"metric_field_id": "Value.fieldId"},
            "expect": {"status_code": 200},
        },
        "readiness": [
            {
                "name": "query metric",
                "request": {
                    "api": "fs_bi_stat.agg_rule.query_agg_rule_by_field_id",
                    "json": {"fieldId": "{{ metric_field_id }}"},
                },
                "expect": {"status_code": 200},
            }
        ],
        "cleanup": {
            "name": "delete metric",
            "request": {
                "api": "fs_bi_stat.agg_rule.delete_agg_rule",
                "json": {"fieldId": "{{ metric_field_id }}"},
            },
            "expect": {"status_code": 200},
        },
    }


def _case(test_level: str = "integration") -> dict:
    return {
        "id": "CASE-DETAIL",
        "test_level": test_level,
        "test_data": {"resource_requirements": [_resource()]},
        "steps": [{"request": {"api": "fs_bi_stat.stat_base.data_query_da655ba1"}}],
    }


def _run(cases: list[dict]) -> dict:
    artifact = TestDataPlannerAgent().run(
        AgentContext("run-1", "new_requirement", "snapshot-1"),
        {"environment": "112", "namespace": "qa-run-1-detail", "cases": cases},
        SecurityPolicy(),
    )
    return artifact.to_dict()


def _policy() -> dict:
    return json.loads((ROOT / "policies/test-data-policy.json").read_text())


def test_a22_plans_owned_112_resource_and_n27_validates_it() -> None:
    artifact = _run([_case()])

    assert artifact["status"] == "completed"
    validation = validate_test_data_plan(artifact["payload"], _policy())
    assert validation["validated_resource_count"] == 1
    assert validation["write_authorized"] is True
    assert validation["phase_permissions"] == {
        "setup": "write",
        "readiness": "read_only",
        "cleanup": "disabled",
        "retention_verification": "read_only",
    }
    bound = bind_plan_to_case(_case(), artifact["payload"])
    assert bound["environment"] == "112"
    assert bound["variables"]["namespace"] == "qa-run-1-detail"
    assert bound["cleanup"][0]["when_variable"] == "metric_field_id"


def test_a22_pauses_unit_cases_without_sending_them_to_data_construction() -> None:
    artifact = _run([_case("unit")])

    assert artifact["status"] == ArtifactStatus.COMPLETED.value
    assert artifact["payload"]["case_plans"] == []
    assert artifact["payload"]["paused_cases"] == [
        {
            "case_id": "CASE-DETAIL",
            "reason_code": "paused_existing_developer_unit_coverage",
        }
    ]


def test_n27_rejects_cross_environment_and_missing_cleanup_binding() -> None:
    plan = _run([_case()])["payload"]
    plan["environment"] = "online"
    with pytest.raises(SecurityPolicyError, match="not allowed"):
        validate_test_data_plan(plan, _policy())

    plan = _run([_case()])["payload"]
    plan["case_plans"][0]["resources"][0]["cleanup"]["request"]["json"] = {
        "fieldId": "unbounded"
    }
    with pytest.raises(SecurityPolicyError, match="extracted resource id"):
        validate_test_data_plan(plan, _policy())


def test_n27_rejects_inline_credentials() -> None:
    plan = _run([_case()])["payload"]
    plan["case_plans"][0]["resources"][0]["setup"]["request"]["token"] = "inline"
    with pytest.raises(SecurityPolicyError, match="inline credential"):
        validate_test_data_plan(plan, _policy())


def test_n27_rejects_write_operation_in_readiness_phase() -> None:
    plan = _run([_case()])["payload"]
    plan["case_plans"][0]["resources"][0]["readiness"][0]["request"]["api"] = (
        "fs_bi_stat.agg_rule.add_new_agg_rule"
    )

    with pytest.raises(SecurityPolicyError, match="read-only readiness operation"):
        validate_test_data_plan(plan, _policy())


def _enum_plan() -> dict:
    plan = _run([_case()])["payload"]
    setup = plan["case_plans"][0]["resources"][0]["setup"]
    setup["request"]["json"]["filterLists"] = [{"filters": [{
        "fieldId": "level-field", "fieldID": "level-field", "fieldType": "Enum",
        "fieldName": "客户级别",
        "value1": '[{"optionCode":"A","optionName":"重点客户"}]',
    }]}]
    return plan


def _bind_enum(plan: dict, **overrides: object) -> None:
    binding = {
        "field_id": "level-field", "field_api_name": "account_level",
        "option_query_operation": "fs_bi_stat.stat_edit.get_filters_result",
        "option_response_hash": "sha256:" + "a" * 64,
        "response_json_path": "$.Value.options[*]",
        "queried_option_codes": ["A", "B"], "selected_option_codes": ["A"],
    }
    binding.update(overrides)
    plan["case_plans"][0]["resources"][0]["setup"]["enum_option_bindings"] = [binding]


def test_n27_accepts_bound_enum_and_plain_numeric_filter() -> None:
    plan = _enum_plan()
    _bind_enum(plan)
    validate_test_data_plan(plan, _policy())
    numeric = _run([_case()])["payload"]
    numeric["case_plans"][0]["resources"][0]["setup"]["request"]["json"]["filterLists"] = [
        {"filters": [{"fieldId": "amount", "fieldType": "Number", "value1": "0"}]}
    ]
    validate_test_data_plan(numeric, _policy())


@pytest.mark.parametrize("mutation,message", [
    ("missing", "enum_option_bindings"), ("hash", "valid option response hash"),
    ("unknown", "not returned"), ("field", "exactly one binding"),
    ("label", "without optionCode"),
])
def test_n27_rejects_unproven_enum_values(mutation: str, message: str) -> None:
    plan = _enum_plan()
    if mutation != "missing":
        overrides: dict[str, object] = {}
        if mutation == "hash": overrides["option_response_hash"] = "sample"
        if mutation == "unknown": overrides["selected_option_codes"] = ["C"]
        if mutation == "field": overrides["field_id"] = "other-field"
        _bind_enum(plan, **overrides)
    if mutation == "label":
        plan["case_plans"][0]["resources"][0]["setup"]["request"]["json"]["filterLists"][0]["filters"][0]["value1"] = '[{"optionName":"重点客户"}]'
    with pytest.raises(SecurityPolicyError, match=message):
        validate_test_data_plan(plan, _policy())


def _custom_dimension_plan() -> dict:
    plan = _run([_case()])["payload"]
    resource = plan["case_plans"][0]["resources"][0]
    resource["resource_type"] = "custom_dimension"
    resource["setup"]["request"]["api"] = "fs_bi_stat.custom_dimension.create_custom_dimension"
    resource["setup"]["request"]["json"] = {
        "customType": "enum_group",
        "sourceDimension": {"fieldId": "source-level", "dimensionField": "account_level"},
        "dimensionConfig": '{"groups":[{"name":"等级组","values":["A"]}]}',
        "ownership": "{{ namespace }}",
    }
    resource["setup"]["enum_option_bindings"] = [{
        "field_id": "source-level", "field_api_name": "account_level",
        "option_query_operation": "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        "option_response_hash": "sha256:" + "b" * 64,
        "response_json_path": "$.Value[*].ui.data[*]",
        "queried_option_codes": ["A", "B"], "selected_option_codes": ["A"],
    }]
    resource["cleanup"]["request"]["api"] = "fs_bi_stat.custom_dimension.delete_custom_dimension"
    return plan


def test_n27_validates_enum_codes_hidden_in_custom_dimension_config() -> None:
    validate_test_data_plan(_custom_dimension_plan(), _policy())
    plan = _custom_dimension_plan()
    plan["case_plans"][0]["resources"][0]["setup"]["request"]["json"]["dimensionConfig"] = (
        '{"groups":[{"name":"等级组","values":["invented"]}]}'
    )
    with pytest.raises(SecurityPolicyError, match="not returned"):
        validate_test_data_plan(plan, _policy())


def _existing_historical_chart_plan() -> dict:
    plan = _run([_case()])["payload"]
    resource = plan["case_plans"][0]["resources"][0]
    resource.pop("setup")
    resource.pop("cleanup")
    resource["resource_type"] = "stat_chart"
    resource["lifecycle_mode"] = "existing_read_only"
    resource["discovery"] = {
        "request": {
            "api": "fs_bi_stat.view_data_query_api.get_chart_config",
            "json": {"viewId": "BI_existing"},
        }
    }
    resource["readiness"] = [resource["discovery"]]
    resource["existing_asset_evidence"] = {
        "historical_required": True,
        "evidence_level": "historical_candidate_verified_by_id_timestamp_and_live_readback",
        "observed_created_at": "2025-09-04T08:08:11Z",
        "requirement_baseline_at": "2026-08-07T11:42:44Z",
        "live_readback_status": "succeeded",
        "configuration_hash": "sha256:" + "c" * 64,
    }
    return plan


def test_n27_accepts_existing_historical_asset_without_fake_setup() -> None:
    plan = _existing_historical_chart_plan()
    validation = validate_test_data_plan(plan, _policy())
    bound = bind_plan_to_case(_case(), plan)

    assert validation["validated_resource_count"] == 1
    assert bound["setup"] == []
    assert [item["phase"] for item in bound["preparation"]] == [
        "discovery", "readiness"
    ]


@pytest.mark.parametrize("mutation,message", [
    ("write", "cannot define setup or cleanup"),
    ("hash", "valid configuration hash"),
    ("readback", "live readback is not proven"),
    ("level", "evidence level is insufficient"),
])
def test_n27_rejects_unproven_existing_historical_asset(
    mutation: str, message: str
) -> None:
    plan = _existing_historical_chart_plan()
    resource = plan["case_plans"][0]["resources"][0]
    evidence = resource["existing_asset_evidence"]
    if mutation == "write":
        resource["setup"] = _resource()["setup"]
    elif mutation == "hash":
        evidence["configuration_hash"] = "sample"
    elif mutation == "readback":
        evidence["live_readback_status"] = "unknown"
    else:
        evidence["evidence_level"] = "repository_reference_only"

    with pytest.raises(SecurityPolicyError, match=message):
        validate_test_data_plan(plan, _policy())


def test_prepare_test_data_plan_writes_hash_bound_a22_and_n27_artifacts(
    tmp_path: Path,
) -> None:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-1",
        workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "compiled_cases": [_case()],
        },
    )
    compiled_path = tmp_path / "n25.json"
    compiled_path.write_text(json.dumps(compiled.to_dict()), encoding="utf-8")

    result = prepare_test_data_plan(
        compiled_path,
        ROOT / "policies/test-data-policy.json",
        tmp_path / "out",
        environment="112",
        namespace="qa-run-1-detail",
    )

    assert result["ready_for_execution"] is True
    assert (tmp_path / "out/artifacts/a22-test-data-plan.json").exists()
    n27 = json.loads(
        (tmp_path / "out/artifacts/n27-test-data-plan-validation.json").read_text()
    )
    assert n27["payload"]["a22_artifact_hash"] == result["a22_artifact"]["artifact_hash"]


def test_policy_skip_defers_only_cases_that_need_missing_data(tmp_path: Path) -> None:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-1",
        workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "compiled_cases": [_case(), {"id": "CASE-EXISTING", "steps": []}],
        },
    )
    compiled_path = tmp_path / "n25.json"
    compiled_path.write_text(json.dumps(compiled.to_dict()), encoding="utf-8")

    result = prepare_test_data_plan(
        compiled_path,
        ROOT / "policies/test-data-policy.json",
        tmp_path / "out",
        environment="112",
        namespace="qa-run-1-detail",
        skip_by_policy=True,
    )

    assert result["ready_for_execution"] is True
    assert result["a22_artifact"]["status"] == "skipped_by_policy"
    assert result["n27_artifact"]["status"] == "skipped_by_policy"
    assert result["executable_case_ids"] == ["CASE-EXISTING"]
    assert result["deferred_cases"][0]["route"] == "deferred_data_construction"


def test_existing_automation_managed_plan_is_completed_and_hash_bound(tmp_path: Path) -> None:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-1", workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases", source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={"schema_version": "n25-compiled-test-cases/1.0", "compiled_cases": [_case()]},
    )
    execution = ArtifactEnvelope(
        workflow_run_id="run-1", workflow_mode="new_requirement",
        artifact_id="n15-execution-plan", source_snapshot_id="snapshot-1",
        producer=Producer("N15", runtime="deterministic"),
        payload={
            "schema_version": "execution-plan/1.0",
            "actions": [{
                "case_id": "CASE-DETAIL", "action": "run_existing",
                "automation_ref": "tests/test_existing.py",
            }],
        },
    )
    compiled_path = tmp_path / "n25.json"
    execution_path = tmp_path / "n15.json"
    compiled_path.write_text(json.dumps(compiled.to_dict()), encoding="utf-8")
    execution_path.write_text(json.dumps(execution.to_dict()), encoding="utf-8")

    result = prepare_test_data_plan(
        compiled_path, ROOT / "policies/test-data-policy.json", tmp_path / "out",
        environment="112", namespace="qa-run-1-detail",
        execution_plan_path=execution_path,
    )

    assert result["ready_for_execution"] is True
    assert result["a22_artifact"]["status"] == "completed"
    n27 = json.loads((tmp_path / "out/artifacts/n27-test-data-plan-validation.json").read_text())
    assert n27["payload"]["decision"] == "existing_automation_managed"
    assert n27["payload"]["execution_plan_hash"] == execution.artifact_hash
