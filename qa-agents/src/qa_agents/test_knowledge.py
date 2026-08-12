"""Deterministic Test Knowledge Packet validation and automation readiness."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .contracts import content_hash
from .errors import ContractError


PACKET_CONTRACT = "test-knowledge-packet/1.0"
READINESS_CONTRACT = "automation-knowledge-readiness/1.0"
CURRENT_AUTHORITIES = {"current_product_documentation", "current_code", "frozen_openapi"}
HISTORICAL_AUTHORITIES = {"historical_risk", "diagnostic_pattern"}


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_test_knowledge_packet(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != PACKET_CONTRACT:
        raise ContractError("Test Knowledge Packet schema_version is invalid")
    snapshot_id = value.get("knowledge_snapshot_id")
    if not _non_empty(snapshot_id):
        raise ContractError("Test Knowledge Packet requires knowledge_snapshot_id")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ContractError("Test Knowledge Packet requires cases")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(cases):
        if not isinstance(raw, Mapping):
            raise ContractError(f"cases[{index}] must be an object")
        case = deepcopy(dict(raw))
        case_id = str(case.get("case_id", "")).strip()
        if not case_id or case_id in seen:
            raise ContractError(f"cases[{index}].case_id must be unique and non-empty")
        seen.add(case_id)
        refs = case.get("source_refs")
        if not isinstance(refs, list) or not refs:
            raise ContractError(f"Case {case_id} requires source_refs")
        for ref_index, ref in enumerate(refs):
            if not isinstance(ref, Mapping):
                raise ContractError(f"Case {case_id} source_refs[{ref_index}] is invalid")
            if not _non_empty(ref.get("source_id")) or not _non_empty(ref.get("authority")):
                raise ContractError(f"Case {case_id} source reference is incomplete")
            if ref.get("authority") in HISTORICAL_AUTHORITIES and ref.get("contract_authority") is not False:
                raise ContractError(
                    f"Case {case_id} historical knowledge must set contract_authority=false"
                )
        normalized.append(case)
    return {
        "schema_version": "test-knowledge-packet-validation/1.0",
        "valid": True,
        "knowledge_snapshot_id": snapshot_id,
        "case_count": len(normalized),
        "packet_hash": content_hash(value),
        "cases": normalized,
    }


def _operation_gaps(case_id: str, operations: Any) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not isinstance(operations, list) or not operations:
        return [{"code": "execution_chain_missing", "path": f"cases.{case_id}.execution_chain"}]
    for index, operation in enumerate(operations):
        path = f"cases.{case_id}.execution_chain.operations[{index}]"
        if not isinstance(operation, Mapping):
            gaps.append({"code": "operation_invalid", "path": path})
            continue
        if operation.get("method") not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            gaps.append({"code": "operation_method_missing", "path": f"{path}.method"})
        if not _non_empty(operation.get("path")):
            gaps.append({"code": "operation_path_missing", "path": f"{path}.path"})
        if not _non_empty(operation.get("operation_id")):
            gaps.append({"code": "operation_contract_binding_missing", "path": f"{path}.operation_id"})
        bindings = operation.get("parameter_bindings")
        if not isinstance(bindings, list):
            gaps.append({"code": "parameter_bindings_missing", "path": f"{path}.parameter_bindings"})
    return gaps


def _data_gaps(case_id: str, data_recipe: Any) -> list[dict[str, str]]:
    path = f"cases.{case_id}.data_recipe"
    if not isinstance(data_recipe, Mapping):
        return [{"code": "data_recipe_missing", "path": path}]
    resources = data_recipe.get("resources")
    if not isinstance(resources, list) or not resources:
        return [{"code": "data_resources_missing", "path": f"{path}.resources"}]
    gaps: list[dict[str, str]] = []
    ids: set[str] = set()
    for index, resource in enumerate(resources):
        item_path = f"{path}.resources[{index}]"
        if not isinstance(resource, Mapping):
            gaps.append({"code": "data_resource_invalid", "path": item_path})
            continue
        resource_id = str(resource.get("id", ""))
        if not resource_id or resource_id in ids:
            gaps.append({"code": "data_resource_id_invalid", "path": f"{item_path}.id"})
        ids.add(resource_id)
        lifecycle_mode = str(resource.get("lifecycle_mode", "managed"))
        if lifecycle_mode not in {"managed", "existing_read_only"}:
            gaps.append({"code": "data_resource_lifecycle_invalid", "path": f"{item_path}.lifecycle_mode"})
        for field, code in (
            ("create_capability", "create_capability_missing"),
            ("readiness", "readiness_check_missing"),
            ("cleanup", "cleanup_capability_missing"),
        ):
            if lifecycle_mode == "existing_read_only" and field in {"create_capability", "cleanup"}:
                continue
            if not resource.get(field):
                gaps.append({"code": code, "path": f"{item_path}.{field}"})
    for index, resource in enumerate(resources):
        if not isinstance(resource, Mapping):
            continue
        unknown = set(map(str, resource.get("depends_on", []))) - ids
        if unknown:
            gaps.append({"code": "data_dependency_unknown", "path": f"{path}.resources[{index}].depends_on"})
    dependencies = {
        str(resource.get("id")): set(map(str, resource.get("depends_on", [])))
        for resource in resources
        if isinstance(resource, Mapping) and str(resource.get("id", ""))
    }
    pending = {resource_id: values & ids for resource_id, values in dependencies.items()}
    while pending:
        ready = {resource_id for resource_id, values in pending.items() if not values}
        if not ready:
            gaps.append({"code": "data_dependency_cycle", "path": f"{path}.resources"})
            break
        pending = {
            resource_id: values - ready
            for resource_id, values in pending.items()
            if resource_id not in ready
        }
    return gaps


def _oracle_gaps(case_id: str, oracles: Any) -> list[dict[str, str]]:
    path = f"cases.{case_id}.oracles"
    if not isinstance(oracles, list) or not oracles:
        return [{"code": "oracle_missing", "path": path}]
    gaps: list[dict[str, str]] = []
    has_business_field = False
    has_negative = False
    for index, oracle in enumerate(oracles):
        item_path = f"{path}[{index}]"
        if not isinstance(oracle, Mapping):
            gaps.append({"code": "oracle_invalid", "path": item_path})
            continue
        if oracle.get("type") == "field":
            has_business_field = True
            if not _non_empty(oracle.get("path")) or "expected" not in oracle:
                gaps.append({"code": "field_oracle_incomplete", "path": item_path})
        if oracle.get("polarity") == "negative":
            has_negative = True
        if not _non_empty(oracle.get("source_ref")):
            gaps.append({"code": "oracle_source_missing", "path": f"{item_path}.source_ref"})
    if not has_business_field:
        gaps.append({"code": "business_field_oracle_missing", "path": path})
    if not has_negative:
        gaps.append({"code": "negative_oracle_missing", "path": path})
    return gaps


def _coverage_gaps(case_id: str, obligations: Any) -> list[dict[str, str]]:
    if obligations is None:
        return []
    path = f"cases.{case_id}.coverage_obligations"
    if not isinstance(obligations, list) or not obligations:
        return [{"code": "coverage_obligations_invalid", "path": path}]
    gaps: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, obligation in enumerate(obligations):
        item_path = f"{path}[{index}]"
        if not isinstance(obligation, Mapping):
            gaps.append({"code": "coverage_obligation_invalid", "path": item_path})
            continue
        obligation_id = str(obligation.get("id", ""))
        if not obligation_id or obligation_id in seen:
            gaps.append({"code": "coverage_obligation_id_invalid", "path": f"{item_path}.id"})
        seen.add(obligation_id)
        if obligation.get("status") != "ready":
            gaps.append({"code": "coverage_obligation_not_ready", "path": item_path})
    return gaps


def _manual_gaps(case_id: str, obligations: Any) -> list[dict[str, str]]:
    if obligations is None:
        return []
    if not isinstance(obligations, list):
        return [{"code": "manual_obligations_invalid", "path": f"cases.{case_id}.manual_obligations"}]
    return [
        {"code": "manual_obligation_not_automatable", "path": f"cases.{case_id}.manual_obligations[{index}]"}
        for index, _ in enumerate(obligations)
    ]


def assess_automation_readiness(
    packet: Mapping[str, Any], compiled_case_ids: set[str]
) -> dict[str, Any]:
    validation = validate_test_knowledge_packet(packet)
    results: list[dict[str, Any]] = []
    packet_ids = {str(case["case_id"]) for case in validation["cases"]}
    for case_id in sorted(compiled_case_ids | packet_ids):
        case = next((item for item in validation["cases"] if item["case_id"] == case_id), None)
        gaps: list[dict[str, str]] = []
        if case_id not in compiled_case_ids:
            gaps.append({"code": "compiled_case_missing", "path": f"cases.{case_id}"})
        if case is None:
            gaps.append({"code": "knowledge_packet_case_missing", "path": f"cases.{case_id}"})
        else:
            authorities = {str(ref.get("authority")) for ref in case["source_refs"]}
            if not authorities & CURRENT_AUTHORITIES:
                gaps.append({"code": "current_contract_evidence_missing", "path": f"cases.{case_id}.source_refs"})
            gaps.extend(_operation_gaps(case_id, case.get("execution_chain", {}).get("operations")))
            gaps.extend(_data_gaps(case_id, case.get("data_recipe")))
            gaps.extend(_oracle_gaps(case_id, case.get("oracles")))
            gaps.extend(_coverage_gaps(case_id, case.get("coverage_obligations")))
            gaps.extend(_manual_gaps(case_id, case.get("manual_obligations")))
        results.append({"case_id": case_id, "status": "ready" if not gaps else "deferred", "gaps": gaps})
    ready = [item["case_id"] for item in results if item["status"] == "ready"]
    deferred = [item["case_id"] for item in results if item["status"] == "deferred"]
    return {
        "schema_version": READINESS_CONTRACT,
        "knowledge_snapshot_id": validation["knowledge_snapshot_id"],
        "packet_hash": validation["packet_hash"],
        "status": "ready" if not deferred else "deferred",
        "ready_case_ids": ready,
        "deferred_case_ids": deferred,
        "cases": results,
    }
