from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.contracts import ArtifactEnvelope, Producer
from qa_agents.errors import ContractError
from qa_agents.recipe_adapter import (
    build_candidate_catalog,
    load_verified_contracts,
    prepare_recipe_candidates,
    select_candidates_for_cases,
    validate_recipe_candidates,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "knowledge/bi-knowledge-sources.json"
CATALOG = ROOT / "knowledge/bi-data-capability-catalog.json"
POLICY = ROOT / "policies/test-data-policy.json"
CONTRACTS_DIR = ROOT / "knowledge"


def _policy_pairs() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8")).get("operation_pairs", {})


def _catalog() -> dict:
    return build_candidate_catalog(
        load_verified_contracts(CONTRACTS_DIR),
        json.loads(SOURCES.read_text(encoding="utf-8")),
        _policy_pairs(),
    )


def test_candidates_from_verified_contracts_declare_evidence_gaps() -> None:
    candidates = _catalog()
    validation = validate_recipe_candidates(candidates)
    assert validation["valid"] is True
    by_id = {item["candidate_id"]: item for item in candidates["candidates"]}
    # aggregate metric is already a published recipe (zero gaps) and must not
    # be emitted as a candidate
    assert "aggregate_metric-create" not in by_id
    assert by_id["custom_dimension-create"]["verification_requirements"] == [
        {
            "code": "live_enum_option_bindings",
            "description": "enum_group dimensionConfig values must come from a live get_ui_type option query with response hash",
            "required_evidence": "option_query_operation + option_response_hash + selected_option_codes",
        }
    ]
    chart_codes = {
        item["code"] for item in by_id["stat_chart-create"]["verification_requirements"]
    }
    assert {"folder_binding", "configuration_hash", "cleanup_operation_pair"} <= chart_codes


def test_candidate_without_verification_requirements_is_rejected() -> None:
    candidates = _catalog()
    fake = json.loads(json.dumps(candidates))
    fake["candidates"][0]["verification_requirements"] = []
    with pytest.raises(ContractError, match="fake completion"):
        validate_recipe_candidates(fake)


def test_composite_chart_detail_candidate_has_dependency_and_roles() -> None:
    candidates = _catalog()
    by_id = {item["candidate_id"]: item for item in candidates["candidates"]}
    composite = by_id["metric-plus-stat-chart-detail"]
    assert composite["asset_types"] == ["aggregate_metric", "stat_chart"]
    metric, chart = composite["resources"]
    assert chart["depends_on"] == [metric["resource_key"]]
    assert {"source_field", "metric_or_dimension"} <= set(metric["scene_roles"])
    assert {
        "metric_or_dimension",
        "chart_or_pivot",
        "view_readiness",
        "detail_entry_execution",
    } <= set(chart["scene_roles"])


def test_select_candidates_for_cases_matches_by_terms_and_keeps_unmatched() -> None:
    candidates = _catalog()
    selection = select_candidates_for_cases(
        [
            {
                "case_id": "CASE-BACKLOG-001",
                "reason_code": "data_capability_not_registered",
                "dataset": "stat_chart",
                "title": "统计图查看明细",
            },
            {
                "case_id": "CASE-BACKLOG-002",
                "reason_code": "data_capability_not_registered",
                "dataset": "unknown_thing",
                "title": "未登记的资源类型",
            },
        ],
        candidates,
    )
    assert [item["case_id"] for item in selection["matched_cases"]] == ["CASE-BACKLOG-001"]
    assert [item["case_id"] for item in selection["unmatched_cases"]] == ["CASE-BACKLOG-002"]


def test_prepare_recipe_candidates_writes_selection_for_backlog_cases(
    tmp_path: Path,
) -> None:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-backlog-1",
        workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "compiled_cases": [
                {
                    "id": "CASE-BACKLOG-003",
                    "title": "统计图查看明细",
                    "test_level": "functional",
                    "preconditions": ["统计图已配置结果集筛选指标"],
                    "test_data": {"dataset": "stat_chart"},
                    "steps": [{"action": "查看明细"}],
                    "expected": [{"description": "返回明细"}],
                }
            ],
        },
    )
    compiled_path = tmp_path / "n25.json"
    compiled_path.write_text(json.dumps(compiled.to_dict()), encoding="utf-8")

    result = prepare_recipe_candidates(
        compiled_path,
        CONTRACTS_DIR,
        tmp_path / "out",
        environment="112",
        namespace="qa-backlog-001",
        capability_catalog_path=CATALOG,
        sources_path=SOURCES,
        policy_path=POLICY,
    )

    assert result["candidate_count"] >= 6
    assert result["matched_case_count"] == 1
    assert (tmp_path / "out/bi-recipe-candidates.json").exists()
    payload = json.loads(
        (tmp_path / "out/bi-recipe-candidates.json").read_text(encoding="utf-8")
    )
    assert payload["selection"]["matched_cases"][0]["case_id"] == "CASE-BACKLOG-003"
