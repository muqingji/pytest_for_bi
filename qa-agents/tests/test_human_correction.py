import json
from pathlib import Path

import pytest

from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.human_correction import (
    DECISION_FILE,
    OUTCOME_FILE,
    STATE_FILE,
    open_multica_human_correction,
    prepare_human_correction_request,
    project_human_correction_state,
    sync_multica_human_correction,
)
from qa_agents.multica import prepare_multica_test_design_correction_input


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "tests" / "fixtures" / "pilot"
POLICY = ROOT / "policies" / "human-correction-policy.json"
WORKSPACE_ID = "457d700f-6c27-4a59-871d-c2c56bca9f46"
PROJECT_ID = "c2c84f1f-20af-456d-9eca-c9fbbd253840"
MEMBER_ID = "c2c6b9c6-4fb9-4439-a4a5-de4e93784c54"


def pilot_artifacts() -> tuple[Path, Path, Path]:
    return (
        PILOT / "multica-stage7" / "artifacts" / "a08-test-design-ir.json",
        PILOT / "multica-stage8" / "artifacts" / "a09-oracle-coverage-review.json",
        PILOT / "multica-stage9" / "artifacts" / "n04-test-case-ir-validation.json",
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class FakeMultica:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.issue = {
            "id": "human-correction-issue-1",
            "workspace_id": WORKSPACE_ID,
            "project_id": PROJECT_ID,
            "assignee_id": MEMBER_ID,
            "assignee_type": "member",
            "metadata": {},
            "status": "todo",
            "updated_at": "2026-08-10T10:00:00Z",
        }

    def __call__(self, args: list[str], cwd: Path) -> dict:
        assert cwd.exists()
        self.calls.append(args)
        if args[:2] == ["issue", "create"]:
            return dict(self.issue)
        if args[:3] == ["issue", "metadata", "set"]:
            self.issue["metadata"][args[args.index("--key") + 1]] = args[
                args.index("--value") + 1
            ]
            return {"ok": True}
        if args[:2] == ["issue", "status"]:
            self.issue["status"] = args[3]
            return dict(self.issue)
        if args[:2] == ["issue", "get"]:
            return json.loads(json.dumps(self.issue))
        raise AssertionError(args)


def prepare(tmp_path: Path) -> tuple[Path, Path]:
    output = tmp_path / "human-correction"
    prepare_human_correction_request(*pilot_artifacts(), POLICY, output)
    return output / "human-correction-request.json", output


def test_prepare_human_correction_from_real_exhausted_pilot(tmp_path: Path) -> None:
    request_path, output = prepare(tmp_path)
    first = read_json(request_path)
    second = prepare_human_correction_request(*pilot_artifacts(), POLICY, output)

    assert second == first
    assert first["budget"] == {
        "correction_attempt": 2,
        "max_correction_attempts": 2,
        "automatic_budget_reset": False,
        "next_attempt": 3,
    }
    assert [item["directive_id"] for item in first["directives"]] == [
        "A09-R001",
        "A09-R002",
        "A09-R003",
        "A09-R004",
    ]
    assert read_json(output / STATE_FILE)["state"] == "prepared"


def test_human_correction_multica_done_authorizes_a08_recovery(tmp_path: Path) -> None:
    request_path, output = prepare(tmp_path)
    multica = FakeMultica()
    opened = open_multica_human_correction(
        request_path, POLICY, output, runner=multica
    )
    paused = sync_multica_human_correction(
        request_path, pilot_artifacts()[2], POLICY, output, runner=multica
    )

    assert opened["state"] == "waiting_for_review"
    assert paused["state"] == "waiting_for_review"
    assert not (output / DECISION_FILE).exists()

    multica.issue["status"] = "done"
    multica.issue["updated_at"] = "2026-08-10T10:05:00Z"
    outcome = sync_multica_human_correction(
        request_path, pilot_artifacts()[2], POLICY, output, runner=multica
    )
    call_count = len(multica.calls)
    repeated = sync_multica_human_correction(
        request_path, pilot_artifacts()[2], POLICY, output, runner=multica
    )

    assert outcome["decision"] == "directed_correction"
    assert outcome["next_node"] == "A08"
    assert outcome["next_correction_attempt"] == 3
    assert outcome["automatic_budget_reset"] is False
    assert repeated == outcome
    assert len(multica.calls) == call_count
    decision = read_json(output / DECISION_FILE)
    assert decision["authorized_directive_ids"] == [
        "A09-R001",
        "A09-R002",
        "A09-R003",
        "A09-R004",
    ]

    bundle = prepare_multica_test_design_correction_input(
        pilot_artifacts()[0],
        PILOT / "multica-inputs" / "a08-correction-01" / "a08-input.json",
        pilot_artifacts()[1],
        pilot_artifacts()[2],
        tmp_path / "a08-human-recovery",
        human_correction_request_path=request_path,
        human_correction_decision_path=output / DECISION_FILE,
        human_correction_policy_path=POLICY,
    )
    feedback = bundle["allowed_inputs"]["correction_feedback"]
    assert bundle["profile_version"] == "1.3.0"
    assert feedback["schema_version"] == "test-design-correction/1.2"
    assert feedback["recovery_mode"] == "human_directed"
    assert feedback["correction_attempt"] == 3
    assert feedback["max_correction_attempts"] == 2
    assert feedback["automatic_budget_reset"] is False
    assert bundle["allowed_inputs"]["human_correction_decision"][
        "decision_hash"
    ] == decision["decision_hash"]
    assert bundle["upstream_human_decision"]["request_hash"] == read_json(
        request_path
    )["request_hash"]


def test_human_correction_cancel_terminates(tmp_path: Path) -> None:
    request_path, output = prepare(tmp_path)
    multica = FakeMultica()
    open_multica_human_correction(request_path, POLICY, output, runner=multica)
    multica.issue["status"] = "cancelled"

    outcome = sync_multica_human_correction(
        request_path, pilot_artifacts()[2], POLICY, output, runner=multica
    )

    assert outcome["decision"] == "terminate"
    assert outcome["next_node"] is None
    assert outcome["status"] == "cancelled"


def test_human_correction_projects_authoritative_state_idempotently(
    tmp_path: Path,
) -> None:
    request_path, output = prepare(tmp_path)
    multica = FakeMultica()
    open_multica_human_correction(request_path, POLICY, output, runner=multica)
    multica.issue["status"] = "done"
    outcome = sync_multica_human_correction(
        request_path, pilot_artifacts()[2], POLICY, output, runner=multica
    )
    request = read_json(request_path)
    state = read_json(output / STATE_FILE)
    run_manifest_path = tmp_path / "multica-run-manifest.json"
    workspace_manifest_path = tmp_path / "workspace-manifest.json"
    run_manifest_path.write_text(
        json.dumps(
            {
                "workflow_run_id": request["workflow_run_id"],
                "current_node": "human_test_design_correction",
                "human_correction": {
                    "request_hash": request["request_hash"],
                    "status": "in_review",
                },
            }
        ),
        encoding="utf-8",
    )
    workspace_manifest_path.write_text(
        json.dumps(
            {
                "pilot_state": {
                    "current_node": "human_test_design_correction",
                    "human_correction": {
                        "request_hash": request["request_hash"],
                        "status": "in_review",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    project_human_correction_state(
        request, outcome, state, run_manifest_path, workspace_manifest_path
    )
    first = read_json(run_manifest_path)
    project_human_correction_state(
        request, outcome, state, run_manifest_path, workspace_manifest_path
    )

    assert read_json(run_manifest_path) == first
    assert first["current_node"] == "A08"
    assert first["human_correction"]["status"] == "done"
    assert first["human_correction"]["decision_hash"] == outcome["decision_hash"]
    workspace = read_json(workspace_manifest_path)["pilot_state"]
    assert workspace["current_node"] == "A08"
    assert workspace["human_correction"]["outcome_hash"] == outcome["outcome_hash"]


def test_human_correction_projection_rejects_stale_manifest(tmp_path: Path) -> None:
    request_path, output = prepare(tmp_path)
    multica = FakeMultica()
    open_multica_human_correction(request_path, POLICY, output, runner=multica)
    multica.issue["status"] = "done"
    outcome = sync_multica_human_correction(
        request_path, pilot_artifacts()[2], POLICY, output, runner=multica
    )
    request = read_json(request_path)
    state = read_json(output / STATE_FILE)
    run_manifest = tmp_path / "run.json"
    workspace_manifest = tmp_path / "workspace.json"
    run_manifest.write_text(
        json.dumps(
            {
                "workflow_run_id": request["workflow_run_id"],
                "human_correction": {"request_hash": "stale"},
            }
        ),
        encoding="utf-8",
    )
    workspace_manifest.write_text(
        json.dumps(
            {
                "pilot_state": {
                    "human_correction": {"request_hash": request["request_hash"]}
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="request binding is stale"):
        project_human_correction_state(
            request, outcome, state, run_manifest, workspace_manifest
        )


def test_human_correction_sync_rejects_partial_manifest_projection(
    tmp_path: Path,
) -> None:
    request_path, output = prepare(tmp_path)

    with pytest.raises(ContractError, match="requires both manifest paths"):
        sync_multica_human_correction(
            request_path,
            pilot_artifacts()[2],
            POLICY,
            output,
            run_manifest_path=tmp_path / "run.json",
        )


def test_human_correction_rejects_wrong_member(tmp_path: Path) -> None:
    request_path, output = prepare(tmp_path)
    multica = FakeMultica()
    open_multica_human_correction(request_path, POLICY, output, runner=multica)
    multica.issue["status"] = "done"
    multica.issue["assignee_id"] = "wrong-member"

    with pytest.raises(SecurityPolicyError, match="unauthorized"):
        sync_multica_human_correction(
            request_path, pilot_artifacts()[2], POLICY, output, runner=multica
        )


def test_human_correction_rejects_non_exhausted_n04(tmp_path: Path) -> None:
    n04 = read_json(pilot_artifacts()[2])
    n04["payload"]["next_node"] = "A08"
    n04["payload"]["correction_attempt"] = 1
    n04.pop("artifact_hash")
    from qa_agents.contracts import artifact_hash_from_mapping

    n04["artifact_hash"] = artifact_hash_from_mapping(n04)
    n04_path = tmp_path / "n04.json"
    n04_path.write_text(json.dumps(n04), encoding="utf-8")

    with pytest.raises(ContractError, match="exhausted N04 human route"):
        prepare_human_correction_request(
            pilot_artifacts()[0],
            pilot_artifacts()[1],
            n04_path,
            POLICY,
            tmp_path / "output",
        )


def test_qaa20_human_recovery_candidate_is_rejected() -> None:
    """QAA-20 must not enter the main chain until binding fields and tool gates pass."""

    from qa_agents.multica import ingest_multica_output

    bundle = PILOT / "multica-inputs" / "a08-human-correction-01" / "a08-input.json"
    response = (
        PILOT / "multica-outputs" / "a08-human-correction-01-run-messages.json"
    )
    with pytest.raises((ContractError, SecurityPolicyError)):
        ingest_multica_output(
            bundle,
            response.read_text(encoding="utf-8"),
            PILOT / "multica-stage10-reject",
            task_id="ef5825a9-71c1-4938-ba70-23939896fa9a",
            issue_id="1cd41070-3051-49bb-82e2-020e7f6281f4",
            attachment_id="019fea88-f67f-7c78-850c-b2f91497c919",
            model_provider="codex",
            model_snapshot="gpt-5.6-sol",
            prompt_version="1.3.0",
        )


def test_a08_v130_instruction_requires_binding_fields_and_text_delivery() -> None:
    instruction = (
        ROOT / "multica" / "agent-instructions" / "a08-v1.3.0.md"
    ).read_text(encoding="utf-8")
    for required in (
        "input_bundle_hash",
        "workflow_run_id",
        "source_snapshot_id",
        "final text message",
        "no file writes",
        "human_directed",
        "correction_attempt=3",
    ):
        assert required in instruction

