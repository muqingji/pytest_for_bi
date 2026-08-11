from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.contracts import ArtifactEnvelope, Producer
from qa_agents.data_planning import (
    compile_resource_plan,
    extract_test_data_intents,
    prepare_autonomous_test_data_plan,
    validate_capability_catalog,
    validate_knowledge_sources,
    verify_knowledge_snapshots,
)
from qa_agents.errors import ContractError
from qa_agents.test_data import bind_plan_to_case, validate_test_data_plan


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "knowledge/bi-knowledge-sources.json"
CATALOG = ROOT / "knowledge/bi-data-capability-catalog.json"
POLICY = ROOT / "policies/test-data-policy.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _semantic_case(variants: list[str] | None = None) -> dict:
    test_data = {
        "dataset": "result_set_metric_types",
        "metric_name": "自动构造指标",
    }
    if variants is not None:
        test_data["variants"] = variants
    return {
        "id": "CASE-AUTO-DATA-001",
        "title": "结果集筛选指标查看明细返回指标名称",
        "test_level": "functional",
        "preconditions": ["指标在数据范围中启用结果集筛选"],
        "test_data": test_data,
        "steps": [{"action": "查看明细"}],
        "expected": [{"description": "返回不支持提示和实际指标名称"}],
    }


def test_official_sources_and_capability_catalog_are_traceable() -> None:
    sources = _load(SOURCES)
    source_result = validate_knowledge_sources(sources)
    catalog_result = validate_capability_catalog(_load(CATALOG), sources)
    snapshot_result = verify_knowledge_snapshots(sources, project_root=ROOT)

    assert source_result["available_count"] == 13
    assert source_result["unavailable_count"] == 1
    assert catalog_result["recipe_count"] == 1
    assert catalog_result["catalog_hash"].startswith("sha256:")
    assert snapshot_result["verified_snapshot_count"] == 2


def test_case_semantics_compile_to_executable_resource_lifecycle() -> None:
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([_semantic_case(["聚合指标"])], catalog)

    assert intent["unresolved_requirements"] == []
    assert intent["case_intents"][0]["recipe_id"] == (
        "aggregate-metric-result-set-filter"
    )
    plan = compile_resource_plan(
        intent,
        catalog,
        environment="112",
        namespace="qa-autonomous-data-001",
    )
    validation = validate_test_data_plan(plan, _load(POLICY))

    assert validation["valid"] is True
    assert validation["planning_mode"] == "autonomous"
    assert validation["write_authorized"] is True
    case_plan = plan["case_plans"][0]
    assert case_plan["resources"][0]["setup"]["request"]["api"] == (
        "fs_bi_stat.agg_rule.add_new_agg_rule"
    )
    assert case_plan["resources"][0]["cleanup"]["request"]["api"] == (
        "fs_bi_stat.agg_rule.delete_agg_rule"
    )
    bound = bind_plan_to_case(_semantic_case(["聚合指标"]), plan)
    assert bound["setup"]
    assert bound["readiness"]
    assert bound["cleanup"][0]["when_variable"] == "metric_field_id"
    assert bound["variables"]["schema_id"] == "BI_e672ff1046fb773b76bc2b56"
    assert bound["variables"]["metric_name"] == (
        "qa-autonomous-data-001-result-filter-metric"
    )


def test_unsupported_case_variants_are_adapter_backlog_not_fake_completion() -> None:
    intent = extract_test_data_intents(
        [_semantic_case(["普通指标", "聚合指标", "计算指标", "同环比指标"])],
        _load(CATALOG),
    )

    assert intent["unresolved_requirements"] == [
        {
            "case_id": "CASE-AUTO-DATA-001",
            "reason_code": "data_capability_variant_not_registered",
            "recipe_id": "aggregate-metric-result-set-filter",
            "missing_variants": ["普通指标", "计算指标", "同环比指标"],
            "route_to": "capability_adapter_backlog",
        }
    ]


def test_catalog_rejects_recipe_without_available_evidence() -> None:
    sources = _load(SOURCES)
    catalog = _load(CATALOG)
    catalog["recipes"][0]["evidence_refs"].append("bi-product-whitepaper")

    with pytest.raises(ContractError, match="unavailable source"):
        validate_capability_catalog(catalog, sources)


def test_autonomous_pipeline_writes_hash_bound_a22_n28_n27_artifacts(
    tmp_path: Path,
) -> None:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-autonomous-1",
        workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "compiled_cases": [_semantic_case(["聚合指标"])],
        },
    )
    compiled_path = tmp_path / "n25.json"
    compiled_path.write_text(json.dumps(compiled.to_dict()), encoding="utf-8")

    result = prepare_autonomous_test_data_plan(
        compiled_path,
        SOURCES,
        CATALOG,
        POLICY,
        tmp_path / "out",
        environment="112",
        namespace="qa-autonomous-data-001",
    )

    assert result["ready_for_execution"] is True
    assert result["resolved_case_count"] == 1
    assert (tmp_path / "out/artifacts/a22-test-data-intent.json").exists()
    assert (tmp_path / "out/artifacts/n28-test-data-resource-plan.json").exists()
    n27 = _load(tmp_path / "out/artifacts/n27-test-data-plan-validation.json")
    assert n27["payload"]["n28_artifact_hash"] == result["n28_artifact_hash"]
