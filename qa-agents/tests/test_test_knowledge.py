import pytest

from qa_agents.errors import ContractError
from qa_agents.test_knowledge import assess_automation_readiness, validate_test_knowledge_packet


def packet(case_id="CASE-1"):
    return {
        "schema_version": "test-knowledge-packet/1.0",
        "knowledge_snapshot_id": "ptkb-20260812",
        "cases": [{
            "case_id": case_id,
            "source_refs": [
                {"source_id": "openapi:query", "authority": "frozen_openapi", "contract_authority": True},
                {"source_id": "bug-finder:risk", "authority": "historical_risk", "contract_authority": False},
            ],
            "execution_chain": {"operations": [{
                "operation_id": "queryResult", "method": "POST", "path": "/api/query",
                "parameter_bindings": [{"name": "datasetId", "from": "dataset.id"}],
            }]},
            "data_recipe": {"resources": [{
                "id": "dataset", "depends_on": [], "create_capability": "dataset-create",
                "readiness": {"capability": "dataset-get"}, "cleanup": {"capability": "dataset-delete"},
            }]},
            "oracles": [
                {"type": "field", "path": "$.data.rows[0].id", "expected": "${record.id}", "source_ref": "openapi:query", "polarity": "positive"},
                {"type": "field", "path": "$.data.rows[*].id", "expected": "not_contains:${excluded.id}", "source_ref": "openapi:query", "polarity": "negative"},
            ],
        }],
    }


def test_complete_packet_is_ready():
    result = assess_automation_readiness(packet(), {"CASE-1"})
    assert result["status"] == "ready"
    assert result["ready_case_ids"] == ["CASE-1"]


def test_historical_knowledge_cannot_be_contract_authority():
    value = packet()
    value["cases"][0]["source_refs"][1]["contract_authority"] = True
    with pytest.raises(ContractError, match="historical knowledge"):
        validate_test_knowledge_packet(value)


def test_missing_current_contract_data_cleanup_and_negative_oracle_are_deferred():
    value = packet()
    value["cases"][0]["source_refs"] = [
        {"source_id": "bug-finder:risk", "authority": "historical_risk", "contract_authority": False}
    ]
    value["cases"][0]["data_recipe"]["resources"][0].pop("cleanup")
    value["cases"][0]["oracles"] = value["cases"][0]["oracles"][:1]
    result = assess_automation_readiness(value, {"CASE-1"})
    codes = {gap["code"] for gap in result["cases"][0]["gaps"]}
    assert {"current_contract_evidence_missing", "cleanup_capability_missing", "negative_oracle_missing"} <= codes


def test_packet_and_compiled_case_sets_must_align():
    result = assess_automation_readiness(packet(), {"CASE-2"})
    by_id = {item["case_id"]: item for item in result["cases"]}
    assert by_id["CASE-1"]["gaps"][0]["code"] == "compiled_case_missing"
    assert by_id["CASE-2"]["gaps"][0]["code"] == "knowledge_packet_case_missing"


def test_cyclic_data_recipe_is_deferred():
    value = packet()
    first = value["cases"][0]["data_recipe"]["resources"][0]
    first["depends_on"] = ["record"]
    value["cases"][0]["data_recipe"]["resources"].append({
        "id": "record", "depends_on": ["dataset"], "create_capability": "record-create",
        "readiness": {"capability": "record-get"}, "cleanup": {"capability": "record-delete"},
    })
    result = assess_automation_readiness(value, {"CASE-1"})
    assert "data_dependency_cycle" in {
        gap["code"] for gap in result["cases"][0]["gaps"]
    }


def test_unknown_data_dependency_is_deferred():
    value = packet()
    value["cases"][0]["data_recipe"]["resources"][0]["depends_on"] = ["missing"]
    result = assess_automation_readiness(value, {"CASE-1"})
    assert "data_dependency_unknown" in {
        gap["code"] for gap in result["cases"][0]["gaps"]
    }


def test_composite_case_requires_every_coverage_obligation():
    value = packet()
    value["cases"][0]["coverage_obligations"] = [
        {"id": "aggregate", "status": "ready"},
        {"id": "ordinary", "status": "deferred"},
    ]
    result = assess_automation_readiness(value, {"CASE-1"})
    assert "coverage_obligation_not_ready" in {
        gap["code"] for gap in result["cases"][0]["gaps"]
    }


def test_existing_read_only_fixture_requires_readiness_but_not_create_or_cleanup():
    value = packet()
    value["cases"][0]["data_recipe"]["resources"] = [{
        "id": "fixture", "depends_on": [], "lifecycle_mode": "existing_read_only",
        "readiness": {"capability": "field-query"},
    }]
    assert assess_automation_readiness(value, {"CASE-1"})["status"] == "ready"


def test_manual_obligation_keeps_parent_case_deferred():
    value = packet()
    value["cases"][0]["manual_obligations"] = [{"id": "M1"}]
    result = assess_automation_readiness(value, {"CASE-1"})
    assert result["cases"][0]["gaps"][0]["code"] == "manual_obligation_not_automatable"
