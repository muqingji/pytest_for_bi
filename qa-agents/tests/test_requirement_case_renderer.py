import json
from pathlib import Path

import pytest

from qa_agents.errors import ContractError
from qa_agents.requirement_case_renderer import (
    normalize_ir_parent_case,
    render_case_ir,
    render_g02_review_items,
    render_review_card,
    render_requirement_case_bundle,
    validate_requirement_case,
    parse_requirement_cards,
)
from qa_agents.skill_registry import SkillRegistry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "policies/backend-skill-registry.json"

CARD = """### `TC-BE-001` 自定义维度三类位置的专用错误与双语提示 · backend / critical / P0

## 测试场景
自定义维度字段位于维度、数据范围、下钻三类位置时，通过保存资产的查看明细入口触发查看明细，均被拒绝进入明细视图。

## 变体
- dimension：自定义维度字段位于统计图维度位置
- data_range：自定义维度字段位于数据范围位置
- drill_field：自定义维度字段位于下钻字段位置

## 前置条件
- 已构造并保存含自定义维度字段的资产，配置回查中精确出现自定义维度 ID

## 测试步骤
1. 构造并保存 dimension 变体资产，配置回查确认自定义维度 ID 出现在维度位置
2. 依次通过各变体资产的查看明细入口实际触发查看明细，记录 detail_api 响应
3. 比对 detail_api.error 的 code、message.zh_CN、message.en 实际值

## 预期结果
- `EXP-BE-001-01`：三个变体均拒绝查看明细并返回错误码 s307011534。
   - deterministic · equals @ `detail_api.error.code` → `s307011534`
- `EXP-BE-001-02`：zh_CN 运行时消息精确为批准模板。
   - deterministic · equals @ `detail_api.error.message.zh_CN` → `维度或数据范围中使用了自定义维度字段，暂不支持查看明细`
- `EXP-BE-001-03`：en 运行时消息精确为批准模板。
   - deterministic · equals @ `detail_api.error.message.en` → `Custom dimension fields are used in the dimension or data range. Details view is not supported.`
"""

ZH_MESSAGE = "维度或数据范围中使用了自定义维度字段，暂不支持查看明细"
EN_MESSAGE = "Custom dimension fields are used in the dimension or data range. Details view is not supported."

IR_PARENT_CASE = {
    "id": "TC-BE-001",
    "title": "自定义维度三类位置的专用错误与双语提示",
    "layer": "backend",
    "risk": "critical",
    "priority": "P0",
    "source_refs": ["REQ-001", "RULE-I18N-CUSTOM-DIMENSION"],
    "preconditions": [
        "真实测试接口连接错误码平台联调环境，不以 G01 配置本身代替运行时 Oracle。",
        "自定义维度字段可分别配置在维度、数据范围和下钻字段。",
    ],
    "steps": [
        "在命名空间内创建基线统计图并确认查看明细请求成功。",
        "对变体 A、B、C 分别以 zh_CN 和 en 调用真实查看明细接口。",
        "核对三类位置沿用现有检测顺序，且未返回统一通用提示。",
    ],
    "expected": [
        {
            "id": "EXP-BE-001-01",
            "description": "三个变体均拒绝查看明细并返回错误码 s307011534。",
            "oracle": {
                "type": "deterministic",
                "matcher": "equals",
                "observation_point": "detail_api.error.code",
                "expected_value": "s307011534",
            },
        },
        {
            "id": "EXP-BE-001-02",
            "description": "zh_CN 运行时消息精确为批准模板。",
            "oracle": {
                "type": "deterministic",
                "matcher": "equals",
                "observation_point": "detail_api.error.message.zh_CN",
                "expected_value": ZH_MESSAGE,
            },
        },
    ],
}


def test_normalize_ir_parent_case_preserves_steps_and_synthesizes_scenario() -> None:
    normalized = normalize_ir_parent_case(IR_PARENT_CASE)
    assert normalized["requirement"]["id"] == "TC-BE-001"
    assert normalized["steps"] == IR_PARENT_CASE["steps"]
    assert normalized["preconditions"] == IR_PARENT_CASE["preconditions"]
    assert normalized["scenario"].startswith("自定义维度三类位置的专用错误与双语提示：")
    assert normalized["expected"][1]["oracle"]["expected_value"] == ZH_MESSAGE


def test_g02_review_items_carry_scenario_steps_preconditions() -> None:
    (case,) = parse_requirement_cards(CARD)
    items = render_g02_review_items([case])
    assert items[0]["case_id"] == "TC-BE-001"
    assert items[0]["scenario"].startswith("自定义维度字段位于维度、数据范围、下钻三类位置时")
    assert items[0]["steps"]
    assert items[0]["preconditions"]


def test_render_review_card_accepts_review_item_shape() -> None:
    normalized = normalize_ir_parent_case(IR_PARENT_CASE)
    item = render_g02_review_items([normalized])[0]
    card = render_review_card(item, index=1)
    assert "### 1. `TC-BE-001` 自定义维度三类位置的专用错误与双语提示 · backend / critical / P0" in card
    assert "**测试场景**" in card
    assert "**前置条件**" in card
    assert "**测试步骤**" in card
    assert "**预期结果**" in card
    assert "1. 在命名空间内创建基线统计图并确认查看明细请求成功。" in card
    assert f"「{ZH_MESSAGE}」" in card


def test_render_review_card_falls_back_for_minimal_review_item() -> None:
    item = {
        "case_id": "TC-X-001",
        "title": "最小审核项",
        "layer": "backend",
        "risk": "high",
        "priority": "P1",
        "source_refs": ["REQ-1"],
        "expected": [
            {
                "id": "EXP-01",
                "description": "拒绝并返回专用错误码。",
                "oracle_type": "deterministic",
                "matcher": "equals",
                "observation_point": "api.error.code",
                "expected_value": "E001",
            }
        ],
    }
    card = render_review_card(item, index=2)
    assert "### 2. `TC-X-001` 最小审核项 · backend / high / P1" in card
    assert "**测试场景**" in card and "**测试步骤**" in card and "**预期结果**" in card
    assert "拒绝并返回专用错误码（错误码 `E001`）" in card
    assert "deterministic · equals" not in card




def test_parse_tc_be_001_normalizes_expected_verbatim() -> None:
    (case,) = parse_requirement_cards(CARD)
    assert case["schema_version"] == "requirement-case/1.0"
    assert case["requirement"] == {
        "id": "TC-BE-001",
        "title": "自定义维度三类位置的专用错误与双语提示",
        "layer": "backend",
        "risk": "critical",
        "priority": "P0",
    }
    assert [v["id"] for v in case["variants"]] == ["dimension", "data_range", "drill_field"]
    assert len(case["steps"]) == 3
    assert len(case["expected"]) == 3
    assert case["expected"][0]["oracle"] == {
        "type": "deterministic",
        "matcher": "equals",
        "observation_point": "detail_api.error.code",
        "expected_value": "s307011534",
    }
    assert case["expected"][1]["oracle"]["expected_value"] == ZH_MESSAGE
    assert case["expected"][2]["oracle"]["expected_value"] == EN_MESSAGE


def test_render_review_card_has_scenario_steps_expected() -> None:
    (case,) = parse_requirement_cards(CARD)
    card = render_review_card(case)
    assert "**测试场景**" in card
    assert "**测试步骤**" in card
    assert "**预期结果**" in card
    assert "### `TC-BE-001` 自定义维度三类位置的专用错误与双语提示 · backend / critical / P0" in card
    assert "EXP-BE-001-01" in card and "EXP-BE-001-02" in card and "EXP-BE-001-03" in card
    assert "deterministic · equals" not in card
    assert "detail_api.error.code" not in card
    assert f"「{ZH_MESSAGE}」" in card
    assert f"：`{EN_MESSAGE}`" in card


def test_g02_review_items_match_g02_review_shape() -> None:
    (case,) = parse_requirement_cards(CARD)
    items = render_g02_review_items([case])
    assert len(items) == 1
    item = items[0]
    assert item["case_id"] == "TC-BE-001"
    assert item["layer"] == "backend" and item["risk"] == "critical" and item["priority"] == "P0"
    expected = item["expected"]
    assert [exp["id"] for exp in expected] == ["EXP-BE-001-01", "EXP-BE-001-02", "EXP-BE-001-03"]
    for exp in expected:
        assert set(exp) == {
            "id", "description", "oracle_type", "matcher", "observation_point", "expected_value"
        }
    assert expected[0]["oracle_type"] == "deterministic"
    assert expected[2]["expected_value"] == EN_MESSAGE


def test_case_ir_has_all_required_fields() -> None:
    (case,) = parse_requirement_cards(CARD)
    ir = render_case_ir(case)
    required = {
        "id", "title", "intent_ids", "layer", "risk", "priority", "source_refs",
        "preconditions", "test_data", "steps", "expected", "cleanup",
        "execution_policy", "automation_candidate",
    }
    assert required <= set(ir)
    assert ir["id"] == "TC-BE-001"
    assert ir["test_data"]["variants"][0]["id"] == "dimension"
    assert ir["expected"][1]["oracle"]["expected_value"] == ZH_MESSAGE


def test_fallback_synthesizes_scenario_and_steps() -> None:
    minimal = (
        "### `TC-X-001` 最小需求 · backend / high / P1\n\n"
        "## 预期结果\n"
        "- `EXP-01`：拒绝并返回专用错误码。\n"
        "   - deterministic · equals @ `api.error.code` → `E001`\n"
    )
    (case,) = parse_requirement_cards(minimal)
    assert case["scenario"].startswith("最小需求：")
    assert case["steps"]
    assert case["expected"][0]["oracle"]["expected_value"] == "E001"


def test_render_requirement_case_bundle_writes_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "requirement.md"
    source.write_text(CARD, encoding="utf-8")
    output = tmp_path / "out"
    outcome = render_requirement_case_bundle(source, output)
    assert outcome["requirement_count"] == 1
    assert outcome["requirement_ids"] == ["TC-BE-001"]
    assert (output / "requirement-case.json").is_file()
    assert (output / "case-card.md").is_file()
    assert (output / "g02-review-items.json").is_file()
    assert (output / "case-ir.json").is_file()
    case = json.loads((output / "requirement-case.json").read_text(encoding="utf-8"))
    assert case["requirement"]["id"] == "TC-BE-001"


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ("### `TC-1` 缺属性标题 · backend / critical\n", "header attributes"),
        ("### `TC-1` 风险非法 · backend / 严重 / P0\n", "risk must be one of"),
        ("### `TC-1` 优先级非法 · backend / high / P5\n", "priority must be one of"),
        ("### `TC-1` 未知区块 · backend / high / P1\n\n## 备注\n- x\n", "Unknown requirement card section"),
    ],
)
def test_rejects_malformed_cards(bad: str, message: str) -> None:
    with pytest.raises(ContractError, match=message):
        parse_requirement_cards(bad)


def test_rejects_expectation_without_oracle() -> None:
    card = "### `TC-1` 无 oracle · backend / high / P1\n\n## 预期结果\n- `EXP-01`：没有 oracle 行。\n"
    with pytest.raises(ContractError, match="must declare an oracle line"):
        parse_requirement_cards(card)


def test_rejects_oracle_without_expectation() -> None:
    card = (
        "### `TC-1` oracle 前无 EXP · backend / high / P1\n\n"
        "## 预期结果\n"
        "   - deterministic · equals @ `api.error.code` → `E001`\n"
    )
    with pytest.raises(ContractError, match="without a preceding expectation"):
        parse_requirement_cards(card)


def test_rejects_duplicate_expectation_and_duplicate_card() -> None:
    duplicate_exp = (
        "### `TC-1` 重复 EXP · backend / high / P1\n\n## 预期结果\n"
        "- `EXP-01`：a。\n   - deterministic · equals @ `p` → `1`\n"
        "- `EXP-01`：b。\n   - deterministic · equals @ `p` → `2`\n"
    )
    with pytest.raises(ContractError, match="Duplicate expectation id"):
        parse_requirement_cards(duplicate_exp)
    duplicate_card = (
        "### `TC-1` 重复卡 · backend / high / P1\n\n## 预期结果\n"
        "- `EXP-01`：a。\n   - deterministic · equals @ `p` → `1`\n"
        "### `TC-1` 重复卡 · backend / high / P1\n\n## 预期结果\n"
        "- `EXP-01`：b。\n   - deterministic · equals @ `p` → `2`\n"
    )
    with pytest.raises(ContractError, match="Duplicate requirement card id"):
        parse_requirement_cards(duplicate_card)


def test_validate_rejects_incomplete_normalized_case() -> None:
    with pytest.raises(ContractError, match="requires scenario"):
        validate_requirement_case({"schema_version": "requirement-case/1.0", "requirement": {
            "id": "TC-1", "title": "t", "layer": "backend", "risk": "high", "priority": "P1"
        }})


def test_skill_is_published_and_authorized_for_a08_a09() -> None:
    registry = SkillRegistry.from_file(REGISTRY)
    skill = registry.skills["requirement-case-render"]
    assert skill["version"] == "1.0.0"
    assert set(skill["agents"]) == {"A08", "A09"}
    assert skill["side_effect"] == "planning_only"
    assert (ROOT / "skills/requirement-case-render/SKILL.md").is_file()
    assert registry.refs(["requirement-case-render"], "A08") == ["requirement-case-render/1.0.0"]
    assert registry.refs(["requirement-case-render"], "A09") == ["requirement-case-render/1.0.0"]


def test_human_expected_value_spells_out_messages_and_codes() -> None:
    item = render_g02_review_items([normalize_ir_parent_case(IR_PARENT_CASE)])[0]
    card = render_review_card(item)
    assert f"zh_CN 运行时消息精确为批准模板：「{ZH_MESSAGE}」" in card
    assert "错误码 `s307011534`）" not in card

    one_of = {
        "case_id": "TC-X", "title": "t", "layer": "backend", "risk": "high",
        "priority": "P1", "source_refs": ["r"],
        "scenario": "s", "steps": ["x"], "preconditions": [],
        "expected": [
            {
                "id": "EXP-01",
                "description": "按实际命中原因返回合法专用错误。",
                "oracle_type": "deterministic", "matcher": "one_of",
                "observation_point": "detail_api.error.code",
                "expected_value": "['s307011535', 's307011537']",
            },
            {
                "id": "EXP-02",
                "description": "无权限响应不包含敏感指标名。",
                "oracle_type": "deterministic", "matcher": "not_contains",
                "observation_point": "detail_api.permission_error_payload",
                "expected_value": "机密收入",
            },
            {
                "id": "EXP-03",
                "description": "元数据缺失时不替换为专用错误；人工确认完整业务响应。",
                "oracle_type": "human_review", "matcher": "manual_confirmation",
                "observation_point": "detail_api.controls.CTRL-02.full_response",
                "expected_value": "preserve_actual_business_response",
            },
        ],
    }
    card = render_review_card(one_of)
    assert "（允许错误码：s307011535、s307011537）" in card
    assert "（不得包含：`机密收入`）" in card
    assert "manual_confirmation" not in card
    assert "preserve_actual_business_response" not in card
