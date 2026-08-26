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
LIFECYCLE_CONTRACT = "test-data-lifecycle-plan/1.0"
SOURCE_CONTRACT = "bi-knowledge-sources/1.0"
CATALOG_CONTRACT = "bi-data-capability-catalog/1.0"
_VARIABLE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
DEFAULT_SUBJECT_PRIORITY = ("客户", "销售订单", "销售记录")
FORBIDDEN_DEFAULT_SUBJECTS = frozenset({"区域测试"})
CHART_DETAIL_TERMS = ("查看明细", "统计图", "拼表", "交叉表", "detail query", "details view")


RESOURCE_INTENT_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "resource_type": "aggregate_metric",
        "data_intent": "metric.aggregate.create",
        "dataset": "aggregate_metric",
        "terms": ("聚合指标", "聚合度量", "agg metric", "aggregate metric"),
    },
    {
        "resource_type": "ordinary_metric",
        "data_intent": "metric.ordinary.create",
        "dataset": "ordinary_metric",
        "terms": ("普通指标", "普通度量", "一般指标", "ordinary metric", "plain metric"),
    },
    {
        "resource_type": "calculated_metric",
        "data_intent": "metric.calculated.create",
        "dataset": "calculated_metric",
        "terms": ("计算指标", "计算度量", "公式指标", "calculated metric", "calc metric"),
    },
    {
        "resource_type": "comparison_metric",
        "data_intent": "metric.comparison.create",
        "dataset": "comparison_metric",
        "terms": ("同环比", "同比", "环比", "comparison metric", "period over period"),
    },
    {
        "resource_type": "stat_chart",
        "data_intent": "chart.create",
        "dataset": "stat_chart",
        "terms": ("统计图", "图表", "图形", "chart", "stat view"),
    },
    {
        "resource_type": "report",
        "data_intent": "report.create",
        "dataset": "report",
        "terms": ("报表", "报告", "report", "dashboard"),
    },
    {
        "resource_type": "pivot_table",
        "data_intent": "pivot.create",
        "dataset": "pivot_table",
        "terms": ("交叉表", "透视表", "pivot", "cross table"),
    },
    {
        "resource_type": "joined_table",
        "data_intent": "joined_table.create",
        "dataset": "joined_table",
        "terms": ("拼表", "关联表", "joined table", "join table"),
    },
    {
        "resource_type": "custom_dimension",
        "data_intent": "custom_dimension.create",
        "dataset": "custom_dimension",
        "terms": ("自定义维度", "枚举维度", "custom dimension"),
    },
)


def infer_resource_intents(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Deterministic resource-type hints from Case semantics without an LLM."""
    text = _case_text(case)
    hits: list[dict[str, Any]] = []
    for group in RESOURCE_INTENT_GROUPS:
        matched_terms = [
            str(term)
            for term in group["terms"]
            if str(term).lower() in text
        ]
        if matched_terms:
            hits.append(
                {
                    "resource_type": str(group["resource_type"]),
                    "data_intent": str(group["data_intent"]),
                    "dataset": str(group["dataset"]),
                    "terms": sorted(matched_terms),
                }
            )
    return hits


def infer_data_intent(case: Mapping[str, Any]) -> str:
    """Synthesize a data_intent only when the Case semantics are unambiguous."""
    hits = infer_resource_intents(case)
    if len(hits) == 1:
        return str(hits[0]["data_intent"])
    return ""




def select_test_subject(
    candidates: list[Mapping[str, Any]], *, explicit_subject: str = ""
) -> dict[str, Any]:
    """Select a verified subject without silently changing an explicit Case constraint."""
    usable = [item for item in candidates if int(item.get("status", 0)) == 1]
    if explicit_subject:
        matches = [
            item
            for item in usable
            if explicit_subject in str(item.get("schemaName", ""))
            or explicit_subject == str(item.get("describeApiName", ""))
        ]
        if not matches:
            raise InputError(
                f"Explicit test subject is unavailable or disabled: {explicit_subject}"
            )
        return deepcopy(dict(matches[0]))

    for preferred in DEFAULT_SUBJECT_PRIORITY:
        for item in usable:
            if preferred in str(item.get("schemaName", "")):
                return deepcopy(dict(item))
    forbidden = [
        item
        for item in usable
        if any(
            name in str(item.get("schemaName", ""))
            for name in FORBIDDEN_DEFAULT_SUBJECTS
        )
    ]
    reason = "only forbidden fallback subjects are available" if forbidden else "no mainstream subject is available"
    raise InputError(f"Default test subject cannot be selected: {reason}")


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


def required_scene_for_case(case: Mapping[str, Any]) -> str:
    """Return the full UI/API asset scene required by the Case semantics."""
    test_data = case.get("test_data", {})
    if isinstance(test_data, Mapping) and test_data.get("required_scene"):
        return str(test_data["required_scene"])
    text = _case_text(case)
    return "chart_detail" if any(term in text for term in CHART_DETAIL_TERMS) else ""


def _is_composite_case(test_data: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    """A Case is composite when it carries a datasets/matrix payload or infers
    multiple resource types that no single-resource recipe should bind.

    A Case that explicitly declares a singular ``dataset`` targets one recipe
    even when its variants mention multiple resource types.
    """
    if any(key in test_data for key in ("datasets", "matrix")):
        return True
    if str(test_data.get("dataset", "")):
        return False
    return len(infer_resource_intents(case)) > 1


def _matches_recipe(case: Mapping[str, Any], recipe: Mapping[str, Any]) -> bool:
    match = recipe.get("match", {})
    if not isinstance(match, Mapping):
        raise ContractError(f"recipe {recipe.get('id')} match must be an object")
    test_data = case.get("test_data", {})
    if not isinstance(test_data, Mapping):
        test_data = {}

    # Composite Cases (datasets/matrix or multiple inferred resource types)
    # only match recipes that declare composite_term_groups.  This prevents a
    # single-resource recipe from fuzzy-binding a multi-resource Case.
    if _is_composite_case(test_data, case):
        composite_groups = match.get("composite_term_groups", [])
        if not composite_groups:
            return False
        text = _case_text(case)
        return all(
            isinstance(group, list) and any(str(term).lower() in text for term in group)
            for group in composite_groups
        )

    explicit_intent = ""
    if isinstance(test_data, Mapping):
        explicit_intent = str(test_data.get("data_intent", ""))
    if not explicit_intent:
        explicit_intent = infer_data_intent(case)
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
                    "requirement_name": str(case.get("requirement_name") or case.get("requirement") or case.get("title") or case_id),
                    "required_scene": required_scene_for_case(case),
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
                    "requirement_name": str(case.get("requirement_name") or case.get("requirement") or case.get("title") or case_id),
                    "required_scene": required_scene_for_case(case),
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
        if not requested_variants and isinstance(test_data, Mapping):
            structured_datasets = test_data.get("datasets", [])
            if isinstance(structured_datasets, list):
                requested_variants = [
                    str(item.get("type", ""))
                    for item in structured_datasets
                    if isinstance(item, Mapping) and str(item.get("type", ""))
                ]
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
                "requirement_name": str(case.get("requirement_name") or case.get("requirement") or case.get("title") or case_id),
                "required_scene": required_scene_for_case(case),
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



def _bind_chart_folder(resource: dict[str, Any], requirement_name: str) -> dict[str, Any]:
    """Set chart asset_folder_name and folder_binding.folder_name to the
    Case requirement_name so N27 folder-equals-requirement validation passes."""
    if resource.get("resource_type") == "stat_chart" and requirement_name:
        resource["asset_folder_name"] = requirement_name
        folder = resource.get("folder_binding")
        if isinstance(folder, dict):
            folder["folder_name"] = requirement_name
            resource["folder_binding"] = folder
    return resource


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
                    "requirement_name": str(item.get("requirement_name") or item.get("case_id", "")),
                    "required_scene": str(item.get("required_scene", "")),
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
        resources = [
            _bind_chart_folder(
                {
                    **resource,
                    "retention_mode": str(resource.get("retention_mode") or "retain"),
                    "ownership_namespace": namespace,
                },
                str(item.get("requirement_name") or item.get("title") or item.get("case_id", "")),
            )
            for resource in _topological_resources(
                list(recipe.get("resources", [])), recipe_id
            )
        ]
        retention_modes = {
            str(resource.get("retention_mode") or "retain") for resource in resources
        }
        # Case-level retention is delete only when every resource opts into delete;
        # mixed or empty graphs stay retain so N27/policy defaults remain safe.
        case_retention = "delete" if retention_modes == {"delete"} else "retain"
        case_plans.append(
            {
                "case_id": str(item.get("case_id", "")),
                "requirement_name": str(item.get("requirement_name") or item.get("title") or item.get("case_id", "")),
                "required_scene": str(item.get("required_scene", "")),
                "retention_mode": case_retention,
                "requires_data_construction": True,
                "planning_mode": "autonomous",
                "recipe_refs": [
                    {"recipe_id": recipe_id, "version": str(recipe.get("version", ""))}
                ],
                "evidence_refs": list(recipe.get("evidence_refs", [])),
                "variables": variables,
                "resources": resources,
            }
        )
    setup_actions = [
        {"case_id": case["case_id"], "resource_key": resource["resource_key"], **deepcopy(resource["setup"])}
        for case in case_plans for resource in case["resources"]
        if resource.get("lifecycle_mode", "create") == "create"
    ]
    readiness_checks = [
        {"case_id": case["case_id"], "resource_key": resource["resource_key"], **deepcopy(check)}
        for case in case_plans for resource in case["resources"] for check in resource.get("readiness", [])
    ]
    cleanup_actions = [
        {"case_id": case["case_id"], "resource_key": resource["resource_key"], **deepcopy(resource["cleanup"])}
        for case in case_plans for resource in reversed(case["resources"])
        if resource.get("retention_mode") == "delete"
    ]
    residue_checks = [
        {"case_id": case["case_id"], "resource_key": resource["resource_key"], **deepcopy(check)}
        for case in case_plans for resource in reversed(case["resources"])
        for check in resource.get("residue_checks", [])
    ]
    return {
        "schema_version": PLAN_CONTRACT,
        "lifecycle_schema_version": LIFECYCLE_CONTRACT,
        "environment": environment,
        "namespace": namespace,
        "planning_mode": "autonomous",
        "capability_catalog_hash": content_hash(catalog),
        "case_plans": case_plans,
        "paused_cases": list(intent.get("paused_cases", [])),
        "unresolved_requirements": list(intent.get("unresolved_requirements", [])),
        "resource_graph": [
            {"case_id": case["case_id"], "resource_key": resource["resource_key"],
             "depends_on": list(resource.get("depends_on", []))}
            for case in case_plans for resource in case["resources"]
        ],
        "setup_actions": setup_actions,
        "readiness_checks": readiness_checks,
        "runtime_variables": {
            case["case_id"]: sorted(case.get("variables", {})) for case in case_plans
        },
        "cleanup_actions": cleanup_actions,
        "retained_assets": [
            {
                "case_id": case["case_id"],
                "requirement_name": case.get("requirement_name", case["case_id"]),
                "resource_key": resource["resource_key"],
                "resource_type": resource["resource_type"],
                "resource_id_variable": resource["resource_id_variable"],
                "retention_mode": "retain",
            }
            for case in case_plans
            for resource in case["resources"]
            if resource.get("retention_mode") == "retain"
        ],
        "residue_checks": residue_checks,
        "unsupported_requirements": list(intent.get("unresolved_requirements", [])),
        "ready_for_execution": not intent.get("unresolved_requirements") and all(
            (
                bool(resource.get("discovery"))
                and bool(resource.get("readiness"))
                and bool(resource.get("existing_asset_evidence"))
            )
            if resource.get("lifecycle_mode") == "existing_read_only"
            else bool(resource.get("residue_checks"))
            for case in case_plans
            for resource in case["resources"]
        ),
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
    inventory_path: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Create hash-bound A22, N28 and N27 Artifacts from one frozen N25 output."""

    from .test_data import validate_test_data_plan

    security = security or SecurityPolicy()
    from .skill_registry import SkillRegistry, route_data_plan
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
    cases = (
        compiled_payload.get("compiled_cases", compiled_payload.get("child_cases"))
        if isinstance(compiled_payload, Mapping)
        else None
    )
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N25 compiled_cases or child_cases must be a list of objects")
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
    registry = SkillRegistry.from_file(policy_path.with_name("backend-skill-registry.json"))
    skill_authorization = route_data_plan(cases, catalog, registry)
    registry.validate_authorization(skill_authorization, agent_id="D01")
    identity = (
        str(compiled.get("workflow_run_id", "")),
        str(compiled.get("workflow_mode", "")),
        str(compiled.get("source_snapshot_id", "")),
    )
    if not all(identity):
        raise ContractError("N25 workflow identity is incomplete")
    intent_payload = extract_test_data_intents(cases, catalog)
    intent_payload["aggregate_agent_id"] = "D01"
    intent_payload["skill_router_binding"] = skill_authorization
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
    if inventory_path is not None:
        from .env_inventory import enrich_plan_with_inventory, load_inventory_snapshot

        inventory = load_inventory_snapshot(inventory_path)
        plan = enrich_plan_with_inventory(plan, inventory)
    plan["aggregate_agent_id"] = "D01"
    plan["skill_router_binding"] = skill_authorization
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
            "skill_router_binding": skill_authorization,
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
        "lifecycle_ready": bool(plan["ready_for_execution"]),
        "skill_registry_hash": registry.registry_hash,
    }
    store.write_json("autonomous-test-data-preparation.json", result)
    return result
