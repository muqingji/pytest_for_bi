from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from qa_agents.contracts import (
    ArtifactEnvelope,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.gates import (
    build_scope_review_outcome,
    prepare_scope_review_request,
    record_scope_review_decision,
    validate_scope_review_decision,
)
from qa_agents.risk import run_risk_strategy_after_g01
from qa_agents.storage import ArtifactStore


POLICY = {
    "schema_version": "g01-review-policy/1.1",
    "allowed_roles": ["qa_owner"],
    "allowed_dispositions": [
        "confirmed",
        "resolved_upstream",
        "return_to_a02",
        "return_to_a03",
        "return_to_a05",
        "return_to_a06",
    ],
    "required_roles_by_source": {
        "A02": ["qa_owner"],
        "A03": ["qa_owner"],
        "A06": ["qa_owner"],
    },
    "approval_mode": "qa_owner_single_signoff",
    "policy_scope": "pilot_test_design_only",
    "temporary_policy": True,
    "production_release_authority": False,
    "required_approval_fields": ["test_rules"],
}

WORKFLOW_INPUT = {
    "schema_version": "workflow-input/1.0",
    "workflow_mode": "new_requirement",
    "title": "提示文案优化",
    "component_applicability": {
        "frontend": {"status": "not_applicable"},
        "backend": {"status": "applicable"},
        "contract": {"status": "applicable"},
        "e2e": {"status": "not_applicable"},
    },
    "source_access_policy": {
        "business_repositories": "read_only",
        "use_mutable_local_worktree": False,
        "allow_business_repository_metadata_writes": False,
        "writable_targets": ["workflow_artifact_store"],
    },
    "sources": [],
}

RISK_POLICY = {
    "schema_version": "risk-policy/1.0",
    "high_risk_keywords": [],
    "security_keywords": [],
    "data_keywords": [],
    "mandatory_layers": {
        "frontend": "frontend",
        "backend": "backend",
        "contract": "contract",
        "e2e": "e2e",
    },
    "high_severity_finding_score": 4,
    "medium_severity_finding_score": 2,
    "high_risk_keyword_score": 6,
    "large_change_file_threshold": 30,
    "medium_risk_score": 2,
    "high_risk_score": 6,
    "critical_risk_score": 10,
}


def write_gate_artifacts(root: Path) -> tuple[Path, Path, Path]:
    store = ArtifactStore(root)
    common = {
        "workflow_run_id": "run-1",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
        "producer": Producer(component_id="test"),
    }
    artifacts = [
        ArtifactEnvelope(
            **common,
            artifact_id="a02-requirement-analysis",
            payload={
                "ambiguities": [
                    {"id": "AMB-001", "issue_code": "copy_unknown", "message": "文案未确认"}
                ]
            },
        ),
        ArtifactEnvelope(
            **common,
            artifact_id="a03-technical-testability-analysis",
            payload={
                "blocking_items": [
                    {"id": "BI-001", "issue_code": "data_missing", "summary": "数据缺失"}
                ]
            },
        ),
        ArtifactEnvelope(
            **common,
            artifact_id="a06-alignment-result",
            payload={
                "findings": [
                    {"id": "FND-001", "severity": "high", "type": "conflict", "summary": "实现冲突"},
                    {"id": "FND-LOW", "severity": "low", "type": "note", "summary": "低风险"},
                ]
            },
        ),
    ]
    for artifact in artifacts:
        store.write_artifact(artifact)
    artifact_dir = root / "artifacts"
    return (
        artifact_dir / "a02-requirement-analysis.json",
        artifact_dir / "a03-technical-testability-analysis.json",
        artifact_dir / "a06-alignment-result.json",
    )


def approved_decision(request: dict) -> dict:
    roles_by_source = POLICY["required_roles_by_source"]
    return {
        "schema_version": "scope-review-decision/1.0",
        "gate_id": "G01",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "decision": "approved",
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "actor": {"type": "human", "id": "user-1", "role": "qa_owner"},
        "reason": "逐项审核完成",
        "test_rules": {"scope": "approved test rules"},
        "resolutions": [
            {
                "issue_id": item["issue_id"],
                "disposition": "confirmed",
                "rationale": "已确认该口径并接受为测试输入",
                "owner": "qa-owner",
                "approvals": [
                    {"type": "human", "id": f"{role}-user", "role": role}
                    for role in roles_by_source[item["source"]]
                ],
            }
            for item in request["issues"]
        ],
    }


def prepare_request(paths: tuple[Path, Path, Path], output_dir: Path) -> dict:
    return prepare_scope_review_request(*paths, output_dir, policy=POLICY)


def test_prepare_g01_request_and_validate_complete_human_approval(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")

    assert request["status"] == "needs_human"
    assert request["issue_count"] == 3
    assert [item["issue_id"] for item in request["issues"]] == [
        "A02:AMB-001",
        "A03:BI-001",
        "A06:FND-001",
    ]
    decision = validate_scope_review_decision(request, approved_decision(request), POLICY)
    assert decision["decision"] == "approved"
    assert decision["decision_hash"].startswith("sha256:")


def test_g01_rejects_agent_approval_and_partial_approval(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    decision = approved_decision(request)
    decision["actor"]["type"] = "agent"
    with pytest.raises(SecurityPolicyError, match="human actor"):
        validate_scope_review_decision(request, decision, POLICY)

    decision = approved_decision(request)
    decision["resolutions"].pop()
    with pytest.raises(ContractError, match="resolve every"):
        validate_scope_review_decision(request, decision, POLICY)

    decision = approved_decision(request)
    a06_resolution = next(
        item for item in decision["resolutions"] if item["issue_id"].startswith("A06:")
    )
    a06_resolution["approvals"] = []
    with pytest.raises(SecurityPolicyError, match="qa_owner"):
        validate_scope_review_decision(request, decision, POLICY)

    decision = approved_decision(request)
    decision["actor"]["role"] = "technical_owner"
    with pytest.raises(SecurityPolicyError, match="actor role is not authorized"):
        validate_scope_review_decision(request, decision, POLICY)

    decision = approved_decision(request)
    decision.pop("test_rules")
    with pytest.raises(ContractError, match="requires decision field: test_rules"):
        validate_scope_review_decision(request, decision, POLICY)


def test_g01_request_changes_requires_and_compiles_upstream_routes(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    decision = approved_decision(request)
    decision["decision"] = "request_changes"
    decision["reason"] = "需求文案需要产品补充"
    decision["resolutions"] = [
        {
            "issue_id": "A02:AMB-001",
            "disposition": "return_to_a02",
            "rationale": "补充中英文精确文案",
            "owner": "product-owner",
            "approvals": [],
        }
    ]
    recorded = validate_scope_review_decision(request, decision, POLICY)
    outcome = build_scope_review_outcome(request, recorded, POLICY)

    assert outcome["action"] == "return_upstream"
    assert outcome["next_node"] is None
    assert outcome["resume_at"] == "A06"
    assert outcome["return_routes"] == [
        {
            "issue_id": "A02:AMB-001",
            "issue_code": "copy_unknown",
            "source": "A02",
            "target_node": "A02",
            "owner": "product-owner",
            "rationale": "补充中英文精确文案",
        }
    ]
    assert outcome["invalidation"] == {
        "roots": ["A06"],
        "include_all_descendants": True,
    }

    decision["resolutions"][0]["disposition"] = "confirmed"
    with pytest.raises(ContractError, match="at least one upstream return route"):
        validate_scope_review_decision(request, decision, POLICY)

    decision["decision"] = "rejected"
    recorded_rejection = validate_scope_review_decision(request, decision, POLICY)
    rejected_outcome = build_scope_review_outcome(request, recorded_rejection, POLICY)
    assert rejected_outcome["action"] == "terminate"
    assert rejected_outcome["return_routes"] == []


def test_g01_approved_outcome_continues_only_to_n24(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    recorded = validate_scope_review_decision(request, approved_decision(request), POLICY)
    outcome = build_scope_review_outcome(request, recorded, POLICY)

    assert outcome["action"] == "continue"
    assert outcome["next_node"] == "N24"
    assert outcome["return_routes"] == []
    assert outcome["outcome_hash"].startswith("sha256:")


def test_record_g01_decision_persists_decision_and_routing_outcome(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    input_store = ArtifactStore(tmp_path / "inputs")
    decision_path = input_store.write_json("decision.json", approved_decision(request))
    policy_path = input_store.write_json("policy.json", POLICY)

    recorded = record_scope_review_decision(
        tmp_path / "g01" / "g01-review-request.json",
        decision_path,
        policy_path,
        tmp_path / "recorded",
    )

    assert recorded["decision"] == "approved"
    persisted = json.loads(
        (tmp_path / "recorded" / "g01-review-decision.json").read_text(encoding="utf-8")
    )
    outcome = json.loads(
        (tmp_path / "recorded" / "g01-review-outcome.json").read_text(encoding="utf-8")
    )
    assert persisted["decision_hash"] == recorded["decision_hash"]
    assert outcome["decision_hash"] == recorded["decision_hash"]
    assert outcome["next_node"] == "N24"


def test_g01_approval_is_invalidated_when_request_changes(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    decision = approved_decision(request)
    changed_request = dict(request)
    changed_request["issue_count"] += 1
    changed_request["request_hash"] = "sha256:stale"

    with pytest.raises(ContractError, match="request hash is invalid"):
        validate_scope_review_decision(changed_request, decision, POLICY)


def test_g01_request_is_bound_to_the_exact_review_policy(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    changed_policy = {**POLICY, "policy_scope": "production_release"}

    with pytest.raises(ContractError, match="does not match the bound request policy"):
        validate_scope_review_decision(
            request,
            approved_decision(request),
            changed_policy,
        )

    unsafe_policy = {
        **POLICY,
        "temporary_policy": True,
        "production_release_authority": True,
    }
    with pytest.raises(SecurityPolicyError, match="cannot grant production release authority"):
        prepare_scope_review_request(
            *paths,
            tmp_path / "unsafe",
            policy=unsafe_policy,
        )


def test_n24_requires_recorded_g01_approval(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    raw_decision = approved_decision(request)
    recorded_decision = validate_scope_review_decision(request, raw_decision, POLICY)
    alignment = json.loads(paths[2].read_text(encoding="utf-8"))
    change_set = {"changed_files": ["Service.java"], "summary": {"files_changed": 1}}

    artifact = run_risk_strategy_after_g01(
        WORKFLOW_INPUT,
        change_set,
        alignment,
        request,
        recorded_decision,
        RISK_POLICY,
        POLICY,
        tmp_path / "n24",
    )
    assert artifact["artifact_id"] == "n24-test-strategy"
    assert artifact["payload"]["risk_level"] == "medium"
    assert artifact["payload"]["required_layers"] == ["backend", "contract"]

    blocked = dict(raw_decision)
    blocked["decision"] = "request_changes"
    blocked["reason"] = "需要回流"
    blocked["resolutions"] = [
        {
            "issue_id": request["issues"][0]["issue_id"],
            "disposition": "return_to_a02",
            "rationale": "补充需求",
            "owner": "product",
            "approvals": [],
        }
    ]
    blocked_record = validate_scope_review_decision(request, blocked, POLICY)
    with pytest.raises(ContractError, match="blocked until G01 is approved"):
        run_risk_strategy_after_g01(
            WORKFLOW_INPUT,
            change_set,
            alignment,
            request,
            blocked_record,
            RISK_POLICY,
            POLICY,
            tmp_path / "blocked",
        )


def test_n24_rejects_tampered_g01_decision_hash(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    recorded = validate_scope_review_decision(request, approved_decision(request), POLICY)
    recorded["reason"] = "篡改后的理由"
    alignment = json.loads(paths[2].read_text(encoding="utf-8"))

    with pytest.raises(ContractError, match="decision hash is invalid"):
        run_risk_strategy_after_g01(
            WORKFLOW_INPUT,
            {"changed_files": [], "summary": {"files_changed": 0}},
            alignment,
            request,
            recorded,
            RISK_POLICY,
            POLICY,
            tmp_path / "n24",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("workflow_run_id", "run-2", "another workflow run"),
        ("source_snapshot_id", "snapshot-2", "another source snapshot"),
        ("workflow_mode", "change_regression", "another workflow mode"),
    ],
)
def test_n24_rejects_a06_from_another_execution_identity(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    recorded = validate_scope_review_decision(request, approved_decision(request), POLICY)
    alignment = json.loads(paths[2].read_text(encoding="utf-8"))
    alignment[field] = value
    alignment["artifact_hash"] = artifact_hash_from_mapping(alignment)

    with pytest.raises(ContractError, match=message):
        run_risk_strategy_after_g01(
            WORKFLOW_INPUT,
            {"changed_files": [], "summary": {"files_changed": 0}},
            alignment,
            request,
            recorded,
            RISK_POLICY,
            POLICY,
            tmp_path / "n24",
        )


def test_n24_rejects_a06_not_bound_by_g01_request(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    recorded = validate_scope_review_decision(request, approved_decision(request), POLICY)
    alignment = json.loads(paths[2].read_text(encoding="utf-8"))
    alignment["payload"] = {"findings": []}
    alignment["artifact_hash"] = artifact_hash_from_mapping(alignment)

    with pytest.raises(ContractError, match="does not bind the current A06 Artifact hash"):
        run_risk_strategy_after_g01(
            WORKFLOW_INPUT,
            {"changed_files": [], "summary": {"files_changed": 0}},
            alignment,
            request,
            recorded,
            RISK_POLICY,
            POLICY,
            tmp_path / "n24",
        )


def test_n24_rechecks_required_g01_signatures(tmp_path: Path) -> None:
    paths = write_gate_artifacts(tmp_path / "run")
    request = prepare_request(paths, tmp_path / "g01")
    raw = approved_decision(request)
    a06_resolution = next(
        item for item in raw["resolutions"] if item["issue_id"].startswith("A06:")
    )
    a06_resolution["approvals"] = []
    recorded = dict(raw)
    recorded["decision_hash"] = content_hash(raw)
    alignment = json.loads(paths[2].read_text(encoding="utf-8"))

    with pytest.raises(SecurityPolicyError, match="qa_owner"):
        run_risk_strategy_after_g01(
            WORKFLOW_INPUT,
            {"changed_files": [], "summary": {"files_changed": 0}},
            alignment,
            request,
            recorded,
            RISK_POLICY,
            POLICY,
            tmp_path / "n24",
        )
