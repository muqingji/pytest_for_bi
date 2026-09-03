"""A22 test-data planning and deterministic N27 safety validation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .agents.base import AgentContext, AgentOutput, BaseAgent
from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
)
from .errors import ContractError, InputError, SecurityPolicyError
from .security import SecurityPolicy
from .storage import ArtifactStore
from .data_integrity import (
    integrity_evidence_valid,
    required_validity_contract,
    validate_integrity_probe_plan,
    validate_validity_contract,
)


PLAN_CONTRACT = "test-data-plan/1.0"
PAUSED_UNIT_REASON = "paused_existing_developer_unit_coverage"
POLICY_SKIP_REASON = "test_data_agent_paused_by_policy"
_NAMESPACE = re.compile(r"^qa-[a-z0-9][a-z0-9-]{5,80}$")
_CREATE_HINTS = (
    "创建",
    "新建",
    "构造",
    "create",
    "prepare",
    "统计图",
    "拼表",
    "交叉表",
    "驾驶舱",
    "指标",
    "主题",
)
_SECRET_KEYS = {"password", "token", "secret", "authorization", "cookie"}
_CJK = re.compile(r"[\u4e00-\u9fff]")
_NAMED_BUSINESS_RESOURCES = {
    "aggregate_metric", "calculated_metric", "stat_schema", "crm_field", "custom_dimension"
}
_CHART_RESOURCES = {"stat_chart", "joined_report", "pivot_table", "report"}
_CHART_DETAIL_CLOSURE_ROLES = {
    "source_field",
    "metric_or_dimension",
    "requirement_folder",
    "chart_or_pivot",
    "view_readiness",
    "detail_entry_execution",
}
_ENUM_FIELD_TYPE_HINTS = ("enum", "select", "option", "bpm", "boolean", "bool")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _validate_joined_table_create(
    resource: Mapping[str, Any], setup: Mapping[str, Any], path: str
) -> None:
    if resource.get("resource_type") != "joined_table":
        return
    if _operation_id(setup, path) != "fs_bi_dev.lwt_manager.save":
        raise SecurityPolicyError(f"{path} joined table must use the controlled save operation")
    request = setup.get("request", {})
    body = request.get("json", {}) if isinstance(request, Mapping) else {}
    if not isinstance(body, Mapping) or body.get("saveType") != 0:
        raise SecurityPolicyError(f"{path} joined table must be a create-only save")
    lwt = body.get("lwtArgs")
    query = body.get("queryLwtArg")
    if not isinstance(lwt, Mapping) or not isinstance(query, Mapping):
        raise ContractError(f"{path} joined table requires lwtArgs and queryLwtArg")
    if str(lwt.get("lwtId", "")) or str(query.get("id", "")):
        raise SecurityPolicyError(f"{path} joined table create IDs must be empty")
    requirement_name = str(resource.get("requirement_name", ""))
    if not requirement_name or resource.get("asset_folder_name") != requirement_name:
        raise SecurityPolicyError(f"{path} joined table folder must equal requirement name")
    evidence = setup.get("live_discovery_evidence")
    if not isinstance(evidence, Mapping):
        raise SecurityPolicyError(f"{path} joined table requires live discovery evidence")
    for key in ("folder", "topology", "identity"):
        item = evidence.get(key)
        if not isinstance(item, Mapping) or _SHA256.fullmatch(
            str(item.get("response_hash", ""))
        ) is None:
            raise SecurityPolicyError(f"{path} joined table {key} evidence is invalid")
    folder = evidence["folder"]
    if folder.get("name") != requirement_name or str(folder.get("id")) != str(body.get("categoryID")):
        raise SecurityPolicyError(f"{path} joined table folder binding does not match live evidence")
    sources = lwt.get("dataSources", [])
    relations = lwt.get("relations", [])
    fields = lwt.get("displayFields", [])
    if not isinstance(sources, list) or len(sources) < 2 or not relations or not fields:
        raise SecurityPolicyError(f"{path} joined table topology is incomplete")
    source_ids = {str(item.get("id")) for item in sources if isinstance(item, Mapping) and item.get("id")}
    if len(source_ids) != len(sources):
        raise SecurityPolicyError(f"{path} joined table source IDs are missing or duplicated")
    for field in fields:
        if not isinstance(field, Mapping) or str(field.get("dataSourceId")) not in source_ids:
            raise SecurityPolicyError(f"{path} joined table output field has no selected source")
    for relation in relations:
        if not isinstance(relation, Mapping):
            raise SecurityPolicyError(f"{path} joined table relation is invalid")
        endpoints = {str(relation.get("leftDataSourceId")), str(relation.get("rightDataSourceId"))}
        if endpoints - source_ids or not relation.get("leftFieldId") or not relation.get("rightFieldId"):
            raise SecurityPolicyError(f"{path} joined table relation is not live-bound")


def _walk_filter_objects(value: Any, path: str) -> list[tuple[str, Mapping[str, Any]]]:
    found: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(value, Mapping):
        keys = {str(key) for key in value}
        if "value1" in keys and ("fieldId" in keys or "fieldID" in keys):
            found.append((path, value))
        for key, child in value.items():
            found.extend(_walk_filter_objects(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_filter_objects(child, f"{path}[{index}]"))
    return found


def _is_enum_filter(filter_value: Mapping[str, Any]) -> bool:
    value_kind = str(filter_value.get("value_kind", "")).strip().lower()
    if value_kind:
        return value_kind in {"enum", "business_enum", "option"}
    field_types = " ".join(
        str(filter_value.get(key, "")).lower()
        for key in ("fieldType", "subFieldType", "originalType")
    )
    return any(hint in field_types for hint in _ENUM_FIELD_TYPE_HINTS)


def _option_codes(value: Any, path: str) -> set[str]:
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise SecurityPolicyError(f"{path}.value1 must contain optionCode objects") from error
    if not isinstance(parsed, list) or not parsed:
        raise SecurityPolicyError(f"{path}.value1 must contain non-empty optionCode objects")
    codes: set[str] = set()
    for index, item in enumerate(parsed):
        if not isinstance(item, Mapping) or not str(item.get("optionCode", "")).strip():
            raise SecurityPolicyError(
                f"{path}.value1[{index}] is a handwritten enum value without optionCode"
            )
        codes.add(str(item["optionCode"]))
    return codes


def _validate_enum_provenance(
    setup: Mapping[str, Any], path: str, approved_operations: set[str]
) -> int:
    request = setup.get("request", {})
    request_json = request.get("json", {}) if isinstance(request, Mapping) else {}
    filters = [item for item in _walk_filter_objects(request_json, f"{path}.request.json") if _is_enum_filter(item[1])]
    if not filters:
        return 0
    bindings = setup.get("enum_option_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise SecurityPolicyError(f"{path} enum filters require enum_option_bindings")
    validated = 0
    for filter_path, filter_value in filters:
        field_id = str(filter_value.get("fieldId") or filter_value.get("fieldID") or "")
        matches = [item for item in bindings if isinstance(item, Mapping) and str(item.get("field_id", "")) == field_id]
        if len(matches) != 1:
            raise SecurityPolicyError(f"{filter_path} requires exactly one binding for field {field_id!r}")
        binding = matches[0]
        operation = str(binding.get("option_query_operation", ""))
        if operation not in approved_operations:
            raise SecurityPolicyError(f"{filter_path} option query operation is not approved")
        if _SHA256.fullmatch(str(binding.get("option_response_hash", ""))) is None:
            raise SecurityPolicyError(f"{filter_path} requires a valid option response hash")
        if not str(binding.get("response_json_path", "")).strip():
            raise SecurityPolicyError(f"{filter_path} requires option response_json_path")
        selected = binding.get("selected_option_codes")
        available = binding.get("queried_option_codes")
        if not isinstance(selected, list) or not selected or not isinstance(available, list) or not available:
            raise SecurityPolicyError(f"{filter_path} requires selected and queried option codes")
        selected_codes = {str(item) for item in selected if str(item)}
        available_codes = {str(item) for item in available if str(item)}
        request_codes = _option_codes(filter_value.get("value1"), filter_path)
        if not selected_codes or not selected_codes <= available_codes:
            raise SecurityPolicyError(f"{filter_path} selected option was not returned by the option query")
        if request_codes != selected_codes:
            raise SecurityPolicyError(f"{filter_path} request option codes do not match its binding")
        validated += 1
    return validated


def _validate_custom_dimension_enum_provenance(
    setup: Mapping[str, Any], path: str, approved_operations: set[str]
) -> int:
    request = setup.get("request", {})
    body = request.get("json", {}) if isinstance(request, Mapping) else {}
    if not isinstance(body, Mapping) or body.get("customType") != "enum_group":
        return 0
    raw_config = body.get("dimensionConfig")
    try:
        config = json.loads(raw_config) if isinstance(raw_config, str) else raw_config
    except json.JSONDecodeError as error:
        raise SecurityPolicyError(f"{path}.request.json.dimensionConfig is invalid JSON") from error
    if not isinstance(config, Mapping):
        raise SecurityPolicyError(f"{path}.request.json.dimensionConfig must be an object")
    requested_codes = {
        str(code)
        for group in config.get("groups", [])
        if isinstance(group, Mapping) and not group.get("isNotGrouped")
        for code in group.get("values", [])
        if str(code)
    }
    if not requested_codes:
        raise SecurityPolicyError(f"{path} enum_group requires live option codes")
    bindings = setup.get("enum_option_bindings")
    if not isinstance(bindings, list) or len(bindings) != 1 or not isinstance(bindings[0], Mapping):
        raise SecurityPolicyError(f"{path} enum_group requires exactly one enum_option_binding")
    binding = bindings[0]
    source = body.get("sourceDimension") or body.get("sourceField") or {}
    source_field_id = str(source.get("fieldId", "")) if isinstance(source, Mapping) else ""
    if not source_field_id or str(binding.get("field_id", "")) != source_field_id:
        raise SecurityPolicyError(f"{path} enum_group binding must match its source field")
    operation = str(binding.get("option_query_operation", ""))
    if operation not in approved_operations:
        raise SecurityPolicyError(f"{path} enum_group option query operation is not approved")
    if _SHA256.fullmatch(str(binding.get("option_response_hash", ""))) is None:
        raise SecurityPolicyError(f"{path} enum_group requires a valid option response hash")
    if not str(binding.get("response_json_path", "")).strip():
        raise SecurityPolicyError(f"{path} enum_group requires option response_json_path")
    queried = {str(code) for code in binding.get("queried_option_codes", []) if str(code)}
    selected = {str(code) for code in binding.get("selected_option_codes", []) if str(code)}
    if requested_codes != selected or not selected <= queried:
        raise SecurityPolicyError(f"{path} enum_group values were not returned by its option query")
    return 1


def _is_unit_case(case: Mapping[str, Any]) -> bool:
    level = str(case.get("test_level", "") or "").strip().lower()
    return level in {"unit", "unit_test", "单元", "单元测试"}


def _requires_constructed_data(case: Mapping[str, Any]) -> bool:
    if case.get("setup") or case.get("resource_requirements"):
        return True
    test_data = case.get("test_data")
    if isinstance(test_data, Mapping) and test_data.get("resource_requirements"):
        return True
    text = json.dumps(
        {
            "preconditions": case.get("preconditions", []),
            "test_data": test_data or {},
            "steps": case.get("steps", []),
        },
        ensure_ascii=False,
    ).lower()
    return any(hint in text for hint in _CREATE_HINTS)


class TestDataPlannerAgent(BaseAgent):
    """Plan isolated 112 resources for later creation by the execution Runner."""

    agent_id = "A22"
    profile_version = "1.0.0"
    output_name = "test-data-plan"
    output_contract = PLAN_CONTRACT
    runtime = "test-data-planning-runtime"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        environment = str(inputs.get("environment", ""))
        namespace = str(inputs.get("namespace", ""))
        cases = inputs.get("cases", [])
        if not isinstance(cases, list):
            raise ContractError("A22 cases must be a list")

        case_plans: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        paused: list[dict[str, str]] = []
        for raw_case in cases:
            if not isinstance(raw_case, Mapping):
                raise ContractError("A22 cases must contain objects")
            case = dict(raw_case)
            case_id = str(case.get("id", ""))
            if not case_id:
                raise ContractError("A22 Case requires id")
            if _is_unit_case(case):
                paused.append({"case_id": case_id, "reason_code": PAUSED_UNIT_REASON})
                continue
            test_data = case.get("test_data", {})
            requirements = case.get("resource_requirements")
            if requirements is None and isinstance(test_data, Mapping):
                requirements = test_data.get("resource_requirements")
            if requirements is None and case.get("setup"):
                setup_steps = case.get("setup", [])
                cleanup_steps = case.get("cleanup", [])
                if (
                    isinstance(test_data, Mapping)
                    and isinstance(setup_steps, list)
                    and len(setup_steps) == 1
                    and isinstance(cleanup_steps, list)
                    and len(cleanup_steps) == 1
                    and isinstance(setup_steps[0], Mapping)
                    and isinstance(cleanup_steps[0], Mapping)
                ):
                    extract = setup_steps[0].get("extract", {})
                    id_variable = str(test_data.get("resource_id_variable", ""))
                    if not id_variable and isinstance(extract, Mapping) and len(extract) == 1:
                        id_variable = str(next(iter(extract)))
                    requirements = [
                        {
                            "resource_key": str(test_data.get("resource_key", "resource")),
                            "resource_type": str(test_data.get("resource_type", "")),
                            "resource_id_variable": id_variable,
                            "setup": deepcopy(setup_steps[0]),
                            "readiness": deepcopy(case.get("readiness", [])),
                            "cleanup": deepcopy(cleanup_steps[0]),
                        }
                    ]
            if requirements is None:
                requirements = []
            if not isinstance(requirements, list):
                raise ContractError(f"A22 Case {case_id} resource_requirements must be a list")
            if _requires_constructed_data(case) and not requirements:
                unresolved.append(
                    {
                        "case_id": case_id,
                        "reason_code": "test_data_operations_not_resolved",
                        "required_capability": "model_or_domain_template",
                    }
                )
            planned_resources = deepcopy(requirements)
            for resource in planned_resources:
                if isinstance(resource, dict) and str(resource.get("resource_type")) in _CHART_RESOURCES:
                    resource.setdefault(
                        "validity_contract",
                        required_validity_contract(str(resource.get("resource_type"))),
                    )
            case_plans.append(
                {
                    "case_id": case_id,
                    "requires_data_construction": bool(requirements),
                    "resources": planned_resources,
                }
            )

        payload = {
            "schema_version": PLAN_CONTRACT,
            "environment": environment,
            "namespace": namespace,
            "case_plans": case_plans,
            "paused_cases": paused,
            "unresolved_requirements": unresolved,
        }
        if unresolved:
            return AgentOutput(
                payload=payload,
                status=ArtifactStatus.NEEDS_HUMAN,
                reason_code="test_data_plan_incomplete",
            )
        return AgentOutput(payload=payload)


def _operation_id(operation: Mapping[str, Any], path: str) -> str:
    request = operation.get("request")
    if not isinstance(request, Mapping):
        raise ContractError(f"{path}.request must be an object")
    operation_id = str(request.get("api", ""))
    if not operation_id:
        raise ContractError(f"{path}.request.api is required")
    return operation_id


def _assert_no_inline_secrets(value: Any, path: str = "plan") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _SECRET_KEYS and child not in (None, "", []):
                raise SecurityPolicyError(f"{path}.{key} contains an inline credential")
            _assert_no_inline_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_inline_secrets(child, f"{path}[{index}]")


def _validate_planning_level_resource(
    resource: Mapping[str, Any],
    path: str,
    *,
    pairs: Mapping[str, Any],
    readiness_operations: set[str],
    default_retention: str,
) -> None:
    """Validate the A22 Agent planning-level resource contract.

    The Multica A22 Agent names operations (``setup_operation``) instead of
    embedding full request/expect operation objects; request-level details are
    enforced later by N07/N08 against live schemas. N27 still enforces the
    security-relevant structure: allowed types, operation pairs, retention
    mode, read-only discovery for existing assets and run-namespace binding.
    """

    setup_operation = str(resource.get("setup_operation", ""))
    retention_mode = str(resource.get("retention_mode", default_retention))
    lifecycle_mode = str(resource.get("lifecycle_mode", "create"))
    if lifecycle_mode == "existing_read_only":
        if setup_operation not in readiness_operations:
            raise SecurityPolicyError(
                f"{path} existing_read_only setup_operation must be a read-only operation"
            )
        return
    if lifecycle_mode != "create":
        raise SecurityPolicyError(f"{path}.lifecycle_mode is invalid")
    if setup_operation not in pairs:
        raise SecurityPolicyError(f"{path}.setup_operation is not an allowed setup operation")
    if retention_mode not in {"delete", "retain"}:
        raise SecurityPolicyError(f"{path}.retention_mode is invalid")
    if retention_mode == "delete":
        cleanup_operation = str(pairs.get(setup_operation, ""))
        if not cleanup_operation:
            raise SecurityPolicyError(
                f"{path} delete mode requires a cleanup operation pair for {setup_operation!r}"
            )


def validate_test_data_plan(
    plan: Mapping[str, Any], policy: Mapping[str, Any]
) -> dict[str, Any]:
    """N27 rejects unsafe or non-recoverable plans before 112 execution."""

    if plan.get("schema_version") != PLAN_CONTRACT:
        raise ContractError("test-data plan schema_version is invalid")
    if policy.get("schema_version") != "test-data-policy/1.0":
        raise ContractError("test-data policy schema_version is invalid")
    environment = str(plan.get("environment", ""))
    allowed_environments = {str(item) for item in policy.get("allowed_environments", [])}
    if environment not in allowed_environments:
        raise SecurityPolicyError(f"test-data writes are not allowed in environment {environment!r}")
    namespace = str(plan.get("namespace", ""))
    if not _NAMESPACE.fullmatch(namespace):
        raise SecurityPolicyError("test-data namespace is missing or invalid")
    _assert_no_inline_secrets(plan)
    autonomous = plan.get("planning_mode") == "autonomous"
    if autonomous:
        catalog_hash = str(plan.get("capability_catalog_hash", ""))
        if re.fullmatch(r"sha256:[0-9a-f]{64}", catalog_hash) is None:
            raise ContractError("autonomous test-data plan requires capability_catalog_hash")

    pairs = policy.get("operation_pairs", {})
    if not isinstance(pairs, Mapping):
        raise ContractError("test-data policy operation_pairs must be an object")
    phase_permissions = policy.get("phase_permissions", {})
    if phase_permissions != {
        "setup": "write",
        "readiness": "read_only",
        "cleanup": "disabled",
        "retention_verification": "read_only",
    }:
        raise ContractError(
            "test-data policy must allow setup/cleanup writes and keep readiness read-only"
        )
    readiness_operations = {
        str(item) for item in policy.get("readiness_operations", [])
    }
    enum_option_operations = {
        str(item) for item in policy.get("enum_option_operations", [])
    }
    allowed_types = {str(item) for item in policy.get("resource_types", [])}
    unsupported_case_ids = {
        str(item.get("case_id") or "")
        for item in plan.get("unsupported_requirements", [])
        if isinstance(item, Mapping)
    }
    validated_resources = 0
    for case_index, case_plan in enumerate(plan.get("case_plans", [])):
        if not isinstance(case_plan, Mapping):
            raise ContractError(f"case_plans[{case_index}] must be an object")
        resources = case_plan.get("resources", [])
        if not isinstance(resources, list):
            raise ContractError(f"case_plans[{case_index}].resources must be a list")
        if autonomous and resources:
            recipe_refs = case_plan.get("recipe_refs")
            evidence_refs = case_plan.get("evidence_refs")
            if not isinstance(recipe_refs, list) or not recipe_refs:
                raise ContractError(
                    f"case_plans[{case_index}] autonomous resources require recipe_refs"
                )
            if not isinstance(evidence_refs, list) or not evidence_refs:
                raise ContractError(
                    f"case_plans[{case_index}] autonomous resources require evidence_refs"
                )
        if (
            case_plan.get("required_scene") == "chart_detail"
            and str(case_plan.get("case_id") or "") not in unsupported_case_ids
        ):
            roles = {
                str(role)
                for resource in resources
                if isinstance(resource, Mapping)
                for role in resource.get("scene_roles", [])
            }
            missing_roles = sorted(_CHART_DETAIL_CLOSURE_ROLES - roles)
            if missing_roles:
                raise SecurityPolicyError(
                    f"case_plans[{case_index}] chart_detail scene closure is incomplete; "
                    f"missing roles: {', '.join(missing_roles)}"
                )
        seen_keys: set[str] = set()
        for resource_index, resource in enumerate(resources):
            path = f"case_plans[{case_index}].resources[{resource_index}]"
            if not isinstance(resource, Mapping):
                raise ContractError(f"{path} must be an object")
            resource_key = str(resource.get("resource_key", ""))
            resource_type = str(resource.get("resource_type", ""))
            id_variable = str(resource.get("resource_id_variable", ""))
            if not resource_key or resource_key in seen_keys:
                raise ContractError(f"{path}.resource_key must be unique and non-empty")
            seen_keys.add(resource_key)
            if resource_type not in allowed_types:
                raise SecurityPolicyError(f"{path}.resource_type is not allowed")
            if not id_variable:
                raise ContractError(f"{path}.resource_id_variable is required")
            if resource_type in _CHART_RESOURCES:
                if (
                    str(resource.get("retention_mode", "retain")) == "retain"
                    and resource.get("asset_folder_name")
                    != str(case_plan.get("requirement_name", ""))
                ):
                    raise SecurityPolicyError(
                        f"{path} chart folder must equal the requirement name"
                    )
                validate_validity_contract(
                    resource.get("validity_contract"), resource_type=resource_type, path=path
                )
                if str(resource.get("lifecycle_mode", "create")) == "create":
                    validate_integrity_probe_plan(resource.get("integrity_probes"), path=path)
            setup_operation = resource.get("setup_operation")
            if isinstance(setup_operation, str) and setup_operation.strip():
                _validate_planning_level_resource(
                    resource,
                    path,
                    pairs=pairs,
                    readiness_operations=readiness_operations,
                    default_retention=str(policy.get("default_retention_mode", "retain")),
                )
                validated_resources += 1
                continue
            setup = resource.get("setup")
            cleanup = resource.get("cleanup")
            retention_mode = str(resource.get("retention_mode", "retain"))
            lifecycle_mode = str(resource.get("lifecycle_mode", "create"))
            if lifecycle_mode == "existing_read_only":
                if setup is not None or cleanup is not None:
                    raise SecurityPolicyError(
                        f"{path} existing_read_only resource cannot define setup or cleanup"
                    )
                discovery = resource.get("discovery")
                if not isinstance(discovery, Mapping):
                    raise SecurityPolicyError(
                        f"{path} existing_read_only resource requires discovery"
                    )
                discovery_id = _operation_id(discovery, f"{path}.discovery")
                if discovery_id not in readiness_operations:
                    raise SecurityPolicyError(
                        f"{path}.discovery must use a read-only operation"
                    )
                evidence = resource.get("existing_asset_evidence")
                if not isinstance(evidence, Mapping):
                    raise SecurityPolicyError(
                        f"{path} existing_read_only resource requires existing_asset_evidence"
                    )
                if evidence.get("live_readback_status") != "succeeded":
                    raise SecurityPolicyError(f"{path} existing asset live readback is not proven")
                if resource_type in _CHART_RESOURCES and not integrity_evidence_valid(
                    evidence.get("integrity_evidence")
                ):
                    raise SecurityPolicyError(f"{path} existing asset integrity is not proven")
                if re.fullmatch(
                    r"sha256:[0-9a-f]{64}", str(evidence.get("configuration_hash", ""))
                ) is None:
                    raise SecurityPolicyError(
                        f"{path} existing asset requires a valid configuration hash"
                    )
                if evidence.get("historical_required"):
                    if evidence.get("evidence_level") not in {
                        "database_created_at_and_live_readback",
                        "historical_candidate_verified_by_id_timestamp_and_live_readback",
                    }:
                        raise SecurityPolicyError(
                            f"{path} historical asset evidence level is insufficient"
                        )
                    if not str(evidence.get("observed_created_at", "")) or not str(
                        evidence.get("requirement_baseline_at", "")
                    ):
                        raise SecurityPolicyError(
                            f"{path} historical asset requires timestamp and requirement baseline"
                        )
                readiness = resource.get("readiness", [])
                if not isinstance(readiness, list) or not readiness:
                    raise SecurityPolicyError(
                        f"{path} existing_read_only resource requires online readiness checks"
                    )
                for check_index, check in enumerate(readiness):
                    check_id = _operation_id(check, f"{path}.readiness[{check_index}]")
                    if check_id not in readiness_operations:
                        raise SecurityPolicyError(
                            f"{path}.readiness[{check_index}] operation is not read-only"
                        )
                validated_resources += 1
                continue
            if lifecycle_mode != "create":
                raise SecurityPolicyError(f"{path}.lifecycle_mode is invalid")
            if not isinstance(setup, Mapping):
                raise SecurityPolicyError(f"{path} requires a setup operation")
            setup_id = _operation_id(setup, f"{path}.setup")
            _validate_joined_table_create(resource, setup, f"{path}.setup")
            _validate_enum_provenance(setup, f"{path}.setup", enum_option_operations)
            _validate_custom_dimension_enum_provenance(
                setup, f"{path}.setup", enum_option_operations
            )
            if retention_mode == "delete":
                if not isinstance(cleanup, Mapping):
                    raise SecurityPolicyError(f"{path} delete mode requires cleanup")
                cleanup_id = _operation_id(cleanup, f"{path}.cleanup")
                if str(pairs.get(setup_id, "")) != cleanup_id:
                    raise SecurityPolicyError(
                        f"{path} operation pair {setup_id!r} -> {cleanup_id!r} is not allowed"
                    )
            elif retention_mode != "retain":
                raise SecurityPolicyError(f"{path}.retention_mode is invalid")
            extract = setup.get("extract")
            if not isinstance(extract, Mapping) or id_variable not in extract:
                raise ContractError(f"{path}.setup must extract {id_variable!r}")
            cleanup_text = json.dumps(cleanup, ensure_ascii=False) if cleanup else ""
            if retention_mode == "delete" and f"{{{{ {id_variable} }}}}" not in cleanup_text:
                raise SecurityPolicyError(
                    f"{path}.cleanup must target the extracted resource id"
                )
            setup_text = json.dumps(setup, ensure_ascii=False)
            ownership_namespace = str(resource.get("ownership_namespace", ""))
            if f"{{{{ namespace }}}}" not in setup_text and ownership_namespace != namespace:
                raise SecurityPolicyError(
                    f"{path} must bind the run namespace as hidden ownership metadata"
                )
            if retention_mode == "retain" and resource_type in _NAMED_BUSINESS_RESOURCES:
                display_name = str(resource.get("display_name", ""))
                field_type = str(resource.get("source_field_type", ""))
                if not _CJK.search(display_name) or not field_type:
                    raise SecurityPolicyError(
                        f"{path} requires typed Chinese semantic naming evidence"
                    )
            if retention_mode == "retain" and resource_type in _CHART_RESOURCES:
                requirement_name = str(case_plan.get("requirement_name", ""))
                if not requirement_name or resource.get("asset_folder_name") != requirement_name:
                    raise SecurityPolicyError(
                        f"{path} chart folder must equal the requirement name"
                    )
            if resource_type == "stat_chart":
                folder = resource.get("folder_binding")
                if not isinstance(folder, Mapping):
                    raise SecurityPolicyError(f"{path} chart requires live folder binding")
                requirement_name = str(case_plan.get("requirement_name", ""))
                if str(folder.get("folder_name", "")) != requirement_name:
                    raise SecurityPolicyError(f"{path} chart folder binding name mismatch")
                category_id = str(folder.get("category_id", ""))
                if not category_id or not str(folder.get("folder_query_operation", "")):
                    raise SecurityPolicyError(f"{path} chart folder discovery is incomplete")
                if _SHA256.fullmatch(str(folder.get("folder_response_hash", ""))) is None:
                    raise SecurityPolicyError(f"{path} chart folder response hash is invalid")
                if _SHA256.fullmatch(str(resource.get("configuration_hash", ""))) is None:
                    raise SecurityPolicyError(f"{path} chart configuration hash is invalid")
                request = setup.get("request", {})
                request_json = request.get("json", {}) if isinstance(request, Mapping) else {}
                base_info = request_json.get("statViewBaseInfo", {}) if isinstance(request_json, Mapping) else {}
                if setup_id == "fs_bi_crm.stat_create.copy_stat_view":
                    provenance = resource.get("source_provenance")
                    if not isinstance(provenance, Mapping) or not str(provenance.get("source_view_id", "")):
                        raise SecurityPolicyError(f"{path} chart clone source is missing")
                    if _SHA256.fullmatch(str(provenance.get("source_config_hash", ""))) is None:
                        raise SecurityPolicyError(f"{path} chart clone source hash is invalid")
                    post_setup = resource.get("post_setup")
                    if not isinstance(post_setup, list) or len(post_setup) != 3:
                        raise SecurityPolicyError(f"{path} chart clone requires rename, origin readback and conditional move")
                    rename = post_setup[0].get("request", {})
                    origin_readback = post_setup[1]
                    move_step = post_setup[2]
                    move = move_step.get("request", {})
                    if move.get("api") != "fs_bi_crm.rpt_view_display.move_rpt_view" or str(
                        move.get("json", {}).get("targetCategoryID", "")
                    ) != category_id:
                        raise SecurityPolicyError(f"{path} chart clone move target does not match folder")
                    if (origin_readback.get("request", {}).get("api") != "fs_bi_crm.stat_edit.get_stat_view"
                            or origin_readback.get("extract", {}).get("chart_origin_category_id") != "Value.categoryID"):
                        raise SecurityPolicyError(f"{path} chart clone requires live origin folder readback")
                    if (move.get("json", {}).get("originCategoryID") != "{{ chart_origin_category_id }}"
                            or move_step.get("condition", {}).get("operator") != "not_equals"):
                        raise SecurityPolicyError(f"{path} chart clone move must be conditional on live origin folder")
                    if rename.get("api") != "fs_bi_crm.rpt_view_display.rename_rpt_view" or str(
                        rename.get("json", {}).get("viewName", "")
                    ) != str(resource.get("display_name", "")):
                        raise SecurityPolicyError(f"{path} chart clone rename does not match display name")
                elif not isinstance(base_info, Mapping) or str(base_info.get("categoryID", "")) != category_id:
                    raise SecurityPolicyError(f"{path} chart category does not match folder binding")
            readiness = resource.get("readiness", [])
            if not isinstance(readiness, list):
                raise ContractError(f"{path}.readiness must be a list")
            for check_index, check in enumerate(readiness):
                if not isinstance(check, Mapping):
                    raise ContractError(f"{path}.readiness[{check_index}] must be an object")
                check_id = _operation_id(check, f"{path}.readiness[{check_index}]")
                if check_id not in readiness_operations:
                    raise SecurityPolicyError(
                        f"{path}.readiness[{check_index}] operation is not a read-only "
                        "readiness operation"
                    )
            residue = resource.get("residue_checks", [])
            if autonomous and (not isinstance(residue, list) or not residue):
                raise SecurityPolicyError(f"{path} requires residue verification")
            if not isinstance(residue, list):
                raise ContractError(f"{path}.residue_checks must be a list")
            for check_index, check in enumerate(residue):
                if not isinstance(check, Mapping):
                    raise ContractError(f"{path}.residue_checks[{check_index}] must be an object")
                check_id = _operation_id(check, f"{path}.residue_checks[{check_index}]")
                if check_id not in readiness_operations:
                    raise SecurityPolicyError(
                        f"{path}.residue_checks[{check_index}] must use a read-only operation"
                    )
            validated_resources += 1
    return {
        "schema_version": "test-data-plan-validation/1.0",
        "valid": True,
        "environment": environment,
        "namespace": namespace,
        "validated_resource_count": validated_resources,
        "phase_permissions": dict(phase_permissions),
        "write_authorized": validated_resources > 0,
        "planning_mode": "autonomous" if autonomous else "case_explicit",
    }



# Stable native dimension pool for cases without a custom_dimension resource.
# Verified sticky on 112 updateStatView after fieldType coercion.
_DEFAULT_FALLBACK_DIMENSION_FIELD_IDS = (
    "BI_5bcebcddcab2980001ee22b3",  # 客户级别 select_one
    "BI_5bcebcddcab2980001ee22d7",  # 创建时间 date_time
    "BI_e68d52002e7dd8e19eb46dc0",  # 拜访频率 select_one
    "BI_4f6ba1123c8ddf09e655610a0d40f",  # 退回/收回原因 text
    "BI_5cac8e840492437edb7d3a13",  # 预计收回时间 date_time
)

# Native filter pool so 筛选 also rotates per case when no second metric exists.
# Keep measure/filter split inside one chart (filters are schema fields, not metrics).
_DEFAULT_FALLBACK_FILTER_FIELD_IDS = (
    "BI_5bcebcddcab2980001ee22d3",  # 转手次数 number
    "BI_5bcebcddcab2980001ee22d7",  # 创建时间 date_time
    "BI_5bcebcddcab2980001ee22b3",  # 客户级别 select_one
    "BI_e68d52002e7dd8e19eb46dc0",  # 拜访频率 select_one
    "BI_5cac8e840492437edb7d3a13",  # 预计收回时间 date_time
)


def _rotate_pool(pool: list[str], seed: str, *, offset: int = 0) -> str:
    if not pool:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    index = (int(digest[:8], 16) + offset) % len(pool)
    return pool[index]


def _build_id_pool(
    variables: Mapping[str, Any],
    *,
    pool_key: str,
    default_ids: tuple[str, ...],
    extra_keys: tuple[str, ...] = (),
) -> list[str]:
    pool: list[str] = []
    raw_pool = variables.get(pool_key)
    explicit_pool = isinstance(raw_pool, list) and any(str(item).strip() for item in raw_pool)
    if explicit_pool:
        pool.extend(str(item).strip() for item in raw_pool if str(item).strip())
        return pool
    for key in extra_keys:
        value = str(variables.get(key) or "").strip()
        if value and value not in pool:
            pool.append(value)
    for value in default_ids:
        if value not in pool:
            pool.append(value)
    return pool


def _case_chart_bind_inputs(
    resources: list[Mapping[str, Any]],
    *,
    variables: Mapping[str, Any] | None = None,
    case_id: str = "",
) -> dict[str, str]:
    """Pick dimension/measure/filter bindings so cloned charts differ per case.

    Preference:
    - dimension: case custom_dimension, else rotated native fallback dims
    - measure: first aggregate_metric (replaceable source shell required)
    - filter: second aggregate_metric when present, else rotated native filter
      fields (never the measure field) so 指标/筛选 split and charts differ
    """
    variables = dict(variables or {})
    dimension_var = ""
    measure_var = ""
    filter_var = ""
    dimension_id = ""
    filter_id = ""
    aggregate_vars: list[str] = []
    for resource in resources:
        if not isinstance(resource, Mapping):
            continue
        rtype = str(resource.get("resource_type") or "")
        id_var = str(resource.get("resource_id_variable") or "")
        if rtype == "custom_dimension" and id_var and not dimension_var:
            dimension_var = id_var
        if rtype == "aggregate_metric" and id_var:
            aggregate_vars.append(id_var)
    if aggregate_vars:
        measure_var = aggregate_vars[0]
        if len(aggregate_vars) > 1:
            filter_var = aggregate_vars[1]
    seed = str(case_id or variables.get("namespace") or "case")
    if not dimension_var:
        dim_pool = _build_id_pool(
            variables,
            pool_key="fallback_dimension_field_ids",
            default_ids=_DEFAULT_FALLBACK_DIMENSION_FIELD_IDS,
            extra_keys=("account_level_field_id", "date_field_id"),
        )
        dimension_id = _rotate_pool(dim_pool, seed, offset=0)
    if not filter_var:
        filter_pool = _build_id_pool(
            variables,
            pool_key="fallback_filter_field_ids",
            default_ids=_DEFAULT_FALLBACK_FILTER_FIELD_IDS,
            extra_keys=("amount_field_id", "date_field_id", "account_level_field_id"),
        )
        # Prefer a filter that is not the same native field as dimension.
        blocked = {dimension_id} if dimension_id else set()
        preferred = [item for item in filter_pool if item not in blocked]
        candidates = preferred or filter_pool
        filter_id = _rotate_pool(candidates, seed, offset=1)
        if not filter_id:
            amount_id = str(variables.get("amount_field_id") or "").strip()
            filter_id = amount_id
    return {
        "dimension_field_id_var": dimension_var,
        "dimension_field_id": dimension_id,
        "measure_field_id_var": measure_var,
        "filter_field_id_var": filter_var,
        "filter_field_id": filter_id,
    }


def bind_plan_to_case(
    case: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Materialize a validated Case plan into CaseRunner lifecycle steps."""

    case_id = str(case.get("id", ""))
    case_plan = next(
        (
            item
            for item in plan.get("case_plans", [])
            if isinstance(item, Mapping) and str(item.get("case_id", "")) == case_id
        ),
        None,
    )
    if case_plan is None:
        raise ContractError(f"test-data plan does not contain Case {case_id}")
    setup: list[dict[str, Any]] = []
    readiness: list[dict[str, Any]] = []
    preparation: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    residue: list[dict[str, Any]] = []
    existing_resource_variables: dict[str, str] = {}
    has_chart_resource = any(
        isinstance(item, Mapping)
        and str(item.get("resource_type") or "") in _CHART_RESOURCES
        for item in case_plan.get("resources", [])
    )
    for resource in case_plan.get("resources", []):
        if resource.get("lifecycle_mode") == "existing_read_only":
            resource_id = str(resource.get("resource_id") or "").strip()
            resource_id_variable = str(resource.get("resource_id_variable") or "").strip()
            if resource_id and resource_id_variable:
                existing_resource_variables[resource_id_variable] = resource_id
            discovery_step = deepcopy(resource["discovery"])
            resource_readiness = deepcopy(resource.get("readiness", []))
            readiness.append(discovery_step)
            readiness.extend(resource_readiness)
            preparation.append({"phase": "discovery", "step": discovery_step})
            preparation.extend(
                {"phase": "readiness", "step": readiness_step}
                for readiness_step in resource_readiness
            )
            continue
        setup_step = deepcopy(resource["setup"])
        setup_step["resource_key"] = str(resource.get("resource_key") or "")
        setup_step["resource_type"] = str(resource.get("resource_type") or "")
        setup_step["resource_display_name"] = str(resource.get("display_name") or "")
        setup_step["resource_folder_name"] = str(resource.get("asset_folder_name") or "")
        resource_readiness = deepcopy(resource.get("readiness", []))
        setup.append(setup_step)
        readiness.extend(resource_readiness)
        preparation.append({"phase": "setup", "step": setup_step})
        # Chart clone recipes carry rename/origin-readback/conditional-move as
        # post_setup. Materialize them into the executable setup stream so the
        # CaseRunner actually lands the asset in the requirement folder with a
        # human-visible name.
        namespace = str(plan.get("namespace", ""))
        from .asset_scene_naming import scene_display_name

        display_name = scene_display_name(
            resource_type=str(resource.get("resource_type") or ""),
            resource_key=str(resource.get("resource_key") or ""),
            case_id=case_id,
            title=str(case.get("title") or case_plan.get("requirement_name") or ""),
            existing_name=str(resource.get("display_name") or ""),
        ) or str(resource.get("display_name") or resource.get("resource_key") or "asset")
        visible_name = (
            f"{namespace}-{display_name}"
            if namespace and str(resource.get("resource_type") or "") == "stat_chart"
            else display_name
        )
        for index, raw_post in enumerate(resource.get("post_setup") or [], start=1):
            if not isinstance(raw_post, Mapping):
                continue
            post_step = deepcopy(raw_post)
            request = post_step.get("request")
            if isinstance(request, Mapping):
                api = str(request.get("api", ""))
                body = request.get("json")
                if api == "fs_bi_crm.rpt_view_display.rename_rpt_view" and isinstance(body, dict):
                    body["viewName"] = visible_name
                    request = {**request, "json": body}
                    post_step["request"] = request
            post_step.setdefault(
                "name",
                f"{display_name} post_setup {index}",
            )
            post_step.setdefault(
                "expect",
                {"status_code": 200, "json_path": {"Result.FailureCode": 0}},
            )
            setup.append(post_step)
            preparation.append({"phase": "setup", "step": post_step})
        # After clone rename/move, bind case-owned dimension/measure/filter so
        # charts are not identical copies of the source view.
        if str(resource.get("resource_type") or "") == "stat_chart":
            bind_variables = {
                **dict(plan.get("variables") or {}),
                **dict(case_plan.get("variables") or {}),
                **dict(case.get("variables") or {}),
            }
            bind_vars = _case_chart_bind_inputs(
                list(case_plan.get("resources") or []),
                variables=bind_variables,
                case_id=case_id,
            )
            dim_var = bind_vars.get("dimension_field_id_var") or ""
            measure_var = bind_vars.get("measure_field_id_var") or ""
            filter_var = bind_vars.get("filter_field_id_var") or ""
            dim_literal = bind_vars.get("dimension_field_id") or ""
            filter_literal = bind_vars.get("filter_field_id") or ""
            chart_id_var = str(resource.get("resource_id_variable") or "chart_view_id")
            if dim_var:
                dimension_value = f"{{{{ {dim_var} }}}}"
            else:
                dimension_value = dim_literal
            if measure_var:
                measure_value = f"{{{{ {measure_var} }}}}"
            else:
                measure_value = ""
            if filter_var:
                filter_value = f"{{{{ {filter_var} }}}}"
            elif filter_literal and filter_literal == str(
                bind_variables.get("amount_field_id") or ""
            ):
                filter_value = "{{ amount_field_id }}"
            else:
                filter_value = filter_literal
            if dimension_value or measure_value or filter_value:
                bind_step = {
                    "name": f"{display_name} bind differentiated chart config",
                    "action": "bind_stat_chart_config",
                    "inputs": {
                        "chart_view_id": f"{{{{ {chart_id_var} }}}}",
                        "schema_id": "{{ schema_id }}",
                        "dimension_field_id": dimension_value,
                        "measure_field_id": measure_value,
                        "filter_field_id": filter_value,
                    },
                    "expect": {"status_code": 200, "json_path": {"Result.FailureCode": 0}},
                }
                setup.append(bind_step)
                preparation.append({"phase": "setup", "step": bind_step})
        preparation.extend(
            {"phase": "readiness", "step": readiness_step}
            for readiness_step in resource_readiness
        )
        if (
            str(resource.get("resource_type") or "") == "stat_chart"
            and resource.get("integrity_probes")
        ):
            chart_id_var = str(resource.get("resource_id_variable") or "chart_view_id")
            baseline_step = {
                "name": f"{display_name} baseline chart query",
                "action": "prime_stat_chart_data",
                "inputs": {"chart_view_id": f"{{{{ {chart_id_var} }}}}"},
                "expect": {"status_code": 200, "json_path": {"Result.FailureCode": 0}},
            }
            readiness.append(baseline_step)
            preparation.append({"phase": "readiness", "step": baseline_step})
            integrity_step = {
                "name": f"{display_name} warehouse integrity validation",
                "action": "validate_chart_integrity",
                "integrity_probes": deepcopy(resource["integrity_probes"]),
                "expect": {"status_code": 200, "json_path": {"Result.FailureCode": 0}},
            }
            readiness.append(integrity_step)
            preparation.append({"phase": "readiness", "step": integrity_step})
        if resource.get("retention_mode") == "delete":
            cleanup_step = deepcopy(resource["cleanup"])
            cleanup_step["when_variable"] = str(resource["resource_id_variable"])
            cleanup.append(cleanup_step)
            for residue_step in deepcopy(resource.get("residue_checks", [])):
                residue_step["when_variable"] = str(resource["resource_id_variable"])
                residue.append(residue_step)
    bound_steps = deepcopy(list(case.get("steps", [])))
    if has_chart_resource:
        for step in bound_steps:
            if not isinstance(step, Mapping):
                continue
            request = step.get("request")
            body = request.get("json") if isinstance(request, Mapping) else None
            if not isinstance(body, dict):
                continue
            chart_marker = str(body.get("id") or "").replace(" ", "")
            if chart_marker == "{{chart_view_id}}":
                body["isView"] = 1
    return {
        **deepcopy(dict(case)),
        "environment": str(plan["environment"]),
        "namespace": str(plan["namespace"]),
        "retention_mode": str(case_plan.get("retention_mode", "retain")),
        "data_validity": [
            {
                "resource_key": str(resource.get("resource_key") or ""),
                "resource_type": str(resource.get("resource_type") or ""),
                "contract": deepcopy(resource.get("validity_contract")),
                "integrity_probes": deepcopy(resource.get("integrity_probes", [])),
                "existing_integrity_evidence": deepcopy(
                    (resource.get("existing_asset_evidence") or {}).get("integrity_evidence")
                ) if isinstance(resource.get("existing_asset_evidence"), Mapping) else None,
            }
            for resource in case_plan.get("resources", [])
            if str(resource.get("resource_type") or "") in _CHART_RESOURCES
        ],
        "retained_assets": [
            {
                "requirement_name": case_plan.get("requirement_name", case_id),
                "resource_key": resource["resource_key"],
                "resource_type": resource["resource_type"],
                "resource_id_variable": resource["resource_id_variable"],
                "display_name": (
                    f"{plan.get('namespace')}-{resource.get('display_name')}"
                    if resource.get("resource_type") == "stat_chart"
                    and plan.get("namespace")
                    and resource.get("display_name")
                    else resource.get("display_name")
                ),
                "source_field_type": resource.get("source_field_type"),
            }
            for resource in case_plan.get("resources", [])
            if resource.get("retention_mode") == "retain"
        ],
        "variables": {
            **deepcopy(dict(case.get("variables", {}))),
            **deepcopy(dict(case_plan.get("variables", {}))),
            "namespace": str(plan["namespace"]),
            **existing_resource_variables,
        },
        "setup": setup,
        "steps": bound_steps,
        "readiness": readiness,
        "preparation": preparation,
        "cleanup": cleanup,
        "residue_checks": residue,
    }


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


def prepare_test_data_plan(
    compiled_cases_path: Path,
    policy_path: Path,
    output_dir: Path,
    *,
    environment: str,
    namespace: str,
    knowledge_sources_path: Path | None = None,
    capability_catalog_path: Path | None = None,
    inventory_path: Path | None = None,
    execution_plan_path: Path | None = None,
    skip_by_policy: bool = False,
    existing_data_case_ids: set[str] | None = None,
    deferred_frontend_case_ids: set[str] | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Run legacy explicit planning or autonomous A22 -> N28 -> N27 planning."""

    if skip_by_policy and (
        knowledge_sources_path is not None or capability_catalog_path is not None
    ):
        raise ContractError("Skipped data planning cannot consume autonomous planning inputs")
    if (knowledge_sources_path is None) != (capability_catalog_path is None):
        raise ContractError(
            "Autonomous data planning requires both knowledge sources and capability catalog"
        )
    if execution_plan_path is not None and (
        skip_by_policy or knowledge_sources_path is not None or capability_catalog_path is not None
    ):
        raise ContractError(
            "Existing-automation-managed data planning is exclusive with skip and autonomous inputs"
        )
    if knowledge_sources_path is not None and capability_catalog_path is not None:
        from .data_planning import prepare_autonomous_test_data_plan

        return prepare_autonomous_test_data_plan(
            compiled_cases_path,
            knowledge_sources_path,
            capability_catalog_path,
            policy_path,
            output_dir,
            environment=environment,
            namespace=namespace,
            inventory_path=inventory_path,
            security=security,
        )

    security = security or SecurityPolicy()
    compiled = _read_object(compiled_cases_path, "N25 compiled cases Artifact")
    if compiled.get("schema_version") != "artifact-envelope/1.0":
        raise ContractError("N25 compiled cases is not an Artifact Envelope")
    if compiled.get("artifact_hash") != artifact_hash_from_mapping(compiled):
        raise ContractError("N25 compiled cases Artifact hash is invalid")
    if compiled.get("artifact_id") != "n25-compiled-test-cases":
        raise ContractError("A22 requires Artifact n25-compiled-test-cases")
    producer = compiled.get("producer")
    if not isinstance(producer, Mapping) or producer.get("component_id") != "N25":
        raise ContractError("A22 compiled Case producer must be N25")
    payload = compiled.get("payload")
    if not isinstance(payload, Mapping):
        raise ContractError("N25 compiled Case payload must be an object")
    cases = payload.get("compiled_cases", payload.get("child_cases"))
    if not isinstance(cases, list):
        raise ContractError("N25 compiled_cases or child_cases must be a list")
    policy = _read_object(policy_path, "test-data policy")
    security.assert_no_secret_values(policy)

    identity = (
        str(compiled.get("workflow_run_id", "")),
        str(compiled.get("workflow_mode", "")),
        str(compiled.get("source_snapshot_id", "")),
    )
    if not all(identity):
        raise ContractError("N25 workflow identity is incomplete")
    context = AgentContext(
        identity[0],
        identity[1],
        identity[2],
        (str(compiled_cases_path), str(policy_path)),
    )
    if execution_plan_path is not None:
        execution_plan = _read_object(execution_plan_path, "N15 execution plan Artifact")
        if (
            execution_plan.get("schema_version") != "artifact-envelope/1.0"
            or execution_plan.get("artifact_id") != "n15-execution-plan"
            or execution_plan.get("artifact_hash") != artifact_hash_from_mapping(execution_plan)
        ):
            raise ContractError("Existing-data planning requires a valid N15 execution plan Artifact")
        if (
            execution_plan.get("workflow_run_id"),
            execution_plan.get("workflow_mode"),
            execution_plan.get("source_snapshot_id"),
        ) != identity:
            raise ContractError("N15 execution plan belongs to a different workflow run")
        actions = execution_plan.get("payload", {}).get("actions", [])
        actions_by_case = {
            str(item.get("case_id", "")): item
            for item in actions if isinstance(item, Mapping)
        }
        case_ids = {str(item.get("id", "")) for item in cases}
        invalid = sorted(
            case_id for case_id in case_ids
            if actions_by_case.get(case_id, {}).get("action") != "run_existing"
            or not str(actions_by_case.get(case_id, {}).get("automation_ref", ""))
        )
        if invalid:
            raise ContractError(
                "Existing automation does not manage test data for Cases: " + ", ".join(invalid)
            )
        executable = sorted(case_ids)
        a22 = ArtifactEnvelope(
            workflow_run_id=identity[0], workflow_mode=identity[1],
            artifact_id="a22-test-data-plan", source_snapshot_id=identity[2],
            producer=Producer(component_id="A22", runtime="deterministic"),
            payload={
                "schema_version": PLAN_CONTRACT,
                "environment": environment,
                "namespace": namespace,
                "planning_mode": "existing_automation_managed",
                "case_plans": [],
                "paused_cases": [],
                "unresolved_requirements": [],
                "executable_case_ids": executable,
                "automation_bindings": {
                    case_id: str(actions_by_case[case_id]["automation_ref"])
                    for case_id in executable
                },
                "execution_plan_hash": execution_plan["artifact_hash"],
            },
            status=ArtifactStatus.COMPLETED,
            evidence_refs=(EvidenceRef(
                source_type="artifact", source_id="n15-execution-plan",
                location=execution_plan_path.name,
                content_hash=str(execution_plan["artifact_hash"]),
            ),),
        )
        validation = {
            "schema_version": "test-data-plan-validation/1.0",
            "valid": True,
            "decision": "existing_automation_managed",
            "next_node": "N07",
            "environment": environment,
            "namespace": namespace,
            "validated_resource_count": 0,
            "write_authorized": False,
            "planning_mode": "existing_automation_managed",
            "execution_plan_hash": execution_plan["artifact_hash"],
            "executable_case_ids": executable,
            "deferred_cases": [],
        }
    elif skip_by_policy:
        if environment not in {str(item) for item in policy.get("allowed_environments", [])}:
            raise SecurityPolicyError(
                f"test-data policy skip is not allowed in environment {environment!r}"
            )
        if not _NAMESPACE.fullmatch(namespace):
            raise SecurityPolicyError("test-data namespace is missing or invalid")
        available = set(existing_data_case_ids or ())
        frontend_deferred = set(deferred_frontend_case_ids or ())
        deferred = []
        executable = []
        paused = []
        for raw_case in cases:
            if not isinstance(raw_case, Mapping):
                raise ContractError("N25 compiled_cases must contain objects")
            case_id = str(raw_case.get("id", ""))
            if not case_id:
                raise ContractError("A22 Case requires id")
            if _is_unit_case(raw_case):
                paused.append({"case_id": case_id, "reason_code": PAUSED_UNIT_REASON})
            elif case_id in frontend_deferred:
                deferred.append(
                    {
                        "case_id": case_id,
                        "route": "deferred_frontend",
                        "reason_code": "frontend_scope_deferred_by_policy",
                    }
                )
            elif (
                _requires_constructed_data(raw_case)
                or bool(raw_case.get("test_data"))
                or bool(raw_case.get("preconditions"))
            ) and case_id not in available:
                deferred.append(
                    {
                        "case_id": case_id,
                        "route": "deferred_data_construction",
                        "reason_code": "required_test_data_not_available_while_agent_paused",
                    }
                )
            else:
                executable.append(case_id)
        a22 = ArtifactEnvelope(
            workflow_run_id=identity[0],
            workflow_mode=identity[1],
            artifact_id="a22-test-data-plan",
            source_snapshot_id=identity[2],
            producer=Producer(component_id="A22", runtime="deterministic"),
            payload={
                "schema_version": PLAN_CONTRACT,
                "environment": environment,
                "namespace": namespace,
                "planning_mode": "skipped_by_policy",
                "policy_reason": POLICY_SKIP_REASON,
                "case_plans": [],
                "paused_cases": paused,
                "unresolved_requirements": [],
                "existing_data_case_ids": sorted(available),
                "executable_case_ids": sorted(executable),
                "deferred_cases": deferred,
            },
            status=ArtifactStatus.SKIPPED_BY_POLICY,
            reason_code=POLICY_SKIP_REASON,
            evidence_refs=(
                EvidenceRef(
                    source_type="artifact",
                    source_id=str(compiled["artifact_id"]),
                    location=compiled_cases_path.name,
                    content_hash=str(compiled["artifact_hash"]),
                ),
            ),
        )
        validation = {
            "schema_version": "test-data-plan-validation/1.0",
            "valid": True,
            "decision": "skipped_by_policy",
            "next_node": "N07",
            "environment": environment,
            "namespace": namespace,
            "validated_resource_count": 0,
            "write_authorized": False,
            "planning_mode": "skipped_by_policy",
            "policy_reason": POLICY_SKIP_REASON,
            "executable_case_ids": sorted(executable),
            "deferred_cases": deferred,
        }
    else:
        a22 = TestDataPlannerAgent().run(
            context,
            {"environment": environment, "namespace": namespace, "cases": cases},
            security,
        )
        validation = validate_test_data_plan(a22.payload, policy)
    n27 = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id=identity[2],
        producer=Producer(component_id="N27", runtime="deterministic"),
        payload={
            **validation,
            "a22_artifact_id": a22.artifact_id,
            "a22_artifact_hash": a22.artifact_hash,
        },
        status=(
            ArtifactStatus.SKIPPED_BY_POLICY
            if a22.status == ArtifactStatus.SKIPPED_BY_POLICY
            else ArtifactStatus.COMPLETED
            if a22.status == ArtifactStatus.COMPLETED
            else ArtifactStatus.BLOCKED
        ),
        reason_code=(
            POLICY_SKIP_REASON
            if a22.status == ArtifactStatus.SKIPPED_BY_POLICY
            else None
            if a22.status == ArtifactStatus.COMPLETED
            else "test_data_plan_incomplete"
        ),
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=a22.artifact_id,
                location=f"{a22.artifact_id}.json",
                content_hash=a22.artifact_hash,
            ),
        ),
    )
    store = ArtifactStore(output_dir)
    store.write_artifact(a22)
    store.write_artifact(n27)
    result = {
        "schema_version": "test-data-preparation/1.0",
        "workflow_run_id": identity[0],
        "environment": environment,
        "namespace": namespace,
        "a22_artifact": {
            "artifact_id": a22.artifact_id,
            "artifact_hash": a22.artifact_hash,
            "status": a22.status.value,
        },
        "n27_artifact": {
            "artifact_id": n27.artifact_id,
            "artifact_hash": n27.artifact_hash,
            "status": n27.status.value,
        },
        "ready_for_execution": n27.status
        in {ArtifactStatus.COMPLETED, ArtifactStatus.SKIPPED_BY_POLICY},
        "executable_case_ids": list(validation.get("executable_case_ids", [])),
        "deferred_cases": list(validation.get("deferred_cases", [])),
    }
    store.write_json("test-data-preparation.json", result)
    return result


def record_constructed_test_data(
    a22_plan_path: Path,
    n08_execution_path: Path,
    auto_dir: Path,
    env_observed_path: Path,
) -> dict[str, Any]:
    """Register resources actually constructed during N08 into env-observed.

    The A22 plan declares per-case resources with a ``setup_operation``; the N08
    execution artifact carries per-shard lifecycle evidence recording which
    operations completed (step status ``completed`` with an HTTP response). Only
    resources whose setup operation actually completed *and was asserted* (the
    lifecycle step carried a non-empty ``expect``) are registered, so
    ``env-observed.test_data`` reflects reality instead of the plan. A planned
    resource whose current evidence no longer verifies construction is demoted
    to ``stale`` instead of keeping a phantom ``constructed`` claim. Idempotent:
    entries with the same ``(case_id, key)`` are replaced, unrelated entries are
    preserved, and missing evidence degrades to an empty registration.
    """

    def _payload(path: Path, label: str) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        payload = value.get("payload", {}) if isinstance(value, Mapping) else {}
        return payload if isinstance(payload, Mapping) else {}

    def _lifecycle_cases(path: Path) -> list[Any]:
        if not path.exists():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(value, Mapping):
            return []
        cases = value.get("cases", [])
        return cases if isinstance(cases, list) else []

    plan = _payload(a22_plan_path, "A22 test-data plan")
    execution = _payload(n08_execution_path, "N08 automation execution")
    planned: list[dict[str, Any]] = []
    for case_plan in plan.get("case_plans", []):
        if not isinstance(case_plan, Mapping):
            continue
        case_id = str(case_plan.get("case_id", ""))
        resources = case_plan.get("resources", [])
        if not isinstance(resources, list):
            continue
        for resource in resources:
            if not isinstance(resource, Mapping):
                continue
            operation = str(resource.get("setup_operation", "")).strip()
            if not operation:
                setup = resource.get("setup")
                request = setup.get("request") if isinstance(setup, Mapping) else None
                if isinstance(request, Mapping):
                    operation = str(request.get("api") or "").strip()
            if not operation:
                continue
            planned.append(
                {
                    "case_id": case_id,
                    "key": str(resource.get("resource_key", "")),
                    "resource_type": str(resource.get("resource_type", "")),
                    "operation": operation,
                    "resource_id_variable": str(resource.get("resource_id_variable", "")),
                    "display_name": str(resource.get("display_name") or ""),
                    "folder_name": str(resource.get("asset_folder_name") or ""),
                    "integrity_probes": deepcopy(resource.get("integrity_probes", [])),
                }
            )

    completed: dict[str, set[str]] = {}
    evidence_hashes: dict[str, str] = {}
    response_hashes: dict[str, str] = {}
    shards = execution.get("shards", [])
    if not isinstance(shards, list):
        shards = []
    for shard in shards:
        if not isinstance(shard, Mapping):
            continue
        case_ids = [
            str(item) for item in shard.get("case_ids", []) if str(item)
        ]
        evidence_path = shard.get("lifecycle_evidence_path")
        evidence_hash = str(shard.get("lifecycle_evidence_hash", "") or "")
        if isinstance(evidence_path, str) and evidence_path:
            resolved = auto_dir / evidence_path
            cases = _lifecycle_cases(resolved)
            for case in cases:
                if not isinstance(case, Mapping):
                    continue
                case_id = str(case.get("case_id", ""))
                phases = case.get("phases", {})
                if not isinstance(phases, Mapping):
                    continue
                for phase in ("setup", "test"):
                    steps = phases.get(phase, [])
                    if not isinstance(steps, list):
                        continue
                    for step in steps:
                        if not isinstance(step, Mapping):
                            continue
                        if str(step.get("status", "")) != "completed":
                            continue
                        if step.get("verified") is not True:
                            continue
                        operation = str(step.get("operation", "")).strip()
                        if operation:
                            completed.setdefault(case_id, set()).add(operation)
                            if evidence_hash:
                                evidence_hashes[f"{case_id}:{operation}"] = evidence_hash
                            response_hash = str(step.get("response_hash", "") or "")
                            if response_hash:
                                response_hashes[f"{case_id}:{operation}"] = response_hash
        else:
            for case_id in case_ids:
                completed.setdefault(case_id, set())

    namespace = str(plan.get("namespace", "") or "")
    if env_observed_path.exists():
        observed = json.loads(env_observed_path.read_text(encoding="utf-8"))
    else:
        observed = {}
    if not isinstance(observed, Mapping):
        observed = {}
    if not namespace:
        namespaces = observed.get("test_namespaces", [])
        if isinstance(namespaces, list) and namespaces:
            first = namespaces[0] if isinstance(namespaces[0], Mapping) else {}
            namespace = str(first.get("namespace", "") or "")

    registered: list[dict[str, Any]] = []
    by_case_key = {
        (str(item.get("case_id", "")), str(item.get("key", ""))): item
        for item in observed.get("test_data", [])
        if isinstance(item, Mapping)
    }
    planned_by_key = {
        (str(resource["case_id"]), str(resource["key"])): resource
        for resource in planned
    }
    test_data: list[dict[str, Any]] = []
    for resource in planned:
        case_id = resource["case_id"]
        operations = completed.get(case_id, set())
        if resource["operation"] not in operations:
            continue
        entry = {
            "key": resource["key"],
            "resource_type": resource["resource_type"],
            "case_id": case_id,
            "operation": resource["operation"],
            "status": "constructed",
            "display_name": resource["display_name"],
            "folder_name": resource["folder_name"],
            "integrity_probes": resource["integrity_probes"],
        }
        if resource["resource_id_variable"]:
            entry["resource_id_variable"] = resource["resource_id_variable"]
        if namespace:
            entry["namespace"] = namespace
        evidence_key = f"{case_id}:{resource['operation']}"
        if evidence_key in response_hashes:
            entry["response_hash"] = response_hashes[evidence_key]
        if evidence_key in evidence_hashes:
            entry["lifecycle_evidence_hash"] = evidence_hashes[evidence_key]
        by_case_key[(case_id, resource["key"])] = entry
        registered.append(entry)
    for item in by_case_key.values():
        planned_resource = planned_by_key.get(
            (str(item.get("case_id", "")), str(item.get("key", "")))
        )
        if (
            planned_resource is not None
            and item.get("status") == "constructed"
            and str(planned_resource["operation"])
            not in completed.get(str(planned_resource["case_id"]), set())
        ):
            item["status"] = "stale"
        test_data.append(item)
    test_data.sort(key=lambda item: (str(item.get("case_id", "")), str(item.get("key", ""))))
    observed["test_data"] = test_data
    env_observed_path.parent.mkdir(parents=True, exist_ok=True)
    env_observed_path.write_text(
        json.dumps(observed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    from .asset_scene_naming import load_case_titles
    from .constructed_assets import (
        INVENTORY_FILENAME,
        collect_evidence_assets,
        merge_constructed_inventory,
        write_constructed_asset_inventory,
    )

    evidence_assets = collect_evidence_assets(auto_dir)
    titles = load_case_titles(
        auto_dir / "artifacts" / "n25-compiled-test-cases.json",
        auto_dir / "artifacts" / "a08-test-design-ir.json",
        a22_plan_path,
    )
    inventory = merge_constructed_inventory(registered, evidence_assets, titles=titles)
    inventory_path = auto_dir / "artifacts" / INVENTORY_FILENAME
    write_constructed_asset_inventory(
        inventory_path,
        inventory,
        namespace=namespace,
        environment=str(observed.get("environment") or plan.get("environment") or ""),
    )
    return {
        "registered": registered,
        "planned_resources": len(planned),
        "constructed_operations": sum(len(value) for value in completed.values()),
        "namespace": namespace,
        "inventory_path": str(inventory_path),
        "inventory_count": len(inventory),
    }
