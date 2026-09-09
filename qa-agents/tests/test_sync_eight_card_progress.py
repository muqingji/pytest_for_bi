import json
from pathlib import Path
import shutil

import importlib.util
import pytest

from qa_agents.contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    content_hash,
)
from qa_agents.multica import (
    ContractError,
    prepare_multica_automation_generation_input,
    prepare_multica_automation_review_input,
    prepare_multica_oracle_review_input,
    prepare_multica_test_data_plan_input,
    prepare_multica_test_data_plan_revision_input,
)
from qa_agents.security import SecurityPolicy
from qa_agents.storage import ArtifactStore

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_eight_card_progress.py"
_spec = importlib.util.spec_from_file_location("sync_eight_card_progress", _SCRIPT_PATH)
_sync_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_sync_module)
ensure_g01_scope_review = _sync_module.ensure_g01_scope_review
prepare_reconcile_spec = _sync_module.prepare_reconcile_spec
publish_g01_decision_artifact = _sync_module.publish_g01_decision_artifact
ensure_n24_test_strategy = _sync_module.ensure_n24_test_strategy
ensure_a06_dispatch = _sync_module.ensure_a06_dispatch
ensure_a08_dispatch = _sync_module.ensure_a08_dispatch
ensure_a08_correction_dispatch = _sync_module.ensure_a08_correction_dispatch
ensure_a09_dispatch = _sync_module.ensure_a09_dispatch
ensure_a09_correction_dispatch = _sync_module.ensure_a09_correction_dispatch
ensure_n04_validation = _sync_module.ensure_n04_validation
ensure_g02_review = _sync_module.ensure_g02_review
ensure_g02_correction_dispatch = _sync_module.ensure_g02_correction_dispatch
ensure_human_correction_dispatch = _sync_module.ensure_human_correction_dispatch
ensure_n25_compilation = _sync_module.ensure_n25_compilation
ensure_a11_dispatch = _sync_module.ensure_a11_dispatch
ensure_n26_selection = _sync_module.ensure_n26_selection
ensure_n15_execution_plan = _sync_module.ensure_n15_execution_plan
ensure_node_record_issues = _sync_module.ensure_node_record_issues
_refresh_waiting_node_cards = _sync_module._refresh_waiting_node_cards
ensure_a14_dispatch = _sync_module.ensure_a14_dispatch
ensure_a15_dispatch = _sync_module.ensure_a15_dispatch
ensure_a22_dispatch = _sync_module.ensure_a22_dispatch
ensure_a18_dispatch = _sync_module.ensure_a18_dispatch
ensure_a18_be_deterministic_review = _sync_module.ensure_a18_be_deterministic_review
_already_ingested = _sync_module._already_ingested
_completed_run_ingest_action = _sync_module._completed_run_ingest_action
ensure_n27_validation = _sync_module.ensure_n27_validation
ensure_a22_correction_dispatch = _sync_module.ensure_a22_correction_dispatch
ensure_n05_aggregation = _sync_module.ensure_n05_aggregation
ensure_g03_review = _sync_module.ensure_g03_review
ensure_n07_precheck = _sync_module.ensure_n07_precheck
ensure_quality_tail = _sync_module.ensure_quality_tail
_comment_artifact_output = _sync_module._comment_artifact_output
_ingest_issue = _sync_module._ingest_issue

PILOT_RUN = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pilot"
QA_AGENTS_ROOT = Path(__file__).resolve().parents[1]


def test_node_dispatch_rejects_node_missing_from_monitor_plan(
    tmp_path: Path, monkeypatch
) -> None:
    plan = {
        "schema_version": "dispatch-authorization/1.0",
        "workflow_run_id": "run-1",
        "allowed_nodes": ["A03"],
    }
    plan["plan_hash"] = content_hash(plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    input_path = tmp_path / "a02-input.json"
    input_path.write_text(json.dumps({"bundle_hash": "sha256:bundle"}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(_sync_module, "_multica", lambda *args, **kwargs: calls.append(args))

    _sync_module._load_dispatch_authorization(plan_path, "run-1")
    try:
        with pytest.raises(ContractError, match="A02 was not authorized"):
            _sync_module._create_node_issue(
                config={
                    "internal_project_id": "project",
                    "workspace_id": "workspace",
                    "node_agents": {"A02": "agent"},
                },
                run_id="run-1",
                node_id="A02",
                label="需求分析",
                input_path=input_path,
            )
    finally:
        _sync_module._load_dispatch_authorization(None, "run-1")
    assert calls == []


def test_ensure_a06_dispatch_records_issue_bundle_binding(
    tmp_path: Path, monkeypatch
) -> None:
    auto_dir = tmp_path / "artifacts-auto"
    inputs_dir = tmp_path / "inputs"
    artifacts = auto_dir / "artifacts"
    artifacts.mkdir(parents=True)
    for artifact_id in (
        "a02-requirement-analysis",
        "a03-technical-testability-analysis",
        "a05-backend-change-analysis",
    ):
        (artifacts / f"{artifact_id}.json").write_text("{}", encoding="utf-8")

    def fake_prepare(_artifact_dir: Path, target_dir: Path) -> dict:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "a06-input.json").write_text("{}", encoding="utf-8")
        return {"bundle_hash": "sha256:test"}

    monkeypatch.setattr(_sync_module, "prepare_multica_alignment_input", fake_prepare)
    monkeypatch.setattr(
        _sync_module,
        "_create_node_issue",
        lambda **kwargs: {"issue_id": "issue-a06", "issue_identifier": "QAA-1"},
    )

    result = ensure_a06_dispatch(
        {}, "run-1", auto_dir, inputs_dir, tmp_path, {}, apply=True
    )

    assert result["issue_id"] == "issue-a06"
    bindings = json.loads((inputs_dir / ".issue-bundles.json").read_text(encoding="utf-8"))
    assert bindings == {"issue-a06": str((inputs_dir / "a06-input.json").resolve())}


def test_ensure_a06_dispatch_repairs_missing_existing_issue_binding(tmp_path: Path) -> None:
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    bundle = inputs_dir / "a06-input.json"
    bundle.write_text("{}", encoding="utf-8")

    result = ensure_a06_dispatch(
        {},
        "run-1",
        tmp_path / "artifacts-auto",
        inputs_dir,
        tmp_path,
        {"A06": [{"id": "existing-a06", "status": "in_progress"}]},
        apply=True,
    )

    assert result == {
        "node_id": "A06",
        "action": "already_dispatched",
        "issue_id": "existing-a06",
    }
    bindings = json.loads((inputs_dir / ".issue-bundles.json").read_text(encoding="utf-8"))
    assert bindings == {"existing-a06": str(bundle.resolve())}


def _write_artifact(dir_path: Path, artifact_id: str, payload: dict, status: ArtifactStatus) -> None:
    envelope = ArtifactEnvelope(
        workflow_run_id="REQ-1-r001",
        workflow_mode="new_requirement",
        artifact_id=artifact_id,
        source_snapshot_id="snapshot-1",
        producer=Producer("N01"),
        payload=payload,
        status=status,
    )
    (dir_path / "artifacts").mkdir(parents=True, exist_ok=True)
    (dir_path / "artifacts" / f"{artifact_id}.json").write_text(
        json.dumps(envelope.to_dict(), ensure_ascii=False), encoding="utf-8"
    )


def _policy(tmp_path: Path) -> Path:
    policy = {
        "schema_version": "g01-review-policy/1.1",
        "allowed_roles": ["qa_owner"],
        "allowed_dispositions": ["confirmed"],
        "required_roles_by_source": {"A02": ["qa_owner"], "A03": ["qa_owner"], "A06": ["qa_owner"]},
        "approval_mode": "qa_owner_single_signoff",
        "policy_scope": "pilot_test_design_only",
        "temporary_policy": True,
        "production_release_authority": False,
        "required_approval_fields": ["test_rules"],
        "approval_rule": "all_review_issues_confirmed_or_resolved_upstream",
        "agent_approval_allowed": False,
    }
    path = tmp_path / "g01-policy.json"
    path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    return path


def test_prepare_reconcile_spec_merges_binding_without_revision_regression(
    tmp_path: Path,
) -> None:
    current_dir = tmp_path / "current"
    current_dir.mkdir()
    current_path = current_dir / "workflow-center-spec.json"
    current_path.write_text(
        json.dumps(
            {
                "workflow_run_id": "run-1",
                "revision": 8,
                "nodes": [
                    {"node_id": "G01", "state": "waiting_human"},
                    {"node_id": "N24", "state": "not_started"},
                ],
            }
        ),
        encoding="utf-8",
    )
    recovered_path = tmp_path / "recovered.json"
    recovered_path.write_text(
        json.dumps(
            {
                "workflow_run_id": "run-1",
                "revision": 1,
                "nodes": [
                    {
                        "node_id": "G01",
                        "state": "not_started",
                        "issue_id": "issue-274",
                        "issue_identifier": "QAA-274",
                    },
                    {"node_id": "N24", "state": "running"},
                ],
            }
        ),
        encoding="utf-8",
    )
    projection_path = tmp_path / "workflow-projection.json"
    projection_path.write_text(json.dumps({"revision": 10}), encoding="utf-8")

    merged_path = prepare_reconcile_spec(
        recovered_path,
        current_path,
        published_projection_path=projection_path,
    )

    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    assert merged["revision"] == 11
    assert merged["nodes"][0] == {
        "node_id": "G01",
        "state": "waiting_human",
        "issue_id": "issue-274",
        "issue_identifier": "QAA-274",
    }
    assert merged["nodes"][1]["state"] == "not_started"


def test_ensure_g01_scope_review_builds_plain_chinese_request(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {"ambiguities": [{"id": "AMB-001", "message": "多限制提示优先级未规定"}]},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": [{"id": "BI-001", "summary": "文案口径未定", "recommendation": "确认端无关文案"}]},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {"findings": [{"id": "FIND-001", "severity": "high", "type": "conflict", "summary": "filter.fieldName 未解析"}]},
        ArtifactStatus.NEEDS_HUMAN,
    )

    first = ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=tmp_path / "g01-auto")
    assert first is not None
    assert first["reused"] is False
    assert first["issue_count"] == 3
    assert (tmp_path / "g01-auto" / "g01-review-request.md").exists()
    decision_template = json.loads(
        (tmp_path / "g01-auto" / "g01-decision-template.json").read_text(encoding="utf-8")
    )
    assert decision_template["decision"] == ""
    assert len(decision_template["resolutions"]) == 3
    target = artifact_dir / "artifacts" / "g01-scope-review.json"
    assert target.exists()
    envelope = json.loads(target.read_text(encoding="utf-8"))
    assert envelope["artifact_id"] == "g01-scope-review"
    assert envelope["status"] == "needs_human"
    issues = envelope["payload"]["issues"]
    assert [item["source"] for item in issues] == ["A02", "A03", "A06"]
    assert issues[0]["category"] == "待确认需求"
    assert issues[1]["category"] == "待确认技术方案"
    assert issues[2]["category"] == "待确认测试范围"
    assert "需求文档里没有写清楚" in issues[0]["plain_summary"]
    assert "筛选字段名称" in issues[2]["plain_summary"]

    second = ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=tmp_path / "g01-auto")
    assert second is not None
    assert second["reused"] is True


def test_ensure_g01_scope_review_completes_without_review_items(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {"ambiguities": []},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": []},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {"findings": []},
        ArtifactStatus.COMPLETED,
    )
    result = ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=tmp_path / "g01-auto")
    assert result == {
        "artifact_id": "g01-scope-review",
        "status": "completed",
        "reused": False,
        "issue_count": 0,
    }
    envelope = json.loads(
        (artifact_dir / "artifacts" / "g01-scope-review.json").read_text(encoding="utf-8")
    )
    assert envelope["status"] == "completed"
    assert envelope["payload"]["decision"] == "not_required"


def test_ensure_g01_scope_review_uses_a02_items_when_a06_completed(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {"ambiguities": [{"id": "AMB-001", "message": "移动端范围未规定"}]},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": []},
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {"findings": []},
        ArtifactStatus.COMPLETED,
    )

    result = ensure_g01_scope_review(
        artifact_dir, _policy(tmp_path), output_dir=tmp_path / "g01-auto"
    )

    assert result is not None
    assert result["status"] == "needs_human"
    assert result["issue_count"] == 1
    envelope = json.loads(
        (artifact_dir / "artifacts" / "g01-scope-review.json").read_text(encoding="utf-8")
    )
    assert envelope["payload"]["issues"][0]["source"] == "A02"


def test_ensure_g01_archives_state_when_followup_request_changes(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(artifact_dir, "a02-requirement-analysis", {"ambiguities": [{"id": "AMB-1", "message": "特殊what/whatlist范围未明确"}]}, ArtifactStatus.COMPLETED_WITH_GAPS)
    _write_artifact(artifact_dir, "a03-technical-testability-analysis", {"blocking_items": []}, ArtifactStatus.COMPLETED)
    _write_artifact(artifact_dir, "a06-alignment-result", {"findings": [{"id": "F-2", "type": "conflict", "summary": "whatlist 当前实现位置与方案不同"}]}, ArtifactStatus.NEEDS_HUMAN)
    output = tmp_path / "g01-auto"
    output.mkdir()
    (output / "g01-review-request.json").write_text(json.dumps({"workflow_run_id": "REQ-1-r001", "issues": [{"issue_id": "A02:AMB-1", "plain_summary": "特殊what/whatlist范围未明确", "detail": {"message": "特殊what/whatlist范围未明确"}}]}), encoding="utf-8")
    (output / "g01-review-decision.json").write_text(json.dumps({"workflow_run_id": "REQ-1-r001", "decision": "request_changes", "resolutions": [{"issue_id": "A02:AMB-1", "disposition": "return_to_a06"}]}), encoding="utf-8")
    (output / "g01-workflow-state.json").write_text(json.dumps({"request_hash": "sha256:old"}), encoding="utf-8")

    result = ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=output)

    assert result["issue_count"] == 1
    assert not (output / "g01-workflow-state.json").exists()
    assert (output / "history" / "old" / "g01-workflow-state.json").exists()


def _approved_decision(request: dict) -> dict:
    return {
        "schema_version": "scope-review-decision/1.0",
        "gate_id": "G01",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "decision": "approved",
        "decided_at": "2026-08-17T09:10:11+00:00",
        "actor": {"type": "human", "id": "muqj11262", "role": "qa_owner"},
        "reason": "已逐项回复并确认",
        "test_rules": "按逐项回复冻结的口径执行测试设计",
        "resolutions": [
            {
                "issue_id": item["issue_id"],
                "disposition": "confirmed",
                "rationale": "已确认",
                "owner": "QA Owner",
            }
            for item in request["issues"]
        ],
        "decision_hash": "sha256:test-decision",
    }


def test_publish_g01_decision_artifact_terminates_gate(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {"ambiguities": [{"id": "AMB-1", "message": "特殊what/whatlist范围未明确"}]},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": []},
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {"findings": [{"id": "F-2", "type": "conflict", "summary": "实现与方案位置不同"}]},
        ArtifactStatus.NEEDS_HUMAN,
    )
    review_dir = tmp_path / "g01-auto"
    ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=review_dir)
    request = json.loads(
        (review_dir / "g01-review-request.json").read_text(encoding="utf-8")
    )
    (review_dir / "g01-review-decision.json").write_text(
        json.dumps(_approved_decision(request), ensure_ascii=False), encoding="utf-8"
    )

    result = publish_g01_decision_artifact(artifact_dir, review_dir)

    assert result["status"] == "completed"
    target = artifact_dir / "artifacts" / "g01-scope-review.json"
    envelope = json.loads(target.read_text(encoding="utf-8"))
    assert envelope["status"] == "completed"
    assert envelope["payload"]["decision"] == "approved"

    second = ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=review_dir)
    assert second["status"] == "completed"
    after = json.loads(target.read_text(encoding="utf-8"))
    assert after["status"] == "completed"
    assert after["payload"]["issue_count"] == 0


def test_ensure_g01_carries_forward_confirmed_scope(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {"ambiguities": [{"id": "AMB-1", "message": "特殊what/whatlist范围未明确"}]},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": []},
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {
            "findings": [
                {"id": "F-2", "type": "conflict", "summary": "whatlist 当前实现位置与方案不同"},
                {
                    "id": "F-12",
                    "type": "out_of_scope_change",
                    "summary": "员工或部门主题特殊分支将本地化消息改为空字符串",
                },
            ]
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    review_dir = tmp_path / "g01-auto"
    ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=review_dir)
    request = json.loads(
        (review_dir / "g01-review-request.json").read_text(encoding="utf-8")
    )
    first_ids = [item["issue_id"] for item in request["issues"]]
    assert "A02:AMB-1" in first_ids
    assert "A06:F-12" in first_ids
    decision = _approved_decision(request)
    decision["resolutions"] = [
        resolution
        for resolution in decision["resolutions"]
        if resolution["issue_id"] != "A06:F-12"
    ]
    (review_dir / "g01-review-decision.json").write_text(
        json.dumps(decision, ensure_ascii=False), encoding="utf-8"
    )

    result = ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=review_dir)

    assert result["issue_count"] == 1
    rebuilt = json.loads(
        (review_dir / "g01-review-request.json").read_text(encoding="utf-8")
    )
    assert [item["issue_id"] for item in rebuilt["issues"]] == ["A06:F-12"]
    assert "新增待确认项" in rebuilt["issues"][0]["review_reason"]


def test_ensure_g01_aggregates_all_prior_decisions(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {
            "ambiguities": [
                {"id": "AMB-1", "message": "特殊what/whatlist范围未明确"},
                {"id": "AMB-2", "message": "目标语言与英文译文未指定"},
            ]
        },
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": []},
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {
            "findings": [
                {"id": "F-12", "type": "out_of_scope_change", "summary": "员工主题错误分支改为空字符串"}
            ]
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    review_dir = tmp_path / "g01-auto"
    older_dir = tmp_path / "g01-c2"
    older_dir.mkdir()
    policy = _policy(tmp_path)
    first = ensure_g01_scope_review(artifact_dir, policy, output_dir=review_dir)
    assert first["issue_count"] == 3
    request = json.loads(
        (review_dir / "g01-review-request.json").read_text(encoding="utf-8")
    )
    round1 = {
        "schema_version": "scope-review-decision/1.0",
        "gate_id": "G01",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": "sha256:round-1",
        "decision": "request_changes",
        "decided_at": "2026-08-17T08:00:00+00:00",
        "actor": {"type": "human", "id": "muqj11262", "role": "qa_owner"},
        "reason": "存在未理解问题",
        "test_rules": "按当前口径执行",
        "resolutions": [
            {"issue_id": "A02:AMB-1", "disposition": "return_to_a06", "rationale": "没看明白", "owner": "A06"},
            {"issue_id": "A02:AMB-2", "disposition": "return_to_a06", "rationale": "没看明白", "owner": "A06"},
        ],
        "decision_hash": "sha256:round-1-decision",
    }
    (older_dir / "g01-review-decision.json").write_text(
        json.dumps(round1, ensure_ascii=False), encoding="utf-8"
    )
    round2 = {
        "schema_version": "scope-review-decision/1.0",
        "gate_id": "G01",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "decision": "approved",
        "decided_at": "2026-08-17T09:00:00+00:00",
        "actor": {"type": "human", "id": "muqj11262", "role": "qa_owner"},
        "reason": "已逐项回复并确认",
        "test_rules": "按逐项回复冻结的口径执行",
        "resolutions": [
            {
                "issue_id": "A06:FOLLOWUP-A06-ALN-F010",
                "disposition": "confirmed",
                "rationale": "确认",
                "owner": "QA Owner",
                "topic_key": "what_whatlist",
            }
        ],
        "decision_hash": "sha256:round-2-decision",
    }
    (review_dir / "g01-review-decision.json").write_text(
        json.dumps(round2, ensure_ascii=False), encoding="utf-8"
    )

    result = ensure_g01_scope_review(artifact_dir, policy, output_dir=review_dir)

    assert result["issue_count"] == 1
    rebuilt = json.loads(
        (review_dir / "g01-review-request.json").read_text(encoding="utf-8")
    )
    assert [item["issue_id"] for item in rebuilt["issues"]] == ["A06:F-12"]
def test_ensure_n24_test_strategy_runs_after_g01_approval(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {"ambiguities": []},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": []},
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {"findings": [{"id": "F-2", "type": "conflict", "severity": "high", "summary": "实现与方案位置不同"}]},
        ArtifactStatus.NEEDS_HUMAN,
    )
    review_dir = tmp_path / "g01-auto"
    ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=review_dir)
    request = json.loads(
        (review_dir / "g01-review-request.json").read_text(encoding="utf-8")
    )
    decision = _approved_decision(request)
    for resolution in decision["resolutions"]:
        resolution["approvals"] = [
            {"type": "human", "id": "muqj11262", "role": "qa_owner"}
        ]
    decision["decision_hash"] = content_hash(
        {key: value for key, value in decision.items() if key != "decision_hash"}
    )
    (review_dir / "g01-review-decision.json").write_text(
        json.dumps(decision, ensure_ascii=False), encoding="utf-8"
    )

    workflow_input = tmp_path / "workflow-input.json"
    workflow_input.write_text(
        json.dumps(
            {
                "schema_version": "pilot-workflow-input/1.0",
                "workflow_mode": "new_requirement",
                "title": "测试需求",
                "component_applicability": {
                    "backend": {"status": "applicable"},
                    "contract": {"status": "applicable"},
                    "e2e": {"status": "applicable"},
                },
                "source_access_policy": {
                    "business_repositories": "read_only",
                    "use_mutable_local_worktree": False,
                    "allow_business_repository_metadata_writes": False,
                    "writable_targets": ["workflow_artifact_store"],
                },
            }
        ),
        encoding="utf-8",
    )
    source_snapshot = tmp_path / "source-snapshot.json"
    source_snapshot.write_text(
        json.dumps(
            {
                "schema_version": "pilot-source-snapshot/1.0",
                "snapshot_id": "snapshot-1",
                "integrity": {
                    "source_credentials_embedded": False,
                    "business_repository_write_allowed": False,
                    "oracle_included_in_agent_input": False,
                },
                "implementation_source": {
                    "repository_id": "fs-bi",
                    "repository": "fs-bi",
                    "commit": "c6b785344c6973b6d6fc5bb108c45b3971f36c64",
                    "commit_kind": "single",
                    "parents": ["parent-1"],
                    "access_class": "business_source_read_only",
                    "comparison": {
                        "mode": "first_parent",
                        "base": "parent-1",
                        "head": "c6b785344c6973b6d6fc5bb108c45b3971f36c64",
                    },
                    "change_summary": {
                        "changed_paths": ["fs-bi-stat/src/main/java/Test.java"]
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    risk_policy = tmp_path / "risk-policy.json"
    risk_policy.write_text(
        json.dumps(
            {
                "schema_version": "risk-policy/1.0",
                "high_severity_finding_score": 4,
                "medium_severity_finding_score": 2,
                "high_risk_keyword_score": 6,
                "large_change_file_threshold": 30,
                "medium_risk_score": 2,
                "high_risk_score": 6,
                "critical_risk_score": 10,
                "high_risk_keywords": [],
                "security_keywords": [],
                "data_keywords": [],
                "mandatory_layers": {
                    "backend": "backend",
                    "contract": "contract",
                    "e2e": "e2e",
                },
            }
        ),
        encoding="utf-8",
    )
    config = {
        "g01_policy": str(_policy(tmp_path)),
        "n24_workflow_input": str(workflow_input),
        "n24_source_snapshot": str(source_snapshot),
        "n24_risk_policy": str(risk_policy),
    }

    result = ensure_n24_test_strategy(config, artifact_dir, review_dir, tmp_path)

    assert result is not None
    assert result["artifact_id"] == "n24-test-strategy"
    target = artifact_dir / "artifacts" / "n24-test-strategy.json"
    envelope = json.loads(target.read_text(encoding="utf-8"))
    assert envelope["artifact_id"] == "n24-test-strategy"
    assert envelope["payload"]["required_layers"] == ["backend", "contract", "e2e"]
    assert ensure_n24_test_strategy(config, artifact_dir, review_dir, tmp_path) is None


def test_ensure_n24_test_strategy_skips_without_approval(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {"ambiguities": []},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": []},
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {"findings": []},
        ArtifactStatus.NEEDS_HUMAN,
    )
    review_dir = tmp_path / "g01-auto"
    ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=review_dir)
    config = {"g01_policy": str(_policy(tmp_path))}

    assert ensure_n24_test_strategy(config, artifact_dir, review_dir, tmp_path) is None


def _write_n24_strategy(
    artifact_dir: Path, a06_artifact_hash: str, decision_hash: str
) -> None:
    envelope = ArtifactEnvelope(
        workflow_run_id="REQ-1-r001",
        workflow_mode="new_requirement",
        artifact_id="n24-test-strategy",
        source_snapshot_id="snapshot-1",
        producer=Producer("N24"),
        payload={
            "schema_version": "test-strategy/1.0",
            "risk_level": "critical",
            "risk_score": 42,
            "required_layers": ["backend", "contract", "e2e"],
            "required_non_functional": [],
            "human_gates": {"test_case_ir_review": "required"},
            "unresolved_items": [],
            "reasons": [],
            "policy_version": "risk-policy/1.0",
        },
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a06-alignment-result",
                location="payload",
                content_hash=a06_artifact_hash,
            ),
            EvidenceRef(
                source_type="human_gate_decision",
                source_id="G01",
                location="g01-review-decision.json",
                content_hash=decision_hash,
            ),
        ),
    )
    ArtifactStore(artifact_dir).write_artifact(envelope)


def _approved_g01_setup(tmp_path: Path) -> dict:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a02-requirement-analysis",
        {"ambiguities": [{"id": "AMB-1", "message": "特殊what/whatlist范围未明确"}]},
        ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    _write_artifact(
        artifact_dir,
        "a03-technical-testability-analysis",
        {"blocking_items": []},
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "a06-alignment-result",
        {"findings": [{"id": "F-2", "type": "conflict", "summary": "whatlist 当前实现位置与方案不同"}]},
        ArtifactStatus.NEEDS_HUMAN,
    )
    review_dir = tmp_path / "g01-auto"
    ensure_g01_scope_review(artifact_dir, _policy(tmp_path), output_dir=review_dir)
    request = json.loads(
        (review_dir / "g01-review-request.json").read_text(encoding="utf-8")
    )
    decision = _approved_decision(request)
    for resolution in decision["resolutions"]:
        resolution["approvals"] = [
            {"type": "human", "id": "muqj11262", "role": "qa_owner"}
        ]
    decision["decision_hash"] = content_hash(
        {key: value for key, value in decision.items() if key != "decision_hash"}
    )
    (review_dir / "g01-review-decision.json").write_text(
        json.dumps(decision, ensure_ascii=False), encoding="utf-8"
    )
    a06_hash = json.loads(
        (artifact_dir / "artifacts" / "a06-alignment-result.json").read_text(
            encoding="utf-8"
        )
    )["artifact_hash"]
    _write_n24_strategy(artifact_dir, a06_hash, decision["decision_hash"])
    prior_dir = tmp_path / "prior"
    prior_dir.mkdir()
    (prior_dir / "g01-review-decision.json").write_text(
        json.dumps(
            {
                "schema_version": "scope-review-decision/1.0",
                "gate_id": "G01",
                "workflow_run_id": "REQ-1-r000",
                "source_snapshot_id": "snapshot-1",
                "decision": "approved",
                "decided_at": "2026-08-17T08:00:00+00:00",
                "test_rules": {
                    "multiple_reasons": {"message_count": 1},
                    "metric_name": {"filter": "all_metric_display_names"},
                    "entry_consistency": {
                        "required_entries": ["web_chart", "web_joined_table"]
                    },
                    "custom_dimension": {
                        "error_key": "CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED"
                    },
                    "dynamic_relation": {
                        "error_key": "DYNAMIC_RELATION_METRIC_DETAIL_UNSUPPORTED"
                    },
                    "multi_relation": {
                        "error_key": "MULTI_RELATION_METRIC_DETAIL_UNSUPPORTED"
                    },
                    "permission": {"preserve_detection_order": True},
                    "compatibility": {"success_response": "unchanged"},
                    "localization": {
                        "errors": [
                            {
                                "key": "CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED",
                                "code": "s307011534",
                                "zh_CN": "维度或数据范围中使用了自定义维度字段",
                                "en": "Custom dimension fields are used.",
                                "parameters": [],
                            },
                            {
                                "key": "RESULT_SET_FILTER_DETAIL_UNSUPPORTED",
                                "code": "s307011535",
                                "zh_CN": "统计图数据范围中设置了「指标名称」按结果集筛选",
                                "en": "The chart data range uses Metric Name.",
                                "parameters": ["all_metric_display_names"],
                            },
                            {
                                "key": "MULTI_RELATION_METRIC_DETAIL_UNSUPPORTED",
                                "code": "s307011536",
                                "zh_CN": "基于多关联关系创建的统计指标，暂不支持查看明细",
                                "en": "Metrics created based on multiple relationships.",
                                "parameters": [],
                            },
                            {
                                "key": "DYNAMIC_RELATION_METRIC_DETAIL_UNSUPPORTED",
                                "code": "s307011537",
                                "zh_CN": "基于动态关联关系创建的统计指标，暂不支持查看明细",
                                "en": "Metrics created based on dynamic relationships.",
                                "parameters": [],
                            },
                        ]
                    },
                },
                "decision_hash": "sha256:prior",
            }
        ),
        encoding="utf-8",
    )
    return {
        "artifact_dir": artifact_dir,
        "review_dir": review_dir,
        "request": request,
        "decision": decision,
        "prior": prior_dir / "g01-review-decision.json",
    }


def _a08_config(tmp_path: Path, prior_path: Path) -> dict:
    instruction_path = tmp_path / "a08-v1.1.1.md"
    instruction_path.write_text(
        "# A08 测试设计 Agent v1.1.1\n按冻结附件执行测试设计。",
        encoding="utf-8",
    )
    return {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A08": "agent-a08", "A09": "agent-a09"},
        "node_instruction_files": {"A08": {"1.1.0": str(instruction_path)}},
        "g01_policy": str(_policy(tmp_path)),
        "prior_test_rules_paths": [str(prior_path)],
        "oracle_rule_library": str(
            QA_AGENTS_ROOT / "policies" / "oracle-rule-library.json"
        ),
    }


def test_ensure_a08_dispatch_prepares_input_in_dry_run(tmp_path: Path) -> None:
    setup = _approved_g01_setup(tmp_path)
    config = _a08_config(tmp_path, setup["prior"])
    result = ensure_a08_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        tmp_path / "inputs",
        setup["review_dir"],
        tmp_path,
        {},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch"
    bundle = json.loads(
        (tmp_path / "inputs" / "a08-input.json").read_text(encoding="utf-8")
    )
    scope = bundle["allowed_inputs"]["approved_scope"]
    assert scope["test_rule_fallback"]["mode"] == "prior_frozen_scope"
    assert scope["test_rule_instruction"] == "按逐项回复冻结的口径执行测试设计"
    assert (
        bundle["allowed_inputs"]["approved_scope"]["test_rules"]["localization"][
            "errors"
        ][0]["key"]
        == "CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED"
    )


def test_ensure_a08_dispatch_creates_issue_and_syncs_instruction(
    tmp_path: Path, monkeypatch
) -> None:
    setup = _approved_g01_setup(tmp_path)
    config = _a08_config(tmp_path, setup["prior"])
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("agent", "get"):
            return {"instructions": "# A08 测试设计 Agent v1.1.1"}
        if args[:2] == ("issue", "create"):
            return {"id": "issue-a08", "identifier": "QAA-900"}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    result = ensure_a08_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        tmp_path / "inputs",
        setup["review_dir"],
        tmp_path,
        {},
        apply=True,
    )
    assert result["action"] == "dispatched"
    assert result["issue_id"] == "issue-a08"
    created = next(
        call for call in calls if call[:2] == ["issue", "create"]
    )
    assert "--assignee-id" in created and "agent-a08" in created
    assert "--attachment" in created
    assert any("a08-input.json" in str(part) for part in created)


def test_ensure_a08_dispatch_is_idempotent_when_issue_exists(tmp_path: Path) -> None:
    setup = _approved_g01_setup(tmp_path)
    config = _a08_config(tmp_path, setup["prior"])
    result = ensure_a08_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        tmp_path / "inputs",
        setup["review_dir"],
        tmp_path,
        {
            "A08": [
                {"id": "issue-existing", "title": "[run-1] A08 测试设计", "status": "in_progress"}
            ]
        },
        apply=True,
    )
    assert result is not None
    assert result["action"] == "already_dispatched"
    assert result["issue_id"] == "issue-existing"


def test_ensure_a08_dispatch_reruns_after_failed_ingest(
    tmp_path: Path, monkeypatch
) -> None:
    setup = _approved_g01_setup(tmp_path)
    config = _a08_config(tmp_path, setup["prior"])
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("agent", "get"):
            return {"instructions": "# A08 测试设计 Agent v1.1.1"}
        if args[:2] == ("issue", "create"):
            return {"id": "issue-rerun", "identifier": "QAA-901"}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    result = ensure_a08_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        tmp_path / "inputs",
        setup["review_dir"],
        tmp_path,
        {
            "A08": [
                {"id": "issue-old", "title": "[run-1] A08 测试设计", "status": "done"}
            ]
        },
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["issue_id"] == "issue-rerun"
    created = next(call for call in calls if call[:2] == ["issue", "create"])
    assert any("a08-input.json" in str(part) for part in created)


def test_ensure_a08_dispatch_respects_rerun_budget(tmp_path: Path) -> None:
    setup = _approved_g01_setup(tmp_path)
    config = _a08_config(tmp_path, setup["prior"])
    config["agent_rerun_budget"] = 1
    result = ensure_a08_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        tmp_path / "inputs",
        setup["review_dir"],
        tmp_path,
        {
            "A08": [
                {"id": "issue-1", "title": "[run-1] A08 测试设计", "status": "done"},
                {"id": "issue-2", "title": "[run-1] A08 测试设计", "status": "done"},
            ]
        },
        apply=True,
    )
    assert result is not None
    assert result["action"] == "rerun_budget_exhausted"
    assert result["attempts"] == 2


def test_ensure_a09_dispatch_creates_issue(tmp_path: Path, monkeypatch) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    (artifact_dir / "artifacts").mkdir(parents=True)
    shutil.copyfile(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        artifact_dir / "artifacts" / "a08-test-design-ir.json",
    )
    shutil.copyfile(
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        inputs_dir / "a08-input.json",
    )
    config = {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A09": "agent-a09"},
        "oracle_rule_library": str(
            QA_AGENTS_ROOT / "policies" / "oracle-rule-library.json"
        ),
    }
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "create"):
            return {"id": "issue-a09", "identifier": "QAA-901"}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    result = ensure_a09_dispatch(
        config,
        "run-1",
        artifact_dir,
        inputs_dir,
        QA_AGENTS_ROOT,
        {},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert (inputs_dir / "a09-input.json").exists()
    created = next(call for call in calls if call[:2] == ["issue", "create"])
    assert any("a09-input.json" in str(part) for part in created)


def test_ensure_n04_validation_runs_after_a08_and_a09(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    (artifact_dir / "artifacts").mkdir(parents=True)
    shutil.copyfile(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        artifact_dir / "artifacts" / "a08-test-design-ir.json",
    )
    shutil.copyfile(
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        inputs_dir / "a08-input.json",
    )
    oracle_rules = QA_AGENTS_ROOT / "policies" / "oracle-rule-library.json"
    bundle = prepare_multica_oracle_review_input(
        artifact_dir / "artifacts" / "a08-test-design-ir.json",
        inputs_dir / "a08-input.json",
        oracle_rules,
        inputs_dir,
    )
    evidence = bundle["allowed_inputs"]["frozen_evidence"]
    design = bundle["allowed_inputs"]["test_design_ir"]
    cases = design["parent_cases"]
    case_ids = [case["id"] for case in cases]
    requirements = evidence["validated_analysis"]["requirement_analysis"]["requirements"]
    obligations = evidence["approved_scope"]["test_rule_obligations"]
    dimensions = bundle["allowed_inputs"]["oracle_rule_library"][
        "required_coverage_dimensions"
    ]
    output = {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "approved": True,
        "issues": [],
        "coverage_dimensions": [
            {
                "dimension": dimension,
                "status": "covered",
                "case_ids": case_ids,
                "source_refs": ["a08-test-design-ir"],
                "rationale": "reviewed",
            }
            for dimension in dimensions
        ],
        "requirement_coverage": [
            {
                "requirement_id": item["id"],
                "status": "covered",
                "case_ids": case_ids,
            }
            for item in requirements
        ],
        "test_rule_coverage": [
            {"rule_id": item["id"], "status": "covered", "case_ids": case_ids}
            for item in obligations
        ],
        "manual_case_recommendations": [],
        "code_coverage_reviewed": False,
        "evaluation_oracle_accessed": False,
    }
    from qa_agents.multica import ingest_multica_output

    ingest_multica_output(
        inputs_dir / "a09-input.json",
        json.dumps(output, ensure_ascii=False),
        artifact_dir,
        task_id="task-a09",
        issue_id="issue-a09",
        attachment_id="attachment-a09",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )

    assert ensure_n04_validation(artifact_dir, inputs_dir) is not None
    target = artifact_dir / "artifacts" / "n04-test-case-ir-validation.json"
    envelope = json.loads(target.read_text(encoding="utf-8"))
    assert envelope["artifact_id"] == "n04-test-case-ir-validation"
    assert ensure_n04_validation(artifact_dir, inputs_dir) is None


def test_ensure_n04_validation_skips_without_a09(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    (artifact_dir / "artifacts").mkdir(parents=True)
    shutil.copyfile(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        artifact_dir / "artifacts" / "a08-test-design-ir.json",
    )
    assert ensure_n04_validation(artifact_dir, inputs_dir) is None


def test_ensure_g02_review_opens_after_valid_n04(tmp_path: Path, monkeypatch) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    (artifact_dir / "artifacts").mkdir(parents=True)
    a08 = json.loads(
        (PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json").read_text(
            encoding="utf-8"
        )
    )
    (artifact_dir / "artifacts" / "a08-test-design-ir.json").write_text(
        json.dumps(a08, ensure_ascii=False), encoding="utf-8"
    )
    producer_a09 = Producer(
        component_id="A09",
        component_version="1.0.0",
        runtime="agent",
        profile_version="1.1.1",
        model_provider="openai",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
        tool_bundle_version="1.0.0",
    )
    a09 = ArtifactEnvelope(
        workflow_run_id=a08["workflow_run_id"],
        workflow_mode=a08["workflow_mode"],
        artifact_id="a09-oracle-coverage-review",
        source_snapshot_id=a08["source_snapshot_id"],
        producer=producer_a09,
        payload={
            "schema_version": "oracle-review/1.1",
            "workflow_run_id": a08["workflow_run_id"],
            "source_snapshot_id": a08["source_snapshot_id"],
            "approved": True,
            "issues": [],
            "coverage_dimensions": [],
            "requirement_coverage": [],
            "test_rule_coverage": [],
            "manual_case_recommendations": [],
            "code_coverage_reviewed": True,
            "evaluation_oracle_accessed": False,
        },
        status=ArtifactStatus.COMPLETED,
    ).to_dict()
    ArtifactStore(artifact_dir).write_artifact(
        ArtifactEnvelope(
            workflow_run_id=a08["workflow_run_id"],
            workflow_mode=a08["workflow_mode"],
            artifact_id="a09-oracle-coverage-review",
            source_snapshot_id=a08["source_snapshot_id"],
            producer=producer_a09,
            payload=a09["payload"],
            status=ArtifactStatus.COMPLETED,
        )
    )
    n04 = ArtifactEnvelope(
        workflow_run_id=a08["workflow_run_id"],
        workflow_mode=a08["workflow_mode"],
        artifact_id="n04-test-case-ir-validation",
        source_snapshot_id=a08["source_snapshot_id"],
        producer=Producer("N04"),
        payload={
            "schema_version": "test-case-ir-validation/1.0",
            "valid": True,
            "test_design_artifact_id": "a08-test-design-ir",
            "test_design_artifact_hash": a08["artifact_hash"],
            "oracle_review_artifact_id": "a09-oracle-coverage-review",
            "oracle_review_artifact_hash": a09["artifact_hash"],
            "issues": [],
            "issue_count": 0,
            "blocking_issue_count": 0,
            "route_summary": {},
            "correction_attempt": 1,
            "max_correction_attempts": 2,
            "next_node": "G02",
            "g02_status": "pending",
        },
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a08-test-design-ir",
                location="a08-test-design-ir.json",
                content_hash=a08["artifact_hash"],
            ),
            EvidenceRef(
                source_type="artifact",
                source_id="a09-oracle-coverage-review",
                location="a09-oracle-coverage-review.json",
                content_hash=a09["artifact_hash"],
            ),
        ),
        reason_code="test_case_ir_valid",
    ).to_dict()
    ArtifactStore(artifact_dir).write_artifact(
        ArtifactEnvelope(
            workflow_run_id=a08["workflow_run_id"],
            workflow_mode=a08["workflow_mode"],
            artifact_id="n04-test-case-ir-validation",
            source_snapshot_id=a08["source_snapshot_id"],
            producer=Producer("N04"),
            payload=n04["payload"],
            status=ArtifactStatus.COMPLETED,
            evidence_refs=(
                EvidenceRef(
                    source_type="artifact",
                    source_id="a08-test-design-ir",
                    location="a08-test-design-ir.json",
                    content_hash=a08["artifact_hash"],
                ),
                EvidenceRef(
                    source_type="artifact",
                    source_id="a09-oracle-coverage-review",
                    location="a09-oracle-coverage-review.json",
                    content_hash=a09["artifact_hash"],
                ),
            ),
            reason_code="test_case_ir_valid",
        )
    )

    config = {
        "g02_policy": str(QA_AGENTS_ROOT / "policies" / "g02-review-policy.json")
    }
    policy = json.loads(
        (QA_AGENTS_ROOT / "policies" / "g02-review-policy.json").read_text(
            encoding="utf-8"
        )
    )
    workspace_id = policy["multica"]["workspace_id"]

    def fake_runner(args: list, cwd: Path):
        if args[0] == "issue" and args[1] == "create":
            return {"id": "issue-g02", "workspace_id": workspace_id, "status": "todo"}
        if args[0] == "issue" and args[1] == "get":
            return {"id": "issue-g02", "status": "in_review"}
        return {}

    import qa_agents.g02_review as g02_module

    monkeypatch.setattr(g02_module, "_default_runner", fake_runner)
    result = ensure_g02_review(
        config,
        artifact_dir,
        tmp_path / "g02-auto",
        QA_AGENTS_ROOT,
        apply=True,
    )
    assert result is not None
    assert result["node_id"] == "G02"
    assert (tmp_path / "g02-auto" / "g02-review-request.json").exists()
    gate_artifact = json.loads(
        (artifact_dir / "artifacts" / "g02-test-case-ir-review.json").read_text(
            encoding="utf-8"
        )
    )
    assert gate_artifact["status"] == "needs_human"
    review_items = gate_artifact["payload"]["review_items"]
    assert isinstance(review_items, list) and review_items
    assert all(item.get("case_id") for item in review_items)
    assert gate_artifact["payload"]["review_summary"]["parent_case_count"] == len(review_items)


def test_ensure_g02_review_skips_without_valid_n04(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    config = {
        "g02_policy": str(QA_AGENTS_ROOT / "policies" / "g02-review-policy.json")
    }
    assert (
        ensure_g02_review(
            config, artifact_dir, tmp_path / "g02-auto", QA_AGENTS_ROOT, apply=True
        )
        is None
    )


def test_ensure_g02_review_binds_done_c3_and_unlocks_n25(
    tmp_path: Path, monkeypatch
) -> None:
    state = _correction_state(tmp_path)
    _flip_state_to_g02_ready(state)
    config = {
        "g02_policy": str(QA_AGENTS_ROOT / "policies" / "g02-review-policy.json")
    }
    policy = json.loads(
        (QA_AGENTS_ROOT / "policies" / "g02-review-policy.json").read_text(
            encoding="utf-8"
        )
    )
    workspace_id = policy["multica"]["workspace_id"]
    member_id = policy["multica"]["assignee_member_id"]
    metadata: dict[str, str] = {}
    status_calls: list[str] = []
    issue = {
        "id": "c3-issue",
        "workspace_id": workspace_id,
        "project_id": "84580297-a0ca-4cce-9db9-59cade66f83c",
        "assignee_id": member_id,
        "assignee_type": "member",
        "status": "done",
        "updated_at": "2026-09-01T12:00:00Z",
        "metadata": metadata,
    }

    def fake_runner(args: list, cwd: Path):
        if args[:2] == ["issue", "create"]:
            raise AssertionError("G02 must bind the C3 stage card")
        if args[:3] == ["issue", "metadata", "set"]:
            metadata[args[args.index("--key") + 1]] = args[args.index("--value") + 1]
            return {}
        if args[:2] == ["issue", "status"]:
            status_calls.append(args[3])
            issue["status"] = args[3]
            return dict(issue)
        if args[:2] == ["issue", "get"]:
            return {**issue, "metadata": dict(metadata)}
        if args[:3] == ["issue", "comment", "list"]:
            return {"comments": []}
        return {}

    import qa_agents.g02_review as g02_module

    monkeypatch.setattr(g02_module, "_default_runner", fake_runner)
    review_dir = tmp_path / "g02-auto"
    result = ensure_g02_review(
        config,
        state["artifact_dir"],
        review_dir,
        QA_AGENTS_ROOT,
        apply=True,
        issue_id="c3-issue",
    )
    assert result is not None
    assert result.get("error") is None
    assert "in_review" not in status_calls
    gate = json.loads(
        (state["artifact_dir"] / "artifacts" / "g02-test-case-ir-review.json").read_text(
            encoding="utf-8"
        )
    )
    assert gate["status"] == "completed"
    assert gate["payload"]["decision"] == "approved"
    n25 = ensure_n25_compilation(state["artifact_dir"], review_dir)
    assert n25 is not None
    assert n25["artifact_id"] == "n25-compiled-test-cases"


def test_ensure_g02_correction_dispatch_dispatches_a08_v140(
    tmp_path: Path, monkeypatch
) -> None:
    state = _correction_state(tmp_path)
    review_dir = _write_g02_returned_round(state, tmp_path)
    instruction_path = tmp_path / "a08-v1.4.0.md"
    instruction_path.write_text(
        "# A08 测试设计 Agent v1.4.0\n按 G02 评论修正。", encoding="utf-8"
    )
    config = {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A08": "agent-a08"},
        "node_instruction_files": {"A08": {"1.4.0": str(instruction_path)}},
    }
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("agent", "get"):
            return {"instructions": "# A08 测试设计 Agent v1.4.0"}
        if args[:2] == ("issue", "create"):
            return {"id": "issue-g02-corr", "identifier": "QAA-920"}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    result = ensure_g02_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        review_dir,
        state["inputs_dir"],
        tmp_path,
        {"A08": []},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["mode"] == "g02_reviewer_direction"
    assert result["correction_attempt"] == 2
    bundle = json.loads(
        (state["inputs_dir"] / "a08-correction-2" / "a08-input.json").read_text(
            encoding="utf-8"
        )
    )
    assert bundle["profile_version"] == "1.4.0"
    direction = bundle["allowed_inputs"]["g02_review_direction"]
    assert direction["reason"] == "缺少 en 下钻边界场景：补充 CASE 的 en 分支断言"
    assert direction["reviewer_comment"]["id"] == "g02-comment-1"
    marker = json.loads(
        (review_dir / "g02-correction-dispatched.json").read_text(encoding="utf-8")
    )
    assert marker["issue_id"] == "issue-g02-corr"
    registry = json.loads(
        (state["inputs_dir"] / ".issue-bundles.json").read_text(encoding="utf-8")
    )
    assert registry["issue-g02-corr"].endswith("a08-correction-2/a08-input.json")


def test_ensure_g02_correction_dispatch_is_idempotent(tmp_path: Path) -> None:
    state = _correction_state(tmp_path)
    review_dir = _write_g02_returned_round(state, tmp_path)
    outcome = json.loads(
        (review_dir / "g02-review-outcome.json").read_text(encoding="utf-8")
    )
    marker = {
        "outcome_hash": outcome["outcome_hash"],
        "decision_hash": outcome["decision_hash"],
        "issue_id": "issue-g02-corr",
        "input": "inputs/a08-correction-2/a08-input.json",
    }
    (review_dir / "g02-correction-dispatched.json").write_text(
        json.dumps(marker, ensure_ascii=False), encoding="utf-8"
    )
    config = {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A08": "agent-a08"},
    }
    result = ensure_g02_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        review_dir,
        state["inputs_dir"],
        tmp_path,
        {"A08": []},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "g02_correction_dispatched"


def test_ensure_a09_correction_dispatch_after_g02_return(
    tmp_path: Path, monkeypatch
) -> None:
    state = _correction_state(tmp_path)
    _ingest_g02_corrected_a08(state, tmp_path)
    config = {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A09": "agent-a09"},
        "oracle_rule_library": str(state["oracle_rules"]),
    }
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "create"):
            return {"id": "issue-a09-g02-corr", "identifier": "QAA-921"}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    result = ensure_a09_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        state["inputs_dir"],
        QA_AGENTS_ROOT,
        {"A09": []},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["mode"] == "correction"
    bundle = json.loads(
        (state["inputs_dir"] / "a09-correction-1" / "a09-input.json").read_text(
            encoding="utf-8"
        )
    )
    assert bundle["profile_id"] == "A09"


def test_ensure_g02_review_archives_stale_round_and_opens_fresh(
    tmp_path: Path, monkeypatch
) -> None:
    from qa_agents.contracts import artifact_hash_from_mapping

    state = _correction_state(tmp_path)
    _flip_state_to_g02_ready(state)
    n04_path = state["artifact_dir"] / "artifacts" / "n04-test-case-ir-validation.json"
    config = {
        "g02_policy": str(QA_AGENTS_ROOT / "policies" / "g02-review-policy.json")
    }
    policy = json.loads(
        (QA_AGENTS_ROOT / "policies" / "g02-review-policy.json").read_text(
            encoding="utf-8"
        )
    )
    workspace_id = policy["multica"]["workspace_id"]
    created: list[str] = []

    def fake_runner(args: list, cwd: Path):
        if args[:2] == ["issue", "create"]:
            issue_id = f"issue-g02-{len(created) + 1}"
            created.append(issue_id)
            return {"id": issue_id, "workspace_id": workspace_id, "status": "todo"}
        if args[:2] == ["issue", "get"]:
            return {"id": created[-1], "status": "in_review"}
        return {}

    import qa_agents.g02_review as g02_module

    monkeypatch.setattr(g02_module, "_default_runner", fake_runner)
    review_dir = tmp_path / "g02-auto"
    first = ensure_g02_review(
        config, state["artifact_dir"], review_dir, QA_AGENTS_ROOT, apply=True
    )
    assert first is not None
    assert first.get("archived_round") is None
    first_request = json.loads(
        (review_dir / "g02-review-request.json").read_text(encoding="utf-8")
    )

    envelope = json.loads(n04_path.read_text(encoding="utf-8"))
    envelope["payload"]["correction_attempt"] = (
        envelope["payload"].get("correction_attempt", 1) + 1
    )
    envelope.pop("artifact_hash", None)
    envelope["artifact_hash"] = artifact_hash_from_mapping(envelope)
    n04_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")

    second = ensure_g02_review(
        config, state["artifact_dir"], review_dir, QA_AGENTS_ROOT, apply=True
    )
    assert second is not None
    assert second.get("archived_round") is True
    assert len(created) == 2
    archives = [path for path in tmp_path.glob("g02-round-*") if path.is_dir()]
    assert len(archives) == 1
    second_request = json.loads(
        (review_dir / "g02-review-request.json").read_text(encoding="utf-8")
    )
    assert second_request["request_hash"] != first_request["request_hash"]


def test_ensure_g02_review_publishes_returned_artifact_on_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    state = _correction_state(tmp_path)
    _flip_state_to_g02_ready(state)
    config = {
        "g02_policy": str(QA_AGENTS_ROOT / "policies" / "g02-review-policy.json")
    }
    policy = json.loads(
        (QA_AGENTS_ROOT / "policies" / "g02-review-policy.json").read_text(
            encoding="utf-8"
        )
    )
    workspace_id = policy["multica"]["workspace_id"]
    member_id = policy["multica"]["assignee_member_id"]
    created: list[str] = []
    metadata: dict[str, str] = {}

    def fake_runner(args: list, cwd: Path):
        if args[:2] == ["issue", "create"]:
            issue_id = "issue-g02-returned"
            created.append(issue_id)
            return {"id": issue_id, "workspace_id": workspace_id, "status": "todo"}
        if args[:3] == ["issue", "metadata", "set"]:
            metadata[args[args.index("--key") + 1]] = args[args.index("--value") + 1]
            return {}
        if args[:2] == ["issue", "get"]:
            return {
                "id": "issue-g02-returned",
                "workspace_id": workspace_id,
                "project_id": policy["multica"]["project_id"],
                "assignee_id": member_id,
                "assignee_type": "member",
                "status": "blocked",
                "updated_at": "2026-08-10T08:05:00Z",
                "metadata": dict(metadata),
            }
        if args[:3] == ["issue", "comment", "list"]:
            return {
                "comments": [
                    {
                        "id": "comment-g02",
                        "creator_type": "member",
                        "creator_id": member_id,
                        "created_at": "2026-08-10T08:04:00Z",
                        "content": "补充 en 分支断言场景",
                    }
                ]
            }
        return {}

    import qa_agents.g02_review as g02_module

    monkeypatch.setattr(g02_module, "_default_runner", fake_runner)
    result = ensure_g02_review(
        config,
        state["artifact_dir"],
        tmp_path / "g02-auto",
        QA_AGENTS_ROOT,
        apply=True,
    )
    assert result is not None
    assert result["returned"] is True
    gate = json.loads(
        (
            state["artifact_dir"]
            / "artifacts"
            / "g02-test-case-ir-review.json"
        ).read_text(encoding="utf-8")
    )
    assert gate["status"] == "blocked_input"
    assert gate["payload"]["decision"] == "request_changes"


def _a09_review_output(bundle: dict, *, approved: bool, issues: list) -> dict:
    evidence = bundle["allowed_inputs"]["frozen_evidence"]
    design = bundle["allowed_inputs"]["test_design_ir"]
    cases = design["parent_cases"]
    case_ids = [case["id"] for case in cases]
    requirements = evidence["validated_analysis"]["requirement_analysis"]["requirements"]
    obligations = evidence["approved_scope"]["test_rule_obligations"]
    dimensions = bundle["allowed_inputs"]["oracle_rule_library"][
        "required_coverage_dimensions"
    ]
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed" if approved else "needs_human",
        "approved": approved,
        "issues": issues,
        "coverage_dimensions": [
            {
                "dimension": dimension,
                "status": "covered",
                "case_ids": case_ids,
                "source_refs": ["a08-test-design-ir"],
                "rationale": "reviewed",
            }
            for dimension in dimensions
        ],
        "requirement_coverage": [
            {"requirement_id": item["id"], "status": "covered", "case_ids": case_ids}
            for item in requirements
        ],
        "test_rule_coverage": [
            {"rule_id": item["id"], "status": "covered", "case_ids": case_ids}
            for item in obligations
        ],
        "manual_case_recommendations": [],
        "code_coverage_reviewed": False,
        "evaluation_oracle_accessed": False,
    }


def _correction_state(tmp_path: Path) -> dict:
    artifact_dir = tmp_path / "artifacts-auto"
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    (artifact_dir / "artifacts").mkdir(parents=True)
    shutil.copyfile(
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        inputs_dir / "a08-input.json",
    )
    from qa_agents.multica import ingest_multica_output

    original_bundle = json.loads(
        (inputs_dir / "a08-input.json").read_text(encoding="utf-8")
    )
    ingest_multica_output(
        inputs_dir / "a08-input.json",
        json.dumps(_valid_a08_design(original_bundle), ensure_ascii=False),
        artifact_dir,
        task_id="task-a08",
        issue_id="issue-a08",
        attachment_id="attachment-a08",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    oracle_rules = QA_AGENTS_ROOT / "policies" / "oracle-rule-library.json"
    a09_bundle = prepare_multica_oracle_review_input(
        artifact_dir / "artifacts" / "a08-test-design-ir.json",
        inputs_dir / "a08-input.json",
        oracle_rules,
        inputs_dir,
    )
    blocking_issue = {
        "id": "A09-ISSUE-001",
        "issue_code": "DYNAMIC_RELATION_SCOPE_CONFLICT",
        "human_title": "动态关联范围与冻结口径冲突",
        "plain_summary": "动态关联用例的范围与冻结口径不一致，需要修正测试设计。",
        "severity": "blocking",
        "category": "upstream_conflict",
        "message": "冻结业务口径冲突，需要修正测试设计。",
        "path": "$.allowed_inputs.test_design_ir.parent_cases[3]",
        "route_to": "A08",
        "case_id": "CASE-REQ-001",
        "expected_id": "",
        "source_refs": ["a08-test-design-ir"],
        "recommendation": "按冻结口径调整负向 Case 边界。",
    }
    ingest_multica_output(
        inputs_dir / "a09-input.json",
        json.dumps(
            _a09_review_output(a09_bundle, approved=False, issues=[blocking_issue]),
            ensure_ascii=False,
        ),
        artifact_dir,
        task_id="task-a09",
        issue_id="issue-a09",
        attachment_id="attachment-a09",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    n04 = ensure_n04_validation(artifact_dir, inputs_dir)
    assert n04 is not None and n04["valid"] is False and n04["next_node"] == "A08"
    return {
        "artifact_dir": artifact_dir,
        "inputs_dir": inputs_dir,
        "oracle_rules": oracle_rules,
        "a08_bundle_path": inputs_dir / "a08-input.json",
        "n04_payload": json.loads(
            (artifact_dir / "artifacts" / "n04-test-case-ir-validation.json").read_text(
                encoding="utf-8"
            )
        )["payload"],
    }


def _valid_a08_design(
    bundle: dict, *, correction_resolutions: list | None = None
) -> dict:
    evidence = bundle["allowed_inputs"]
    requirements = evidence["validated_analysis"]["requirement_analysis"]["requirements"]
    obligations = evidence["approved_scope"]["test_rule_obligations"]
    strategy = evidence["test_strategy"]
    risk = str(strategy.get("risk_level", ""))
    priority = {
        "critical": "P0",
        "high": "P1",
        "medium": "P2",
        "low": "P3",
    }.get(risk, "P2")
    layers = list(map(str, strategy.get("required_layers", [])))
    requirement_ids = [str(item["id"]) for item in requirements]
    cases = []
    for index, req_id in enumerate(requirement_ids):
        case_id = f"CASE-REQ-{index + 1:03d}"
        cases.append(
            {
                "id": case_id,
                "title": f"Case {req_id}",
                "intent_ids": ["INTENT-001"],
                "layer": "backend",
                "required_layers": layers,
                "risk": risk,
                "priority": priority,
                "source_refs": [req_id],
                "preconditions": [],
                "test_data": {"datasets": []},
                "steps": ["触发下钻明细并断言提示文案。"],
                "expected": [
                    {
                        "id": f"EXP-{index + 1:03d}",
                        "description": "返回当前语言提示",
                        "oracle": {
                            "type": "deterministic",
                            "observation_point": "detail_api.error",
                            "matcher": "equals",
                            "source_ref": req_id,
                        },
                    }
                ],
                "cleanup": [],
                "execution_policy": {"allowed_modes": ["automated", "manual"]},
                "automation_candidate": True,
            }
        )
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "test_intents": [
            {
                "id": "INTENT-001",
                "objective": "覆盖全部冻结需求的下钻明细提示",
                "risk": risk,
                "required_layers": layers,
                "source_refs": requirement_ids,
            }
        ],
        "parent_cases": cases,
        "coverage_matrix": [
            {"requirement_id": req_id, "case_ids": [f"CASE-REQ-{index + 1:03d}"]}
            for index, req_id in enumerate(requirement_ids)
        ],
        "test_rule_coverage": [
            {"rule_id": item["id"], "case_ids": [cases[0]["id"]]}
            for item in obligations
        ],
        **(
            {"correction_resolutions": correction_resolutions}
            if correction_resolutions is not None
            else {}
        ),
    }


def _ingest_corrected_a08(state: dict, tmp_path: Path) -> Path:
    from qa_agents.multica import (
        ingest_multica_output,
        prepare_multica_test_design_correction_input,
    )

    correction_dir = state["inputs_dir"] / "a08-correction-1"
    correction_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_test_design_correction_input(
        state["artifact_dir"] / "artifacts" / "a08-test-design-ir.json",
        state["a08_bundle_path"],
        state["artifact_dir"] / "artifacts" / "a09-oracle-coverage-review.json",
        state["artifact_dir"] / "artifacts" / "n04-test-case-ir-validation.json",
        correction_dir,
    )
    payload = _valid_a08_design(
        bundle,
        correction_resolutions=[
            {
                "feedback_id": "A09-ISSUE-001",
                "disposition": "fixed",
                "affected_case_ids": ["CASE-REQ-001"],
                "source_refs": ["a08-test-design-ir"],
                "rationale": "按冻结口径修正负向 Case 边界。",
            }
        ],
    )
    ingest_multica_output(
        correction_dir / "a08-input.json",
        json.dumps(payload, ensure_ascii=False),
        state["artifact_dir"],
        task_id="task-a08-correction",
        issue_id="issue-a08-correction",
        attachment_id="attachment-a08-correction",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.2.1",
    )
    return correction_dir / "a08-input.json"


def _write_g02_returned_round(state: dict, tmp_path: Path) -> Path:
    from qa_agents.contracts import artifact_hash_from_mapping
    from qa_agents.g02_review import prepare_test_case_review_request

    _flip_state_to_g02_ready(state)
    review_dir = tmp_path / "g02-auto"
    review_dir.mkdir(parents=True, exist_ok=True)
    n04_path = state["artifact_dir"] / "artifacts" / "n04-test-case-ir-validation.json"
    request = prepare_test_case_review_request(
        state["artifact_dir"] / "artifacts" / "a08-test-design-ir.json",
        state["artifact_dir"] / "artifacts" / "a09-oracle-coverage-review.json",
        n04_path,
        QA_AGENTS_ROOT / "policies" / "g02-review-policy.json",
        review_dir,
    )
    comment = {
        "id": "g02-comment-1",
        "created_at": "2026-08-10T08:04:00Z",
        "content": "缺少 en 下钻边界场景：补充 CASE 的 en 分支断言",
    }
    decision = {
        "schema_version": "test-case-ir-review-decision/1.0",
        "gate_id": "G02",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "review_key": request["review_key"],
        "decision": "request_changes",
        "decided_at": "2026-08-10T08:05:00Z",
        "actor": {
            "type": "human",
            "id": "muqj11262",
            "role": "qa_owner",
            "multica_member_id": "c2c6b9c6-4fb9-4439-a4a5-de4e93784c54",
        },
        "multica_event": {
            "workspace_id": "457d700f-6c27-4a59-871d-c2c56bca9f46",
            "issue_id": "issue-g02",
            "event_id": "event-1",
            "status": "blocked",
            "comment_id": comment["id"],
            "identity_evidence_mode": "assigned_member_pilot",
        },
        "reviewer_comment": comment,
        "reason": comment["content"],
    }
    decision["decision_hash"] = content_hash(decision)
    (review_dir / "g02-review-decision.json").write_text(
        json.dumps(decision, ensure_ascii=False), encoding="utf-8"
    )
    outcome = {
        "schema_version": "test-case-ir-review-outcome/1.0",
        "gate_id": "G02",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "review_key": request["review_key"],
        "decision_hash": decision["decision_hash"],
        "decision": "request_changes",
        "status": "blocked_input",
        "action": "return_upstream",
        "next_node": "A08",
        "resume_at": "A08",
        "invalidation": {"roots": ["A08"], "include_all_descendants": True},
        "idempotency_key": content_hash(
            {
                "gate_id": "G02",
                "request_hash": request["request_hash"],
                "decision_hash": decision["decision_hash"],
            }
        ),
    }
    outcome["outcome_hash"] = content_hash(outcome)
    (review_dir / "g02-review-outcome.json").write_text(
        json.dumps(outcome, ensure_ascii=False), encoding="utf-8"
    )
    return review_dir


def _flip_state_to_g02_ready(state: dict) -> None:
    """Make the correction-loop fixture G02-ready: approved A09 and valid N04."""

    from qa_agents.contracts import artifact_hash_from_mapping

    a09_path = state["artifact_dir"] / "artifacts" / "a09-oracle-coverage-review.json"
    a09 = json.loads(a09_path.read_text(encoding="utf-8"))
    a09["payload"]["approved"] = True
    a09["status"] = "completed"
    a09["artifact_hash"] = artifact_hash_from_mapping(a09)
    a09_path.write_text(json.dumps(a09, ensure_ascii=False), encoding="utf-8")
    n04_path = state["artifact_dir"] / "artifacts" / "n04-test-case-ir-validation.json"
    envelope = json.loads(n04_path.read_text(encoding="utf-8"))
    envelope["payload"]["oracle_review_artifact_hash"] = a09["artifact_hash"]
    envelope["payload"]["valid"] = True
    envelope["payload"]["blocking_issue_count"] = 0
    envelope["payload"]["issues"] = []
    envelope["payload"]["next_node"] = "G02"
    envelope["payload"]["g02_status"] = "pending"
    envelope["evidence_refs"] = [
        {
            **dict(item),
            "content_hash": a09["artifact_hash"],
        }
        if str(item.get("source_id", "")) == "a09-oracle-coverage-review"
        else dict(item)
        for item in envelope.get("evidence_refs", [])
    ]
    envelope.pop("artifact_hash", None)
    envelope["artifact_hash"] = artifact_hash_from_mapping(envelope)
    n04_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")


def _ingest_g02_corrected_a08(state: dict, tmp_path: Path) -> None:
    from qa_agents.multica import (
        ingest_multica_output,
        prepare_multica_test_design_correction_input,
    )

    review_dir = _write_g02_returned_round(state, tmp_path)
    correction_dir = state["inputs_dir"] / "a08-correction-2"
    correction_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_test_design_correction_input(
        state["artifact_dir"] / "artifacts" / "a08-test-design-ir.json",
        state["a08_bundle_path"],
        state["artifact_dir"] / "artifacts" / "a09-oracle-coverage-review.json",
        state["artifact_dir"] / "artifacts" / "n04-test-case-ir-validation.json",
        correction_dir,
        g02_review_request_path=review_dir / "g02-review-request.json",
        g02_review_decision_path=review_dir / "g02-review-decision.json",
    )
    payload = _valid_a08_design(
        bundle,
        correction_resolutions=[
            {
                "feedback_id": "G02-REVIEW-COMMENT",
                "disposition": "fixed",
                "affected_case_ids": ["CASE-REQ-001"],
                "source_refs": ["g02-review-decision"],
                "rationale": "按 G02 评论补充 en 分支断言。",
            }
        ],
    )
    ingest_multica_output(
        correction_dir / "a08-input.json",
        json.dumps(payload, ensure_ascii=False),
        state["artifact_dir"],
        task_id="task-a08-g02-correction",
        issue_id="issue-a08-g02-correction",
        attachment_id="attachment-a08-g02-correction",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.4.0",
    )


def test_ensure_a08_correction_dispatch_after_n04_route(
    tmp_path: Path, monkeypatch
) -> None:
    state = _correction_state(tmp_path)
    instruction_path = tmp_path / "a08-v1.2.1.md"
    instruction_path.write_text(
        "# A08 测试设计 Agent v1.2.1\n定向修正输入。", encoding="utf-8"
    )
    config = {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A08": "agent-a08"},
        "node_instruction_files": {"A08": {"1.2.1": str(instruction_path)}},
    }
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("agent", "get"):
            return {"instructions": "# A08 测试设计 Agent v1.2.1"}
        if args[:2] == ("issue", "create"):
            return {"id": "issue-a08-corr", "identifier": "QAA-910"}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    result = ensure_a08_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        state["inputs_dir"],
        tmp_path,
        {"A08": []},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["mode"] == "correction"
    assert result["correction_attempt"] == 1
    bundle = json.loads(
        (state["inputs_dir"] / "a08-correction-1" / "a08-input.json").read_text(
            encoding="utf-8"
        )
    )
    assert bundle["profile_version"] == "1.2.1"
    assert bundle["allowed_inputs"]["correction_feedback"]["a09_issues"][0]["id"] == (
        "A09-ISSUE-001"
    )
    created = next(call for call in calls if call[:2] == ["issue", "create"])
    assert any("a08-correction-1" in str(part) for part in created)
    registry = json.loads(
        (state["inputs_dir"] / ".issue-bundles.json").read_text(encoding="utf-8")
    )
    assert "issue-a08-corr" in registry
    assert registry["issue-a08-corr"].endswith("a08-correction-1/a08-input.json")


def test_ensure_a08_correction_dispatch_is_idempotent(tmp_path: Path) -> None:
    state = _correction_state(tmp_path)
    config = {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A08": "agent-a08"},
    }
    result = ensure_a08_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        state["inputs_dir"],
        tmp_path,
        {
            "A08": [
                {
                    "id": "issue-a08-corr",
                    "title": "[run-1] A08 测试设计修正",
                    "status": "in_progress",
                }
            ]
        },
        apply=True,
    )
    assert result is not None
    assert result["action"] == "already_dispatched"
    assert result["issue_id"] == "issue-a08-corr"


def test_ensure_a08_correction_dispatch_budget_exhausted(tmp_path: Path) -> None:
    state = _correction_state(tmp_path)
    payload_path = (
        state["artifact_dir"] / "artifacts" / "n04-test-case-ir-validation.json"
    )
    envelope = json.loads(payload_path.read_text(encoding="utf-8"))
    envelope["payload"]["correction_attempt"] = 2
    envelope["payload"]["max_correction_attempts"] = 2
    payload_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    config = {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A08": "agent-a08"},
    }
    result = ensure_a08_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        state["inputs_dir"],
        tmp_path,
        {"A08": []},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "correction_budget_exhausted"
    assert result["next_node"] == "human"


def test_ensure_a09_correction_dispatch_after_corrected_a08(
    tmp_path: Path, monkeypatch
) -> None:
    state = _correction_state(tmp_path)
    corrected_bundle = _ingest_corrected_a08(state, tmp_path)
    config = {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A09": "agent-a09"},
        "oracle_rule_library": str(state["oracle_rules"]),
    }
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "create"):
            return {"id": "issue-a09-corr", "identifier": "QAA-911"}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    result = ensure_a09_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        state["inputs_dir"],
        QA_AGENTS_ROOT,
        {"A09": []},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["mode"] == "correction"
    bundle = json.loads(
        (state["inputs_dir"] / "a09-correction-1" / "a09-input.json").read_text(
            encoding="utf-8"
        )
    )
    assert bundle["profile_id"] == "A09"
    current_hash = json.loads(
        (state["artifact_dir"] / "artifacts" / "a08-test-design-ir.json").read_text(
            encoding="utf-8"
        )
    )["artifact_hash"]
    upstream = {
        item["artifact_id"]: item["artifact_hash"]
        for item in bundle["upstream_artifacts"]
    }
    assert upstream["a08-test-design-ir"] == current_hash


def test_ensure_n04_validation_reruns_after_correction_loop(
    tmp_path: Path,
) -> None:
    state = _correction_state(tmp_path)
    corrected_bundle = _ingest_corrected_a08(state, tmp_path)
    from qa_agents.multica import ingest_multica_output

    a09_corr_dir = state["inputs_dir"] / "a09-correction-1"
    a09_corr_dir.mkdir(parents=True, exist_ok=True)
    a09_bundle = prepare_multica_oracle_review_input(
        state["artifact_dir"] / "artifacts" / "a08-test-design-ir.json",
        corrected_bundle,
        state["oracle_rules"],
        a09_corr_dir,
    )
    ingest_multica_output(
        a09_corr_dir / "a09-input.json",
        json.dumps(
            _a09_review_output(a09_bundle, approved=True, issues=[]),
            ensure_ascii=False,
        ),
        state["artifact_dir"],
        task_id="task-a09-correction",
        issue_id="issue-a09-correction",
        attachment_id="attachment-a09-correction",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    result = ensure_n04_validation(state["artifact_dir"], state["inputs_dir"])
    assert result is not None
    assert result["valid"] is True
    assert result["correction_attempt"] == 2
    target = (
        state["artifact_dir"] / "artifacts" / "n04-test-case-ir-validation.json"
    )
    envelope = json.loads(target.read_text(encoding="utf-8"))
    assert envelope["payload"]["valid"] is True
    assert ensure_n04_validation(state["artifact_dir"], state["inputs_dir"]) is None


def _ingest_issue_fixture(tmp_path: Path, run: dict) -> tuple[dict, Path]:
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir(parents=True)
    artifact_dir = tmp_path / "artifacts-auto"
    shutil.copyfile(
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        inputs_dir / "a08-input.json",
    )
    bundle = json.loads(
        (inputs_dir / "a08-input.json").read_text(encoding="utf-8")
    )
    run = {
        "id": "run-a08",
        "status": "completed",
        "result": {"output": json.dumps(_valid_a08_design(bundle), ensure_ascii=False)},
        **run,
    }
    artifact = _sync_module._ingest_issue(
        issue={
            "id": "issue-a08",
            "attachments": [{"id": "attachment-a08"}],
        },
        run=run,
        node_id="A08",
        bundle_path=inputs_dir / "a08-input.json",
        output_dir=artifact_dir,
    )
    envelope = json.loads(
        (artifact_dir / "artifacts" / "a08-test-design-ir.json").read_text(
            encoding="utf-8"
        )
    )
    return artifact, envelope


def test_ingest_issue_reads_model_from_run_usage(tmp_path: Path) -> None:
    artifact, envelope = _ingest_issue_fixture(
        tmp_path,
        {"usage": [{"provider": "deepseek", "model": "deepseek-v4-flash"}]},
    )
    assert artifact["artifact_id"] == "a08-test-design-ir"
    producer = envelope["producer"]
    assert producer["model_provider"] == "deepseek"
    assert producer["model_snapshot"] == "deepseek-v4-flash"


def test_ingest_issue_uses_last_usage_entry(tmp_path: Path) -> None:
    _, envelope = _ingest_issue_fixture(
        tmp_path,
        {
            "usage": [
                {"provider": "codex", "model": "gpt-5.6-sol"},
                {"provider": "deepseek", "model": "deepseek-v4-flash"},
            ]
        },
    )
    producer = envelope["producer"]
    assert producer["model_provider"] == "deepseek"
    assert producer["model_snapshot"] == "deepseek-v4-flash"


def test_ingest_issue_falls_back_without_usage(tmp_path: Path) -> None:
    _, envelope = _ingest_issue_fixture(tmp_path, {})
    producer = envelope["producer"]
    assert producer["model_provider"] == "unknown"
    assert producer["model_snapshot"] == "unknown"


def _human_route_state(tmp_path: Path) -> dict:
    """A08/A09 correction loop that exhausted the automatic budget (N04 -> human)."""

    state = _correction_state(tmp_path)
    corrected_bundle = _ingest_corrected_a08(state, tmp_path)
    from qa_agents.multica import ingest_multica_output

    a09_corr_dir = state["inputs_dir"] / "a09-correction-1"
    a09_corr_dir.mkdir(parents=True, exist_ok=True)
    a09_bundle = prepare_multica_oracle_review_input(
        state["artifact_dir"] / "artifacts" / "a08-test-design-ir.json",
        corrected_bundle,
        state["oracle_rules"],
        a09_corr_dir,
    )
    blocking_issue = {
        "id": "A09-ISSUE-002",
        "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE",
        "human_title": "预期结果无法解析",
        "plain_summary": "用例的预期结果引用无法解析，需要人工指定后再修正。",
        "severity": "blocking",
        "category": "upstream_conflict",
        "message": "期望引用无法解析，需要人工定向修正。",
        "path": "$.parent_cases[0].expected[0].oracle",
        "route_to": "A08",
        "case_id": "CASE-REQ-001",
        "expected_id": "",
        "source_refs": ["a08-test-design-ir"],
        "recommendation": "由人工指定可解析的期望来源后再修正。",
    }
    ingest_multica_output(
        a09_corr_dir / "a09-input.json",
        json.dumps(
            _a09_review_output(a09_bundle, approved=False, issues=[blocking_issue]),
            ensure_ascii=False,
        ),
        state["artifact_dir"],
        task_id="task-a09-human",
        issue_id="issue-a09-human",
        attachment_id="attachment-a09-human",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.1",
    )
    result = ensure_n04_validation(state["artifact_dir"], state["inputs_dir"])
    assert result is not None
    assert result["valid"] is False
    assert result["next_node"] == "human"
    assert result["correction_attempt"] == 2
    return state


def _human_correction_policy(tmp_path: Path) -> Path:
    policy = {
        "schema_version": "human-test-design-correction-policy/1.0",
        "node_id": "human_test_design_correction",
        "allowed_actor_ids": ["tester"],
        "allowed_roles": ["qa_owner"],
        "allowed_multica_member_ids": ["member-1"],
        "allowed_decisions": ["directed_correction", "terminate"],
        "automatic_budget_reset": False,
        "required_revalidation": ["A09", "N04"],
        "temporary_policy": True,
        "production_release_authority": False,
        "multica": {
            "workspace_id": "workspace-1",
            "project_id": "project-internal",
            "assignee_member_id": "member-1",
            "identity_evidence_mode": "assigned_member_pilot",
            "initial_status": "in_review",
            "decision_statuses": {"done": "directed_correction", "cancelled": "terminate"},
        },
    }
    path = tmp_path / "human-correction-policy.json"
    path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    return path


def _human_config(tmp_path: Path) -> dict:
    instruction_path = tmp_path / "a08-v1.3.0.md"
    instruction_path.write_text(
        "# A08 测试设计 Agent v1.3.0\n人工恢复输入。", encoding="utf-8"
    )
    return {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A08": "agent-a08", "A09": "agent-a09"},
        "human_correction_policy": str(_human_correction_policy(tmp_path)),
        "node_instruction_files": {"A08": {"1.3.0": str(instruction_path)}},
        "oracle_rule_library": str(QA_AGENTS_ROOT / "policies" / "oracle-rule-library.json"),
    }


def test_ensure_human_correction_dispatch_opens_issue(tmp_path: Path, monkeypatch) -> None:
    state = _human_route_state(tmp_path)
    config = _human_config(tmp_path)
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "create"):
            return {"id": "human-issue-1", "identifier": "QAA-950", "workspace_id": "workspace-1"}
        if args[:2] == ("issue", "get"):
            return {"id": args[2], "identifier": "QAA-950", "status": "in_review"}
        if args[:2] in {("issue", "status"), ("issue", "metadata")}:
            return {}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    opened = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert opened is not None
    assert opened["action"] == "opened"
    assert opened["issue_id"] == "human-issue-1"
    assert opened["issue_identifier"] == "QAA-950"
    request_path = tmp_path / "human-correction" / "human-correction-request.json"
    assert request_path.exists()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["node_id"] == "human_test_design_correction"
    assert request["budget"]["correction_attempt"] == 2
    assert request["budget"]["next_attempt"] == 3
    assert request["budget"]["automatic_budget_reset"] is False

    waiting = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert waiting is not None
    assert waiting["action"] == "waiting_for_human"
    assert waiting["issue_id"] == "human-issue-1"


def test_ensure_human_correction_dispatch_dispatches_recovery_after_decision(
    tmp_path: Path, monkeypatch
) -> None:
    state = _human_route_state(tmp_path)
    config = _human_config(tmp_path)
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "create"):
            title = args[args.index("--title") + 1] if "--title" in args else ""
            if title.startswith("【人工修正】测试设计（A08）"):
                return {"id": "human-issue-1", "identifier": "QAA-950", "workspace_id": "workspace-1"}
            return {"id": "recovery-issue-1", "identifier": "QAA-951"}
        if args[:2] == ("issue", "get"):
            if args[2] == "human-issue-1":
                request = json.loads(
                    (tmp_path / "human-correction" / "human-correction-request.json").read_text(
                        encoding="utf-8"
                    )
                )
                return {
                    "id": "human-issue-1",
                    "identifier": "QAA-950",
                    "status": "done",
                    "workspace_id": "workspace-1",
                    "project_id": "project-internal",
                    "assignee_type": "member",
                    "assignee_id": "member-1",
                    "updated_at": "2026-08-18T00:00:00Z",
                    "metadata": {
                        "qa_item_type": "human_action",
                        "qa_node_id": request["node_id"],
                        "qa_action_required": "true",
                        "qa_request_hash": request["request_hash"],
                        "qa_policy_hash": request["policy"]["policy_hash"],
                        "qa_visible_in_workflow_center": "false",
                        "qa_workflow_run_id": request["workflow_run_id"],
                    },
                }
            return {"id": args[2], "identifier": "QAA-950"}
        if args[:2] == ("agent", "get"):
            return {"instructions": "# A08 测试设计 Agent v1.3.0"}
        if args[:2] in {("issue", "status"), ("issue", "metadata")}:
            return {}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    opened = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert opened is not None and opened["action"] == "opened"
    result = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["mode"] == "human_recovery"
    assert result["issue_id"] == "recovery-issue-1"
    assert result["correction_attempt"] == 3
    recovery_bundle = json.loads(
        (state["inputs_dir"] / "a08-correction-3" / "a08-input.json").read_text(
            encoding="utf-8"
        )
    )
    assert recovery_bundle["profile_id"] == "A08"
    assert recovery_bundle["profile_version"] == "1.3.0"
    assert (tmp_path / "human-correction" / "human-correction-outcome.json").exists()
    outcome = json.loads(
        (tmp_path / "human-correction" / "human-correction-outcome.json").read_text(
            encoding="utf-8"
        )
    )
    assert outcome["decision"] == "directed_correction"
    assert outcome["next_node"] == "A08"
    assert outcome["automatic_budget_reset"] is False


def test_ensure_a09_correction_dispatch_allows_human_recovery(
    tmp_path: Path, monkeypatch
) -> None:
    state = _human_route_state(tmp_path)
    config = _human_config(tmp_path)
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "create"):
            title = args[args.index("--title") + 1] if "--title" in args else ""
            if title.startswith("【人工修正】测试设计（A08）"):
                return {"id": "human-issue-1", "identifier": "QAA-950", "workspace_id": "workspace-1"}
            return {"id": "a09-recovery-issue", "identifier": "QAA-952"}
        if args[:2] == ("issue", "get"):
            if args[2] == "human-issue-1":
                request = json.loads(
                    (tmp_path / "human-correction" / "human-correction-request.json").read_text(
                        encoding="utf-8"
                    )
                )
                return {
                    "id": "human-issue-1",
                    "identifier": "QAA-950",
                    "status": "done",
                    "workspace_id": "workspace-1",
                    "project_id": "project-internal",
                    "assignee_type": "member",
                    "assignee_id": "member-1",
                    "updated_at": "2026-08-18T00:00:00Z",
                    "metadata": {
                        "qa_item_type": "human_action",
                        "qa_node_id": request["node_id"],
                        "qa_action_required": "true",
                        "qa_request_hash": request["request_hash"],
                        "qa_policy_hash": request["policy"]["policy_hash"],
                        "qa_visible_in_workflow_center": "false",
                        "qa_workflow_run_id": request["workflow_run_id"],
                    },
                }
            return {"id": args[2], "identifier": "QAA-950"}
        if args[:2] == ("agent", "get"):
            return {"instructions": "# A08 测试设计 Agent v1.3.0"}
        if args[:2] in {("issue", "status"), ("issue", "metadata")}:
            return {}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    first = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert first is not None and first["action"] == "opened"
    opened = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert opened is not None and opened["action"] == "dispatched"

    # Simulate the accepted human-recovery A08 run: same content, new producer hash.
    corrected_bundle = json.loads(
        (state["inputs_dir"] / "a08-correction-1" / "a08-input.json").read_text(
            encoding="utf-8"
        )
    )
    from qa_agents.multica import ingest_multica_output

    ingest_multica_output(
        state["inputs_dir"] / "a08-correction-1" / "a08-input.json",
        json.dumps(
            _valid_a08_design(
                corrected_bundle,
                correction_resolutions=[
                    {
                        "feedback_id": "A09-ISSUE-001",
                        "disposition": "fixed",
                        "affected_case_ids": ["CASE-REQ-001"],
                        "source_refs": ["a08-test-design-ir"],
                        "rationale": "按人工定向修正。",
                    }
                ],
            ),
            ensure_ascii=False,
        ),
        state["artifact_dir"],
        task_id="task-a08-recovery",
        issue_id="issue-a08-recovery",
        attachment_id="attachment-a08-recovery",
        model_provider="openai",
        model_snapshot="gpt-test",
        prompt_version="1.3.0",
    )
    result = ensure_a09_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        state["inputs_dir"],
        tmp_path,
        {"A09": [], "A08": []},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["issue_id"] == "a09-recovery-issue"
    bundle = json.loads(
        (state["inputs_dir"] / "a09-correction-2" / "a09-input.json").read_text(
            encoding="utf-8"
        )
    )
    assert bundle["profile_id"] == "A09"
    current_hash = json.loads(
        (state["artifact_dir"] / "artifacts" / "a08-test-design-ir.json").read_text(
            encoding="utf-8"
        )
    )["artifact_hash"]
    upstream = {
        item["artifact_id"]: item["artifact_hash"]
        for item in bundle["upstream_artifacts"]
    }
    assert upstream["a08-test-design-ir"] == current_hash


def test_ensure_human_correction_dispatch_reports_recovery_completed(
    tmp_path: Path, monkeypatch
) -> None:
    state = _human_route_state(tmp_path)
    config = _human_config(tmp_path)
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "create"):
            title = args[args.index("--title") + 1] if "--title" in args else ""
            if title.startswith("【人工修正】测试设计（A08）"):
                return {"id": "human-issue-1", "identifier": "QAA-950", "workspace_id": "workspace-1"}
            return {"id": "recovery-issue-1", "identifier": "QAA-951"}
        if args[:2] == ("issue", "get"):
            if args[2] == "human-issue-1":
                request = json.loads(
                    (tmp_path / "human-correction" / "human-correction-request.json").read_text(
                        encoding="utf-8"
                    )
                )
                return {
                    "id": "human-issue-1",
                    "identifier": "QAA-950",
                    "status": "done",
                    "workspace_id": "workspace-1",
                    "project_id": "project-internal",
                    "assignee_type": "member",
                    "assignee_id": "member-1",
                    "updated_at": "2026-08-18T00:00:00Z",
                    "metadata": {
                        "qa_item_type": "human_action",
                        "qa_node_id": request["node_id"],
                        "qa_action_required": "true",
                        "qa_request_hash": request["request_hash"],
                        "qa_policy_hash": request["policy"]["policy_hash"],
                        "qa_visible_in_workflow_center": "false",
                        "qa_workflow_run_id": request["workflow_run_id"],
                    },
                }
            return {"id": args[2], "identifier": "QAA-950"}
        if args[:2] == ("agent", "get"):
            return {"instructions": "# A08 测试设计 Agent v1.3.0"}
        if args[:2] in {("issue", "status"), ("issue", "metadata")}:
            return {}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    opened = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert opened is not None and opened["action"] == "opened"
    dispatched = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert dispatched is not None and dispatched["action"] == "dispatched"

    # The accepted human-recovery A08 run lands: N04 no longer binds the design.
    corrected_bundle = json.loads(
        (state["inputs_dir"] / "a08-correction-1" / "a08-input.json").read_text(
            encoding="utf-8"
        )
    )
    from qa_agents.multica import ingest_multica_output

    ingest_multica_output(
        state["inputs_dir"] / "a08-correction-1" / "a08-input.json",
        json.dumps(
            _valid_a08_design(
                corrected_bundle,
                correction_resolutions=[
                    {
                        "feedback_id": "A09-ISSUE-001",
                        "disposition": "fixed",
                        "affected_case_ids": ["CASE-REQ-001"],
                        "source_refs": ["a08-test-design-ir"],
                        "rationale": "按人工定向修正。",
                    }
                ],
            ),
            ensure_ascii=False,
        ),
        state["artifact_dir"],
        task_id="task-a08-recovery",
        issue_id="issue-a08-recovery",
        attachment_id="attachment-a08-recovery",
        model_provider="openai",
        model_snapshot="gpt-test",
        prompt_version="1.3.0",
    )
    completed = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [{"title": "[run] A08 测试设计人工修正", "status": "done"}], "A09": []},
        apply=True,
    )
    assert completed is not None
    assert completed["action"] == "recovery_completed"


def test_ensure_a09_correction_dispatch_ignores_done_stale_correction_issue(
    tmp_path: Path, monkeypatch
) -> None:
    state = _human_route_state(tmp_path)
    config = _human_config(tmp_path)
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "create"):
            title = args[args.index("--title") + 1] if "--title" in args else ""
            if title.startswith("【人工修正】测试设计（A08）"):
                return {"id": "human-issue-1", "identifier": "QAA-950", "workspace_id": "workspace-1"}
            return {"id": "a09-recovery-issue", "identifier": "QAA-952"}
        if args[:2] == ("issue", "get"):
            if args[2] == "human-issue-1":
                request = json.loads(
                    (tmp_path / "human-correction" / "human-correction-request.json").read_text(
                        encoding="utf-8"
                    )
                )
                return {
                    "id": "human-issue-1",
                    "identifier": "QAA-950",
                    "status": "done",
                    "workspace_id": "workspace-1",
                    "project_id": "project-internal",
                    "assignee_type": "member",
                    "assignee_id": "member-1",
                    "updated_at": "2026-08-18T00:00:00Z",
                    "metadata": {
                        "qa_item_type": "human_action",
                        "qa_node_id": request["node_id"],
                        "qa_action_required": "true",
                        "qa_request_hash": request["request_hash"],
                        "qa_policy_hash": request["policy"]["policy_hash"],
                        "qa_visible_in_workflow_center": "false",
                        "qa_workflow_run_id": request["workflow_run_id"],
                    },
                }
            return {"id": args[2], "identifier": "QAA-950"}
        if args[:2] == ("agent", "get"):
            return {"instructions": "# A08 测试设计 Agent v1.3.0"}
        if args[:2] in {("issue", "status"), ("issue", "metadata")}:
            return {}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    opened = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert opened is not None and opened["action"] == "opened"
    dispatched = ensure_human_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        tmp_path,
        state["inputs_dir"],
        tmp_path,
        {"A08": [], "A09": []},
        apply=True,
    )
    assert dispatched is not None and dispatched["action"] == "dispatched"
    corrected_bundle = json.loads(
        (state["inputs_dir"] / "a08-correction-1" / "a08-input.json").read_text(
            encoding="utf-8"
        )
    )
    from qa_agents.multica import ingest_multica_output

    ingest_multica_output(
        state["inputs_dir"] / "a08-correction-1" / "a08-input.json",
        json.dumps(
            _valid_a08_design(
                corrected_bundle,
                correction_resolutions=[
                    {
                        "feedback_id": "A09-ISSUE-001",
                        "disposition": "fixed",
                        "affected_case_ids": ["CASE-REQ-001"],
                        "source_refs": ["a08-test-design-ir"],
                        "rationale": "按人工定向修正。",
                    }
                ],
            ),
            ensure_ascii=False,
        ),
        state["artifact_dir"],
        task_id="task-a08-recovery",
        issue_id="issue-a08-recovery",
        attachment_id="attachment-a08-recovery",
        model_provider="openai",
        model_snapshot="gpt-test",
        prompt_version="1.3.0",
    )
    result = ensure_a09_correction_dispatch(
        config,
        "run-1",
        state["artifact_dir"],
        state["inputs_dir"],
        tmp_path,
        {
            "A09": [
                {
                    "id": "stale-a09-correction",
                    "title": "[run-1] A09 Oracle 与覆盖审查修正",
                    "status": "done",
                }
            ],
            "A08": [],
        },
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["issue_id"] == "a09-recovery-issue"


def test_refresh_waiting_node_cards_rebuilds_approval_description(tmp_path: Path) -> None:
    auto_dir = tmp_path / "auto"
    _write_artifact(
        auto_dir,
        "n04-test-case-ir-validation",
        {
            "valid": False,
            "next_node": "human",
            "issues": [
                {"id": "A09-ISSUE-007", "origin": "A09", "severity": "blocking"},
                {"id": "A09-ISSUE-008", "origin": "A09", "severity": "blocking"},
            ],
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    _write_artifact(
        auto_dir,
        "a09-oracle-coverage-review",
        {
            "approved": False,
            "issues": [
                {
                    "id": "A09-ISSUE-007",
                    "severity": "blocking",
                    "route_to": "A08",
                    "case_id": "TC-E2E-001",
                    "recommendation": "改 expected_value",
                },
                {
                    "id": "A09-ISSUE-008",
                    "severity": "blocking",
                    "route_to": "A08",
                    "case_id": "TC-BE-002",
                    "recommendation": "按 locale 拆分数据行",
                },
            ],
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    node_entries = {
        "A09": {
            "issue": {
                "id": "issue-a09",
                "identifier": "QAA-324",
                "title": "[REQ-1-r001] A09 Oracle 与覆盖审查修正",
            },
            "run": {},
            "bundle_path": tmp_path / "a09-input.json",
        }
    }
    refreshed = _refresh_waiting_node_cards(
        config={"internal_project_id": "project-internal"},
        auto_dir=auto_dir,
        node_entries=node_entries,
        run_id="REQ-1-r001",
        apply=False,
    )
    assert len(refreshed) == 1
    assert refreshed[0]["node_id"] == "A09"
    assert refreshed[0]["issue_identifier"] == "QAA-324"
    assert refreshed[0]["approval_count"] == 2


def test_refresh_waiting_node_cards_skips_terminal_cards(tmp_path: Path, monkeypatch) -> None:
    auto_dir = tmp_path / "auto"
    _write_artifact(
        auto_dir,
        "n04-test-case-ir-validation",
        {
            "valid": False,
            "next_node": "human",
            "issues": [
                {"id": "A09-ISSUE-007", "origin": "A09", "severity": "blocking"},
                {"id": "A09-ISSUE-008", "origin": "A09", "severity": "blocking"},
            ],
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    _write_artifact(
        auto_dir,
        "a09-oracle-coverage-review",
        {
            "approved": False,
            "issues": [
                {
                    "id": "A09-ISSUE-007",
                    "severity": "blocking",
                    "route_to": "A08",
                    "case_id": "TC-E2E-001",
                    "recommendation": "改 expected_value",
                },
                {
                    "id": "A09-ISSUE-008",
                    "severity": "blocking",
                    "route_to": "A08",
                    "case_id": "TC-BE-002",
                    "recommendation": "按 locale 拆分数据行",
                },
            ],
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    node_entries = {
        "A09": {
            "issue": {
                "id": "issue-a09",
                "identifier": "QAA-324",
                "title": "[REQ-1-r001] A09 Oracle 与覆盖审查修正",
                "status": "done",
            },
            "run": {},
            "bundle_path": tmp_path / "a09-input.json",
        }
    }

    def fail_on_multica(*args, **kwargs):
        raise AssertionError("terminal cards must not be updated")

    monkeypatch.setattr(_sync_module, "_multica", fail_on_multica)
    refreshed = _refresh_waiting_node_cards(
        config={"internal_project_id": "project-internal"},
        auto_dir=auto_dir,
        node_entries=node_entries,
        run_id="REQ-1-r001",
        apply=True,
    )
    assert refreshed == []


def test_comment_artifact_output_filters_by_contract_and_task(monkeypatch) -> None:
    comments = [
        {
            "id": "c1",
            "source_task_id": "task-1",
            "created_at": "2026-08-18T10:00:00Z",
            "content": json.dumps(
                {"schema_version": "oracle-review/1.1", "status": "completed"},
                ensure_ascii=False,
            ),
        },
        {
            "id": "c2",
            "source_task_id": "task-2",
            "created_at": "2026-08-18T10:01:00Z",
            "content": json.dumps({"schema_version": "other/1.0"}, ensure_ascii=False),
        },
        {
            "id": "c3",
            "source_task_id": "task-1",
            "created_at": "2026-08-18T10:02:00Z",
            "content": "这是一条过程说明，不是 Artifact。",
        },
    ]
    monkeypatch.setattr(_sync_module, "_multica", lambda *args, **kwargs: comments)
    output = _comment_artifact_output(
        {"id": "issue-1"}, {"id": "task-1"}, "oracle-review/1.1"
    )
    assert output is not None
    assert json.loads(output)["status"] == "completed"


def test_ingest_issue_falls_back_to_comment_artifact(tmp_path: Path, monkeypatch) -> None:
    bundle_path = tmp_path / "a09-input.json"
    bundle_path.write_text(
        json.dumps(
            {"output_contract": "oracle-review/1.1", "profile_version": "1.1.0"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    comment_content = json.dumps(
        {"schema_version": "oracle-review/1.1", "status": "completed_with_gaps"},
        ensure_ascii=False,
    )

    def fake_extract(raw_output: str):
        if "已完成" in raw_output:
            raise ContractError("Multica response file must be valid JSON")
        return {"ok": True}

    def fake_ingest(bundle_path, raw_output, output_dir, **kwargs):
        assert raw_output == comment_content
        return {
            "artifact_id": "a09-oracle-coverage-review",
            "producer": {"tool_bundle_version": f"multica-task:{kwargs['task_id']}"},
        }

    monkeypatch.setattr(_sync_module, "extract_multica_model_output", fake_extract)
    monkeypatch.setattr(_sync_module, "ingest_multica_output", fake_ingest)
    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: [
            {
                "id": "c1",
                "source_task_id": "task-1",
                "created_at": "2026-08-18T10:00:00Z",
                "content": comment_content,
            }
        ],
    )
    artifact = _ingest_issue(
        issue={"id": "issue-1", "attachments": [{"id": "att-1"}]},
        run={"id": "task-1", "result": {"output": "已完成审查，结果为……"}},
        node_id="A09",
        bundle_path=bundle_path,
        output_dir=tmp_path / "out",
    )
    assert artifact is not None
    assert artifact["artifact_id"] == "a09-oracle-coverage-review"


def test_inject_human_action_entry_skips_done_or_cancelled_decision(
    tmp_path: Path, monkeypatch
) -> None:
    _inject_human_action_entry = _sync_module._inject_human_action_entry
    state_path = tmp_path / "human-correction" / "human-correction-state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "issue_id": "human-issue-1",
                "observed_multica_status": "open",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def spec_with_entry() -> dict:
        return {
            "workflow_run_id": "REQ-1-r001",
            "nodes": [
                {
                    "node_id": "C3",
                    "state": "waiting_human",
                    "human_action_entry": {
                        "issue_id": "stale-issue",
                        "issue_identifier": "QAA-999",
                        "status": "open",
                    },
                },
                {"node_id": "A09", "state": "running"},
            ],
        }

    def fake_multica(*args: str, **kwargs):
        return {"identifier": "QAA-950", "status": live_status}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)

    live_status = "open"
    spec_path = tmp_path / "current" / "workflow-center-spec.json"
    spec_path.parent.mkdir()
    spec_path.write_text(json.dumps(spec_with_entry()), encoding="utf-8")
    _inject_human_action_entry(spec_path, tmp_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    entry = spec["nodes"][0]["human_action_entry"]
    assert entry["issue_id"] == "human-issue-1"
    assert entry["issue_identifier"] == "QAA-950"
    assert entry["status"] == "open"

    for live_status in ("done", "cancelled"):
        spec_path.write_text(json.dumps(spec_with_entry()), encoding="utf-8")
        _inject_human_action_entry(spec_path, tmp_path)
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        assert "human_action_entry" not in spec["nodes"][0]


def test_create_node_issue_passes_absolute_attachment_with_relative_input(
    tmp_path: Path, monkeypatch
) -> None:
    _create_node_issue = _sync_module._create_node_issue
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append((list(args), kwargs.get("cwd")))
        return {"id": "issue-rel", "identifier": "QAA-901"}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    input_path = inputs_dir / "a08-input.json"
    input_path.write_text("{}", encoding="utf-8")
    result = _create_node_issue(
        config={
            "internal_project_id": "project-internal",
            "workspace_id": "workspace-1",
            "node_agents": {"A08": "agent-a08"},
        },
        run_id="run-1",
        node_id="A08",
        label="测试设计人工修正",
        input_path=input_path,
    )
    assert result["issue_id"] == "issue-rel"
    created, cwd = calls[0]
    assert "--attachment" in created
    attachment = created[created.index("--attachment") + 1]
    assert Path(attachment).is_absolute()
    assert attachment.endswith("a08-input.json")
    assert cwd == input_path.parent


def _stage_two_setup(tmp_path: Path) -> dict:
    """A08 accepted + approved G02 outcome + A08 bundle; N25 compiled."""
    artifact_dir = tmp_path / "artifacts-auto"
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "profile_id": "A08",
        "workflow_run_id": "REQ-1-r001",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
    }
    bundle["bundle_hash"] = content_hash(
        {key: value for key, value in bundle.items() if key != "bundle_hash"}
    )
    (inputs_dir / "a08-input.json").write_text(
        json.dumps(bundle, ensure_ascii=False), encoding="utf-8"
    )
    _write_artifact(
        artifact_dir,
        "a08-test-design-ir",
        {
            "input_bundle_hash": bundle["bundle_hash"],
            "parent_cases": [
                {
                    "id": "TC-BE-001",
                    "title": "自定义维度查看明细",
                    "required_layers": ["backend"],
                    "expected": [
                        {
                            "id": "EXP-1",
                            "oracle_id": "O-1",
                            "type": "error_code",
                            "expectation": "s307011534",
                        }
                    ],
                }
            ],
        },
        ArtifactStatus.COMPLETED,
    )
    a08 = json.loads(
        (artifact_dir / "artifacts" / "a08-test-design-ir.json").read_text(
            encoding="utf-8"
        )
    )
    g02_dir = tmp_path / "g02-auto"
    g02_dir.mkdir(parents=True, exist_ok=True)
    request = {
        "schema_version": "test-case-ir-review-request/1.0",
        "workflow_run_id": "REQ-1-r001",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
        "upstream_artifacts": [
            {
                "artifact_id": "a08-test-design-ir",
                "artifact_hash": a08["artifact_hash"],
            }
        ],
    }
    request["request_hash"] = content_hash(
        {key: value for key, value in request.items() if key != "request_hash"}
    )
    outcome = {
        "schema_version": "test-case-ir-review-outcome/1.0",
        "workflow_run_id": "REQ-1-r001",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
        "decision": "approved",
        "next_node": "N25",
        "request_hash": request["request_hash"],
    }
    outcome["outcome_hash"] = content_hash(
        {key: value for key, value in outcome.items() if key != "outcome_hash"}
    )
    (g02_dir / "g02-review-request.json").write_text(
        json.dumps(request, ensure_ascii=False), encoding="utf-8"
    )
    (g02_dir / "g02-review-outcome.json").write_text(
        json.dumps(outcome, ensure_ascii=False), encoding="utf-8"
    )
    n25_result = ensure_n25_compilation(artifact_dir, g02_dir)
    assert n25_result is not None
    assert n25_result["artifact_id"] == "n25-compiled-test-cases"
    return {
        "artifact_dir": artifact_dir,
        "inputs_dir": inputs_dir,
        "g02_dir": g02_dir,
        "a08": a08,
    }


def _a11_config() -> dict:
    return {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {"A08": "agent-a08", "A11": "agent-a11"},
        "oracle_rule_library": str(
            QA_AGENTS_ROOT / "policies" / "oracle-rule-library.json"
        ),
    }


def test_ensure_n25_compilation_runs_after_g02_approval(tmp_path: Path) -> None:
    setup = _stage_two_setup(tmp_path)
    target = setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json"
    envelope = json.loads(target.read_text(encoding="utf-8"))
    assert envelope["artifact_id"] == "n25-compiled-test-cases"
    assert envelope["payload"]["parent_count"] == 1
    assert envelope["payload"]["child_count"] == 1
    assert (
        ensure_n25_compilation(setup["artifact_dir"], setup["g02_dir"]) is None
    )


def test_ensure_n25_compilation_skips_without_approval(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "a08-test-design-ir",
        {"parent_cases": []},
        ArtifactStatus.COMPLETED,
    )
    g02_dir = tmp_path / "g02-auto"
    g02_dir.mkdir(parents=True, exist_ok=True)
    (g02_dir / "g02-review-outcome.json").write_text(
        json.dumps(
            {
                "schema_version": "test-case-ir-review-outcome/1.0",
                "decision": "rejected",
                "next_node": "A08",
            }
        ),
        encoding="utf-8",
    )
    (g02_dir / "g02-review-request.json").write_text("{}", encoding="utf-8")
    assert ensure_n25_compilation(artifact_dir, g02_dir) is None
    assert not (
        artifact_dir / "artifacts" / "n25-compiled-test-cases.json"
    ).exists()


def test_ensure_a11_dispatch_prepares_input_in_dry_run(tmp_path: Path) -> None:
    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    result = ensure_a11_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        setup["inputs_dir"],
        tmp_path,
        {},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch"
    bundle = json.loads(
        (setup["inputs_dir"] / "a11-input.json").read_text(encoding="utf-8")
    )
    assert bundle["profile_id"] == "A11"
    assert bundle["output_contract"] == "split-review/1.0"


def test_ensure_a11_dispatch_creates_issue(tmp_path: Path, monkeypatch) -> None:
    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        return {"id": "issue-a11", "identifier": "QAA-910"}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    result = ensure_a11_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        setup["inputs_dir"],
        tmp_path,
        {},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["issue_id"] == "issue-a11"
    created = next(call for call in calls if call[:2] == ["issue", "create"])
    assert "--assignee-id" in created and "agent-a11" in created
    assert any("a11-input.json" in str(part) for part in created)
    bundles = json.loads(
        (setup["inputs_dir"] / ".issue-bundles.json").read_text(encoding="utf-8")
    )
    assert bundles["issue-a11"].endswith("a11-input.json")


def test_ensure_a11_dispatch_is_idempotent_when_issue_exists(tmp_path: Path) -> None:
    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    result = ensure_a11_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        setup["inputs_dir"],
        tmp_path,
        {"A11": [{"id": "issue-running", "title": "[run-1] A11 拆分覆盖审查", "status": "in_progress"}]},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "already_dispatched"
    assert result["issue_id"] == "issue-running"


def test_ensure_a11_dispatch_does_not_replace_blocked_ingest(tmp_path: Path) -> None:
    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    result = ensure_a11_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        setup["inputs_dir"],
        tmp_path,
        {"A11": [{"id": "issue-blocked", "title": "[run-1] A11 拆分覆盖审查", "status": "blocked"}]},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "awaiting_ingest"
    assert result["issue_id"] == "issue-blocked"


def test_ensure_n26_selection_runs_after_approved_a11(tmp_path: Path) -> None:
    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    ensure_a11_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        setup["inputs_dir"],
        tmp_path,
        {},
        apply=False,
    )
    bundle = json.loads(
        (setup["inputs_dir"] / "a11-input.json").read_text(encoding="utf-8")
    )
    _write_artifact(
        setup["artifact_dir"],
        "a11-split-coverage-review",
        {"approved": True, "input_bundle_hash": bundle["bundle_hash"], "issues": []},
        ArtifactStatus.COMPLETED,
    )
    result = ensure_n26_selection(
        config, setup["artifact_dir"], setup["inputs_dir"], tmp_path
    )
    assert result is not None
    assert result["artifact_id"] == "n26-test-selection"
    assert result["status"] == "completed"
    assert result["next_node"] == "N15"
    target = setup["artifact_dir"] / "artifacts" / "n26-test-selection.json"
    assert target.exists()
    assert (
        ensure_n26_selection(config, setup["artifact_dir"], setup["inputs_dir"], tmp_path)
        is None
    )


def test_ensure_n26_selection_skips_without_approved_a11(tmp_path: Path) -> None:
    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    _write_artifact(
        setup["artifact_dir"],
        "a11-split-coverage-review",
        {"approved": False, "input_bundle_hash": "sha256:none", "issues": []},
        ArtifactStatus.NEEDS_HUMAN,
    )
    assert (
        ensure_n26_selection(config, setup["artifact_dir"], setup["inputs_dir"], tmp_path)
        is None
    )
    assert not (
        setup["artifact_dir"] / "artifacts" / "n26-test-selection.json"
    ).exists()


def test_ensure_n15_execution_plan_runs_after_n26(tmp_path: Path) -> None:
    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    ensure_a11_dispatch(
        config,
        "run-1",
        setup["artifact_dir"],
        setup["inputs_dir"],
        tmp_path,
        {},
        apply=False,
    )
    bundle = json.loads(
        (setup["inputs_dir"] / "a11-input.json").read_text(encoding="utf-8")
    )
    _write_artifact(
        setup["artifact_dir"],
        "a11-split-coverage-review",
        {"approved": True, "input_bundle_hash": bundle["bundle_hash"], "issues": []},
        ArtifactStatus.COMPLETED,
    )
    n26 = ensure_n26_selection(
        config, setup["artifact_dir"], setup["inputs_dir"], tmp_path
    )
    assert n26 is not None
    result = ensure_n15_execution_plan(setup["artifact_dir"])
    assert result is not None
    assert result["artifact_id"] == "n15-execution-plan"
    target = setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json"
    assert target.exists()
    assert ensure_n15_execution_plan(setup["artifact_dir"]) is None


def test_ensure_node_record_issues_creates_record_cards(
    tmp_path: Path, monkeypatch
) -> None:
    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        return {"id": f"record-{len(calls)}", "identifier": f"QAA-{900 + len(calls)}"}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    records = ensure_node_record_issues(
        config, "run-1", setup["artifact_dir"], {}, apply=True
    )
    node_ids = {record["node_id"] for record in records}
    assert "N25" in node_ids
    assert "A08" not in node_ids
    created = next(call for call in calls if call[:2] == ["issue", "create"])
    assert "--status" in created
    assert "done" in created
    assert any("n25-compiled-test-cases.json" in str(part) for part in created)
    # 已存在且状态一致时不重复创建
    rerun = ensure_node_record_issues(
        config,
        "run-1",
        setup["artifact_dir"],
        {"N25": [{"id": "existing-record", "status": "done"}]},
        apply=True,
    )
    assert all(record["node_id"] != "N25" for record in rerun)
    # 已存在但状态与 Artifact 不一致时同步回显（N27 blocked -> completed_with_gaps）
    synced_calls = []

    def syncing_multica(*args: str, **kwargs):
        synced_calls.append(list(args))
        if args[:2] == ("issue", "status"):
            return {"id": args[2], "status": args[3]}
        return {"id": f"record-{len(synced_calls)}", "identifier": "QAA-950"}

    monkeypatch.setattr(_sync_module, "_multica", syncing_multica)
    synced = ensure_node_record_issues(
        config,
        "run-1",
        setup["artifact_dir"],
        {"N25": [{"id": "existing-record", "status": "blocked"}]},
        apply=True,
    )
    n25_synced = next(record for record in synced if record["node_id"] == "N25")
    assert n25_synced["action"] == "synced"
    assert n25_synced["status"] == "done"
    assert any(call[:2] == ["issue", "status"] and call[3] == "done" for call in synced_calls)


def test_ensure_node_record_issues_syncs_blocked_artifact_to_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    """A blocked deterministic Artifact must echo blocked on the record Issue
    (for example N11 quality_blocked), not fall back to the default done."""

    setup = _stage_two_setup(tmp_path)
    config = _a11_config()
    calls = []

    def syncing_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "status"):
            return {"id": args[2], "status": args[3]}
        return {"id": f"record-{len(calls)}", "identifier": "QAA-960"}

    monkeypatch.setattr(_sync_module, "_multica", syncing_multica)
    n25_path = setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json"
    blocked = json.loads(n25_path.read_text(encoding="utf-8"))
    blocked["status"] = ArtifactStatus.BLOCKED.value
    n25_path.write_text(json.dumps(blocked, ensure_ascii=False), encoding="utf-8")
    synced = ensure_node_record_issues(
        config,
        "run-1",
        setup["artifact_dir"],
        {"N25": [{"id": "existing-record", "status": "done"}]},
        apply=True,
    )
    n25_synced = next(record for record in synced if record["node_id"] == "N25")
    assert n25_synced["action"] == "synced"
    assert n25_synced["status"] == "blocked"
    assert any(call[:2] == ["issue", "status"] and call[3] == "blocked" for call in calls)


def _write_artifact_with_reason(
    dir_path: Path,
    artifact_id: str,
    payload: dict,
    status: ArtifactStatus,
    reason_code: str,
) -> Path:
    envelope = ArtifactEnvelope(
        workflow_run_id="REQ-1-r001",
        workflow_mode="new_requirement",
        artifact_id=artifact_id,
        source_snapshot_id="snapshot-1",
        producer=Producer("N01"),
        payload=payload,
        status=status,
        reason_code=reason_code,
    )
    (dir_path / "artifacts").mkdir(parents=True, exist_ok=True)
    target = dir_path / "artifacts" / f"{artifact_id}.json"
    target.write_text(
        json.dumps(envelope.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    return target


def test_ensure_node_record_issues_renders_retry_approval_on_retryable(
    tmp_path: Path, monkeypatch
) -> None:
    """A failed_retryable record (N08/N10) must flip to in_review and carry a
    structured retry-approval block instead of an empty 审核中 card."""

    artifact_dir = tmp_path / "artifacts-auto"
    n08 = _write_artifact_with_reason(
        artifact_dir,
        "n08-automation-execution",
        {
            "schema_version": "n08-automation-execution/1.0",
            "decision": "retryable_infrastructure_failure",
            "next_node": "N10",
            "summary": {"total": 6, "failed": 1, "passed": 0, "skipped": 0},
        },
        ArtifactStatus.FAILED_RETRYABLE,
        reason_code="automation_infrastructure_failure",
    )
    n10 = _write_artifact_with_reason(
        artifact_dir,
        "n10-retry-budget",
        {
            "schema_version": "n10-retry-budget/1.0",
            "attempt": 0,
            "decision": "retry_allowed",
            "max_attempts": 1,
            "next_node": "N07",
        },
        ArtifactStatus.FAILED_RETRYABLE,
        reason_code="environment_retry_allowed",
    )
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        return {"id": f"record-{len(calls)}", "identifier": f"QAA-{900 + len(calls)}"}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    records = ensure_node_record_issues(
        _a11_config(), "run-1", artifact_dir, {}, apply=True
    )
    by_node = {record["node_id"]: record for record in records}
    assert by_node["N08"]["status"] == "in_review"
    assert by_node["N08"]["approval_rendered"] is True
    assert by_node["N10"]["status"] == "in_review"
    assert by_node["N10"]["approval_rendered"] is True
    n08_desc = (n08.with_name(f"{n08.name}.record.md")).read_text(encoding="utf-8")
    assert "## 你需要处理" in n08_desc
    assert "批准重试" in n08_desc
    assert "重试预算" in n08_desc
    assert "`automation_infrastructure_failure`" in n08_desc
    assert "`total=6`" in n08_desc
    assert "`retry_allowed`" in n08_desc
    assert "`N07`" in n08_desc
    n10_desc = (n10.with_name(f"{n10.name}.record.md")).read_text(encoding="utf-8")
    assert "## 你需要处理" in n10_desc
    assert "`environment_retry_allowed`" in n10_desc
    assert "允许重试：`1` 次" in n10_desc
    created = [call for call in calls if call[:2] == ["issue", "create"]]
    assert len(created) == 2
    assert all("--status" in call and call[call.index("--status") + 1] == "in_review" for call in created)


def test_ensure_node_record_issues_refreshes_retry_content_when_already_in_review(
    tmp_path: Path, monkeypatch
) -> None:
    """A retryable record already in_review with the old generic template must
    still get its approval block rewritten on the next sync."""

    artifact_dir = tmp_path / "artifacts-auto"
    n08 = _write_artifact_with_reason(
        artifact_dir,
        "n08-automation-execution",
        {
            "schema_version": "n08-automation-execution/1.0",
            "decision": "retryable_infrastructure_failure",
            "next_node": "N10",
            "summary": {"total": 6, "failed": 1, "passed": 0, "skipped": 0},
        },
        ArtifactStatus.FAILED_RETRYABLE,
        reason_code="automation_infrastructure_failure",
    )
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "update"):
            return {"id": args[2], "status": args[args.index("--status") + 1]}
        return {"id": f"record-{len(calls)}", "identifier": "QAA-970"}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    synced = ensure_node_record_issues(
        _a11_config(),
        "run-1",
        artifact_dir,
        {"N08": [{"id": "existing-n08", "identifier": "QAA-349", "status": "in_review"}]},
        apply=True,
    )
    n08_synced = next(record for record in synced if record["node_id"] == "N08")
    assert n08_synced["action"] == "synced"
    assert n08_synced["approval_rendered"] is True
    update = next(call for call in calls if call[:2] == ["issue", "update"])
    assert update[update.index("--status") + 1] == "in_review"
    assert "--description-file" in update
    desc = (n08.with_name(f"{n08.name}.record.md")).read_text(encoding="utf-8")
    assert "## 你需要处理" in desc
    assert "批准重试" in desc


def test_ensure_node_record_issues_refreshes_existing_n12_with_standard_report(
    tmp_path: Path, monkeypatch
) -> None:
    artifact_dir = tmp_path / "artifacts-auto"
    _write_artifact(
        artifact_dir,
        "n11-quality-decision",
        {
            "summary": "测试完成：执行 2，通过 1，失败 1",
            "case_outcomes": [
                {
                    "case_id": "PC-BE-001",
                    "title": "限制提示",
                    "scene": "命中限制时返回专用中文提示。",
                    "status": "failed",
                    "reason": "实际返回通用提示，本应返回专用提示",
                    "requests": [{"name": "main", "trace_id": "FSW-1.2-abc"}],
                },
                {
                    "case_id": "PC-BE-002",
                    "title": "正常明细",
                    "scene": "不受限时正常返回明细。",
                    "status": "passed",
                    "requests": [{"name": "main", "trace_id": "FSW-1.2-def"}],
                },
            ],
        },
        ArtifactStatus.COMPLETED,
    )
    n12 = artifact_dir / "artifacts" / "n12-quality-report.json"
    _write_artifact(
        artifact_dir,
        "n12-quality-report",
        {
            "decision": "completed_with_defects",
            "release_disposition": "pending",
            "bug_draft_count": 1,
        },
        ArtifactStatus.COMPLETED,
    )
    (artifact_dir / "artifacts" / "constructed-test-assets.json").write_text(
        json.dumps(
            {
                "schema_version": "constructed-test-assets/1.0",
                "assets": [
                    {
                        "case_id": "PC-BE-001",
                        "resource_type": "stat_chart",
                        "display_name": "限制提示验证统计图",
                        "resource_id": "BI_chart_1",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        return {"id": args[2] if len(args) > 2 else "record", "status": "done"}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    synced = ensure_node_record_issues(
        _a11_config(),
        "run-1",
        artifact_dir,
        {"N12": [{"id": "existing-n12", "identifier": "QAA-442", "status": "done"}]},
        apply=True,
    )
    n12_synced = next(record for record in synced if record["node_id"] == "N12")
    assert n12_synced["action"] == "synced"
    update = next(call for call in calls if call[:2] == ["issue", "update"] and call[2] == "existing-n12")
    assert "--description-file" in update
    description = n12.with_name(f"{n12.name}.record.md").read_text(encoding="utf-8")
    assert "## 产出" in description
    assert "## 标准测试报告" in description
    assert "### 4. 用例执行明细" in description
    assert "FSW-1.2-abc" in description
    assert "统计图：`限制提示验证统计图`（`BI_chart_1`）" in description


def _c5_config() -> dict:
    return {
        "internal_project_id": "project-internal",
        "workspace_id": "workspace-1",
        "node_agents": {
            "A14": "agent-a14",
            "A15": "agent-a15",
            "A22": "agent-a22",
            "A18-BE": "agent-a18-be",
            "A18-CT": "agent-a18-ct",
        },
        "automation_target_policy": str(
            QA_AGENTS_ROOT / "policies" / "automation-target-policy.json"
        ),
        "test_data_policy": str(QA_AGENTS_ROOT / "policies" / "test-data-policy.json"),
        "capability_catalog": str(
            QA_AGENTS_ROOT / "knowledge" / "bi-data-capability-catalog.json"
        ),
        "knowledge_sources": str(
            QA_AGENTS_ROOT / "knowledge" / "bi-knowledge-sources.json"
        ),
        "g03_policy": str(QA_AGENTS_ROOT / "policies" / "g03-review-policy.json"),
    }


def _c5_setup(tmp_path: Path) -> dict:
    """N25 with backend+contract children and an N15 execution plan."""
    artifact_dir = tmp_path / "artifacts-auto"
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        {
            "id": "TC-BE-001-BACKEND",
            "parent_case_id": "TC-BE-001",
            "title": "自定义维度查看明细",
            "layer": "backend",
            "automation_candidate": True,
            "execution_policy": {"allowed_modes": ["automated", "manual"]},
            "expected": [
                {
                    "id": "EXP-1",
                    "description": "返回 s307011534",
                    "oracle": {
                        "type": "deterministic",
                        "matcher": "equals",
                        "observation_point": "detail_api.error.code",
                        "source_ref": "RULE-I18N-CUSTOM-DIMENSION",
                    },
                }
            ],
            "preconditions": ["真实接口联调环境"],
            "test_data": {"datasets": ["基线统计图"], "locales": ["zh_CN", "en"]},
            "steps": ["打开统计图", "点击查看明细"],
            "cleanup": [],
            "source_refs": ["REQ-001"],
            "intent_ids": ["INT-1"],
            "risk": "critical",
            "priority": "P0",
        },
        {
            "id": "TC-CON-001-CONTRACT",
            "parent_case_id": "TC-CON-001",
            "title": "契约兼容性",
            "layer": "contract",
            "automation_candidate": True,
            "execution_policy": {"allowed_modes": ["automated", "manual"]},
            "expected": [
                {
                    "id": "EXP-C1",
                    "description": "契约字段兼容",
                    "oracle": {
                        "type": "deterministic",
                        "matcher": "equals",
                        "observation_point": "contract.fields",
                        "source_ref": "RULE-CONTRACT",
                    },
                }
            ],
            "preconditions": [],
            "test_data": {"contract_ref": "openapi-detail-drill", "method": "POST", "path": "/api/detail"},
            "steps": ["调用契约校验"],
            "cleanup": [],
            "source_refs": ["REQ-002"],
            "intent_ids": ["INT-2"],
            "risk": "medium",
            "priority": "P2",
        },
    ]
    _write_artifact(
        artifact_dir,
        "n25-compiled-test-cases",
        {
            "schema_version": "compiled-test-cases/1.0",
            "parent_count": 2,
            "child_count": 2,
            "compiled_cases": cases,
            "parent_artifact_id": "a08-test-design-ir",
            "parent_artifact_hash": "sha256:parent",
        },
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "n15-execution-plan",
        {
            "schema_version": "execution-plan/1.0",
            "actions": [
                {"action": "generate_new", "case_id": case["id"], "reason_code": "new_case_without_automation"}
                for case in cases
            ],
            "selection_artifact_id": "n26-test-selection",
            "selection_artifact_hash": "sha256:sel",
        },
        ArtifactStatus.COMPLETED,
    )
    return {"artifact_dir": artifact_dir, "inputs_dir": inputs_dir}




def _write_valid_n27(artifact_dir: Path) -> None:
    """N27 valid + A22 completed, which A14 now requires before dispatch."""

    _write_artifact(
        artifact_dir,
        "a22-test-data-plan",
        {
            "schema_version": "test-data-plan/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "status": "completed",
            "environment": "112",
            "namespace": "qa-namespace-from-plan",
            "case_plans": [],
            "paused_cases": [],
            "unresolved_requirements": [],
        },
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        artifact_dir,
        "n27-test-data-plan-validation",
        {
            "schema_version": "test-data-plan-validation/1.0",
            "valid": True,
            "decision": "validated",
            "deferred_cases": [],
        },
        ArtifactStatus.COMPLETED,
    )

def _generation_artifact(
    artifact_dir: Path,
    bundle_path: Path,
    profile_id: str,
    artifact_id: str,
    case_ids: list[str],
) -> Path:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    candidate_path = f"generated/backend/test_{case_ids[0].casefold().replace('-', '_')}.py"
    content = (
        '"""Artifact-only candidate generated from approved Test Case IR."""\n'
        "CASE_SPEC = {\n"
        '    "id": "TC-BE-001-BACKEND",\n'
        '    "test_level": "integration",\n'
        '    "steps": [{"name": "describe detail", "request": {"api": "fs_bi_stat.describe_query.detail", "json": {}}}],\n'
        '    "expected": [{"id": "EXP-1", "oracle": {"matcher": "equals", "observation_point": "detail_api.error.code", "expected_value": "s307011534"}}],\n'
        '    "cleanup": [],\n'
        "}\n"
        "def test_x(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = {
        "path": candidate_path,
        "content": content,
        "content_hash": content_hash(content),
    }
    manifest = {
        "schema_version": "automation-manifest/1.0",
        "manifest_id": "manifest-a14-backend",
        "generator_profile": "A14/1.0.0",
        "layer": "backend",
        "target_repository": {
            "repository_id": "pytest_for_bi",
            "access_class": "approved_automation_repository",
            "write_mode": "artifact_only_candidate",
        },
        "framework": "pytest",
        "language": "python",
        "case_mappings": [
            {"case_id": case_ids[0], "expected_ids": ["EXP-1"], "manual_expected_ids": [], "candidate_path": candidate_path}
        ],
        "candidate_files": [{"path": candidate_path, "content_hash": candidate["content_hash"]}],
        "execution": {"command": ["pytest", "-q", candidate_path], "timeout_seconds": 600},
        "permissions": {"business_repository_write": False, "network": False, "secrets": []},
        "expected_artifacts": ["junit_xml"],
        "input_bindings": {},
    }
    _write_artifact(
        artifact_dir,
        artifact_id,
        {
            "schema_version": "automation-generation/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "input_bundle_hash": bundle["bundle_hash"],
            "status": "completed",
            "manifest": manifest,
            "code_candidates": [candidate],
            "rejected_cases": [
                {"case_id": cid, "reason_code": "case_not_machine_executable", "source_refs": [cid]}
                for cid in case_ids[1:]
            ],
            "evaluation_oracle_accessed": False,
        },
        ArtifactStatus.COMPLETED,
    )
    return artifact_dir / "artifacts" / f"{artifact_id}.json"


def test_ensure_a14_dispatch_prepares_input_in_dry_run(tmp_path: Path) -> None:
    setup = _c5_setup(tmp_path)
    _write_valid_n27(setup["artifact_dir"])
    result = ensure_a14_dispatch(
        _c5_config(),
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch"
    assert (setup["inputs_dir"] / "a14-input.json").exists()
    bundle = json.loads(
        (setup["inputs_dir"] / "a14-input.json").read_text(encoding="utf-8")
    )
    assert bundle["profile_id"] == "A14"
    assert bundle["output_contract"] == "automation-generation/1.0"
    assert bundle["allowed_inputs"]["layer"] == "backend"


def test_ensure_a15_dispatch_prepares_input_in_dry_run(tmp_path: Path) -> None:
    setup = _c5_setup(tmp_path)
    result = ensure_a15_dispatch(
        _c5_config(),
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch"
    assert (setup["inputs_dir"] / "a15-input.json").exists()


def test_ensure_a22_dispatch_prepares_input_in_dry_run(tmp_path: Path) -> None:
    setup = _c5_setup(tmp_path)
    result = ensure_a22_dispatch(
        _c5_config(),
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch"
    bundle = json.loads(
        (setup["inputs_dir"] / "a22-input.json").read_text(encoding="utf-8")
    )
    assert bundle["profile_id"] == "A22"
    assert bundle["output_contract"] == "test-data-plan/1.0"
    assert bundle["allowed_inputs"]["planning_defaults"]["environment"] == "112"


def test_ensure_a18_dispatch_prepares_input_after_generation(tmp_path: Path) -> None:
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    result = ensure_a18_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        reviewer="A18-BE",
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch"
    assert (setup["inputs_dir"] / "a18-be-input.json").exists()


def test_ensure_a18_dispatch_skips_fresh_review(tmp_path: Path) -> None:
    """复核 generation_hash 与当前生成载荷一致时视为新鲜，不再派发。"""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": content_hash(generation["payload"]),
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    result = ensure_a18_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        reviewer="A18-BE",
        apply=False,
    )
    assert result is None


def test_ensure_a18_dispatch_redispatch_when_review_stale(tmp_path: Path) -> None:
    """A14 重生成后旧复核失效：移除陈旧 artifact 并触发复核重派。"""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    review_path = setup["artifact_dir"] / "artifacts" / "a18-be-backend-automation-review.json"
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": "sha256:stale-generation",
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    assert review_path.exists()
    result = ensure_a18_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        reviewer="A18-BE",
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch"
    assert not review_path.exists()


def test_ensure_a18_dispatch_keeps_frozen_bundle_when_issue_in_flight(
    tmp_path: Path,
) -> None:
    """在途复核 issue 存在时不得重建 bundle 或清理 stale artifact。

    回归：A18 曾先重建复核输入 bundle（regeneration_round 递增改变哈希）
    再在 _dispatch_c5_agent 内发现在途 issue，导致在途 run 绑定哈希被覆盖，
    完成后摄入哈希不匹配而永久 in_progress/blocked。
    """
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    review_path = setup["artifact_dir"] / "artifacts" / "a18-be-backend-automation-review.json"
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": "sha256:stale-generation",
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    prepare_multica_automation_review_input(
        generation_path,
        setup["inputs_dir"] / "a14-input.json",
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A18-BE",
        regeneration_round=0,
    )
    bundle_path = setup["inputs_dir"] / "a18-be-input.json"
    hash_before = content_hash(json.loads(bundle_path.read_text(encoding="utf-8")))
    assert review_path.exists()
    in_flight = [
        {
            "id": "issue-in-flight",
            "identifier": "QAA-1",
            "title": "[REQ-1-r001] A18-BE 服务端自动化独立复核",
            "status": "in_progress",
        }
    ]
    result = ensure_a18_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {"A18-BE": in_flight},
        reviewer="A18-BE",
        apply=False,
    )
    assert result is not None
    assert result["action"] == "already_dispatched"
    assert content_hash(json.loads(bundle_path.read_text(encoding="utf-8"))) == hash_before
    assert review_path.exists()


def test_ensure_a18_be_deterministic_review_replaces_llm_overblock(
    tmp_path: Path,
) -> None:
    """LLM A18-BE 误把可执行候选打成 needs_human 时，确定性复核必须改回 approved。"""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": content_hash(generation["payload"]),
            "approved": False,
            "issues": [
                {
                    "issue_code": "execution_contract_mismatch",
                    "severity": "blocking",
                    "route_to": "A18-BE",
                    "message": "dotted extract keys are not overwrite",
                }
            ],
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    result = ensure_a18_be_deterministic_review(setup["artifact_dir"])
    assert result is not None
    assert result["approved"] is True
    assert result["status"] == "completed"
    artifact = json.loads(
        (
            setup["artifact_dir"] / "artifacts" / "a18-be-backend-automation-review.json"
        ).read_text(encoding="utf-8")
    )
    assert artifact["status"] == "completed"
    assert artifact["payload"]["approved"] is True
    assert artifact["payload"]["issues"] == []


def test_already_ingested_accepts_deterministic_a18_be_review(tmp_path: Path) -> None:
    """In-repo A18-BE reviewer must count as ingested so LLM ingest failures cannot pin the card."""
    auto_dir = tmp_path / "artifacts-auto"
    (auto_dir / "artifacts").mkdir(parents=True)
    bundle_path = tmp_path / "a18-be-input.json"
    bundle_path.write_text(
        json.dumps({"profile_id": "A18-BE", "bundle_hash": "sha256:bundle"}),
        encoding="utf-8",
    )
    review = ArtifactEnvelope(
        workflow_run_id="REQ-1-r001",
        workflow_mode="new_requirement",
        artifact_id="a18-be-backend-automation-review",
        source_snapshot_id="snapshot-1",
        producer=Producer(component_id="A18-BE", runtime="automation-review-runtime"),
        payload={"approved": True, "generation_hash": "sha256:gen", "issues": []},
        status=ArtifactStatus.COMPLETED,
    )
    ArtifactStore(auto_dir).write_artifact(review)
    assert _already_ingested(auto_dir, bundle_path, "llm-run-1") is True
    failures = {
        "A18-BE": [{"issue_id": "issue-a18", "run_id": "llm-run-1"}],
    }
    assert (
        _completed_run_ingest_action(
            auto_dir=auto_dir,
            bundle_path=bundle_path,
            run_id="llm-run-1",
            ingest_failures=failures,
            node_id="A18-BE",
            issue_id="issue-a18",
        )
        == "mark_done"
    )


def test_completed_run_keeps_blocked_when_no_deterministic_artifact(
    tmp_path: Path,
) -> None:
    auto_dir = tmp_path / "artifacts-auto"
    (auto_dir / "artifacts").mkdir(parents=True)
    bundle_path = tmp_path / "a18-be-input.json"
    bundle_path.write_text(
        json.dumps({"profile_id": "A18-BE", "bundle_hash": "sha256:bundle"}),
        encoding="utf-8",
    )
    failures = {
        "A18-BE": [{"issue_id": "issue-a18", "run_id": "llm-run-1"}],
    }
    assert (
        _completed_run_ingest_action(
            auto_dir=auto_dir,
            bundle_path=bundle_path,
            run_id="llm-run-1",
            ingest_failures=failures,
            node_id="A18-BE",
            issue_id="issue-a18",
        )
        == "keep_blocked"
    )


def test_ensure_a18_be_deterministic_review_closes_blocked_issue(
    tmp_path: Path, monkeypatch
) -> None:
    """Approved deterministic A18-BE must close a leftover blocked Multica Issue."""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    calls: list[list[str]] = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        return {"id": args[2], "status": args[3]}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    issues = {
        "A18-BE": [
            {
                "id": "issue-a18-be",
                "identifier": "QAA-451",
                "title": "[REQ-1-r001] A18-BE 服务端自动化独立复核",
                "status": "blocked",
            }
        ]
    }
    result = ensure_a18_be_deterministic_review(
        setup["artifact_dir"], issues, apply=True
    )
    assert result is not None
    assert result["approved"] is True
    assert result["closed_issues"] == ["issue-a18-be"]
    assert issues["A18-BE"][0]["status"] == "done"
    assert any(
        call[:4] == ["issue", "status", "issue-a18-be", "done"] for call in calls
    )
    rerun = ensure_a18_be_deterministic_review(
        setup["artifact_dir"], issues, apply=True
    )
    assert rerun is None


def test_ensure_n05_aggregation_recomputes_when_review_changes(tmp_path: Path) -> None:
    """复核 Artifact 变化后 N05 必须重算，避免用旧复核放行新代码。"""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": content_hash(generation["payload"]),
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    first = ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert first is not None and first["status"] == "completed"
    # 复核内容变化（artifact_hash 变化）后 N05 必须重算。
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": content_hash(generation["payload"]),
            "approved": True,
            "issues": [],
            "note": "re-reviewed after regeneration",
        },
        ArtifactStatus.COMPLETED,
    )
    second = ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert second is not None and second["status"] == "completed"


def test_ensure_n05_aggregation_excludes_stale_review_after_regeneration(
    tmp_path: Path,
) -> None:
    """A14 重生成后遗留的旧复核（generation_hash 不匹配）不得算 review_passed。

    N05 本身只做确定性代码检查；A18 是否批准不再把 N05 打成 needs_human，
    否则去掉 G03 后 C5 仍会显示成人工审核中。
    """
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    def _n05_passed() -> bool:
        artifact = json.loads(
            (setup["artifact_dir"] / "artifacts" / "n05-automation-code-check.json").read_text(
                encoding="utf-8"
            )
        )
        return bool(artifact.get("payload", {}).get("passed"))

    no_review = ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert no_review is not None and no_review["status"] == "completed"
    assert _n05_passed() is True
    no_review_artifact = json.loads(
        (setup["artifact_dir"] / "artifacts" / "n05-automation-code-check.json").read_text(
            encoding="utf-8"
        )
    )
    assert no_review_artifact.get("status") == "completed"
    assert no_review_artifact.get("payload", {}).get("issues") == []
    assert no_review_artifact.get("payload", {}).get("review_passed") is False
    # 旧复核：generation_hash 指向旧代，不得计入。
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": "sha256:old-generation",
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    # 陈旧复核被排除后，N05 代码检查仍可通过；review_passed 不能被旧复核带真。
    ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert _n05_passed() is True
    stale_artifact = json.loads(
        (setup["artifact_dir"] / "artifacts" / "n05-automation-code-check.json").read_text(
            encoding="utf-8"
        )
    )
    assert stale_artifact.get("payload", {}).get("review_passed") is False
    # 新复核：generation_hash 绑定当前生成，才计入 review_passed。
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": content_hash(generation["payload"]),
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    second = ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert second is not None and second["status"] == "completed"
    assert _n05_passed() is True
    artifact = json.loads(
        (setup["artifact_dir"] / "artifacts" / "n05-automation-code-check.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(
        str(binding.get("generation_hash", "")) == content_hash(generation["payload"])
        for binding in artifact["payload"]["input_bindings"]
    )


def test_ensure_n05_aggregation_recomputes_when_review_removed(tmp_path: Path) -> None:
    """复核被移除必须触发 N05 重算证据，但代码检查通过时 N05 仍是 completed。

    A18 缺失不再把 N05 打成 needs_human，避免 C5 阶段卡回到人工审核中。
    """
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    review_path = setup["artifact_dir"] / "artifacts" / "a18-be-backend-automation-review.json"
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": content_hash(generation["payload"]),
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )

    def _n05_passed() -> bool:
        artifact = json.loads(
            (setup["artifact_dir"] / "artifacts" / "n05-automation-code-check.json").read_text(
                encoding="utf-8"
            )
        )
        return bool(artifact.get("payload", {}).get("passed"))

    assert ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT) is not None
    assert _n05_passed() is True
    # 移除复核后必须重算证据；代码检查通过则 N05 保持 completed。
    review_path.unlink()
    result = ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert result is not None and result["status"] == "completed"
    assert _n05_passed() is True
    artifact = json.loads(
        (setup["artifact_dir"] / "artifacts" / "n05-automation-code-check.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact.get("payload", {}).get("review_passed") is False


def test_ensure_n27_validation_writes_artifact(tmp_path: Path) -> None:
    from qa_agents.agents.base import AgentContext
    from qa_agents.test_data import TestDataPlannerAgent

    setup = _c5_setup(tmp_path)
    config = _c5_config()
    resource = {
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
    planner = TestDataPlannerAgent().run(
        AgentContext("REQ-1-r001", "new_requirement", "snapshot-1"),
        {
            "environment": "112",
            "namespace": "qa-a22-test-plan",
            "cases": [
                {
                    "id": "TC-BE-001-BACKEND",
                    "test_level": "integration",
                    "test_data": {"resource_requirements": [resource]},
                    "steps": [{"request": {"api": "fs_bi_stat.stat_base.data_query_da655ba1"}}],
                },
                {
                    "id": "TC-CON-001-CONTRACT",
                    "test_level": "integration",
                    "test_data": {},
                    "steps": [{"request": {"api": "fs_bi_stat.stat_base.data_query_da655ba1"}}],
                },
            ],
        },
        SecurityPolicy(),
    )
    plan_payload = planner.payload
    plan_payload["workflow_run_id"] = "REQ-1-r001"
    plan_payload["source_snapshot_id"] = "snapshot-1"
    plan_payload["input_bundle_hash"] = "sha256:bundle"
    plan_payload["status"] = "completed"
    _write_artifact(
        setup["artifact_dir"], "a22-test-data-plan", plan_payload, ArtifactStatus.COMPLETED
    )
    result = ensure_n27_validation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert result is not None
    assert result["node_id"] == "N27"
    assert result["status"] == "completed"
    assert (setup["artifact_dir"] / "artifacts" / "n27-test-data-plan-validation.json").exists()
    # idempotent
    assert ensure_n27_validation(config, setup["artifact_dir"], QA_AGENTS_ROOT) is None


def test_ensure_a22_correction_dispatch_prepares_revision_input(
    tmp_path: Path,
) -> None:
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_test_data_plan_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["test_data_policy"]),
        setup["inputs_dir"],
        capability_catalog_path=Path(config["capability_catalog"]),
        knowledge_sources_path=Path(config["knowledge_sources"]),
    )
    _write_artifact(
        setup["artifact_dir"],
        "a22-test-data-plan",
        {
            "schema_version": "test-data-plan/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "input_bundle_hash": bundle["bundle_hash"],
            "status": "needs_human",
            "environment": "112",
            "namespace": "qa-a22-plan-test",
            "case_plans": [
                {
                    "case_id": "TC-BE-001-BACKEND",
                    "requires_data_construction": True,
                    "resources": [
                        {
                            "resource_key": "custom_dimension",
                            "resource_type": "custom_dimension",
                            "resource_id_variable": "dimension_field_id",
                            "setup_operation": False,
                        }
                    ],
                }
            ],
            "paused_cases": [],
            "unresolved_requirements": [],
            "planning_mode": "case_explicit",
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    _write_artifact(
        setup["artifact_dir"],
        "n27-test-data-plan-validation",
        {
            "schema_version": "test-data-plan-validation/1.0",
            "valid": False,
            "decision": "rejected",
            "validation_error": "case_plans[0].resources[0] requires a setup operation",
            "a22_artifact_id": "a22-test-data-plan",
            "a22_artifact_hash": "sha256:plan",
        },
        ArtifactStatus.BLOCKED,
    )
    result = ensure_a22_correction_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch_revision"
    assert result["revision_attempt"] == 1
    revision_path = (
        setup["inputs_dir"] / "a22-correction-1" / "a22-input-revision-1.json"
    )
    assert revision_path.exists()
    revision = json.loads(revision_path.read_text(encoding="utf-8"))
    assert revision["profile_id"] == "A22"
    assert revision["output_contract"] == "test-data-plan/1.0"
    assert revision["revision"]["revision_attempt"] == 1
    assert "requires a setup operation" in revision["revision"]["validation_error"]
    assert revision["allowed_inputs"]["previous_plan"]["case_plans"][0]["case_id"] == (
        "TC-BE-001-BACKEND"
    )
    assert revision["allowed_inputs"]["n27_validation"]["decision"] == "rejected"
    assert revision["bundle_hash"] == content_hash(
        {key: value for key, value in revision.items() if key != "bundle_hash"}
    )


def test_ensure_a22_correction_dispatch_in_flight_and_budget(tmp_path: Path) -> None:
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_test_data_plan_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["test_data_policy"]),
        setup["inputs_dir"],
        capability_catalog_path=Path(config["capability_catalog"]),
        knowledge_sources_path=Path(config["knowledge_sources"]),
    )
    _write_artifact(
        setup["artifact_dir"],
        "a22-test-data-plan",
        {
            "schema_version": "test-data-plan/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "input_bundle_hash": bundle["bundle_hash"],
            "status": "needs_human",
            "environment": "112",
            "namespace": "qa-a22-plan-test",
            "case_plans": [],
            "paused_cases": [],
            "unresolved_requirements": [],
            "planning_mode": "case_explicit",
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    _write_artifact(
        setup["artifact_dir"],
        "n27-test-data-plan-validation",
        {
            "schema_version": "test-data-plan-validation/1.0",
            "valid": False,
            "decision": "rejected",
            "validation_error": "case_plans[0].resources[0] requires a setup operation",
            "a22_artifact_id": "a22-test-data-plan",
            "a22_artifact_hash": "sha256:plan",
        },
        ArtifactStatus.BLOCKED,
    )
    in_flight = ensure_a22_correction_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {
            "A22": [
                {
                    "id": "issue-a22-rev",
                    "title": "[REQ-1-r001] A22 测试数据规划修正",
                    "status": "in_progress",
                }
            ]
        },
        apply=False,
    )
    assert in_flight["action"] == "correction_in_flight"
    exhausted = ensure_a22_correction_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {
            "A22": [
                {
                    "id": "issue-a22-rev",
                    "title": "[REQ-1-r001] A22 测试数据规划修正",
                    "status": "done",
                }
            ]
        },
        apply=False,
    )
    assert exhausted["action"] == "rerun_budget_exhausted"


def test_ensure_n05_aggregation_after_generation_and_reviews(tmp_path: Path) -> None:
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    generation_path = _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": content_hash(generation["payload"]),
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    result = ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert result is not None
    assert result["node_id"] == "N05"
    assert result["status"] == "completed"
    assert result["passed"] is True


def test_ensure_g03_review_skips_human_gate(tmp_path: Path) -> None:
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        setup["artifact_dir"],
        "n05-automation-code-check",
        {
            "schema_version": "automation-code-check/1.0",
            "passed": True,
            "fatal_security_violation": False,
            "issues": [],
            "repair_routes": [],
            "generation_count": 1,
            "planned_generation_count": 1,
            "rejected_cases": [],
        },
        ArtifactStatus.COMPLETED,
    )
    result = ensure_g03_review(
        config, setup["artifact_dir"], tmp_path / "g03-auto", QA_AGENTS_ROOT, apply=False
    )
    assert result is not None
    assert result["node_id"] == "G03"
    assert result["action"] == "skipped_human_gate_removed"
    g03 = json.loads(
        (
            setup["artifact_dir"] / "artifacts" / "g03-automation-code-review.json"
        ).read_text(encoding="utf-8")
    )
    assert g03["status"] == "skipped_by_policy"
    assert g03["payload"]["decision"] == "skipped_by_policy"
    again = ensure_g03_review(
        config, setup["artifact_dir"], tmp_path / "g03-auto", QA_AGENTS_ROOT, apply=False
    )
    assert again is None


def test_ensure_a14_dispatch_does_not_overwrite_bundle_while_in_flight(
    tmp_path: Path,
) -> None:
    """A dispatched/running A14 Issue must not trigger a bundle regeneration.

    Regenerating ``a14-input.json`` after dispatch changes its content-addressed
    hash; the Agent output binds the original hash and ingestion fails forever.
    """
    setup = _c5_setup(tmp_path)
    _write_valid_n27(setup["artifact_dir"])
    config = _c5_config()
    first = ensure_a14_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        apply=False,
    )
    assert first is not None and first["action"] == "would_dispatch"
    bundle_path = setup["inputs_dir"] / "a14-input.json"
    original = bundle_path.read_bytes()

    running_issue = {
        "id": "issue-a14-running",
        "identifier": "QAA-999",
        "title": "[REQ-1-r001] A14 服务端自动化生成",
        "status": "in_progress",
    }
    result = ensure_a14_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {"A14": [running_issue]},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "already_dispatched"
    assert result["issue_id"] == "issue-a14-running"
    assert bundle_path.read_bytes() == original


def test_ensure_a15_dispatch_does_not_overwrite_bundle_while_in_flight(
    tmp_path: Path,
) -> None:
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    first = ensure_a15_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        apply=False,
    )
    assert first is not None and first["action"] == "would_dispatch"
    bundle_path = setup["inputs_dir"] / "a15-input.json"
    original = bundle_path.read_bytes()

    running_issue = {
        "id": "issue-a15-running",
        "title": "[REQ-1-r001] A15 契约自动化生成",
        "status": "in_progress",
    }
    result = ensure_a15_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {"A15": [running_issue]},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "already_dispatched"
    assert bundle_path.read_bytes() == original


def test_ensure_a14_dispatch_redispatch_after_failed_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    """A blocked (ingest-failed) attempt frees the rerun budget: the node can
    re-dispatch with a fresh bundle instead of staying in_progress forever."""
    setup = _c5_setup(tmp_path)
    _write_valid_n27(setup["artifact_dir"])
    config = _c5_config()
    config["agent_rerun_budget"] = 1

    def fake_multica(*args: str, **kwargs):
        if args[:2] == ("issue", "create"):
            return {"id": "issue-a14-retry", "identifier": "QAA-1000"}
        return {}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    failed_issue = {
        "id": "issue-a14-old",
        "title": "[REQ-1-r001] A14 服务端自动化生成",
        "status": "blocked",
    }
    result = ensure_a14_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {"A14": [failed_issue]},
        apply=True,
    )
    assert result is not None
    assert result["action"] == "dispatched"
    assert result["issue_id"] == "issue-a14-retry"
    bundles = json.loads(
        (setup["inputs_dir"] / ".issue-bundles.json").read_text(encoding="utf-8")
    )
    assert bundles["issue-a14-retry"].endswith("a14-input.json")


def test_ensure_a22_dispatch_gate_respects_rerun_budget(tmp_path: Path) -> None:
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    config["agent_rerun_budget"] = 1
    done_issues = [
        {"id": "a22-1", "title": "[REQ-1-r001] A22 112 测试数据规划", "status": "done"},
        {"id": "a22-2", "title": "[REQ-1-r001] A22 测试数据规划修正", "status": "done"},
    ]
    result = ensure_a22_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {"A22": done_issues},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "rerun_budget_exhausted"
    assert not (setup["inputs_dir"] / "a22-input.json").exists()


def test_ensure_n27_validation_accepts_needs_human_plan_as_gaps(
    tmp_path: Path,
) -> None:
    """A22 may legally return needs_human (unresolved data semantics). N27 must
    run the security-level structural validation and release the plan as
    completed_with_gaps instead of dead-locking C5 on rejected."""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    _write_artifact(
        setup["artifact_dir"],
        "a22-test-data-plan",
        {
            "schema_version": "test-data-plan/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "input_bundle_hash": "sha256:bundle",
            "status": "needs_human",
            "environment": "112",
            "namespace": "qa-a22-pending-human",
            "planning_mode": "case_explicit",
            "case_plans": [
                {
                    "case_id": "TC-BE-001-BACKEND",
                    "requires_data_construction": True,
                    "source_refs": ["TC-BE-001-BACKEND"],
                    "resources": [
                        {
                            "resource_key": "cd_field",
                            "resource_type": "custom_dimension",
                            "resource_id_variable": "cd_field_id",
                            "setup_operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                        }
                    ],
                }
            ],
            "paused_cases": [],
            "unresolved_requirements": [
                {"requirement_id": "UR-01", "reason_code": "chart_create_op_unverified"}
            ],
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    result = ensure_n27_validation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert result is not None
    assert result["node_id"] == "N27"
    assert result["status"] == "completed_with_gaps"
    assert result["valid"] is True
    n27 = json.loads(
        (setup["artifact_dir"] / "artifacts" / "n27-test-data-plan-validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert n27["payload"]["valid"] is True
    assert n27["payload"]["pending_human"] is True


def test_ensure_n27_validation_carries_paused_cases_as_deferred(
    tmp_path: Path,
) -> None:
    """Paused Cases must reach N27 as deferred_cases so N08 never executes
    them and the run still completes with gaps instead of stalling."""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    _write_artifact(
        setup["artifact_dir"],
        "a22-test-data-plan",
        {
            "schema_version": "test-data-plan/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "input_bundle_hash": "sha256:bundle",
            "status": "needs_human",
            "environment": "112",
            "namespace": "qa-a22-pending-human",
            "planning_mode": "case_explicit",
            "case_plans": [
                {
                    "case_id": "TC-CON-002-CONTRACT",
                    "requires_data_construction": True,
                    "source_refs": ["TC-CON-002-CONTRACT"],
                    "resources": [],
                }
            ],
            "paused_cases": [
                {
                    "case_id": "TC-CON-002-CONTRACT",
                    "reason_code": "historical_fixture_seed_unverified",
                }
            ],
            "unresolved_requirements": [
                {
                    "requirement_id": "UR-04",
                    "reason_code": "historical_fixture_seed_unverified",
                }
            ],
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    result = ensure_n27_validation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert result is not None
    assert result["status"] == "completed_with_gaps"
    n27 = json.loads(
        (setup["artifact_dir"] / "artifacts" / "n27-test-data-plan-validation.json").read_text(
            encoding="utf-8"
        )
    )
    assert n27["payload"]["deferred_cases"] == [
        {
            "case_id": "TC-CON-002-CONTRACT",
            "reason_code": "historical_fixture_seed_unverified",
            "route": "deferred_data_construction",
        }
    ]


def test_ensure_n27_validation_still_rejects_invalid_needs_human_plan(
    tmp_path: Path,
) -> None:
    """Security-level violations (for example an unknown setup operation) must
    stay rejected even when the plan is waiting for human confirmation."""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    _write_artifact(
        setup["artifact_dir"],
        "a22-test-data-plan",
        {
            "schema_version": "test-data-plan/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "input_bundle_hash": "sha256:bundle",
            "status": "needs_human",
            "environment": "112",
            "namespace": "qa-a22-pending-human",
            "planning_mode": "case_explicit",
            "case_plans": [
                {
                    "case_id": "TC-BE-001-BACKEND",
                    "requires_data_construction": True,
                    "source_refs": ["TC-BE-001-BACKEND"],
                    "resources": [
                        {
                            "resource_key": "cd_field",
                            "resource_type": "custom_dimension",
                            "resource_id_variable": "cd_field_id",
                            "setup_operation": "not.a.real.operation",
                        }
                    ],
                }
            ],
            "paused_cases": [],
            "unresolved_requirements": [],
        },
        ArtifactStatus.NEEDS_HUMAN,
    )
    result = ensure_n27_validation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert result is not None
    assert result["status"] == "blocked"
    assert result["valid"] is False
    assert result["decision"] == "rejected"


def _not_applicable_generation(
    artifact_dir: Path, bundle_path: Path
) -> None:
    """A15-style generation: no contract Cases, manifest stays null."""
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    _write_artifact(
        artifact_dir,
        "a15-contract-automation-generation",
        {
            "schema_version": "automation-generation/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "input_bundle_hash": bundle["bundle_hash"],
            "status": "not_applicable",
            "manifest": None,
            "code_candidates": [],
            "rejected_cases": [
                {
                    "case_id": "TC-CON-001-CONTRACT",
                    "reason_code": "contract_ref_missing",
                    "source_refs": ["TC-CON-001-CONTRACT"],
                }
            ],
            "evaluation_oracle_accessed": False,
        },
        ArtifactStatus.NOT_APPLICABLE,
    )


def test_ensure_a18_dispatch_marks_reviewer_skipped_for_not_applicable_generation(
    tmp_path: Path,
) -> None:
    """A not_applicable generation (A15) must produce a deterministic
    not_applicable reviewer marker (A18-CT) instead of leaving the reviewer
    node not_started and stalling the stage card forever."""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A15",
    )
    _not_applicable_generation(setup["artifact_dir"], setup["inputs_dir"] / "a15-input.json")
    result = ensure_a18_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        reviewer="A18-CT",
        apply=False,
    )
    assert result is not None
    assert result["action"] == "skipped_not_applicable"
    marker = json.loads(
        (
            setup["artifact_dir"]
            / "artifacts"
            / "a18-ct-contract-automation-review.json"
        ).read_text(encoding="utf-8")
    )
    assert marker["status"] == "not_applicable"
    assert marker["payload"]["decision"] == "not_applicable"
    assert marker["payload"]["generation_hash"] == content_hash(
        json.loads(
            (
                setup["artifact_dir"]
                / "artifacts"
                / "a15-contract-automation-generation.json"
            ).read_text(encoding="utf-8")
        )["payload"]
    )


def test_ensure_a18_dispatch_not_applicable_marker_is_idempotent(
    tmp_path: Path,
) -> None:
    """The deterministic not_applicable marker must not be rewritten while the
    generation payload is unchanged."""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A15",
    )
    _not_applicable_generation(setup["artifact_dir"], setup["inputs_dir"] / "a15-input.json")
    first = ensure_a18_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        reviewer="A18-CT",
        apply=False,
    )
    assert first is not None and first["action"] == "skipped_not_applicable"
    marker_path = (
        setup["artifact_dir"]
        / "artifacts"
        / "a18-ct-contract-automation-review.json"
    )
    marker_before = marker_path.read_text(encoding="utf-8")
    second = ensure_a18_dispatch(
        config,
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        reviewer="A18-CT",
        apply=False,
    )
    assert second is None
    assert marker_path.read_text(encoding="utf-8") == marker_before


def test_ensure_n05_aggregation_ignores_not_applicable_reviewer_marker(
    tmp_path: Path,
) -> None:
    """A deterministic not_applicable reviewer marker is evidence of a skip,
    not a real review: it must not flip N05 review_passed to False."""
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(config["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
    )
    _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    generation = json.loads(
        (
            setup["artifact_dir"]
            / "artifacts"
            / "a14-backend-automation-generation.json"
        ).read_text(encoding="utf-8")
    )
    _write_artifact(
        setup["artifact_dir"],
        "a18-be-backend-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": content_hash(generation["payload"]),
            "approved": True,
            "issues": [],
        },
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        setup["artifact_dir"],
        "a18-ct-contract-automation-review",
        {
            "schema_version": "automation-review/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "generation_hash": "sha256:not-applicable",
            "decision": "not_applicable",
            "approved": False,
        },
        ArtifactStatus.NOT_APPLICABLE,
    )
    result = ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert result is not None
    assert result["node_id"] == "N05"
    assert result["passed"] is True
    assert result["status"] == "completed"


def test_n05_and_g03_replace_stale_results_when_all_generations_not_applicable(
    tmp_path: Path,
) -> None:
    setup = _c5_setup(tmp_path)
    config = _c5_config()
    for artifact_id, case_id in (
        ("a14-backend-automation-generation", "TC-BE-001-BACKEND"),
        ("a15-contract-automation-generation", "TC-CON-001-CONTRACT"),
    ):
        _write_artifact(
            setup["artifact_dir"],
            artifact_id,
            {
                "schema_version": "automation-generation/1.0",
                "status": "not_applicable",
                "manifest": None,
                "code_candidates": [],
                "rejected_cases": [
                    {
                        "case_id": case_id,
                        "reason_code": "setup_contract_unavailable",
                        "source_refs": [case_id],
                    }
                ],
            },
            ArtifactStatus.NOT_APPLICABLE,
        )
    _write_artifact(
        setup["artifact_dir"],
        "n05-automation-code-check",
        {"schema_version": "automation-code-check/1.0", "passed": True},
        ArtifactStatus.COMPLETED,
    )
    _write_artifact(
        setup["artifact_dir"],
        "g03-automation-code-review",
        {"schema_version": "automation-code-review/1.0", "decision": "approved"},
        ArtifactStatus.COMPLETED,
    )

    n05_result = ensure_n05_aggregation(config, setup["artifact_dir"], QA_AGENTS_ROOT)
    assert n05_result is not None
    assert n05_result["status"] == "not_applicable"
    n05 = json.loads(
        (
            setup["artifact_dir"] / "artifacts" / "n05-automation-code-check.json"
        ).read_text(encoding="utf-8")
    )
    assert n05["payload"]["rejected_cases"] == [
        "TC-BE-001-BACKEND",
        "TC-CON-001-CONTRACT",
    ]
    assert len(n05["evidence_refs"]) == 2

    g03_result = ensure_g03_review(
        config, setup["artifact_dir"], tmp_path / "g03-auto", QA_AGENTS_ROOT, apply=False
    )
    assert g03_result is not None
    assert g03_result["action"] == "skipped_not_applicable"
    g03 = json.loads(
        (
            setup["artifact_dir"] / "artifacts" / "g03-automation-code-review.json"
        ).read_text(encoding="utf-8")
    )
    assert g03["status"] == "not_applicable"
    assert g03["payload"]["n05_artifact_hash"] == n05["artifact_hash"]


def _c5_terminal_artifacts(artifact_dir: Path) -> None:
    """Minimal accepted Artifact set that makes _c5_terminal() True."""
    for artifact_id in (
        "a14-backend-automation-generation",
        "a15-contract-automation-generation",
        "a18-be-backend-automation-review",
        "n05-automation-code-check",
        "g03-automation-code-review",
    ):
        _write_artifact(
            artifact_dir,
            artifact_id,
            {
                "schema_version": "artifact/1.0",
                "workflow_run_id": "REQ-1-r001",
                "source_snapshot_id": "snapshot-1",
            },
            ArtifactStatus.COMPLETED,
        )
    n27 = ArtifactEnvelope(
        workflow_run_id="REQ-1-r001",
        workflow_mode="new_requirement",
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id="snapshot-1",
        producer=Producer("N27"),
        payload={
            "schema_version": "test-data-plan-validation/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "valid": True,
            "decision": "validated",
            "deferred_cases": [],
        },
        status=ArtifactStatus.COMPLETED,
    )
    (artifact_dir / "artifacts" / "n27-test-data-plan-validation.json").write_text(
        json.dumps(n27.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    _write_artifact(
        artifact_dir,
        "a22-test-data-plan",
        {
            "schema_version": "test-data-plan/1.0",
            "workflow_run_id": "REQ-1-r001",
            "source_snapshot_id": "snapshot-1",
            "status": "completed",
            "environment": "112",
            "namespace": "qa-namespace-from-plan",
        },
        ArtifactStatus.COMPLETED,
    )



def test_ensure_a14_dispatch_waits_until_n27_valid(tmp_path: Path) -> None:
    """A14 must not dispatch before the data plan is validated; otherwise
    resource_requirements never reach the generator and N08 cannot construct 112 data."""
    setup = _c5_setup(tmp_path)
    result = ensure_a14_dispatch(
        _c5_config(),
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        apply=False,
    )
    assert result is None
    assert not (setup["inputs_dir"] / "a14-input.json").exists()
    _write_valid_n27(setup["artifact_dir"])
    result = ensure_a14_dispatch(
        _c5_config(),
        "REQ-1-r001",
        setup["artifact_dir"],
        setup["inputs_dir"],
        QA_AGENTS_ROOT,
        {},
        apply=False,
    )
    assert result is not None
    assert result["action"] == "would_dispatch"
    bundle = json.loads((setup["inputs_dir"] / "a14-input.json").read_text(encoding="utf-8"))
    assert any(
        item["artifact_id"] == "a22-test-data-plan"
        for item in bundle["upstream_artifacts"]
    )


def test_c5_terminal_blocks_when_backend_generate_new_missing(tmp_path: Path) -> None:
    """C5 cannot open N07/N08 while a backend generate_new Case is absent from A14."""
    setup = _c5_setup(tmp_path)
    _c5_terminal_artifacts(setup["artifact_dir"])
    assert _sync_module._c5_terminal(setup["artifact_dir"]) is False

    _write_valid_n27(setup["artifact_dir"])
    bundle = prepare_multica_automation_generation_input(
        setup["artifact_dir"] / "artifacts" / "n25-compiled-test-cases.json",
        setup["artifact_dir"] / "artifacts" / "n15-execution-plan.json",
        Path(_c5_config()["automation_target_policy"]),
        setup["inputs_dir"],
        profile_id="A14",
        test_data_plan_path=setup["artifact_dir"] / "artifacts" / "a22-test-data-plan.json",
        test_data_validation_path=setup["artifact_dir"] / "artifacts" / "n27-test-data-plan-validation.json",
    )
    _generation_artifact(
        setup["artifact_dir"],
        setup["inputs_dir"] / "a14-input.json",
        "A14",
        "a14-backend-automation-generation",
        ["TC-BE-001-BACKEND"],
    )
    assert bundle["profile_id"] == "A14"
    assert _sync_module._c5_terminal(setup["artifact_dir"]) is True


def test_ensure_n07_precheck_synthesizes_env_inputs(tmp_path: Path) -> None:
    """N07 must synthesize env target/observed from the run's own data instead
    of waiting forever for a manual environment handoff, so C6 can start."""
    artifact_dir = tmp_path / "artifacts-auto"
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    _c5_terminal_artifacts(artifact_dir)
    config = _c5_config()
    result = ensure_n07_precheck(
        config, "REQ-1-r001", artifact_dir, inputs_dir, QA_AGENTS_ROOT
    )
    assert result is not None
    assert result["node_id"] == "N07"
    assert result["env_input_synthesized"] is True
    target = json.loads((inputs_dir / "env-target.json").read_text(encoding="utf-8"))
    observed = json.loads(
        (inputs_dir / "env-observed.json").read_text(encoding="utf-8")
    )
    assert target["schema_version"] == "environment-target/1.0"
    assert target["environment_class"] == "112"
    assert observed["schema_version"] == "environment-observation/1.0"
    assert observed["test_namespaces"][0]["namespace"] == "qa-namespace-from-plan"
    assert (artifact_dir / "artifacts" / "n07-environment-precheck.json").exists()
    second = ensure_n07_precheck(
        config, "REQ-1-r001", artifact_dir, inputs_dir, QA_AGENTS_ROOT
    )
    assert second is None


def test_policy_path_resolves_hyphenated_default(tmp_path: Path) -> None:
    """Config keys are underscore-separated but policy files are hyphenated;
    the fallback must resolve execution_policy to execution-policy.json."""
    policy = _sync_module._policy_path({}, "execution_policy", QA_AGENTS_ROOT)
    assert policy is not None
    assert policy.name == "execution-policy.json"


def test_multica_timeout_fails_fast(monkeypatch) -> None:
    """A hung multica call must raise instead of holding the sync lock forever."""
    import subprocess as real_subprocess

    def fake_run(*args, **kwargs):
        raise real_subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

    monkeypatch.setattr(_sync_module.subprocess, "run", fake_run)
    try:
        _sync_module._multica("issue", "list", "--project", "p")
    except RuntimeError as error:
        assert "timed out" in str(error)
    else:
        raise AssertionError("_multica must raise on timeout")


def test_multica_binary_falls_back_to_common_paths(monkeypatch) -> None:
    """launchd runs the timer with a minimal PATH; the script must still find
    the multica CLI in the common Homebrew/usr/local locations."""
    monkeypatch.setattr(_sync_module, "_MULTICA_BINARY", None)
    monkeypatch.setattr(_sync_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        _sync_module.os.path,
        "exists",
        lambda path: path == "/usr/local/bin/multica",
    )
    assert _sync_module._multica_binary() == "/usr/local/bin/multica"


def test_multica_binary_raises_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(_sync_module, "_MULTICA_BINARY", None)
    monkeypatch.setattr(_sync_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(_sync_module.os.path, "exists", lambda path: False)
    try:
        _sync_module._multica_binary()
    except RuntimeError as error:
        assert "multica CLI not found" in str(error)
    else:
        raise AssertionError("_multica_binary must raise when the CLI is missing")


def test_sync_run_lock_reports_holder(tmp_path: Path) -> None:
    """A starved sync pass must report who holds the lock instead of failing
    silently, so the unattended timer's skip log is diagnosable."""
    lock_path = tmp_path / ".sync-eight-card.lock"
    with _sync_module._sync_run_lock(lock_path):
        assert lock_path.read_text(encoding="utf-8").startswith("pid=")
        try:
            with _sync_module._sync_run_lock(lock_path):
                pass
        except OSError as error:
            assert "already running" in str(error)
            assert "pid=" in str(error)
        else:
            raise AssertionError("second lock acquisition must fail")


def _a22_needs_human_plan(auto_dir: Path) -> dict:
    plan_payload = {
        "schema_version": "test-data-plan/1.0",
        "namespace": "qa-pilot-001-source-v1",
        "case_plans": [],
        "unresolved_requirements": [
            {
                "requirement_id": "UR-01",
                "reason_code": "chart_create_op_unverified",
                "requirement": "stat_chart 创建接口及参数未验证，图表 setup_operation 需人工确认",
            },
            {
                "requirement_id": "UR-02",
                "reason_code": "fault_injection_capability_unconfirmed",
                "requirement": "TC-BE-005 元数据服务异常、超时等故障注入无已验证机制",
            },
        ],
    }
    _write_artifact(
        auto_dir, "a22-test-data-plan", plan_payload, ArtifactStatus.NEEDS_HUMAN
    )
    return plan_payload


def test_parse_a22_dispositions_requires_full_coverage(monkeypatch) -> None:
    issue = {"id": "issue-a22"}
    unresolved = [
        {"requirement_id": "UR-01"},
        {"requirement_id": "UR-02"},
    ]

    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: [
            {"content": "UR-01: confirmed\nUR-02: 跳过"},
        ],
    )
    result = _sync_module._parse_a22_dispositions(issue, unresolved)
    assert result == [
        {"requirement_id": "UR-01", "disposition": "confirmed"},
        {"requirement_id": "UR-02", "disposition": "skip"},
    ]

    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: [
            {"content": "UR-01: confirmed"},
        ],
    )
    assert _sync_module._parse_a22_dispositions(issue, unresolved) is None

    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: [],
    )
    assert _sync_module._parse_a22_dispositions(issue, unresolved) is None


def test_a22_confirmation_requires_disposition_comment(
    tmp_path: Path, monkeypatch
) -> None:
    auto_dir = tmp_path / "auto"
    _a22_needs_human_plan(auto_dir)
    issues_by_node = {
        "A22": [{"id": "issue-a22", "identifier": "QAA-338", "status": "done"}]
    }

    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: [],
    )
    result = _sync_module.ensure_a22_human_confirmation(
        "run-1", auto_dir, issues_by_node
    )
    assert result is not None
    assert result["action"] == "review_pending"
    assert not (auto_dir / "artifacts" / "a22-human-confirmation.json").exists()

    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: [
            {"content": "UR-01: confirmed\nUR-02: 跳过（无故障注入机制）"},
        ],
    )
    result = _sync_module.ensure_a22_human_confirmation(
        "run-1", auto_dir, issues_by_node
    )
    assert result is not None
    assert result.get("action") != "review_pending"
    assert result["confirmed"] == 1
    assert result["deferred"] == 1
    confirmation = json.loads(
        (auto_dir / "artifacts" / "a22-human-confirmation.json").read_text()
    )
    assert confirmation["payload"]["dispositions"] == [
        {"requirement_id": "UR-01", "disposition": "confirmed"},
        {"requirement_id": "UR-02", "disposition": "skip"},
    ]
    assert confirmation["payload"]["confirmed_requirement_ids"] == ["UR-01"]
    assert confirmation["payload"]["deferred_requirement_ids"] == ["UR-02"]
    assert confirmation["payload"]["decision"] == "confirmed_with_gaps"
    assert confirmation["status"] == "completed_with_gaps"


def test_a22_confirmation_releases_need_evidence_but_blocks_return(
    tmp_path: Path, monkeypatch
) -> None:
    """need_evidence/skip release the gate with gaps; return keeps it open."""
    auto_dir = tmp_path / "auto"
    _a22_needs_human_plan(auto_dir)
    issues_by_node = {
        "A22": [{"id": "issue-a22", "identifier": "QAA-338", "status": "done"}]
    }

    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: [
            {"content": "UR-01: confirmed\nUR-02: need_evidence"},
        ],
    )
    result = _sync_module.ensure_a22_human_confirmation(
        "run-1", auto_dir, issues_by_node
    )
    assert result is not None
    assert result.get("action") != "review_pending"
    assert result["confirmed"] == 1
    assert result["deferred"] == 1
    confirmation = json.loads(
        (auto_dir / "artifacts" / "a22-human-confirmation.json").read_text()
    )
    assert confirmation["payload"]["deferred_requirement_ids"] == ["UR-02"]
    assert confirmation["payload"]["decision"] == "confirmed_with_gaps"

    auto_dir2 = tmp_path / "auto2"
    _a22_needs_human_plan(auto_dir2)
    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: [
            {"content": "UR-01: confirmed\nUR-02: return（计划需修正）"},
        ],
    )
    result = _sync_module.ensure_a22_human_confirmation(
        "run-1", auto_dir2, issues_by_node
    )
    assert result is not None
    assert result["action"] == "review_pending"
    assert "return" in result["reason"]
    assert not (auto_dir2 / "artifacts" / "a22-human-confirmation.json").exists()


def test_refresh_a22_waiting_card_renders_ur_and_sets_in_review(
    tmp_path: Path, monkeypatch
) -> None:
    auto_dir = tmp_path / "auto"
    _a22_needs_human_plan(auto_dir)
    (tmp_path / "inputs").mkdir(parents=True)
    (tmp_path / "inputs" / "a22-input.json").write_text("{}", encoding="utf-8")
    issues_by_node = {
        "A22": [{"id": "issue-a22", "identifier": "QAA-338", "status": "todo"}]
    }
    config = {"internal_project_id": "proj-1"}
    calls = []
    monkeypatch.setattr(
        _sync_module,
        "_multica",
        lambda *args, **kwargs: calls.append(list(args)) or {},
    )

    result = _sync_module._refresh_a22_waiting_card(
        config, "run-1", auto_dir, issues_by_node, apply=True
    )
    assert result is not None
    assert result["approval_count"] == 2
    update_call = next(call for call in calls if call[:2] == ["issue", "update"])
    assert "--status" in update_call and "in_review" in update_call
    card = (tmp_path / "inputs" / "a22-input.json.card.md").read_text()
    assert "UR-01" in card
    assert "未决数据需求" in card
    assert "stat_chart 创建接口及参数未验证" in card


def test_ensure_quality_tail_waits_when_n17_needs_human_even_if_n18_exists(
    tmp_path: Path,
) -> None:
    auto_dir = tmp_path / "artifacts-auto"
    artifacts = auto_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "n08-automation-execution.json").write_text("{}", encoding="utf-8")
    (artifacts / "n17-manual-execution.json").write_text(
        json.dumps({"status": "blocked", "payload": {"pending_count": 2}}),
        encoding="utf-8",
    )
    (artifacts / "n18-quality-signals.json").write_text("{}", encoding="utf-8")
    (artifacts / "n11-quality-decision.json").write_text("{}", encoding="utf-8")

    result = ensure_quality_tail({}, auto_dir, tmp_path)

    assert result == {
        "node_id": "QUALITY_TAIL",
        "status": "blocked",
        "current_node": "N17",
        "next_node": "N17",
    }
    assert not (artifacts / "n18-quality-signals.json").exists()
    assert not (artifacts / "n11-quality-decision.json").exists()


def test_ensure_quality_tail_reruns_blocked_n17_when_inputs_exist(
    tmp_path: Path, monkeypatch
) -> None:
    auto_dir = tmp_path / "artifacts-auto"
    artifacts = auto_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "n08-automation-execution.json").write_text("{}", encoding="utf-8")
    (artifacts / "n17-manual-execution.json").write_text(
        json.dumps({"status": "blocked", "payload": {"pending_count": 4}}),
        encoding="utf-8",
    )
    (artifacts / "n15-execution-plan.json").write_text("{}", encoding="utf-8")
    (artifacts / "n25-compiled-test-cases.json").write_text("{}", encoding="utf-8")
    (artifacts / "n07-environment-precheck.json").write_text("{}", encoding="utf-8")
    (artifacts / "n18-quality-signals.json").write_text("{}", encoding="utf-8")
    policy = tmp_path / "policies" / "quality-policy.json"
    policy.parent.mkdir(parents=True)
    policy.write_text("{}", encoding="utf-8")
    calls: list[int] = []
    monkeypatch.setattr(
        _sync_module,
        "run_server_quality_tail",
        lambda *args, **kwargs: calls.append(1)
        or {"decision": "blocked", "current_node": "N11"},
    )

    result = ensure_quality_tail({}, auto_dir, tmp_path)

    assert calls == [1]
    assert result == {
        "node_id": "QUALITY_TAIL",
        "status": "blocked",
        "current_node": "N11",
        "next_node": "N11",
    }
    assert not (artifacts / "n18-quality-signals.json").exists()




def test_ensure_node_record_issues_refreshes_n08_constructed_assets(
    tmp_path: Path, monkeypatch
) -> None:
    """An existing done N08 record must still get the constructed-asset section."""

    artifact_dir = tmp_path / "artifacts-auto"
    n08 = _write_artifact_with_reason(
        artifact_dir,
        "n08-automation-execution",
        {
            "schema_version": "n08-automation-execution/1.0",
            "decision": "test_failures",
            "next_node": "N09",
            "summary": {"total": 1, "failed": 1, "passed": 0, "skipped": 0},
        },
        ArtifactStatus.COMPLETED_WITH_GAPS,
        reason_code="automation_test_failures",
    )
    inventory = {
        "schema_version": "constructed-test-assets/1.0",
        "assets": [
            {
                "resource_type": "stat_chart",
                "display_name": "自定义维度查看明细验证统计图",
                "resource_id": "BI_chart_46",
                "resource_key": "variant_chart_set",
            }
        ],
    }
    (artifact_dir / "artifacts" / "constructed-test-assets.json").write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
    )
    calls = []

    def fake_multica(*args: str, **kwargs):
        calls.append(list(args))
        if args[:2] == ("issue", "update"):
            return {"id": args[2], "status": args[args.index("--status") + 1]}
        return {"id": f"record-{len(calls)}", "identifier": "QAA-980"}

    monkeypatch.setattr(_sync_module, "_multica", fake_multica)
    synced = ensure_node_record_issues(
        _a11_config(),
        "run-1",
        artifact_dir,
        {"N08": [{"id": "existing-n08", "identifier": "QAA-349", "status": "done"}]},
        apply=True,
    )
    n08_synced = next(record for record in synced if record["node_id"] == "N08")
    assert n08_synced["action"] == "synced"
    update = next(call for call in calls if call[:2] == ["issue", "update"])
    assert "--description-file" in update
    desc = (n08.with_name(f"{n08.name}.record.md")).read_text(encoding="utf-8")
    assert "## 已构造测试数据" in desc
    assert "自定义维度查看明细验证统计图" in desc
    assert "销售订单统计_副本" not in desc
