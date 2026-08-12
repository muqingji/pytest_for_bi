"""Deterministic N21 schema and N22 Agent release controls."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import content_hash
from .errors import ContractError, SecurityPolicyError


def _version(value: str) -> tuple[str, int, int]:
    try:
        name, raw = value.rsplit("/", 1)
        major, minor = raw.split(".", 1)
        return name, int(major), int(minor)
    except (ValueError, AttributeError) as error:
        raise ContractError(f"Invalid contract version: {value}") from error


def validate_schema_handoff(
    registry: Mapping[str, Any], *, contract: str, consumer: str
) -> dict[str, Any]:
    if registry.get("schema_version") != "schema-registry/1.0":
        raise ContractError("N21 schema registry version is invalid")
    name, major, minor = _version(contract)
    entry = registry.get("contracts", {}).get(name)
    if not isinstance(entry, Mapping):
        raise ContractError(f"N21 has no registered contract: {name}")
    published = entry.get("published_versions", [])
    if contract not in published:
        raise ContractError(f"Contract version is not published: {contract}")
    accepted = entry.get("consumers", {}).get(consumer)
    if not isinstance(accepted, list) or not accepted:
        raise ContractError(f"Consumer has no registered compatibility range: {consumer}")

    compatible = False
    for value in accepted:
        accepted_name, accepted_major, accepted_minor = _version(str(value))
        if accepted_name == name and accepted_major == major and minor >= accepted_minor:
            compatible = True
            break
    if not compatible:
        raise ContractError(f"Consumer {consumer} is incompatible with {contract}")
    result = {
        "schema_version": "schema-handoff-validation/1.0",
        "contract": contract,
        "consumer": consumer,
        "decision": "compatible",
        "registry_hash": content_hash(registry),
    }
    result["validation_hash"] = content_hash(result)
    return result


def decide_agent_release(
    policy: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    if policy.get("schema_version") != "agent-release-policy/1.0":
        raise ContractError("N22 Agent release policy version is invalid")
    if candidate.get("schema_version") != "agent-release-candidate/1.0":
        raise ContractError("N22 Agent release candidate version is invalid")
    profile_id = str(candidate.get("profile_id", ""))
    binding = policy.get("profiles", {}).get(profile_id)
    if not isinstance(binding, Mapping):
        raise ContractError(f"N22 has no release policy for {profile_id}")
    current = str(binding.get("production_version", ""))
    proposed = str(candidate.get("candidate_version", ""))
    if candidate.get("base_version") != current:
        raise ContractError("Agent candidate is based on a stale production version")
    if proposed == current:
        raise ContractError("Agent candidate must differ from production")
    if candidate.get("tools") != binding.get("allowed_tools", []):
        raise SecurityPolicyError("Agent candidate changes its frozen tool boundary")
    if candidate.get("output_contract") != binding.get("output_contract"):
        raise ContractError("Agent candidate changes its frozen output contract")

    evaluation = candidate.get("evaluation")
    shadow = candidate.get("shadow_run")
    if not isinstance(evaluation, Mapping) or not isinstance(shadow, Mapping):
        raise ContractError("Agent candidate requires evaluation and shadow-run evidence")
    thresholds = binding.get("promotion_thresholds", {})
    failures = []
    for metric, minimum in thresholds.items():
        actual = evaluation.get(metric)
        if not isinstance(actual, (int, float)) or actual < minimum:
            failures.append(metric)
    if shadow.get("status") != "passed" or shadow.get("production_side_effects") is not False:
        failures.append("shadow_run")
    decision = "rollback" if failures else "promote"
    target = current if failures else proposed
    result = {
        "schema_version": "agent-release-decision/1.0",
        "profile_id": profile_id,
        "current_version": current,
        "candidate_version": proposed,
        "decision": decision,
        "target_version": target,
        "failed_checks": sorted(failures),
        "policy_hash": content_hash(policy),
        "candidate_hash": content_hash(candidate),
    }
    result["decision_hash"] = content_hash(result)
    return result
