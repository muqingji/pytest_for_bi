import pytest

from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.release_control import decide_agent_release, validate_schema_handoff


def registry():
    return {
        "schema_version": "schema-registry/1.0",
        "contracts": {
            "test-design-ir": {
                "published_versions": ["test-design-ir/1.0", "test-design-ir/1.1"],
                "consumers": {"A09": ["test-design-ir/1.1"]},
            }
        },
    }


def policy():
    return {
        "schema_version": "agent-release-policy/1.0",
        "profiles": {
            "A08": {
                "production_version": "1.3.0",
                "output_contract": "test-design-ir/1.1",
                "allowed_tools": ["read_attachment", "jq"],
                "promotion_thresholds": {"contract_pass_rate": 1.0, "semantic_pass_rate": 0.95},
            }
        },
    }


def candidate():
    return {
        "schema_version": "agent-release-candidate/1.0",
        "profile_id": "A08",
        "base_version": "1.3.0",
        "candidate_version": "1.3.1",
        "output_contract": "test-design-ir/1.1",
        "tools": ["read_attachment", "jq"],
        "evaluation": {"contract_pass_rate": 1.0, "semantic_pass_rate": 0.98},
        "shadow_run": {"status": "passed", "production_side_effects": False},
    }


def test_n21_accepts_registered_backward_compatible_minor() -> None:
    result = validate_schema_handoff(registry(), contract="test-design-ir/1.1", consumer="A09")
    assert result["decision"] == "compatible"
    assert result["validation_hash"].startswith("sha256:")


def test_n21_rejects_unpublished_or_incompatible_contract() -> None:
    with pytest.raises(ContractError, match="not published"):
        validate_schema_handoff(registry(), contract="test-design-ir/1.2", consumer="A09")
    with pytest.raises(ContractError, match="incompatible"):
        validate_schema_handoff(registry(), contract="test-design-ir/1.0", consumer="A09")


def test_n22_promotes_only_evaluated_side_effect_free_shadow() -> None:
    result = decide_agent_release(policy(), candidate())
    assert result["decision"] == "promote"
    assert result["target_version"] == "1.3.1"


def test_n22_rolls_back_failed_candidate_and_rejects_tool_expansion() -> None:
    value = candidate()
    value["evaluation"]["semantic_pass_rate"] = 0.8
    result = decide_agent_release(policy(), value)
    assert result["decision"] == "rollback"
    assert result["target_version"] == "1.3.0"
    value = candidate()
    value["tools"].append("shell")
    with pytest.raises(SecurityPolicyError, match="tool boundary"):
        decide_agent_release(policy(), value)
