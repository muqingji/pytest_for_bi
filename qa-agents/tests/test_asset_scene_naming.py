from qa_agents.asset_scene_naming import (
    catalog_display_name,
    is_usable_visible_name,
    scene_display_name,
)


def test_scene_display_name_uses_catalog_semantic_name() -> None:
    assert scene_display_name(
        resource_type="stat_chart",
        resource_key="variant_chart_set",
        case_id="PC-BE-001-BACKEND",
        title="Backend custom dimension three-path dedicated error s307011534",
    ) == "自定义维度查看明细验证统计图"
    assert scene_display_name(
        resource_type="aggregate_metric",
        resource_key="aggregate_metric_resolution_set",
        title="Backend result-set metric filter dedicated error s307011535",
    ) == "结果集筛选聚合指标"
    assert scene_display_name(
        resource_type="calculated_metric",
        resource_key="calculated_metric_dynamic_name_pair",
        title="Backend result-set metric filter",
    ) == "结果集筛选计算指标"
    assert scene_display_name(
        resource_type="stat_chart",
        resource_key="multi_relation_chart_set",
        title="Backend multi-relation replace-on-failure",
    ) == "多关联查看明细验证统计图"
    assert scene_display_name(
        resource_type="stat_chart",
        resource_key="dynamic_relation_chart_set",
        title="Backend dynamic relation what/whatlist",
    ) == "动态关联查看明细验证统计图"
    assert scene_display_name(
        resource_type="stat_chart",
        resource_key="combo_chart_set",
        title="Backend multiple matched reasons",
    ) == "组合原因查看明细验证统计图"
    assert scene_display_name(
        resource_type="stat_chart",
        resource_key="restricted_chart",
        title="Backend permission errors preserve existing behavior",
    ) == "权限查看明细验证统计图"
    assert catalog_display_name("custom_dimension_fixture") == "客户等级枚举分组自定义维度"
    assert catalog_display_name("baseline_metric") == "基线聚合指标"


def test_scene_display_name_rejects_copy_suffix_and_short_labels() -> None:
    assert is_usable_visible_name("销售订单统计_副本46") is False
    assert is_usable_visible_name("qa-pilot-销售金额") is False
    assert is_usable_visible_name("自定义维度") is False
    assert is_usable_visible_name("销售金额结果集筛选聚合指标") is True
    assert is_usable_visible_name("自定义维度查看明细验证统计图") is True
    assert scene_display_name(
        resource_type="stat_chart",
        resource_key="variant_chart_set",
        existing_name="销售订单统计_副本46",
    ) == "自定义维度查看明细验证统计图"
    assert scene_display_name(
        resource_type="stat_chart",
        resource_key="variant_chart_set",
        existing_name="自定义维度",
    ) == "自定义维度查看明细验证统计图"
    assert scene_display_name(
        resource_type="stat_chart",
        title="Backend custom dimension three-path",
        existing_name="销售订单统计_副本46",
    ) == "自定义维度"
    assert scene_display_name(
        resource_type="aggregate_metric",
        existing_name="销售金额结果集筛选聚合指标",
    ) == "销售金额结果集筛选聚合指标"
