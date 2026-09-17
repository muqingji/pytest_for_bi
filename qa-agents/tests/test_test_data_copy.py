"""A22 unresolved-data copy must tell the QA owner what to give the planner."""

from qa_agents.test_data_copy import (
    A22_OWNER_HEADING,
    A22_SYSTEM_HEADING,
    DEFAULT_UNRESOLVED_TITLE,
    GENERIC_UNRESOLVED_CONFIRM,
    GENERIC_UNRESOLVED_NEEDED,
    GENERIC_UNRESOLVED_PROBLEM,
    GENERIC_UNRESOLVED_RESOLUTION,
    GENERIC_UNRESOLVED_SCENE,
    UNRESOLVED_REASON_ZH,
    has_cjk,
    humanize_unresolved_requirement,
    is_disposition_comment,
    is_owner_review,
    render_a22_approval_sections,
    unresolved_requirement_id,
)

# The seven reason codes the 20260915-R001 A22 run put in front of the QA Owner.
RUN_20260915_CODES = (
    "stat_chart_integrity_probes_missing",
    "historical_pre_change_assets_missing",
    "pre_change_response_baselines_missing",
    "joined_table_policy_gap",
    "frozen_dynamic_relation_metadata_missing",
    "permission_test_fixtures_missing",
    "result_set_metric_type_fixtures_missing",
)

ENTRY_FIELDS = ("title", "scene", "problem", "needed", "provide", "data", "review", "confirm", "resolution")
BANNED_REVIEW_TERMS = (
    "fxops_query",
    "recipe",
    "existing_asset_discovery",
    "decision=reusable",
    "whatlist",
    "setup_operation",
    "minimum_rows",
    "resource_types",
    "joined_table",
    "integrity_probes",
    "stat_chart",
)


def _raw_plan_item(code: str) -> dict:
    return {
        "id": code,
        "affected_cases": ["A08-TC-EXAMPLE-BACKEND"],
        "required_resolution": (
            "Provide a verified recipe covering source, topology, dimension and aggregation."
        ),
    }


def test_every_mapped_reason_code_has_decision_copy() -> None:
    for code, entry in UNRESOLVED_REASON_ZH.items():
        assert set(entry) == set(ENTRY_FIELDS), code
        assert has_cjk(entry["title"]), code
        assert len(entry["title"]) <= 12, code
        assert entry["review"] in {"owner", "system"}, code
        for field in ENTRY_FIELDS:
            value = entry[field]
            if field in {"provide", "review"} and (not value or field == "review"):
                continue
            assert has_cjk(value), f"{code}.{field}"
            blob = value.lower()
            leaked = [term for term in BANNED_REVIEW_TERMS if term in blob]
            assert leaked == [], f"{code}.{field} leaked {leaked}"


def test_run_reason_codes_are_all_mapped() -> None:
    missing = [code for code in RUN_20260915_CODES if code not in UNRESOLVED_REASON_ZH]
    assert missing == []


def test_humanize_replaces_english_plan_fields_with_decision_copy() -> None:
    for index, code in enumerate(RUN_20260915_CODES):
        item = _raw_plan_item(code)
        humanized = humanize_unresolved_requirement(item, index)
        entry = UNRESOLVED_REASON_ZH[code]
        assert humanized["human_title"] == entry["title"]
        assert humanized["product_scene"] == entry["scene"]
        assert humanized["plain_summary"] == entry["problem"]
        assert humanized["data_to_build"] == entry["data"]
        assert humanized["review_kind"] == entry["review"]
        if entry["review"] == "system":
            assert humanized["needed_from_you"].startswith("不需要你审")
            assert "不用回评论" in humanized["confirm_action"]
        else:
            assert humanized["needed_from_you"] == entry["needed"]
            assert humanized["provide_from_you"] == entry["provide"]
            assert humanized["confirm_action"] == entry["confirm"]
        assert humanized["recommendation"] == entry["resolution"]
        assert humanized["requirement_id"] == f"UR-{index + 1:02d}"
        assert humanized["affected_case_ids"] == ["A08-TC-EXAMPLE-BACKEND"]
        assert humanized["id"] == code
        assert humanized["required_resolution"] == item["required_resolution"]


def test_known_reason_code_ignores_author_jargon() -> None:
    humanized = humanize_unresolved_requirement(
        {
            "requirement_id": "UR-03",
            "reason_code": "chart_create_op_unverified",
            "requirement": "stat_chart 创建接口及参数未验证，图表 setup_operation 需人工确认",
            "required_resolution": "Provide a verified chart creation recipe.",
        },
        2,
    )

    assert humanized["requirement_id"] == "UR-03"
    assert humanized["human_title"] == UNRESOLVED_REASON_ZH["chart_create_op_unverified"]["title"]
    assert "stat_chart" not in humanized["plain_summary"]
    assert "recipe" not in humanized["recommendation"]
    assert humanized["review_kind"] == "system"
    assert humanized["needed_from_you"].startswith("不需要你审")
    assert "隔离统计图" in humanized["data_to_build"]


def test_humanize_falls_back_to_chinese_for_unknown_reason_code() -> None:
    humanized = humanize_unresolved_requirement(
        {
            "id": "brand_new_data_gap",
            "affected_cases": ["A08-TC-EXAMPLE-BACKEND"],
            "required_resolution": "Provide the brand new thing.",
        },
        0,
    )

    assert humanized["human_title"] == DEFAULT_UNRESOLVED_TITLE
    assert humanized["product_scene"] == GENERIC_UNRESOLVED_SCENE
    assert humanized["plain_summary"].startswith(GENERIC_UNRESOLVED_PROBLEM)
    assert "brand_new_data_gap" in humanized["plain_summary"]
    assert humanized["needed_from_you"] == GENERIC_UNRESOLVED_NEEDED
    assert humanized["confirm_action"] == GENERIC_UNRESOLVED_CONFIRM
    assert humanized["recommendation"] == GENERIC_UNRESOLVED_RESOLUTION
    assert "Provide the brand new thing." not in humanized["plain_summary"]
    assert "Provide the brand new thing." not in humanized["needed_from_you"]


def test_disposition_comment_is_not_treated_as_confirm_action() -> None:
    assert is_disposition_comment("UR-01: confirmed/skip/return/need_evidence")
    humanized = humanize_unresolved_requirement(
        {
            "id": "brand_new_data_gap",
            "confirm_action": "UR-01: confirmed/skip/return/need_evidence",
        },
        0,
    )
    assert humanized["confirm_action"] == GENERIC_UNRESOLVED_CONFIRM


def test_unresolved_requirement_id_prefers_declared_ur_ids() -> None:
    assert unresolved_requirement_id({"requirement_id": "ur-02"}, 5) == "UR-02"
    assert unresolved_requirement_id({"reason_code": "joined_table_policy_gap"}, 4) == "UR-05"
    assert unresolved_requirement_id({}, 0) == "UR-01"
    assert unresolved_requirement_id({"id": "UR-01", "reason_code": "joined_table_policy_gap"}, 4) == "UR-01"
    assert unresolved_requirement_id({"id": "UR-DISC-01"}, 0) == "UR-DISC-01"

def test_case_title_becomes_product_scene() -> None:
    humanized = humanize_unresolved_requirement(
        {
            "reason_code": "stat_chart_integrity_probes_missing",
            "affected_cases": ["TC-NEW-CONTRACT-001"],
        },
        0,
        case_titles={"TC-NEW-CONTRACT-001": "合同到期提醒不支持查看明细"},
    )
    assert humanized["product_scene"] == "合同到期提醒不支持查看明细。"
    assert humanized["affected_case_titles"]["TC-NEW-CONTRACT-001"] == "合同到期提醒不支持查看明细"
    assert humanized["review_kind"] == "system"


def test_unknown_reason_code_is_owner_review() -> None:
    humanized = humanize_unresolved_requirement({"id": "brand_new_data_gap"}, 0)
    assert humanized["review_kind"] == "owner"
    assert is_owner_review(humanized) is True
    assert is_owner_review("brand_new_data_gap") is True


def test_render_sections_lock_owner_and_system_fields() -> None:
    markdown = "\n".join(
        render_a22_approval_sections(
            [
                {
                    "requirement_id": "UR-01",
                    "reason_code": "historical_pre_change_assets_missing",
                    "affected_cases": ["TC-BE-001"],
                },
                {
                    "requirement_id": "UR-02",
                    "reason_code": "stat_chart_integrity_probes_missing",
                    "affected_cases": ["TC-BE-002"],
                },
                {
                    "requirement_id": "UR-03",
                    "id": "never_seen_gap",
                    "affected_cases": ["TC-BE-003"],
                },
            ]
        )
    )
    owner = markdown.split(A22_SYSTEM_HEADING, 1)[0]
    system = markdown.split(A22_SYSTEM_HEADING, 1)[1]
    assert markdown.startswith(A22_OWNER_HEADING)
    assert A22_SYSTEM_HEADING in markdown
    assert owner.count("   - 请拍板：") == 2
    assert owner.count("   - 处置评论：") == 2
    assert "UR-01: confirmed/skip/return/need_evidence" in owner
    assert "UR-03: confirmed/skip/return/need_evidence" in owner
    assert "   - 请拍板：" not in system
    assert "   - 处置评论：" not in system
    assert "   - 要测什么：" in owner
    assert "   - 要造什么：" in owner
    assert "   - 要测什么：" in system
    assert "   - 要造什么：" in system
    assert "产品场景：" not in markdown
    assert "这轮不造新图" not in markdown
