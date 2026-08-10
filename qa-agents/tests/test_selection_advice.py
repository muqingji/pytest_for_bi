"""Hermetic tests for A12 Test Selection Advisor and N26 advice validation."""

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
from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.multica import (
    ingest_multica_output,
    prepare_multica_selection_advice_input,
)
from qa_agents.selection import (
    apply_selection_advice,
    compile_execution_plan,
    select_cases,
)
from qa_agents.storage import ArtifactStore


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_RUN_ID = "multica-run-selection"
WORKFLOW_MODE = "new_requirement"
SOURCE_SNAPSHOT_ID = "snapshot-selection-v1"


def child_case(case_id: str, *, layer: str = "backend", modules: list[str] | None = None) -> dict:
    return {
        "id": case_id,
        "title": f"Child {case_id}",
        "parent_case_id": "PARENT-001",
        "intent_ids": ["INTENT-001"],
        "layer": layer,
        "required_layers": ["backend", "contract"],
        "risk": "critical",
        "priority": "P0",
        "source_refs": ["REQ-001"],
        "preconditions": [],
        "test_data": {"dataset": ["zh-CN"]},
        "steps": ["call api"],
        "expected": [
            {
                "id": "EXP-1",
                "description": "returns message",
                "oracle": {
                    "type": "deterministic",
                    "observation_point": "response.message",
                    "matcher": "exact",
                    "source_ref": "REQ-001",
                },
            }
        ],
        "cleanup": [],
        "execution_policy": {"allowed_modes": ["automated"]},
        "automation_candidate": True,
        "evidence_modules": modules or [f"{case_id}-module"],
    }


def cases() -> list[dict]:
    return [
        child_case("CASE-001-BACKEND", modules=["billing-core"]),
        child_case("CASE-002-CONTRACT", layer="contract", modules=["billing-core", "api"]),
        child_case("CASE-003-E2E", layer="e2e", modules=["ui-flow"]),
    ]


def base_policy() -> dict:
    return {
        "schema_version": "test-selection-policy/1.0",
        "forced_selection": [
            {
                "rule_id": "policy-smoke-must-run",
                "selection": "must_run",
                "layers": ["smoke"],
                "reason": "P0 smoke never skippable",
            }
        ],
        "skip_selection": [],
    }


def select(cases_list=None, assets=None, **kwargs) -> dict:
    return select_cases(cases_list if cases_list is not None else cases(), assets, **kwargs)


# ---------------------------------------------------------------- N26 rules


def test_selection_policy_forces_must_run_by_layer() -> None:
    policy = base_policy()
    policy["forced_selection"].append(
        {"rule_id": "policy-auth-must-run", "selection": "must_run", "layers": ["backend"]}
    )
    selection = select(selection_policy=policy)
    by_id = {item["case_id"]: item for item in selection["selected_cases"]}
    assert by_id["CASE-001-BACKEND"]["selection"] == "must_run"
    assert by_id["CASE-001-BACKEND"]["rule_id"] == "policy-auth-must-run"
    assert by_id["CASE-001-BACKEND"]["reason_code"] == "policy_forced"
    assert selection["unresolved_items"] == []


def test_selection_skip_requires_approved_policy_rule() -> None:
    policy = base_policy()
    policy["skip_selection"] = [
        {
            "rule_id": "policy-skip-e2e",
            "selection": "skip",
            "case_ids": ["CASE-003-E2E"],
            "approved": False,
            "reason": "not yet approved",
        }
    ]
    by_id = {item["case_id"]: item for item in select(selection_policy=policy)["selected_cases"]}
    assert by_id["CASE-003-E2E"]["selection"] != "skip"

    policy["skip_selection"][0]["approved"] = True
    by_id = {item["case_id"]: item for item in select(selection_policy=policy)["selected_cases"]}
    assert by_id["CASE-003-E2E"]["selection"] == "skip"
    assert by_id["CASE-003-E2E"]["rule_id"] == "policy-skip-e2e"
    plan = compile_execution_plan(
        {"schema_version": "test-selection/1.0", "selected_cases": list(by_id.values())},
        cases(),
    )
    assert {item["action"] for item in plan["actions"]} == {"skip", "generate_new"}


def test_high_confidence_impact_resolves_without_advice() -> None:
    assets = {
        "automation_assets": {
            "CASE-001-BACKEND": {"status": "active", "impacted": True, "commit": "abc"},
        },
        "impact_evidence": {
            "CASE-001-BACKEND": {"confidence": "high", "evidence": ["call-graph:main"]}
        },
    }
    selection = select(assets=assets)
    by_id = {item["case_id"]: item for item in selection["selected_cases"]}
    assert by_id["CASE-001-BACKEND"]["reason_code"] == "automation_requires_update"
    assert by_id["CASE-001-BACKEND"]["rule_id"] == "impact-evidence-high-confidence"
    assert selection["unresolved_items"] == []


def test_low_confidence_impact_stays_must_run_and_goes_to_a12() -> None:
    assets = {
        "automation_assets": {
            "CASE-001-BACKEND": {"status": "active", "impacted": True, "commit": "abc"},
        },
    }
    selection = select(assets=assets)
    by_id = {item["case_id"]: item for item in selection["selected_cases"]}
    assert by_id["CASE-001-BACKEND"]["selection"] == "must_run"
    assert by_id["CASE-001-BACKEND"]["reason_code"] == "missing_call_graph"
    assert len(selection["unresolved_items"]) == 1
    assert selection["unresolved_items"][0]["advisory_topic"] == "missing_call_graph"


def test_cross_repo_conflict_is_unresolved_but_never_shrinks() -> None:
    assets = {
        "automation_assets": {
            "CASE-001-BACKEND": {"status": "active", "impacted": True, "commit": "abc"},
        },
        "impact_evidence": {
            "CASE-001-BACKEND": {"cross_repo_conflict": True, "evidence": ["repo:billing"]}
        },
    }
    selection = select(assets=assets)
    by_id = {item["case_id"]: item for item in selection["selected_cases"]}
    assert by_id["CASE-001-BACKEND"]["selection"] == "must_run"
    assert by_id["CASE-001-BACKEND"]["reason_code"] == "cross_repo_impact_conflict"
    assert selection["unresolved_items"][0]["advisory_topic"] == "cross_repo_impact_conflict"


def test_selection_backward_compatible_without_assets_or_policy() -> None:
    selection = select()
    by_id = {item["case_id"]: item for item in selection["selected_cases"]}
    assert all(item["selection"] == "must_run" for item in by_id.values())
    assert all(
        item["reason_code"] == "new_case_without_automation" for item in by_id.values()
    )
    assert selection["unresolved_items"] == []


# ------------------------------------------------------------- advice folding


def advice_item(
    unresolved: dict,
    *,
    recommendation: str = "keep_must_run",
    suggested: list[str] | None = None,
    **overrides,
) -> dict:
    item = {
        "id": "A12-001",
        "unresolved_item_id": unresolved["id"],
        "case_id": unresolved["case_id"],
        "advisory_topic": unresolved["advisory_topic"],
        "recommendation": recommendation,
        "suggested_case_ids": suggested or [],
        "evidence": list(unresolved["evidence"]),
        "uncertainty": unresolved["uncertainty"],
        "source_refs": [f"unresolved:{unresolved['id']}"],
    }
    item.update(overrides)
    return item


def unresolved_selection() -> dict:
    assets = {
        "automation_assets": {
            "CASE-001-BACKEND": {"status": "active", "impacted": True, "commit": "abc"},
        },
    }
    return select(assets=assets)


def test_expand_selection_upgrades_recommended_to_must_run() -> None:
    assets = {
        "automation_assets": {
            "CASE-001-BACKEND": {"status": "active", "impacted": True, "commit": "abc"},
            "CASE-002-CONTRACT": {"status": "active", "impacted": True, "commit": "def"},
        },
        "impact_evidence": {
            "CASE-002-CONTRACT": {"confidence": "medium", "evidence": ["call-graph:api"]}
        },
    }
    selection = select(assets=assets)
    by_id = {item["case_id"]: item for item in selection["selected_cases"]}
    assert by_id["CASE-002-CONTRACT"]["selection"] == "recommended"
    unresolved = selection["unresolved_items"][0]
    advice = {
        "schema_version": "test-selection-advice/1.0",
        "advice_items": [
            advice_item(
                unresolved,
                recommendation="expand_selection",
                suggested=["CASE-002-CONTRACT"],
            )
        ],
        "uncertainty_notes": ["upgrade recommended case to must_run"],
    }
    folded = apply_selection_advice(selection, advice, cases())
    by_id = {item["case_id"]: item for item in folded["selected_cases"]}
    assert by_id["CASE-002-CONTRACT"]["selection"] == "must_run"
    assert by_id["CASE-002-CONTRACT"]["reason_code"] == "a12_expanded_scope"
    assert by_id["CASE-002-CONTRACT"]["rule_id"] == "A12-ADVICE-VALIDATED"
    assert folded["unresolved_items"] == []
    assert folded["advice"]["applied_count"] == 1


def test_request_human_escalates_target_case() -> None:
    selection = unresolved_selection()
    unresolved = selection["unresolved_items"][0]
    advice = {
        "schema_version": "test-selection-advice/1.0",
        "advice_items": [advice_item(unresolved, recommendation="request_human")],
        "uncertainty_notes": ["needs human"],
    }
    folded = apply_selection_advice(selection, advice, cases())
    by_id = {item["case_id"]: item for item in folded["selected_cases"]}
    assert by_id["CASE-001-BACKEND"]["selection"] == "needs_human"
    assert by_id["CASE-001-BACKEND"]["reason_code"] == "a12_advice_request_human"


def test_keep_must_run_resolves_unresolved_item() -> None:
    selection = unresolved_selection()
    unresolved = selection["unresolved_items"][0]
    advice = {
        "schema_version": "test-selection-advice/1.0",
        "advice_items": [advice_item(unresolved, recommendation="keep_must_run")],
        "uncertainty_notes": ["keep conservative scope"],
    }
    folded = apply_selection_advice(selection, advice, cases())
    by_id = {item["case_id"]: item for item in folded["selected_cases"]}
    assert by_id["CASE-001-BACKEND"]["selection"] == "must_run"
    assert folded["unresolved_items"] == []


def test_unresolved_without_advice_is_never_silently_dropped() -> None:
    selection = unresolved_selection()
    unresolved = selection["unresolved_items"][0]
    advice = {
        "schema_version": "test-selection-advice/1.0",
        "advice_items": [
            advice_item(unresolved, recommendation="keep_must_run", id="A12-001")
        ],
        "uncertainty_notes": ["only one item advised"],
    }
    selection["unresolved_items"].append(
        {
            "id": "N26-U002",
            "case_id": "CASE-002-CONTRACT",
            "advisory_topic": "uncertain_asset_mapping",
            "reason_code": "uncertain_asset_mapping",
            "evidence": ["test-case:CASE-002-CONTRACT"],
            "uncertainty": "mapping unknown",
        }
    )
    folded = apply_selection_advice(selection, advice, cases())
    assert len(folded["unresolved_items"]) == 1
    assert folded["unresolved_items"][0]["id"] == "N26-U002"


def test_advice_referencing_unknown_unresolved_item_is_rejected() -> None:
    selection = unresolved_selection()
    advice = {
        "schema_version": "test-selection-advice/1.0",
        "advice_items": [
            {
                "id": "A12-001",
                "unresolved_item_id": "N26-U999",
                "case_id": "CASE-001-BACKEND",
                "advisory_topic": "missing_call_graph",
                "recommendation": "keep_must_run",
                "evidence": ["test-case:CASE-001-BACKEND"],
                "uncertainty": "n/a",
                "source_refs": ["unresolved:N26-U999"],
            }
        ],
        "uncertainty_notes": [],
    }
    with pytest.raises(ContractError, match="unknown unresolved item"):
        apply_selection_advice(selection, advice, cases())


def test_advice_suggesting_unknown_case_is_rejected() -> None:
    selection = unresolved_selection()
    unresolved = selection["unresolved_items"][0]
    advice = {
        "schema_version": "test-selection-advice/1.0",
        "advice_items": [
            advice_item(
                unresolved,
                recommendation="expand_selection",
                suggested=["CASE-NOT-EXISTS"],
            )
        ],
        "uncertainty_notes": [],
    }
    with pytest.raises(ContractError, match="suggests an unknown Case"):
        apply_selection_advice(selection, advice, cases())


def test_advice_cannot_downgrade_policy_forced_case_to_human() -> None:
    policy = base_policy()
    policy["forced_selection"].append(
        {"rule_id": "policy-backend-must-run", "selection": "must_run", "layers": ["backend"]}
    )
    selection = select(selection_policy=policy)
    selection["unresolved_items"].append(
        {
            "id": "N26-U001",
            "case_id": "CASE-001-BACKEND",
            "advisory_topic": "missing_call_graph",
            "reason_code": "missing_call_graph",
            "evidence": ["test-case:CASE-001-BACKEND"],
            "uncertainty": "unknown",
        }
    )
    advice = {
        "schema_version": "test-selection-advice/1.0",
        "advice_items": [
            advice_item(
                selection["unresolved_items"][0], recommendation="request_human"
            )
        ],
        "uncertainty_notes": [],
    }
    with pytest.raises(SecurityPolicyError, match="policy-forced Case"):
        apply_selection_advice(selection, advice, cases(), selection_policy=policy)


def test_advice_schema_version_is_enforced() -> None:
    selection = unresolved_selection()
    with pytest.raises(ContractError, match="schema_version"):
        apply_selection_advice(selection, {"schema_version": "wrong", "advice_items": []}, cases())


def test_no_unresolved_items_is_a_noop() -> None:
    selection = select()
    folded = apply_selection_advice(
        selection, {"schema_version": "test-selection-advice/1.0", "advice_items": []}, cases()
    )
    assert folded["unresolved_items"] == []
    assert folded["advice"]["applied_count"] == 0


# -------------------------------------------------------------- local A12 agent


def test_local_a12_expands_to_related_same_layer_cases() -> None:
    from qa_agents.agents.phase_one import TestSelectionAdvisorAgent
    from qa_agents.agents.base import AgentContext

    selection = unresolved_selection()
    agent = TestSelectionAdvisorAgent()
    output = agent.analyze(
        {
            "unresolved_items": selection["unresolved_items"],
            "compiled_case_index": {
                case["id"]: {
                    "layer": case["layer"],
                    "required_layers": case["required_layers"],
                    "evidence_modules": case["evidence_modules"],
                    "automation_candidate": case["automation_candidate"],
                }
                for case in cases()
            },
            "asset_evidence": {
                "impact_evidence": {},
                "impact_index": {"billing-core": ["CASE-001-BACKEND", "CASE-002-CONTRACT"]},
            },
        }
    )
    assert output.payload["schema_version"] == "test-selection-advice/1.0"
    assert output.payload["advice_items"][0]["recommendation"] == "expand_selection"
    assert "CASE-002-CONTRACT" in output.payload["advice_items"][0]["suggested_case_ids"]


def test_local_a12_requests_human_for_uncertain_asset_mapping() -> None:
    from qa_agents.agents.phase_one import TestSelectionAdvisorAgent

    agent = TestSelectionAdvisorAgent()
    output = agent.analyze(
        {
            "unresolved_items": [
                {
                    "id": "N26-U001",
                    "case_id": "CASE-001-BACKEND",
                    "advisory_topic": "uncertain_asset_mapping",
                    "reason_code": "uncertain_asset_mapping",
                    "evidence": ["test-case:CASE-001-BACKEND"],
                    "uncertainty": "mapping unknown",
                }
            ],
            "compiled_case_index": {},
            "asset_evidence": {},
        }
    )
    assert output.payload["advice_items"][0]["recommendation"] == "request_human"
    assert output.status == ArtifactStatus.COMPLETED


# ------------------------------------------------------------- Multica contract


def write_artifact(dir_path: Path, artifact: ArtifactEnvelope) -> Path:
    return ArtifactStore(dir_path).write_artifact(artifact)


def compiled_artifact(store_root: Path, child_list: list[dict] | None = None) -> dict:
    artifact = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(component_id="N25", runtime="deterministic"),
        payload={
            "schema_version": "compiled-test-cases/1.0",
            "parent_artifact_hash": "sha256:parent",
            "compiled_cases": child_list if child_list is not None else cases(),
        },
        status=ArtifactStatus.COMPLETED,
        created_at="2026-08-10T00:00:00+00:00",
    )
    write_artifact(store_root, artifact)
    return artifact.to_dict()


def selection_artifact(store_root: Path, compiled: dict, *, with_unresolved: bool = True) -> dict:
    selection = unresolved_selection() if with_unresolved else select()
    artifact = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="n26-test-selection",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(component_id="N26", runtime="deterministic"),
        payload={
            "schema_version": "test-selection/1.0",
            "compiled_artifact_id": compiled["artifact_id"],
            "compiled_artifact_hash": compiled["artifact_hash"],
            "selected_cases": selection["selected_cases"],
            "unresolved_items": selection["unresolved_items"],
        },
        status=(
            ArtifactStatus.NEEDS_HUMAN
            if selection["unresolved_items"]
            else ArtifactStatus.COMPLETED
        ),
        created_at="2026-08-10T00:00:00+00:00",
    )
    write_artifact(store_root, artifact)
    return artifact.to_dict()


def prepare_a12_bundle(tmp_path: Path) -> tuple[dict, dict, dict]:
    compiled = compiled_artifact(tmp_path / "stage13")
    selection = selection_artifact(tmp_path / "stage15", compiled)
    bundle = prepare_multica_selection_advice_input(
        tmp_path / "stage15" / "artifacts" / "n26-test-selection.json",
        tmp_path / "stage13" / "artifacts" / "n25-compiled-test-cases.json",
        tmp_path / "a12-input",
        selection_policy_path=ROOT / "policies" / "selection-policy.json",
    )
    return bundle, selection, compiled


def valid_a12_output(bundle: dict) -> dict:
    unresolved = bundle["allowed_inputs"]["unresolved_items"]
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "advice_items": [
            {
                "id": "A12-001",
                "unresolved_item_id": item["id"],
                "case_id": item["case_id"],
                "advisory_topic": item["advisory_topic"],
                "recommendation": "keep_must_run",
                "suggested_case_ids": [],
                "evidence": list(item["evidence"]),
                "uncertainty": item["uncertainty"],
                "source_refs": [f"unresolved:{item['id']}"],
            }
            for item in unresolved
        ],
        "uncertainty_notes": ["all kept conservative"],
        "evaluation_oracle_accessed": False,
    }


def test_prepare_a12_input_is_bound_and_isolated(tmp_path: Path) -> None:
    bundle, selection, compiled = prepare_a12_bundle(tmp_path)

    assert bundle["profile_id"] == "A12"
    assert bundle["profile_version"] == "1.0.0"
    assert bundle["output_contract"] == "test-selection-advice/1.0"
    upstream = {
        item["artifact_id"]: item["artifact_hash"] for item in bundle["upstream_artifacts"]
    }
    assert upstream["n26-test-selection"] == selection["artifact_hash"]
    assert upstream["n25-compiled-test-cases"] == compiled["artifact_hash"]
    assert all(value is False for value in bundle["integrity"].values())
    assert set(bundle["allowed_inputs"]) == {
        "unresolved_items",
        "compiled_case_index",
        "change_set",
        "asset_evidence",
        "selection_policy",
    }
    assert (tmp_path / "a12-input" / "a12-input.json").exists()
    assert bundle["allowed_inputs"]["selection_policy"]["schema_version"] == (
        "test-selection-policy/1.0"
    )


def test_prepare_a12_rejects_deterministic_selection_without_unresolved(
    tmp_path: Path,
) -> None:
    compiled = compiled_artifact(tmp_path / "stage13")
    selection = selection_artifact(tmp_path / "stage15", compiled, with_unresolved=False)
    with pytest.raises(ContractError, match="requires N26 unresolved"):
        prepare_multica_selection_advice_input(
            tmp_path / "stage15" / "artifacts" / "n26-test-selection.json",
            tmp_path / "stage13" / "artifacts" / "n25-compiled-test-cases.json",
            tmp_path / "a12-input",
        )


def test_prepare_a12_rejects_cross_run_binding(tmp_path: Path) -> None:
    compiled = compiled_artifact(tmp_path / "stage13")
    selection = selection_artifact(tmp_path / "stage15", compiled)
    selection["workflow_run_id"] = "another-run"
    tampered = ArtifactEnvelope(
        workflow_run_id="another-run",
        workflow_mode=WORKFLOW_MODE,
        artifact_id="n26-test-selection",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(component_id="N26", runtime="deterministic"),
        payload=selection["payload"],
        status=ArtifactStatus.NEEDS_HUMAN,
    )
    write_artifact(tmp_path / "stage15-tampered", tampered)
    with pytest.raises(ContractError, match="different runs"):
        prepare_multica_selection_advice_input(
            tmp_path / "stage15-tampered" / "artifacts" / "n26-test-selection.json",
            tmp_path / "stage13" / "artifacts" / "n25-compiled-test-cases.json",
            tmp_path / "a12-input",
        )


def test_ingest_a12_accepts_valid_advice(tmp_path: Path) -> None:
    bundle, _, _ = prepare_a12_bundle(tmp_path)
    output = valid_a12_output(bundle)

    artifact = ingest_multica_output(
        tmp_path / "a12-input" / "a12-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage15b",
        task_id="task-a12",
        issue_id="issue-a12",
        attachment_id="attachment-a12",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    assert artifact["artifact_id"] == "a12-test-selection-advice"
    assert artifact["producer"]["profile_version"] == "1.0.0"
    assert artifact["payload"]["advice_items"][0]["recommendation"] == "keep_must_run"


def test_ingest_a12_rejects_unknown_suggested_case(tmp_path: Path) -> None:
    bundle, _, _ = prepare_a12_bundle(tmp_path)
    output = valid_a12_output(bundle)
    output["advice_items"][0]["suggested_case_ids"] = ["CASE-NOT-EXISTS"]

    with pytest.raises(ContractError, match="suggests an unknown Case"):
        ingest_multica_output(
            tmp_path / "a12-input" / "a12-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "rejected",
            task_id="task-a12",
            issue_id="issue-a12",
            attachment_id="attachment-a12",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_ingest_a12_rejects_unknown_unresolved_reference(tmp_path: Path) -> None:
    bundle, _, _ = prepare_a12_bundle(tmp_path)
    output = valid_a12_output(bundle)
    output["advice_items"][0]["unresolved_item_id"] = "N26-U999"

    with pytest.raises(ContractError, match="unknown unresolved item"):
        ingest_multica_output(
            tmp_path / "a12-input" / "a12-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "rejected",
            task_id="task-a12",
            issue_id="issue-a12",
            attachment_id="attachment-a12",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_ingest_a12_rejects_evaluation_oracle_access(tmp_path: Path) -> None:
    bundle, _, _ = prepare_a12_bundle(tmp_path)
    output = valid_a12_output(bundle)
    output["evaluation_oracle_registry"] = {"answer": "hidden"}

    with pytest.raises(SecurityPolicyError, match="Evaluation Oracle field"):
        ingest_multica_output(
            tmp_path / "a12-input" / "a12-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "rejected",
            task_id="task-a12",
            issue_id="issue-a12",
            attachment_id="attachment-a12",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


# ------------------------------------------------------- stage-two integration


def test_run_n26_folds_validated_a12_advice(tmp_path: Path) -> None:
    from qa_agents.stage_two_nodes import run_n26_after_a11

    compiled = compiled_artifact(tmp_path / "stage13")
    selection = selection_artifact(tmp_path / "stage15", compiled)
    review_bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "workflow_mode": WORKFLOW_MODE,
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "profile_id": "A11",
        "profile_version": "1.0.0",
        "output_contract": "split-review/1.0",
        "allowed_inputs": {"parent_test_cases": [], "compiled_child_cases": cases()},
        "upstream_artifacts": [
            {"artifact_id": compiled["artifact_id"], "artifact_hash": compiled["artifact_hash"]}
        ],
        "integrity": {
            "evaluation_oracle_registry_included": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    review_bundle["bundle_hash"] = content_hash(review_bundle)
    write_artifact(
        tmp_path / "a11",
        ArtifactEnvelope(
            workflow_run_id=WORKFLOW_RUN_ID,
            workflow_mode=WORKFLOW_MODE,
            artifact_id="a11-split-coverage-review",
            source_snapshot_id=SOURCE_SNAPSHOT_ID,
            producer=Producer(component_id="A11", runtime="multica"),
            payload={
                "schema_version": "split-review/1.0",
                "approved": True,
                "issues": [],
                "input_bundle_hash": review_bundle["bundle_hash"],
            },
            status=ArtifactStatus.COMPLETED,
        ),
    )
    advice = {
        "schema_version": "test-selection-advice/1.0",
        "advice_items": [
            {
                "id": "A12-001",
                "unresolved_item_id": selection["payload"]["unresolved_items"][0]["id"],
                "case_id": "CASE-001-BACKEND",
                "advisory_topic": "missing_call_graph",
                "recommendation": "expand_selection",
                "suggested_case_ids": ["CASE-002-CONTRACT"],
                "evidence": ["test-case:CASE-001-BACKEND"],
                "uncertainty": "impact unknown",
                "source_refs": ["unresolved:N26-U001"],
            }
        ],
        "uncertainty_notes": [],
    }
    advice_artifact = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="a12-test-selection-advice",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(component_id="A12", runtime="multica"),
        payload=advice,
        status=ArtifactStatus.COMPLETED,
    )
    write_artifact(tmp_path / "a12", advice_artifact)

    asset_catalog = {
        "automation_assets": {
            "CASE-001-BACKEND": {"status": "active", "impacted": True, "commit": "abc"},
            "CASE-002-CONTRACT": {"status": "active", "impacted": True, "commit": "def"},
        },
        "impact_evidence": {
            "CASE-002-CONTRACT": {"confidence": "medium", "evidence": ["call-graph:api"]}
        },
    }
    write_json(tmp_path / "catalog.json", asset_catalog)
    artifact = run_n26_after_a11(
        tmp_path / "stage13" / "artifacts" / "n25-compiled-test-cases.json",
        tmp_path / "a11" / "artifacts" / "a11-split-coverage-review.json",
        write_json(tmp_path / "a11" / "a11-input.json", review_bundle),
        tmp_path / "stage15-final",
        asset_catalog_path=tmp_path / "catalog.json",
        selection_advice_path=tmp_path / "a12" / "artifacts" / "a12-test-selection-advice.json",
        selection_policy_path=ROOT / "policies" / "selection-policy.json",
    )
    assert artifact["status"] == "completed"
    by_id = {item["case_id"]: item for item in artifact["payload"]["selected_cases"]}
    assert by_id["CASE-002-CONTRACT"]["reason_code"] == "a12_expanded_scope"
    assert artifact["payload"]["unresolved_items"] == []


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
