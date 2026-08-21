"""Deterministic adapters between frozen QA artifacts and Multica tasks."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any, Mapping, Sequence

from .change_set import normalize_change_set
from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from .errors import ContractError, RetryableAgentError, SecurityPolicyError
from .gates import validate_recorded_scope_review_decision
from .human_correction import validate_human_correction_decision
from .historical_behavior import (
    assert_historical_regression_coverage,
    validate_historical_behavior_packet,
)
from .security import SecurityPolicy
from .storage import ArtifactStore


HUMAN_FACING_ISSUE_FIELDS = frozenset({"plain_summary", "human_title"})


PROFILE_INPUTS = {
    "A02": {
        "output_contract": "requirement-analysis/1.0",
        "material_fields": {"frozen_requirement": "requirement"},
    },
    "A03": {
        "output_contract": "technical-analysis/1.0",
        "material_fields": {"frozen_technical_design": "technical_design"},
        "static_inputs": {"test_tool_capabilities": []},
    },
    "A05": {
        "output_contract": "change-analysis/1.0",
        "material_fields": {"backend_change_set": "implementation_diff"},
        "static_inputs": {"read_only_source_snapshot": True},
        "profile_version": "1.1.0",
    },
}

PROFILE_OUTPUTS = {
    "A02": {
        "artifact_id": "a02-requirement-analysis",
        "required_fields": {"requirements", "ambiguities", "needs_human"},
        "evidence_collections": {"requirements", "ambiguities", "needs_human"},
        "collection_item_fields": {
            "requirements": {"id", "summary", "acceptance_criteria", "source_refs"},
        },
    },
    "A03": {
        "artifact_id": "a03-technical-testability-analysis",
        "required_fields": {
            "technical_facts",
            "testability",
            "testability_gaps",
            "blocking_items",
        },
        "evidence_collections": {"technical_facts", "blocking_items"},
        "collection_item_fields": {
            "technical_facts": {"id", "summary", "source_refs"},
            "testability": {"capability", "status"},
            "testability_gaps": {"capability", "status"},
            "blocking_items": {
                "id",
                "issue_code",
                "summary",
                "recommendation",
                "owner",
                "start_condition",
                "source_refs",
            },
        },
    },
    "A05": {
        "artifact_id": "a05-backend-change-analysis",
        "required_fields": {"domain", "change_set_id", "facts"},
        "evidence_collections": {"facts"},
        "collection_item_fields": {
            "facts": {
                "id",
                "path",
                "change_set_id",
                "summary",
                "evidence_class",
                "eligible_for_business_alignment",
                "source_refs",
            },
        },
    },
    "A06": {
        "artifact_id": "a06-alignment-result",
        "required_fields": {"mappings", "findings"},
        "evidence_collections": {"mappings", "findings"},
        "collection_item_fields": {
            "mappings": {
                "requirement_id",
                "technical_fact_ids",
                "change_fact_ids",
                "status",
                "source_refs",
            },
            "findings": {
                "id",
                "type",
                "severity",
                "summary",
                "requirement_ids",
                "technical_fact_ids",
                "implementation_ids",
                "source_refs",
            },
        },
    },
    "A08": {
        "artifact_id": "a08-test-design-ir",
        "required_fields": {
            "test_intents",
            "parent_cases",
            "coverage_matrix",
            "test_rule_coverage",
        },
        "evidence_collections": {"test_intents", "parent_cases"},
        "collection_item_fields": {
            "test_intents": {
                "id",
                "objective",
                "risk",
                "required_layers",
                "source_refs",
            },
            "parent_cases": {
                "id",
                "title",
                "intent_ids",
                "layer",
                "required_layers",
                "risk",
                "priority",
                "source_refs",
                "preconditions",
                "test_data",
                "steps",
                "expected",
                "cleanup",
                "execution_policy",
                "automation_candidate",
            },
            "coverage_matrix": {"requirement_id", "case_ids"},
            "test_rule_coverage": {"rule_id", "case_ids"},
        },
    },
    "A09": {
        "artifact_id": "a09-oracle-coverage-review",
        "required_fields": {
            "approved",
            "issues",
            "coverage_dimensions",
            "requirement_coverage",
            "test_rule_coverage",
            "manual_case_recommendations",
            "code_coverage_reviewed",
            "evaluation_oracle_accessed",
        },
        "evidence_collections": {"issues", "coverage_dimensions"},
        "collection_item_fields": {
            "issues": {
                "id",
                "issue_code",
                "severity",
                "category",
                "message",
                "path",
                "route_to",
                "case_id",
                "expected_id",
                "source_refs",
                "recommendation",
                "plain_summary",
                "human_title",
            },
            "coverage_dimensions": {
                "dimension",
                "status",
                "case_ids",
                "source_refs",
                "rationale",
            },
            "requirement_coverage": {"requirement_id", "status", "case_ids"},
            "test_rule_coverage": {"rule_id", "status", "case_ids"},
        },
    },
    "A11": {
        "artifact_id": "a11-split-coverage-review",
        "required_fields": {
            "approved",
            "issues",
            "parent_case_coverage",
            "layer_coverage",
            "evaluation_oracle_accessed",
        },
        "evidence_collections": {"issues", "parent_case_coverage", "layer_coverage"},
        "collection_item_fields": {
            "issues": {
                "id",
                "issue_code",
                "severity",
                "category",
                "message",
                "path",
                "route_to",
                "case_id",
                "source_refs",
                "recommendation",
                "plain_summary",
                "human_title",
            },
            "parent_case_coverage": {
                "parent_case_id",
                "status",
                "covered_child_ids",
                "source_refs",
                "rationale",
            },
            "layer_coverage": {
                "layer",
                "status",
                "case_ids",
                "source_refs",
                "rationale",
            },
        },
    },
    "A12": {
        "artifact_id": "a12-test-selection-advice",
        "required_fields": {"advice_items", "uncertainty_notes"},
        "evidence_collections": {"advice_items"},
        "collection_item_fields": {
            "advice_items": {
                "id",
                "case_id",
                "advisory_topic",
                "recommendation",
                "evidence",
                "uncertainty",
                "source_refs",
            },
        },
    },
    "A14": {
        "artifact_id": "a14-backend-automation-generation",
        "required_fields": {
            "schema_version",
            "manifest",
            "code_candidates",
            "rejected_cases",
        },
        "evidence_collections": {"rejected_cases"},
        "collection_item_fields": {
            "rejected_cases": {"case_id", "reason_code", "source_refs"},
        },
    },
    "A15": {
        "artifact_id": "a15-contract-automation-generation",
        "required_fields": {
            "schema_version",
            "manifest",
            "code_candidates",
            "rejected_cases",
        },
        "evidence_collections": {"rejected_cases"},
        "collection_item_fields": {
            "rejected_cases": {"case_id", "reason_code", "source_refs"},
        },
    },
    "A18-BE": {
        "artifact_id": "a18-be-backend-automation-review",
        "required_fields": {
            "schema_version",
            "review_profile",
            "approved",
            "issues",
            "generation_hash",
            "manifest_hash",
            "candidate_hashes",
            "generator_hidden_reasoning_accessed",
            "evaluation_oracle_accessed",
        },
        "evidence_collections": {"issues"},
        "collection_item_fields": {
            "issues": {
                "id",
                "issue_code",
                "severity",
                "category",
                "message",
                "path",
                "route_to",
                "case_id",
                "expected_id",
                "source_refs",
                "recommendation",
                "plain_summary",
                "human_title",
            },
        },
    },
    "A18-CT": {
        "artifact_id": "a18-ct-contract-automation-review",
        "required_fields": {
            "schema_version",
            "review_profile",
            "approved",
            "issues",
            "generation_hash",
            "manifest_hash",
            "candidate_hashes",
            "generator_hidden_reasoning_accessed",
            "evaluation_oracle_accessed",
        },
        "evidence_collections": {"issues"},
        "collection_item_fields": {
            "issues": {
                "id",
                "issue_code",
                "severity",
                "category",
                "message",
                "path",
                "route_to",
                "case_id",
                "expected_id",
                "source_refs",
                "recommendation",
                "plain_summary",
                "human_title",
            },
        },
    },
    "A22": {
        "artifact_id": "a22-test-data-plan",
        "required_fields": {
            "schema_version",
            "environment",
            "namespace",
            "case_plans",
            "paused_cases",
            "unresolved_requirements",
        },
        "evidence_collections": {"case_plans"},
        "collection_item_fields": {
            "case_plans": {
                "case_id",
                "requires_data_construction",
                "resources",
                "source_refs",
            },
        },
    },
}


ALIGNMENT_UPSTREAM_ARTIFACTS = {
    "requirement_analysis": "a02-requirement-analysis.json",
    "technical_analysis": "a03-technical-testability-analysis.json",
    "backend_change_analysis": "a05-backend-change-analysis.json",
}


TEST_RULE_IDS = {
    "RULE-MULTIPLE-REASONS",
    "RULE-SINGLE-METRIC",
    "RULE-ENTRY-CONSISTENCY",
    "RULE-CUSTOM-DIMENSION",
    "RULE-DYNAMIC-RELATION",
    "RULE-MULTI-RELATION",
    "RULE-PERMISSION-PRIORITY",
    "RULE-HISTORICAL-COMPATIBILITY",
    "RULE-I18N-CUSTOM-DIMENSION",
    "RULE-I18N-RESULT-SET",
    "RULE-I18N-MULTI-RELATION",
    "RULE-I18N-DYNAMIC-RELATION",
}


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def prepare_multica_inputs(
    input_dir: Path,
    output_dir: Path,
    *,
    workflow_run_id: str,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Create least-privilege profile bundles without exposing evaluation Oracle data."""

    if "oracle" in {part.casefold() for part in input_dir.parts}:
        raise SecurityPolicyError("Multica input source cannot be an Oracle directory")
    security = security or SecurityPolicy()
    workflow_input = _read(input_dir / "workflow-input.json")
    source_snapshot = _read(input_dir / "source-snapshot.json")
    source_material = _read(input_dir / "source-material.json")
    security.validate_workflow_input(workflow_input)
    security.validate_snapshot(source_snapshot)
    security.assert_no_secret_values(source_material)

    snapshot_id = str(source_snapshot["snapshot_id"])
    store = ArtifactStore(output_dir)
    manifest_entries = []
    for profile_id, config in PROFILE_INPUTS.items():
        allowed_inputs: dict[str, Any] = {}
        for input_name, material_name in config["material_fields"].items():
            material = source_material.get(material_name)
            if not isinstance(material, Mapping):
                raise ValueError(f"Missing source material field: {material_name}")
            allowed_inputs[input_name] = dict(material)
        if profile_id == "A05":
            allowed_inputs["backend_change_set"] = {
                "change_set": normalize_change_set(source_snapshot),
                "implementation_diff": allowed_inputs["backend_change_set"],
            }
        allowed_inputs.update(config.get("static_inputs", {}))
        bundle = {
            "schema_version": "multica-agent-input/1.0",
            "workflow_run_id": workflow_run_id,
            "workflow_mode": workflow_input["workflow_mode"],
            "source_snapshot_id": snapshot_id,
            "profile_id": profile_id,
            "profile_version": config.get("profile_version", "1.0.0"),
            "output_contract": config["output_contract"],
            "allowed_inputs": allowed_inputs,
            "integrity": {
                "oracle_included_in_agent_input": False,
                "credentials_embedded": False,
                "business_repository_write_allowed": False,
                "external_side_effects_allowed": False,
            },
        }
        security.assert_no_secret_values(bundle)
        bundle["bundle_hash"] = content_hash(bundle)
        filename = f"{profile_id.lower()}-input.json"
        store.write_json(filename, bundle)
        manifest_entries.append(
            {
                "profile_id": profile_id,
                "file": filename,
                "bundle_hash": bundle["bundle_hash"],
                "output_contract": config["output_contract"],
            }
        )

    manifest = {
        "schema_version": "multica-input-manifest/1.0",
        "workflow_run_id": workflow_run_id,
        "source_snapshot_id": snapshot_id,
        "bundles": manifest_entries,
    }
    store.write_json("manifest.json", manifest)
    return manifest


def prepare_multica_alignment_input(
    artifact_dir: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile provenance-checked Stage 1 artifacts into A06's only input bundle."""

    security = security or SecurityPolicy()
    upstream: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, str, str]] = set()
    upstream_refs: list[dict[str, str]] = []
    for input_name, filename in ALIGNMENT_UPSTREAM_ARTIFACTS.items():
        artifact = _read(artifact_dir / filename)
        security.assert_no_secret_values(artifact)
        if artifact.get("artifact_id") != filename.removesuffix(".json"):
            raise ContractError(f"Unexpected artifact identity in {filename}")
        expected_hash = artifact_hash_from_mapping(artifact)
        if artifact.get("artifact_hash") != expected_hash:
            raise ContractError(f"Artifact hash mismatch: {filename}")
        if artifact.get("status") not in {
            ArtifactStatus.COMPLETED.value,
            ArtifactStatus.COMPLETED_WITH_GAPS.value,
            ArtifactStatus.NEEDS_HUMAN.value,
        }:
            raise ContractError(f"Upstream artifact is not consumable: {filename}")
        identity = (
            str(artifact.get("workflow_run_id", "")),
            str(artifact.get("workflow_mode", "")),
            str(artifact.get("source_snapshot_id", "")),
        )
        if not all(identity):
            raise ContractError(f"Upstream artifact identity is incomplete: {filename}")
        identities.add(identity)
        payload = artifact.get("payload")
        if not isinstance(payload, Mapping):
            raise ContractError(f"Upstream artifact payload is invalid: {filename}")
        upstream[input_name] = dict(payload)
        upstream_refs.append(
            {
                "artifact_id": str(artifact["artifact_id"]),
                "artifact_hash": str(artifact["artifact_hash"]),
            }
        )
    if len(identities) != 1:
        raise ContractError("A06 upstream artifacts belong to different workflow runs")

    workflow_run_id, workflow_mode, snapshot_id = identities.pop()
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": "A06",
        "profile_version": "1.0.0",
        "output_contract": "alignment-result/1.0",
        "allowed_inputs": upstream,
        "upstream_artifacts": upstream_refs,
        "integrity": {
            "oracle_included_in_agent_input": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    security.assert_no_secret_values(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json("a06-input.json", bundle)
    return bundle


def _verified_artifact(
    path: Path,
    expected_id: str,
    security: SecurityPolicy,
    *,
    allowed_statuses: set[str] | None = None,
) -> dict[str, Any]:
    artifact = _read(path)
    security.assert_no_secret_values(artifact)
    if artifact.get("artifact_id") != expected_id:
        raise ContractError(f"Expected Artifact {expected_id}: {path}")
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError(f"Artifact hash mismatch: {expected_id}")
    if allowed_statuses is None:
        allowed_statuses = {
            ArtifactStatus.COMPLETED.value,
            ArtifactStatus.COMPLETED_WITH_GAPS.value,
            ArtifactStatus.NEEDS_HUMAN.value,
        }
    if artifact.get("status") not in allowed_statuses:
        raise ContractError(f"Upstream Artifact is not consumable: {expected_id}")
    if not isinstance(artifact.get("payload"), Mapping):
        raise ContractError(f"Artifact payload is invalid: {expected_id}")
    return artifact


def _test_rule_obligations(test_rules: Mapping[str, Any]) -> list[dict[str, Any]]:
    localization = test_rules.get("localization", {})
    errors = localization.get("errors", []) if isinstance(localization, Mapping) else []
    error_by_key = {
        str(item.get("key")): item for item in errors if isinstance(item, Mapping)
    }
    localization_rules = [
        (
            "RULE-I18N-CUSTOM-DIMENSION",
            "CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED",
        ),
        ("RULE-I18N-RESULT-SET", "RESULT_SET_FILTER_DETAIL_UNSUPPORTED"),
        ("RULE-I18N-MULTI-RELATION", "MULTI_RELATION_METRIC_DETAIL_UNSUPPORTED"),
        (
            "RULE-I18N-DYNAMIC-RELATION",
            "DYNAMIC_RELATION_METRIC_DETAIL_UNSUPPORTED",
        ),
    ]
    obligations = [
        {
            "id": "RULE-MULTIPLE-REASONS",
            "definition": test_rules.get("multiple_reasons"),
        },
        {"id": "RULE-SINGLE-METRIC", "definition": test_rules.get("metric_name")},
        {
            "id": "RULE-ENTRY-CONSISTENCY",
            "definition": test_rules.get("entry_consistency"),
        },
        {
            "id": "RULE-CUSTOM-DIMENSION",
            "definition": test_rules.get("custom_dimension"),
        },
        {
            "id": "RULE-DYNAMIC-RELATION",
            "definition": test_rules.get("dynamic_relation"),
        },
        {
            "id": "RULE-MULTI-RELATION",
            "definition": test_rules.get("multi_relation"),
        },
        {
            "id": "RULE-PERMISSION-PRIORITY",
            "definition": test_rules.get("permission"),
        },
        {
            "id": "RULE-HISTORICAL-COMPATIBILITY",
            "definition": test_rules.get("compatibility"),
        },
    ]
    obligations.extend(
        {
            "id": rule_id,
            "definition": error_by_key.get(error_key),
        }
        for rule_id, error_key in localization_rules
    )
    missing = [item["id"] for item in obligations if not item["definition"]]
    if missing:
        raise ContractError(
            f"G01 test_rules are incomplete for A08: {', '.join(sorted(missing))}"
        )
    return obligations


def _default_prior_test_rules_paths(output_dir: Path) -> list[Path]:
    """Locate archived G01 decisions that may carry structured test_rules."""

    root = output_dir.parent
    paths = [
        *root.glob("g01*/g01-review-decision.json"),
        *root.glob("g01*/history/*/g01-review-decision.json"),
    ]
    if root.parent != root:
        paths.extend(root.parent.glob("*/g01*/g01-review-decision.json"))
        paths.extend(root.parent.glob("*/g01*/history/*/g01-review-decision.json"))
    return sorted({Path(path) for path in paths}, key=str)


def _resolve_structured_test_rules(
    decision: Mapping[str, Any],
    prior_test_rules_paths: Sequence[Path],
) -> tuple[Mapping[str, Any] | None, dict[str, Any] | None]:
    """Resolve structured test_rules for A08 when G01 recorded concise rules.

    The concise decision stores ``test_rules`` as a plain string (e.g. "按逐项
    回复冻结的口径执行测试设计"). The per-item resolutions freeze the scope but do
    not carry the structured rule table. When available, reuse the structured
    rules from the most recent approved G01 decision bound to the same source
    snapshot so the A08 Agent still receives an explicit rule set. The fallback
    is recorded as provenance inside the bundle; it never rewrites the archived
    decision itself.
    """

    test_rules = decision.get("test_rules")
    if isinstance(test_rules, Mapping):
        return dict(test_rules), None
    snapshot_id = str(decision.get("source_snapshot_id", ""))
    candidates: list[tuple[str, Mapping[str, Any], str, str]] = []
    for path in prior_test_rules_paths:
        try:
            value = _read(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, Mapping):
            continue
        if str(value.get("decision", "")) != "approved":
            continue
        if str(value.get("source_snapshot_id", "")) != snapshot_id:
            continue
        rules = value.get("test_rules")
        if not isinstance(rules, Mapping):
            continue
        candidates.append(
            (
                str(value.get("decided_at", "")),
                dict(rules),
                str(value.get("decision_hash", "")),
                str(value.get("workflow_run_id", "")),
            )
        )
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, rules, decision_hash, run_id = candidates[0]
    return rules, {
        "mode": "prior_frozen_scope",
        "workflow_run_id": run_id,
        "decision_hash": decision_hash,
    }


def prepare_multica_test_design_input(
    requirement_artifact_path: Path,
    technical_artifact_path: Path,
    alignment_artifact_path: Path,
    n24_artifact_path: Path,
    g01_request_path: Path,
    g01_decision_path: Path,
    g01_policy_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
    prior_test_rules_paths: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """Compile G01-approved evidence and N24 strategy into A08's only input."""

    security = security or SecurityPolicy()
    artifacts = {
        "requirement_analysis": _verified_artifact(
            requirement_artifact_path, "a02-requirement-analysis", security
        ),
        "technical_analysis": _verified_artifact(
            technical_artifact_path, "a03-technical-testability-analysis", security
        ),
        "alignment": _verified_artifact(
            alignment_artifact_path, "a06-alignment-result", security
        ),
        "test_strategy": _verified_artifact(
            n24_artifact_path, "n24-test-strategy", security
        ),
    }
    identities = {
        (
            str(item.get("workflow_run_id", "")),
            str(item.get("workflow_mode", "")),
            str(item.get("source_snapshot_id", "")),
        )
        for item in artifacts.values()
    }
    if len(identities) != 1 or not all(next(iter(identities))):
        raise ContractError("A08 upstream Artifacts belong to different workflow runs")
    workflow_run_id, workflow_mode, snapshot_id = identities.pop()

    request = _read(g01_request_path)
    recorded_decision = _read(g01_decision_path)
    policy = _read(g01_policy_path)
    decision = validate_recorded_scope_review_decision(request, recorded_decision, policy)
    if decision.get("decision") != "approved":
        raise ContractError("A08 is blocked until G01 is approved")
    if request.get("workflow_run_id") != workflow_run_id or request.get(
        "source_snapshot_id"
    ) != snapshot_id:
        raise ContractError("A08 G01 approval belongs to another workflow run")
    request_artifacts = {
        str(item.get("artifact_id")): str(item.get("artifact_hash"))
        for item in request.get("upstream_artifacts", [])
        if isinstance(item, Mapping)
    }
    for input_name in ("requirement_analysis", "technical_analysis", "alignment"):
        artifact = artifacts[input_name]
        if request_artifacts.get(str(artifact["artifact_id"])) != artifact["artifact_hash"]:
            raise ContractError(f"A08 G01 request does not bind {artifact['artifact_id']}")

    alignment_hash = str(artifacts["alignment"]["artifact_hash"])
    decision_hash = str(decision["decision_hash"])
    strategy_refs = {
        (str(item.get("source_type")), str(item.get("source_id"))): str(
            item.get("content_hash")
        )
        for item in artifacts["test_strategy"].get("evidence_refs", [])
        if isinstance(item, Mapping)
    }
    if strategy_refs.get(("artifact", "a06-alignment-result")) != alignment_hash:
        raise ContractError("A08 N24 strategy does not bind the current A06 Artifact")
    if strategy_refs.get(("human_gate_decision", "G01")) != decision_hash:
        raise ContractError("A08 N24 strategy does not bind the current G01 decision")

    test_rules = decision.get("test_rules")
    test_rule_instruction = None
    test_rule_fallback = None
    if not isinstance(test_rules, Mapping):
        test_rule_instruction = str(test_rules).strip() if test_rules else None
        prior_paths = list(
            prior_test_rules_paths or _default_prior_test_rules_paths(output_dir)
        )
        test_rules, test_rule_fallback = _resolve_structured_test_rules(
            decision, prior_paths
        )
        if not isinstance(test_rules, Mapping):
            raise ContractError(
                "A08 requires structured G01 test_rules; the recorded decision is "
                "concise and no structured rules are available for this snapshot"
            )
    obligations = _test_rule_obligations(test_rules)
    allowed_inputs = {
        "validated_analysis": {
            input_name: artifact["payload"]
            for input_name, artifact in artifacts.items()
            if input_name != "test_strategy"
        },
        "approved_scope": {
            "gate_id": "G01",
            "decision": "approved",
            "status": "approved",
            "request_hash": request["request_hash"],
            "decision_hash": decision_hash,
            "review_policy": request["review_policy"],
            "test_rules": dict(test_rules),
            "test_rule_obligations": obligations,
            **(
                {"test_rule_instruction": test_rule_instruction}
                if test_rule_instruction
                else {}
            ),
            **(
                {"test_rule_fallback": test_rule_fallback}
                if test_rule_fallback
                else {}
            ),
        },
        "test_strategy": artifacts["test_strategy"]["payload"],
        "case_provider_draft": {
            "provider_status": "incompatible",
            "candidate_count": 0,
            "candidates": [],
            "reason": "Frozen fs-qa-knowledge provider has no artifact-only capability",
        },
    }
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": "A08",
        "profile_version": "1.1.0",
        "output_contract": "test-design-ir/1.1",
        "allowed_inputs": allowed_inputs,
        "upstream_artifacts": [
            {
                "artifact_id": artifact["artifact_id"],
                "artifact_hash": artifact["artifact_hash"],
            }
            for artifact in artifacts.values()
        ],
        "upstream_gate": {
            "gate_id": "G01",
            "request_hash": request["request_hash"],
            "decision_hash": decision_hash,
            "policy_hash": request["review_policy"]["policy_hash"],
        },
        "integrity": {
            "evaluation_oracle_included_in_agent_input": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    security.assert_no_secret_values(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json("a08-input.json", bundle)
    return bundle


def _group_n04_correction_issues(issues: list[Any]) -> list[dict[str, Any]]:
    """Collapse repeated field-level N04 findings without losing affected locations."""

    groups: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for issue in issues:
        if not isinstance(issue, Mapping) or issue.get("origin") != "N04":
            continue
        key = (
            str(issue.get("issue_code", "")),
            str(issue.get("severity", "error")),
            str(issue.get("category", "")),
            str(issue.get("message", "")),
            str(issue.get("recommendation", "")),
        )
        group = groups.setdefault(
            key,
            {
                "issue_code": key[0],
                "severity": key[1],
                "category": key[2],
                "message": key[3],
                "route_to": "A08",
                "recommendation": key[4],
                "affected_locations": [],
                "source_refs": [],
            },
        )
        group["affected_locations"].append(
            {
                "case_id": issue.get("case_id"),
                "expected_id": issue.get("expected_id"),
                "path": issue.get("path"),
            }
        )
        for source_ref in issue.get("source_refs", []):
            if source_ref not in group["source_refs"]:
                group["source_refs"].append(source_ref)
    result = [groups[key] for key in sorted(groups)]
    for index, group in enumerate(result, 1):
        group["group_id"] = f"N04-G{index:03d}"
    return result


def _validate_g02_review_direction(
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    n04: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a request_changes G02 decision as an A08 fix direction."""

    if request.get("schema_version") != "test-case-ir-review-request/1.0":
        raise ContractError("A08 G02 direction request schema is invalid")
    if request.get("gate_id") != "G02":
        raise ContractError("A08 G02 direction request gate is invalid")
    if decision.get("schema_version") != "test-case-ir-review-decision/1.0":
        raise ContractError("A08 G02 direction decision schema is invalid")
    if decision.get("gate_id") != "G02":
        raise ContractError("A08 G02 direction decision gate is invalid")
    for value, label, field in (
        (request, "G02 review request", "request_hash"),
        (decision, "G02 review decision", "decision_hash"),
    ):
        unhashed = {key: item for key, item in value.items() if key != field}
        if value.get(field) != content_hash(unhashed):
            raise ContractError(f"{label} hash is invalid")
    if decision.get("decision") != "request_changes":
        raise ContractError("A08 G02 direction requires a request_changes decision")
    if decision.get("request_hash") != request.get("request_hash"):
        raise ContractError("A08 G02 direction decision does not bind the request")
    if decision.get("review_key") != request.get("review_key"):
        raise ContractError("A08 G02 direction review_key is stale")
    actor = decision.get("actor")
    if not isinstance(actor, Mapping) or actor.get("type") != "human":
        raise SecurityPolicyError("A08 G02 direction was not decided by a human")
    upstream = {
        str(item.get("artifact_id")): str(item.get("artifact_hash"))
        for item in request.get("upstream_artifacts", [])
        if isinstance(item, Mapping)
    }
    if upstream.get("n04-test-case-ir-validation") != n04.get("artifact_hash"):
        raise ContractError("A08 G02 direction N04 binding is stale")
    return {
        "schema_version": "test-design-g02-direction/1.0",
        "request_hash": request["request_hash"],
        "decision_hash": decision["decision_hash"],
        "decision": decision["decision"],
        "actor": dict(actor),
        "reason": str(decision.get("reason", "")),
        "reviewer_comment": dict(decision.get("reviewer_comment") or {}),
        "automatic_budget_reset": False,
        "required_revalidation": ["A09", "N04"],
    }


def prepare_multica_test_design_correction_input(
    previous_test_design_artifact_path: Path,
    previous_test_design_bundle_path: Path,
    oracle_review_artifact_path: Path,
    n04_artifact_path: Path,
    output_dir: Path,
    *,
    human_correction_request_path: Path | None = None,
    human_correction_decision_path: Path | None = None,
    human_correction_policy_path: Path | None = None,
    g02_review_request_path: Path | None = None,
    g02_review_decision_path: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Build a hash-bound A08 correction input after an N04 or G02 route back."""

    security = security or SecurityPolicy()
    design = _verified_artifact(
        previous_test_design_artifact_path, "a08-test-design-ir", security
    )
    review = _verified_artifact(
        oracle_review_artifact_path, "a09-oracle-coverage-review", security
    )
    n04 = _verified_artifact(n04_artifact_path, "n04-test-case-ir-validation", security)
    previous_bundle = _read(previous_test_design_bundle_path)
    for value in (previous_bundle, design, review, n04):
        security.assert_no_secret_values(value)
    _assert_no_forbidden_oracle_fields(previous_bundle)

    expected_bundle_hash = str(previous_bundle.get("bundle_hash", ""))
    unhashed_bundle = {
        key: value for key, value in previous_bundle.items() if key != "bundle_hash"
    }
    if (
        previous_bundle.get("profile_id") != "A08"
        or not expected_bundle_hash
        or expected_bundle_hash != content_hash(unhashed_bundle)
    ):
        raise ContractError("A08 correction requires the valid previous A08 input bundle")
    if design["payload"].get("input_bundle_hash") != expected_bundle_hash:
        raise ContractError("A08 correction previous Artifact does not bind its input bundle")

    identities = {
        (
            str(item.get("workflow_run_id", "")),
            str(item.get("workflow_mode", "")),
            str(item.get("source_snapshot_id", "")),
        )
        for item in (design, review, n04)
    }
    if len(identities) != 1 or not all(next(iter(identities))):
        raise ContractError("A08 correction Artifacts belong to different workflow runs")
    workflow_run_id, workflow_mode, snapshot_id = identities.pop()
    for field_name, expected in (
        ("workflow_run_id", workflow_run_id),
        ("workflow_mode", workflow_mode),
        ("source_snapshot_id", snapshot_id),
    ):
        if previous_bundle.get(field_name) != expected:
            raise ContractError(
                f"A08 correction previous input {field_name} does not match its Artifact"
            )

    recovery_paths = (
        human_correction_request_path,
        human_correction_decision_path,
        human_correction_policy_path,
    )
    if any(recovery_paths) and not all(recovery_paths):
        raise ContractError("A08 human recovery requires request, decision, and policy")
    human_recovery = all(recovery_paths)
    g02_paths = (g02_review_request_path, g02_review_decision_path)
    if any(g02_paths) and not all(g02_paths):
        raise ContractError("A08 G02 correction requires request and decision")
    g02_direction = all(g02_paths)
    if human_recovery and g02_direction:
        raise ContractError("A08 correction cannot mix human recovery and G02 direction")
    n04_payload = n04["payload"]
    expected_route = "human" if human_recovery else "A08"
    if g02_direction:
        route_ok = (
            n04_payload.get("valid") is True
            and n04_payload.get("next_node") == "G02"
            and n04_payload.get("g02_status") == "pending"
        )
    else:
        route_ok = (
            n04_payload.get("valid") is False
            and n04_payload.get("next_node") == expected_route
            and n04_payload.get("g02_status") == "not_started"
        )
    if not route_ok:
        raise ContractError(
            "A08 correction requires the matching N04 correction route before G02"
        )
    if n04_payload.get("test_design_artifact_hash") != design["artifact_hash"]:
        raise ContractError("A08 correction N04 does not bind the previous A08 Artifact")
    if n04_payload.get("oracle_review_artifact_hash") != review["artifact_hash"]:
        raise ContractError("A08 correction N04 does not bind the A09 review Artifact")
    attempt = n04_payload.get("correction_attempt")
    max_attempts = n04_payload.get("max_correction_attempts")
    if not isinstance(attempt, int) or not isinstance(max_attempts, int):
        raise ContractError("A08 correction N04 retry budget is invalid")
    if attempt >= max_attempts and not (human_recovery or g02_direction):
        raise ContractError("A08 correction retry budget is exhausted")

    human_authorization: dict[str, Any] | None = None
    if human_recovery:
        request = _read(human_correction_request_path)
        decision = _read(human_correction_decision_path)
        correction_policy = _read(human_correction_policy_path)
        for value in (request, decision, correction_policy):
            security.assert_no_secret_values(value)
        validate_human_correction_decision(request, decision, correction_policy)
        if decision.get("decision") != "directed_correction":
            raise ContractError("A08 human recovery requires directed_correction")
        request_upstream = {
            str(item.get("artifact_id")): str(item.get("artifact_hash"))
            for item in request.get("upstream_artifacts", [])
            if isinstance(item, Mapping)
        }
        for artifact in (design, review, n04):
            if request_upstream.get(artifact["artifact_id"]) != artifact["artifact_hash"]:
                raise ContractError("A08 human correction authorization is stale")
        if request.get("budget", {}).get("automatic_budget_reset") is not False:
            raise SecurityPolicyError("A08 human recovery cannot reset the automatic budget")
        if request.get("budget", {}).get("next_attempt") != attempt + 1:
            raise ContractError("A08 human recovery attempt is invalid")
        human_authorization = {
            "schema_version": decision["schema_version"],
            "request_hash": request["request_hash"],
            "decision_hash": decision["decision_hash"],
            "decision": decision["decision"],
            "actor": dict(decision["actor"]),
            "authorized_directive_ids": list(decision["authorized_directive_ids"]),
            "automatic_budget_reset": False,
            "required_revalidation": list(decision["required_revalidation"]),
        }

    g02_authorization: dict[str, Any] | None = None
    if g02_direction:
        g02_request = _read(g02_review_request_path)
        g02_decision = _read(g02_review_decision_path)
        for value in (g02_request, g02_decision):
            security.assert_no_secret_values(value)
        g02_authorization = _validate_g02_review_direction(
            g02_request, g02_decision, n04
        )
        request_upstream = {
            str(item.get("artifact_id")): str(item.get("artifact_hash"))
            for item in g02_request.get("upstream_artifacts", [])
            if isinstance(item, Mapping)
        }
        for artifact in (design, review, n04):
            if request_upstream.get(artifact["artifact_id"]) != artifact["artifact_hash"]:
                raise ContractError("A08 G02 direction is stale")

    previous_inputs = previous_bundle.get("allowed_inputs")
    if not isinstance(previous_inputs, Mapping):
        raise ContractError("A08 correction previous frozen inputs are invalid")
    required_frozen_inputs = {
        "validated_analysis",
        "approved_scope",
        "test_strategy",
        "case_provider_draft",
    }
    if not required_frozen_inputs.issubset(previous_inputs):
        raise ContractError("A08 correction previous frozen inputs are incomplete")
    previous_scope = previous_inputs.get("approved_scope")
    previous_gate = previous_bundle.get("upstream_gate")
    if not isinstance(previous_scope, Mapping) or not isinstance(previous_gate, Mapping):
        raise ContractError("A08 correction previous G01 approval is invalid")
    if (
        previous_scope.get("gate_id") != "G01"
        or previous_gate.get("gate_id") != "G01"
        or previous_scope.get("decision_hash") != previous_gate.get("decision_hash")
        or previous_scope.get("request_hash") != previous_gate.get("request_hash")
    ):
        raise ContractError("A08 correction previous G01 approval binding is invalid")

    review_issues = review["payload"].get("issues")
    if not isinstance(review_issues, list):
        raise ContractError("A08 correction A09 issue list is invalid")
    routed_review_issues = [
        dict(item)
        for item in review_issues
        if isinstance(item, Mapping) and item.get("route_to") == "A08"
    ]
    if human_recovery:
        feedback_schema = "test-design-correction/1.2"
        feedback_attempt = attempt + 1
        recovery_mode = "human_directed"
    elif g02_direction:
        feedback_schema = "test-design-correction/1.3"
        feedback_attempt = attempt + 1
        recovery_mode = "g02_reviewer_direction"
    else:
        feedback_schema = "test-design-correction/1.1"
        feedback_attempt = attempt
        recovery_mode = "automatic"
    correction_feedback = {
        "schema_version": feedback_schema,
        "correction_attempt": feedback_attempt,
        "max_correction_attempts": max_attempts,
        "recovery_mode": recovery_mode,
        "automatic_budget_reset": False,
        "previous_artifact_hash": design["artifact_hash"],
        "oracle_review_artifact_hash": review["artifact_hash"],
        "n04_artifact_hash": n04["artifact_hash"],
        "n04_schema_issue_groups": _group_n04_correction_issues(
            list(n04_payload.get("issues", []))
        ),
        "a09_issues": routed_review_issues,
        "required_outcome": {
            "route": "A09_then_N04",
            "g02_must_remain_blocked_until_n04_valid": True,
            "preserve_previous_artifact": True,
            "record_every_feedback_disposition": True,
        },
    }
    allowed_input_keys = [
        "validated_analysis",
        "approved_scope",
        "test_strategy",
        "case_provider_draft",
    ]
    if "historical_behavior_packet" in previous_inputs:
        allowed_input_keys.append("historical_behavior_packet")
    allowed_inputs = {
        key: previous_inputs[key]
        for key in allowed_input_keys
    }
    allowed_inputs["approved_scope"] = {
        **dict(previous_scope),
        "decision": "approved",
        "status": "approved",
    }
    allowed_inputs.update(
        {
            "previous_test_design_ir": {
                key: value
                for key, value in design["payload"].items()
                if key
                not in {
                    "schema_version",
                    "workflow_run_id",
                    "source_snapshot_id",
                    "input_bundle_hash",
                    "status",
                }
            },
            "correction_feedback": correction_feedback,
        }
    )
    if human_authorization is not None:
        allowed_inputs["human_correction_decision"] = human_authorization
    if g02_authorization is not None:
        allowed_inputs["g02_review_direction"] = g02_authorization
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": "A08",
        "profile_version": (
            "1.3.0" if human_recovery else "1.4.0" if g02_direction else "1.2.1"
        ),
        "output_contract": "test-design-ir/1.1",
        "allowed_inputs": allowed_inputs,
        "upstream_artifacts": [
            {
                "artifact_id": item["artifact_id"],
                "artifact_hash": item["artifact_hash"],
            }
            for item in (design, review, n04)
        ],
        "upstream_gate": dict(previous_bundle.get("upstream_gate", {})),
        "integrity": {
            "evaluation_oracle_included_in_agent_input": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    if human_authorization is not None:
        bundle["upstream_human_decision"] = {
            "request_hash": human_authorization["request_hash"],
            "decision_hash": human_authorization["decision_hash"],
        }
    if g02_authorization is not None:
        bundle["upstream_g02_decision"] = {
            "request_hash": g02_authorization["request_hash"],
            "decision_hash": g02_authorization["decision_hash"],
        }
    security.assert_no_secret_values(bundle)
    _assert_no_forbidden_oracle_fields(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json("a08-input.json", bundle)
    return bundle


def prepare_multica_oracle_review_input(
    test_design_artifact_path: Path,
    test_design_bundle_path: Path,
    oracle_rule_library_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile the accepted A08 Artifact and generic Oracle rules into A09 input."""

    security = security or SecurityPolicy()
    test_design = _verified_artifact(
        test_design_artifact_path, "a08-test-design-ir", security
    )
    test_design_bundle = _read(test_design_bundle_path)
    oracle_rules = _read(oracle_rule_library_path)
    security.assert_no_secret_values(test_design_bundle)
    security.assert_no_secret_values(oracle_rules)
    _assert_no_forbidden_oracle_fields(oracle_rules)

    expected_bundle_hash = str(test_design_bundle.get("bundle_hash", ""))
    unhashed_bundle = {
        key: value for key, value in test_design_bundle.items() if key != "bundle_hash"
    }
    if (
        test_design_bundle.get("profile_id") != "A08"
        or not expected_bundle_hash
        or expected_bundle_hash != content_hash(unhashed_bundle)
    ):
        raise ContractError("A09 requires the valid A08 input bundle")
    if test_design["payload"].get("input_bundle_hash") != expected_bundle_hash:
        raise ContractError("A09 A08 Artifact does not bind the supplied A08 input")
    if oracle_rules.get("schema_version") != "oracle-rule-library/1.0":
        raise ContractError("A09 Oracle rule library version is unsupported")

    required_dimensions = oracle_rules.get("required_coverage_dimensions")
    if not isinstance(required_dimensions, list) or not required_dimensions:
        raise ContractError("A09 Oracle rule library has no coverage dimensions")
    a08_inputs = test_design_bundle.get("allowed_inputs")
    if not isinstance(a08_inputs, Mapping):
        raise ContractError("A09 A08 bundle has no frozen evidence")

    workflow_run_id = str(test_design.get("workflow_run_id", ""))
    workflow_mode = str(test_design.get("workflow_mode", ""))
    snapshot_id = str(test_design.get("source_snapshot_id", ""))
    if not workflow_run_id or not workflow_mode or not snapshot_id:
        raise ContractError("A09 A08 Artifact identity is incomplete")
    for field_name, expected in (
        ("workflow_run_id", workflow_run_id),
        ("workflow_mode", workflow_mode),
        ("source_snapshot_id", snapshot_id),
    ):
        if test_design_bundle.get(field_name) != expected:
            raise ContractError(f"A09 A08 input {field_name} does not match its Artifact")

    frozen_evidence = {
        key: a08_inputs[key]
        for key in (
            "validated_analysis",
            "approved_scope",
            "test_strategy",
            "historical_behavior_packet",
        )
        if key in a08_inputs
    }
    required_frozen_evidence = {
        "validated_analysis",
        "approved_scope",
        "test_strategy",
    }
    if set(frozen_evidence) not in (
        required_frozen_evidence,
        required_frozen_evidence | {"historical_behavior_packet"},
    ):
        raise ContractError("A09 frozen evidence is incomplete")
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": "A09",
        "profile_version": "1.1.1",
        "output_contract": "oracle-review/1.1",
        "allowed_inputs": {
            "test_design_ir": test_design["payload"],
            "oracle_rule_library": oracle_rules,
            "frozen_evidence": frozen_evidence,
        },
        "upstream_artifacts": [
            {
                "artifact_id": test_design["artifact_id"],
                "artifact_hash": test_design["artifact_hash"],
            }
        ],
        "integrity": {
            "evaluation_oracle_registry_included": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    security.assert_no_secret_values(bundle)
    _assert_no_forbidden_oracle_fields(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json("a09-input.json", bundle)
    return bundle


def prepare_multica_split_review_input(
    test_design_artifact_path: Path,
    test_design_bundle_path: Path,
    compiled_artifact_path: Path,
    oracle_rule_library_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile the accepted A08 + N25 compiled cases into A11 post-split input."""

    security = security or SecurityPolicy()
    test_design = _verified_artifact(
        test_design_artifact_path, "a08-test-design-ir", security
    )
    test_design_bundle = _read(test_design_bundle_path)
    compiled = _verified_artifact(
        compiled_artifact_path, "n25-compiled-test-cases", security
    )
    oracle_rules = _read(oracle_rule_library_path)
    for value in (test_design_bundle, oracle_rules):
        security.assert_no_secret_values(value)
    _assert_no_forbidden_oracle_fields(oracle_rules)

    expected_bundle_hash = str(test_design_bundle.get("bundle_hash", ""))
    unhashed_bundle = {
        key: value for key, value in test_design_bundle.items() if key != "bundle_hash"
    }
    if (
        test_design_bundle.get("profile_id") != "A08"
        or not expected_bundle_hash
        or expected_bundle_hash != content_hash(unhashed_bundle)
    ):
        raise ContractError("A11 requires the valid A08 input bundle")
    if test_design["payload"].get("input_bundle_hash") != expected_bundle_hash:
        raise ContractError("A11 A08 Artifact does not bind the supplied A08 input")
    if compiled["payload"].get("parent_artifact_hash") != test_design["artifact_hash"]:
        raise ContractError("A11 N25 compiled cases do not bind the current A08 Artifact")
    if _identity_of(test_design) != _identity_of(compiled):
        raise ContractError("A11 A08 and N25 Artifacts belong to different runs")

    workflow_run_id, workflow_mode, snapshot_id = _identity_of(test_design)
    if oracle_rules.get("schema_version") != "oracle-rule-library/1.0":
        raise ContractError("A11 Oracle rule library version is unsupported")
    parents = [
        item for item in test_design["payload"].get("parent_cases", [])
        if isinstance(item, Mapping)
    ]
    corrected_parents = compiled["payload"].get("review_parent_cases")
    if corrected_parents is not None:
        if not isinstance(corrected_parents, list) or not all(
            isinstance(item, Mapping) for item in corrected_parents
        ):
            raise ContractError("A11 N25 review parent cases are invalid")
        original_ids = {str(item.get("id")) for item in parents}
        corrected_ids = {str(item.get("id")) for item in corrected_parents}
        if corrected_ids != original_ids:
            raise ContractError("A11 N25 review parent cases changed the parent Case set")
        parents = corrected_parents
    children = [
        item for item in compiled["payload"].get("compiled_cases", [])
        if isinstance(item, Mapping)
    ]
    parent_index = {str(item.get("id")): item for item in parents}
    parent_cases = [_compact_a11_review_case(item) for item in parents]
    compiled_child_cases = [
        _compact_a11_review_case(item, parent=parent_index.get(str(item.get("parent_case_id"))))
        for item in children
    ]
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": "A11",
        "profile_version": "1.0.0",
        "output_contract": "split-review/1.0",
        "allowed_inputs": {
            "parent_test_cases": parent_cases,
            "compiled_child_cases": compiled_child_cases,
            "oracle_rule_library": oracle_rules,
        },
        "upstream_artifacts": [
            {
                "artifact_id": test_design["artifact_id"],
                "artifact_hash": test_design["artifact_hash"],
            },
            {
                "artifact_id": compiled["artifact_id"],
                "artifact_hash": compiled["artifact_hash"],
            },
        ],
        "integrity": {
            "evaluation_oracle_registry_included": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    security.assert_no_secret_values(bundle)
    _assert_no_forbidden_oracle_fields(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json("a11-input.json", bundle)
    return bundle


GENERATION_LAYER_BY_PROFILE = {
    "A14": "backend",
    "A15": "contract",
}
GENERATION_ARTIFACT_BY_PROFILE = {
    "A14": "a14-backend-automation-generation",
    "A15": "a15-contract-automation-generation",
}
REVIEW_AGENT_BY_GENERATION = {
    "A14": "A18-BE",
    "A15": "A18-CT",
}
REVIEW_PROFILE_BY_AGENT = {
    "A18-BE": "A18-BE/1.0.0",
    "A18-CT": "A18-CT/1.0.0",
}


def _compact_generation_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Compress one N25 child Case into the automation generation scope.

    Keeps every field the generator needs to emit an artifact-only candidate while
    dropping audit-only fields that would inflate the Agent context (parent IR
    copies, split bookkeeping).
    """

    policy = case.get("execution_policy")
    expected = []
    for item in case.get("expected", []):
        if not isinstance(item, Mapping):
            continue
        oracle = item.get("oracle")
        oracle_value = dict(oracle) if isinstance(oracle, Mapping) else {}
        expected.append(
            {
                "id": item.get("id"),
                "description": item.get("description"),
                "type": oracle_value.get("type"),
                "matcher": oracle_value.get("matcher"),
                "observation_point": oracle_value.get("observation_point"),
                "source_ref": oracle_value.get("source_ref"),
                "expected_value": oracle_value.get("expected_value"),
                "expected_values": oracle_value.get("expected_values"),
                "oracle": oracle_value,
            }
        )
    compact: dict[str, Any] = {
        "id": case.get("id"),
        "parent_case_id": case.get("parent_case_id"),
        "title": case.get("title"),
        "layer": case.get("layer"),
        "risk": case.get("risk"),
        "priority": case.get("priority"),
        "automation_candidate": case.get("automation_candidate") is True,
        "source_refs": list(case.get("source_refs", [])),
        "intent_ids": list(case.get("intent_ids", [])),
        "preconditions": list(case.get("preconditions", [])),
        "test_data": dict(case.get("test_data", {})),
        "steps": list(case.get("steps", [])),
        "expected": expected,
        "cleanup": list(case.get("cleanup", [])),
        "execution_policy": (
            dict(policy) if isinstance(policy, Mapping) else {}
        ),
    }
    for lifecycle_key in (
        "environment", "namespace", "variables", "setup", "readiness", "residue_checks",
    ):
        if lifecycle_key in case:
            compact[lifecycle_key] = case[lifecycle_key]
    return compact


def _http_operation_catalog(framework_root: Path | None = None) -> dict[str, Any]:
    """Compact operationId/method/path summary of the target repo IDL catalog.

    Generation Agents are sandboxed to their Issue attachment and cannot read the
    target repository, so the N08 ``case_runner`` API vocabulary must travel with
    the input bundle. Only the stable identifiers are included (no schemas): the
    Agent uses them to emit real ``request.api`` operations instead of inventing
    paths, and N08 resolves them against the runtime ``idl/http`` catalog.
    """

    root = framework_root or Path(__file__).resolve().parents[3]
    catalog_dir = root / "idl" / "http"
    operations: list[dict[str, str]] = []
    if catalog_dir.is_dir():
        for path in sorted(catalog_dir.rglob("*.openapi.json")):
            try:
                document = _read(path)
            except (OSError, json.JSONDecodeError):
                continue
            for api_path, path_item in document.get("paths", {}).items():
                if not isinstance(path_item, Mapping):
                    continue
                for method, definition in path_item.items():
                    if str(method).lower() not in {"get", "post", "put", "patch", "delete"}:
                        continue
                    operation_id = (
                        definition.get("operationId")
                        if isinstance(definition, Mapping) else None
                    )
                    if not operation_id:
                        continue
                    operations.append(
                        {
                            "operationId": str(operation_id),
                            "method": str(method).upper(),
                            "path": str(api_path),
                        }
                    )
    return {
        "schema_version": "http-operation-catalog/1.0",
        "source": "idl/http",
        "operation_count": len(operations),
        "operations": operations,
    }


def _verified_setup_contracts(
    security: SecurityPolicy,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Load the 112-verified setup body contracts for A14 data construction.

    The contracts are the only permitted source for setup ``json`` bodies:
    A14 must reproduce the ``body_template`` verbatim and fill only
    ``{{PLACEHOLDER}}`` markers, so N08 ``case_runner`` calls succeed against
    the real 112 environment instead of failing business validation.
    """

    source = path or Path(__file__).resolve().parents[2] / "knowledge" / "verified-setup-contracts.json"
    if not source.exists():
        return None
    contracts = _read(source)
    security.assert_no_secret_values(contracts)
    if contracts.get("schema_version") != "verified-setup-contracts/1.0":
        raise ContractError("verified-setup-contracts schema version is unsupported")
    return contracts


def _resources_with_contract_keys(
    resources: Sequence[Mapping[str, Any]],
    contracts: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Attach the verified contract's required body keys to each resource.

    N05 uses ``required_body_keys`` to reject placeholder setup bodies (only
    namespace/variant) that would fail 112 business validation at runtime.
    Read-only resources (no creation body) stay untouched.
    """

    by_operation = {}
    if contracts is not None:
        by_operation = {
            str(key): value for key, value in contracts.get("contracts", {}).items()
        }
    merged: list[dict[str, Any]] = []
    for resource in resources:
        item = dict(resource)
        operation = str(item.get("setup_operation", ""))
        contract = by_operation.get(operation)
        if isinstance(contract, Mapping):
            required = contract.get("required_body_keys")
            if isinstance(required, list) and required:
                item["required_body_keys"] = [str(key) for key in required]
            retention_mode = str(contract.get("retention_mode", ""))
            if retention_mode:
                item["retention_mode"] = retention_mode
        merged.append(item)
    return merged


def _merge_test_data_plan_resources(
    layer_cases: list[dict[str, Any]],
    data_plan: Mapping[str, Any] | None,
    contracts: Mapping[str, Any] | None,
) -> None:
    """Merge A22 plan resources into each generation Case's test_data.

    A22 already planned which resources each Case constructs (resource type,
    setup_operation, id variable, high_risk_write). The generator needs them as
    ``test_data.resource_requirements`` so it can emit real setup/cleanup
    requests instead of inventing placeholder bodies.
    """

    if data_plan is None:
        return
    plan_payload = data_plan.get("payload")
    case_plans = plan_payload.get("case_plans", []) if isinstance(plan_payload, Mapping) else []
    resources_by_case: dict[str, list[Mapping[str, Any]]] = {}
    for case_plan in case_plans:
        if not isinstance(case_plan, Mapping):
            continue
        resources = case_plan.get("resources")
        if isinstance(resources, list):
            resources_by_case[str(case_plan.get("case_id", ""))] = resources
    for layer_case in layer_cases:
        case_id = str(layer_case.get("id", ""))
        planned = resources_by_case.get(case_id)
        if not planned:
            continue
        enriched = _resources_with_contract_keys(planned, contracts)
        test_data = layer_case.get("test_data")
        if not isinstance(test_data, Mapping):
            test_data = {}
            layer_case["test_data"] = test_data
        existing = test_data.get("resource_requirements")
        if isinstance(existing, list) and existing:
            by_key = {
                str(item.get("resource_key", "")): dict(item)
                for item in existing
                if isinstance(item, Mapping)
            }
            for item in enriched:
                by_key[str(item.get("resource_key", ""))] = item
            test_data["resource_requirements"] = list(by_key.values())
        else:
            test_data["resource_requirements"] = enriched


def prepare_multica_automation_generation_input(
    compiled_cases_path: Path,
    execution_plan_path: Path,
    automation_policy_path: Path,
    output_dir: Path,
    *,
    profile_id: str,
    test_data_plan_path: Path | None = None,
    test_data_validation_path: Path | None = None,
    knowledge_readiness_path: Path | None = None,
    verified_setup_contracts_path: Path | None = None,
    regeneration_round: int | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile N25 + N15 + approved automation target into A14/A15 input.

    ``regeneration_round`` stamps a fresh bundle hash for deliberate reruns.
    Without it, deleting a generation Artifact would just re-ingest the latest
    completed Agent run (idempotent recovery) and silently restore the stale
    output, making a genuine regeneration impossible.
    """

    if profile_id not in GENERATION_LAYER_BY_PROFILE:
        raise ContractError(f"Unsupported generation profile: {profile_id}")
    security = security or SecurityPolicy()
    compiled = _verified_artifact(
        compiled_cases_path, "n25-compiled-test-cases", security
    )
    plan = _verified_artifact(execution_plan_path, "n15-execution-plan", security)
    if _identity_of(compiled) != _identity_of(plan):
        raise ContractError(f"{profile_id} N15 and N25 belong to different runs")
    workflow_run_id, workflow_mode, snapshot_id = _identity_of(compiled)
    layer = GENERATION_LAYER_BY_PROFILE[profile_id]
    payload = compiled.get("payload")
    if not isinstance(payload, Mapping):
        raise ContractError("N25 compiled cases payload is invalid")
    cases = payload.get("compiled_cases", payload.get("child_cases"))
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N25 compiled_cases or child_cases must be a list of objects")
    layer_cases = [
        _compact_generation_case(item)
        for item in cases
        if str(item.get("layer", "")) == layer
    ]
    if not layer_cases:
        raise ContractError(f"{profile_id} has no {layer} Cases in the compiled set")
    plan_actions = plan.get("payload", {}).get("actions", [])
    if not isinstance(plan_actions, list):
        raise ContractError("N15 execution plan actions are invalid")
    actions_by_case = {
        str(item.get("case_id", "")): item
        for item in plan_actions
        if isinstance(item, Mapping)
    }
    missing_actions = sorted(
        case_id for case_id in {str(item["id"]) for item in layer_cases}
        if case_id not in actions_by_case
    )
    if missing_actions:
        raise ContractError(f"{profile_id} N15 has no action for: {', '.join(missing_actions)}")

    target_policy = _read(automation_policy_path)
    security.assert_no_secret_values(target_policy)
    if target_policy.get("schema_version") != "automation-target-policy/1.0":
        raise ContractError(f"{profile_id} automation target policy version is unsupported")
    targets = target_policy.get("targets", [])
    if not isinstance(targets, list) or not targets:
        raise ContractError(f"{profile_id} automation target policy has no targets")
    target_config = {
        "targets": targets,
        "layer_profile": next(
            (
                item
                for item in target_policy.get("layer_profiles", {}).values()
                if isinstance(item, Mapping) and item.get("agent_id") == profile_id
            ),
            None,
        ),
        "command_allowlist": target_policy.get("command_allowlist", []),
        "forbidden_python_imports": target_policy.get("forbidden_python_imports", []),
        "forbidden_calls": target_policy.get("forbidden_calls", []),
    }
    if target_config["layer_profile"] is None:
        raise ContractError(f"{profile_id} automation target has no layer profile")

    upstream: list[dict[str, str]] = [
        {"artifact_id": "n25-compiled-test-cases", "artifact_hash": compiled["artifact_hash"]},
        {"artifact_id": "n15-execution-plan", "artifact_hash": plan["artifact_hash"]},
    ]
    input_bindings: dict[str, Any] = {}
    data_validation = None
    if test_data_validation_path is not None:
        data_validation = _verified_artifact(
            test_data_validation_path, "n27-test-data-plan-validation", security
        )
        upstream.append(
            {
                "artifact_id": "n27-test-data-plan-validation",
                "artifact_hash": data_validation["artifact_hash"],
            }
        )
        input_bindings["test_data_validation_hash"] = data_validation["artifact_hash"]
    verified_contracts = None
    if profile_id == "A14":
        verified_contracts = _verified_setup_contracts(security, verified_setup_contracts_path)
        if verified_contracts is not None:
            input_bindings["verified_setup_contracts_hash"] = content_hash(verified_contracts)
    if test_data_plan_path is not None:
        data_plan = _verified_artifact(
            test_data_plan_path, "a22-test-data-plan", security
        )
        upstream.append(
            {"artifact_id": "a22-test-data-plan", "artifact_hash": data_plan["artifact_hash"]}
        )
        input_bindings["test_data_plan_hash"] = data_plan["artifact_hash"]
        _merge_test_data_plan_resources(layer_cases, data_plan, verified_contracts)
    if knowledge_readiness_path is not None:
        knowledge = _read(knowledge_readiness_path)
        security.assert_no_secret_values(knowledge)
        packet_hash = str(knowledge.get("packet_hash", ""))
        if not packet_hash:
            raise ContractError(f"{profile_id} knowledge readiness packet has no packet_hash")
        input_bindings["knowledge_packet_hash"] = packet_hash

    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": profile_id,
        "profile_version": "1.0.0",
        "output_contract": "automation-generation/1.0",
        "allowed_inputs": {
            "layer": layer,
            "cases": layer_cases,
            "execution_plan_actions": [
                actions_by_case[str(item["id"])] for item in layer_cases
            ],
            "automation_target": target_config,
            "api_catalog": _http_operation_catalog(),
            "input_bindings": input_bindings,
            **({"verified_setup_contracts": verified_contracts} if verified_contracts is not None else {}),
        },
        "upstream_artifacts": upstream,
        "integrity": {
            "evaluation_oracle_registry_included": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    if regeneration_round is not None:
        bundle["regeneration_round"] = str(regeneration_round)
    security.assert_no_secret_values(bundle)
    _assert_no_forbidden_oracle_fields(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json(f"{profile_id.lower()}-input.json", bundle)
    return bundle


def prepare_multica_automation_review_input(
    generation_artifact_path: Path,
    generation_bundle_path: Path,
    compiled_cases_path: Path,
    automation_policy_path: Path,
    output_dir: Path,
    *,
    profile_id: str,
    regeneration_round: int | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile one A14/A15 generation plus N25 scope into A18-BE/A18-CT input."""

    if profile_id not in REVIEW_AGENT_BY_GENERATION.values():
        raise ContractError(f"Unsupported review profile: {profile_id}")
    generator_profile = next(
        key for key, value in REVIEW_AGENT_BY_GENERATION.items() if value == profile_id
    )
    generation_artifact_id = GENERATION_ARTIFACT_BY_PROFILE[generator_profile]
    security = security or SecurityPolicy()
    generation = _verified_artifact(
        generation_artifact_path, generation_artifact_id, security
    )
    generation_bundle = _read(generation_bundle_path)
    compiled = _verified_artifact(
        compiled_cases_path, "n25-compiled-test-cases", security
    )
    for value in (generation_bundle, compiled):
        security.assert_no_secret_values(value)
    _assert_no_forbidden_oracle_fields(generation_bundle)

    expected_bundle_hash = str(generation_bundle.get("bundle_hash", ""))
    unhashed_bundle = {
        key: value for key, value in generation_bundle.items() if key != "bundle_hash"
    }
    if (
        generation_bundle.get("profile_id") != generator_profile
        or not expected_bundle_hash
        or expected_bundle_hash != content_hash(unhashed_bundle)
    ):
        raise ContractError(f"{profile_id} requires the valid {generator_profile} input bundle")
    if generation["payload"].get("input_bundle_hash") != expected_bundle_hash:
        raise ContractError(f"{profile_id} generation Artifact does not bind its input")
    if _identity_of(generation) != _identity_of(compiled):
        raise ContractError(f"{profile_id} generation and N25 belong to different runs")
    workflow_run_id, workflow_mode, snapshot_id = _identity_of(generation)

    layer = GENERATION_LAYER_BY_PROFILE[generator_profile]
    payload = compiled.get("payload")
    cases = (
        payload.get("compiled_cases", payload.get("child_cases"))
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N25 compiled_cases or child_cases must be a list of objects")
    layer_cases = [
        _compact_generation_case(item)
        for item in cases
        if str(item.get("layer", "")) == layer
    ]
    target_policy = _read(automation_policy_path)
    security.assert_no_secret_values(target_policy)
    generation_payload = generation.get("payload")
    if not isinstance(generation_payload, Mapping):
        raise ContractError(f"{generation_artifact_id} payload is invalid")
    manifest = generation_payload.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ContractError(f"{profile_id} cannot review a not-applicable generation")

    review_allowed_inputs = {
        "layer": layer,
        "cases": layer_cases,
        "generation": generation_payload,
        "security_rules": {
            "command_allowlist": target_policy.get("command_allowlist", []),
            "forbidden_python_imports": target_policy.get("forbidden_python_imports", []),
            "forbidden_calls": target_policy.get("forbidden_calls", []),
        },
        "review_profile": REVIEW_PROFILE_BY_AGENT[profile_id],
    }
    if profile_id == "A18-BE":
        generation_allowed_inputs = generation_bundle.get("allowed_inputs")
        verified_contracts = (
            generation_allowed_inputs.get("verified_setup_contracts")
            if isinstance(generation_allowed_inputs, Mapping)
            else None
        )
        if not isinstance(verified_contracts, Mapping):
            raise ContractError(
                "A18-BE requires verified_setup_contracts from the A14 input bundle"
            )
        review_allowed_inputs["verified_setup_contracts"] = dict(verified_contracts)

    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": profile_id,
        "profile_version": "1.0.0",
        "output_contract": "automation-review/1.0",
        "allowed_inputs": review_allowed_inputs,
        "upstream_artifacts": [
            {"artifact_id": generation_artifact_id, "artifact_hash": generation["artifact_hash"]},
            {"artifact_id": "n25-compiled-test-cases", "artifact_hash": compiled["artifact_hash"]},
        ],
        "integrity": {
            "evaluation_oracle_registry_included": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    if regeneration_round is not None:
        bundle["regeneration_round"] = str(regeneration_round)
    security.assert_no_secret_values(bundle)
    _assert_no_forbidden_oracle_fields(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json(f"{profile_id.lower()}-input.json", bundle)
    return bundle


def prepare_multica_test_data_plan_input(
    compiled_cases_path: Path,
    execution_plan_path: Path,
    test_data_policy_path: Path,
    output_dir: Path,
    *,
    capability_catalog_path: Path | None = None,
    knowledge_sources_path: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile N25 + N15 + data policy into the A22 test-data plan input."""

    security = security or SecurityPolicy()
    compiled = _verified_artifact(
        compiled_cases_path, "n25-compiled-test-cases", security
    )
    plan = _verified_artifact(execution_plan_path, "n15-execution-plan", security)
    if _identity_of(compiled) != _identity_of(plan):
        raise ContractError("A22 N15 and N25 belong to different runs")
    workflow_run_id, workflow_mode, snapshot_id = _identity_of(compiled)
    payload = compiled.get("payload")
    if not isinstance(payload, Mapping):
        raise ContractError("N25 compiled cases payload is invalid")
    cases = payload.get("compiled_cases", payload.get("child_cases"))
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N25 compiled_cases or child_cases must be a list of objects")
    policy = _read(test_data_policy_path)
    security.assert_no_secret_values(policy)
    if policy.get("schema_version") != "test-data-policy/1.0":
        raise ContractError("A22 test-data policy version is unsupported")
    plan_actions = plan.get("payload", {}).get("actions", [])
    if not isinstance(plan_actions, list):
        raise ContractError("N15 execution plan actions are invalid")
    actions_by_case = {
        str(item.get("case_id", "")): item
        for item in plan_actions
        if isinstance(item, Mapping)
    }

    context: dict[str, Any] = {}
    if capability_catalog_path is not None:
        catalog = _read(capability_catalog_path)
        security.assert_no_secret_values(catalog)
        context["capability_catalog"] = catalog
    if knowledge_sources_path is not None:
        sources = _read(knowledge_sources_path)
        security.assert_no_secret_values(sources)
        context["knowledge_sources"] = sources
    if (capability_catalog_path is None) != (knowledge_sources_path is None):
        raise ContractError("A22 catalog and knowledge sources must be provided together")

    allowed_environments = {
        str(item) for item in policy.get("allowed_environments", [])
    }
    default_namespace = "qa-a22-" + str(snapshot_id).casefold().replace("_", "-")[:40]
    default_namespace = re.sub(r"[^a-z0-9-]", "-", default_namespace).strip("-")
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": "A22",
        "profile_version": "1.0.0",
        "output_contract": "test-data-plan/1.0",
        "allowed_inputs": {
            "cases": [_compact_generation_case(item) for item in cases],
            "execution_plan_actions": [
                actions_by_case[str(item.get("id", ""))] for item in cases
            ],
            "test_data_policy": policy,
            "planning_defaults": {
                "environment": sorted(allowed_environments)[0] if allowed_environments else "112",
                "namespace": default_namespace,
            },
            **context,
        },
        "upstream_artifacts": [
            {"artifact_id": "n25-compiled-test-cases", "artifact_hash": compiled["artifact_hash"]},
            {"artifact_id": "n15-execution-plan", "artifact_hash": plan["artifact_hash"]},
        ],
        "integrity": {
            "evaluation_oracle_registry_included": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    security.assert_no_secret_values(bundle)
    _assert_no_forbidden_oracle_fields(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json("a22-input.json", bundle)
    return bundle


def prepare_multica_test_data_plan_revision_input(
    previous_plan_path: Path,
    validation_path: Path,
    previous_input_path: Path,
    output_dir: Path,
    *,
    revision_attempt: int,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Build an A22 revision input from the rejected plan and N27 validation.

    The revision re-freezes the original cases/actions/policy scope and adds the
    rejected plan plus the N27 validation error so the Agent can fix only what
    N27 blocked. Revision attempts are content-addressed per attempt.
    """

    security = security or SecurityPolicy()
    if int(revision_attempt) < 1:
        raise ContractError("A22 revision_attempt must be >= 1")
    previous = _verified_artifact(
        previous_plan_path,
        "a22-test-data-plan",
        security,
    )
    validation = _verified_artifact(
        validation_path,
        "n27-test-data-plan-validation",
        security,
        allowed_statuses={ArtifactStatus.BLOCKED.value},
    )
    if _identity_of(previous) != _identity_of(validation):
        raise ContractError("A22 revision plan and validation belong to different runs")
    validation_payload = validation.get("payload", {})
    if not isinstance(validation_payload, Mapping) or validation_payload.get(
        "valid"
    ) is not False:
        raise ContractError("A22 revision requires a rejected N27 validation")
    previous_input = _read(previous_input_path)
    if previous_input.get("schema_version") != "multica-agent-input/1.0":
        raise ContractError("A22 revision previous input schema_version is invalid")
    if str(previous_input.get("profile_id", "")) != "A22":
        raise ContractError("A22 revision previous input is not an A22 bundle")
    if str(previous.get("payload", {}).get("input_bundle_hash", "")) != str(
        previous_input.get("bundle_hash", "")
    ):
        raise ContractError("A22 revision previous Artifact does not bind its input bundle")

    allowed_inputs = previous_input.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError("A22 revision previous input has no frozen scope")
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": previous_input["workflow_run_id"],
        "workflow_mode": previous_input["workflow_mode"],
        "source_snapshot_id": previous_input["source_snapshot_id"],
        "profile_id": "A22",
        "profile_version": "1.0.0",
        "output_contract": "test-data-plan/1.0",
        "revision": {
            "revision_attempt": int(revision_attempt),
            "previous_plan_hash": previous["artifact_hash"],
            "validation_hash": validation["artifact_hash"],
            "validation_error": str(validation_payload.get("validation_error", "")),
        },
        "allowed_inputs": {
            **allowed_inputs,
            "previous_plan": previous["payload"],
            "n27_validation": validation_payload,
        },
        "upstream_artifacts": list(previous_input.get("upstream_artifacts", [])) + [
            {
                "artifact_id": "a22-test-data-plan",
                "artifact_hash": previous["artifact_hash"],
            },
            {
                "artifact_id": "n27-test-data-plan-validation",
                "artifact_hash": validation["artifact_hash"],
            },
        ],
        "integrity": previous_input.get("integrity", {}),
    }
    security.assert_no_secret_values(bundle)
    _assert_no_forbidden_oracle_fields(bundle)
    bundle["bundle_hash"] = content_hash(
        {key: value for key, value in bundle.items() if key != "bundle_hash"}
    )
    ArtifactStore(output_dir).write_json(
        f"a22-input-revision-{int(revision_attempt)}.json", bundle
    )
    return bundle


def _compact_a11_review_case(
    case: Mapping[str, Any], *, parent: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Compress one case into the A11 review scope without losing audit fields.

    N25 only copies or narrows execution responsibility, so child cases repeat the
    parent content. A11 reviews the split, not the full payloads; keeping the full
    duplicated test_data/steps/oracle bodies in the Agent input inflates the context
    and can exceed the runtime semantic-inactivity watchdog during final generation.
    """

    policy = case.get("execution_policy")
    allowed_modes = (
        list(policy.get("allowed_modes", [])) if isinstance(policy, Mapping) else []
    )
    expected = []
    for item in case.get("expected", []):
        if not isinstance(item, Mapping):
            continue
        oracle = item.get("oracle")
        expected.append(
            {
                "id": item.get("id"),
                "description": item.get("description"),
                "type": oracle.get("type") if isinstance(oracle, Mapping) else None,
                "matcher": oracle.get("matcher") if isinstance(oracle, Mapping) else None,
                "source_ref": (
                    oracle.get("source_ref") if isinstance(oracle, Mapping) else None
                ),
            }
        )
    compact: dict[str, Any] = {
        "id": case.get("id"),
        "title": case.get("title"),
        "layer": case.get("layer"),
        "required_layers": list(case.get("required_layers", [])),
        "risk": case.get("risk"),
        "priority": case.get("priority"),
        "source_refs": list(case.get("source_refs", [])),
        "intent_ids": list(case.get("intent_ids", [])),
        "expected": expected,
        "execution_policy": {"allowed_modes": allowed_modes},
        "test_data_present": isinstance(case.get("test_data"), Mapping),
        "cleanup_present": bool(case.get("cleanup")),
        "cleanup_oracle_present": isinstance(case.get("cleanup_oracle"), Mapping),
        "steps_count": len(case.get("steps", [])) if isinstance(case.get("steps"), list) else 0,
        "preconditions_count": (
            len(case.get("preconditions", [])) if isinstance(case.get("preconditions"), list) else 0
        ),
    }
    if parent is not None:
        compact["parent_case_id"] = case.get("parent_case_id")
        compact["inherits_parent"] = {
            field: _a11_field_equal(parent, case, field)
            for field in (
                "test_data",
                "cleanup",
                "cleanup_oracle",
                "source_refs",
                "execution_policy",
                "preconditions",
            )
        }
        parent_ids = {
            str(item.get("id")) for item in parent.get("expected", [])
            if isinstance(item, Mapping)
        }
        child_ids = {
            str(item.get("id")) for item in case.get("expected", [])
            if isinstance(item, Mapping)
        }
        compact["inherits_parent"]["expected_oracle_ids"] = child_ids <= parent_ids
    return compact


def _a11_field_equal(
    parent: Mapping[str, Any], child: Mapping[str, Any], field: str, *, key: str | None = None
) -> bool:
    left = parent.get(field)
    right = child.get(field)
    if key is not None:
        left = [item.get(key) for item in left] if isinstance(left, list) else left
        right = [item.get(key) for item in right] if isinstance(right, list) else right
    return left == right


def prepare_multica_selection_advice_input(
    selection_artifact_path: Path,
    compiled_artifact_path: Path,
    output_dir: Path,
    *,
    change_set_path: Path | None = None,
    asset_catalog_path: Path | None = None,
    selection_policy_path: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile N26 unresolved items + ChangeSet + asset evidence into A12 input.

    A12 only runs when N26 has unresolved impact relationships; it returns
    advice-only suggestions that N26 validates before folding.  The input is
    hash-bound to the N26 selection and N25 compiled Artifacts.
    """

    security = security or SecurityPolicy()
    selection = _verified_artifact(
        selection_artifact_path, "n26-test-selection", security
    )
    compiled = _verified_artifact(
        compiled_artifact_path, "n25-compiled-test-cases", security
    )
    unresolved = selection["payload"].get("unresolved_items")
    if not isinstance(unresolved, list) or not unresolved:
        raise ContractError("A12 requires N26 unresolved selection items")
    if selection["payload"].get("compiled_artifact_hash") != compiled["artifact_hash"]:
        raise ContractError("A12 N26 selection does not bind the compiled Artifact")
    if _identity_of(selection) != _identity_of(compiled):
        raise ContractError("A12 N26 and N25 Artifacts belong to different runs")
    workflow_run_id, workflow_mode, snapshot_id = _identity_of(selection)

    compiled_cases = compiled["payload"].get("compiled_cases")
    if not isinstance(compiled_cases, list) or not all(
        isinstance(item, Mapping) for item in compiled_cases
    ):
        raise ContractError("A12 compiled child cases are invalid")
    case_index = {
        str(case.get("id", "")): {
            "layer": case.get("layer"),
            "required_layers": case.get("required_layers", []),
            "evidence_modules": case.get("evidence_modules", []),
            "automation_candidate": case.get("automation_candidate", False),
        }
        for case in compiled_cases
        if isinstance(case, Mapping) and case.get("id")
    }

    change_set = _read(change_set_path) if change_set_path is not None else {}
    asset_catalog = _read(asset_catalog_path) if asset_catalog_path is not None else {}
    selection_policy = (
        _read(selection_policy_path) if selection_policy_path is not None else {}
    )
    for value in (change_set, asset_catalog, selection_policy):
        security.assert_no_secret_values(value)
    _assert_no_forbidden_oracle_fields(selection_policy)

    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": "A12",
        "profile_version": "1.0.0",
        "output_contract": "test-selection-advice/1.0",
        "allowed_inputs": {
            "unresolved_items": unresolved,
            "compiled_case_index": case_index,
            "change_set": change_set,
            "asset_evidence": asset_catalog,
            "selection_policy": selection_policy,
        },
        "upstream_artifacts": [
            {
                "artifact_id": selection["artifact_id"],
                "artifact_hash": selection["artifact_hash"],
            },
            {
                "artifact_id": compiled["artifact_id"],
                "artifact_hash": compiled["artifact_hash"],
            },
        ],
        "integrity": {
            "evaluation_oracle_registry_included": False,
            "credentials_embedded": False,
            "business_repository_write_allowed": False,
            "external_side_effects_allowed": False,
        },
    }
    security.assert_no_secret_values(bundle)
    _assert_no_forbidden_oracle_fields(bundle)
    bundle["bundle_hash"] = content_hash(bundle)
    ArtifactStore(output_dir).write_json("a12-input.json", bundle)
    return bundle


def _identity_of(artifact: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(artifact.get("workflow_run_id", "")),
        str(artifact.get("workflow_mode", "")),
        str(artifact.get("source_snapshot_id", "")),
    )


def _assert_no_forbidden_oracle_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in {
                "evaluation_oracle",
                "evaluation_oracle_registry",
                "golden_answer",
                "expected_agent_output",
            }:
                raise SecurityPolicyError(f"Evaluation Oracle field found at {path}.{key}")
            _assert_no_forbidden_oracle_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_oracle_fields(item, f"{path}[{index}]")


def _parse_raw_model_output(raw_output: str) -> dict[str, Any]:
    if not raw_output.strip():
        raise ContractError("Multica model output is empty")
    try:
        value = json.loads(raw_output)
    except json.JSONDecodeError as error:
        value = _trailing_json_object(raw_output)
        if value is None:
            raise ContractError(
                "Multica model output must be one raw JSON object without Markdown fences"
            ) from error
    if not isinstance(value, dict):
        raise ContractError("Multica model output must be a JSON object")
    return value


def _trailing_json_object(raw_output: str) -> dict[str, Any] | None:
    """Extract the last JSON object when the model wraps it in prose or fences."""

    decoder = json.JSONDecoder()
    index = raw_output.rfind("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(raw_output, index)
        except json.JSONDecodeError:
            index = raw_output.rfind("{", 0, index)
            continue
        if not isinstance(value, dict):
            index = raw_output.rfind("{", 0, index)
            continue
        tail = raw_output[end:].strip()
        if not tail or tail in {"```", "````", "```json"}:
            return value
        index = raw_output.rfind("{", 0, index)
    return None


def _coerce_raw_response(raw_response: str) -> dict[str, Any] | list[Any] | None:
    """Parse a raw model response, tolerating a human-readable prose preamble."""

    try:
        value = json.loads(raw_response)
    except json.JSONDecodeError:
        value = _trailing_json_object(raw_response)
    if isinstance(value, (dict, list)):
        return value
    return None


def extract_multica_model_output(raw_response: str) -> dict[str, Any]:
    """Extract the final pure-JSON text message without parsing an aggregated task log."""

    response = _coerce_raw_response(raw_response)
    if response is None:
        raise ContractError("Multica response file must be valid JSON")
    if isinstance(response, dict):
        return response
    if not isinstance(response, list):
        raise ContractError("Multica response must be a model JSON object or run-messages array")
    text_messages = [
        item.get("content")
        for item in response
        if isinstance(item, Mapping)
        and item.get("type") == "text"
        and isinstance(item.get("content"), str)
    ]
    if not text_messages:
        raise ContractError("Multica run-messages response has no text output")
    return _parse_raw_model_output(text_messages[-1])


def audit_multica_tool_trace(
    raw_response: str,
    *,
    profile_id: str,
    task_id: str,
    issue_id: str,
    attachment_id: str,
) -> list[str]:
    """Reject model tool calls outside the frozen-input read boundary."""

    response = _coerce_raw_response(raw_response)
    if response is None:
        raise ContractError("Multica response file must be valid JSON")
    if isinstance(response, dict):
        return []
    if not isinstance(response, list):
        raise ContractError("Multica response must be a model JSON object or run-messages array")

    allowed_input_name = f"{profile_id.casefold()}-input.json"
    audited_commands: list[str] = []
    for index, message in enumerate(response):
        if not isinstance(message, Mapping):
            raise ContractError(f"Multica message {index} is not an object")
        message_task_id = message.get("task_id")
        if message_task_id is not None and message_task_id != task_id:
            raise ContractError(f"Multica message {index} belongs to another task")
        message_issue_id = message.get("issue_id")
        if message_issue_id is not None and message_issue_id != issue_id:
            raise ContractError(f"Multica message {index} belongs to another issue")
        if message.get("type") != "tool_use":
            continue
        if message.get("tool") != "exec_command":
            raise SecurityPolicyError(f"Unapproved Multica tool at message {index}")
        command = message.get("input", {}).get("command")
        if not isinstance(command, str):
            raise ContractError(f"Multica tool command missing at message {index}")
        try:
            outer = shlex.split(command)
        except ValueError as error:
            raise ContractError(f"Invalid shell command at message {index}") from error
        if len(outer) != 3 or outer[0] not in {"/bin/zsh", "/bin/bash"} or outer[1] != "-lc":
            raise SecurityPolicyError(f"Unapproved shell wrapper at message {index}")
        inner = outer[2]
        if any(token in inner for token in ("&&", "||", ";", "$(", "`")):
            raise SecurityPolicyError(f"Shell composition is forbidden at message {index}")
        try:
            tokens = shlex.split(inner)
        except ValueError as error:
            raise ContractError(f"Invalid inner shell command at message {index}") from error
        allowed = False
        if tokens[:3] == ["multica", "issue", "get"]:
            allowed = tokens in (
                ["multica", "issue", "get", issue_id],
                ["multica", "issue", "get", issue_id, "--output", "json"],
            )
        elif tokens in (
            ["multica", "attachment", "--help"],
            ["multica", "attachment", "download", "--help"],
        ):
            allowed = True
        elif tokens[:3] == ["multica", "attachment", "download"]:
            allowed = tokens in (
                ["multica", "attachment", "download", attachment_id],
                [
                    "multica",
                    "attachment",
                    "download",
                    attachment_id,
                    "--output-dir",
                    ".",
                ],
                [
                    "multica",
                    "attachment",
                    "download",
                    attachment_id,
                    "-o",
                    ".",
                ],
            )
        elif tokens and tokens[0] == "cat" and len(tokens) == 2:
            path = tokens[1].replace("\\", "/")
            allowed = path.endswith(f"/{allowed_input_name}") or path == allowed_input_name
            allowed = allowed or path.endswith(
                "/codex-home/skills/multica-working-on-issues/SKILL.md"
            )
        elif tokens and tokens[0] == "jq" and len(tokens) >= 3:
            input_path = tokens[-1].replace("\\", "/")
            jq_program = " ".join(tokens[1:-1])
            allowed = (
                (input_path.endswith(f"/{allowed_input_name}") or input_path == allowed_input_name)
                and not re.search(r"(?i)(?:\benv\b|\$ENV)", jq_program)
            )
        if not allowed:
            raise SecurityPolicyError(f"Unapproved Multica command at message {index}: {inner}")
        audited_commands.append(inner)
    return audited_commands


def _validate_evidence_collections(
    payload: Mapping[str, Any], collection_names: set[str]
) -> None:
    for collection_name in sorted(collection_names):
        collection = payload.get(collection_name)
        if not isinstance(collection, list):
            raise ContractError(f"{collection_name} must be a list")
        for index, item in enumerate(collection):
            if not isinstance(item, Mapping):
                raise ContractError(f"{collection_name}[{index}] must be an object")
            source_refs = item.get("source_refs")
            if not isinstance(source_refs, list) or not source_refs:
                raise ContractError(
                    f"{collection_name}[{index}].source_refs must be a non-empty list"
                )


def _validate_collection_item_fields(
    payload: Mapping[str, Any], field_requirements: Mapping[str, set[str]]
) -> None:
    for collection_name, required_fields in field_requirements.items():
        collection = payload.get(collection_name)
        if not isinstance(collection, list):
            raise ContractError(f"{collection_name} must be a list")
        for index, item in enumerate(collection):
            if not isinstance(item, Mapping):
                raise ContractError(f"{collection_name}[{index}] must be an object")
            effective_required = set(required_fields)
            if collection_name == "issues" and str(item.get("severity") or "") not in {
                "error",
                "blocking",
            }:
                effective_required -= HUMAN_FACING_ISSUE_FIELDS
            missing = sorted(effective_required - set(item))
            if missing:
                raise ContractError(
                    f"{collection_name}[{index}] is missing fields: {', '.join(missing)}"
                )


def _validate_profile_semantics(
    profile_id: str, bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    if profile_id == "A06":
        _validate_alignment_semantics(bundle, payload)
        return
    if profile_id == "A08":
        _validate_test_design_semantics(bundle, payload)
        return
    if profile_id == "A09":
        _validate_oracle_review_semantics(bundle, payload)
        return
    if profile_id == "A11":
        _validate_split_review_semantics(bundle, payload)
        return
    if profile_id == "A12":
        _validate_selection_advice_semantics(bundle, payload)
        return
    if profile_id in {"A14", "A15"}:
        _validate_automation_generation_semantics(profile_id, bundle, payload)
        return
    if profile_id in {"A18-BE", "A18-CT"}:
        _validate_automation_review_semantics(profile_id, bundle, payload)
        return
    if profile_id == "A22":
        _validate_test_data_plan_semantics(bundle, payload)
        return
    if profile_id != "A05":
        return
    allowed_inputs = bundle.get("allowed_inputs", {})
    backend_input = (
        allowed_inputs.get("backend_change_set", {})
        if isinstance(allowed_inputs, Mapping)
        else {}
    )
    change_set = backend_input.get("change_set", {}) if isinstance(backend_input, Mapping) else {}
    if not isinstance(change_set, Mapping):
        raise ContractError("A05 input has no deterministic ChangeSet")
    expected_id = str(change_set.get("change_set_id", ""))
    changed_files = change_set.get("changed_files", [])
    if not expected_id or not isinstance(changed_files, list):
        raise ContractError("A05 deterministic ChangeSet is incomplete")
    if payload.get("domain") != "backend":
        raise ContractError("A05 output domain must be backend")
    if payload.get("change_set_id") != expected_id:
        raise ContractError("A05 output change_set_id does not match its frozen input")
    if payload.get("changed_file_count") != len(changed_files):
        raise ContractError("A05 output changed_file_count does not match its frozen input")
    allowed_paths = {str(path) for path in changed_files}
    for index, fact in enumerate(payload.get("facts", [])):
        if fact.get("change_set_id") != expected_id:
            raise ContractError(f"facts[{index}].change_set_id does not match its frozen input")
        if str(fact.get("path", "")) not in allowed_paths:
            raise ContractError(f"facts[{index}].path is outside the frozen ChangeSet")


def _validate_alignment_semantics(
    bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    allowed_inputs = bundle.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError("A06 input has no approved upstream artifacts")
    requirements = allowed_inputs.get("requirement_analysis", {}).get("requirements", [])
    technical_facts = allowed_inputs.get("technical_analysis", {}).get("technical_facts", [])
    change_facts = allowed_inputs.get("backend_change_analysis", {}).get("facts", [])
    requirement_ids = {str(item.get("id")) for item in requirements}
    technical_ids = {str(item.get("id")) for item in technical_facts}
    change_ids = {str(item.get("id")) for item in change_facts}
    evidence_ids = requirement_ids | technical_ids | change_ids
    for collection_name in ("ambiguities", "needs_human"):
        evidence_ids.update(
            str(item.get("id"))
            for item in allowed_inputs.get("requirement_analysis", {}).get(
                collection_name, []
            )
        )
    evidence_ids.update(
        str(item.get("id"))
        for item in allowed_inputs.get("technical_analysis", {}).get(
            "blocking_items", []
        )
    )
    eligible_change_ids = {
        str(item.get("id"))
        for item in change_facts
        if item.get("eligible_for_business_alignment") is True
    }
    mapping_requirement_ids: list[str] = []
    allowed_statuses = {
        "aligned",
        "partially_aligned",
        "implementation_not_evidenced",
        "design_not_evidenced",
        "conflict",
        "needs_human",
    }
    for index, mapping in enumerate(payload.get("mappings", [])):
        requirement_id = str(mapping.get("requirement_id", ""))
        mapping_requirement_ids.append(requirement_id)
        if mapping.get("status") not in allowed_statuses:
            raise ContractError(f"mappings[{index}].status is invalid")
        if not set(map(str, mapping.get("technical_fact_ids", []))) <= technical_ids:
            raise ContractError(f"mappings[{index}] references an unknown technical fact")
        mapped_change_ids = set(map(str, mapping.get("change_fact_ids", [])))
        if not mapped_change_ids <= change_ids:
            raise ContractError(f"mappings[{index}] references an unknown change fact")
        if not mapped_change_ids <= eligible_change_ids:
            raise ContractError(f"mappings[{index}] uses non-business implementation evidence")
        mapping_refs = mapping.get("source_refs", [])
        if not all(isinstance(item, str) and item in evidence_ids for item in mapping_refs):
            raise ContractError(f"mappings[{index}] references unknown source evidence")
    if len(mapping_requirement_ids) != len(set(mapping_requirement_ids)):
        raise ContractError("A06 output maps a requirement more than once")
    if set(mapping_requirement_ids) != requirement_ids:
        raise ContractError("A06 output must map every frozen requirement exactly once")
    for index, finding in enumerate(payload.get("findings", [])):
        if not set(map(str, finding.get("requirement_ids", []))) <= requirement_ids:
            raise ContractError(f"findings[{index}] references an unknown requirement")
        if not set(map(str, finding.get("technical_fact_ids", []))) <= technical_ids:
            raise ContractError(f"findings[{index}] references an unknown technical fact")
        if not set(map(str, finding.get("implementation_ids", []))) <= change_ids:
            raise ContractError(f"findings[{index}] references an unknown change fact")
        finding_refs = finding.get("source_refs", [])
        if not all(isinstance(item, str) and item in evidence_ids for item in finding_refs):
            raise ContractError(f"findings[{index}] references unknown source evidence")


def _validate_test_design_semantics(
    bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    allowed_inputs = bundle.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError("A08 input has no approved upstream evidence")
    validated = allowed_inputs.get("validated_analysis", {})
    approved_scope = allowed_inputs.get("approved_scope", {})
    strategy = allowed_inputs.get("test_strategy", {})
    historical = allowed_inputs.get("historical_behavior_packet")
    if not all(isinstance(item, Mapping) for item in (validated, approved_scope, strategy)):
        raise ContractError("A08 approved inputs are invalid")
    if historical is not None:
        if not isinstance(historical, Mapping):
            raise ContractError("A08 historical behavior knowledge packet is invalid")
        validate_historical_behavior_packet(historical)

    requirements = validated.get("requirement_analysis", {}).get("requirements", [])
    requirement_ids = {str(item.get("id")) for item in requirements}
    required_layers = set(map(str, strategy.get("required_layers", [])))
    expected_risk = str(strategy.get("risk_level", ""))
    expected_priority = {
        "critical": "P0",
        "high": "P1",
        "medium": "P2",
        "low": "P3",
    }.get(expected_risk)
    if not requirement_ids or not required_layers or expected_priority is None:
        raise ContractError("A08 input requirements or deterministic strategy are incomplete")

    intents = payload.get("test_intents", [])
    cases = payload.get("parent_cases", [])
    intent_ids = [str(item.get("id", "")) for item in intents]
    case_ids = [str(item.get("id", "")) for item in cases]
    if not all(intent_ids) or len(intent_ids) != len(set(intent_ids)):
        raise ContractError("A08 test intent IDs must be non-empty and unique")
    if not all(case_ids) or len(case_ids) != len(set(case_ids)):
        raise ContractError("A08 parent Case IDs must be non-empty and unique")
    intent_id_set = set(intent_ids)
    case_id_set = set(case_ids)
    observed_layers: set[str] = set()
    for index, case in enumerate(cases):
        case_intents = set(map(str, case.get("intent_ids", [])))
        if not case_intents or not case_intents <= intent_id_set:
            raise ContractError(f"parent_cases[{index}] references an unknown test intent")
        case_layers = set(map(str, case.get("required_layers", [])))
        if not case_layers or not case_layers <= required_layers:
            raise ContractError(f"parent_cases[{index}] has an invalid required test layer")
        observed_layers.update(case_layers)
        if case.get("risk") != expected_risk or case.get("priority") != expected_priority:
            raise ContractError(f"parent_cases[{index}] does not preserve N24 risk")
        if not isinstance(case.get("test_data"), Mapping):
            raise ContractError(f"parent_cases[{index}].test_data must be an object")
        execution_policy = case.get("execution_policy")
        if not isinstance(execution_policy, Mapping):
            raise ContractError(f"parent_cases[{index}].execution_policy must be an object")
        allowed_modes = execution_policy.get("allowed_modes")
        if (
            not isinstance(allowed_modes, list)
            or not allowed_modes
            or not all(mode in {"automated", "manual"} for mode in allowed_modes)
        ):
            raise ContractError(
                f"parent_cases[{index}].execution_policy.allowed_modes is invalid"
            )
        expected_items = case.get("expected")
        if not isinstance(expected_items, list) or not expected_items:
            raise ContractError(f"parent_cases[{index}] has no expected assertions")
        for expected_index, expected in enumerate(expected_items):
            oracle = expected.get("oracle") if isinstance(expected, Mapping) else None
            if not isinstance(oracle, Mapping):
                raise ContractError(
                    f"parent_cases[{index}].expected[{expected_index}] has no executable Oracle"
                )
            missing_oracle_fields = [
                field
                for field in ("type", "observation_point", "matcher", "source_ref")
                if not isinstance(oracle.get(field), str) or not oracle.get(field)
            ]
            if missing_oracle_fields:
                raise ContractError(
                    f"parent_cases[{index}].expected[{expected_index}].oracle is missing "
                    + ", ".join(missing_oracle_fields)
                )
            if oracle["type"] not in {"deterministic", "human_review"}:
                raise ContractError(
                    f"parent_cases[{index}].expected[{expected_index}].oracle.type is invalid"
                )
            if oracle["type"] == "human_review" and "manual" not in allowed_modes:
                raise ContractError(
                    f"parent_cases[{index}] does not route its human Oracle to manual"
                )
    if observed_layers != required_layers:
        raise ContractError("A08 parent Cases do not cover every N24-required test layer")

    coverage = payload.get("coverage_matrix", [])
    covered_requirements: list[str] = []
    for index, item in enumerate(coverage):
        requirement_id = str(item.get("requirement_id", ""))
        covered_requirements.append(requirement_id)
        covered_cases = set(map(str, item.get("case_ids", [])))
        if not covered_cases or not covered_cases <= case_id_set:
            raise ContractError(f"coverage_matrix[{index}] references an unknown Case")
    if len(covered_requirements) != len(set(covered_requirements)):
        raise ContractError("A08 coverage_matrix maps a requirement more than once")
    if set(covered_requirements) != requirement_ids:
        raise ContractError("A08 must cover every frozen requirement exactly once")

    required_rule_ids = {
        str(item.get("id"))
        for item in approved_scope.get("test_rule_obligations", [])
        if isinstance(item, Mapping)
    }
    rule_coverage = payload.get("test_rule_coverage", [])
    covered_rules: list[str] = []
    for index, item in enumerate(rule_coverage):
        rule_id = str(item.get("rule_id", ""))
        covered_rules.append(rule_id)
        covered_cases = set(map(str, item.get("case_ids", [])))
        if not covered_cases or not covered_cases <= case_id_set:
            raise ContractError(f"test_rule_coverage[{index}] references an unknown Case")
    if len(covered_rules) != len(set(covered_rules)):
        raise ContractError("A08 test_rule_coverage maps a rule more than once")
    if set(covered_rules) != required_rule_ids or required_rule_ids != TEST_RULE_IDS:
        raise ContractError("A08 must cover every G01-approved test rule exactly once")
    if historical is not None:
        assert_historical_regression_coverage(payload, historical)

    if bundle.get("profile_version") in {"1.2.0", "1.2.1", "1.3.0"}:
        feedback = allowed_inputs.get("correction_feedback")
        resolutions = payload.get("correction_resolutions")
        if not isinstance(feedback, Mapping) or not isinstance(resolutions, list):
            raise ContractError("A08 correction output must include correction_resolutions")
        required_feedback_ids = {
            str(item.get("id"))
            for item in feedback.get("a09_issues", [])
            if isinstance(item, Mapping)
        }
        n04_groups = [
            item
            for item in feedback.get("n04_schema_issue_groups", [])
            if isinstance(item, Mapping)
        ]
        required_group_ids = {str(item.get("group_id") or "") for item in n04_groups}
        grouped_feedback_version = bool(n04_groups) and all(required_group_ids)
        required_issue_codes = {str(item.get("issue_code")) for item in n04_groups}
        resolved_feedback_id_list: list[str] = []
        resolved_group_id_list: list[str] = []
        resolved_issue_code_list: list[str] = []
        allowed_dispositions = {
            "fixed",
            "not_applicable",
            "rejected_conflict_with_frozen_evidence",
        }
        for index, resolution in enumerate(resolutions):
            if not isinstance(resolution, Mapping):
                raise ContractError(f"correction_resolutions[{index}] must be an object")
            feedback_id = str(resolution.get("feedback_id") or "")
            group_id = str(resolution.get("group_id") or "")
            issue_code = str(resolution.get("issue_code") or "")
            identifiers = [identifier for identifier in (feedback_id, group_id, issue_code) if identifier]
            if len(identifiers) != 1:
                raise ContractError(
                    f"correction_resolutions[{index}] must identify one feedback item"
                )
            if resolution.get("disposition") not in allowed_dispositions:
                raise ContractError(
                    f"correction_resolutions[{index}] has an invalid disposition"
                )
            if not isinstance(resolution.get("affected_case_ids"), list):
                raise ContractError(
                    f"correction_resolutions[{index}].affected_case_ids must be a list"
                )
            if not set(map(str, resolution["affected_case_ids"])) <= case_id_set:
                raise ContractError(
                    f"correction_resolutions[{index}] references an unknown Case"
                )
            if not isinstance(resolution.get("source_refs"), list) or not resolution.get(
                "source_refs"
            ):
                raise ContractError(
                    f"correction_resolutions[{index}].source_refs must be non-empty"
                )
            if not str(resolution.get("rationale", "")):
                raise ContractError(
                    f"correction_resolutions[{index}].rationale must be non-empty"
                )
            if feedback_id:
                resolved_feedback_id_list.append(feedback_id)
            elif group_id:
                resolved_group_id_list.append(group_id)
            else:
                resolved_issue_code_list.append(issue_code)
        if (
            len(resolved_feedback_id_list) != len(set(resolved_feedback_id_list))
            or set(resolved_feedback_id_list) != required_feedback_ids
        ):
            raise ContractError("A08 correction must resolve every A09 feedback item exactly once")
        if grouped_feedback_version:
            if resolved_issue_code_list or (
                len(resolved_group_id_list) != len(set(resolved_group_id_list))
                or set(resolved_group_id_list) != required_group_ids
            ):
                raise ContractError("A08 correction must resolve every N04 issue group")
        elif resolved_group_id_list or set(resolved_issue_code_list) != required_issue_codes:
            raise ContractError("A08 correction must resolve every legacy N04 issue code")


def _validate_oracle_review_semantics(
    bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    allowed_inputs = bundle.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError("A09 input has no approved A08 design")
    design = allowed_inputs.get("test_design_ir", {})
    rules = allowed_inputs.get("oracle_rule_library", {})
    evidence = allowed_inputs.get("frozen_evidence", {})
    if not all(isinstance(item, Mapping) for item in (design, rules, evidence)):
        raise ContractError("A09 inputs are invalid")

    cases = design.get("parent_cases", [])
    case_ids = {str(item.get("id")) for item in cases if isinstance(item, Mapping)}
    expected_ids = {
        (str(case.get("id")), str(expected.get("id")))
        for case in cases
        if isinstance(case, Mapping)
        for expected in case.get("expected", [])
        if isinstance(expected, Mapping)
    }
    requirements = (
        evidence.get("validated_analysis", {})
        .get("requirement_analysis", {})
        .get("requirements", [])
    )
    requirement_ids = {
        str(item.get("id")) for item in requirements if isinstance(item, Mapping)
    }
    obligations = evidence.get("approved_scope", {}).get(
        "test_rule_obligations", []
    )
    rule_ids = {str(item.get("id")) for item in obligations if isinstance(item, Mapping)}
    required_dimensions = set(map(str, rules.get("required_coverage_dimensions", [])))
    if not case_ids or not requirement_ids or rule_ids != TEST_RULE_IDS or not required_dimensions:
        raise ContractError("A09 frozen review scope is incomplete")

    issue_ids: list[str] = []
    blocking_count = 0
    allowed_routes = {"A08", "A07", "A06/G01", "human"}
    for index, issue in enumerate(payload.get("issues", [])):
        issue_id = str(issue.get("id", ""))
        issue_ids.append(issue_id)
        case_id = str(issue.get("case_id") or "")
        expected_id = str(issue.get("expected_id") or "")
        if case_id and case_id not in case_ids:
            raise ContractError(f"A09 issues[{index}] references an unknown Case")
        if expected_id and (case_id, expected_id) not in expected_ids:
            raise ContractError(f"A09 issues[{index}] references an unknown expected result")
        if issue.get("route_to") not in allowed_routes:
            raise ContractError(f"A09 issues[{index}] has an invalid route")
        if issue.get("severity") in {"error", "blocking"} and not str(
            issue.get("plain_summary") or ""
        ).strip():
            raise ContractError(
                f"A09 issues[{index}] requires a human-readable plain_summary"
            )
        if issue.get("severity") in {"error", "blocking"}:
            blocking_count += 1
    if not all(issue_ids) or len(issue_ids) != len(set(issue_ids)):
        raise ContractError("A09 issue IDs must be non-empty and unique")

    observed_dimensions: list[str] = []
    for index, item in enumerate(payload.get("coverage_dimensions", [])):
        dimension = str(item.get("dimension", ""))
        observed_dimensions.append(dimension)
        if item.get("status") not in {"covered", "partial", "missing", "not_applicable"}:
            raise ContractError(f"A09 coverage_dimensions[{index}] has an invalid status")
        if not set(map(str, item.get("case_ids", []))) <= case_ids:
            raise ContractError(f"A09 coverage_dimensions[{index}] references an unknown Case")
    if len(observed_dimensions) != len(set(observed_dimensions)):
        raise ContractError("A09 maps a coverage dimension more than once")
    if set(observed_dimensions) != required_dimensions:
        raise ContractError("A09 must review every required test-defense dimension")

    for collection_name, id_name, required_ids in (
        ("requirement_coverage", "requirement_id", requirement_ids),
        ("test_rule_coverage", "rule_id", rule_ids),
    ):
        observed: list[str] = []
        for index, item in enumerate(payload.get(collection_name, [])):
            observed_id = str(item.get(id_name, ""))
            observed.append(observed_id)
            if item.get("status") not in {"covered", "partial", "missing"}:
                raise ContractError(f"A09 {collection_name}[{index}] has an invalid status")
            if not set(map(str, item.get("case_ids", []))) <= case_ids:
                raise ContractError(
                    f"A09 {collection_name}[{index}] references an unknown Case"
                )
        if len(observed) != len(set(observed)) or set(observed) != required_ids:
            raise ContractError(f"A09 must review every {id_name} exactly once")

    if payload.get("evaluation_oracle_accessed") is not False:
        raise SecurityPolicyError("A09 must not access the evaluation Oracle Registry")
    if payload.get("code_coverage_reviewed") is not False:
        raise ContractError("A09 reviews test-design coverage, not code coverage")
    approved = payload.get("approved")
    if not isinstance(approved, bool) or approved != (blocking_count == 0):
        raise ContractError("A09 approval does not match its blocking issue count")
    if approved and payload.get("status") not in {
        ArtifactStatus.COMPLETED.value,
        ArtifactStatus.COMPLETED_WITH_GAPS.value,
    }:
        raise ContractError("A09 approved output has an invalid status")
    if not approved and payload.get("status") != ArtifactStatus.NEEDS_HUMAN.value:
        raise ContractError("A09 rejected output must be needs_human")


def _validate_split_review_semantics(
    bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    allowed_inputs = bundle.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError("A11 input has no compiled test cases")
    parents = allowed_inputs.get("parent_test_cases", [])
    children = allowed_inputs.get("compiled_child_cases", [])
    if not isinstance(parents, list) or not isinstance(children, list):
        raise ContractError("A11 parent/child case inputs are invalid")
    parent_ids = {str(item.get("id")) for item in parents if isinstance(item, Mapping)}
    parent_expected = {
        str(item.get("id")): {
            str(expected.get("id"))
            for expected in item.get("expected", [])
            if isinstance(expected, Mapping)
        }
        for item in parents
        if isinstance(item, Mapping)
    }
    child_ids = {str(item.get("id")) for item in children if isinstance(item, Mapping)}
    child_parents = {
        str(item.get("id")): str(item.get("parent_case_id", ""))
        for item in children
        if isinstance(item, Mapping)
    }
    child_expected = {
        str(item.get("id")): {
            str(expected.get("id"))
            for expected in item.get("expected", [])
            if isinstance(expected, Mapping)
        }
        for item in children
        if isinstance(item, Mapping)
    }
    if not parent_ids or not child_ids:
        raise ContractError("A11 review scope is empty")

    issue_ids: list[str] = []
    blocking_count = 0
    allowed_routes = {"N25", "N26", "human"}
    for index, issue in enumerate(payload.get("issues", [])):
        issue_id = str(issue.get("id", ""))
        issue_ids.append(issue_id)
        case_id = str(issue.get("case_id") or "")
        if case_id and case_id not in parent_ids | child_ids:
            raise ContractError(f"A11 issues[{index}] references an unknown Case")
        if issue.get("route_to") not in allowed_routes:
            raise ContractError(f"A11 issues[{index}] has an invalid route")
        if issue.get("severity") in {"error", "blocking"} and not str(
            issue.get("plain_summary") or ""
        ).strip():
            raise ContractError(
                f"A11 issues[{index}] requires a human-readable plain_summary"
            )
        if issue.get("severity") in {"error", "blocking"}:
            blocking_count += 1
    if not all(issue_ids) or len(issue_ids) != len(set(issue_ids)):
        raise ContractError("A11 issue IDs must be non-empty and unique")

    observed_parents: list[str] = []
    for index, item in enumerate(payload.get("parent_case_coverage", [])):
        parent_id = str(item.get("parent_case_id", ""))
        observed_parents.append(parent_id)
        if item.get("status") not in {"covered", "partial", "missing"}:
            raise ContractError(f"A11 parent_case_coverage[{index}] has an invalid status")
        covered = set(map(str, item.get("covered_child_ids", [])))
        if not covered <= child_ids:
            raise ContractError(
                f"A11 parent_case_coverage[{index}] references an unknown child Case"
            )
        for child_id in covered:
            if child_parents.get(child_id) != parent_id:
                raise ContractError(
                    f"A11 parent_case_coverage[{index}] child {child_id} has a different parent"
                )
            if not child_expected.get(child_id, set()) <= parent_expected.get(parent_id, set()):
                raise ContractError(
                    f"A11 parent_case_coverage[{index}] child {child_id} added or changed an Oracle"
                )
        covered_oracles = set().union(*(child_expected.get(child_id, set()) for child_id in covered))
        if covered_oracles != parent_expected.get(parent_id, set()):
            raise ContractError(
                f"A11 parent_case_coverage[{index}] children do not cover the parent Oracle set"
            )
    if len(observed_parents) != len(set(observed_parents)) or set(observed_parents) != parent_ids:
        raise ContractError("A11 must review every parent Case exactly once")

    coverage_by_parent = {
        str(item.get("parent_case_id")): str(item.get("status"))
        for item in payload.get("parent_case_coverage", [])
        if isinstance(item, Mapping)
    }
    issues_by_case = {
        str(issue.get("case_id") or "")
        for issue in payload.get("issues", [])
        if isinstance(issue, Mapping) and issue.get("route_to") == "N25"
    }
    has_global_n25_issue = any(
        isinstance(issue, Mapping)
        and issue.get("route_to") == "N25"
        and not issue.get("case_id")
        and issue.get("severity") in {"error", "blocking"}
        for issue in payload.get("issues", [])
    )
    for parent in parents:
        if not isinstance(parent, Mapping):
            continue
        parent_id = str(parent.get("id", ""))
        expected_layers = set(map(str, parent.get("required_layers", [])))
        split_children = [
            child for child in children
            if isinstance(child, Mapping)
            and str(child.get("parent_case_id", "")) == parent_id
        ]
        split_layers = {str(child.get("layer", "")) for child in split_children}
        responsibilities_unchanged = bool(split_children) and all(
            child.get("expected") == parent.get("expected") for child in split_children
        )
        if len(expected_layers) > 1 and len(split_layers) > 1 and responsibilities_unchanged:
            related_ids = {parent_id} | {str(child.get("id", "")) for child in split_children}
            if (
                coverage_by_parent.get(parent_id) not in {"partial", "missing"}
                or not (has_global_n25_issue or related_ids & issues_by_case)
            ):
                raise ContractError(
                    f"A11 parent {parent_id} has unscoped cross-layer responsibilities"
                )

    layers = {str(item.get("layer")) for item in children if isinstance(item, Mapping)}
    observed_layers: list[str] = []
    for index, item in enumerate(payload.get("layer_coverage", [])):
        layer = str(item.get("layer", ""))
        observed_layers.append(layer)
        if item.get("status") not in {"covered", "partial", "missing", "not_applicable"}:
            raise ContractError(f"A11 layer_coverage[{index}] has an invalid status")
        if not set(map(str, item.get("case_ids", []))) <= child_ids:
            raise ContractError(f"A11 layer_coverage[{index}] references an unknown Case")
    if len(observed_layers) != len(set(observed_layers)) or set(observed_layers) != layers:
        raise ContractError("A11 must review every compiled layer exactly once")

    if payload.get("evaluation_oracle_accessed") is not False:
        raise SecurityPolicyError("A11 must not access the evaluation Oracle Registry")
    approved = payload.get("approved")
    if not isinstance(approved, bool) or approved != (blocking_count == 0):
        raise ContractError("A11 approval does not match its blocking issue count")
    if approved and payload.get("status") not in {
        ArtifactStatus.COMPLETED.value,
        ArtifactStatus.COMPLETED_WITH_GAPS.value,
    }:
        raise ContractError("A11 approved output has an invalid status")
    if not approved and payload.get("status") != ArtifactStatus.NEEDS_HUMAN.value:
        raise ContractError("A11 rejected output must be needs_human")


def _validate_selection_advice_semantics(
    bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    allowed_inputs = bundle.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError("A12 input has no N26 unresolved items")
    unresolved = allowed_inputs.get("unresolved_items", [])
    case_index = allowed_inputs.get("compiled_case_index", {})
    selection_policy = allowed_inputs.get("selection_policy", {})
    if not isinstance(unresolved, list) or not unresolved:
        raise ContractError("A12 input has no unresolved selection items")
    if not isinstance(case_index, Mapping) or not case_index:
        raise ContractError("A12 input has no compiled case index")

    unresolved_ids = {
        str(item.get("id"))
        for item in unresolved
        if isinstance(item, Mapping) and item.get("id")
    }
    unresolved_keys = {
        (str(item.get("case_id")), str(item.get("advisory_topic")))
        for item in unresolved
        if isinstance(item, Mapping)
    }
    known_case_ids = set(map(str, case_index))
    advice = payload.get("advice_items")
    if not isinstance(advice, list) or not advice:
        raise ContractError("A12 output advice_items is empty")
    seen_ids: list[str] = []
    allowed_recommendations = {
        "expand_selection",
        "keep_must_run",
        "request_human",
    }
    for index, item in enumerate(advice):
        if not isinstance(item, Mapping):
            raise ContractError(f"A12 advice_items[{index}] must be an object")
        item_id = str(item.get("id", ""))
        seen_ids.append(item_id)
        recommendation = item.get("recommendation")
        if recommendation not in allowed_recommendations:
            raise ContractError(f"A12 advice_items[{index}] has an invalid recommendation")
        if item.get("unresolved_item_id"):
            target_ok = str(item.get("unresolved_item_id", "")) in unresolved_ids
        else:
            target_ok = (
                str(item.get("case_id", "")),
                str(item.get("advisory_topic", "")),
            ) in unresolved_keys
        if not target_ok:
            raise ContractError(
                f"A12 advice_items[{index}] references an unknown unresolved item"
            )
        if not isinstance(item.get("evidence"), list) or not item["evidence"]:
            raise ContractError(f"A12 advice_items[{index}] evidence must be non-empty")
        if not isinstance(item.get("source_refs"), list) or not item["source_refs"]:
            raise ContractError(f"A12 advice_items[{index}] source_refs must be non-empty")
        if not str(item.get("uncertainty", "")).strip():
            raise ContractError(f"A12 advice_items[{index}] uncertainty must be non-empty")
        suggested = set(map(str, item.get("suggested_case_ids", [])))
        if not suggested <= known_case_ids:
            raise ContractError(f"A12 advice_items[{index}] suggests an unknown Case")
        if recommendation == "request_human":
            target_case_id = str(item.get("case_id", ""))
            target_layer = (
                str(case_index.get(target_case_id, {}).get("layer", ""))
                if isinstance(case_index.get(target_case_id), Mapping)
                else ""
            )
            forced = [
                rule
                for rule in selection_policy.get("forced_selection", [])
                if isinstance(rule, Mapping)
                and rule.get("selection") == "must_run"
                and (
                    str(rule.get("scope", "")) == "all"
                    or target_case_id
                    in {str(cid) for cid in rule.get("case_ids", [])}
                    or target_layer in {str(layer) for layer in rule.get("layers", [])}
                )
            ]
            if forced:
                raise SecurityPolicyError(
                    "A12 cannot downgrade a policy-forced Case to human"
                )
    if not all(seen_ids) or len(seen_ids) != len(set(seen_ids)):
        raise ContractError("A12 advice item IDs must be non-empty and unique")
    if payload.get("evaluation_oracle_accessed") is not False:
        raise SecurityPolicyError("A12 must not access the evaluation Oracle Registry")


def _validate_automation_generation_semantics(
    profile_id: str, bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    allowed_inputs = bundle.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError(f"{profile_id} input has no frozen automation scope")
    cases = allowed_inputs.get("cases", [])
    if not isinstance(cases, list) or not cases or not all(
        isinstance(item, Mapping) for item in cases
    ):
        raise ContractError(f"{profile_id} input has no compiled Cases")
    frozen_case_ids = {str(item.get("id")) for item in cases}
    layer = allowed_inputs.get("layer", "")
    if not layer:
        raise ContractError(f"{profile_id} input layer is missing")
    if payload.get("schema_version") != "automation-generation/1.0":
        raise ContractError(f"{profile_id} output schema_version is invalid")

    rejected_case_ids: list[str] = []
    for index, item in enumerate(payload.get("rejected_cases", [])):
        if not isinstance(item, Mapping):
            raise ContractError(f"{profile_id} rejected_cases[{index}] must be an object")
        case_id = str(item.get("case_id", ""))
        rejected_case_ids.append(case_id)
        if case_id not in frozen_case_ids:
            raise ContractError(f"{profile_id} rejected_cases[{index}] references an unknown Case")
        if not str(item.get("reason_code", "")).strip():
            raise ContractError(f"{profile_id} rejected_cases[{index}] has no reason_code")
    if len(rejected_case_ids) != len(set(rejected_case_ids)):
        raise ContractError(f"{profile_id} rejected Case IDs must be unique")

    manifest = payload.get("manifest")
    candidates = payload.get("code_candidates", [])
    if manifest is None:
        if candidates or rejected_case_ids != sorted(frozen_case_ids):
            raise ContractError(
                f"{profile_id} not-applicable output must reject every frozen Case"
            )
        return
    if not isinstance(manifest, Mapping):
        raise ContractError(f"{profile_id} manifest must be an object")
    if not isinstance(candidates, list) or not all(
        isinstance(item, Mapping) for item in candidates
    ):
        raise ContractError(f"{profile_id} code_candidates must be a list of objects")
    if manifest.get("schema_version") != "automation-manifest/1.0":
        raise ContractError(f"{profile_id} manifest schema_version is invalid")
    if str(manifest.get("generator_profile", "")) != f"{profile_id}/1.0.0":
        raise ContractError(f"{profile_id} manifest generator_profile is invalid")
    manifest_layer = str(manifest.get("layer", ""))
    if manifest_layer and manifest_layer != layer:
        raise ContractError(f"{profile_id} manifest layer does not match its frozen scope")
    mapped_case_ids: list[str] = []
    for index, mapping in enumerate(manifest.get("case_mappings", [])):
        if not isinstance(mapping, Mapping):
            raise ContractError(f"{profile_id} case_mappings[{index}] must be an object")
        case_id = str(mapping.get("case_id", ""))
        mapped_case_ids.append(case_id)
        if case_id not in frozen_case_ids or case_id in set(rejected_case_ids):
            raise ContractError(
                f"{profile_id} case_mappings[{index}] maps a rejected or unknown Case"
            )
        if not isinstance(mapping.get("expected_ids"), list):
            raise ContractError(f"{profile_id} case_mappings[{index}] expected_ids is invalid")
    if len(mapped_case_ids) != len(set(mapped_case_ids)):
        raise ContractError(f"{profile_id} mapped Case IDs must be unique")

    candidate_files = manifest.get("candidate_files", [])
    if not isinstance(candidate_files, list) or not candidate_files:
        raise ContractError(f"{profile_id} manifest candidate_files is empty")
    # Agent 输出可能把路径写成 ``path`` 或 ``candidate_path``（与 case_mappings
    # 的键名混用）。这里做归一化，避免仅因键名差异把合法输出拒之门外；
    # 内容哈希仍以 ``content`` 现场计算为权威，杜绝伪造哈希。
    candidate_index: dict[str, Mapping[str, Any]] = {}
    for item in candidates:
        path = str(item.get("path") or item.get("candidate_path") or "").strip()
        if path:
            candidate_index[path] = item
    mapped_paths = {str(item.get("candidate_path")) for item in manifest["case_mappings"]}
    for index, file_item in enumerate(candidate_files):
        if not isinstance(file_item, Mapping):
            raise ContractError(f"{profile_id} candidate_files[{index}] must be an object")
        path = str(file_item.get("path") or file_item.get("candidate_path") or "").strip()
        if path not in candidate_index:
            raise ContractError(f"{profile_id} candidate_files[{index}] has no candidate code")
        candidate = candidate_index[path]
        content = candidate.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ContractError(
                f"{profile_id} candidate {path} must carry inline content"
            )
    if mapped_paths and not mapped_paths <= set(candidate_index):
        raise ContractError(f"{profile_id} case_mappings reference missing candidate files")
    expected_manifest_layers = {"backend": "A14", "contract": "A15"}.get(layer)
    if expected_manifest_layers and manifest.get("manifest_id") != (
        "manifest-a14-backend" if profile_id == "A14" else "manifest-a15-contract"
    ):
        raise ContractError(f"{profile_id} manifest_id is invalid")
    if manifest.get("permissions", {}).get("business_repository_write") is not False:
        raise SecurityPolicyError(f"{profile_id} manifest requests business repository writes")
    # ``execution`` / ``expected_artifacts`` 是 N05/N08 的确定性派生契约：Agent 若
    # 提供则必须与候选文件精确一致（防注入），缺失时由摄入归一化按候选派生回填。
    declared_paths = [
        str(file_item.get("path") or file_item.get("candidate_path") or "")
        for file_item in candidate_files
        if isinstance(file_item, Mapping)
    ]
    execution = manifest.get("execution")
    if execution is not None:
        if not isinstance(execution, Mapping):
            raise ContractError(f"{profile_id} manifest execution must be an object")
        if execution.get("command") != ["pytest", "-q", *declared_paths]:
            raise ContractError(
                f"{profile_id} manifest execution command must be derived from candidate paths"
            )
        timeout = execution.get("timeout_seconds")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ContractError(f"{profile_id} manifest execution timeout_seconds is invalid")
    expected_artifacts = manifest.get("expected_artifacts")
    if expected_artifacts is not None and (
        not isinstance(expected_artifacts, list)
        or not expected_artifacts
        or not all(
            isinstance(item, str) and item.strip() for item in expected_artifacts
        )
    ):
        raise ContractError(f"{profile_id} manifest expected_artifacts is invalid")
    if payload.get("evaluation_oracle_accessed") is not False:
        raise SecurityPolicyError(f"{profile_id} must not access the evaluation Oracle Registry")


def _validate_automation_review_semantics(
    profile_id: str, bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    allowed_inputs = bundle.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError(f"{profile_id} input has no generation to review")
    cases = allowed_inputs.get("cases", [])
    generation = allowed_inputs.get("generation", {})
    if not isinstance(cases, list) or not cases or not isinstance(generation, Mapping):
        raise ContractError(f"{profile_id} review inputs are incomplete")
    frozen_case_ids = {str(item.get("id")) for item in cases if isinstance(item, Mapping)}
    manifest = generation.get("manifest") if isinstance(generation, Mapping) else None
    candidates = generation.get("code_candidates", []) if isinstance(generation, Mapping) else []
    if payload.get("schema_version") != "automation-review/1.0":
        raise ContractError(f"{profile_id} output schema_version is invalid")
    if payload.get("generation_hash") != content_hash(generation):
        raise ContractError(f"{profile_id} generation_hash does not match its frozen input")
    if payload.get("manifest_hash") != content_hash(manifest):
        raise ContractError(f"{profile_id} manifest_hash does not match its frozen input")
    if not isinstance(manifest, Mapping):
        raise ContractError(f"{profile_id} has no manifest to review")
    candidate_index = {
        str(item.get("path")): str(item.get("content_hash", ""))
        for item in candidates
        if isinstance(item, Mapping)
    }
    candidate_hashes = payload.get("candidate_hashes")
    if not isinstance(candidate_hashes, Mapping) or candidate_hashes != candidate_index:
        raise ContractError(f"{profile_id} candidate_hashes do not match the frozen candidates")
    if payload.get("generator_hidden_reasoning_accessed") is not False:
        raise SecurityPolicyError(f"{profile_id} must not access generator hidden reasoning")
    if payload.get("evaluation_oracle_accessed") is not False:
        raise SecurityPolicyError(f"{profile_id} must not access the evaluation Oracle Registry")
    approved = payload.get("approved")
    if not isinstance(approved, bool):
        raise ContractError(f"{profile_id} approved must be a boolean")
    issue_ids: list[str] = []
    blocking_count = 0
    for index, issue in enumerate(payload.get("issues", [])):
        if not isinstance(issue, Mapping):
            raise ContractError(f"{profile_id} issues[{index}] must be an object")
        issue_id = str(issue.get("id", ""))
        issue_ids.append(issue_id)
        case_id = str(issue.get("case_id") or "")
        if case_id and case_id not in frozen_case_ids:
            raise ContractError(f"{profile_id} issues[{index}] references an unknown Case")
        if str(issue.get("route_to", "")) != profile_id:
            raise ContractError(f"{profile_id} issues[{index}] has an invalid route_to")
        if issue.get("severity") in {"error", "blocking"}:
            blocking_count += 1
    if not all(issue_ids) or len(issue_ids) != len(set(issue_ids)):
        raise ContractError(f"{profile_id} issue IDs must be non-empty and unique")
    if approved != (blocking_count == 0):
        raise ContractError(f"{profile_id} approval does not match its blocking issue count")
    if approved and payload.get("status") not in {
        ArtifactStatus.COMPLETED.value,
        ArtifactStatus.COMPLETED_WITH_GAPS.value,
    }:
        raise ContractError(f"{profile_id} approved output has an invalid status")
    if not approved and payload.get("status") != ArtifactStatus.NEEDS_HUMAN.value:
        raise ContractError(f"{profile_id} rejected output must be needs_human")


def _validate_test_data_plan_semantics(
    bundle: Mapping[str, Any], payload: Mapping[str, Any]
) -> None:
    allowed_inputs = bundle.get("allowed_inputs", {})
    if not isinstance(allowed_inputs, Mapping):
        raise ContractError("A22 input has no frozen data planning scope")
    cases = allowed_inputs.get("cases", [])
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("A22 input has no compiled Cases")
    frozen_case_ids = {str(item.get("id")) for item in cases}
    policy = allowed_inputs.get("test_data_policy", {})
    if not isinstance(policy, Mapping) or policy.get("schema_version") != "test-data-policy/1.0":
        raise ContractError("A22 input test-data policy is invalid")
    if payload.get("schema_version") != "test-data-plan/1.0":
        raise ContractError("A22 output schema_version is invalid")
    allowed_environments = {str(item) for item in policy.get("allowed_environments", [])}
    if str(payload.get("environment", "")) not in allowed_environments:
        raise SecurityPolicyError("A22 output targets a non-approved environment")
    namespace = str(payload.get("namespace", ""))
    if not re.fullmatch(r"qa-[a-z0-9][a-z0-9-]{5,80}", namespace):
        raise ContractError("A22 output namespace is invalid")

    paused_ids: list[str] = []
    for index, item in enumerate(payload.get("paused_cases", [])):
        if not isinstance(item, Mapping):
            raise ContractError(f"A22 paused_cases[{index}] must be an object")
        case_id = str(item.get("case_id", ""))
        paused_ids.append(case_id)
        if case_id not in frozen_case_ids:
            raise ContractError(f"A22 paused_cases[{index}] references an unknown Case")
    if len(paused_ids) != len(set(paused_ids)):
        raise ContractError("A22 paused Case IDs must be unique")

    planned_case_ids: list[str] = []
    for index, item in enumerate(payload.get("case_plans", [])):
        if not isinstance(item, Mapping):
            raise ContractError(f"A22 case_plans[{index}] must be an object")
        case_id = str(item.get("case_id", ""))
        planned_case_ids.append(case_id)
        if case_id not in frozen_case_ids:
            raise ContractError(f"A22 case_plans[{index}] references an unknown Case")
        if not isinstance(item.get("resources"), list):
            raise ContractError(f"A22 case_plans[{index}].resources must be a list")
        if item.get("requires_data_construction") is True and not item["resources"]:
            raise ContractError(
                f"A22 case_plans[{index}] requires construction without resources"
            )
    if len(planned_case_ids) != len(set(planned_case_ids)):
        raise ContractError("A22 planned Case IDs must be unique")
    if set(planned_case_ids) & set(paused_ids):
        raise ContractError("A22 cannot plan and pause the same Case")

    unresolved = payload.get("unresolved_requirements", [])
    if not isinstance(unresolved, list):
        raise ContractError("A22 unresolved_requirements must be a list")
    if unresolved and payload.get("status") != ArtifactStatus.NEEDS_HUMAN.value:
        raise ContractError("A22 unresolved requirements must route to needs_human")
    if not unresolved and payload.get("status") != ArtifactStatus.COMPLETED.value:
        raise ContractError("A22 complete plan must be completed")


def _normalize_automation_generation_payload(
    payload: dict[str, Any],
) -> None:
    """Backfill authoritative content hashes into an A14/A15 generation payload.

    A14/A15 Agents work under a read-only command allowlist and cannot reliably
    compute sha256 themselves, so the system computes ``content_hash`` from the
    inline ``content`` and writes it back into ``code_candidates[]`` and
    ``manifest.candidate_files[]``. Path keys are also canonicalized to ``path``.
    """

    manifest = payload.get("manifest")
    candidates = payload.get("code_candidates")
    if not isinstance(manifest, Mapping) or not isinstance(candidates, list):
        return
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        content = candidate.get("content")
        if isinstance(content, str) and content.strip():
            candidate["content_hash"] = content_hash(content)
        path = str(candidate.get("path") or candidate.get("candidate_path") or "").strip()
        if path:
            candidate["path"] = path
            candidate.pop("candidate_path", None)
    by_path = {
        str(candidate.get("path")): candidate
        for candidate in candidates
        if isinstance(candidate, Mapping) and str(candidate.get("path", "")).strip()
    }
    files = manifest.get("candidate_files")
    declared_paths: list[str] = []
    if isinstance(files, list):
        for file_item in files:
            if not isinstance(file_item, Mapping):
                continue
            path = str(file_item.get("path") or file_item.get("candidate_path") or "").strip()
            if not path:
                continue
            file_item["path"] = path
            file_item.pop("candidate_path", None)
            declared_paths.append(path)
            candidate = by_path.get(path)
            if isinstance(candidate, Mapping) and candidate.get("content_hash"):
                file_item["content_hash"] = candidate["content_hash"]
    # ``execution`` / ``expected_artifacts`` 由候选文件确定性派生：Agent 未声明时
    # 系统回填，保证 N05/N08 永远拿到完整执行契约；已声明时校验已确保精确一致。
    if declared_paths:
        execution = manifest.get("execution")
        if not isinstance(execution, Mapping):
            execution = {
                "command": ["pytest", "-q", *declared_paths],
                "timeout_seconds": 600,
            }
            manifest["execution"] = execution
        elif not execution.get("command"):
            execution["command"] = ["pytest", "-q", *declared_paths]
        if manifest.get("expected_artifacts") is None:
            manifest["expected_artifacts"] = ["junit_xml", "stdout", "stderr"]


def _normalize_automation_review_bindings(
    bundle: Mapping[str, Any],
    payload: dict[str, Any],
) -> None:
    """Backfill A18-BE/A18-CT review hash bindings from the frozen inputs.

    Review Agents cannot reliably compute sha256 under the read-only command
    allowlist; the system recomputes ``generation_hash`` / ``manifest_hash`` /
    ``candidate_hashes`` from ``allowed_inputs.generation`` and overwrites the
    agent's best-effort values before semantic validation.
    """

    allowed_inputs = bundle.get("allowed_inputs", {})
    generation = allowed_inputs.get("generation", {}) if isinstance(allowed_inputs, Mapping) else {}
    if not isinstance(generation, Mapping):
        return
    manifest = generation.get("manifest")
    payload["generation_hash"] = content_hash(generation)
    payload["manifest_hash"] = content_hash(manifest) if isinstance(manifest, Mapping) else ""
    candidate_hashes: dict[str, str] = {}
    for item in generation.get("code_candidates", []):
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("path") or item.get("candidate_path") or "").strip()
        content = item.get("content")
        if path and isinstance(content, str) and content.strip():
            candidate_hashes[path] = content_hash(content)
    payload["candidate_hashes"] = candidate_hashes


def ingest_multica_output(
    bundle_path: Path,
    raw_output: str,
    output_dir: Path,
    *,
    task_id: str,
    issue_id: str,
    attachment_id: str,
    model_provider: str,
    model_snapshot: str,
    prompt_version: str,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Validate and persist one model response as a provenance-bound Artifact Envelope."""

    security = security or SecurityPolicy()
    bundle = _read(bundle_path)
    security.assert_no_secret_values(bundle)
    profile_id = str(bundle.get("profile_id", ""))
    if profile_id not in PROFILE_OUTPUTS:
        raise ContractError(f"Unsupported Multica profile: {profile_id or '<missing>'}")
    expected_bundle_hash = str(bundle.get("bundle_hash", ""))
    unhashed_bundle = {key: value for key, value in bundle.items() if key != "bundle_hash"}
    if not expected_bundle_hash or expected_bundle_hash != content_hash(unhashed_bundle):
        raise ContractError("Multica input bundle_hash is invalid")

    integrity = bundle.get("integrity")
    if not isinstance(integrity, Mapping) or any(value is not False for value in integrity.values()):
        raise SecurityPolicyError("Multica input integrity flags must all be false")

    audited_commands = audit_multica_tool_trace(
        raw_output,
        profile_id=profile_id,
        task_id=task_id,
        issue_id=issue_id,
        attachment_id=attachment_id,
    )
    payload = extract_multica_model_output(raw_output)
    security.assert_no_secret_values(payload)
    _assert_no_forbidden_oracle_fields(payload)
    expected_contract = str(bundle.get("output_contract", ""))
    binding_fields = {
        "schema_version": expected_contract,
        "workflow_run_id": str(bundle.get("workflow_run_id", "")),
        "source_snapshot_id": str(bundle.get("source_snapshot_id", "")),
        "input_bundle_hash": expected_bundle_hash,
    }
    for field_name, expected in binding_fields.items():
        if payload.get(field_name) != expected:
            raise ContractError(
                f"Multica output {field_name} does not match its frozen input"
            )

    output_config = PROFILE_OUTPUTS[profile_id]
    missing = sorted(output_config["required_fields"] - set(payload))
    if missing:
        raise ContractError(f"Multica output is missing required fields: {', '.join(missing)}")
    _validate_evidence_collections(payload, output_config["evidence_collections"])
    _validate_collection_item_fields(payload, output_config["collection_item_fields"])
    if profile_id in {"A18-BE", "A18-CT"}:
        _normalize_automation_review_bindings(bundle, payload)
    _validate_profile_semantics(profile_id, bundle, payload)
    if profile_id in {"A14", "A15"}:
        _normalize_automation_generation_payload(payload)

    try:
        status = ArtifactStatus(str(payload.get("status", "")))
    except ValueError as error:
        raise ContractError("Multica output has an invalid or missing status") from error
    artifact = ArtifactEnvelope(
        workflow_run_id=binding_fields["workflow_run_id"],
        workflow_mode=str(bundle.get("workflow_mode", "")),
        artifact_id=output_config["artifact_id"],
        source_snapshot_id=binding_fields["source_snapshot_id"],
        producer=Producer(
            component_id=profile_id,
            runtime="multica",
            profile_version=str(bundle.get("profile_version", "")),
            model_provider=model_provider,
            model_snapshot=model_snapshot,
            prompt_version=prompt_version,
            inference_config_hash=content_hash(
                {"model_provider": model_provider, "model_snapshot": model_snapshot}
            ),
            tool_bundle_version=f"multica-task:{task_id}",
        ),
        payload=payload,
        status=status,
        evidence_refs=(
            EvidenceRef(
                source_type="multica_agent_input",
                source_id=profile_id,
                location=bundle_path.name,
                content_hash=expected_bundle_hash,
            ),
        ),
        facts=(
            {
                "type": "multica_tool_trace_audit",
                "result": "passed" if audited_commands else "not_available",
                "task_id": task_id,
                "issue_id": issue_id,
                "attachment_id": attachment_id,
                "commands": audited_commands,
            },
        ),
    )
    artifact_dict = artifact.to_dict()
    security.assert_no_secret_values(artifact_dict)
    ArtifactStore(output_dir).write_artifact(artifact)
    return artifact_dict


def fetch_multica_run_messages(
    workspace_id: str,
    task_id: str,
    output_path: Path,
    *,
    security: SecurityPolicy | None = None,
) -> list[dict[str, Any]]:
    """Fetch one task's auditable message stream without shell interpolation."""

    security = security or SecurityPolicy()
    completed = subprocess.run(
        [
            "multica",
            "issue",
            "run-messages",
            task_id,
            "--workspace-id",
            workspace_id,
            "--output",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Multica run-messages failed"
        raise RetryableAgentError(detail)
    try:
        messages = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ContractError("Multica run-messages returned invalid JSON") from error
    if not isinstance(messages, list):
        raise ContractError("Multica run-messages must return a JSON array")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ContractError(f"Multica message {index} is not an object")
        if message.get("task_id") != task_id:
            raise ContractError(f"Multica message {index} belongs to another task")
    security.assert_no_secret_values(messages)
    ArtifactStore(output_path.parent).write_json(output_path.name, messages)
    return messages
