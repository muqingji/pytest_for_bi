from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.contracts import ArtifactEnvelope, Producer
from qa_agents.data_planning import (
    compile_declared_a22_plan,
    compile_resource_plan,
    extract_test_data_intents,
    infer_data_intent,
    infer_resource_intents,
    prepare_autonomous_test_data_plan,
    select_test_subject,
    validate_capability_catalog,
    validate_knowledge_sources,
    verify_knowledge_snapshots,
    required_scene_for_case,
)
from qa_agents.errors import ContractError, InputError
from qa_agents.test_data import bind_plan_to_case, validate_test_data_plan


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "knowledge/bi-knowledge-sources.json"
CATALOG = ROOT / "knowledge/bi-data-capability-catalog.json"
POLICY = ROOT / "policies/test-data-policy.json"


MAINSTREAM_SUBJECTS = [
    {"schemaId": "sales-record", "schemaName": "销售记录统计", "describeApiName": "ActiveRecordObj", "status": 1},
    {"schemaId": "sales-order", "schemaName": "销售订单统计", "describeApiName": "SalesOrderObj", "status": 1},
    {"schemaId": "account", "schemaName": "客户统计", "describeApiName": "AccountObj", "status": 1},
    {"schemaId": "region", "schemaName": "区域测试", "describeApiName": "RegionObj", "status": 1},
]


def test_subject_selector_prefers_explicit_case_subject() -> None:
    selected = select_test_subject(MAINSTREAM_SUBJECTS, explicit_subject="销售订单")
    assert selected["schemaId"] == "sales-order"


def test_subject_selector_defaults_to_customer_and_never_region() -> None:
    selected = select_test_subject(MAINSTREAM_SUBJECTS)
    assert selected["schemaId"] == "account"

    with pytest.raises(InputError, match="forbidden fallback"):
        select_test_subject([MAINSTREAM_SUBJECTS[-1]])


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


def _metric_lifecycle_case(variants: list[str] | None = None) -> dict:
    case = _semantic_case(variants)
    case["test_data"]["required_scene"] = "metric_lifecycle"
    return case


def test_official_sources_and_capability_catalog_are_traceable() -> None:
    sources = _load(SOURCES)
    source_result = validate_knowledge_sources(sources)
    catalog_result = validate_capability_catalog(_load(CATALOG), sources)
    snapshot_result = verify_knowledge_snapshots(sources, project_root=ROOT)

    assert source_result["available_count"] == 14
    assert source_result["unavailable_count"] == 1
    assert catalog_result["recipe_count"] == 17
    assert catalog_result["catalog_hash"].startswith("sha256:")
    assert snapshot_result["verified_snapshot_count"] == 2


def test_case_semantics_compile_to_executable_resource_lifecycle() -> None:
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([_metric_lifecycle_case(["聚合指标"])], catalog)

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
    assert required_scene_for_case(_semantic_case(["聚合指标"])) == "chart_detail"
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
    assert [item["phase"] for item in bound["preparation"]] == ["setup", "readiness"]
    assert bound["cleanup"] == []
    assert bound["residue_checks"] == []
    assert bound["retention_mode"] == "retain"
    assert bound["retained_assets"][0]["display_name"] == "销售金额结果集筛选聚合指标"
    assert plan["lifecycle_schema_version"] == "test-data-lifecycle-plan/1.0"
    assert plan["ready_for_execution"] is True
    assert bound["variables"]["schema_id"] == "BI_e672ff1046fb773b76bc2b56"
    # namespace-prefixed display names avoid 聚合规则名称重复 on retain runs
    assert bound["variables"]["metric_name"] == (
        "qa-autonomous-data-001-销售金额结果集筛选聚合指标"
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


def test_composite_dataset_does_not_fuzzy_match_single_resource_recipe() -> None:
    case = _semantic_case(["聚合指标"])
    case["test_data"] = {
        "datasets": [
            {"type": "aggregate", "scenario": "result_set_filter"},
            {"type": "calculated", "scenario": "result_set_filter"},
        ]
    }

    intent = extract_test_data_intents([case], _load(CATALOG))

    assert intent["unresolved_requirements"] == [
        {
            "case_id": "CASE-AUTO-DATA-001",
            "reason_code": "data_capability_not_registered",
            "dataset": None,
            "route_to": "capability_adapter_backlog",
        }
    ]


def test_calculated_metric_recipe_has_dependency_order_and_strong_residue_checks() -> None:
    case = _semantic_case(["计算指标"])
    case["test_data"] = {
        "dataset": "calculated_result_filter_metric",
        "data_intent": "metric.calculated_result_set_filter.detail_unsupported",
        "variants": ["计算指标"],
    }
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([case], catalog)
    plan = compile_resource_plan(intent, catalog, environment="112", namespace="qa-calc-001")

    resources = plan["case_plans"][0]["resources"]
    assert [item["resource_key"] for item in resources] == [
        "aggregate_base", "calculated_metric"
    ]
    assert plan["cleanup_actions"] == []
    assert [item["resource_key"] for item in plan["retained_assets"]] == [
        "aggregate_base", "calculated_metric"
    ]
    assert resources[1]["setup"]["request"]["api"] == (
        "fs_bi_stat.stat_calc_field.save_calc_field"
    )
    assert resources[1]["cleanup"]["request"]["api"] == (
        "fs_bi_stat.stat_calc_field.delete_calc_field"
    )
    assert resources[1]["residue_checks"][0]["expect"]["body_not_contains_values"]


def test_n28_existing_asset_readiness_uses_discovery_not_residue_cleanup() -> None:
    intent = {
        "schema_version": "test-data-intent/1.0",
        "case_intents": [{
            "case_id": "PC-006",
            "requirement_name": "历史兼容",
            "required_scene": "",
            "recipe_id": "historical-chart",
        }],
        "paused_cases": [],
        "unresolved_requirements": [],
    }
    catalog = {
        "environment_profiles": {"112": {"environment": "112", "variables": {}}},
        "recipes": [{
            "id": "historical-chart", "version": "1.0", "environment_profile": "112",
            "evidence_refs": ["live-112"],
            "resources": [{
                "resource_key": "chart", "resource_type": "stat_chart",
                "resource_id_variable": "view_id", "depends_on": [],
                "lifecycle_mode": "existing_read_only",
                "discovery": {"request": {"api": "chart.query", "json": {}}},
                "readiness": [{"request": {"api": "chart.query", "json": {}}}],
                "existing_asset_evidence": {"live_readback_status": "succeeded"},
            }],
        }],
    }

    plan = compile_resource_plan(intent, catalog, environment="112", namespace="qa-pc006")

    assert plan["ready_for_execution"] is True
    assert plan["setup_actions"] == []
    assert plan["cleanup_actions"] == []


def test_catalog_rejects_recipe_without_available_evidence() -> None:
    sources = _load(SOURCES)
    catalog = _load(CATALOG)
    catalog["recipes"][0]["evidence_refs"].append("bi-product-whitepaper")

    with pytest.raises(ContractError, match="unavailable source"):
        validate_capability_catalog(catalog, sources)


def test_n27_rejects_resource_without_residue_verification() -> None:
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([_metric_lifecycle_case(["聚合指标"])], catalog)
    plan = compile_resource_plan(intent, catalog, environment="112", namespace="qa-no-residue-001")
    del plan["case_plans"][0]["resources"][0]["residue_checks"]

    with pytest.raises(Exception, match="requires residue verification"):
        validate_test_data_plan(plan, _load(POLICY))


def test_n27_rejects_retained_metric_without_typed_chinese_name() -> None:
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([_metric_lifecycle_case(["聚合指标"])], catalog)
    plan = compile_resource_plan(intent, catalog, environment="112", namespace="qa-name-001")
    resource = plan["case_plans"][0]["resources"][0]
    resource["display_name"] = "result metric"
    resource["source_field_type"] = ""

    with pytest.raises(Exception, match="typed Chinese semantic naming evidence"):
        validate_test_data_plan(plan, _load(POLICY))


def test_n27_rejects_chart_outside_requirement_folder() -> None:
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([_semantic_case(["聚合指标"])], catalog)
    plan = compile_resource_plan(intent, catalog, environment="112", namespace="qa-folder-001")
    case_plan = plan["case_plans"][0]
    resource = case_plan["resources"][0]
    resource["scene_roles"] = [
        "source_field", "metric_or_dimension", "requirement_folder",
        "chart_or_pivot", "view_readiness", "detail_entry_execution",
    ]
    resource["resource_type"] = "stat_chart"
    resource["asset_folder_name"] = "通用测试目录"

    with pytest.raises(Exception, match="chart folder must equal the requirement name"):
        validate_test_data_plan(plan, _load(POLICY))


def test_n27_rejects_detail_case_when_only_metric_is_created() -> None:
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([_semantic_case(["聚合指标"])], catalog)
    plan = compile_resource_plan(intent, catalog, environment="112", namespace="qa-detail-gap-001")

    assert plan["case_plans"][0]["required_scene"] == "chart_detail"
    with pytest.raises(Exception, match="chart_detail scene closure is incomplete"):
        validate_test_data_plan(plan, _load(POLICY))


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
            "compiled_cases": [_metric_lifecycle_case(["聚合指标"])],
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

def _ordinary_metric_case() -> dict:
    return {
        "id": "CASE-AUTO-DATA-002",
        "title": "创建普通指标后回查返回指标名称",
        "test_level": "functional",
        "preconditions": ["存在可用数值字段"],
        "test_data": {"metric_name": "普通指标"},
        "steps": [{"action": "创建普通指标"}],
        "expected": [{"description": "普通指标创建成功"}],
    }


def test_infer_data_intent_resolves_ordinary_metric_without_declaration() -> None:
    case = _ordinary_metric_case()
    intents = infer_resource_intents(case)
    assert intents == [
        {
            "resource_type": "ordinary_metric",
            "data_intent": "metric.ordinary.create",
            "dataset": "ordinary_metric",
            "terms": ["普通指标"],
        }
    ]
    assert infer_data_intent(case) == "metric.ordinary.create"
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([case], catalog)
    assert intent["unresolved_requirements"] == []
    assert intent["case_intents"][0]["recipe_id"] == "ordinary-metric-create"


def test_inferred_intent_stays_unresolved_for_ambiguous_case() -> None:
    ambiguous = {
        "id": "CASE-AUTO-DATA-003",
        "title": "报表与统计图同时出现的多资源场景",
        "test_level": "functional",
        "test_data": {"metric_name": "多资源"},
        "steps": [{"action": "打开报表和统计图"}],
        "expected": [{"description": "展示报表与统计图"}],
    }
    assert len(infer_resource_intents(ambiguous)) > 1
    assert infer_data_intent(ambiguous) == ""
    intent = extract_test_data_intents([ambiguous], _load(CATALOG))
    assert intent["unresolved_requirements"] == [
        {
            "case_id": "CASE-AUTO-DATA-003",
            "reason_code": "data_capability_not_registered",
            "dataset": None,
            "route_to": "capability_adapter_backlog",
        }
    ]


def test_ordinary_metric_create_recipe_compiles_and_n27_validates() -> None:
    catalog = _load(CATALOG)
    intent = extract_test_data_intents([_ordinary_metric_case()], catalog)
    plan = compile_resource_plan(
        intent, catalog, environment="112", namespace="qa-autonomous-data-002"
    )
    validation = validate_test_data_plan(plan, _load(POLICY))
    assert validation["valid"] is True
    case_plan = plan["case_plans"][0]
    assert case_plan["resources"][0]["setup"]["request"]["api"] == (
        "fs_bi_stat.agg_rule.add_new_agg_rule"
    )
    assert case_plan["resources"][0]["cleanup"]["request"]["api"] == (
        "fs_bi_stat.agg_rule.delete_agg_rule"
    )
    assert plan["ready_for_execution"] is True


def test_declared_empty_resources_are_inferred_from_compiled_case_semantics() -> None:
    catalog = _load(CATALOG)
    case = _ordinary_metric_case()
    plan = compile_declared_a22_plan(
        {"case_plans": [{"case_id": case["id"], "resources": []}]},
        catalog,
        environment="112",
        namespace="qa-declared-inference",
        compiled_cases=[case],
    )
    assert plan["case_plans"][0]["recipe_refs"][0]["recipe_id"] == "ordinary-metric-create"
    assert plan["case_plans"][0]["resources"]


def test_unproven_relation_recipe_is_not_selected_by_semantics() -> None:
    case = {
        "id": "CASE-RELATION",
        "title": "多关联失败替换后原成功关系回归",
        "test_level": "functional",
        "test_data": {"datasets": [{"type": "多关联"}]},
        "steps": [{"action": "查看明细"}],
        "expected": [{"description": "关联关系正确"}],
    }
    intent = extract_test_data_intents([case], _load(CATALOG))
    assert intent["case_intents"][0]["resource_goals"] == []
    assert intent["unresolved_requirements"][0]["reason_code"] == "data_capability_not_registered"


def test_declared_unproven_relation_recipe_is_structurally_blocked() -> None:
    plan = compile_declared_a22_plan(
        {
            "case_plans": [{
                "case_id": "CASE-RELATION",
                "resources": [
                    {"resource_key": "multi_relation_metric_matrix"},
                    {"resource_key": "multi_relation_chart_set"},
                ],
            }]
        },
        _load(CATALOG),
        environment="112",
        namespace="qa-relation-blocked",
    )
    assert plan["ready_for_execution"] is False
    assert plan["case_plans"][0]["resources"] == []
    assert plan["unsupported_requirements"][0]["reason_code"] == "data_recipe_semantics_not_proven"
    assert validate_test_data_plan(plan, _load(POLICY))["valid"] is True


def test_historical_string_dataset_matrix_requires_live_discovery() -> None:
    case = {
        "id": "CASE-HISTORICAL",
        "title": "Historical compatibility",
        "test_level": "functional",
        "test_data": {"datasets": [
            "historical_chart_custom_dim_no_migration",
            "historical_chart_result_set_no_migration",
            "historical_success_detail_query",
            "hour_minute_non_target",
            "downstream_virtual_metric_non_target",
        ]},
        "steps": [{"action": "detail"}],
        "expected": [],
    }
    intent = extract_test_data_intents([case], _load(CATALOG))
    assert intent["case_intents"][0]["resource_goals"] == []
    assert intent["unresolved_requirements"][0]["reason_code"] == "data_capability_not_registered"
