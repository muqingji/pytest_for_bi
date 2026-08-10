"""Deterministic N25/N26/N15 stage-two node drivers for the real chain.

N25 consumes the accepted A08 Artifact after G02 approval, N26 consumes the A11
post-split review, and N15 compiles the deterministic execution plan. All three
verify content-addressed upstream bindings before writing new Artifacts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .case_compiler import compile_cases
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
from .selection import compile_execution_plan, select_cases
from .storage import ArtifactStore


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Cannot read valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Expected a JSON object: {path}")
    return value


def _verified_artifact(path: Path, expected_id: str, security: SecurityPolicy) -> dict[str, Any]:
    artifact = _read_object(path)
    if artifact.get("artifact_id") != expected_id:
        raise ContractError(f"Expected Artifact {expected_id}: {path}")
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError(f"Artifact hash mismatch: {expected_id}")
    security.assert_no_secret_values(artifact)
    return artifact


def _validated_hash(value: Mapping[str, Any], hash_field: str, label: str) -> None:
    unhashed = {key: item for key, item in value.items() if key != hash_field}
    if value.get(hash_field) != content_hash(unhashed):
        raise ContractError(f"{label} hash is invalid")


def _identity(artifact: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(artifact.get("workflow_run_id", "")),
        str(artifact.get("workflow_mode", "")),
        str(artifact.get("source_snapshot_id", "")),
    )


def run_n25_after_g02(
    a08_artifact_path: Path,
    g02_request_path: Path,
    g02_outcome_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile parent Test Case IR into layered child cases after G02 approval."""

    security = security or SecurityPolicy()
    design = _verified_artifact(a08_artifact_path, "a08-test-design-ir", security)
    request = _read_object(g02_request_path)
    outcome = _read_object(g02_outcome_path)
    for value in (request, outcome):
        security.assert_no_secret_values(value)
    _validated_hash(request, "request_hash", "G02 review request")
    _validated_hash(outcome, "outcome_hash", "G02 review outcome")
    if outcome.get("schema_version") != "test-case-ir-review-outcome/1.0":
        raise ContractError("N25 G02 outcome schema_version is invalid")
    if outcome.get("decision") != "approved" or outcome.get("next_node") != "N25":
        raise ContractError("N25 requires an approved G02 outcome routed to N25")
    if outcome.get("request_hash") != request.get("request_hash"):
        raise ContractError("N25 G02 outcome does not bind the review request")
    if (
        str(outcome.get("workflow_run_id", "")) != str(request.get("workflow_run_id", ""))
        or str(outcome.get("source_snapshot_id", ""))
        != str(request.get("source_snapshot_id", ""))
    ):
        raise ContractError("N25 G02 request and outcome belong to different runs")
    if _identity(design) != _identity(request):
        raise ContractError("N25 A08 Artifact does not belong to the G02 run")

    upstream = {
        str(item.get("artifact_id")): str(item.get("artifact_hash"))
        for item in request.get("upstream_artifacts", [])
        if isinstance(item, Mapping)
    }
    if upstream.get("a08-test-design-ir") != design["artifact_hash"]:
        raise ContractError("N25 G02 approval does not bind the current A08 Artifact")

    parent_cases = design["payload"].get("parent_cases")
    if not isinstance(parent_cases, list) or not all(
        isinstance(item, Mapping) for item in parent_cases
    ):
        raise ContractError("N25 A08 parent_cases are invalid")
    child_cases = compile_cases(parent_cases, strategy={})
    workflow_run_id, workflow_mode, snapshot_id = _identity(design)
    payload = {
        "schema_version": "n25-compiled-test-cases/1.0",
        "parent_artifact_id": design["artifact_id"],
        "parent_artifact_hash": design["artifact_hash"],
        "compiled_cases": child_cases,
        "parent_count": len(parent_cases),
        "child_count": len(child_cases),
        "compile_rule_version": "n25-compiler/1.0",
    }
    artifact = ArtifactEnvelope(
        workflow_run_id=workflow_run_id,
        workflow_mode=workflow_mode,
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id=snapshot_id,
        producer=Producer(component_id="N25", runtime="deterministic"),
        payload=payload,
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=design["artifact_id"],
                location=a08_artifact_path.name,
                content_hash=design["artifact_hash"],
            ),
        ),
    )
    artifact_dict = artifact.to_dict()
    security.assert_no_secret_values(artifact_dict)
    ArtifactStore(output_dir).write_artifact(artifact)
    return artifact_dict


def run_n26_after_a11(
    compiled_artifact_path: Path,
    split_review_artifact_path: Path,
    split_review_bundle_path: Path,
    output_dir: Path,
    *,
    asset_catalog_path: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Select the final test set from A11-approved compiled cases."""

    security = security or SecurityPolicy()
    compiled = _verified_artifact(compiled_artifact_path, "n25-compiled-test-cases", security)
    review = _verified_artifact(
        split_review_artifact_path, "a11-split-coverage-review", security
    )
    review_bundle = _read_object(split_review_bundle_path)
    for value in (review_bundle,):
        security.assert_no_secret_values(value)
    expected_bundle_hash = str(review_bundle.get("bundle_hash", ""))
    unhashed_bundle = {
        key: item for key, item in review_bundle.items() if key != "bundle_hash"
    }
    if (
        review_bundle.get("profile_id") != "A11"
        or not expected_bundle_hash
        or expected_bundle_hash != content_hash(unhashed_bundle)
    ):
        raise ContractError("N26 A11 input bundle is invalid")
    if review["payload"].get("input_bundle_hash") != expected_bundle_hash:
        raise ContractError("N26 A11 Artifact does not bind its input bundle")
    if review["payload"].get("approved") is not True:
        raise ContractError("N26 requires an approved A11 split-coverage review")
    upstream = {
        str(item.get("artifact_id")): str(item.get("artifact_hash"))
        for item in review_bundle.get("upstream_artifacts", [])
        if isinstance(item, Mapping)
    }
    if upstream.get("n25-compiled-test-cases") != compiled["artifact_hash"]:
        raise ContractError("N26 A11 review does not bind the current N25 Artifact")
    if _identity(review) != _identity(compiled):
        raise ContractError("N26 A11 and N25 Artifacts belong to different runs")

    asset_catalog = (
        _read_object(asset_catalog_path) if asset_catalog_path is not None else {}
    )
    child_cases = compiled["payload"].get("compiled_cases")
    if not isinstance(child_cases, list) or not all(
        isinstance(item, Mapping) for item in child_cases
    ):
        raise ContractError("N26 N25 compiled_cases are invalid")
    selection = select_cases(child_cases, asset_catalog)
    workflow_run_id, workflow_mode, snapshot_id = _identity(compiled)
    payload = {
        "schema_version": "test-selection/1.0",
        "compiled_artifact_id": compiled["artifact_id"],
        "compiled_artifact_hash": compiled["artifact_hash"],
        "selected_cases": selection["selected_cases"],
        "unresolved_items": selection["unresolved_items"],
    }
    artifact = ArtifactEnvelope(
        workflow_run_id=workflow_run_id,
        workflow_mode=workflow_mode,
        artifact_id="n26-test-selection",
        source_snapshot_id=snapshot_id,
        producer=Producer(component_id="N26", runtime="deterministic"),
        payload=payload,
        status=(
            ArtifactStatus.NEEDS_HUMAN
            if selection["unresolved_items"]
            else ArtifactStatus.COMPLETED
        ),
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=review["artifact_id"],
                location=split_review_artifact_path.name,
                content_hash=review["artifact_hash"],
            ),
        ),
    )
    artifact_dict = artifact.to_dict()
    security.assert_no_secret_values(artifact_dict)
    ArtifactStore(output_dir).write_artifact(artifact)
    return artifact_dict


def run_n15_after_n26(
    selection_artifact_path: Path,
    compiled_artifact_path: Path,
    output_dir: Path,
    *,
    asset_catalog_path: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile the deterministic execution plan from the N26 selection."""

    security = security or SecurityPolicy()
    selection_artifact = _verified_artifact(
        selection_artifact_path, "n26-test-selection", security
    )
    compiled = _verified_artifact(compiled_artifact_path, "n25-compiled-test-cases", security)
    if _identity(selection_artifact) != _identity(compiled):
        raise ContractError("N15 N26 and N25 Artifacts belong to different runs")
    upstream = selection_artifact["payload"].get("compiled_artifact_hash")
    if upstream != compiled["artifact_hash"]:
        raise ContractError("N15 N26 selection does not bind the current N25 Artifact")

    asset_catalog = (
        _read_object(asset_catalog_path) if asset_catalog_path is not None else {}
    )
    child_cases = compiled["payload"].get("compiled_cases")
    if not isinstance(child_cases, list):
        raise ContractError("N15 N25 compiled_cases are invalid")
    plan = compile_execution_plan(
        selection_artifact["payload"], child_cases, asset_catalog
    )
    workflow_run_id, workflow_mode, snapshot_id = _identity(compiled)
    artifact = ArtifactEnvelope(
        workflow_run_id=workflow_run_id,
        workflow_mode=workflow_mode,
        artifact_id="n15-execution-plan",
        source_snapshot_id=snapshot_id,
        producer=Producer(component_id="N15", runtime="deterministic"),
        payload={
            "schema_version": "execution-plan/1.0",
            "selection_artifact_id": selection_artifact["artifact_id"],
            "selection_artifact_hash": selection_artifact["artifact_hash"],
            "actions": plan["actions"],
        },
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=selection_artifact["artifact_id"],
                location=selection_artifact_path.name,
                content_hash=selection_artifact["artifact_hash"],
            ),
        ),
    )
    artifact_dict = artifact.to_dict()
    security.assert_no_secret_values(artifact_dict)
    ArtifactStore(output_dir).write_artifact(artifact)
    return artifact_dict
