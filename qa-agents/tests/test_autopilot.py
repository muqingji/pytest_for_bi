import json
from pathlib import Path

import pytest

from qa_agents.autopilot import initialize_autopilot, reconcile_autopilot
from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer
from qa_agents.errors import ContractError


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _request(path: Path, run_id: str = "REQ-1-r001") -> Path:
    return _write(
        path,
        {
            "schema_version": "autopilot-request/1.0",
            "workflow_id": "REQ-1",
            "requirement_id": "REQ-1",
            "workflow_run_id": run_id,
            "workflow_definition_version": "server-requirement/1.0",
            "source_snapshot_id": "snapshot-1",
            "title": "服务端接口优化",
            "human_owner_member_id": "member-qa",
        },
    )


def _config(path: Path) -> Path:
    return _write(
        path,
        {
            "schema_version": "multica-workflow-center/1.0",
            "workspace_id": "workspace-1",
            "workflow_project_id": "project-workflow",
            "internal_project_id": "project-internal",
            "workflow_lead_id": "agent-lead",
            "properties": {},
        },
    )


class FakeMultica:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.number = 0

    def __call__(self, command: list[str], _stdin: str | None) -> dict:
        self.calls.append(command)
        self.number += 1
        if command[1:3] == ["autopilot", "create"]:
            return {
                "id": f"autopilot-{self.number}",
                "assignee_id": command[command.index("--agent") + 1],
                "project_id": command[command.index("--project") + 1],
                "execution_mode": "run_only",
                "status": "active",
            }
        project_id = command[command.index("--project") + 1]
        return {
            "id": f"issue-{self.number}",
            "identifier": f"QAA-{self.number}",
            "project_id": project_id,
        }


def test_autopilot_reuses_requirement_parent_and_run_idempotently(tmp_path: Path) -> None:
    request = _request(tmp_path / "request.json")
    config = _config(tmp_path / "config.json")
    multica = FakeMultica()

    first = initialize_autopilot(
        request, config, tmp_path / "registry", tmp_path / "run-1", runner=multica
    )
    repeated = initialize_autopilot(
        request, config, tmp_path / "registry", tmp_path / "run-1-repeat", runner=multica
    )

    assert first["parent_reused"] is False
    assert first["run_reused"] is False
    assert repeated["parent_reused"] is True
    assert repeated["run_reused"] is True
    assert repeated["parent_issue"] == first["parent_issue"]
    assert repeated["run_issue"] == first["run_issue"]
    assert len(multica.calls) == 3
    assert repeated["autopilot"] == first["autopilot"]
    assert repeated["autopilot_reused"] is True

    second_request = _request(tmp_path / "request-2.json", "REQ-1-r002")
    second = initialize_autopilot(
        second_request,
        config,
        tmp_path / "registry",
        tmp_path / "run-2",
        runner=multica,
    )
    assert second["parent_issue"] == first["parent_issue"]
    assert second["run_issue"] != first["run_issue"]
    assert len(multica.calls) == 4
    registry = json.loads((tmp_path / "registry/autopilot-registry.json").read_text())
    assert len(registry["workflows"]["REQ-1"]["runs"]) == 2
    assert registry["workflows"]["REQ-1"]["runs"][0]["status"] == "superseded"


def test_autopilot_creates_parent_in_center_and_run_in_internal_project(tmp_path: Path) -> None:
    multica = FakeMultica()
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "run",
        runner=multica,
    )

    parent, autopilot, run = multica.calls
    assert parent[parent.index("--project") + 1] == "project-workflow"
    assert "--parent" not in parent
    assert run[run.index("--project") + 1] == "project-internal"
    assert run[run.index("--parent") + 1] == "issue-1"
    assert autopilot[1:3] == ["autopilot", "create"]
    assert autopilot[autopilot.index("--mode") + 1] == "run_only"


def test_autopilot_initializes_complete_server_quality_dag(tmp_path: Path) -> None:
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "run",
        runner=FakeMultica(),
    )

    spec = json.loads((tmp_path / "run/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    assert {
        "A14", "A15", "A18-BE", "A18-CT", "N05", "G03", "N07", "N08",
        "N10", "N17", "N18", "N09", "N20", "N11", "N19", "N12", "N13", "N23",
    } <= set(nodes)
    assert nodes["A14"]["stage"] == nodes["A15"]["stage"]
    assert nodes["N08"]["stage"] == nodes["N17"]["stage"]
    assert nodes["N23"]["stage"] > nodes["N12"]["stage"]


def test_reconcile_derives_nodes_and_human_actions_from_artifacts(tmp_path: Path) -> None:
    multica = FakeMultica()
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "initial",
        runner=multica,
    )
    artifacts = tmp_path / "artifacts"
    for component, artifact_id, status, payload in (
        (
            "N01",
            "n01-source-extraction-manifest",
            ArtifactStatus.COMPLETED,
            {"summary": "输入已冻结"},
        ),
        (
            "A02",
            "a02-requirement-analysis",
            ArtifactStatus.COMPLETED_WITH_GAPS,
            {"summary": "识别 2 个开放问题"},
        ),
        (
            "G01",
            "g01-scope-review",
            ArtifactStatus.NEEDS_HUMAN,
            {"decision": "pending", "issues": [{"id": "I1"}, {"id": "I2"}]},
        ),
    ):
        envelope = ArtifactEnvelope(
            workflow_run_id="REQ-1-r001",
            workflow_mode="new_requirement",
            artifact_id=artifact_id,
            source_snapshot_id="snapshot-1",
            producer=Producer(component),
            payload=payload,
            status=status,
        )
        _write(artifacts / f"{artifact_id}.json", envelope.to_dict())

    result = reconcile_autopilot(
        tmp_path / "initial/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled",
    )

    assert result["changed"] is True
    assert result["revision"] == 2
    assert result["artifact_node_count"] == 3
    assert result["open_action_count"] == 1
    spec = json.loads((tmp_path / "reconciled/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    assert nodes["INPUT-FREEZE"]["state"] == "completed"
    assert nodes["A02"]["state"] == "completed"
    assert nodes["G01"]["state"] == "waiting_human"
    assert spec["actions"][0]["item_count"] == 2

    unchanged = reconcile_autopilot(
        tmp_path / "reconciled/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled-again",
    )
    assert unchanged["changed"] is False
    assert unchanged["revision"] == 2


def test_autopilot_rejects_tampered_registry(tmp_path: Path) -> None:
    multica = FakeMultica()
    request = _request(tmp_path / "request.json")
    config = _config(tmp_path / "config.json")
    initialize_autopilot(
        request, config, tmp_path / "registry", tmp_path / "run", runner=multica
    )
    registry_path = tmp_path / "registry/autopilot-registry.json"
    registry = json.loads(registry_path.read_text())
    registry["revision"] = 99
    _write(registry_path, registry)

    with pytest.raises(ContractError, match="registry hash is invalid"):
        initialize_autopilot(
            request, config, tmp_path / "registry", tmp_path / "run-2", runner=multica
        )
