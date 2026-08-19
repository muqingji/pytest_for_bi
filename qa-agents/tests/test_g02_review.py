import json
from pathlib import Path

import pytest

from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, EvidenceRef, Producer
from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.g02_review import (
    DECISION_FILE,
    OUTCOME_FILE,
    STATE_FILE,
    open_multica_test_case_review,
    prepare_test_case_review_request,
    sync_multica_test_case_review,
)
from qa_agents.storage import ArtifactStore


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "policies" / "g02-review-policy.json"
WORKSPACE_ID = "457d700f-6c27-4a59-871d-c2c56bca9f46"
MEMBER_ID = "c2c6b9c6-4fb9-4439-a4a5-de4e93784c54"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_valid_gate_artifacts(root: Path) -> tuple[Path, Path, Path]:
    store = ArtifactStore(root)
    common = {
        "workflow_run_id": "multica-run-1",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
    }
    design = ArtifactEnvelope(
        **common,
        artifact_id="a08-test-design-ir",
        producer=Producer(component_id="A08", runtime="multica"),
        payload={"parent_cases": [{"id": "CASE-001"}]},
        status=ArtifactStatus.COMPLETED,
    )
    review = ArtifactEnvelope(
        **common,
        artifact_id="a09-oracle-coverage-review",
        producer=Producer(component_id="A09", runtime="multica"),
        payload={"approved": True, "issues": []},
        status=ArtifactStatus.COMPLETED,
    )
    n04 = ArtifactEnvelope(
        **common,
        artifact_id="n04-test-case-ir-validation",
        producer=Producer(component_id="N04", runtime="deterministic"),
        payload={
            "schema_version": "test-case-ir-validation/1.0",
            "valid": True,
            "test_design_artifact_id": design.artifact_id,
            "test_design_artifact_hash": design.artifact_hash,
            "oracle_review_artifact_id": review.artifact_id,
            "oracle_review_artifact_hash": review.artifact_hash,
            "issues": [],
            "issue_count": 0,
            "blocking_issue_count": 0,
            "route_summary": {},
            "correction_attempt": 3,
            "max_correction_attempts": 2,
            "next_node": "G02",
            "g02_status": "pending",
        },
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=design.artifact_id,
                location="a08-test-design-ir.json",
                content_hash=design.artifact_hash,
            ),
            EvidenceRef(
                source_type="artifact",
                source_id=review.artifact_id,
                location="a09-oracle-coverage-review.json",
                content_hash=review.artifact_hash,
            ),
        ),
        reason_code="test_case_ir_valid",
    )
    for artifact in (design, review, n04):
        store.write_artifact(artifact)
    artifact_dir = root / "artifacts"
    return (
        artifact_dir / "a08-test-design-ir.json",
        artifact_dir / "a09-oracle-coverage-review.json",
        artifact_dir / "n04-test-case-ir-validation.json",
    )


class FakeMultica:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.comments: list[dict] = []
        self.issue = {
            "id": "g02-issue-1",
            "workspace_id": WORKSPACE_ID,
            "project_id": "f2f893a2-55dc-414d-87d9-a483e51765d6",
            "assignee_id": MEMBER_ID,
            "assignee_type": "member",
            "metadata": {},
            "status": "todo",
            "updated_at": "2026-08-10T08:00:00Z",
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
        if args[:3] == ["issue", "comment", "list"]:
            return {"comments": [dict(comment) for comment in self.comments]}
        raise AssertionError(f"Unexpected Multica command: {args}")


def prepare_valid_review(tmp_path: Path) -> tuple[tuple[Path, Path, Path], Path]:
    artifacts = write_valid_gate_artifacts(tmp_path / "run")
    output = tmp_path / "g02"
    prepare_test_case_review_request(*artifacts, POLICY_PATH, output)
    return artifacts, output


def test_prepare_g02_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    artifacts, output = prepare_valid_review(tmp_path)
    first = read_json(output / "g02-review-request.json")
    second = prepare_test_case_review_request(*artifacts, POLICY_PATH, output)

    assert second == first
    assert first["review_policy"]["allowed_actor_ids"] == ["muqj11262"]
    assert first["multica_control"]["assignee_member_id"] == MEMBER_ID
    assert first["review_summary"]["n04_valid"] is True
    assert [item["case_id"] for item in first["review_items"]] == ["CASE-001"]
    assert read_json(output / STATE_FILE)["state"] == "prepared"


def test_prepare_g02_rejects_current_invalid_pilot_n04(tmp_path: Path) -> None:
    pilot = ROOT / "tests" / "fixtures" / "pilot"
    with pytest.raises(ContractError, match="cannot start before N04"):
        prepare_test_case_review_request(
            pilot / "multica-stage7" / "artifacts" / "a08-test-design-ir.json",
            pilot / "multica-stage8" / "artifacts" / "a09-oracle-coverage-review.json",
            pilot / "multica-stage9" / "artifacts" / "n04-test-case-ir-validation.json",
            POLICY_PATH,
            tmp_path / "g02",
        )


def test_open_g02_creates_one_bound_multica_review_issue(tmp_path: Path) -> None:
    _, output = prepare_valid_review(tmp_path)
    multica = FakeMultica()
    request = output / "g02-review-request.json"

    first = open_multica_test_case_review(
        request, POLICY_PATH, output, runner=multica
    )
    call_count = len(multica.calls)
    second = open_multica_test_case_review(
        request, POLICY_PATH, output, runner=multica
    )

    assert first["state"] == "waiting_for_review"
    assert first["observed_multica_status"] == "in_review"
    assert second == first
    assert len(multica.calls) == call_count
    assert multica.issue["metadata"]["qa_request_hash"] == first["request_hash"]


def test_in_review_pauses_and_done_resumes_once(tmp_path: Path) -> None:
    artifacts, output = prepare_valid_review(tmp_path)
    multica = FakeMultica()
    request = output / "g02-review-request.json"
    open_multica_test_case_review(request, POLICY_PATH, output, runner=multica)

    paused = sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )
    assert paused["state"] == "waiting_for_review"
    assert not (output / DECISION_FILE).exists()

    multica.issue["status"] = "done"
    multica.issue["updated_at"] = "2026-08-10T08:05:00Z"
    approved = sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )
    call_count = len(multica.calls)
    repeated = sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )

    assert approved["decision"] == "approved"
    assert approved["action"] == "continue"
    assert approved["next_node"] == "N25"
    assert repeated == approved
    assert len(multica.calls) == call_count
    assert read_json(output / STATE_FILE)["state"] == "resumed"


@pytest.mark.parametrize(
    ("multica_status", "decision", "action", "next_node"),
    [
        ("blocked", "request_changes", "return_upstream", "A08"),
        ("cancelled", "rejected", "terminate", None),
    ],
)
def test_g02_terminal_status_routes_deterministically(
    tmp_path: Path,
    multica_status: str,
    decision: str,
    action: str,
    next_node: str | None,
) -> None:
    artifacts, output = prepare_valid_review(tmp_path)
    multica = FakeMultica()
    request = output / "g02-review-request.json"
    open_multica_test_case_review(request, POLICY_PATH, output, runner=multica)
    multica.issue["status"] = multica_status

    outcome = sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )

    assert outcome["decision"] == decision
    assert outcome["action"] == action
    assert outcome["next_node"] == next_node


def test_g02_blocked_uses_reviewer_comment_as_fix_direction(
    tmp_path: Path,
) -> None:
    artifacts, output = prepare_valid_review(tmp_path)
    multica = FakeMultica()
    request = output / "g02-review-request.json"
    open_multica_test_case_review(request, POLICY_PATH, output, runner=multica)
    multica.comments.append(
        {
            "id": "comment-1",
            "creator_type": "member",
            "creator_id": MEMBER_ID,
            "created_at": "2026-08-10T08:04:00Z",
            "content": "缺少 en 维度下钻边界场景：补充 CASE-001 的 en 分支断言",
        }
    )
    multica.issue["status"] = "blocked"
    multica.issue["updated_at"] = "2026-08-10T08:05:00Z"

    outcome = sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )

    assert outcome["decision"] == "request_changes"
    assert outcome["next_node"] == "A08"
    decision = read_json(output / DECISION_FILE)
    assert decision["reason"] == "缺少 en 维度下钻边界场景：补充 CASE-001 的 en 分支断言"
    assert decision["reviewer_comment"]["id"] == "comment-1"
    assert decision["multica_event"]["comment_id"] == "comment-1"


def test_g02_done_with_confirm_comment_records_approved_reason(
    tmp_path: Path,
) -> None:
    artifacts, output = prepare_valid_review(tmp_path)
    multica = FakeMultica()
    request = output / "g02-review-request.json"
    open_multica_test_case_review(request, POLICY_PATH, output, runner=multica)
    multica.comments.append(
        {
            "id": "comment-2",
            "creator_type": "member",
            "creator_id": MEMBER_ID,
            "created_at": "2026-08-10T08:04:00Z",
            "content": "确认无缺场景",
        }
    )
    multica.issue["status"] = "done"
    multica.issue["updated_at"] = "2026-08-10T08:05:00Z"

    outcome = sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )

    assert outcome["decision"] == "approved"
    decision = read_json(output / DECISION_FILE)
    assert decision["reason"] == "确认无缺场景"


def test_g02_blocked_ignores_comment_from_unauthorized_author(
    tmp_path: Path,
) -> None:
    artifacts, output = prepare_valid_review(tmp_path)
    multica = FakeMultica()
    request = output / "g02-review-request.json"
    open_multica_test_case_review(request, POLICY_PATH, output, runner=multica)
    multica.comments.append(
        {
            "id": "comment-3",
            "creator_type": "member",
            "creator_id": "not-the-reviewer",
            "created_at": "2026-08-10T08:04:00Z",
            "content": "请补充场景",
        }
    )
    multica.issue["status"] = "blocked"
    multica.issue["updated_at"] = "2026-08-10T08:05:00Z"

    outcome = sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )

    assert outcome["decision"] == "request_changes"
    decision = read_json(output / DECISION_FILE)
    assert decision["reviewer_comment"] is None
    assert "status transition to blocked" in decision["reason"]


def test_g02_rejects_wrong_assignee_and_stale_n04(tmp_path: Path) -> None:
    artifacts, output = prepare_valid_review(tmp_path)
    multica = FakeMultica()
    request = output / "g02-review-request.json"
    open_multica_test_case_review(request, POLICY_PATH, output, runner=multica)
    multica.issue["status"] = "done"
    multica.issue["assignee_id"] = "another-member"

    with pytest.raises(SecurityPolicyError, match="authorized reviewer"):
        sync_multica_test_case_review(
            request, artifacts[2], POLICY_PATH, output, runner=multica
        )

    stale = read_json(artifacts[2])
    stale["payload"]["correction_attempt"] = 99
    stale.pop("artifact_hash")
    from qa_agents.contracts import artifact_hash_from_mapping

    stale["artifact_hash"] = artifact_hash_from_mapping(stale)
    stale_path = tmp_path / "stale-n04.json"
    stale_path.write_text(json.dumps(stale), encoding="utf-8")
    with pytest.raises(ContractError, match="current N04 Artifact changed"):
        sync_multica_test_case_review(
            request, stale_path, POLICY_PATH, output, runner=multica
        )


def test_g02_recovers_missing_outcome_without_reprocessing_event(tmp_path: Path) -> None:
    artifacts, output = prepare_valid_review(tmp_path)
    multica = FakeMultica()
    request = output / "g02-review-request.json"
    open_multica_test_case_review(request, POLICY_PATH, output, runner=multica)
    multica.issue["status"] = "done"
    sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )
    (output / OUTCOME_FILE).unlink()
    call_count = len(multica.calls)

    recovered = sync_multica_test_case_review(
        request, artifacts[2], POLICY_PATH, output, runner=multica
    )

    assert recovered["next_node"] == "N25"
    assert (output / OUTCOME_FILE).exists()
    assert len(multica.calls) == call_count
