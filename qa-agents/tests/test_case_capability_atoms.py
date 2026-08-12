from qa_agents.case_compiler import project_capability_atoms


def test_composite_case_projects_evidence_bound_atoms_without_claiming_parent_oracle() -> None:
    case = {
        "id": "PC-002-BACKEND",
        "layer": "backend",
        "parent_case_id": "PC-002",
        "source_refs": ["REQ-001", "RULE-I18N-RESULT-SET"],
        "test_data": {"datasets": [
            {"type": "ordinary", "zh_CN": "收入"},
            {"type": "aggregate", "zh_CN": "成交额"},
            {"type": "calculated", "zh_CN": "利润率"},
            {"type": "comparison", "zh_CN": "收入同比"},
        ]},
        "expected": [
            {"id": "PC-002-E01", "oracle": {"type": "deterministic"}},
            {"id": "PC-002-E04", "oracle": {"type": "human_review"}},
        ],
    }
    capabilities = {
        "aggregate": {"allowed_layers": ["backend"], "label": "聚合指标", "dataset": "aggregate", "data_intent": "agg", "recipe_id": "agg/1"},
        "calculated": {"allowed_layers": ["backend"], "label": "计算指标", "dataset": "calculated", "data_intent": "calc", "recipe_id": "calc/1"},
    }

    result = project_capability_atoms([case], capabilities)

    assert [item["id"] for item in result["atoms"]] == [
        "PC-002-BACKEND::ordinary", "PC-002-BACKEND::aggregate",
        "PC-002-BACKEND::calculated", "PC-002-BACKEND::comparison",
    ]
    aggregate = result["atoms"][1]
    assert aggregate["parent_case_id"] == "PC-002-BACKEND"
    assert aggregate["approved_parent_case_id"] == "PC-002"
    assert aggregate["source_refs"] == case["source_refs"]
    assert aggregate["capability_status"] == "registered"
    assert aggregate["parent_oracle_satisfied"] is False
    assert aggregate["parent_oracle_observations"] == [{
        "parent_oracle_id": "PC-002-E01", "satisfaction_mode": "contribution_only"
    }]
    assert result["atoms"][0]["capability_status"] == "deferred"
    aggregation = result["aggregations"][0]
    assert aggregation["manual_obligation_ids"] == ["PC-002-E04"]
    assert aggregation["oracle_rules"][0]["required_atom_ids"] == [
        item["id"] for item in result["atoms"]
    ]


def test_non_composite_case_is_not_projected() -> None:
    result = project_capability_atoms(
        [{"id": "CASE-1", "test_data": {"dataset": "one"}}], {}
    )
    assert result["atoms"] == []
    assert result["aggregations"] == []


def test_duplicate_variant_collection_is_not_treated_as_capability_matrix() -> None:
    case = {
        "id": "CASE-1",
        "test_data": {"datasets": [{"type": "aggregate"}, {"type": "aggregate"}]},
    }
    assert project_capability_atoms([case], {})["atoms"] == []
