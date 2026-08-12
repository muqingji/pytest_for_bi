"""Build a conservative Test Knowledge Packet from approved deterministic inputs."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .contracts import content_hash
from .errors import ContractError


DETAIL_OPERATION_ID = "fs_bi_stat.stat_base.data_query_da655ba1"


def _find_operation(openapi: Mapping[str, Any], operation_id: str) -> tuple[str, str]:
    for path, methods in openapi.get("paths", {}).items():
        if not isinstance(methods, Mapping):
            continue
        for method, operation in methods.items():
            if isinstance(operation, Mapping) and operation.get("operationId") == operation_id:
                return str(method).upper(), str(path)
    raise ContractError(f"Frozen OpenAPI operation is missing: {operation_id}")


def _recipe_by_variant(catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for recipe in catalog.get("recipes", []):
        if not isinstance(recipe, Mapping):
            continue
        for variant in recipe.get("supported_variants", []):
            result[str(variant).lower()] = recipe
    return result


def _resources(recipe: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if recipe is None:
        return []
    result: list[dict[str, Any]] = []
    prefix = str(recipe.get("id", "recipe"))
    raw_resources = [item for item in recipe.get("resources", []) if isinstance(item, Mapping)]
    key_map = {str(item.get("resource_key", "")): f"{prefix}:{item.get('resource_key', '')}" for item in raw_resources}
    for resource in raw_resources:
        if not isinstance(resource, Mapping):
            continue
        readiness = deepcopy(resource.get("readiness"))
        if not readiness and resource.get("lifecycle_mode", "managed") == "managed":
            readiness = {
                "mode": "creation_response",
                "expect": deepcopy(resource.get("setup", {}).get("expect", {})),
            }
        result.append({
            "id": key_map[str(resource.get("resource_key", ""))],
            "depends_on": [key_map[str(item)] for item in resource.get("depends_on", [])],
            "lifecycle_mode": str(resource.get("lifecycle_mode", "managed")),
            "create_capability": deepcopy(resource.get("setup")),
            "readiness": readiness,
            "cleanup": deepcopy(resource.get("cleanup")),
            "residue_checks": deepcopy(resource.get("residue_checks", [])),
            "recipe_id": str(recipe.get("id", "")),
        })
    return result


def _variants(case: Mapping[str, Any]) -> list[str]:
    data = case.get("test_data", {})
    if not isinstance(data, Mapping):
        return []
    datasets = data.get("datasets")
    if isinstance(datasets, list):
        return [
            str(item.get("type", item.get("id", item.get("row_id", "")))).lower()
            for item in datasets
            if isinstance(item, Mapping)
        ]
    matrix = data.get("matrix")
    if isinstance(matrix, list):
        return [str(item.get("row_id", "")).lower() for item in matrix if isinstance(item, Mapping)]
    return []


def _oracles(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for expected in case.get("expected", []):
        if not isinstance(expected, Mapping):
            continue
        oracle = expected.get("oracle")
        if not isinstance(oracle, Mapping) or oracle.get("type") != "deterministic":
            continue
        result.append({
            "id": str(expected.get("id", "")),
            "type": "field",
            "path": str(oracle.get("observation_point", "")),
            "expected": deepcopy(oracle.get("expected_value")),
            "matcher": str(oracle.get("matcher", "")),
            "source_ref": str(oracle.get("source_ref", "")),
            "polarity": "positive",
        })
    # Every interface error Case must also prove that detail data was not leaked.
    if result:
        result.append({
            "id": f"{case.get('id')}-NO-DETAIL-LEAK",
            "type": "field",
            "path": "detail_api.detail_data",
            "expected": "absent",
            "matcher": "absent",
            "source_ref": str(result[0]["source_ref"]),
            "polarity": "negative",
        })
    return result


def _manual_obligations(case: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"id": str(item.get("id", "")), "description": str(item.get("description", ""))}
        for item in case.get("expected", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("oracle"), Mapping)
        and item["oracle"].get("type") != "deterministic"
    ]


def build_test_knowledge_packet(
    compiled_artifact: Mapping[str, Any],
    openapi: Mapping[str, Any],
    catalog: Mapping[str, Any],
    *,
    knowledge_snapshot_id: str,
) -> dict[str, Any]:
    payload = compiled_artifact.get("payload", compiled_artifact)
    cases = payload.get("compiled_cases") if isinstance(payload, Mapping) else None
    if not isinstance(cases, list):
        raise ContractError("Compiled artifact requires compiled_cases")
    method, path = _find_operation(openapi, DETAIL_OPERATION_ID)
    recipes = _recipe_by_variant(catalog)
    packet_cases: list[dict[str, Any]] = []
    for raw in cases:
        if not isinstance(raw, Mapping) or raw.get("layer") == "e2e":
            continue
        case = dict(raw)
        case_id = str(case.get("id", ""))
        variants = _variants(case)
        obligations: list[dict[str, str]] = []
        matched_recipes: list[Mapping[str, Any]] = []
        for variant in variants:
            aliases = {
                "aggregate": "aggregate_metric",
                "calculated": "calculated_metric",
            }
            recipe = recipes.get(variant) or recipes.get(aliases.get(variant, ""))
            obligations.append({
                "id": variant,
                "status": "ready" if recipe is not None else "deferred",
                "recipe_id": str(recipe.get("id", "")) if recipe else "",
            })
            if recipe is not None and recipe not in matched_recipes:
                matched_recipes.append(recipe)
        resources: list[dict[str, Any]] = []
        # Parent Cases remain deferred until one coherent recipe covers every variant.
        if variants and obligations and all(item["status"] == "ready" for item in obligations):
            for recipe in matched_recipes:
                resources.extend(_resources(recipe))
        packet_case = {
            "case_id": case_id,
            "source_refs": [
                {"source_id": "fs-bi-contract-c6b7853", "authority": "frozen_openapi", "contract_authority": True},
                {"source_id": "fs-bi-source", "authority": "current_code", "contract_authority": True},
                {"source_id": "bug-finder-diagnostic-knowledge", "authority": "historical_risk", "contract_authority": False},
            ],
            "execution_chain": {"operations": [{
                "operation_id": DETAIL_OPERATION_ID,
                "method": method,
                "path": path,
                "parameter_bindings": [
                    {"name": "id", "from": "data_recipe.schema_id"},
                    {"name": "measureFieldID", "from": "data_recipe.metric_field_id"},
                    {"name": "lan", "from": "case.locale"},
                ],
            }]},
            "data_recipe": {"resources": resources},
            "oracles": _oracles(case),
        }
        if obligations:
            packet_case["coverage_obligations"] = obligations
        manual = _manual_obligations(case)
        if manual:
            packet_case["manual_obligations"] = manual
        packet_cases.append(packet_case)
    packet = {
        "schema_version": "test-knowledge-packet/1.0",
        "knowledge_snapshot_id": knowledge_snapshot_id,
        "compiled_artifact_hash": str(compiled_artifact.get("artifact_hash", content_hash(payload))),
        "openapi_hash": content_hash(openapi),
        "capability_catalog_hash": content_hash(catalog),
        "cases": packet_cases,
    }
    packet["packet_content_hash"] = content_hash(packet)
    return packet
