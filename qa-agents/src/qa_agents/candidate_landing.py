"""Land approved automation candidates into an isolated workspace.

Business repositories stay read-only. Landing writes only under the workflow
artifact store (or an explicitly approved automation workspace root) and never
opens an MR or production write path by itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .automation import AutomationPolicy, check_automation_generation
from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from .errors import ContractError, InputError, SecurityPolicyError
from .security import SecurityPolicy
from .storage import ArtifactStore


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be a JSON object")
    return value


def _validate_artifact(artifact: Mapping[str, Any], label: str) -> None:
    if artifact.get("schema_version") != "artifact-envelope/1.0":
        raise ContractError(f"{label} is not an Artifact Envelope")
    if artifact_hash_from_mapping(artifact) != artifact.get("artifact_hash"):
        raise ContractError(f"{label} artifact hash is invalid")
    if not isinstance(artifact.get("producer"), Mapping):
        raise ContractError(f"{label} producer is missing")
    if not isinstance(artifact.get("payload"), Mapping):
        raise ContractError(f"{label} payload is not an object")


def _binding(payload: Mapping[str, Any], generation_hash: str) -> Mapping[str, Any] | None:
    if payload.get("generation_hash") == generation_hash:
        return payload
    for item in payload.get("input_bindings", []):
        if isinstance(item, Mapping) and item.get("generation_hash") == generation_hash:
            return item
    return None


def _safe_relative(path: str) -> PurePosixPath:
    pure = PurePosixPath(path)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise SecurityPolicyError(f"Candidate path is not confined: {path}")
    return pure


def _resolve_landing_root(output_dir: Path, landing_root: Path | None) -> Path:
    store_root = output_dir.resolve()
    if landing_root is None:
        return (store_root / "automation-workspace").resolve()
    root = landing_root.resolve()
    if root != store_root and store_root not in root.parents:
        raise SecurityPolicyError(
            "Landing root must stay inside the workflow artifact output directory"
        )
    return root


def land_automation_candidates(
    generation_path: Path,
    review_path: Path,
    code_check_path: Path,
    automation_policy_path: Path,
    output_dir: Path,
    *,
    landing_root: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Materialize hash-bound candidates after A18/N05 approval.

    Does not create MRs, does not write business repositories, and does not
    execute tests. Execution remains N08's responsibility.
    """

    security = security or SecurityPolicy()
    generation_artifact = _load(generation_path, "automation generation Artifact")
    review_artifact = _load(review_path, "automation review Artifact")
    code_check_artifact = _load(code_check_path, "N05 code-check Artifact")
    for label, artifact in (
        ("generation", generation_artifact),
        ("review", review_artifact),
        ("code check", code_check_artifact),
    ):
        _validate_artifact(artifact, label)
        security.assert_no_secret_values(artifact)

    run_ids = {
        str(item.get("workflow_run_id", ""))
        for item in (generation_artifact, review_artifact, code_check_artifact)
    }
    snapshots = {
        str(item.get("source_snapshot_id", ""))
        for item in (generation_artifact, review_artifact, code_check_artifact)
    }
    workflow_modes = {
        str(item.get("workflow_mode", ""))
        for item in (generation_artifact, review_artifact, code_check_artifact)
    }
    if (
        len(run_ids) != 1
        or "" in run_ids
        or len(snapshots) != 1
        or "" in snapshots
        or len(workflow_modes) != 1
        or "" in workflow_modes
    ):
        raise ContractError("Candidate landing upstream workflow/source/mode bindings do not match")

    generation = generation_artifact["payload"]
    if generation_artifact.get("status") != "completed" or not isinstance(
        generation.get("manifest"), Mapping
    ):
        raise ContractError("Landing requires a completed automation generation")
    generator_id = str(generation["manifest"].get("generator_profile", "")).split("/", 1)[0]
    if not generator_id:
        raise ContractError("Automation generation has no generator profile")
    if generation_artifact["producer"].get("component_id") != generator_id:
        raise ContractError("Automation generation producer does not match generator profile")
    if generation.get("schema_version") != "automation-generation/1.0":
        raise ContractError("Automation generation payload contract is invalid")

    generation_hash = content_hash(generation)
    manifest = generation["manifest"]
    manifest_hash = content_hash(manifest)
    candidate_hashes = {
        str(item.get("path")): str(item.get("content_hash", ""))
        for item in generation.get("code_candidates", [])
        if isinstance(item, Mapping)
    }
    if not candidate_hashes:
        raise ContractError("Landing requires at least one code candidate")

    review = review_artifact["payload"]
    review_id = str(review.get("review_profile", "")).split("/", 1)[0]
    if not review_id.startswith("A18-"):
        raise ContractError("Automation review has no independent A18 profile")
    if review_artifact["producer"].get("component_id") != review_id:
        raise ContractError("Automation review producer must match review profile")
    if review.get("schema_version") != "automation-review/1.0":
        raise ContractError("Automation review payload contract is invalid")
    if review_artifact.get("status") != "completed" or review.get("approved") is not True:
        raise ContractError("Landing requires an approved independent automation review")
    review_binding = _binding(review, generation_hash)
    if not review_binding or review_binding.get("manifest_hash") != manifest_hash:
        raise ContractError("Automation review is not bound to this generation manifest")
    if dict(review_binding.get("candidate_hashes", {})) != candidate_hashes:
        raise ContractError("Automation review candidate bindings do not match generation")

    code_check = code_check_artifact["payload"]
    if code_check_artifact["producer"].get("component_id") != "N05":
        raise ContractError("Code check producer must be N05")
    if code_check.get("schema_version") != "automation-code-check/1.0":
        raise ContractError("N05 payload contract is invalid")
    if code_check_artifact.get("status") != "completed" or code_check.get("passed") is not True:
        raise ContractError("Landing requires a passed N05 code check")
    check_binding = _binding(code_check, generation_hash)
    if not check_binding or check_binding.get("manifest_hash") != manifest_hash:
        raise ContractError("N05 is not bound to this generation manifest")
    if dict(check_binding.get("candidate_hashes", {})) != candidate_hashes:
        raise ContractError("N05 candidate bindings do not match generation")

    automation_policy = AutomationPolicy.from_file(automation_policy_path)
    recheck = check_automation_generation(generation, automation_policy)
    if not recheck["passed"]:
        raise SecurityPolicyError("Generation no longer passes the current automation policy")

    target = manifest.get("target_repository", {})
    if not isinstance(target, Mapping):
        raise ContractError("Manifest target_repository is required")
    if target.get("access_class") != "approved_automation_repository":
        raise SecurityPolicyError("Landing only supports approved_automation_repository targets")
    if target.get("write_mode") not in {
        "artifact_only_candidate",
        "isolated_workspace_landing",
        "approved_automation_repository",
    }:
        raise SecurityPolicyError(f"Unsupported automation write_mode: {target.get('write_mode')}")

    root = _resolve_landing_root(output_dir, landing_root)
    root.mkdir(parents=True, exist_ok=True)
    store = ArtifactStore(output_dir)
    landed: list[dict[str, Any]] = []
    for item in generation.get("code_candidates", []):
        if not isinstance(item, Mapping):
            raise ContractError("code_candidates must contain objects")
        path = str(item.get("path", ""))
        pure = _safe_relative(path)
        content = str(item.get("content", ""))
        expected_hash = str(item.get("content_hash", ""))
        if content_hash(content) != expected_hash:
            raise ContractError(f"Candidate content hash drifted before landing: {path}")
        target_path = root.joinpath(*pure.parts)
        if root not in target_path.resolve().parents and target_path.resolve() != root:
            raise SecurityPolicyError(f"Landed path escapes workspace: {path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        written_hash = content_hash(target_path.read_text(encoding="utf-8"))
        if written_hash != expected_hash:
            raise ContractError(f"Landed candidate hash mismatch: {path}")
        relative = str(pure)
        landed.append(
            {
                "path": relative,
                "absolute_path": str(target_path),
                "content_hash": written_hash,
                "bytes": target_path.stat().st_size,
            }
        )

    payload = {
        "schema_version": "n29-candidate-landing/1.0",
        "workflow_run_id": next(iter(run_ids)),
        "source_snapshot_id": next(iter(snapshots)),
        "landed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "landing_root": str(root),
        "write_mode": "isolated_workspace_landing",
        "target_repository": {
            "repository_id": str(target.get("repository_id", "")),
            "access_class": str(target.get("access_class", "")),
        },
        "input_bindings": {
            "generation_hash": generation_artifact["artifact_hash"],
            "review_hash": review_artifact["artifact_hash"],
            "code_check_hash": code_check_artifact["artifact_hash"],
            "manifest_hash": manifest_hash,
            "candidate_hashes": candidate_hashes,
        },
        "landed_files": landed,
        "file_count": len(landed),
        "mr_disposition": "not_requested",
        "business_repository_write": False,
        "next_node": "N08",
        "notes": [
            "Candidates are materialized for isolated trial execution only.",
            "MR creation and production isolation runners remain separate adapters.",
        ],
    }
    security.assert_no_secret_values(payload)
    artifact = ArtifactEnvelope(
        workflow_run_id=next(iter(run_ids)),
        workflow_mode=next(iter(workflow_modes)),
        artifact_id="n29-candidate-landing",
        source_snapshot_id=next(iter(snapshots)),
        producer=Producer("N29", profile_version="1.0.0"),
        payload=payload,
        status=ArtifactStatus.COMPLETED,
    )
    store.write_artifact(artifact)
    store.write_json(
        "candidate-landing-receipt.json",
        {
            "schema_version": "candidate-landing-receipt/1.0",
            "artifact_hash": artifact.artifact_hash,
            "landing_root": str(root),
            "file_count": len(landed),
            "paths": [item["path"] for item in landed],
            "mr_disposition": "not_requested",
        },
    )
    return artifact.to_dict()
