from qa_agents.card_copy import (
    DEFAULT_NODE_COPY,
    NODE_CARD_COPY,
    human_correction_description,
    human_correction_title,
    node_issue_description,
    node_issue_title,
    g02_review_description,
    g02_review_title,
    scope_review_title,
    stage_card_sections,
)

DEDICATED_NODES = ("A02", "A03", "A05", "A06", "A08", "A09", "A11", "A14", "A15", "A22")

NODE_ARTIFACTS = {
    "A02": "a02-requirement-analysis",
    "A03": "a03-technical-testability-analysis",
    "A05": "a05-backend-change-analysis",
    "A06": "a06-alignment-result",
    "A08": "a08-test-design-ir",
    "A09": "a09-oracle-coverage-review",
    "A11": "a11-split-coverage-review",
    "A14": "a14-backend-automation-generation",
    "A15": "a15-contract-automation-generation",
    "A22": "a22-test-data-plan",
}


def test_stage_card_sections_follow_five_section_template() -> None:
    copy = stage_card_sections("C3")
    for field in ("goal", "background", "scope_includes", "scope_excludes", "inputs", "acceptance"):
        assert field in copy and copy[field]


def test_node_issue_title_and_description_are_readable() -> None:
    assert node_issue_title("run-1", "A08", "测试设计") == "[run-1] A08 测试设计"
    description = node_issue_description("A08", "测试设计修正", input_name="a08-input.json")
    assert "## 目标" in description and "## 背景" in description
    assert "## 范围" in description and "## 输入材料" in description
    assert "## 验收" in description
    assert "本卡为修正轮" in description
    assert "（附件：`a08-input.json`）" in description


def test_node_issue_description_includes_approval_details() -> None:
    approval_issues = [
        {
            "id": "A09-ISSUE-007",
            "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE",
            "human_title": "预期结果无法解析",
            "severity": "blocking",
            "plain_summary": "EXP-E2E-001-01 的 expected_value 指向不存在的字段路径。",
            "recommendation": "改为可直接解析的结构化四行期望矩阵。",
            "case_id": "TC-E2E-001",
            "expected_id": "EXP-E2E-001-01",
            "source_refs": ["REQ-006", "RULE-ENTRY-CONSISTENCY"],
        }
    ]
    description = node_issue_description(
        "A09",
        "Oracle 与覆盖审查修正",
        input_name="a09-input.json",
        approval_issues=approval_issues,
    )
    assert "## 你需要处理" in description
    assert "待审批：`1` 项" in description
    assert "1. **预期结果无法解析**（`A09-ISSUE-007` · blocking）" in description
    assert "建议修正：改为可直接解析的结构化四行期望矩阵。" in description
    assert "涉及用例：`TC-E2E-001`" in description
    assert "期望项：`EXP-E2E-001-01`" in description
    assert "来源：`REQ-006`、`RULE-ENTRY-CONSISTENCY`" in description
    assert "置 **done**" in description
    assert "置 **cancelled**" in description


def test_all_dedicated_nodes_have_own_copy_not_default() -> None:
    for node_id in DEDICATED_NODES:
        copy = NODE_CARD_COPY[node_id]
        assert copy["goal"] != DEFAULT_NODE_COPY["goal"]
        assert copy["background"] != DEFAULT_NODE_COPY["background"]
        for field in ("scope_includes", "scope_excludes", "inputs", "acceptance"):
            assert copy[field], f"{node_id} {field} 为空"
        assert copy["inputs"][0] == "输入参数包（附件）"


def test_every_dedicated_node_description_is_five_section() -> None:
    for node_id in DEDICATED_NODES:
        description = node_issue_description(node_id, "测试设计", input_name="input.json")
        for heading in ("## 目标", "## 背景", "## 范围", "## 输入材料", "## 验收"):
            assert heading in description, f"{node_id} 缺少 {heading}"
        assert "（附件：`input.json`）" in description


def test_node_acceptance_binds_expected_artifact() -> None:
    for node_id, artifact_id in NODE_ARTIFACTS.items():
        acceptance = "\n".join(NODE_CARD_COPY[node_id]["acceptance"])
        assert artifact_id in acceptance, f"{node_id} 验收未绑定 {artifact_id}"


def test_human_correction_title_and_description_are_readable() -> None:
    request = {
        "workflow_run_id": "run-1",
        "budget": {"correction_attempt": 1, "max_correction_attempts": 2},
        "upstream_artifacts": [
            {"artifact_id": "a08-test-design-ir", "artifact_hash": "sha256:a08"},
        ],
        "directives": [
            {
                "directive_id": "A09-ISSUE-007",
                "human_title": "预期结果写错了",
                "severity": "blocking",
                "case_id": "TC-E2E-001",
                "expected_id": "EXP-E2E-001-01",
                "plain_summary": "预期结果指向不存在的字段。",
                "recommendation": "改为可解析的期望矩阵。",
            }
        ],
    }
    assert human_correction_title(request) == "【人工修正】测试设计（A08）· 1 个问题待授权"
    description = human_correction_description(request)
    assert "## 本次授权明细" in description
    assert "1. **预期结果写错了**（`A09-ISSUE-007` · blocking）" in description
    assert "涉及用例：`TC-E2E-001`" in description
    assert "期望项：`EXP-E2E-001-01`" in description
    assert "Human A08 correction" not in description


def test_review_titles_are_readable() -> None:
    assert scope_review_title({"workflow_run_id": "run-1", "issue_count": 6}) == (
        "[run-1] G01 范围与口径审核 · 6 项待确认"
    )
    assert g02_review_title(
        {"workflow_run_id": "run-1", "review_summary": {"parent_case_count": 3}}
    ) == "[run-1] G02 测试用例审核 · 待审核 3 条用例"


def test_test_case_review_description_follows_five_sections() -> None:
    description = g02_review_description(
        {
            "review_summary": {
                "parent_case_count": 3,
                "blocking_issue_count": 0,
                "warning_count": 1,
                "n04_valid": True,
            },
            "upstream_artifacts": [
                {"artifact_id": "n04-test-case-ir-validation", "artifact_hash": "sha256:n04"}
            ],
        }
    )
    for heading in ("## 目标", "## 背景", "## 范围", "## 输入材料", "## 你需要审核什么", "## 验收"):
        assert heading in description
    assert "置 **done**" in description and "置 **blocked**" in description


def test_test_case_review_description_renders_review_items() -> None:
    description = g02_review_description(
        {
            "review_summary": {
                "parent_case_count": 1,
                "blocking_issue_count": 0,
                "warning_count": 0,
                "n04_valid": True,
            },
            "upstream_artifacts": [
                {"artifact_id": "n04-test-case-ir-validation", "artifact_hash": "sha256:n04"}
            ],
            "review_items": [
                {
                    "case_id": "TC-BE-001",
                    "title": "自定义维度三类位置的专用错误与双语提示",
                    "layer": "backend",
                    "risk": "critical",
                    "priority": "P0",
                    "source_refs": ["REQ-001"],
                    "expected": [
                        {
                            "id": "EXP-BE-001-01",
                            "description": "三个变体均拒绝查看明细并返回错误码。",
                            "oracle_type": "deterministic",
                            "matcher": "equals",
                            "observation_point": "detail_api.error.code",
                            "expected_value": "s307011534",
                        }
                    ],
                }
            ],
        }
    )
    assert "## 待审核用例明细" in description
    assert "`TC-BE-001` 自定义维度三类位置的专用错误与双语提示 · backend / critical / P0" in description
    assert "`EXP-BE-001-01`：三个变体均拒绝查看明细并返回错误码（错误码 `s307011534`）" in description
    assert "（错误码 `s307011534`）" in description
    assert "deterministic · equals" not in description

    assert "**测试场景**" in description
    assert "**测试步骤**" in description
    assert "**预期结果**" in description


def test_test_case_review_description_renders_scenario_and_steps() -> None:
    description = g02_review_description(
        {
            "review_summary": {
                "parent_case_count": 1,
                "blocking_issue_count": 0,
                "warning_count": 0,
                "n04_valid": True,
            },
            "upstream_artifacts": [
                {"artifact_id": "n04-test-case-ir-validation", "artifact_hash": "sha256:n04"}
            ],
            "review_items": [
                {
                    "case_id": "TC-BE-001",
                    "title": "自定义维度三类位置的专用错误与双语提示",
                    "layer": "backend",
                    "risk": "critical",
                    "priority": "P0",
                    "source_refs": ["REQ-001"],
                    "scenario": "三个变体均拒绝查看明细并返回错误码。",
                    "preconditions": ["测试租户支持创建统计图并触发查看明细。"],
                    "steps": [
                        "对变体 A、B、C 分别以 zh_CN 和 en 调用真实查看明细接口。",
                        "核对三类位置沿用现有检测顺序。",
                    ],
                    "expected": [
                        {
                            "id": "EXP-BE-001-01",
                            "description": "三个变体均拒绝查看明细并返回错误码。",
                            "oracle_type": "deterministic",
                            "matcher": "equals",
                            "observation_point": "detail_api.error.code",
                            "expected_value": "s307011534",
                        }
                    ],
                }
            ],
        }
    )
    assert "### 1. `TC-BE-001` 自定义维度三类位置的专用错误与双语提示 · backend / critical / P0" in description
    assert "**测试场景**" in description
    assert "三个变体均拒绝查看明细并返回错误码。" in description
    assert "**前置条件**" in description
    assert "测试租户支持创建统计图并触发查看明细。" in description
    assert "**测试步骤**" in description
    assert "1. 对变体 A、B、C 分别以 zh_CN 和 en 调用真实查看明细接口。" in description
    assert "**预期结果**" in description
    assert "（错误码 `s307011534`）" in description
    assert "deterministic · equals" not in description
