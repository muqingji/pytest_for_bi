from pathlib import Path

from qa_agents.card_copy import constructed_assets_markdown, node_record_description
from qa_agents.constructed_assets import (
    merge_constructed_inventory,
    render_constructed_assets_markdown,
    write_constructed_asset_inventory,
)
from qa_agents.workflow_center import _render_stage_card_markdown, _stage_cards


def _assets() -> list[dict[str, str]]:
    return [
        {
            "resource_type": "stat_chart",
            "display_name": "自定义维度查看明细验证统计图",
            "resource_id": "BI_chart_46",
            "folder_name": "示例",
            "resource_key": "variant_chart_set",
        },
        {
            "resource_type": "aggregate_metric",
            "display_name": "销售订单退款金额聚合指标",
            "resource_id": "BI_metric_1",
        },
        {
            "resource_type": "custom_dimension",
            "display_name": "客户等级枚举分组自定义维度",
            "resource_id": "BI_dim_1",
            "subject": "客户",
        },
        {
            "resource_type": "joined_table",
            "display_name": "客户销售订单查看明细验证拼表",
            "resource_id": "BI_join_1",
        },
    ]


def test_renderer_uses_fixed_category_order_and_empty_placeholder() -> None:
    markdown = render_constructed_assets_markdown(_assets())
    assert markdown.startswith("## 已构造测试数据")
    order = [line for line in markdown.splitlines() if line.startswith("### ")]
    assert order == [
        "### 统计图",
        "### 报表",
        "### 交叉表",
        "### 驾驶舱",
        "### 指标",
        "### 自定义维度",
        "### 拼表",
    ]
    assert "- `自定义维度查看明细验证统计图`（`BI_chart_46`） · 目录：示例" in markdown
    assert "### 报表\n- 无" in markdown
    assert "### 交叉表\n- 无" in markdown
    assert "### 驾驶舱\n- 无" in markdown
    assert "variant_chart_set" not in markdown
    assert render_constructed_assets_markdown([]) == ""
    assert constructed_assets_markdown(None) == ""


def test_renderer_uses_scene_name_instead_of_internal_key() -> None:
    markdown = render_constructed_assets_markdown(
        [
            {
                "resource_type": "stat_chart",
                "resource_key": "variant_chart_set",
                "case_id": "PC-BE-001-BACKEND",
                "title": "Backend custom dimension three-path dedicated error s307011534",
            }
        ]
    )
    assert "`自定义维度查看明细验证统计图`" in markdown
    assert "- `自定义维度`" not in markdown
    assert "未记录名称" not in markdown
    assert "variant_chart_set" not in markdown
    assert "PC-BE-001-BACKEND" not in markdown


def test_c5_and_c6_stage_cards_include_constructed_assets_after_output() -> None:
    node = {
        "node_id": "N08",
        "state": "completed",
        "label": "受控自动化执行",
        "artifact_id": "n08-automation-execution",
        "artifact_hash": "sha256:abc",
    }
    c6 = _render_stage_card_markdown(
        "C6", "测试执行", [node], constructed_assets=_assets()
    )
    assert "## 已构造测试数据" in c6
    assert c6.index("## 产出") < c6.index("## 已构造测试数据") < c6.index("## 异常处理")
    assert "自定义维度查看明细验证统计图" in c6
    c3 = _render_stage_card_markdown(
        "C3", "测试设计与审核", [node], constructed_assets=_assets()
    )
    assert "## 已构造测试数据" not in c3
    cards = _stage_cards(
        {
            "nodes": [
                {
                    "node_id": "A22",
                    "state": "completed",
                    "stage_card_id": "C5",
                    "stage_card_title": "自动化与测试数据准备",
                }
            ]
        },
        constructed_assets=_assets(),
    )
    assert "## 已构造测试数据" in cards[0]["description"]


def test_n08_record_card_appends_constructed_assets_before_approval() -> None:
    plain = node_record_description(
        "N08",
        "受控自动化执行",
        artifact_name="n08-automation-execution.json",
        constructed_assets=_assets(),
    )
    assert "## 已构造测试数据" in plain
    assert plain.index("## 产出") < plain.index("## 已构造测试数据")
    with_block = node_record_description(
        "N08",
        "受控自动化执行",
        artifact_name="n08-automation-execution.json",
        constructed_assets=_assets(),
        approval_block=["- 置 **done**：批准重试。"],
    )
    assert with_block.index("## 已构造测试数据") < with_block.index("## 你需要处理")


def test_merge_prefers_evidence_ids_but_scene_names(tmp_path: Path) -> None:
    registered = [
        {
            "resource_type": "stat_chart",
            "key": "variant_chart_set",
            "case_id": "PC-BE-001-BACKEND",
            "status": "constructed",
        }
    ]
    evidence = [
        {
            "resource_type": "stat_chart",
            "display_name": "销售订单统计_副本46",
            "resource_id": "BI_chart_46",
            "case_id": "PC-BE-001-BACKEND",
        }
    ]
    merged = merge_constructed_inventory(
        registered,
        evidence,
        titles={"PC-BE-001-BACKEND": "Backend custom dimension three-path dedicated error s307011534"},
    )
    assert merged[0]["display_name"] == "自定义维度查看明细验证统计图"
    assert merged[0]["resource_id"] == "BI_chart_46"
    assert merged[0]["resource_key"] == "variant_chart_set"
    markdown = render_constructed_assets_markdown(merged)
    assert "自定义维度查看明细验证统计图" in markdown
    assert "销售订单统计_副本46" not in markdown
    assert "- `自定义维度`" not in markdown
    path = write_constructed_asset_inventory(tmp_path / "constructed-test-assets.json", merged)
    assert path.exists()
