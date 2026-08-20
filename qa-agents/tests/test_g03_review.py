import json
from pathlib import Path

import pytest

from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer
from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.g03_review import (
    DECISION_FILE,
    OUTCOME_FILE,
    STATE_FILE,
    open_multica_automation_code_review,
    prepare_automation_code_review_request,
    sync_multica_automation_code_review,
)
from qa_agents.storage import ArtifactStore


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "policies" / "g03-review-policy.json"
WORKSPACE_ID = "457d700f-6c27-4a59-871d-c2c56bca9f46"
PROJECT_ID = "f2f893a2-55dc-414d-87d9-a483e51765d6"
MEMBER_ID = "c2c6b9c6-4fb9-4439-a4a5-de4e93784c54"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _generation(store: ArtifactStore, common: dict, artifact_id: str, component: str) -> ArtifactEnvelope:
    manifest = {
        "schema_version": "automation-manifest/1.0",
        "manifest_id": f"manifest-{component}",
        "generator_profile": f"{component}/1.0.0",
        "target_repository": {
            "repository_id": "pytest_for_bi",
            "access_class": "approved_automation_repository",
            "write_mode": "artifact_only_candidate",
        },
        "framework": "pytest",
        "language": "python",
        "case_mappings": [{"case_id": f"{component}-001", "expected_ids": ["E1"], "manual_expected_ids": [], "candidate_path": f"generated/{component}/test_a.py"}],
        "candidate_files": [{"path": f"generated/{component}/test_a.py", "content_hash": "sha256:abc"}],
        "execution": {"command": ["pytest", "-q"], "timeout_seconds": 600},
        "permissions": {"business_repository_write": False, "network": False, "secrets": []},
        "expected_artifacts": ["junit_xml"],
        "input_bindings": {},
    }
    artifact = ArtifactEnvelope(
        **common,
        artifact_id=artifact_id,
        producer=Producer(component_id=component, runtime="multica"),
        payload={
            "schema_version": "automation-generation/1.0",
            "manifest": manifest,
            "code_candidates": [{"path": f"generated/{component}/test_a.py", "content": "CASE_SPEC = {}", "content_hash": "sha256:abc"}],
            "rejected_cases": [],
        },
        status=ArtifactStatus.COMPLETED,
    )
    store.write_artifact(artifact)
    return artifact


def write_valid_c5_artifacts(root: Path, *, n05_passed: bool = True) -> dict[str, Path]:
    store = ArtifactStore(root)
    common = {
        "workflow_run_id": "multica-run-1",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
    }
    a14 = _generation(store, common, "a14-backend-automation-generation", "A14")
    a15 = _generation(store, common, "a15-contract-automation-generation", "A15")
    reviews = []
    for component, artifact_id in (("A18-BE", "a18-be-backend-automation-review"), ("A18-CT", "a18-ct-contract-automation-review")):
        review = ArtifactEnvelope(
            **common,
            artifact_id=artifact_id,
            producer=Producer(component_id=component, runtime="multica"),
            payload={
                "schema_version": "automation-review/1.0",
                "approved": True,
                "issues": [],
            },
            status=ArtifactStatus.COMPLETED,
        )
        store.write_artifact(review)
        reviews.append(review)
    n05 = ArtifactEnvelope(
        **common,
        artifact_id="n05-automation-code-check",
        producer=Producer(component_id="N05", runtime="deterministic"),
        payload={
            "schema_version": "automation-code-check/1.0",
            "passed": n05_passed,
            "fatal_security_violation": False,
            "issues": [],
            "repair_routes": [],
            "generation_count": 2,
            "planned_generation_count": 2,
            "rejected_cases": [],
        },
        status=ArtifactStatus.COMPLETED if n05_passed else ArtifactStatus.NEEDS_HUMAN,
    )
    store.write_artifact(n05)
    artifact_dir = root / "artifacts"
    return {
        "n05": artifact_dir / "n05-automation-code-check.json",
        "a14": artifact_dir / "a14-backend-automation-generation.json",
        "a15": artifact_dir / "a15-contract-automation-generation.json",
        "a18_be": artifact_dir / "a18-be-backend-automation-review.json",
        "a18_ct": artifact_dir / "a18-ct-contract-automation-review.json",
    }


class FakeMultica:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.comments: list[dict] = []
        self.issue = {
            "id": "g03-issue-1",
            "workspace_id": WORKSPACE_ID,
            "project_id": PROJECT_ID,
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
            return {"status": "ok"}
        if args[:2] == ["issue", "status"]:
            self.issue["status"] = args[3]
            return {"status": self.issue["status"]}
        if args[:2] == ["issue", "get"]:
            return dict(self.issue)
        if args[:3] == ["issue", "comment", "list"]:
            return {"comments": list(self.comments)}
        raise AssertionError(f"unexpected call: {args}")


def _prepare(tmp_path: Path) -> dict:
    paths = write_valid_c5_artifacts(tmp_path)
    request = prepare_automation_code_review_request(
        paths["n05"],
        {"A14": paths["a14"], "A15": paths["a15"]},
        {"A18-BE": paths["a18_be"], "A18-CT": paths["a18_ct"]},
        POLICY_PATH,
        tmp_path / "g03-auto",
    )
    return {**paths, "request": request, "review_dir": tmp_path / "g03-auto"}


def test_prepare_g03_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    setup = _prepare(tmp_path)
    assert setup["request"]["schema_version"] == "automation-code-review-request/1.0"
    assert setup["request"]["gate_id"] == "G03"
    assert setup["request"]["summary"]["candidate_count"] == 2
    assert setup["request"]["summary"]["n05_passed"] is True
    again = prepare_automation_code_review_request(
        setup["n05"],
        {"A14": setup["a14"], "A15": setup["a15"]},
        {"A18-BE": setup["a18_be"], "A18-CT": setup["a18_ct"]},
        POLICY_PATH,
        setup["review_dir"],
    )
    assert again["request_hash"] == setup["request"]["request_hash"]


def test_prepare_g03_lists_covered_cases_in_request_and_markdown(tmp_path: Path) -> None:
    setup = _prepare(tmp_path)
    cases = [item for item in setup["request"]["generation_cases"] if item["case_id"] == "A14-001"]
    assert len(cases) == 1
    assert cases[0]["candidate_path"] == "generated/A14/test_a.py"
    assert cases[0]["expected_ids"] == ["E1"]
    assert cases[0]["manual_expected_ids"] == []
    md = (setup["review_dir"] / "g03-review-request.md").read_text(encoding="utf-8")
    assert "本批候选覆盖 Case" in md
    assert "`A14-001`" in md
    assert "generated/A14/test_a.py" in md
    assert "E1" in md


def test_prepare_g03_includes_case_titles_from_n25(tmp_path: Path) -> None:
    setup = _prepare(tmp_path)
    store = ArtifactStore(tmp_path)
    common = {
        "workflow_run_id": "multica-run-1",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
    }
    n25 = ArtifactEnvelope(
        **common,
        artifact_id="n25-compiled-test-cases",
        producer=Producer(component_id="N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "compiled_cases": [
                {
                    "id": "A14-001",
                    "title": "自定义维度三类位置的专用错误与双语提示",
                    "risk": "critical",
                    "priority": "P0",
                }
            ],
        },
        status=ArtifactStatus.COMPLETED,
    )
    store.write_artifact(n25)
    request = prepare_automation_code_review_request(
        setup["n05"],
        {"A14": setup["a14"], "A15": setup["a15"]},
        {"A18-BE": setup["a18_be"], "A18-CT": setup["a18_ct"]},
        POLICY_PATH,
        tmp_path / "g03-with-n25",
        compiled_cases_path=tmp_path / "artifacts" / "n25-compiled-test-cases.json",
    )
    case = next(item for item in request["generation_cases"] if item["case_id"] == "A14-001")
    assert case["title"] == "自定义维度三类位置的专用错误与双语提示"
    assert case["risk"] == "critical"
    md = (tmp_path / "g03-with-n25" / "g03-review-request.md").read_text(encoding="utf-8")
    assert "自定义维度三类位置的专用错误与双语提示" in md


def test_prepare_g03_rejects_failed_n05(tmp_path: Path) -> None:
    paths = write_valid_c5_artifacts(tmp_path, n05_passed=False)
    with pytest.raises(ContractError):
        prepare_automation_code_review_request(
            paths["n05"],
            {"A14": paths["a14"], "A15": paths["a15"]},
            {"A18-BE": paths["a18_be"], "A18-CT": paths["a18_ct"]},
            POLICY_PATH,
            tmp_path / "g03-auto",
        )


def test_open_g03_creates_one_bound_multica_review_issue(tmp_path: Path) -> None:
    setup = _prepare(tmp_path)
    fake = FakeMultica()
    request_path = setup["review_dir"] / "g03-review-request.json"
    state = open_multica_automation_code_review(request_path, POLICY_PATH, setup["review_dir"], runner=fake)
    assert state["issue_id"] == "g03-issue-1"
    assert state["state"] == "waiting_for_review"
    issue = fake.issue
    assert issue["metadata"]["qa_gate_id"] == "G03"
    assert issue["metadata"]["qa_request_hash"] == setup["request"]["request_hash"]
    create_calls = [call for call in fake.calls if call[:2] == ["issue", "create"]]
    assert len(create_calls) == 1
    # idempotent re-open does not create a second issue
    again = open_multica_automation_code_review(request_path, POLICY_PATH, setup["review_dir"], runner=fake)
    assert again["issue_id"] == "g03-issue-1"
    assert len([call for call in fake.calls if call[:2] == ["issue", "create"]]) == 1


def test_g03_done_resumes_into_n08(tmp_path: Path) -> None:
    setup = _prepare(tmp_path)
    fake = FakeMultica()
    request_path = setup["review_dir"] / "g03-review-request.json"
    open_multica_automation_code_review(request_path, POLICY_PATH, setup["review_dir"], runner=fake)
    fake.issue["status"] = "done"
    fake.issue["updated_at"] = "2026-08-10T09:00:00Z"
    outcome = sync_multica_automation_code_review(
        request_path, setup["n05"], POLICY_PATH, setup["review_dir"], runner=fake
    )
    assert outcome["decision"] == "approved"
    assert outcome["status"] == "completed"
    assert outcome["next_node"] == "N08"
    decision = read_json(setup["review_dir"] / DECISION_FILE)
    assert decision["actor"]["multica_member_id"] == MEMBER_ID


def test_g03_blocked_routes_back_to_n05_with_comment(tmp_path: Path) -> None:
    setup = _prepare(tmp_path)
    fake = FakeMultica()
    fake.comments.append(
        {
            "id": "c1",
            "created_at": "2026-08-10T09:05:00Z",
            "content": "候选包含禁止的 os 导入，请修正后重审。",
            "creator_type": "member",
            "creator_id": MEMBER_ID,
        }
    )
    request_path = setup["review_dir"] / "g03-review-request.json"
    open_multica_automation_code_review(request_path, POLICY_PATH, setup["review_dir"], runner=fake)
    fake.issue["status"] = "blocked"
    fake.issue["updated_at"] = "2026-08-10T09:10:00Z"
    outcome = sync_multica_automation_code_review(
        request_path, setup["n05"], POLICY_PATH, setup["review_dir"], runner=fake
    )
    assert outcome["decision"] == "request_changes"
    assert outcome["status"] == "blocked_input"
    assert outcome["next_node"] == "N05"
    decision = read_json(setup["review_dir"] / DECISION_FILE)
    assert decision["reason"] == "候选包含禁止的 os 导入，请修正后重审。"


def test_g03_rejects_wrong_assignee_and_stale_n05(tmp_path: Path) -> None:
    setup = _prepare(tmp_path)
    fake = FakeMultica()
    request_path = setup["review_dir"] / "g03-review-request.json"
    open_multica_automation_code_review(request_path, POLICY_PATH, setup["review_dir"], runner=fake)
    fake.issue["assignee_id"] = "somebody-else"
    fake.issue["status"] = "done"
    fake.issue["updated_at"] = "2026-08-10T09:00:00Z"
    with pytest.raises(SecurityPolicyError):
        sync_multica_automation_code_review(
            request_path, setup["n05"], POLICY_PATH, setup["review_dir"], runner=fake
        )
    fake.issue["assignee_id"] = MEMBER_ID
    # stale N05 hash: replace the n05 artifact
    store = ArtifactStore(tmp_path)
    stale = ArtifactEnvelope(
        workflow_run_id="multica-run-1",
        workflow_mode="new_requirement",
        artifact_id="n05-automation-code-check",
        source_snapshot_id="snapshot-1",
        producer=Producer(component_id="N05", runtime="deterministic"),
        payload={"schema_version": "automation-code-check/1.0", "passed": True, "issues": []},
        status=ArtifactStatus.COMPLETED,
    )
    store.write_artifact(stale)
    with pytest.raises(ContractError):
        sync_multica_automation_code_review(
            request_path, tmp_path / "artifacts" / "n05-automation-code-check.json",
            POLICY_PATH, setup["review_dir"], runner=fake,
        )
