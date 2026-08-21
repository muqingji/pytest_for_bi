from copy import deepcopy

from qa_agents.case_executability import classify_case_executability


def _case() -> dict:
    return {
        "id": "CASE-BE-001",
        "title": "detail query",
        "layer": "backend",
        "automation_candidate": True,
        "execution_policy": {"allowed_modes": ["automated"]},
        "setup": [],
        "readiness": [],
        "steps": [
            {
                "name": "query",
                "request": {"api": "detail.query", "json": {}},
            }
        ],
        "cleanup": [],
        "residue_checks": [],
        "expected": [
            {
                "id": "EXP-1",
                "oracle": {
                    "type": "deterministic",
                    "matcher": "equals",
                    "observation_point": "response.code",
                    "expected_value": "OK",
                },
            }
        ],
    }


def test_classifies_machine_executable_case() -> None:
    result = classify_case_executability(
        _case(), known_operations={"detail.query"}
    )
    assert result == {
        "case_id": "CASE-BE-001",
        "classification": "machine_executable",
        "reason_codes": [],
        "issues": [],
    }


def test_classifies_unknown_operation_as_capability_missing() -> None:
    result = classify_case_executability(_case(), known_operations=set())
    assert result["classification"] == "capability_missing"
    assert result["reason_codes"] == ["operation_not_registered"]


def test_classifies_text_step_as_invalid_case() -> None:
    case = _case()
    case["steps"] = ["call the real endpoint"]
    result = classify_case_executability(case)
    assert result["classification"] == "invalid_case"
    assert "execution_step_not_structured" in result["reason_codes"]


def test_classifies_manual_oracle_as_manual_only() -> None:
    case = deepcopy(_case())
    case["execution_policy"]["allowed_modes"] = ["manual"]
    case["expected"][0]["oracle"]["matcher"] = "manual_confirmation"
    result = classify_case_executability(case)
    assert result["classification"] == "manual_only"
    assert result["reason_codes"] == ["case_not_machine_executable"]


def test_requires_readback_and_effective_setup_assertion() -> None:
    case = _case()
    case["setup"] = [
        {
            "request": {"api": "resource.create", "json": {}},
            "extract": {"resource_id": "Value.id"},
            "expect": {"status": "success"},
        }
    ]
    result = classify_case_executability(
        case, known_operations={"detail.query", "resource.create"}
    )
    assert result["classification"] == "invalid_case"
    assert "response_expectation_unsupported" in result["reason_codes"]
    assert "test_data_readiness_missing" in result["reason_codes"]
