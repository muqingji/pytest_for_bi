"""Deterministically bind compiled contract Cases to one frozen OpenAPI revision."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from .errors import ContractError, InputError
from .security import SecurityPolicy
from .storage import ArtifactStore


_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be an object")
    return value


def _pointer(path: str) -> str:
    return path.replace("~", "~0").replace("/", "~1")


def bind_frozen_contract_refs(
    compiled_cases_path: Path,
    openapi_path: Path,
    bindings_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Emit a revised N25 Artifact with auditable OpenAPI refs on contract Cases."""

    security = security or SecurityPolicy()
    compiled = _read(compiled_cases_path, "N25 compiled cases")
    openapi = _read(openapi_path, "frozen OpenAPI")
    bindings = _read(bindings_path, "contract Case bindings")
    # OpenAPI auth extensions describe credential parameter names (for example
    # ``cookie``); they are contract metadata, not credential values.
    for value in (compiled, bindings):
        security.assert_no_secret_values(value)
    producer = compiled.get("producer")
    if (
        compiled.get("schema_version") != "artifact-envelope/1.0"
        or compiled.get("artifact_hash") != artifact_hash_from_mapping(compiled)
        or compiled.get("artifact_id") != "n25-compiled-test-cases"
        or not isinstance(producer, Mapping)
        or producer.get("component_id") != "N25"
    ):
        raise ContractError("Contract binding requires a valid N25 compiled Case Artifact")
    source = openapi.get("x-contract-source")
    commit = str(source.get("ref", "")) if isinstance(source, Mapping) else ""
    info = openapi.get("info")
    if (
        openapi.get("openapi") not in {"3.0.0", "3.0.1", "3.1.0"}
        or not _COMMIT.fullmatch(commit)
        or not isinstance(info, Mapping)
        or info.get("version") != commit
    ):
        raise ContractError("OpenAPI does not carry one valid frozen source commit")
    if bindings.get("schema_version") != "contract-case-bindings/1.0":
        raise ContractError("Contract Case binding schema_version is invalid")
    if bindings.get("source_commit") != commit:
        raise ContractError("Contract Case bindings do not match the OpenAPI source commit")
    raw_bindings = bindings.get("bindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise ContractError("Contract Case bindings must be a non-empty list")
    paths = openapi.get("paths")
    if not isinstance(paths, Mapping):
        raise ContractError("OpenAPI paths are missing")
    contract_location = str(bindings.get("contract_location", openapi_path.as_posix()))
    by_case: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_bindings):
        if not isinstance(raw, Mapping):
            raise ContractError(f"bindings[{index}] must be an object")
        case_id = str(raw.get("case_id", "")).strip()
        path = str(raw.get("path", "")).strip()
        method = str(raw.get("method", "")).strip().lower()
        if not case_id or case_id in by_case:
            raise ContractError(f"bindings[{index}].case_id must be unique and non-empty")
        path_item = paths.get(path)
        if method not in _METHODS or not isinstance(path_item, Mapping):
            raise ContractError(f"Binding {case_id} references an unknown OpenAPI operation")
        operation = path_item.get(method)
        if not isinstance(operation, Mapping) or not str(operation.get("operationId", "")):
            raise ContractError(f"Binding {case_id} references an unknown OpenAPI operation")
        operation_id = str(operation["operationId"])
        if str(raw.get("operation_id", operation_id)) != operation_id:
            raise ContractError(f"Binding {case_id} operation_id does not match OpenAPI")
        by_case[case_id] = {
            "contract_ref": (
                f"openapi:fs-bi@{commit}:{contract_location}"
                f"#/paths/{_pointer(path)}/{method}"
            ),
            "contract_source_commit": commit,
            "method": method.upper(),
            "path": path,
            "operation_id": operation_id,
        }

    payload = compiled.get("payload")
    cases = payload.get("compiled_cases") if isinstance(payload, Mapping) else None
    if not isinstance(cases, list):
        raise ContractError("N25 compiled_cases are invalid")
    revised_cases: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    required_contract_ids: set[str] = set()
    for raw_case in cases:
        if not isinstance(raw_case, Mapping):
            raise ContractError("N25 compiled_cases must contain objects")
        case = deepcopy(dict(raw_case))
        case_id = str(case.get("id", ""))
        known_ids.add(case_id)
        if case.get("layer") == "contract" and case.get("automation_candidate") is True:
            required_contract_ids.add(case_id)
        binding = by_case.get(case_id)
        if binding is not None:
            if case.get("layer") != "contract":
                raise ContractError(f"Binding {case_id} targets a non-contract Case")
            test_data = case.get("test_data")
            case["test_data"] = {
                **(deepcopy(dict(test_data)) if isinstance(test_data, Mapping) else {}),
                **binding,
            }
        revised_cases.append(case)
    unknown = sorted(set(by_case) - known_ids)
    missing = sorted(required_contract_ids - set(by_case))
    if unknown:
        raise ContractError(f"Contract bindings reference unknown Cases: {unknown}")
    if missing:
        raise ContractError(f"Machine-executable contract Cases lack bindings: {missing}")

    binding_summary = {
        "schema_version": "contract-binding-summary/1.0",
        "source_repository": str(source.get("repository", "fs-bi")),
        "source_commit": commit,
        "openapi_hash": content_hash(openapi),
        "binding_manifest_hash": content_hash(bindings),
        "bound_case_ids": sorted(by_case),
    }
    artifact = ArtifactEnvelope(
        workflow_run_id=str(compiled["workflow_run_id"]),
        workflow_mode=str(compiled["workflow_mode"]),
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id=str(compiled["source_snapshot_id"]),
        producer=Producer(component_id="N25", profile_version="1.1.0", runtime="deterministic"),
        payload={
            **deepcopy(dict(payload)),
            "compiled_cases": revised_cases,
            "contract_binding": binding_summary,
        },
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                "artifact",
                "n25-compiled-test-cases",
                compiled_cases_path.name,
                str(compiled["artifact_hash"]),
            ),
            EvidenceRef(
                "openapi", "fs-bi-stat", contract_location, binding_summary["openapi_hash"]
            ),
            EvidenceRef(
                "binding_manifest",
                "contract-case-bindings",
                bindings_path.name,
                binding_summary["binding_manifest_hash"],
            ),
        ),
    )
    store = ArtifactStore(output_dir)
    store.write_artifact(artifact)
    result = {
        **binding_summary,
        "binding_schema_version": binding_summary["schema_version"],
        "schema_version": "contract-binding-result/1.0",
        "artifact_id": artifact.artifact_id,
        "artifact_hash": artifact.artifact_hash,
        "artifact_path": str(output_dir / "artifacts/n25-compiled-test-cases.json"),
    }
    store.write_json("contract-binding-result.json", result)
    return result
