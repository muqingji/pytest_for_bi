"""A13/A15/A16/A17-* generation, A18-* review and N05 checks."""

from copy import deepcopy
from pathlib import Path

from qa_agents.agents import (
    AUTOMATION_PROFILES,
    DomainAutomationAgent,
    DomainAutomationReviewAgent,
    profile_for_case,
)
from qa_agents.agents.base import AgentContext
from qa_agents.automation import AutomationPolicy, check_automation_generation
from qa_agents.contracts import ArtifactStatus, content_hash
from qa_agents.security import SecurityPolicy


ROOT = Path(__file__).resolve().parents[1]


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


def case(layer: str, test_data: dict | None = None, **extra) -> dict:
    value = {
        "id": f"CASE-{layer.upper()}-001",
        "parent_case_id": f"PARENT-{layer.upper()}-001",
        "intent_ids": ["INTENT-001"],
        "title": f"{layer} 可执行测试",
        "layer": layer,
        "risk": "high",
        "priority": "P1",
        "source_refs": [
            {"type": "requirement", "id": "REQ-1", "location": "section-1"}
        ],
        "preconditions": ["准备测试账号"],
        "test_data": {"request": {"method": "GET", "path": "/api/report"}},
        "steps": [
            {
                "name": "执行场景",
                "request": {"api": "fs_bi_stat.describe_query.detail", "json": {}},
            }
        ],
        "expected": [
            {
                "id": "EXP-01",
                "description": "结果符合预期",
                "oracle": {
                    "type": "deterministic",
                    "observation_point": "response.dataRowsAll[*].value",
                    "matcher": "equals:expected",
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
    if test_data is not None:
        value["test_data"] = test_data
    value.update(extra)
    return value


def frontend_case() -> dict:
    return case(
        "frontend",
        {
            "route": "/report/detail",
            "locators": ["role:button[name=查询]", "testid:detail-table"],
        },
    )


def contract_case() -> dict:
    return case(
        "contract",
        {
            "contract_ref": "openapi:report-service/v1",
            "method": "GET",
            "path": "/api/report/detail",
        },
    )


def e2e_case() -> dict:
    return case(
        "e2e",
        {
            "journey": "用户下钻查看明细",
            "cross_service_evidence": True,
        },
    )


def non_functional_case(kind: str) -> dict:
    return case(
        "non_functional",
        {
            "metric": "p95_latency",
            "threshold": 2000,
            "threshold_source": "approved-standard:performance-baseline-v1",
        },
        non_functional_kind=kind,
    )


def run_profile(agent_id: str, cases: list[dict]):
    security = SecurityPolicy()
    profile = AUTOMATION_PROFILES[agent_id]
    generation = DomainAutomationAgent(profile).run(
        context(), {"cases": cases, "target": target()}, security
    )
    assert generation.status == ArtifactStatus.COMPLETED
    review = DomainAutomationReviewAgent(profile).run(
        context(), {"cases": cases, "generation": generation.payload}, security
    )
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    check = check_automation_generation(generation.payload, policy)
    return generation, review, check


def test_frontend_profile_generates_reviews_and_passes_n05() -> None:
    generation, review, check = run_profile("A13", [frontend_case()])
    assert generation.payload["manifest"]["framework"] == "playwright"
    assert generation.payload["manifest"]["generator_profile"] == "A13/1.0.0"
    assert generation.payload["manifest"]["candidate_files"][0]["path"].startswith(
        "generated/frontend/"
    )
    assert review.producer.runtime == "automation-review-runtime"
    assert review.payload["review_profile"] == "A18-FE/1.0.0"
    assert review.payload["approved"] is True
    assert check["passed"] is True
    assert check["fatal_security_violation"] is False


def test_contract_profile_generates_reviews_and_passes_n05() -> None:
    generation, review, check = run_profile("A15", [contract_case()])
    assert generation.payload["manifest"]["framework"] == "pytest"
    assert generation.payload["manifest"]["generator_profile"] == "A15/1.0.0"
    assert generation.payload["manifest"]["candidate_files"][0]["path"].startswith(
        "generated/contract/"
    )
    assert review.payload["review_profile"] == "A18-CT/1.0.0"
    assert review.payload["approved"] is True
    assert check["passed"] is True


def test_e2e_profile_generates_reviews_and_passes_n05() -> None:
    generation, review, check = run_profile("A16", [e2e_case()])
    assert generation.payload["manifest"]["framework"] == "playwright"
    assert generation.payload["manifest"]["generator_profile"] == "A16/1.0.0"
    assert generation.payload["manifest"]["candidate_files"][0]["path"].startswith(
        "generated/e2e/"
    )
    assert review.payload["review_profile"] == "A18-E2E/1.0.0"
    assert review.payload["approved"] is True
    assert check["passed"] is True


def test_generator_splits_manual_oracles_without_dropping_automated_subset() -> None:
    mixed = case("backend")
    mixed["expected"].append(
        {
            "id": "EXP-MANUAL",
            "description": "人工确认终端视觉结果",
            "oracle": {"matcher": "manual_confirmation"},
        }
    )
    generation, review, check = run_profile("A14", [mixed])

    mapping = generation.payload["manifest"]["case_mappings"][0]
    assert mapping["expected_ids"] == ["EXP-01"]
    assert mapping["manual_expected_ids"] == ["EXP-MANUAL"]
    assert "EXP-MANUAL" not in generation.payload["code_candidates"][0]["content"]
    assert review.payload["approved"] is True
    assert check["passed"] is True


def test_non_functional_profiles_generate_and_review() -> None:
    expected = {
        "performance": ("A17-PERF", "A18-PERF"),
        "security": ("A17-SEC", "A18-SEC"),
        "accessibility": ("A17-A11Y", "A18-A11Y"),
        "compatibility": ("A17-COMPAT", "A18-COMPAT"),
        "resilience": ("A17-RES", "A18-RES"),
        "data_consistency": ("A17-DATA", "A18-DATA"),
    }
    for kind, (generator_id, reviewer_id) in expected.items():
        generation, review, check = run_profile(generator_id, [non_functional_case(kind)])
        assert generation.payload["manifest"]["generator_profile"] == f"{generator_id}/1.0.0"
        assert generation.payload["manifest"]["candidate_files"][0]["path"].startswith(
            "generated/non_functional/"
        )
        assert review.payload["review_profile"] == f"{reviewer_id}/1.0.0"
        assert review.payload["approved"] is True
        assert check["passed"] is True


def test_frontend_generator_rejects_unstable_locator() -> None:
    bad = frontend_case()
    bad["test_data"]["locators"] = ["button.primary > span:nth-child(2)"]
    security = SecurityPolicy()
    generation = DomainAutomationAgent(AUTOMATION_PROFILES["A13"]).run(
        context(), {"cases": [bad], "target": target()}, security
    )
    assert generation.status == ArtifactStatus.NOT_APPLICABLE
    assert generation.reason_code == "no_machine_executable_frontend_case"
    assert generation.payload["rejected_cases"] == [
        {"case_id": bad["id"], "reason_code": "frontend_locator_not_stable"}
    ]


def test_frontend_reviewer_rejects_unstable_locator_and_missing_driver() -> None:
    generated = DomainAutomationAgent(AUTOMATION_PROFILES["A13"]).run(
        context(),
        {"cases": [frontend_case()], "target": target()},
        SecurityPolicy(),
    ).payload
    candidate = generated["code_candidates"][0]
    tampered_spec = deepcopy(candidate)
    tampered_spec["content"] = (
        candidate["content"]
        .replace("'driver': 'playwright'", "'driver': 'webdriver'")
        .replace("'testid:detail-table'", "'#detail-table'")
    )
    tampered_spec["content_hash"] = content_hash(tampered_spec["content"])
    generated["code_candidates"] = [tampered_spec]
    generated["manifest"]["candidate_files"][0]["content_hash"] = tampered_spec["content_hash"]
    review = DomainAutomationReviewAgent(AUTOMATION_PROFILES["A13"]).run(
        context(), {"cases": [frontend_case()], "generation": generated}, SecurityPolicy()
    )
    assert review.payload["approved"] is False
    codes = {item["issue_code"] for item in review.payload["issues"]}
    assert {"ui_driver_missing", "unstable_locator"} <= codes


def test_n05_rejects_frontend_candidate_in_backend_root() -> None:
    generated = DomainAutomationAgent(AUTOMATION_PROFILES["A13"]).run(
        context(),
        {"cases": [frontend_case()], "target": target()},
        SecurityPolicy(),
    ).payload
    path = generated["code_candidates"][0]["path"]
    generated["code_candidates"][0]["path"] = path.replace(
        "generated/frontend", "generated/backend"
    )
    generated["manifest"]["candidate_files"][0]["path"] = generated["code_candidates"][0]["path"]
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    check = check_automation_generation(generated, policy)
    assert check["passed"] is False
    assert check["fatal_security_violation"] is True
    assert "candidate_path_not_allowed" in {item["issue_code"] for item in check["issues"]}


def test_frontend_generator_never_requests_business_repo_write() -> None:
    generated = DomainAutomationAgent(AUTOMATION_PROFILES["A13"]).run(
        context(),
        {"cases": [frontend_case()], "target": target()},
        SecurityPolicy(),
    ).payload
    assert generated["manifest"]["permissions"]["business_repository_write"] is False
    assert generated["manifest"]["target_repository"]["write_mode"] == (
        "artifact_only_candidate"
    )
    business_target = deepcopy(generated)
    business_target["manifest"]["target_repository"]["repository_id"] = "fs-bi"
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    check = check_automation_generation(business_target, policy)
    assert check["fatal_security_violation"] is True
    assert "target_repository_not_approved" in {item["issue_code"] for item in check["issues"]}


def test_profile_for_case_dispatches_layer_and_non_functional_kind() -> None:
    assert profile_for_case(frontend_case()).agent_id == "A13"
    assert profile_for_case(case("backend")).agent_id == "A14"
    assert profile_for_case(contract_case()).agent_id == "A15"
    assert profile_for_case(e2e_case()).agent_id == "A16"
    assert profile_for_case(non_functional_case("security")).agent_id == "A17-SEC"
    unknown = case("unknown_layer")
    assert profile_for_case(unknown) is None


def test_policy_layer_profiles_are_consistent_with_code_registry() -> None:
    import json

    with (ROOT / "policies" / "automation-target-policy.json").open(encoding="utf-8") as file:
        policy = json.load(file)
    for layer, config in policy["layer_profiles"].items():
        if layer == "non_functional":
            continue
        profile = AUTOMATION_PROFILES[config["agent_id"]]
        assert profile.generator_profile == config["generator_profile"]
        assert profile.review_profile == config["review_profile"]
        assert profile.manifest_id == config["manifest_id"]
        assert profile.framework == config["framework"]
        assert profile.candidate_root == config["candidate_root"]
    for kind, config in policy["layer_profiles"]["non_functional"]["kinds"].items():
        profile = AUTOMATION_PROFILES[config["agent_id"]]
        assert profile.kind == kind
        assert profile.generator_profile == config["generator_profile"]
        assert profile.review_profile == config["review_profile"]
        assert profile.framework == config["framework"]
