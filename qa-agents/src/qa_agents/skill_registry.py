"""Versioned Skill registry and deterministic B01/D01 authorization Router."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from .contracts import content_hash
from .errors import ContractError, InputError, SecurityPolicyError


SHARED_PYTEST = (
    "pytest-parameterization", "pytest-oracle-assertions", "pytest-fixture-binding",
    "pytest-evidence", "pytest-security-boundary", "retained-test-asset-naming",
)
COMMON_DATA = (
    "data-intent-parser", "capability-catalog-resolver", "resource-dag-planner",
    "namespace-isolation", "setup-plan", "readiness-plan", "cleanup-plan",
    "residue-verification", "runtime-variable-binding", "data-plan-security-review",
    "retained-test-asset-naming",
)


class SkillRegistry:
    def __init__(self, value: Mapping[str, Any], *, root: Path | None = None) -> None:
        if value.get("schema_version") != "skill-registry/1.0":
            raise ContractError("Skill registry schema_version is invalid")
        skills = value.get("skills")
        if not isinstance(skills, list) or not skills:
            raise ContractError("Skill registry requires skills")
        self.value = dict(value)
        self.root = root
        self.skills: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(skills):
            if not isinstance(item, Mapping):
                raise ContractError(f"skills[{index}] must be an object")
            skill_id, version = str(item.get("id", "")), str(item.get("version", ""))
            if not skill_id or not version or skill_id in self.skills:
                raise ContractError("Skill IDs must be unique and versioned")
            if item.get("side_effect") not in {"artifact_only", "planning_only", "validation_only"}:
                raise SecurityPolicyError(f"Skill {skill_id} requests an unsafe side effect")
            self.skills[skill_id] = dict(item)
            if root is not None and not (root / skill_id / "SKILL.md").is_file():
                raise ContractError(f"Published Skill package is missing: {skill_id}")
        self.registry_hash = content_hash(value)

    @classmethod
    def from_file(cls, path: Path) -> "SkillRegistry":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise InputError(f"Required Skill registry is missing: {path}") from error
        except (OSError, json.JSONDecodeError) as error:
            raise ContractError(f"Skill registry is invalid JSON: {path}") from error
        skills_root = path.parent.parent / str(value.get("skills_root", "skills"))
        return cls(value, root=skills_root)

    def refs(self, skill_ids: list[str] | tuple[str, ...], agent_id: str) -> list[str]:
        refs: list[str] = []
        for skill_id in skill_ids:
            skill = self.skills.get(skill_id)
            if skill is None:
                raise SecurityPolicyError(f"Skill is not published: {skill_id}")
            if agent_id not in skill.get("agents", []):
                raise SecurityPolicyError(f"Skill {skill_id} is not authorized for {agent_id}")
            refs.append(f"{skill_id}/{skill['version']}")
        return refs

    def validate_authorization(self, authorization: Mapping[str, Any], *, agent_id: str) -> None:
        if authorization.get("schema_version") != "skill-authorization/1.0":
            raise ContractError("Skill authorization contract is invalid")
        if authorization.get("agent_id") != agent_id:
            raise SecurityPolicyError("Skill authorization agent identity mismatch")
        if authorization.get("registry_hash") != self.registry_hash:
            raise SecurityPolicyError("Skill authorization registry hash mismatch")
        expected = self.refs(
            [str(ref).rsplit("/", 1)[0] for ref in authorization.get("required_skills", [])],
            agent_id,
        )
        if expected != authorization.get("required_skills"):
            raise SecurityPolicyError("Skill authorization contains unknown or stale versions")


def route_backend_case(case: Mapping[str, Any], registry: SkillRegistry) -> dict[str, Any]:
    layer = str(case.get("layer", "")).lower()
    level = str(case.get("test_level", "api") or "api").lower()
    if layer not in {"backend", "contract"}:
        raise SecurityPolicyError("B01 cannot route frontend or non-server Cases")
    if level in {"unit", "unit_test", "单元", "单元测试"}:
        raise SecurityPolicyError("B01 cannot route developer unit tests")
    primary = "pytest-contract-test" if layer == "contract" else (
        "pytest-integration-test" if level in {"integration", "integration_test", "集成"}
        else "pytest-api-test"
    )
    agent_id = "A15" if layer == "contract" else "A14"
    refs = registry.refs([primary, *SHARED_PYTEST], agent_id)
    return {
        "schema_version": "skill-authorization/1.0", "aggregate_agent_id": "B01",
        "agent_id": agent_id, "case_id": str(case.get("id", "")),
        "required_skills": refs,
        "forbidden_skills": list(registry.value.get("forbidden_skills", [])),
        "allowed_tools": ["case_runner"], "registry_hash": registry.registry_hash,
    }


def route_data_plan(
    cases: list[Mapping[str, Any]], catalog: Mapping[str, Any], registry: SkillRegistry
) -> dict[str, Any]:
    text = json.dumps(cases, ensure_ascii=False).lower()
    resource_types: set[str] = set()
    for recipe in catalog.get("recipes", []):
        if not isinstance(recipe, Mapping):
            continue
        match = recipe.get("match", {})
        terms = [
            str(term).lower() for group in match.get("all_term_groups", [])
            if isinstance(group, list) for term in group
        ] if isinstance(match, Mapping) else []
        datasets = {
            str(case.get("test_data", {}).get("dataset", ""))
            for case in cases if isinstance(case.get("test_data"), Mapping)
        }
        matched = bool(set(match.get("datasets", [])) & datasets) if isinstance(match, Mapping) else False
        matched = matched or any(term in text for term in terms)
        if matched:
            resource_types.update(
                str(goal.get("resource_type", ""))
                for goal in recipe.get("resource_goals", []) if isinstance(goal, Mapping)
            )
    mapping = {"stat_schema":"bi-stat-schema", "aggregate_metric":"bi-aggregate-metric",
               "calculated_metric":"bi-calculated-metric", "custom_dimension":"bi-custom-dimension"}
    selected = list(COMMON_DATA) + [mapping[item] for item in sorted(resource_types) if item in mapping]
    if any(term in text for term in ("result_set_filter", "result-set-filter", "结果集筛选", "结果集数据范围")):
        selected.append("bi-result-set-filter")
    refs = registry.refs(list(dict.fromkeys(selected)), "D01")
    return {
        "schema_version": "skill-authorization/1.0", "aggregate_agent_id": "D01",
        "agent_id": "D01", "required_skills": refs,
        "forbidden_skills": list(registry.value.get("forbidden_skills", [])),
        "allowed_tools": [], "registry_hash": registry.registry_hash,
    }
