import json
from pathlib import Path

import importlib.util

from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_eight_card_progress.py"
_spec = importlib.util.spec_from_file_location("sync_eight_card_progress", _SCRIPT_PATH)
_sync_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_sync_module)
ensure_g01_scope_review = _sync_module.ensure_g01_scope_review
prepare_reconcile_spec = _sync_module.prepare_reconcile_spec


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
    assert issues[0]["category"] == "需求待确认"
    assert issues[1]["category"] == "技术方案待确认"
    assert issues[2]["category"] == "实现与测试范围待确认"
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
