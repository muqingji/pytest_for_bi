from qa_agents.review_copy import (
    build_g02_decision_items,
    g02_approval_items,
    humanize_review_item,
)


def test_humanize_keeps_chinese_author_fields() -> None:
    item = {
        "case_id": "TC-BE-001",
        "title": "自定义维度三类位置的专用错误与双语提示",
        "layer": "backend",
        "scenario": "自定义维度出现在维度、数据范围、下钻时均拒绝查看明细。",
        "expected": [{"id": "E-1"}],
    }
    copy = humanize_review_item(item)
    assert copy["human_title"] == "自定义维度三类位置的专用错误与双语提示"
    assert copy["plain_summary"].startswith("自定义维度出现在维度、数据范围、下钻时均拒绝查看明细")
    assert "1 条预期" in copy["plain_summary"]


def test_humanize_rewrites_english_ir_into_chinese_scene() -> None:
    item = {
        "case_id": "PC-BE-001",
        "title": "Backend custom dimension three-path dedicated error s307011534",
        "layer": "backend",
        "priority": "P0",
        "risk": "critical",
        "scenario": "Custom dimension in dimension returns dedicated error code s307011534",
        "source_refs": ["REQ-001", "RULE-CUSTOM-DIMENSION", "RULE-I18N-CUSTOM-DIMENSION"],
        "expected": [
            {"id": "E-1", "expected_value": "s307011534"},
            {"id": "E-2", "expected_value": "s307011534"},
        ],
        "steps": [
            "Prepare fixtures with custom dimension only in dimension, data_range, and drill_field"
        ],
    }
    copy = humanize_review_item(item)
    assert copy["human_title"] == "自定义维度拒绝明细"
    assert "服务端校验「自定义维度不支持查看明细」" in copy["plain_summary"]
    assert "维度、数据范围、下钻" in copy["plain_summary"]
    assert "s307011534" in copy["plain_summary"]
    assert "Custom dimension" not in copy["human_title"]
    assert "Custom dimension" not in copy["plain_summary"]


def test_humanize_distinguishes_permission_and_e2e_cases() -> None:
    permission = humanize_review_item(
        {
            "case_id": "PC-BE-006",
            "title": "Backend permission errors preserve existing behavior",
            "layer": "backend",
            "source_refs": ["RULE-PERMISSION-PRIORITY"],
            "expected": [{"id": "E-1"}, {"id": "E-2"}, {"id": "E-3"}],
        }
    )
    assert permission["human_title"] == "权限错误优先"
    assert "权限错误优先于明细提示" in permission["plain_summary"]

    mobile = humanize_review_item(
        {
            "case_id": "PC-E2E-002",
            "title": "E2E mobile and web detail consistency across chart and joined-table",
            "layer": "e2e",
            "source_refs": ["RULE-ENTRY-CONSISTENCY"],
            "expected": [{"id": "E-1"}],
        }
    )
    assert mobile["human_title"] == "移动端与Web一致"
    assert "移动端与 Web 明细提示一致" in mobile["plain_summary"]


def test_g02_decision_items_only_include_unfrozen_product_calls() -> None:
    items = build_g02_decision_items(
        [
            {
                "case_id": "PC-BE-001",
                "title": "Backend custom dimension dedicated error",
                "layer": "backend",
                "source_refs": ["RULE-CUSTOM-DIMENSION"],
                "expected": [
                    {"id": "E-1", "oracle": {"type": "deterministic", "matcher": "equals"}}
                ],
            },
            {
                "case_id": "PC-BE-006",
                "title": "Backend permission errors preserve existing behavior",
                "layer": "backend",
                "source_refs": ["RULE-PERMISSION-PRIORITY"],
                "expected": [
                    {
                        "id": "E-BE-006-02",
                        "description": "permission failure code versus baseline",
                        "oracle": {"type": "human_review", "matcher": "manual_confirmation"},
                    }
                ],
            },
            {
                "case_id": "PC-BE-007",
                "title": "Backend historical compatibility",
                "layer": "backend",
                "source_refs": ["RULE-HISTORICAL-COMPATIBILITY"],
                "expected": [
                    {
                        "id": "E-BE-007-09",
                        "description": "successful detail sql_shape equals frozen baseline",
                        "oracle": {"type": "human_review", "matcher": "manual_confirmation"},
                    }
                ],
            },
        ],
        skipped_scenarios=[
            {
                "id": "SKIP-EMPTY-METRIC-NAME",
                "reason": "skip_not_applicable",
                "details": "Empty metric display name must not generate specialized copy.",
                "rule_ref": "RULE-SINGLE-METRIC",
            }
        ],
    )
    assert [item["id"] for item in items] == [
        "PC-BE-006:human_review",
        "PC-BE-007:human_review",
        "SKIP-EMPTY-METRIC-NAME",
    ]
    assert items[0]["human_title"] == "没权限时不要改提示"
    assert "原来的权限失败" in items[0]["product_scene"]
    assert "没有写死" in items[0]["plain_summary"]
    assert items[1]["human_title"] == "老图能看的明细不能丢"
    assert items[2]["human_title"] == "空指标名这轮不测"
    assert all("请确认该用例的场景、步骤和预期结果可直接执行" not in item["confirm_action"] for item in items)


def test_g02_approval_items_never_empty_when_all_cases_are_frozen() -> None:
    items = g02_approval_items(
        {
            "review_summary": {"parent_case_count": 11},
            "review_items": [
                {
                    "case_id": "PC-BE-001",
                    "title": "Backend custom dimension dedicated error",
                    "expected": [{"id": "E-1", "oracle": {"type": "deterministic"}}],
                }
            ],
        }
    )
    assert len(items) == 1
    assert items[0]["id"] == "g02-delivery-confirmation"
    assert items[0]["human_title"] == "没有未冻结的产品口径"
    assert "11 条父用例" in items[0]["plain_summary"]
