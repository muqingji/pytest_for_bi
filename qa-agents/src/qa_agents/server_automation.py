"""Prepare hash-bound server automation Artifacts from an approved N15 plan."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from .agents import DomainAutomationAgent, DomainAutomationReviewAgent, profile_for_case
from .agents.base import AgentContext
from .automation import AutomationPolicy, check_automation_generation
from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
)
from .errors import ContractError, InputError
from .security import SecurityPolicy
from .storage import ArtifactStore
from .skill_registry import SkillRegistry, route_backend_case


SERVER_LAYERS = {"backend", "contract"}
GENERATION_ACTIONS = {"generate_new", "update_existing"}


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be a JSON object")
    return value


def _verified_artifact(
    path: Path,
    label: str,
    *,
    artifact_id: str,
    producer_id: str,
    security: SecurityPolicy,
) -> dict[str, Any]:
    artifact = _read_object(path, label)
    if artifact.get("schema_version") != "artifact-envelope/1.0":
        raise ContractError(f"{label} is not an Artifact Envelope")
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError(f"{label} Artifact hash is invalid")
    if artifact.get("artifact_id") != artifact_id:
        raise ContractError(f"{label} must be Artifact {artifact_id}")
    producer = artifact.get("producer")
    if not isinstance(producer, Mapping) or producer.get("component_id") != producer_id:
        raise ContractError(f"{label} producer must be {producer_id}")
    if not isinstance(artifact.get("payload"), Mapping):
        raise ContractError(f"{label} payload must be an object")
    security.assert_no_secret_values(artifact)
    return artifact


def _identity(artifact: Mapping[str, Any]) -> tuple[str, str, str]:
    value = (
        str(artifact.get("workflow_run_id", "")).strip(),
        str(artifact.get("workflow_mode", "")).strip(),
        str(artifact.get("source_snapshot_id", "")).strip(),
    )
    if not all(value):
        raise ContractError("Artifact workflow identity is incomplete")
    return value


def _node_artifact(
    identity: tuple[str, str, str],
    component_id: str,
    artifact_id: str,
    payload: Mapping[str, Any],
    status: ArtifactStatus,
    reason_code: str | None,
    evidence: tuple[EvidenceRef, ...] = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id=artifact_id,
        source_snapshot_id=identity[2],
        producer=Producer(component_id=component_id, runtime="deterministic"),
        payload=payload,
        status=status,
        reason_code=reason_code,
        evidence_refs=evidence,
    )


def _artifact_ref(artifact: Mapping[str, Any], location: str) -> EvidenceRef:
    return EvidenceRef(
        source_type="artifact",
        source_id=str(artifact["artifact_id"]),
        location=location,
        content_hash=str(artifact["artifact_hash"]),
    )


def prepare_server_automation(
    execution_plan_path: Path,
    compiled_cases_path: Path,
    automation_policy_path: Path,
    target_path: Path,
    output_dir: Path,
    *,
    test_data_validation_path: Path | None = None,
    test_data_resource_plan_path: Path | None = None,
    knowledge_readiness_path: Path | None = None,
    security: SecurityPolicy | None = None,
    skill_registry_path: Path | None = None,
) -> dict[str, Any]:
    """Run A14/A15, independent A18 review and aggregate N05 for one Run.

    The function only emits artifact-only candidates. It never writes generated
    files into an automation or business repository.
    """

    security = security or SecurityPolicy()
    plan = _verified_artifact(
        execution_plan_path,
        "N15 execution plan",
        artifact_id="n15-execution-plan",
        producer_id="N15",
        security=security,
    )
    compiled = _verified_artifact(
        compiled_cases_path,
        "N25 compiled cases",
        artifact_id="n25-compiled-test-cases",
        producer_id="N25",
        security=security,
    )
    identity = _identity(plan)
    if _identity(compiled) != identity:
        raise ContractError("N15 and N25 belong to different workflow runs")
    data_validation: dict[str, Any] | None = None
    data_resource_plan: dict[str, Any] | None = None
    deferred_data_case_ids: set[str] = set()
    deferred_knowledge_case_ids: set[str] = set()
    knowledge_readiness: dict[str, Any] | None = None
    if knowledge_readiness_path is not None:
        knowledge_readiness = _read_object(
            knowledge_readiness_path, "automation knowledge readiness"
        )
        if knowledge_readiness.get("schema_version") != "automation-knowledge-readiness/1.0":
            raise ContractError("Automation knowledge readiness contract is invalid")
        if not isinstance(knowledge_readiness.get("deferred_case_ids"), list):
            raise ContractError("Automation knowledge readiness deferred_case_ids is invalid")
        deferred_knowledge_case_ids = set(
            map(str, knowledge_readiness["deferred_case_ids"])
        )
    if test_data_validation_path is not None:
        data_validation = _verified_artifact(
            test_data_validation_path,
            "N27 test-data validation",
            artifact_id="n27-test-data-plan-validation",
            producer_id="N27",
            security=security,
        )
        if _identity(data_validation) != identity:
            raise ContractError("N27 and N15 belong to different workflow runs")
        data_payload = data_validation["payload"]
        if data_payload.get("valid") is not True or data_validation.get("status") not in {
            "completed", "completed_with_gaps", "skipped_by_policy"
        }:
            raise ContractError("Server automation requires valid N27 data routing")
        if data_validation.get("status") == "completed_with_gaps" and (
            data_payload.get("decision") != "partial_capability_routing"
            or not isinstance(data_payload.get("executable_case_ids"), list)
            or not isinstance(data_payload.get("deferred_cases"), list)
        ):
            raise ContractError("Partial N27 routing contract is invalid")
        deferred_data_case_ids = {
            str(item.get("case_id", ""))
            for item in data_payload.get("deferred_cases", [])
            if isinstance(item, Mapping) and str(item.get("case_id", ""))
        }
    if test_data_resource_plan_path is not None:
        if data_validation is None:
            raise ContractError("N28 resource plan requires an N27 validation binding")
        data_resource_plan = _verified_artifact(
            test_data_resource_plan_path,
            "N28 test-data resource plan",
            artifact_id="n28-test-data-resource-plan",
            producer_id="N28",
            security=security,
        )
        if _identity(data_resource_plan) != identity:
            raise ContractError("N28 and N15 belong to different workflow runs")
        if data_validation["payload"].get("n28_artifact_hash") != data_resource_plan["artifact_hash"]:
            raise ContractError("N27 is not bound to the supplied N28 resource plan")
    if plan["payload"].get("schema_version") != "execution-plan/1.0":
        raise ContractError("N15 execution plan payload contract is invalid")
    if compiled["payload"].get("schema_version") != "n25-compiled-test-cases/1.0":
        raise ContractError("N25 compiled cases payload contract is invalid")

    target = _read_object(target_path, "automation target")
    security.assert_no_secret_values(target)
    required_target = {"repository_id", "access_class", "timeout_seconds", "network", "secrets"}
    if not required_target.issubset(target):
        missing = sorted(required_target - set(target))
        raise ContractError(f"Automation target is missing required fields: {missing}")
    policy = AutomationPolicy.from_file(automation_policy_path)
    registry = SkillRegistry.from_file(
        skill_registry_path or automation_policy_path.with_name("backend-skill-registry.json")
    )

    actions = plan["payload"].get("actions")
    cases = compiled["payload"].get("compiled_cases")
    if not isinstance(actions, list) or not all(isinstance(item, Mapping) for item in actions):
        raise ContractError("N15 actions must be a list of objects")
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N25 compiled_cases must be a list of objects")
    cases_by_id = {str(item.get("id", "")): dict(item) for item in cases}
    if "" in cases_by_id or len(cases_by_id) != len(cases):
        raise ContractError("N25 compiled cases require unique non-empty IDs")
    unknown_knowledge_cases = deferred_knowledge_case_ids - set(cases_by_id)
    if unknown_knowledge_cases:
        raise ContractError(
            "Automation knowledge readiness references unknown compiled Cases: "
            f"{sorted(unknown_knowledge_cases)}"
        )

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    manual_case_ids: list[str] = []
    excluded_case_ids: list[str] = []
    deferred_case_ids: list[str] = []
    unsupported: list[dict[str, str]] = []
    seen_action_ids: set[str] = set()
    for action in actions:
        case_id = str(action.get("case_id", "")).strip()
        if not case_id or case_id in seen_action_ids:
            raise ContractError("N15 actions require unique non-empty case_id values")
        seen_action_ids.add(case_id)
        case = cases_by_id.get(case_id)
        if case is None:
            raise ContractError(f"N15 action references unknown compiled Case: {case_id}")
        action_name = str(action.get("action", ""))
        if case_id in deferred_data_case_ids or case_id in deferred_knowledge_case_ids:
            deferred_case_ids.append(case_id)
            continue
        if action_name.startswith("deferred_"):
            deferred_case_ids.append(case_id)
            continue
        if action_name == "manual_run":
            manual_case_ids.append(case_id)
            continue
        if action_name not in GENERATION_ACTIONS:
            continue
        layer = str(case.get("layer", ""))
        if layer not in SERVER_LAYERS:
            excluded_case_ids.append(case_id)
            continue
        level = str(case.get("test_level", "") or "").strip().lower()
        if level in {"unit", "unit_test", "单元", "单元测试"}:
            unsupported.append({
                "case_id": case_id,
                "reason_code": "paused_existing_developer_unit_coverage",
            })
            continue
        profile = profile_for_case(case)
        if profile is None:
            unsupported.append({"case_id": case_id, "reason_code": "profile_not_implemented"})
            continue
        groups[profile.agent_id].append(case)

    store = ArtifactStore(output_dir)
    context = AgentContext(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        source_snapshot_id=identity[2],
        input_paths=(str(execution_plan_path), str(compiled_cases_path), str(target_path)),
    )
    generations: list[ArtifactEnvelope] = []
    reviews: list[ArtifactEnvelope] = []
    checks: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = list(unsupported)
    for agent_id in sorted(groups):
        profile = profile_for_case(groups[agent_id][0])
        if profile is None:  # guarded above; retained for defensive type narrowing
            continue
        generation_cases = groups[agent_id]
        if data_resource_plan is not None:
            from .test_data import bind_plan_to_case

            generation_cases = [
                bind_plan_to_case(case, data_resource_plan["payload"]) for case in generation_cases
            ]
        authorizations = {
            str(case["id"]): route_backend_case(case, registry) for case in generation_cases
        }
        generation = DomainAutomationAgent(profile).run(
            context,
            {"cases": generation_cases, "target": target,
             "skill_router_bindings": authorizations,
             "input_bindings": {
                 "knowledge_packet_hash": (
                     str(knowledge_readiness.get("packet_hash", ""))
                     if knowledge_readiness is not None else ""
                 ),
                 "test_data_validation_hash": (
                     str(data_validation["artifact_hash"])
                     if data_validation is not None else ""
                 ),
                 "test_data_resource_plan_hash": (
                     str(data_resource_plan["artifact_hash"])
                     if data_resource_plan is not None else ""
                 ),
             }}, security
        )
        store.write_artifact(generation)
        generations.append(generation)
        rejected.extend(dict(item) for item in generation.payload.get("rejected_cases", []))

        if generation.status == ArtifactStatus.NOT_APPLICABLE:
            review = _node_artifact(
                identity,
                profile.review_agent_id,
                f"{profile.review_agent_id.lower()}-{profile.review_output_name}",
                {
                    "schema_version": "automation-review/1.0",
                    "review_profile": profile.review_profile,
                    "approved": False,
                    "issues": [],
                    "generator_status": generation.status.value,
                    "rejected_cases": list(generation.payload.get("rejected_cases", [])),
                },
                ArtifactStatus.NOT_APPLICABLE,
                "generator_not_applicable",
                (_artifact_ref(generation.to_dict(), f"{generation.artifact_id}.json"),),
            )
        else:
            review = DomainAutomationReviewAgent(profile).run(
                context,
                {"cases": generation_cases, "generation": generation.payload},
                security,
            )
        store.write_artifact(review)
        reviews.append(review)
        if generation.status == ArtifactStatus.COMPLETED:
            checks.append(check_automation_generation(generation.payload, policy))

    issues = [item for check in checks for item in check["issues"]]
    bindings = [
        {
            "generation_hash": check["generation_hash"],
            "manifest_hash": check["manifest_hash"],
            "candidate_hashes": check["candidate_hashes"],
        }
        for check in checks
    ]
    passed = bool(checks) and all(check["passed"] for check in checks)
    fatal = any(check["fatal_security_violation"] for check in checks)
    n05_payload = {
        "schema_version": "automation-code-check/1.0",
        "input_bindings": bindings,
        "passed": passed,
        "fatal_security_violation": fatal,
        "issues": issues,
        "repair_routes": sorted(
            {route for check in checks for route in check["repair_routes"]}
        ),
        "generation_count": len(checks),
        "planned_generation_count": sum(len(items) for items in groups.values()),
        "rejected_cases": rejected,
    }
    if not checks:
        n05_status = ArtifactStatus.NOT_APPLICABLE
        n05_reason = "no_machine_executable_server_candidate"
    elif passed:
        n05_status = ArtifactStatus.COMPLETED
        n05_reason = None
    elif fatal:
        n05_status = ArtifactStatus.FAILED_FATAL
        n05_reason = "security_policy_violation"
    else:
        n05_status = ArtifactStatus.NEEDS_HUMAN
        n05_reason = "automation_code_check_failed"
    n05 = _node_artifact(
        identity,
        "N05",
        "n05-automation-code-check",
        n05_payload,
        n05_status,
        n05_reason,
        tuple(
            _artifact_ref(item.to_dict(), f"{item.artifact_id}.json")
            for item in generations
        ),
    )
    store.write_artifact(n05)

    result = {
        "schema_version": "server-automation-preparation/1.0",
        "workflow_run_id": identity[0],
        "source_snapshot_id": identity[2],
        "server_layers": sorted(SERVER_LAYERS),
        "aggregate_agent_id": "B01",
        "skill_registry_hash": registry.registry_hash,
        "planned_generation_case_ids": sorted(
            str(case["id"]) for items in groups.values() for case in items
        ),
        "generated_artifacts": [
            {
                "component_id": item.producer.component_id,
                "artifact_id": item.artifact_id,
                "status": item.status.value,
                "artifact_hash": item.artifact_hash,
            }
            for item in generations
        ],
        "review_artifacts": [
            {
                "component_id": item.producer.component_id,
                "artifact_id": item.artifact_id,
                "status": item.status.value,
                "artifact_hash": item.artifact_hash,
            }
            for item in reviews
        ],
        "n05_artifact": {
            "artifact_id": n05.artifact_id,
            "status": n05.status.value,
            "artifact_hash": n05.artifact_hash,
        },
        "manual_case_ids": sorted(manual_case_ids),
        "excluded_non_server_case_ids": sorted(excluded_case_ids),
        "deferred_case_ids": sorted(deferred_case_ids),
        "test_data_validation_hash": (
            str(data_validation["artifact_hash"]) if data_validation is not None else None
        ),
        "test_data_resource_plan_hash": (
            str(data_resource_plan["artifact_hash"]) if data_resource_plan is not None else None
        ),
        "knowledge_packet_hash": (
            str(knowledge_readiness.get("packet_hash", ""))
            if knowledge_readiness is not None else None
        ),
        "rejected_cases": rejected,
        "ready_for_n08": passed
        and all(item.status == ArtifactStatus.COMPLETED for item in reviews),
    }
    store.write_json("server-automation-preparation.json", result)
    return result
