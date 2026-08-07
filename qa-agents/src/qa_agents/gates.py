"""Deterministic inputs for human Gate decisions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .contracts import artifact_hash_from_mapping, content_hash
from .errors import ContractError, SecurityPolicyError
from .security import SecurityPolicy
from .storage import ArtifactStore


RETURN_DISPOSITION_TARGETS = {
    "return_to_a02": "A02",
    "return_to_a03": "A03",
    "return_to_a05": "A05",
    "return_to_a06": "A06",
}


def scope_gate_issues(
    requirement_analysis: Mapping[str, Any],
    technical_analysis: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for ambiguity in requirement_analysis.get("ambiguities", []):
        issues.append(
            {
                "issue_id": f"A02:{ambiguity.get('id', len(issues) + 1)}",
                "issue_code": ambiguity.get("issue_code", "requirement_ambiguity"),
                "source": "A02",
                "route_to": "A02",
                "severity": "high",
                "detail": dict(ambiguity),
            }
        )
    for item in technical_analysis.get("blocking_items", []):
        issues.append(
            {
                "issue_id": f"A03:{item.get('id', len(issues) + 1)}",
                "issue_code": item.get("issue_code", "testability_blocked"),
                "source": "A03",
                "route_to": "A03",
                "severity": "high",
                "detail": dict(item),
            }
        )
    for finding in alignment.get("findings", []):
        if finding.get("severity") in {"high", "critical"}:
            issues.append(
                {
                    "issue_id": f"A06:{finding.get('id', len(issues) + 1)}",
                    "issue_code": finding.get("type", "high_risk_alignment_conflict"),
                    "source": "A06",
                    "route_to": "A06",
                    "severity": finding.get("severity", "high"),
                    "detail": dict(finding),
                }
            )
    return issues


def _read_artifact(path: Path, expected_id: str, security: SecurityPolicy) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        artifact = json.load(file)
    if not isinstance(artifact, dict) or artifact.get("artifact_id") != expected_id:
        raise ContractError(f"Expected Artifact {expected_id}: {path}")
    security.assert_no_secret_values(artifact)
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError(f"Artifact hash mismatch: {expected_id}")
    return artifact


def prepare_scope_review_request(
    requirement_artifact_path: Path,
    technical_artifact_path: Path,
    alignment_artifact_path: Path,
    output_dir: Path,
    *,
    policy: Mapping[str, Any],
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Build a content-addressed G01 request from accepted A02/A03/A06 Artifacts."""

    security = security or SecurityPolicy()
    if not isinstance(policy, Mapping):
        raise ContractError("G01 review policy must be an object")
    if policy.get("temporary_policy") is True and policy.get(
        "production_release_authority"
    ) is not False:
        raise SecurityPolicyError(
            "Temporary G01 review policy cannot grant production release authority"
        )
    artifacts = [
        _read_artifact(requirement_artifact_path, "a02-requirement-analysis", security),
        _read_artifact(technical_artifact_path, "a03-technical-testability-analysis", security),
        _read_artifact(alignment_artifact_path, "a06-alignment-result", security),
    ]
    identities = {
        (
            str(item.get("workflow_run_id", "")),
            str(item.get("workflow_mode", "")),
            str(item.get("source_snapshot_id", "")),
        )
        for item in artifacts
    }
    if len(identities) != 1 or not all(next(iter(identities))):
        raise ContractError("G01 upstream Artifacts belong to different workflow runs")
    workflow_run_id, workflow_mode, source_snapshot_id = identities.pop()
    security.assert_no_secret_values(policy)
    issues = scope_gate_issues(
        artifacts[0]["payload"], artifacts[1]["payload"], artifacts[2]["payload"]
    )
    request = {
        "schema_version": "scope-review-request/1.1",
        "gate_id": "G01",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": source_snapshot_id,
        "status": "needs_human" if issues else "completed",
        "decision": "pending" if issues else "not_required",
        "issues": issues,
        "issue_count": len(issues),
        "upstream_artifacts": [
            {"artifact_id": item["artifact_id"], "artifact_hash": item["artifact_hash"]}
            for item in artifacts
        ],
        "review_policy": {
            "schema_version": policy.get("schema_version"),
            "policy_hash": content_hash(policy),
            "approval_mode": policy.get("approval_mode"),
            "policy_scope": policy.get("policy_scope"),
            "temporary_policy": policy.get("temporary_policy", False),
            "production_release_authority": policy.get(
                "production_release_authority", False
            ),
        },
        "decision_contract": "scope-review-decision/1.0",
    }
    security.assert_no_secret_values(request)
    request["request_hash"] = content_hash(request)
    store = ArtifactStore(output_dir)
    store.write_json("g01-review-request.json", request)
    return request


def validate_scope_review_decision(
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Validate a human G01 decision; this function never creates an approval."""

    security = security or SecurityPolicy()
    security.assert_no_secret_values(decision)
    unhashed_request = {key: value for key, value in request.items() if key != "request_hash"}
    if request.get("request_hash") != content_hash(unhashed_request):
        raise ContractError("G01 review request hash is invalid")
    policy_binding = request.get("review_policy")
    if not isinstance(policy_binding, Mapping) or policy_binding.get(
        "policy_hash"
    ) != content_hash(policy):
        raise ContractError("G01 review policy does not match the bound request policy")
    for field in ("gate_id", "workflow_run_id", "source_snapshot_id", "request_hash"):
        if decision.get(field) != request.get(field):
            raise ContractError(f"G01 decision {field} does not match its request")
    if decision.get("schema_version") != "scope-review-decision/1.0":
        raise ContractError("G01 decision schema_version is invalid")
    actor = decision.get("actor")
    if not isinstance(actor, Mapping) or actor.get("type") != "human":
        raise SecurityPolicyError("G01 decision must be made by a human actor")
    if not str(actor.get("id", "")):
        raise ContractError("G01 decision actor.id is required")
    if actor.get("role") not in set(policy.get("allowed_roles", [])):
        raise SecurityPolicyError("G01 decision actor role is not authorized")
    try:
        decided_at = datetime.fromisoformat(str(decision.get("decided_at", "")))
    except ValueError as error:
        raise ContractError("G01 decision decided_at is invalid") from error
    if decided_at.tzinfo is None:
        raise ContractError("G01 decision decided_at must include a timezone")
    decision_value = decision.get("decision")
    if decision_value not in {"approved", "request_changes", "rejected"}:
        raise ContractError("G01 decision value is invalid")
    resolutions = decision.get("resolutions")
    if not isinstance(resolutions, list):
        raise ContractError("G01 decision resolutions must be a list")
    resolution_ids = [str(item.get("issue_id", "")) for item in resolutions if isinstance(item, Mapping)]
    if len(resolution_ids) != len(resolutions) or len(resolution_ids) != len(set(resolution_ids)):
        raise ContractError("G01 decision contains invalid or duplicate resolution IDs")
    request_issue_ids = {str(item.get("issue_id", "")) for item in request.get("issues", [])}
    if not set(resolution_ids) <= request_issue_ids:
        raise ContractError("G01 decision references an unknown issue")
    allowed_dispositions = set(policy.get("allowed_dispositions", []))
    allowed_roles = set(policy.get("allowed_roles", []))
    request_issues = {
        str(item.get("issue_id", "")): item for item in request.get("issues", [])
    }
    required_roles_by_source = policy.get("required_roles_by_source", {})
    for index, resolution in enumerate(resolutions):
        if resolution.get("disposition") not in allowed_dispositions:
            raise ContractError(f"G01 resolution {index} has an invalid disposition")
        if not str(resolution.get("rationale", "")).strip() or not str(
            resolution.get("owner", "")
        ).strip():
            raise ContractError(f"G01 resolution {index} requires rationale and owner")
        approvals = resolution.get("approvals", [])
        if not isinstance(approvals, list):
            raise ContractError(f"G01 resolution {index} approvals must be a list")
        approval_roles: set[str] = set()
        approval_identities: set[tuple[str, str]] = set()
        for approval in approvals:
            if not isinstance(approval, Mapping) or approval.get("type") != "human":
                raise SecurityPolicyError(f"G01 resolution {index} has a non-human approval")
            identity = (str(approval.get("id", "")), str(approval.get("role", "")))
            if not all(identity) or identity in approval_identities:
                raise ContractError(f"G01 resolution {index} has an invalid approval identity")
            if identity[1] not in allowed_roles:
                raise SecurityPolicyError(f"G01 resolution {index} has an unauthorized role")
            approval_identities.add(identity)
            approval_roles.add(identity[1])
        if decision_value == "approved":
            issue_source = str(request_issues[resolution["issue_id"]].get("source", ""))
            required_roles = set(required_roles_by_source.get(issue_source, []))
            if not required_roles <= approval_roles:
                missing_roles = ", ".join(sorted(required_roles - approval_roles))
                raise SecurityPolicyError(
                    f"G01 resolution {index} is missing required role approvals: {missing_roles}"
                )
    if decision_value == "approved":
        for field in policy.get("required_approval_fields", []):
            value = decision.get(field)
            if value is None or value == "" or value == [] or value == {}:
                raise ContractError(f"G01 approval requires decision field: {field}")
        if set(resolution_ids) != request_issue_ids:
            raise ContractError("G01 approval must resolve every review issue")
        if any(item.get("disposition") not in {"confirmed", "resolved_upstream"} for item in resolutions):
            raise ContractError("G01 approval contains an unresolved disposition")
    else:
        if not str(decision.get("reason", "")).strip():
            raise ContractError("Non-approved G01 decisions require a reason")
        if decision_value == "request_changes" and not any(
            item.get("disposition") in RETURN_DISPOSITION_TARGETS for item in resolutions
        ):
            raise ContractError("G01 request_changes requires at least one upstream return route")

    normalized = dict(decision)
    normalized["decision_hash"] = content_hash(decision)
    return normalized


def validate_recorded_scope_review_decision(
    request: Mapping[str, Any],
    recorded_decision: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    raw_decision = {
        key: value for key, value in recorded_decision.items() if key != "decision_hash"
    }
    if recorded_decision.get("decision_hash") != content_hash(raw_decision):
        raise ContractError("Recorded G01 decision hash is invalid")
    return validate_scope_review_decision(request, raw_decision, policy)


def scope_review_decision_template(request: Mapping[str, Any]) -> dict[str, Any]:
    """Create an intentionally invalid blank form; it cannot be mistaken for approval."""

    return {
        "schema_version": "scope-review-decision/1.0",
        "gate_id": "G01",
        "workflow_run_id": request.get("workflow_run_id"),
        "source_snapshot_id": request.get("source_snapshot_id"),
        "request_hash": request.get("request_hash"),
        "decision": "",
        "decided_at": "",
        "actor": {"type": "human", "id": "", "role": ""},
        "reason": "",
        "resolutions": [
            {
                "issue_id": item.get("issue_id"),
                "disposition": "",
                "rationale": "",
                "owner": "",
                "approvals": [],
            }
            for item in request.get("issues", [])
        ],
    }


def build_scope_review_outcome(
    request: Mapping[str, Any],
    recorded_decision: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile a validated G01 decision into an explicit orchestration action."""

    security = security or SecurityPolicy()
    decision = validate_recorded_scope_review_decision(request, recorded_decision, policy)
    decision_value = str(decision["decision"])
    issues = {
        str(item.get("issue_id", "")): item
        for item in request.get("issues", [])
        if isinstance(item, Mapping)
    }
    return_routes = []
    for resolution in decision.get("resolutions", []):
        target = RETURN_DISPOSITION_TARGETS.get(str(resolution.get("disposition", "")))
        if not target:
            continue
        issue = issues[str(resolution["issue_id"])]
        return_routes.append(
            {
                "issue_id": resolution["issue_id"],
                "issue_code": issue.get("issue_code"),
                "source": issue.get("source"),
                "target_node": target,
                "owner": resolution["owner"],
                "rationale": resolution["rationale"],
            }
        )

    if decision_value == "approved":
        action = "continue"
        status = "completed"
        next_node = "N24"
        invalidation = {"roots": [], "include_all_descendants": False}
        resume_at = None
    elif decision_value == "request_changes":
        action = "return_upstream"
        status = "blocked_input"
        next_node = None
        invalidation = {"roots": ["A06"], "include_all_descendants": True}
        resume_at = "A06"
    else:
        action = "terminate"
        status = "cancelled"
        next_node = None
        return_routes = []
        invalidation = {"roots": ["A06"], "include_all_descendants": True}
        resume_at = None

    outcome = {
        "schema_version": "scope-review-outcome/1.0",
        "gate_id": "G01",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "decision_hash": decision["decision_hash"],
        "decision": decision_value,
        "review_policy": dict(request["review_policy"]),
        "status": status,
        "action": action,
        "next_node": next_node,
        "return_routes": return_routes,
        "resume_at": resume_at,
        "invalidation": invalidation,
    }
    security.assert_no_secret_values(outcome)
    outcome["outcome_hash"] = content_hash(outcome)
    return outcome


def record_scope_review_decision(
    request_path: Path,
    decision_path: Path,
    policy_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    with request_path.open(encoding="utf-8") as file:
        request = json.load(file)
    with decision_path.open(encoding="utf-8") as file:
        decision = json.load(file)
    with policy_path.open(encoding="utf-8") as file:
        policy = json.load(file)
    normalized = validate_scope_review_decision(request, decision, policy)
    store = ArtifactStore(output_dir)
    store.write_json("g01-review-decision.json", normalized)
    store.write_json(
        "g01-review-outcome.json",
        build_scope_review_outcome(request, normalized, policy),
    )
    return normalized
