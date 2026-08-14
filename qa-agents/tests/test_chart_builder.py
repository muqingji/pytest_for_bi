from __future__ import annotations

import pytest

from qa_agents.chart_builder import canonical_hash, compile_chart_clone_resource, compile_chart_resource
from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.test_data import validate_test_data_plan
import json
from pathlib import Path


def _compile(**overrides):
    values = dict(requirement_name="统计图查看明细限制原因提示优化", view_name="客户数量最小统计图",
                  namespace="qa-chart-test", category_id="BI_live_folder",
                  folder_query_operation="bi.portal.query_categories",
                  folder_response_hash=canonical_hash({"categoryID": "BI_live_folder"}),
                  schema_id="BI_live_schema",
                  axis_data={"chartType": "card", "dimensionFields": [],
                             "measureFieldList": [{"fieldId": "BI_live_measure", "fieldType": "Number",
                                                   "yAxisIndex": 1}]},
                  layout={"showTitle": 1},
                  identity={"timeZone": "Asia/Shanghai", "templateID": "BI_live_template", "permType": 2,
                            "userOwnerList": [{"id": "1002", "type": "user"}]})
    values.update(overrides)
    return compile_chart_resource(**values)


def test_compile_chart_binds_live_folder_and_readback():
    value = _compile()
    assert value["asset_folder_name"] == "统计图查看明细限制原因提示优化"
    assert value["setup"]["request"]["json"]["statViewBaseInfo"]["categoryID"] == "BI_live_folder"
    assert value["readiness"][0]["request"]["api"] == "fs_bi_stat.stat_edit.get_chart_config"


@pytest.mark.parametrize("change", [
    {"category_id": ""}, {"folder_query_operation": ""}, {"folder_response_hash": "sha256:bad"},
    {"axis_data": {"chartType": "card", "measureFieldList": []}},
])
def test_compile_chart_rejects_unproven_dynamic_inputs(change):
    with pytest.raises(ContractError):
        _compile(**change)


def test_n27_rechecks_chart_folder_provenance():
    resource = _compile()
    plan = {"schema_version": "test-data-plan/1.0", "environment": "112",
            "namespace": "qa-chart-test", "case_plans": [{
                "case_id": "CHART", "requirement_name": "统计图查看明细限制原因提示优化",
                "resources": [resource]}]}
    root = Path(__file__).resolve().parents[1]
    policy = json.loads((root / "policies/test-data-policy.json").read_text())
    assert validate_test_data_plan(plan, policy)["write_authorized"] is True
    resource["folder_binding"]["category_id"] = "BI_tampered"
    with pytest.raises(SecurityPolicyError, match="category"):
        validate_test_data_plan(plan, policy)


def test_compile_chart_clone_uses_verified_crm_lifecycle():
    value = compile_chart_clone_resource(
        requirement_name="统计图查看明细限制原因提示优化", view_name="客户指标验证统计图",
        namespace="qa-chart-clone", category_id="BI_live_folder",
        folder_query_operation="bi.portal.query_categories",
        folder_response_hash=canonical_hash({"categoryID": "BI_live_folder"}),
        source_view_id="BI_live_source",
        source_config_hash=canonical_hash({"viewId": "BI_live_source", "measureCount": 1}),
    )
    assert value["setup"]["request"]["api"] == "fs_bi_crm.stat_create.copy_stat_view"
    assert [step["request"]["api"] for step in value["post_setup"]] == [
        "fs_bi_crm.rpt_view_display.rename_rpt_view",
        "fs_bi_crm.stat_edit.get_stat_view",
        "fs_bi_crm.rpt_view_display.move_rpt_view",
    ]
    assert value["post_setup"][2]["condition"]["operator"] == "not_equals"
    assert value["post_setup"][1]["extract"] == {
        "chart_origin_category_id": "Value.categoryID"
    }
    assert len(value["readiness"]) == 2


def test_compile_chart_clone_rejects_missing_live_hash():
    with pytest.raises(ContractError):
        compile_chart_clone_resource(
            requirement_name="需求", view_name="客户指标验证统计图", namespace="qa-chart-clone",
            category_id="BI_live_folder", folder_query_operation="query",
            folder_response_hash=canonical_hash({"folder": 1}), source_view_id="BI_source",
            source_config_hash="",
        )
