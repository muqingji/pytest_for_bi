"""Deterministic N07 environment precheck and N16 environment fix gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer, content_hash
from qa_agents.env_precheck import run_n07_env_precheck, run_n16_env_fix
from qa_agents.errors import ContractError, SecurityPolicyError

RUN_ID = "run-env-pilot"
SNAPSHOT = "snapshot-v1"


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def target_dict() -> dict:
    return {
        "schema_version": "environment-target/1.0",
        "expected": {
            "deployment_commits": [
                {"component": "backend", "commit": "abc123"},
                {"component": "frontend", "commit": "def456"},
            ],
            "dependencies": [
                {"name": "mysql", "health_required": "ready"},
                {"name": "redis", "health_required": "ready"},
            ],
            "test_accounts": [
                {"account": "qa-1001", "permissions": ["read", "write"]},
            ],
            "feature_flags": [
                {"flag": "i18n-v2", "expected": "on"},
            ],
            "tenant_configs": [
                {"tenant": "tenant-91863", "field": "language", "value": "en-US"},
            ],
            "test_data_requirements": [
                {"key": "order-1002", "expected_state": "ready"},
            ],
            "runtime": {"timezone": "Asia/Shanghai", "language": "zh-CN"},
            "namespace_policy": {"prefix": "qa-pilot-", "cleanup": {"required": True}},
            "required_locks": [
                {
                    "resource": "test-account-1002",
                    "mode": "exclusive",
                    "reason": "account-level global state",
                },
            ],
        },
    }


def observed_dict() -> dict:
    return {
        "schema_version": "environment-observation/1.0",
        "environment": "staging-1",
        "requester_id": "runner-01",
        "deployment_commits": [
            {"component": "backend", "commit": "abc123"},
            {"component": "frontend", "commit": "def456"},
        ],
        "dependencies": [
            {"name": "mysql", "status": "ready"},
            {"name": "redis", "status": "ready"},
        ],
        "test_accounts": [
            {"account": "qa-1001", "exists": True, "permissions": ["read", "write"]},
        ],
        "feature_flags": [{"flag": "i18n-v2", "value": "on"}],
        "tenant_configs": [{"tenant": "tenant-91863", "language": "en-US"}],
        "test_data": [{"key": "order-1002", "state": "ready"}],
        "runtime": {"timezone": "Asia/Shanghai", "language": "zh-CN"},
        "test_namespaces": [
            {"namespace": "qa-pilot-run-1", "cleanup_policy": {"required": True}},
        ],
        "resource_locks": [
            {"resource": "test-account-1002", "acquired": True, "mode": "exclusive",
             "holder": "runner-01"},
        ],
    }


def run_precheck(
    tmp_path: Path,
    target: dict | None = None,
    observed: dict | None = None,
    *,
    previous_fingerprint: str = "",
    throttle_reason: str = "",
) -> dict:
    target_path = tmp_path / "target.json"
    observed_path = tmp_path / "observed.json"
    write_json(target_path, target or target_dict())
    write_json(observed_path, observed or observed_dict())
    return run_n07_env_precheck(
        target_path,
        observed_path,
        tmp_path,
        workflow_run_id=RUN_ID,
        source_snapshot_id=SNAPSHOT,
        previous_fingerprint=previous_fingerprint,
        throttle_reason=throttle_reason,
    )


def test_n07_passed_environment_records_artifact(tmp_path: Path) -> None:
    artifact = run_precheck(tmp_path)

    assert artifact["artifact_id"] == "n07-environment-precheck"
    assert artifact["status"] == "completed"
    assert artifact["payload"]["decision"] == "passed"
    assert artifact["payload"]["next_node"] == "N08"
    assert artifact["payload"]["summary"] == {"passed": 12, "warning": 0, "failed": 0,
                                             "not_applicable": 0}
    assert artifact["payload"]["environment_fingerprint"].startswith("sha256:")
    assert artifact["payload"]["throttled"] is False
    assert (tmp_path / "artifacts/n07-environment-precheck.json").exists()


def test_n07_accepts_hash_bound_policy_skipped_n27(tmp_path: Path) -> None:
    target_path = write_json(tmp_path / "target.json", target_dict())
    observed_path = write_json(tmp_path / "observed.json", observed_dict())
    n27 = ArtifactEnvelope(
        workflow_run_id=RUN_ID,
        workflow_mode="new_requirement",
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id=SNAPSHOT,
        producer=Producer("N27", runtime="deterministic"),
        payload={
            "schema_version": "test-data-plan-validation/1.0",
            "valid": True,
            "decision": "skipped_by_policy",
            "next_node": "N07",
            "deferred_cases": [{"case_id": "CASE-DATA"}],
        },
        status=ArtifactStatus.SKIPPED_BY_POLICY,
        reason_code="test_data_agent_paused_by_policy",
    )
    n27_path = write_json(tmp_path / "n27.json", n27.to_dict())

    artifact = run_n07_env_precheck(
        target_path,
        observed_path,
        tmp_path / "out",
        workflow_run_id=RUN_ID,
        source_snapshot_id=SNAPSHOT,
        workflow_mode="new_requirement",
        test_data_validation_path=n27_path,
    )

    assert artifact["payload"]["next_node"] == "N08"
    assert artifact["payload"]["test_data_validation_hash"] == n27.artifact_hash
    assert any(item["name"] == "test-data-plan:route" for item in artifact["payload"]["checks"])


def test_n07_accepts_pending_human_n27_evidence(tmp_path: Path) -> None:
    """N27 completed_with_gaps + pending_human (structurally safe plan awaiting
    the A22 human confirmation) is valid evidence for the N07 environment gate."""
    target_path = write_json(tmp_path / "target.json", target_dict())
    observed_path = write_json(tmp_path / "observed.json", observed_dict())
    n27 = ArtifactEnvelope(
        workflow_run_id=RUN_ID,
        workflow_mode="new_requirement",
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id=SNAPSHOT,
        producer=Producer("N27", runtime="deterministic"),
        payload={
            "schema_version": "test-data-plan-validation/1.0",
            "valid": True,
            "pending_human": True,
        },
        status=ArtifactStatus.COMPLETED_WITH_GAPS,
        reason_code="test_data_plan_pending_human",
    )
    n27_path = write_json(tmp_path / "n27.json", n27.to_dict())

    artifact = run_n07_env_precheck(
        target_path,
        observed_path,
        tmp_path / "out",
        workflow_run_id=RUN_ID,
        source_snapshot_id=SNAPSHOT,
        workflow_mode="new_requirement",
        test_data_validation_path=n27_path,
    )

    assert artifact["status"] == "completed"
    assert artifact["payload"]["decision"] == "passed"
    assert artifact["payload"]["next_node"] == "N08"
    assert artifact["payload"]["test_data_validation_hash"] == n27.artifact_hash


def test_n07_can_inherit_parent_workflow_mode(tmp_path: Path) -> None:
    target_path = write_json(tmp_path / "target.json", target_dict())
    observed_path = write_json(tmp_path / "observed.json", observed_dict())

    artifact = run_n07_env_precheck(
        target_path,
        observed_path,
        tmp_path / "out",
        workflow_run_id=RUN_ID,
        source_snapshot_id=SNAPSHOT,
        workflow_mode="new_requirement",
    )

    assert artifact["workflow_mode"] == "new_requirement"
    assert artifact["payload"]["production_isolation"] is False
    assert (tmp_path / "out/artifacts/n07-environment-precheck.json").exists()


def test_n07_failed_check_blocks_and_routes_to_n16(tmp_path: Path) -> None:
    observed = observed_dict()
    observed["deployment_commits"] = [
        {"component": "backend", "commit": "abc123"},
        {"component": "frontend", "commit": "zzz999"},
    ]
    artifact = run_precheck(tmp_path, observed=observed)

    assert artifact["payload"]["decision"] == "blocked"
    assert artifact["status"] == "blocked"
    assert artifact["payload"]["next_node"] == "N16"
    failed = [item for item in artifact["payload"]["checks"] if item["status"] == "failed"]
    assert [item["id"] for item in failed] == ["N07-C002"]


def test_n07_warning_is_completed_with_gaps(tmp_path: Path) -> None:
    observed = observed_dict()
    observed["dependencies"] = [
        {"name": "mysql", "status": "ready"},
        {"name": "redis", "status": "degraded"},
    ]
    artifact = run_precheck(tmp_path, observed=observed)

    assert artifact["payload"]["decision"] == "passed_with_warnings"
    assert artifact["status"] == "completed_with_gaps"
    assert artifact["payload"]["next_node"] == "N08"


def test_n07_throttles_unchanged_environment_without_reason(tmp_path: Path) -> None:
    first = run_precheck(tmp_path)
    fingerprint = first["payload"]["environment_fingerprint"]

    with pytest.raises(ContractError, match="throttled unless a reason"):
        run_precheck(tmp_path, previous_fingerprint=fingerprint)


def test_n07_records_throttled_when_reason_given(tmp_path: Path) -> None:
    first = run_precheck(tmp_path)
    fingerprint = first["payload"]["environment_fingerprint"]

    artifact = run_precheck(
        tmp_path, previous_fingerprint=fingerprint, throttle_reason="explicit recheck after N16"
    )
    assert artifact["payload"]["throttled"] is True
    assert artifact["payload"]["throttle_reason"] == "explicit recheck after N16"


def test_n07_rejects_invalid_target_contract(tmp_path: Path) -> None:
    target = target_dict()
    target["schema_version"] = "environment-target/9.9"
    with pytest.raises(ContractError, match="schema_version"):
        run_precheck(tmp_path, target=target)

    target = target_dict()
    del target["expected"]["runtime"]
    with pytest.raises(ContractError, match="expected.runtime"):
        run_precheck(tmp_path, target=target)


def test_n07_rejects_credential_values(tmp_path: Path) -> None:
    observed = observed_dict()
    observed["feature_flags"] = [
        {"flag": "i18n-v2", "value": "on"},
        {"token": "opaque-credential", "value": "x"},
    ]
    with pytest.raises(SecurityPolicyError, match="Credential-like"):
        run_precheck(tmp_path, observed=observed)


def _action_hash(action: dict) -> str:
    return content_hash(
        {key: value for key, value in action.items() if key != "idempotency_key"}
    )


def _fix_plan_from_precheck(precheck_path: Path, *, tamper_key: bool = False) -> dict:
    artifact = json.loads(precheck_path.read_text(encoding="utf-8"))
    failed = [item for item in artifact["payload"]["checks"] if item["status"] == "failed"]
    actions = []
    for index, check in enumerate(failed):
        action = {
            "id": f"FIX-{index + 1:03d}",
            "target_check": check["id"],
            "result": "performed",
            "expected_state": {"deployment": "target-commit"},
            "pre_state": {"deployment": "stale-commit"},
            "compensation": {"action": "rollback", "reason": "restore previous build"},
        }
        if tamper_key:
            action["idempotency_key"] = "sha256:tampered"
        else:
            action["idempotency_key"] = _action_hash(action)
        actions.append(action)
    return {"schema_version": "environment-fix-plan/1.0", "actions": actions}


def run_fix(tmp_path: Path, plan: dict, precheck: dict | None = None) -> dict:
    if precheck is None:
        precheck = run_precheck(tmp_path, observed=_blocked_observed())
    write_json(tmp_path / "artifacts/n07-environment-precheck.json", precheck)
    precheck_path = tmp_path / "artifacts/n07-environment-precheck.json"
    plan_path = tmp_path / "fix-plan.json"
    write_json(plan_path, plan)
    return run_n16_env_fix(precheck_path, plan_path, tmp_path / "n16")


def _blocked_observed() -> dict:
    observed = observed_dict()
    observed["deployment_commits"] = [
        {"component": "backend", "commit": "abc123"},
        {"component": "frontend", "commit": "zzz999"},
    ]
    return observed


def test_n16_fixed_routes_back_to_n07(tmp_path: Path) -> None:
    precheck = run_precheck(tmp_path, observed=_blocked_observed())
    plan = _fix_plan_from_precheck(tmp_path / "artifacts/n07-environment-precheck.json")

    artifact = run_fix(tmp_path, plan)

    assert artifact["artifact_id"] == "n16-environment-fix"
    assert artifact["status"] == "completed"
    assert artifact["payload"]["decision"] == "fixed"
    assert artifact["payload"]["next_node"] == "N07"
    assert artifact["payload"]["summary"] == {"actions": 1, "performed": 1,
                                             "not_required": 0, "failed": 0}
    assert artifact["payload"]["addressed_checks"] == ["N07-C002"]
    assert artifact["payload"]["precheck_hash"] == precheck["artifact_hash"]
    assert (tmp_path / "n16/artifacts/n16-environment-fix.json").exists()


def test_n16_requires_blocked_precheck(tmp_path: Path) -> None:
    precheck = run_precheck(tmp_path)
    plan = _fix_plan_from_precheck(tmp_path / "artifacts/n07-environment-precheck.json")

    with pytest.raises(ContractError, match="blocked N07 precheck"):
        run_fix(tmp_path, plan, precheck=precheck)


def test_n16_rejects_fix_without_state_change(tmp_path: Path) -> None:
    precheck = run_precheck(tmp_path, observed=_blocked_observed())
    plan = _fix_plan_from_precheck(tmp_path / "artifacts/n07-environment-precheck.json")
    plan["actions"][0]["pre_state"] = dict(plan["actions"][0]["expected_state"])
    plan["actions"][0]["idempotency_key"] = _action_hash(plan["actions"][0])

    with pytest.raises(ContractError, match="without any state change"):
        run_fix(tmp_path, plan)


def test_n16_rejects_unaddressed_failed_checks(tmp_path: Path) -> None:
    observed = _blocked_observed()
    observed["deployment_commits"][0] = {"component": "backend", "commit": "bad111"}
    precheck = run_precheck(tmp_path, observed=observed)
    write_json(tmp_path / "artifacts/n07-environment-precheck.json", precheck)
    plan = _fix_plan_from_precheck(tmp_path / "artifacts/n07-environment-precheck.json")
    plan["actions"] = plan["actions"][:1]

    with pytest.raises(ContractError, match="does not address failed checks"):
        run_fix(tmp_path, plan)


def test_n16_rejects_invalid_idempotency_key(tmp_path: Path) -> None:
    precheck = run_precheck(tmp_path, observed=_blocked_observed())
    write_json(tmp_path / "artifacts/n07-environment-precheck.json", precheck)
    plan = _fix_plan_from_precheck(
        tmp_path / "artifacts/n07-environment-precheck.json", tamper_key=True
    )

    with pytest.raises(ContractError, match="idempotency_key is invalid"):
        run_fix(tmp_path, plan)


def test_n16_blocked_when_fix_action_fails(tmp_path: Path) -> None:
    precheck = run_precheck(tmp_path, observed=_blocked_observed())
    plan = _fix_plan_from_precheck(tmp_path / "artifacts/n07-environment-precheck.json")
    action = plan["actions"][0]
    action["result"] = "failed"
    action["idempotency_key"] = _action_hash(action)

    artifact = run_fix(tmp_path, plan)

    assert artifact["payload"]["decision"] == "blocked"
    assert artifact["payload"]["next_node"] == "human"
    assert artifact["status"] == "blocked"
    assert artifact["reason_code"] == "environment_fix_blocked"


def test_n16_rejects_empty_fix_plan(tmp_path: Path) -> None:
    precheck = run_precheck(tmp_path, observed=_blocked_observed())
    write_json(tmp_path / "artifacts/n07-environment-precheck.json", precheck)
    plan = {"schema_version": "environment-fix-plan/1.0", "actions": []}

    with pytest.raises(ContractError, match="has no actions"):
        run_fix(tmp_path, plan)


def test_n07_n16_cli_end_to_end(tmp_path: Path) -> None:
    from qa_agents.cli import _run

    target_path = tmp_path / "cli" / "target.json"
    observed_path = tmp_path / "cli" / "observed.json"
    write_json(target_path, target_dict())
    write_json(observed_path, _blocked_observed())
    n07_out = tmp_path / "cli" / "stage-n07"
    plan_path = tmp_path / "cli" / "fix-plan.json"

    assert (
        _run(
            [
                "run-n07-env-precheck",
                "--target", str(target_path),
                "--observed", str(observed_path),
                "--output", str(n07_out),
                "--workflow-run-id", RUN_ID,
                "--source-snapshot-id", SNAPSHOT,
            ]
        )
        == 0
    )
    precheck_path = n07_out / "artifacts/n07-environment-precheck.json"
    artifact = json.loads(precheck_path.read_text(encoding="utf-8"))
    assert artifact["payload"]["decision"] == "blocked"

    write_json(plan_path, _fix_plan_from_precheck(precheck_path))
    n16_out = tmp_path / "cli" / "stage-n16"
    assert (
        _run(
            [
                "run-n16-env-fix",
                "--precheck", str(precheck_path),
                "--fix-plan", str(plan_path),
                "--output", str(n16_out),
            ]
        )
        == 0
    )
    fix = json.loads((n16_out / "artifacts/n16-environment-fix.json").read_text(encoding="utf-8"))
    assert fix["payload"]["decision"] == "fixed"
    assert fix["payload"]["next_node"] == "N07"
