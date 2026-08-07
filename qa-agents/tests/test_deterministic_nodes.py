from copy import deepcopy
from pathlib import Path

import pytest

from qa_agents.case_compiler import compile_cases
from qa_agents.change_set import normalize_change_set
from qa_agents.errors import InputError
from qa_agents.risk import RiskPolicyEngine
from qa_agents.selection import compile_execution_plan, select_cases
from qa_agents.validation import validate_test_case_ir


ROOT = Path(__file__).resolve().parents[1]


def merge_snapshot() -> dict:
    return {
        "implementation_source": {
            "repository_id": "fs-bi",
            "repository": "git@example/fs-bi.git",
            "access_class": "business_source_read_only",
            "commit": "head123",
            "commit_kind": "merge",
            "parents": ["base123", "feature123"],
            "comparison": {"mode": "first_parent", "base": "base123", "head": "head123"},
            "change_summary": {
                "files_changed": 2,
                "changed_paths": ["service/AuthService.java", "api/user.yaml"],
            },
        }
    }


def parent_case() -> dict:
    return {
        "id": "CASE-001",
        "parent_case_id": None,
        "intent_ids": ["INTENT-001"],
        "title": "验证权限",
        "layer": "scenario",
        "required_layers": ["backend", "contract"],
        "risk": "high",
        "priority": "P1",
        "source_refs": [{"type": "requirement", "id": "REQ-1", "location": "section-1"}],
        "preconditions": [],
        "test_data": {},
        "steps": ["请求接口"],
        "expected": [
            {
                "id": "EXP-01",
                "description": "拒绝无权限请求",
                "oracle": {
                    "type": "deterministic",
                    "observation_point": "response.status",
                    "matcher": "equals:403",
                    "source_ref": "REQ-1:section-1",
                },
            }
        ],
        "cleanup": [],
        "execution_policy": {"allowed_modes": ["automated"], "required_evidence": ["response"]},
        "automation_candidate": True,
    }


def test_merge_change_set_uses_first_parent() -> None:
    result = normalize_change_set(merge_snapshot())
    assert result["base_commit"] == "base123"
    assert result["diff_mode"] == "first_parent"
    assert result["diff_hash"].startswith("sha256:")


def test_merge_change_set_rejects_second_parent_baseline() -> None:
    snapshot = merge_snapshot()
    snapshot["implementation_source"]["comparison"]["base"] = "feature123"
    with pytest.raises(InputError):
        normalize_change_set(snapshot)


def test_risk_policy_is_deterministic_and_requires_applicable_layers() -> None:
    engine = RiskPolicyEngine.from_file(ROOT / "policies" / "risk-policy.json")
    workflow_input = {
        "title": "权限接口调整",
        "component_applicability": {
            "backend": {"status": "applicable"},
            "contract": {"status": "applicable"},
        },
    }
    first = engine.evaluate(workflow_input, normalize_change_set(merge_snapshot()), {"findings": []})
    second = engine.evaluate(workflow_input, normalize_change_set(merge_snapshot()), {"findings": []})
    assert first == second
    assert first["risk_level"] in {"high", "critical"}
    assert first["required_layers"] == ["backend", "contract"]
    assert first["unresolved_items"] == []


def test_case_compiler_preserves_oracle_and_selection_has_one_action() -> None:
    parent = parent_case()
    children = compile_cases([parent], {"required_layers": ["backend"]})
    assert [case["layer"] for case in children] == ["backend", "contract"]
    assert all(case["expected"] == parent["expected"] for case in children)
    assert validate_test_case_ir(children) == []

    selection = select_cases(children)
    plan = compile_execution_plan(selection, children)
    assert {item["action"] for item in plan["actions"]} == {"generate_new"}
    assert len({item["case_id"] for item in plan["actions"]}) == len(children)


def test_invalid_asset_mapping_is_not_silently_selected() -> None:
    children = compile_cases([parent_case()], {"required_layers": ["backend"]})
    assets = {"automation_assets": {children[0]["id"]: "invalid"}}
    selection = select_cases(children, assets)
    selected = {item["case_id"]: item for item in selection["selected_cases"]}
    assert selected[children[0]["id"]]["selection"] == "needs_human"
    assert selection["unresolved_items"] == [
        {"case_id": children[0]["id"], "reason_code": "invalid_asset_mapping"}
    ]


def test_manual_oracle_requires_manual_execution_mode() -> None:
    case = parent_case()
    case["expected"][0]["oracle"]["matcher"] = "manual_confirmation"
    issues = validate_test_case_ir([case])
    assert {issue.issue_code for issue in issues} == {"manual_oracle_not_routed"}

    fixed = deepcopy(case)
    fixed["execution_policy"]["allowed_modes"] = ["manual"]
    assert validate_test_case_ir([fixed]) == []
