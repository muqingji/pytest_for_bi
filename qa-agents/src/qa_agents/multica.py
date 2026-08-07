"""Deterministic adapters between frozen QA artifacts and Multica tasks."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any, Mapping

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
from .security import SecurityPolicy
from .storage import ArtifactStore


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
) -> dict[str, Any]:
    artifact = _read(path)
    security.assert_no_secret_values(artifact)
    if artifact.get("artifact_id") != expected_id:
        raise ContractError(f"Expected Artifact {expected_id}: {path}")
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError(f"Artifact hash mismatch: {expected_id}")
    if artifact.get("status") not in {
        ArtifactStatus.COMPLETED.value,
        ArtifactStatus.COMPLETED_WITH_GAPS.value,
        ArtifactStatus.NEEDS_HUMAN.value,
    }:
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
    if not isinstance(test_rules, Mapping):
        raise ContractError("A08 requires structured G01 test_rules")
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


def prepare_multica_test_design_correction_input(
    previous_test_design_artifact_path: Path,
    previous_test_design_bundle_path: Path,
    oracle_review_artifact_path: Path,
    n04_artifact_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Build a hash-bound A08 correction input after an N04 route back to A08."""

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

    n04_payload = n04["payload"]
    if (
        n04_payload.get("valid") is not False
        or n04_payload.get("next_node") != "A08"
        or n04_payload.get("g02_status") != "not_started"
    ):
        raise ContractError("A08 correction requires an N04 route to A08 before G02")
    if n04_payload.get("test_design_artifact_hash") != design["artifact_hash"]:
        raise ContractError("A08 correction N04 does not bind the previous A08 Artifact")
    if n04_payload.get("oracle_review_artifact_hash") != review["artifact_hash"]:
        raise ContractError("A08 correction N04 does not bind the A09 review Artifact")
    attempt = n04_payload.get("correction_attempt")
    max_attempts = n04_payload.get("max_correction_attempts")
    if not isinstance(attempt, int) or not isinstance(max_attempts, int):
        raise ContractError("A08 correction N04 retry budget is invalid")
    if attempt >= max_attempts:
        raise ContractError("A08 correction retry budget is exhausted")

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
    correction_feedback = {
        "schema_version": "test-design-correction/1.1",
        "correction_attempt": attempt,
        "max_correction_attempts": max_attempts,
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
    allowed_inputs = {
        key: previous_inputs[key]
        for key in (
            "validated_analysis",
            "approved_scope",
            "test_strategy",
            "case_provider_draft",
        )
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
    bundle = {
        "schema_version": "multica-agent-input/1.0",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "profile_id": "A08",
        "profile_version": "1.2.1",
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
        for key in ("validated_analysis", "approved_scope", "test_strategy")
        if key in a08_inputs
    }
    if set(frozen_evidence) != {
        "validated_analysis",
        "approved_scope",
        "test_strategy",
    }:
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
        raise ContractError(
            "Multica model output must be one raw JSON object without Markdown fences"
        ) from error
    if not isinstance(value, dict):
        raise ContractError("Multica model output must be a JSON object")
    return value


def extract_multica_model_output(raw_response: str) -> dict[str, Any]:
    """Extract the final pure-JSON text message without parsing an aggregated task log."""

    try:
        response = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise ContractError("Multica response file must be valid JSON") from error
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

    try:
        response = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise ContractError("Multica response file must be valid JSON") from error
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
            missing = sorted(required_fields - set(item))
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
    if not all(isinstance(item, Mapping) for item in (validated, approved_scope, strategy)):
        raise ContractError("A08 approved inputs are invalid")

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

    if bundle.get("profile_version") in {"1.2.0", "1.2.1"}:
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
    _validate_profile_semantics(profile_id, bundle, payload)

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
