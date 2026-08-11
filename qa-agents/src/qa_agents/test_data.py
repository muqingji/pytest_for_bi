"""A22 test-data planning and deterministic N27 safety validation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
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
            case_plans.append(
                {
                    "case_id": case_id,
                    "requires_data_construction": bool(requirements),
                    "resources": deepcopy(requirements),
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
        "cleanup": "write",
    }:
        raise ContractError(
            "test-data policy must allow setup/cleanup writes and keep readiness read-only"
        )
    readiness_operations = {
        str(item) for item in policy.get("readiness_operations", [])
    }
    allowed_types = {str(item) for item in policy.get("resource_types", [])}
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
            setup = resource.get("setup")
            cleanup = resource.get("cleanup")
            if not isinstance(setup, Mapping) or not isinstance(cleanup, Mapping):
                raise SecurityPolicyError(f"{path} requires paired setup and cleanup operations")
            setup_id = _operation_id(setup, f"{path}.setup")
            cleanup_id = _operation_id(cleanup, f"{path}.cleanup")
            if str(pairs.get(setup_id, "")) != cleanup_id:
                raise SecurityPolicyError(
                    f"{path} operation pair {setup_id!r} -> {cleanup_id!r} is not allowed"
                )
            extract = setup.get("extract")
            if not isinstance(extract, Mapping) or id_variable not in extract:
                raise ContractError(f"{path}.setup must extract {id_variable!r}")
            cleanup_text = json.dumps(cleanup, ensure_ascii=False)
            if f"{{{{ {id_variable} }}}}" not in cleanup_text:
                raise SecurityPolicyError(
                    f"{path}.cleanup must target the extracted resource id"
                )
            setup_text = json.dumps(setup, ensure_ascii=False)
            if f"{{{{ namespace }}}}" not in setup_text:
                raise SecurityPolicyError(f"{path}.setup must embed the run namespace")
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
    cleanup: list[dict[str, Any]] = []
    for resource in case_plan.get("resources", []):
        setup.append(deepcopy(resource["setup"]))
        readiness.extend(deepcopy(resource.get("readiness", [])))
        cleanup_step = deepcopy(resource["cleanup"])
        cleanup_step["when_variable"] = str(resource["resource_id_variable"])
        cleanup.append(cleanup_step)
    return {
        **deepcopy(dict(case)),
        "environment": str(plan["environment"]),
        "namespace": str(plan["namespace"]),
        "variables": {
            **deepcopy(dict(case.get("variables", {}))),
            **deepcopy(dict(case_plan.get("variables", {}))),
            "namespace": str(plan["namespace"]),
        },
        "setup": setup,
        "readiness": readiness,
        "cleanup": cleanup,
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
    cases = payload.get("compiled_cases")
    if not isinstance(cases, list):
        raise ContractError("N25 compiled_cases must be a list")
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
    if skip_by_policy:
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
