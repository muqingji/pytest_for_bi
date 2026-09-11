import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import threading

import pytest

from qa_agents.contracts import content_hash
from qa_agents.errors import ContractError
from qa_agents.workflow_monitor import (
    check_heartbeat,
    _dispatch_plan,
    discover_workflows,
    load_registry,
    monitor_once,
    register_workflow,
    resume_workflow,
    watchdog_status,
)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _workflow(tmp_path: Path, *, adapter: bool = True):
    root = tmp_path
    artifact_root = root / "generated/run-1"
    config = artifact_root / "workflow-config.json"
    spec = artifact_root / "current/workflow-center-spec.json"
    adapter_path = artifact_root / "g01-policy.json"
    config_value = {
        "node_agents": {"A02": "agent-a02"},
        "g01_policy": "gate-policy.json",
        "workspace_id": "workspace-1",
        "workflow_project_id": "project-1",
        "internal_project_id": "project-1",
    }
    policy = {
        "gate_id": "G01",
        "policy_hash": "sha256:policy",
        "require_human_actor": True,
        "allowed_actor_ids": ["qa"],
        "allowed_multica_member_ids": ["member-1"],
    }
    _write(root / "gate-policy.json", policy)
    if adapter:
        config_value["g01_adapter_policy"] = str(adapter_path.relative_to(root))
        _write(adapter_path, {
            "gate_id": "G01",
            "gate_policy_hash": "sha256:policy",
            "allowed_multica_member_ids": ["member-1"],
        })
    _write(config, config_value)
    _write(
        spec,
        {
            "workflow_id": "WF-1",
            "workflow_run_id": "run-1",
            "stage_cards": [{"stage_card_id": f"C{i}"} for i in range(1, 9)],
            "nodes": [{"node_id": "A08", "state": "queued"}],
        },
    )
    return root, artifact_root, config, spec


def test_registration_requires_gate_adapter(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path, adapter=False)
    with pytest.raises(ContractError, match="G01 adapter policy is required"):
        register_workflow(root / "registry.json", config, artifact_root, spec, root)


def test_monitor_isolates_runs_and_records_dispatch_receipt(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        output = {
            "workflow_run_id": "run-1",
            "a08": {
                "action": "dispatched",
                "node_id": "A08",
                "bundle_hash": "sha256:bundle",
                "issue_id": "issue-a08",
            },
            "sync": {"overall_status": "running"},
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    result = monitor_once(registry_path, root, root / "sync.py", runner=runner)

    assert result["results"][0]["status"] == "running"
    registry = load_registry(registry_path)
    assert registry["workflows"]["run-1"]["consecutive_failures"] == 0
    audit = json.loads((root / "workflow-monitor-audit.json").read_text())
    key = content_hash(
        {
            "workflow_run_id": "run-1",
            "node_id": "A08",
            "input_bundle_hash": "sha256:bundle",
            "attempt": 1,
        }
    )
    assert audit["dispatches"][key]["issue_id"] == "issue-a08"


def test_monitor_runs_workflows_concurrently_but_commits_centrally(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)
    second_root = root / "generated/run-2"
    second_config = second_root / "workflow-config.json"
    second_spec = second_root / "current/workflow-center-spec.json"
    second_adapter = second_root / "g01-policy.json"
    config_value = json.loads(config.read_text())
    config_value["g01_adapter_policy"] = str(second_adapter.relative_to(root))
    _write(second_config, config_value)
    _write(second_adapter, json.loads((artifact_root / "g01-policy.json").read_text()))
    spec_value = json.loads(spec.read_text())
    spec_value["workflow_run_id"] = "run-2"
    _write(second_spec, spec_value)
    register_workflow(registry_path, second_config, second_root, second_spec, root)
    barrier = threading.Barrier(2, timeout=2)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        run_id = "run-2" if "run-2" in " ".join(command) else "run-1"
        barrier.wait()
        return subprocess.CompletedProcess(
            command, 0,
            json.dumps({"workflow_run_id": run_id, "dispatch_supervision": {"eligible_nodes": []}, "sync": {"overall_status": "running"}}),
            "",
        )

    result = monitor_once(registry_path, root, root / "sync.py", runner=runner)

    assert {item["workflow_run_id"] for item in result["results"]} == {"run-1", "run-2"}
    assert len(json.loads((root / "workflow-monitor-audit.json").read_text())["events"]) == 2


def test_eligible_without_dispatch_uses_dispatcher_receipt_not_plan(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0,
            json.dumps({"workflow_run_id": "run-1", "dispatch_supervision": {"eligible_nodes": []}, "sync": {"overall_status": "running"}}),
            "",
        )

    result = monitor_once(registry_path, root, root / "sync.py", runner=runner)

    assert result["heartbeat"]["eligible_without_dispatch_total"] == 0


def test_monitor_lock_skip_is_busy_not_accuracy_violation(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"skipped": "another sync pass is already running"}),
            "",
        )

    result = monitor_once(registry_path, root, root / "sync.py", runner=runner)
    entry = load_registry(registry_path)["workflows"]["run-1"]
    assert entry["status"] != "suspended_accuracy_violation"
    assert result["results"][0]["status"] in {"running", "busy"}


def test_monitor_fatal_json_is_not_accuracy_violation(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"fatal": "multica timed out after 180s"}), ""
        )

    monitor_once(registry_path, root, root / "sync.py", runner=runner)
    entry = load_registry(registry_path)["workflows"]["run-1"]
    assert entry["status"] != "suspended_accuracy_violation"
    assert "multica timed out" in entry["last_error"]["message"]


def test_monitor_suspends_cross_run_result(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"workflow_run_id": "run-2"}), ""
        )

    monitor_once(registry_path, root, root / "sync.py", runner=runner)
    entry = load_registry(registry_path)["workflows"]["run-1"]
    assert entry["status"] == "suspended_accuracy_violation"


def test_monitor_records_structured_sync_errors(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        output = {
            "workflow_run_id": "run-1",
            "errors": [{"node_id": "G01", "error": "comment is incomplete"}],
            "sync": {"overall_status": "needs_action"},
        }
        return subprocess.CompletedProcess(command, 2, json.dumps(output), "")

    monitor_once(registry_path, root, root / "sync.py", runner=runner)

    entry = load_registry(registry_path)["workflows"]["run-1"]
    assert entry["status"] == "needs_action"
    assert entry["consecutive_failures"] == 1
    assert entry["last_error"]["errors"][0]["node_id"] == "G01"
    audit = json.loads((root / "workflow-monitor-audit.json").read_text())
    assert audit["events"][-1]["status"] == "completed_with_errors"


def test_monitor_suspends_duplicate_dispatch_with_different_issue(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)
    issue_ids = iter(("issue-a08-first", "issue-a08-duplicate"))

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        output = {
            "workflow_run_id": "run-1",
            "a08": {
                "action": "dispatched",
                "node_id": "A08",
                "bundle_hash": "sha256:same-bundle",
                "issue_id": next(issue_ids),
            },
            "sync": {"overall_status": "running"},
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    monitor_once(registry_path, root, root / "sync.py", runner=runner)
    monitor_once(registry_path, root, root / "sync.py", runner=runner)

    entry = load_registry(registry_path)["workflows"]["run-1"]
    assert entry["status"] == "suspended_accuracy_violation"
    assert "Duplicate dispatch" in entry["last_error"]["message"]


def test_discovery_registers_valid_workflow_once(tmp_path: Path) -> None:
    root, artifact_root, _config, _spec = _workflow(tmp_path)
    registry_path = root / "active.json"

    first = discover_workflows(registry_path, root)
    second = discover_workflows(registry_path, root)

    assert first["registered"] == ["run-1"]
    assert second["registered"] == []
    assert "run-1" in load_registry(registry_path)["workflows"]


def test_watchdog_accepts_recent_heartbeat(tmp_path: Path) -> None:
    registry_path = tmp_path / "active.json"
    _write(
        tmp_path / "workflow-monitor-heartbeat.json",
        {"updated_at": datetime.now(timezone.utc).isoformat(), "active_count": 1},
    )

    assert check_heartbeat(registry_path, max_age_seconds=90)["status"] == "healthy"


def test_watchdog_rejects_stale_heartbeat(tmp_path: Path) -> None:
    registry_path = tmp_path / "active.json"
    _write(
        tmp_path / "workflow-monitor-heartbeat.json",
        {"updated_at": "2020-01-01T00:00:00+00:00", "active_count": 1},
    )

    with pytest.raises(ContractError, match="heartbeat is stale"):
        check_heartbeat(registry_path, max_age_seconds=90)


def test_watchdog_persists_unhealthy_alert_without_dispatch_authority(tmp_path: Path) -> None:
    registry_path = tmp_path / "active.json"
    _write(tmp_path / "workflow-monitor-heartbeat.json", {"updated_at": "2020-01-01T00:00:00+00:00"})

    result = watchdog_status(registry_path, max_age_seconds=90)

    assert result["status"] == "unhealthy"
    assert result["dispatch_authority"] is False
    assert json.loads((tmp_path / "workflow-monitor-alert.json").read_text())["error"]


def test_monitor_rejects_dispatch_not_present_in_authorization_plan(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        output = {
            "workflow_run_id": "run-1",
            "a08": {
                "action": "dispatched",
                "node_id": "A09",
                "bundle_hash": "sha256:bundle",
                "issue_id": "issue-a08",
            },
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    monitor_once(registry_path, root, root / "sync.py", runner=runner)

    entry = load_registry(registry_path)["workflows"]["run-1"]
    assert entry["status"] == "suspended_accuracy_violation"
    assert "unauthorized node A09" in entry["last_error"]["message"]


def test_monitor_rejects_tampered_audit_chain(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "registry.json"
    register_workflow(registry_path, config, artifact_root, spec, root)

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        output = {"workflow_run_id": "run-1", "sync": {"overall_status": "running"}}
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    monitor_once(registry_path, root, root / "sync.py", runner=runner)
    audit_path = root / "workflow-monitor-audit.json"
    audit = json.loads(audit_path.read_text())
    audit["events"][0]["overall_status"] = "completed"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")

    with pytest.raises(ContractError, match="audit event hash is invalid"):
        monitor_once(registry_path, root, root / "sync.py", runner=runner)


def test_dispatch_plan_allows_retryable_states_but_not_human_or_terminal(
    tmp_path: Path,
) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    value = json.loads(spec.read_text())
    value["nodes"] = [
        {"node_id": "A08", "state": "blocked"},
        {"node_id": "A09", "state": "failed"},
        {"node_id": "G02", "state": "waiting_human"},
        {"node_id": "A11", "state": "completed"},
    ]
    _write(spec, value)
    entry = register_workflow(root / "active.json", config, artifact_root, spec, root)

    plan = _dispatch_plan(entry, 1)

    assert plan["allowed_nodes"] == ["A08", "A09"]
    assert plan["authorization_evidence"]["spec_revision"] is None


def test_dispatch_plan_authorizes_n04_auto_return_target(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    n04_path = artifact_root / "artifacts-auto/artifacts/n04-test-case-ir-validation.json"
    _write(
        n04_path,
        {
            "artifact_id": "n04-test-case-ir-validation",
            "payload": {"next_node": "A08", "valid": False},
        },
    )
    value = json.loads(spec.read_text())
    value["nodes"] = [
        {"node_id": "A08", "state": "completed"},
        {
            "node_id": "N04",
            "state": "blocked",
            "artifact_path": str(n04_path),
        },
        {"node_id": "G02", "state": "waiting_human"},
    ]
    _write(spec, value)
    entry = register_workflow(root / "active.json", config, artifact_root, spec, root)

    plan = _dispatch_plan(entry, 1)

    assert plan["allowed_nodes"] == ["A08", "N04"]


def test_dispatch_plan_blocks_not_started_agent_on_pending_upstream_closure(
    tmp_path: Path,
) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    value = json.loads(spec.read_text())
    value["nodes"] = [
        {"node_id": "A15", "state": "completed"},
        {"node_id": "A22", "state": "waiting_human"},
        {"node_id": "A18-CT", "state": "not_started"},
        {"node_id": "N05", "state": "not_started"},
    ]
    _write(spec, value)
    entry = register_workflow(root / "active.json", config, artifact_root, spec, root)

    plan = _dispatch_plan(entry, 1)

    assert plan["allowed_nodes"] == []


def test_monitor_passes_absolute_dispatch_authorization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "active.json"
    register_workflow(registry_path, config, artifact_root, spec, root)
    commands = []

    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"workflow_run_id": "run-1", "sync": {"overall_status": "running"}}),
            "",
        )

    monkeypatch.chdir(root)
    monitor_once(Path("active.json"), root, root / "sync.py", runner=runner)

    authorization = Path(commands[0][commands[0].index("--dispatch-authorization") + 1])
    assert authorization.is_absolute()
    assert authorization == (root / "plans" / "run-1.json").resolve()


def test_dispatch_plan_authorizes_a08_from_waiting_human_n04_new_issues(
    tmp_path: Path,
) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    n04_path = artifact_root / "artifacts-auto/artifacts/n04-test-case-ir-validation.json"
    _write(
        n04_path,
        {
            "artifact_id": "n04-test-case-ir-validation",
            "payload": {
                "next_node": "human",
                "valid": False,
                "issues": [{"id": "ISS-014", "route_to": "A08"}],
            },
        },
    )
    value = json.loads(spec.read_text())
    value["nodes"] = [
        {"node_id": "A08", "state": "completed"},
        {
            "node_id": "N04",
            "state": "waiting_human",
            "artifact_path": str(n04_path),
        },
    ]
    _write(spec, value)
    entry = register_workflow(root / "active.json", config, artifact_root, spec, root)

    plan = _dispatch_plan(entry, 1)

    assert "A08" in plan["allowed_nodes"]
    assert "N04" not in plan["allowed_nodes"]


def test_shadow_validator_rejects_planner_disagreement(tmp_path: Path) -> None:
    from qa_agents.workflow_monitor import _verify_dispatch_plan

    root, artifact_root, config, spec = _workflow(tmp_path)
    entry = register_workflow(root / "active.json", config, artifact_root, spec, root)
    plan = _dispatch_plan(entry, 1)
    plan["allowed_nodes"] = ["A09"]
    plan["plan_hash"] = content_hash({key: value for key, value in plan.items() if key != "plan_hash"})

    with pytest.raises(ContractError, match="no longer matches"):
        _verify_dispatch_plan(plan, entry)


def test_accuracy_suspension_requires_explicit_resume_acknowledgement(tmp_path: Path) -> None:
    root, artifact_root, config, spec = _workflow(tmp_path)
    registry_path = root / "active.json"
    register_workflow(registry_path, config, artifact_root, spec, root)
    registry = load_registry(registry_path)
    registry["workflows"]["run-1"]["status"] = "suspended_accuracy_violation"
    registry["registry_hash"] = content_hash(
        {key: value for key, value in registry.items() if key != "registry_hash"}
    )
    _write(registry_path, registry)

    with pytest.raises(ContractError, match="explicit acknowledgement"):
        resume_workflow(registry_path, "run-1")
    resumed = resume_workflow(
        registry_path, "run-1", acknowledge_accuracy_violation=True
    )

    assert resumed["status"] == "active"
    assert resumed["accuracy_violation_acknowledged"] is True
