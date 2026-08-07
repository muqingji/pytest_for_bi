"""N24 deterministic risk and required-test-layer policy engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
)
from .errors import ContractError
from .gates import validate_recorded_scope_review_decision
from .security import SecurityPolicy
from .storage import ArtifactStore


class RiskPolicyEngine:
    def __init__(self, policy: Mapping[str, Any]) -> None:
        self.policy = policy

    @classmethod
    def from_file(cls, path: Path) -> "RiskPolicyEngine":
        with path.open(encoding="utf-8") as file:
            return cls(json.load(file))

    def evaluate(
        self,
        workflow_input: Mapping[str, Any],
        change_set: Mapping[str, Any],
        alignment: Mapping[str, Any],
        advice: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        score = 0
        reasons: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []

        severities = [str(item.get("severity", "")) for item in alignment.get("findings", [])]
        high_count = severities.count("high") + severities.count("critical")
        medium_count = severities.count("medium")
        if high_count:
            delta = high_count * int(self.policy["high_severity_finding_score"])
            score += delta
            reasons.append({"rule_id": "high_findings", "score": delta})
        if medium_count:
            delta = medium_count * int(self.policy["medium_severity_finding_score"])
            score += delta
            reasons.append({"rule_id": "medium_findings", "score": delta})

        searchable = " ".join(
            [str(workflow_input.get("title", "")), *map(str, change_set.get("changed_files", []))]
        ).lower()
        matched_keywords = [
            keyword for keyword in self.policy["high_risk_keywords"] if keyword.lower() in searchable
        ]
        if matched_keywords:
            keyword_score = int(self.policy["high_risk_keyword_score"])
            score += keyword_score
            reasons.append(
                {
                    "rule_id": "high_risk_keyword",
                    "score": keyword_score,
                    "matches": matched_keywords,
                }
            )

        files_changed = int(change_set.get("summary", {}).get("files_changed", 0) or 0)
        if files_changed >= int(self.policy["large_change_file_threshold"]):
            score += 3
            reasons.append({"rule_id": "large_change", "score": 3, "files": files_changed})

        applicability = workflow_input.get("component_applicability", {})
        required_layers = [
            layer
            for component, layer in self.policy["mandatory_layers"].items()
            if applicability.get(component, {}).get("status") == "applicable"
        ]
        if not required_layers:
            unresolved.append(
                {
                    "issue_code": "risk_layers_unknown",
                    "message": "No applicable test layer can be determined",
                }
            )

        required_non_functional: list[str] = []
        if any(keyword.lower() in searchable for keyword in self.policy["security_keywords"]):
            required_non_functional.append("security")
        if any(keyword.lower() in searchable for keyword in self.policy["data_keywords"]):
            required_non_functional.append("data_consistency")

        if advice:
            advised_layers = advice.get("suggested_layers", [])
            if isinstance(advised_layers, Sequence) and not isinstance(advised_layers, str):
                allowed_layers = set(self.policy["mandatory_layers"].values())
                required_layers.extend(
                    layer for layer in advised_layers if layer in allowed_layers
                )

        if score >= int(self.policy["critical_risk_score"]):
            level = "critical"
        elif score >= int(self.policy["high_risk_score"]):
            level = "high"
        elif score >= int(self.policy["medium_risk_score"]):
            level = "medium"
        else:
            level = "low"

        return {
            "schema_version": "test-strategy/1.0",
            "risk_level": level,
            "risk_score": score,
            "reasons": reasons,
            "required_layers": sorted(set(required_layers)),
            "required_non_functional": sorted(set(required_non_functional)),
            "human_gates": {
                "test_case_ir_review": "required",
                "automation_review": "required" if level in {"high", "critical"} else "policy",
            },
            "unresolved_items": unresolved,
            "policy_version": self.policy["schema_version"],
        }


def run_risk_strategy_after_g01(
    workflow_input: Mapping[str, Any],
    change_set: Mapping[str, Any],
    alignment_artifact: Mapping[str, Any],
    review_request: Mapping[str, Any],
    recorded_decision: Mapping[str, Any],
    risk_policy: Mapping[str, Any],
    g01_policy: Mapping[str, Any],
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Run deterministic N24 only after a current, fully approved G01 decision."""

    security = security or SecurityPolicy()
    security.validate_workflow_input(workflow_input)
    if alignment_artifact.get("artifact_id") != "a06-alignment-result":
        raise ContractError("N24 requires the accepted A06 alignment Artifact")
    if alignment_artifact.get("artifact_hash") != artifact_hash_from_mapping(alignment_artifact):
        raise ContractError("N24 A06 Artifact hash is invalid")
    if review_request.get("workflow_run_id") != alignment_artifact.get("workflow_run_id"):
        raise ContractError("N24 G01 request belongs to another workflow run")
    if review_request.get("source_snapshot_id") != alignment_artifact.get("source_snapshot_id"):
        raise ContractError("N24 G01 request belongs to another source snapshot")
    if review_request.get("workflow_mode") != alignment_artifact.get("workflow_mode"):
        raise ContractError("N24 G01 request belongs to another workflow mode")
    if workflow_input.get("workflow_mode") != alignment_artifact.get("workflow_mode"):
        raise ContractError("N24 workflow input does not match the accepted A06 workflow mode")
    bound_alignment = [
        item
        for item in review_request.get("upstream_artifacts", [])
        if isinstance(item, Mapping) and item.get("artifact_id") == "a06-alignment-result"
    ]
    if len(bound_alignment) != 1 or bound_alignment[0].get("artifact_hash") != alignment_artifact.get(
        "artifact_hash"
    ):
        raise ContractError("N24 G01 request does not bind the current A06 Artifact hash")
    decision = validate_recorded_scope_review_decision(
        review_request, recorded_decision, g01_policy
    )
    if decision.get("decision") != "approved":
        raise ContractError("N24 is blocked until G01 is approved")

    alignment_payload = alignment_artifact.get("payload")
    if not isinstance(alignment_payload, Mapping):
        raise ContractError("N24 A06 payload is invalid")
    strategy = RiskPolicyEngine(risk_policy).evaluate(
        workflow_input, change_set, alignment_payload
    )
    status = (
        ArtifactStatus.NEEDS_HUMAN
        if strategy.get("unresolved_items")
        else ArtifactStatus.COMPLETED
    )
    artifact = ArtifactEnvelope(
        workflow_run_id=str(alignment_artifact["workflow_run_id"]),
        workflow_mode=str(alignment_artifact["workflow_mode"]),
        artifact_id="n24-test-strategy",
        source_snapshot_id=str(alignment_artifact["source_snapshot_id"]),
        producer=Producer(
            component_id="N24",
            runtime="qa-agents-deterministic",
            profile_version=str(risk_policy.get("schema_version", "")),
            tool_bundle_version="g01-approved-risk-policy",
        ),
        payload=strategy,
        status=status,
        evidence_refs=(
            EvidenceRef(
                "artifact",
                "a06-alignment-result",
                "payload",
                str(alignment_artifact["artifact_hash"]),
            ),
            EvidenceRef(
                "human_gate_decision",
                "G01",
                "g01-review-decision.json",
                str(recorded_decision["decision_hash"]),
            ),
        ),
        facts=(
            {
                "gate_id": "G01",
                "request_hash": review_request.get("request_hash"),
                "decision_hash": recorded_decision.get("decision_hash"),
                "actor": decision.get("actor"),
                "review_policy": review_request.get("review_policy"),
            },
        ),
    )
    ArtifactStore(output_dir).write_artifact(artifact)
    return artifact.to_dict()
