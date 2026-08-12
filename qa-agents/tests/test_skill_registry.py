from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from qa_agents.agents import DomainAutomationAgent, profile_for_case
from qa_agents.agents.base import AgentContext
from qa_agents.automation import AutomationPolicy, check_automation_generation
from qa_agents.errors import SecurityPolicyError
from qa_agents.security import SecurityPolicy
from qa_agents.skill_registry import SkillRegistry, route_backend_case, route_data_plan


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "policies/backend-skill-registry.json"


def _case(layer: str, level: str = "api") -> dict:
    return {
        "id": f"CASE-{layer}-{level}", "title": "case", "layer": layer,
        "test_level": level, "automation_candidate": True,
        "preconditions": [], "test_data": ({"contract_ref": "openapi:x"} if layer == "contract" else {}),
        "steps": ["call"],
        "expected": [{"id": "EXP-1", "oracle": {"matcher": "equals", "expected_value": 200}}],
        "cleanup": [], "execution_policy": {"allowed_modes": ["automated"]},
    }


def test_router_authorizes_backend_and_contract_without_frontend_or_unit() -> None:
    registry = SkillRegistry.from_file(REGISTRY)
    backend = route_backend_case(_case("backend", "integration"), registry)
    contract = route_backend_case(_case("contract"), registry)

    assert "pytest-integration-test/1.0.0" in backend["required_skills"]
    assert "pytest-contract-test/1.0.0" in contract["required_skills"]
    assert "pytest-security-boundary/1.0.0" in backend["required_skills"]
    with pytest.raises(SecurityPolicyError, match="non-server"):
        route_backend_case(_case("frontend"), registry)
    with pytest.raises(SecurityPolicyError, match="unit tests"):
        route_backend_case(_case("backend", "unit"), registry)


def test_n05_rejects_injected_skill_and_tool() -> None:
    registry = SkillRegistry.from_file(REGISTRY)
    case = _case("backend")
    profile = profile_for_case(case)
    assert profile is not None
    generation = DomainAutomationAgent(profile).run(
        AgentContext("run", "new_requirement", "snapshot", ()),
        {"cases": [case], "target": {"repository_id": "pytest_for_bi",
         "access_class": "approved_automation_repository", "timeout_seconds": 30,
         "network": False, "secrets": []},
         "skill_router_bindings": {case["id"]: route_backend_case(case, registry)}},
        SecurityPolicy(),
    ).payload
    tampered = deepcopy(generation)
    tampered["manifest"]["authorized_skills"].append("frontend-playwright/1.0.0")
    tampered["manifest"]["allowed_tools"].append("shell")
    result = check_automation_generation(
        tampered, AutomationPolicy.from_file(ROOT / "policies/automation-target-policy.json")
    )

    assert result["fatal_security_violation"] is True
    assert {item["issue_code"] for item in result["issues"]} >= {
        "unauthorized_skill", "unauthorized_tool"
    }


def test_data_router_authorizes_registered_resource_skills_only() -> None:
    registry = SkillRegistry.from_file(REGISTRY)
    catalog = json.loads((ROOT / "knowledge/bi-data-capability-catalog.json").read_text())
    authorization = route_data_plan(
        [{"id": "C", "title": "结果集筛选", "test_data": {"dataset": "result_set_metric_types"}}],
        catalog, registry,
    )
    assert "bi-aggregate-metric/1.0.0" in authorization["required_skills"]
    assert "bi-result-set-filter/1.0.0" in authorization["required_skills"]
    assert authorization["allowed_tools"] == []
