from qa_agents.gates import scope_gate_issues


def test_scope_gate_collects_only_blocking_or_high_risk_items() -> None:
    issues = scope_gate_issues(
        {"ambiguities": [{"issue_code": "requirement_missing"}]},
        {
            "blocking_items": [
                {
                    "issue_code": "product_acceptance_open_question",
                    "message": "No observation point",
                }
            ]
        },
        {
            "findings": [
                {"id": "LOW", "severity": "low", "type": "scope_drift"},
                {"id": "HIGH", "severity": "high", "type": "implementation_gap"},
            ]
        },
    )
    assert [item["source"] for item in issues] == ["A02", "A03", "A06"]
    assert [item["issue_code"] for item in issues] == [
        "requirement_missing",
        "product_acceptance_open_question",
        "implementation_gap",
    ]
