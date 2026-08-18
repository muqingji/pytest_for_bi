import json
from pathlib import Path
import shutil

import importlib.util

from qa_agents.contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    content_hash,
)
from qa_agents.multica import prepare_multica_oracle_review_input
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
ensure_a08_dispatch = _sync_module.ensure_a08_dispatch
ensure_a08_correction_dispatch = _sync_module.ensure_a08_correction_dispatch
ensure_a09_dispatch = _sync_module.ensure_a09_dispatch
ensure_a09_correction_dispatch = _sync_module.ensure_a09_correction_dispatch
ensure_n04_validation = _sync_module.ensure_n04_validation
ensure_g02_review = _sync_module.ensure_g02_review
ensure_human_correction_dispatch = _sync_module.ensure_human_correction_dispatch

PILOT_RUN = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pilot"
QA_AGENTS_ROOT = Path(__file__).resolve().parents[1]


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

    def fake_multica(*args: str):
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

    def fake_multica(*args: str):
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

    def fake_multica(*args: str):
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

    def fake_multica(*args: str):
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

    def fake_multica(*args: str):
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
    assert producer["model_provider"] == "deepseek"
    assert producer["model_snapshot"] == "deepseek-v4-flash"


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
            if title.startswith("Human A08 correction"):
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
            if title.startswith("Human A08 correction"):
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
