from copy import deepcopy
from pathlib import Path

from qa_agents.agents import BackendAutomationAgent, BackendAutomationReviewAgent
from qa_agents.agents.base import AgentContext
from qa_agents.automation import AutomationPolicy, check_automation_generation
from qa_agents.contracts import ArtifactStatus
from qa_agents.security import SecurityPolicy


ROOT = Path(__file__).resolve().parents[1]


def backend_case() -> dict:
    return {
        "id": "CASE-001-BACKEND",
        "parent_case_id": "CASE-001",
        "intent_ids": ["INTENT-001"],
        "title": "无权限请求返回 403",
        "layer": "backend",
        "risk": "high",
        "priority": "P1",
        "source_refs": [
            {"type": "requirement", "id": "REQ-1", "location": "section-1"}
        ],
        "preconditions": ["使用无权限账号"],
        "test_data": {"request": {"method": "GET", "path": "/api/report"}},
        "steps": ["请求报表接口"],
        "expected": [
            {
                "id": "EXP-01",
                "description": "接口拒绝请求",
                "oracle": {
                    "type": "deterministic",
                    "observation_point": "response.status",
                    "matcher": "equals:403",
                    "source_ref": "REQ-1:section-1",
                },
            }
        ],
        "cleanup": [],
        "execution_policy": {
            "allowed_modes": ["automated"],
            "required_evidence": ["request_response"],
        },
        "automation_candidate": True,
    }


def context() -> AgentContext:
    return AgentContext("run-1", "new_requirement", "snapshot-1", ("input/cases.json",))


def target() -> dict:
    return {
        "repository_id": "pytest_for_bi",
        "access_class": "approved_automation_repository",
        "timeout_seconds": 300,
        "network": False,
        "secrets": [],
    }


def test_backend_generation_review_and_n05_check_are_separate() -> None:
    security = SecurityPolicy()
    case = backend_case()
    generation = BackendAutomationAgent().run(
        context(), {"cases": [case], "target": target()}, security
    )
    assert generation.status == ArtifactStatus.COMPLETED
    assert generation.payload["manifest"]["target_repository"]["write_mode"] == (
        "artifact_only_candidate"
    )

    review = BackendAutomationReviewAgent().run(
        context(), {"cases": [case], "generation": generation.payload}, security
    )
    assert review.producer.runtime == "automation-review-runtime"
    assert review.payload["approved"] is True
    assert review.payload["generator_hidden_reasoning_accessed"] is False

    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    code_check = check_automation_generation(generation.payload, policy)
    assert code_check["passed"] is True
    assert code_check["fatal_security_violation"] is False


def test_n05_rejects_business_repository_and_tampered_candidate() -> None:
    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")

    business_target = deepcopy(generation)
    business_target["manifest"]["target_repository"]["repository_id"] = "fs-bi"
    result = check_automation_generation(business_target, policy)
    assert result["passed"] is False
    assert result["fatal_security_violation"] is True
    assert {item["issue_code"] for item in result["issues"]} == {
        "target_repository_not_approved"
    }

    tampered = deepcopy(generation)
    tampered["code_candidates"][0]["content"] += "\n# changed after generation\n"
    result = check_automation_generation(tampered, policy)
    assert result["passed"] is False
    assert result["fatal_security_violation"] is False
    assert {item["issue_code"] for item in result["issues"]} == {
        "candidate_hash_mismatch"
    }
    assert result["repair_routes"] == ["A14"]


def test_n05_rejects_command_injection_and_unapproved_runtime_call() -> None:
    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")

    command_injection = deepcopy(generation)
    command_injection["manifest"]["execution"]["command"].append("--pdb")
    result = check_automation_generation(command_injection, policy)
    assert result["fatal_security_violation"] is True
    assert "execution_command_mismatch" in {
        item["issue_code"] for item in result["issues"]
    }

    runtime_escape = deepcopy(generation)
    candidate = runtime_escape["code_candidates"][0]
    candidate["content"] += "\ncase_runner.shell('whoami')\n"
    from qa_agents.contracts import content_hash

    candidate["content_hash"] = content_hash(candidate["content"])
    runtime_escape["manifest"]["candidate_files"][0]["content_hash"] = candidate[
        "content_hash"
    ]
    result = check_automation_generation(runtime_escape, policy)
    assert result["fatal_security_violation"] is True
    assert "unapproved_runtime_call" in {
        item["issue_code"] for item in result["issues"]
    }


def test_manual_oracle_is_not_generated_as_automation() -> None:
    case = backend_case()
    case["expected"][0]["oracle"]["matcher"] = "manual_confirmation"
    case["execution_policy"]["allowed_modes"] = ["manual"]
    generation = BackendAutomationAgent().run(
        context(), {"cases": [case], "target": target()}, SecurityPolicy()
    )
    assert generation.status == ArtifactStatus.NOT_APPLICABLE
    assert generation.reason_code == "no_machine_executable_integration_or_functional_case"
    assert generation.payload["manifest"] is None
