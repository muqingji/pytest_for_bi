"""Deterministic stage-two node drivers: N25 after G02, N26 after A11, N15 after N26."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    content_hash,
)
from qa_agents.errors import ContractError
from qa_agents.stage_two_nodes import (
    run_n15_after_n26,
    run_n25_after_g02,
    run_n26_after_a11,
)
from qa_agents.storage import ArtifactStore

RUN_ID = "run-stage-two"
MODE = "new_requirement"
SNAPSHOT = "snapshot-v1"


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def envelope(
    artifact_id: str,
    payload: dict,
    *,
    status: ArtifactStatus = ArtifactStatus.COMPLETED,
    producer_id: str = "N25",
    evidence_refs: tuple[EvidenceRef, ...] = (),
) -> dict:
    return ArtifactEnvelope(
        workflow_run_id=RUN_ID,
        workflow_mode=MODE,
        artifact_id=artifact_id,
        source_snapshot_id=SNAPSHOT,
        producer=Producer(component_id=producer_id, runtime="deterministic"),
        payload=payload,
        status=status,
        evidence_refs=evidence_refs,
    ).to_dict()


def parent_cases() -> list[dict]:
    return [
        {
            "id": "CASE-001",
            "title": "查看明细场景化双语提示",
            "intent_ids": ["INTENT-001"],
            "layer": "scenario",
            "required_layers": ["backend", "contract"],
            "risk": "critical",
            "priority": "P0",
            "source_refs": ["REQ-001"],
            "preconditions": ["准备目标场景数据"],
            "test_data": {"language": ["zh-CN", "en"]},
            "steps": ["调用查看明细接口"],
            "expected": [{"id": "E1", "description": "返回冻结提示"}],
            "cleanup": [],
            "execution_policy": {"allowed_modes": ["automated"]},
            "automation_candidate": True,
        },
        {
            "id": "CASE-002",
            "title": "查看明细接口鉴权",
            "intent_ids": ["INTENT-002"],
            "layer": "scenario",
            "required_layers": ["e2e"],
            "risk": "high",
            "priority": "P1",
            "source_refs": ["REQ-002"],
            "preconditions": [],
            "test_data": {},
            "steps": ["无权限调用查看明细接口"],
            "expected": [{"id": "E2", "description": "返回无权限错误"}],
            "cleanup": [],
            "execution_policy": {"allowed_modes": ["automated"]},
            "automation_candidate": True,
        },
    ]


def write_a08_artifact(dir_path: Path) -> dict:
    artifact = ArtifactEnvelope(
        workflow_run_id=RUN_ID,
        workflow_mode=MODE,
        artifact_id="a08-test-design-ir",
        source_snapshot_id=SNAPSHOT,
        producer=Producer(component_id="A08", runtime="multica"),
        payload={
            "schema_version": "test-design-ir/1.1",
            "test_intents": [],
            "parent_cases": parent_cases(),
            "coverage_matrix": [],
            "test_rule_coverage": [],
        },
        status=ArtifactStatus.COMPLETED,
    )
    ArtifactStore(dir_path).write_artifact(artifact)
    return artifact.to_dict()


def g02_request(design: dict) -> dict:
    raw = {
        "schema_version": "test-case-ir-review-request/1.0",
        "gate_id": "G02",
        "workflow_run_id": RUN_ID,
        "workflow_mode": MODE,
        "source_snapshot_id": SNAPSHOT,
        "status": "pending",
        "decision": "pending",
        "review_key": "review-key-1",
        "outcome_contract": "test-case-ir-review-outcome/1.0",
        "decision_contract": "test-case-ir-review-decision/1.0",
        "upstream_artifacts": [
            {"artifact_id": "a08-test-design-ir", "artifact_hash": design["artifact_hash"]}
        ],
        "review_policy": {
            "policy_hash": "policy-hash-1",
            "approval_mode": "named_qa_owner_single_signoff",
        },
        "review_summary": {"blocking_issue_count": 0, "warning_count": 0},
        "multica_control": {"initial_status": "in_review"},
        "created_at": "2026-08-10T10:50:08+00:00",
    }
    raw["request_hash"] = content_hash(raw)
    return raw


def g02_outcome(request: dict, *, decision: str = "approved") -> dict:
    next_node = "N25" if decision == "approved" else "A08"
    raw = {
        "schema_version": "test-case-ir-review-outcome/1.0",
        "gate_id": "G02",
        "workflow_run_id": RUN_ID,
        "source_snapshot_id": SNAPSHOT,
        "request_hash": request["request_hash"],
        "review_key": request["review_key"],
        "decision_hash": "sha256:decision",
        "decision": decision,
        "status": "completed" if decision == "approved" else "blocked_input",
        "action": "continue" if decision == "approved" else "return_upstream",
        "next_node": next_node,
        "resume_at": next_node,
        "invalidation": {"roots": [] if decision == "approved" else ["A08"], "include_all_descendants": decision != "approved"},
        "idempotency_key": "sha256:idem",
    }
    raw["outcome_hash"] = content_hash(raw)
    return raw


def write_compiled_artifact(dir_path: Path, design: dict) -> dict:
    compiled = envelope(
        "n25-compiled-test-cases",
        {
            "schema_version": "n25-compiled-test-cases/1.0",
            "parent_artifact_id": "a08-test-design-ir",
            "parent_artifact_hash": design["artifact_hash"],
            "compiled_cases": [
                {
                    "id": "CASE-001-BACKEND",
                    "parent_case_id": "CASE-001",
                    "layer": "backend",
                    "title": "backend child",
                    "expected": [{"id": "E1", "description": "返回冻结提示"}],
                },
                {
                    "id": "CASE-001-CONTRACT",
                    "parent_case_id": "CASE-001",
                    "layer": "contract",
                    "title": "contract child",
                    "expected": [{"id": "E1", "description": "返回冻结提示"}],
                },
                {
                    "id": "CASE-002-E2E",
                    "parent_case_id": "CASE-002",
                    "layer": "e2e",
                    "title": "e2e child",
                    "expected": [{"id": "E2", "description": "返回无权限错误"}],
                },
            ],
            "parent_count": 2,
            "child_count": 3,
            "compile_rule_version": "n25-compiler/1.0",
        },
    )
    ArtifactStore(dir_path).write_artifact(
        ArtifactEnvelope(
            workflow_run_id=RUN_ID,
            workflow_mode=MODE,
            artifact_id="n25-compiled-test-cases",
            source_snapshot_id=SNAPSHOT,
            producer=Producer(component_id="N25", runtime="deterministic"),
            payload=compiled["payload"],
            status=ArtifactStatus.COMPLETED,
            evidence_refs=(
                EvidenceRef(
                    source_type="artifact",
                    source_id="a08-test-design-ir",
                    location="a08-test-design-ir.json",
                    content_hash=design["artifact_hash"],
                ),
            ),
        )
    )
    return compiled


def a11_bundle(design: dict, compiled: dict) -> dict:
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": RUN_ID,
        "workflow_mode": MODE,
        "source_snapshot_id": SNAPSHOT,
        "profile_id": "A11",
        "profile_version": "1.0.0",
        "output_contract": "split-review/1.0",
        "allowed_inputs": {
            "parent_test_cases": design["payload"]["parent_cases"],
            "compiled_child_cases": compiled["payload"]["compiled_cases"],
            "oracle_rule_library": {"schema_version": "oracle-rule-library/1.0"},
        },
        "upstream_artifacts": [
            {"artifact_id": "a08-test-design-ir", "artifact_hash": design["artifact_hash"]},
            {"artifact_id": "n25-compiled-test-cases", "artifact_hash": compiled["artifact_hash"]},
        ],
        "integrity": {
            "evaluation_oracle_registry_included": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    bundle["bundle_hash"] = content_hash(bundle)
    return bundle


def a11_review_payload(bundle: dict, *, approved: bool = True, issue: dict | None = None) -> dict:
    parents = bundle["allowed_inputs"]["parent_test_cases"]
    children = bundle["allowed_inputs"]["compiled_child_cases"]
    issues = [] if approved and issue is None else [issue or {
        "id": "A11-001",
        "issue_code": "A11-COVERAGE-GAP",
        "severity": "blocking",
        "category": "coverage",
        "message": "coverage gap",
        "path": "case",
        "route_to": "N26",
        "case_id": children[0]["id"],
        "source_refs": [{"type": "compiled_case", "id": children[0]["id"]}],
        "recommendation": "fix",
    }]
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed" if approved else "needs_human",
        "approved": approved,
        "issues": issues,
        "parent_case_coverage": [
            {
                "parent_case_id": parent["id"],
                "status": "covered",
                "covered_child_ids": [
                    child["id"] for child in children if child["parent_case_id"] == parent["id"]
                ],
                "source_refs": [{"type": "parent_case", "id": parent["id"]}],
                "rationale": "children cover the parent",
            }
            for parent in parents
        ],
        "layer_coverage": [
            {
                "layer": layer,
                "status": "covered",
                "case_ids": [
                    child["id"] for child in children if child["layer"] == layer
                ],
                "source_refs": [{"type": "layer", "id": layer}],
                "rationale": "layer covered",
            }
            for layer in sorted({child["layer"] for child in children})
        ],
        "evaluation_oracle_accessed": False,
    }


def write_a11_review_artifact(dir_path: Path, bundle: dict, payload: dict) -> dict:
    review = envelope(
        "a11-split-coverage-review",
        payload,
        producer_id="A11",
        status=ArtifactStatus(payload["status"]),
        evidence_refs=(
            EvidenceRef(
                source_type="multica_agent_input",
                source_id="A11",
                location="a11-input.json",
                content_hash=bundle["bundle_hash"],
            ),
        ),
    )
    ArtifactStore(dir_path).write_artifact(
        ArtifactEnvelope(
            workflow_run_id=RUN_ID,
            workflow_mode=MODE,
            artifact_id="a11-split-coverage-review",
            source_snapshot_id=SNAPSHOT,
            producer=Producer(component_id="A11", runtime="multica"),
            payload=payload,
            status=ArtifactStatus(payload["status"]),
            evidence_refs=(
                EvidenceRef(
                    source_type="multica_agent_input",
                    source_id="A11",
                    location="a11-input.json",
                    content_hash=bundle["bundle_hash"],
                ),
            ),
        )
    )
    return review


def test_n25_compiles_layered_children_after_g02_approval(tmp_path: Path) -> None:
    stage = tmp_path / "stage13"
    design = write_a08_artifact(stage)
    request = g02_request(design)
    outcome = g02_outcome(request)
    request_path = write_json(tmp_path / "g02" / "g02-review-request.json", request)
    outcome_path = write_json(tmp_path / "g02" / "g02-review-outcome.json", outcome)

    artifact = run_n25_after_g02(
        stage / "artifacts" / "a08-test-design-ir.json",
        request_path,
        outcome_path,
        stage,
    )

    assert artifact["artifact_id"] == "n25-compiled-test-cases"
    assert artifact["status"] == "completed"
    payload = artifact["payload"]
    assert payload["parent_artifact_hash"] == design["artifact_hash"]
    assert payload["child_count"] == 3
    child_ids = {item["id"] for item in payload["compiled_cases"]}
    assert child_ids == {"CASE-001-BACKEND", "CASE-001-CONTRACT", "CASE-002-E2E"}


def test_n25_rejects_non_approved_g02_outcome(tmp_path: Path) -> None:
    stage = tmp_path / "stage13"
    design = write_a08_artifact(stage)
    request = g02_request(design)
    outcome = g02_outcome(request, decision="request_changes")
    request_path = write_json(tmp_path / "g02" / "g02-review-request.json", request)
    outcome_path = write_json(tmp_path / "g02" / "g02-review-outcome.json", outcome)

    with pytest.raises(ContractError, match="approved G02 outcome"):
        run_n25_after_g02(
            stage / "artifacts" / "a08-test-design-ir.json",
            request_path,
            outcome_path,
            stage,
        )


def test_n25_rejects_outcome_bound_to_other_request(tmp_path: Path) -> None:
    stage = tmp_path / "stage13"
    design = write_a08_artifact(stage)
    request = g02_request(design)
    outcome = g02_outcome(request)
    outcome["request_hash"] = "sha256:other"
    outcome["outcome_hash"] = content_hash({k: v for k, v in outcome.items() if k != "outcome_hash"})
    request_path = write_json(tmp_path / "g02" / "g02-review-request.json", request)
    outcome_path = write_json(tmp_path / "g02" / "g02-review-outcome.json", outcome)

    with pytest.raises(ContractError, match="does not bind the review request"):
        run_n25_after_g02(
            stage / "artifacts" / "a08-test-design-ir.json",
            request_path,
            outcome_path,
            stage,
        )


def test_n25_rejects_tampered_a08_artifact_hash(tmp_path: Path) -> None:
    stage = tmp_path / "stage13"
    design = write_a08_artifact(stage)
    request = g02_request(design)
    outcome = g02_outcome(request)
    request_path = write_json(tmp_path / "g02" / "g02-review-request.json", request)
    outcome_path = write_json(tmp_path / "g02" / "g02-review-outcome.json", outcome)
    artifact_path = stage / "artifacts" / "a08-test-design-ir.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["payload"]["parent_cases"].pop()
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ContractError, match="Artifact hash mismatch"):
        run_n25_after_g02(
            artifact_path,
            request_path,
            outcome_path,
            stage,
        )


def test_n26_selects_cases_after_approved_a11(tmp_path: Path) -> None:
    stage = tmp_path / "stage13"
    design = write_a08_artifact(stage)
    request = g02_request(design)
    outcome = g02_outcome(request)
    run_n25_after_g02(
        stage / "artifacts" / "a08-test-design-ir.json",
        write_json(tmp_path / "g02" / "g02-review-request.json", request),
        write_json(tmp_path / "g02" / "g02-review-outcome.json", outcome),
        stage,
    )
    compiled = json.loads(
        (stage / "artifacts" / "n25-compiled-test-cases.json").read_text(encoding="utf-8")
    )
    bundle = a11_bundle(design, compiled)
    bundle_path = write_json(tmp_path / "a11" / "a11-input.json", bundle)
    payload = a11_review_payload(bundle)
    review = write_a11_review_artifact(tmp_path / "stage14", bundle, payload)
    review_path = write_json(
        tmp_path / "stage14" / "a11-split-coverage-review.json", review
    )

    artifact = run_n26_after_a11(
        stage / "artifacts" / "n25-compiled-test-cases.json",
        review_path,
        bundle_path,
        tmp_path / "stage15",
    )

    assert artifact["artifact_id"] == "n26-test-selection"
    assert artifact["status"] == "completed"
    selected = {item["case_id"] for item in artifact["payload"]["selected_cases"]}
    assert selected == {"CASE-001-BACKEND", "CASE-001-CONTRACT", "CASE-002-E2E"}


def test_n26_rejects_non_approved_a11_review(tmp_path: Path) -> None:
    stage = tmp_path / "stage13"
    design = write_a08_artifact(stage)
    request = g02_request(design)
    outcome = g02_outcome(request)
    run_n25_after_g02(
        stage / "artifacts" / "a08-test-design-ir.json",
        write_json(tmp_path / "g02" / "g02-review-request.json", request),
        write_json(tmp_path / "g02" / "g02-review-outcome.json", outcome),
        stage,
    )
    compiled = json.loads(
        (stage / "artifacts" / "n25-compiled-test-cases.json").read_text(encoding="utf-8")
    )
    bundle = a11_bundle(design, compiled)
    bundle_path = write_json(tmp_path / "a11" / "a11-input.json", bundle)
    payload = a11_review_payload(bundle, approved=False)
    review = write_a11_review_artifact(tmp_path / "stage14", bundle, payload)
    review_path = write_json(
        tmp_path / "stage14" / "a11-split-coverage-review.json", review
    )

    with pytest.raises(ContractError, match="approved A11 split-coverage review"):
        run_n26_after_a11(
            stage / "artifacts" / "n25-compiled-test-cases.json",
            review_path,
            bundle_path,
            tmp_path / "stage15",
        )


def test_n15_compiles_execution_plan_after_n26(tmp_path: Path) -> None:
    stage = tmp_path / "stage13"
    run_manifest_path = write_json(
        tmp_path / "multica-run-manifest.json", {"workflow_run_id": RUN_ID}
    )
    design = write_a08_artifact(stage)
    request = g02_request(design)
    outcome = g02_outcome(request)
    run_n25_after_g02(
        stage / "artifacts" / "a08-test-design-ir.json",
        write_json(tmp_path / "g02" / "g02-review-request.json", request),
        write_json(tmp_path / "g02" / "g02-review-outcome.json", outcome),
        stage,
        run_manifest_path=run_manifest_path,
    )
    compiled = json.loads(
        (stage / "artifacts" / "n25-compiled-test-cases.json").read_text(encoding="utf-8")
    )
    bundle = a11_bundle(design, compiled)
    bundle_path = write_json(tmp_path / "a11" / "a11-input.json", bundle)
    payload = a11_review_payload(bundle)
    review = write_a11_review_artifact(tmp_path / "stage14", bundle, payload)
    review_path = write_json(
        tmp_path / "stage14" / "a11-split-coverage-review.json", review
    )
    run_n26_after_a11(
        stage / "artifacts" / "n25-compiled-test-cases.json",
        review_path,
        bundle_path,
        tmp_path / "stage15",
        run_manifest_path=run_manifest_path,
    )
    selection = json.loads(
        (tmp_path / "stage15" / "artifacts" / "n26-test-selection.json").read_text(
            encoding="utf-8"
        )
    )

    artifact = run_n15_after_n26(
        tmp_path / "stage15" / "artifacts" / "n26-test-selection.json",
        stage / "artifacts" / "n25-compiled-test-cases.json",
        tmp_path / "stage16",
        run_manifest_path=run_manifest_path,
    )

    assert artifact["artifact_id"] == "n15-execution-plan"
    assert artifact["status"] == "completed"
    actions = {item["case_id"]: item["action"] for item in artifact["payload"]["actions"]}
    assert set(actions) == {"CASE-001-BACKEND", "CASE-001-CONTRACT", "CASE-002-E2E"}
    assert all(action == "generate_new" for action in actions.values())
    checkpoint = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    assert checkpoint["current_node"] == "N15"
    assert checkpoint["stage_two"]["status"] == "completed"
    assert checkpoint["stage_two"]["next_node"] == "N07"
    assert checkpoint["stage_two"]["n25"]["child_count"] == 3
    assert checkpoint["stage_two"]["a11"]["approved"] is True
    assert checkpoint["stage_two"]["n26"]["unresolved_count"] == 0
    assert checkpoint["stage_two"]["n15"]["action_counts"]["generate_new"] == 3
