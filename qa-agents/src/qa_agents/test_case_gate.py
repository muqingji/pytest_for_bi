"""Deterministic N04 validation and feedback routing for reviewed Test Case IR."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from .errors import ContractError
from .security import SecurityPolicy
from .storage import ArtifactStore
from .validation import validate_test_case_ir


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"N04 cannot read valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"N04 input must be a JSON object: {path}")
    return value


def _verified_artifact(path: Path, expected_id: str) -> dict[str, Any]:
    artifact = _read_object(path)
    if artifact.get("artifact_id") != expected_id:
        raise ContractError(f"N04 expected {expected_id}: {path}")
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError(f"N04 Artifact hash mismatch: {expected_id}")
    if not isinstance(artifact.get("payload"), Mapping):
        raise ContractError(f"N04 Artifact payload is invalid: {expected_id}")
    return artifact


def _recommendation(issue_code: str) -> str:
    recommendations = {
        "invalid_test_data_type": "将 test_data 改为结构化对象，并保留数据集和变体字段。",
        "missing_execution_modes": "在 execution_policy.allowed_modes 中声明 automated 或 manual。",
        "oracle_required_field": "补齐 Oracle 的 type、observation_point、matcher 和单值 source_ref。",
        "manual_oracle_not_routed": "将人工 Oracle 的 allowed_modes 路由为 manual。",
    }
    return recommendations.get(issue_code, "按正式 Test Case IR 契约定向修正后重新运行 A09/N04。")


def _n04_issues(cases: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    case_sources = {
        str(case.get("id")): list(case.get("source_refs", []))
        for case in cases
        if isinstance(case, Mapping)
    }
    result: list[dict[str, Any]] = []
    for index, issue in enumerate(validate_test_case_ir(cases), 1):
        value = issue.to_dict()
        value.update(
            {
                "id": f"N04-{index:04d}",
                "category": "schema"
                if issue.issue_code
                in {
                    "case_required_field",
                    "duplicate_case_id",
                    "duplicate_expected_id",
                    "invalid_test_data_type",
                    "invalid_execution_policy_type",
                    "missing_execution_modes",
                }
                else "oracle",
                "source_refs": case_sources.get(issue.case_id or "", []),
                "recommendation": _recommendation(issue.issue_code),
                "origin": "N04",
            }
        )
        result.append(value)
    return result


def run_n04_after_a09(
    test_design_artifact_path: Path,
    oracle_review_artifact_path: Path,
    oracle_review_bundle_path: Path,
    output_dir: Path,
    *,
    correction_attempt: int = 1,
    max_correction_attempts: int = 2,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Validate A08 plus A09 and route failures without redesigning any Case."""

    security = security or SecurityPolicy()
    design = _verified_artifact(test_design_artifact_path, "a08-test-design-ir")
    review = _verified_artifact(oracle_review_artifact_path, "a09-oracle-coverage-review")
    review_bundle = _read_object(oracle_review_bundle_path)
    for value in (design, review, review_bundle):
        security.assert_no_secret_values(value)

    identities = {
        (
            str(artifact.get("workflow_run_id", "")),
            str(artifact.get("workflow_mode", "")),
            str(artifact.get("source_snapshot_id", "")),
        )
        for artifact in (design, review)
    }
    if len(identities) != 1 or not all(next(iter(identities))):
        raise ContractError("N04 A08 and A09 Artifacts belong to different runs")
    workflow_run_id, workflow_mode, snapshot_id = identities.pop()

    expected_bundle_hash = str(review_bundle.get("bundle_hash", ""))
    unhashed_bundle = {
        key: value for key, value in review_bundle.items() if key != "bundle_hash"
    }
    if (
        review_bundle.get("profile_id") != "A09"
        or not expected_bundle_hash
        or expected_bundle_hash != content_hash(unhashed_bundle)
    ):
        raise ContractError("N04 A09 input bundle is invalid")
    if review["payload"].get("input_bundle_hash") != expected_bundle_hash:
        raise ContractError("N04 A09 Artifact does not bind its input bundle")
    upstream = {
        str(item.get("artifact_id")): str(item.get("artifact_hash"))
        for item in review_bundle.get("upstream_artifacts", [])
        if isinstance(item, Mapping)
    }
    if upstream.get("a08-test-design-ir") != design["artifact_hash"]:
        raise ContractError("N04 A09 review does not bind the current A08 Artifact")

    cases = design["payload"].get("parent_cases")
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N04 A08 parent_cases are invalid")
    issues = _n04_issues(cases)
    for item in review["payload"].get("issues", []):
        if not isinstance(item, Mapping):
            raise ContractError("N04 A09 issue is invalid")
        issues.append({**dict(item), "origin": "A09"})

    blocking_issues = [
        item for item in issues if item.get("severity", "error") in {"error", "blocking"}
    ]
    routes = Counter(str(item.get("route_to", "A08")) for item in blocking_issues)
    valid = not blocking_issues and review["payload"].get("approved") is True
    if valid:
        next_node = "G02"
        reason_code = "test_case_ir_valid"
    elif correction_attempt >= max_correction_attempts:
        next_node = "human"
        reason_code = "test_case_ir_correction_budget_exhausted"
    else:
        route_order = ("A06/G01", "A07", "A08", "human")
        next_node = next((route for route in route_order if routes[route]), "A08")
        reason_code = "test_case_ir_requires_correction"

    payload = {
        "schema_version": "test-case-ir-validation/1.0",
        "valid": valid,
        "test_design_artifact_id": design["artifact_id"],
        "test_design_artifact_hash": design["artifact_hash"],
        "oracle_review_artifact_id": review["artifact_id"],
        "oracle_review_artifact_hash": review["artifact_hash"],
        "issues": issues,
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking_issues),
        "route_summary": dict(sorted(routes.items())),
        "correction_attempt": correction_attempt,
        "max_correction_attempts": max_correction_attempts,
        "next_node": next_node,
        "g02_status": "pending" if valid else "not_started",
    }
    artifact = ArtifactEnvelope(
        workflow_run_id=workflow_run_id,
        workflow_mode=workflow_mode,
        artifact_id="n04-test-case-ir-validation",
        source_snapshot_id=snapshot_id,
        producer=Producer(component_id="N04", runtime="deterministic"),
        payload=payload,
        status=ArtifactStatus.COMPLETED if valid else ArtifactStatus.NEEDS_HUMAN,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=design["artifact_id"],
                location=test_design_artifact_path.name,
                content_hash=design["artifact_hash"],
            ),
            EvidenceRef(
                source_type="artifact",
                source_id=review["artifact_id"],
                location=oracle_review_artifact_path.name,
                content_hash=review["artifact_hash"],
            ),
        ),
        reason_code=reason_code,
    )
    artifact_dict = artifact.to_dict()
    security.assert_no_secret_values(artifact_dict)
    ArtifactStore(output_dir).write_artifact(artifact)
    return artifact_dict
