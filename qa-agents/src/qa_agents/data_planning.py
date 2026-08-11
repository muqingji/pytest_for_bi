"""Evidence-bound BI data intent extraction and deterministic resource planning."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
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


INTENT_CONTRACT = "test-data-intent/1.0"
PLAN_CONTRACT = "test-data-plan/1.0"
SOURCE_CONTRACT = "bi-knowledge-sources/1.0"
CATALOG_CONTRACT = "bi-data-capability-catalog/1.0"
_VARIABLE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be an object")
    return value


def validate_knowledge_sources(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != SOURCE_CONTRACT:
        raise ContractError("BI knowledge source schema_version is invalid")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ContractError("BI knowledge sources must be a non-empty list")
    seen: set[str] = set()
    usable = 0
    blocked = 0
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ContractError(f"sources[{index}] must be an object")
        source_id = str(source.get("id", ""))
        if not source_id or source_id in seen:
            raise ContractError(f"sources[{index}].id must be unique and non-empty")
        seen.add(source_id)
        status = str(source.get("access_status", ""))
        if status not in {"available", "authentication_required", "pending"}:
            raise ContractError(f"sources[{index}].access_status is invalid")
        if status == "available":
            usable += 1
        else:
            blocked += 1
        if not str(source.get("location", "")):
            raise ContractError(f"sources[{index}].location is required")
        if source.get("kind") == "official_product_manual" and status == "available":
            if not str(source.get("snapshot_ref", "")):
                raise ContractError(f"sources[{index}].snapshot_ref is required")
            if re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(source.get("content_hash", ""))
            ) is None:
                raise ContractError(f"sources[{index}].content_hash is invalid")
    return {
        "schema_version": "bi-knowledge-source-validation/1.0",
        "valid": True,
        "source_count": len(sources),
        "available_count": usable,
        "unavailable_count": blocked,
        "source_manifest_hash": content_hash(value),
    }


def verify_knowledge_snapshots(
    value: Mapping[str, Any], *, project_root: Path
) -> dict[str, Any]:
    verified = 0
    root = project_root.resolve()
    for index, source in enumerate(value.get("sources", [])):
        if not isinstance(source, Mapping) or source.get("access_status") != "available":
            continue
        snapshot_ref = str(source.get("snapshot_ref", ""))
        if not snapshot_ref:
            continue
        relative = snapshot_ref.split("#", 1)[0]
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise ContractError(f"sources[{index}].snapshot_ref escapes project root")
        try:
            digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise InputError(f"Knowledge snapshot cannot be read: {path}") from error
        if digest != source.get("content_hash"):
            raise ContractError(f"Knowledge snapshot hash mismatch: {snapshot_ref}")
        verified += 1
    return {
        "schema_version": "bi-knowledge-snapshot-validation/1.0",
        "valid": True,
        "verified_snapshot_count": verified,
    }


def validate_capability_catalog(
    value: Mapping[str, Any], sources: Mapping[str, Any]
) -> dict[str, Any]:
    if value.get("schema_version") != CATALOG_CONTRACT:
        raise ContractError("BI data capability catalog schema_version is invalid")
    source_ids = {
        str(item.get("id"))
        for item in sources.get("sources", [])
        if isinstance(item, Mapping) and item.get("access_status") == "available"
    }
    profiles = value.get("environment_profiles")
    recipes = value.get("recipes")
    if not isinstance(profiles, Mapping) or not profiles:
        raise ContractError("BI data capability catalog requires environment_profiles")
    if not isinstance(recipes, list) or not recipes:
        raise ContractError("BI data capability catalog requires recipes")
    recipe_ids: set[str] = set()
    for index, recipe in enumerate(recipes):
        if not isinstance(recipe, Mapping):
            raise ContractError(f"recipes[{index}] must be an object")
        recipe_id = str(recipe.get("id", ""))
        if not recipe_id or recipe_id in recipe_ids:
            raise ContractError(f"recipes[{index}].id must be unique and non-empty")
        recipe_ids.add(recipe_id)
        profile_id = str(recipe.get("environment_profile", ""))
        if profile_id not in profiles:
            raise ContractError(f"recipe {recipe_id} references an unknown environment profile")
        evidence = recipe.get("evidence_refs")
        if not isinstance(evidence, list) or not evidence:
            raise ContractError(f"recipe {recipe_id} requires evidence_refs")
        for source_id in evidence:
            if str(source_id) not in source_ids:
                raise ContractError(
                    f"recipe {recipe_id} references unavailable source {source_id!r}"
                )
        resources = recipe.get("resources")
        if not isinstance(resources, list) or not resources:
            raise ContractError(f"recipe {recipe_id} requires resources")
        _topological_resources(resources, recipe_id)
    return {
        "schema_version": "bi-data-capability-validation/1.0",
        "valid": True,
        "recipe_count": len(recipes),
        "catalog_hash": content_hash(value),
    }


def _case_text(case: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "title": case.get("title", case.get("name", "")),
            "preconditions": case.get("preconditions", []),
            "test_data": case.get("test_data", {}),
            "steps": case.get("steps", []),
            "expected": case.get("expected", []),
        },
        ensure_ascii=False,
    ).lower()


def _matches_recipe(case: Mapping[str, Any], recipe: Mapping[str, Any]) -> bool:
    match = recipe.get("match", {})
    if not isinstance(match, Mapping):
        raise ContractError(f"recipe {recipe.get('id')} match must be an object")
    test_data = case.get("test_data", {})
    explicit_intent = ""
    if isinstance(test_data, Mapping):
        explicit_intent = str(test_data.get("data_intent", ""))
    intents = {str(item) for item in match.get("data_intents", [])}
    if explicit_intent and explicit_intent in intents:
        return True
    dataset = str(test_data.get("dataset", "")) if isinstance(test_data, Mapping) else ""
    datasets = {str(item) for item in match.get("datasets", [])}
    if dataset:
        return dataset in datasets
    groups = match.get("all_term_groups", [])
    if not groups:
        return False
    text = _case_text(case)
    return all(
        isinstance(group, list) and any(str(term).lower() in text for term in group)
        for group in groups
    )


def extract_test_data_intents(
    cases: list[Mapping[str, Any]], catalog: Mapping[str, Any]
) -> dict[str, Any]:
    """A22 turns Case semantics into resource goals without choosing API calls."""

    recipes = list(catalog.get("recipes", []))
    case_intents: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    paused: list[dict[str, str]] = []
    for case in cases:
        case_id = str(case.get("id", ""))
        if not case_id:
            raise ContractError("A22 Case requires id")
        level = str(case.get("test_level", "") or "").strip().lower()
        if level in {"unit", "unit_test", "单元", "单元测试"}:
            paused.append(
                {
                    "case_id": case_id,
                    "reason_code": "paused_existing_developer_unit_coverage",
                }
            )
            continue
        test_data = case.get("test_data", {})
        dataset = str(test_data.get("dataset", "")) if isinstance(test_data, Mapping) else ""
        matches = [recipe for recipe in recipes if _matches_recipe(case, recipe)]
        if len(matches) > 1:
            unresolved.append(
                {
                    "case_id": case_id,
                    "reason_code": "ambiguous_data_capability",
                    "candidate_recipe_ids": [str(item["id"]) for item in matches],
                    "route_to": "capability_catalog",
                }
            )
            case_intents.append(
                {
                    "case_id": case_id,
                    "requires_data_construction": True,
                    "dataset": dataset,
                    "resource_goals": [],
                }
            )
            continue
        if not matches:
            requires_data = bool(dataset or test_data or case.get("preconditions"))
            if requires_data:
                unresolved.append(
                    {
                        "case_id": case_id,
                        "reason_code": "data_capability_not_registered",
                        "dataset": dataset or None,
                        "route_to": "capability_adapter_backlog",
                    }
                )
            case_intents.append(
                {
                    "case_id": case_id,
                    "requires_data_construction": requires_data,
                    "dataset": dataset,
                    "resource_goals": [],
                }
            )
            continue
        recipe = matches[0]
        requested_variants = (
            [str(item) for item in test_data.get("variants", [])]
            if isinstance(test_data, Mapping)
            else []
        )
        supported_variants = {str(item) for item in recipe.get("supported_variants", [])}
        missing_variants = [
            item for item in requested_variants if item not in supported_variants
        ]
        if missing_variants:
            unresolved.append(
                {
                    "case_id": case_id,
                    "reason_code": "data_capability_variant_not_registered",
                    "recipe_id": str(recipe["id"]),
                    "missing_variants": missing_variants,
                    "route_to": "capability_adapter_backlog",
                }
            )
        case_intents.append(
            {
                "case_id": case_id,
                "requires_data_construction": True,
                "dataset": dataset,
                "resource_goals": deepcopy(recipe.get("resource_goals", [])),
                "recipe_id": str(recipe["id"]),
                "recipe_version": str(recipe.get("version", "")),
                "evidence_refs": list(recipe.get("evidence_refs", [])),
                "requested_variants": requested_variants,
                "supported_variants": sorted(supported_variants),
            }
        )
    return {
        "schema_version": INTENT_CONTRACT,
        "case_intents": case_intents,
        "paused_cases": paused,
        "unresolved_requirements": unresolved,
        "inference_mode": "case_semantics_plus_versioned_capability_catalog",
    }


def _topological_resources(
    resources: list[Any], recipe_id: str
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(resources):
        if not isinstance(raw, Mapping):
            raise ContractError(f"recipe {recipe_id} resources[{index}] must be an object")
        resource = deepcopy(dict(raw))
        key = str(resource.get("resource_key", ""))
        if not key or key in by_key:
            raise ContractError(f"recipe {recipe_id} resource_key must be unique and non-empty")
        by_key[key] = resource
    ordered: list[dict[str, Any]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visited:
            return
        if key in visiting:
            raise ContractError(f"recipe {recipe_id} resource dependency cycle at {key}")
        if key not in by_key:
            raise ContractError(f"recipe {recipe_id} references missing dependency {key}")
        visiting.add(key)
        dependencies = by_key[key].get("depends_on", [])
        if not isinstance(dependencies, list):
            raise ContractError(f"recipe {recipe_id} resource {key} depends_on must be a list")
        for dependency in dependencies:
            visit(str(dependency))
        visiting.remove(key)
        visited.add(key)
        ordered.append(by_key[key])

    for resource_key in by_key:
        visit(resource_key)
    return ordered


def _resolve_variables(variables: Mapping[str, Any], namespace: str) -> dict[str, Any]:
    resolved = deepcopy(dict(variables))
    context: dict[str, Any] = {"namespace": namespace, **resolved}
    for _ in range(len(resolved) + 1):
        changed = False
        for key, raw in list(resolved.items()):
            if not isinstance(raw, str):
                continue

            def replace(match: re.Match[str]) -> str:
                name = match.group(1).strip()
                return str(context.get(name, match.group(0)))

            value = _VARIABLE.sub(replace, raw)
            if value != raw:
                resolved[key] = value
                context[key] = value
                changed = True
        if not changed:
            break
    unresolved = {
        key for key, value in resolved.items() if isinstance(value, str) and _VARIABLE.search(value)
    }
    if unresolved:
        raise ContractError(
            "N28 recipe variables contain unresolved references: "
            + ", ".join(sorted(unresolved))
        )
    return resolved


def compile_resource_plan(
    intent: Mapping[str, Any],
    catalog: Mapping[str, Any],
    *,
    environment: str,
    namespace: str,
) -> dict[str, Any]:
    """N28 expands semantic goals into a deterministic, reversible resource DAG."""

    if intent.get("schema_version") != INTENT_CONTRACT:
        raise ContractError("N28 test-data intent schema_version is invalid")
    recipes = {str(item["id"]): item for item in catalog.get("recipes", [])}
    profiles = catalog.get("environment_profiles", {})
    case_plans: list[dict[str, Any]] = []
    for item in intent.get("case_intents", []):
        if not isinstance(item, Mapping):
            raise ContractError("N28 case_intents must contain objects")
        recipe_id = str(item.get("recipe_id", ""))
        if not recipe_id:
            case_plans.append(
                {
                    "case_id": str(item.get("case_id", "")),
                    "requires_data_construction": bool(
                        item.get("requires_data_construction", False)
                    ),
                    "planning_mode": "autonomous",
                    "recipe_refs": [],
                    "evidence_refs": [],
                    "variables": {},
                    "resources": [],
                }
            )
            continue
        recipe = recipes.get(recipe_id)
        if not isinstance(recipe, Mapping):
            raise ContractError(f"N28 recipe {recipe_id!r} is missing")
        profile_id = str(recipe.get("environment_profile", ""))
        profile = profiles.get(profile_id)
        if not isinstance(profile, Mapping):
            raise ContractError(f"N28 environment profile {profile_id!r} is missing")
        if str(profile.get("environment", "")) != environment:
            raise ContractError(
                f"N28 profile {profile_id!r} does not support environment {environment!r}"
            )
        variables = deepcopy(dict(profile.get("variables", {})))
        variables.update(deepcopy(dict(recipe.get("variables", {}))))
        variables = _resolve_variables(variables, namespace)
        case_plans.append(
            {
                "case_id": str(item.get("case_id", "")),
                "requires_data_construction": True,
                "planning_mode": "autonomous",
                "recipe_refs": [
                    {"recipe_id": recipe_id, "version": str(recipe.get("version", ""))}
                ],
                "evidence_refs": list(recipe.get("evidence_refs", [])),
                "variables": variables,
                "resources": _topological_resources(
                    list(recipe.get("resources", [])), recipe_id
                ),
            }
        )
    return {
        "schema_version": PLAN_CONTRACT,
        "environment": environment,
        "namespace": namespace,
        "planning_mode": "autonomous",
        "capability_catalog_hash": content_hash(catalog),
        "case_plans": case_plans,
        "paused_cases": list(intent.get("paused_cases", [])),
        "unresolved_requirements": list(intent.get("unresolved_requirements", [])),
    }


def prepare_autonomous_test_data_plan(
    compiled_cases_path: Path,
    source_manifest_path: Path,
    capability_catalog_path: Path,
    policy_path: Path,
    output_dir: Path,
    *,
    environment: str,
    namespace: str,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Create hash-bound A22, N28 and N27 Artifacts from one frozen N25 output."""

    from .test_data import validate_test_data_plan

    security = security or SecurityPolicy()
    compiled = _read_object(compiled_cases_path, "N25 compiled cases Artifact")
    if compiled.get("schema_version") != "artifact-envelope/1.0":
        raise ContractError("N25 compiled cases is not an Artifact Envelope")
    if compiled.get("artifact_hash") != artifact_hash_from_mapping(compiled):
        raise ContractError("N25 compiled cases Artifact hash is invalid")
    producer = compiled.get("producer")
    if compiled.get("artifact_id") != "n25-compiled-test-cases" or not isinstance(
        producer, Mapping
    ) or producer.get("component_id") != "N25":
        raise ContractError("Autonomous data planning requires N25 compiled cases")
    compiled_payload = compiled.get("payload")
    cases = compiled_payload.get("compiled_cases") if isinstance(compiled_payload, Mapping) else None
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N25 compiled_cases must be a list of objects")
    sources = _read_object(source_manifest_path, "BI knowledge sources")
    catalog = _read_object(capability_catalog_path, "BI data capability catalog")
    policy = _read_object(policy_path, "test-data policy")
    security.assert_no_secret_values(sources)
    security.assert_no_secret_values(catalog)
    source_validation = validate_knowledge_sources(sources)
    source_validation["snapshot_validation"] = verify_knowledge_snapshots(
        sources, project_root=source_manifest_path.parent.parent
    )
    catalog_validation = validate_capability_catalog(catalog, sources)
    identity = (
        str(compiled.get("workflow_run_id", "")),
        str(compiled.get("workflow_mode", "")),
        str(compiled.get("source_snapshot_id", "")),
    )
    if not all(identity):
        raise ContractError("N25 workflow identity is incomplete")
    intent_payload = extract_test_data_intents(cases, catalog)
    intent_status = (
        ArtifactStatus.BLOCKED
        if intent_payload["unresolved_requirements"]
        else ArtifactStatus.COMPLETED
    )
    common_evidence = (
        EvidenceRef(
            source_type="knowledge_manifest",
            source_id="bi-knowledge-sources",
            location=str(source_manifest_path),
            content_hash=source_validation["source_manifest_hash"],
        ),
        EvidenceRef(
            source_type="capability_catalog",
            source_id="bi-data-capability-catalog",
            location=str(capability_catalog_path),
            content_hash=catalog_validation["catalog_hash"],
        ),
    )
    a22 = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="a22-test-data-intent",
        source_snapshot_id=identity[2],
        producer=Producer("A22", runtime="test-data-intent-runtime"),
        payload=intent_payload,
        status=intent_status,
        reason_code=(
            "test_data_capability_incomplete"
            if intent_status == ArtifactStatus.BLOCKED
            else None
        ),
        evidence_refs=common_evidence,
    )
    plan = compile_resource_plan(
        intent_payload, catalog, environment=environment, namespace=namespace
    )
    n28 = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="n28-test-data-resource-plan",
        source_snapshot_id=identity[2],
        producer=Producer("N28", runtime="deterministic"),
        payload=plan,
        status=intent_status,
        reason_code=a22.reason_code,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=a22.artifact_id,
                location=f"artifacts/{a22.artifact_id}.json",
                content_hash=a22.artifact_hash,
            ),
            *common_evidence,
        ),
    )
    validation = validate_test_data_plan(plan, policy)
    n27_status = (
        ArtifactStatus.COMPLETED
        if n28.status == ArtifactStatus.COMPLETED
        else ArtifactStatus.BLOCKED
    )
    n27 = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id=identity[2],
        producer=Producer("N27", runtime="deterministic"),
        payload={
            **validation,
            "a22_artifact_hash": a22.artifact_hash,
            "n28_artifact_hash": n28.artifact_hash,
            "source_validation": source_validation,
            "catalog_validation": catalog_validation,
        },
        status=n27_status,
        reason_code=n28.reason_code,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=n28.artifact_id,
                location=f"artifacts/{n28.artifact_id}.json",
                content_hash=n28.artifact_hash,
            ),
        ),
    )
    store = ArtifactStore(output_dir)
    for artifact in (a22, n28, n27):
        store.write_artifact(artifact)
    result = {
        "schema_version": "autonomous-test-data-preparation/1.0",
        "workflow_run_id": identity[0],
        "environment": environment,
        "namespace": namespace,
        "a22_artifact_hash": a22.artifact_hash,
        "n28_artifact_hash": n28.artifact_hash,
        "n27_artifact_hash": n27.artifact_hash,
        "resolved_case_count": sum(
            1 for item in plan["case_plans"] if item.get("resources")
        ),
        "unresolved_requirements": plan["unresolved_requirements"],
        "ready_for_execution": n27.status == ArtifactStatus.COMPLETED,
    }
    store.write_json("autonomous-test-data-preparation.json", result)
    return result
