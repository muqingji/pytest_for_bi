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
        "cleanup": "write",
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
