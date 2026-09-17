from qa_agents.card_copy import (
    DEFAULT_NODE_COPY,
    NODE_CARD_COPY,
    human_correction_description,
    human_correction_title,
    node_issue_description,
    node_issue_title,
    node_record_description,
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


def test_node_record_description_appends_approval_block_when_provided() -> None:
    plain = node_record_description("N08", "受控自动化执行", artifact_name="n08-automation-execution.json")
    assert "## 你需要处理" not in plain
    assert "无需 Agent 或人工操作" in plain
    block = [
        "本节点执行判定为可重试失败（`failed_retryable`），需要你决定是否批准重试。",
        "",
        "### 决策动作",
        "- 置 **done**：批准重试。",
    ]
    with_block = node_record_description(
        "N08",
        "受控自动化执行",
        artifact_name="n08-automation-execution.json",
        approval_block=block,
    )
    assert "## 你需要处理" in with_block
    assert "批准重试" in with_block
    assert with_block.index("## 你需要处理") > with_block.index("## 产出")
    assert "无需 Agent 或人工操作" not in with_block
    assert "需要你审批重试决策" in with_block


def test_node_record_description_prints_standard_report_in_outputs() -> None:
    description = node_record_description(
        "N12",
        "质量报告发布",
        artifact_name="n12-quality-report.json",
        standard_quality_report="## 标准测试报告\n\n### 1. 报告结论\n\n- 测试结论：**测试通过，可以准出**",
    )
    assert "## 标准测试报告" in description
    assert description.index("## 标准测试报告") > description.index("## 产出")


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


def test_a22_issue_description_prints_complete_disposition_block() -> None:
    description = node_issue_description(
        "A22",
        "112 测试数据规划",
        input_name="a22-input.json",
        approval_issues=[
            {
                "id": "UR-01",
                "requirement_id": "UR-01",
                "reason_code": "stat_chart_integrity_probes_missing",
                "severity": "blocking",
                "affected_case_ids": ["TC-BE-001", "TC-CT-001"],
                "required_resolution": (
                    "Provide a verified recipe containing read-only fxops_query integrity probes."
                ),
            }
        ],
    )

    assert "## 系统要去造的数据（不用你审）" in description
    assert "1. **确认新建统计图**（`UR-01` · blocking）" in description
    assert "   - 要造什么：" in description
    assert "   - 卡在哪：112 没有现成测试图，本应新建。" in description
    assert "不该问你要不要建" in description
    assert "处置评论：`UR-01:" not in description
    assert "   - 涉及用例：`TC-BE-001`、`TC-CT-001`" in description
    assert "这轮不造新图" not in description
    assert "stat_chart_integrity_probes_missing" not in description
    assert "Provide a verified" not in description
    assert "fxops_query" not in description
    assert "recipe" not in description
    assert "只给上面「你需要处理」里出现「请提供」的项回评论" in description


A22_RUN_APPROVAL_ITEMS = [
    {
        "id": f"UR-{index + 1:02d}",
        "requirement_id": f"UR-{index + 1:02d}",
        "reason_code": code,
        "severity": "blocking",
        "affected_case_ids": ["A08-TC-EXAMPLE-BACKEND"],
        "required_resolution": (
            "Provide a verified recipe covering source, topology, dimension and aggregation."
        ),
    }
    for index, code in enumerate(
        (
            "stat_chart_integrity_probes_missing",
            "historical_pre_change_assets_missing",
            "pre_change_response_baselines_missing",
            "joined_table_policy_gap",
            "frozen_dynamic_relation_metadata_missing",
            "permission_test_fixtures_missing",
            "result_set_metric_type_fixtures_missing",
        )
    )
]


def test_a22_run_requirements_are_rendered_in_chinese() -> None:
    description = node_issue_description(
        "A22",
        "112 测试数据规划",
        input_name="a22-input.json",
        approval_issues=A22_RUN_APPROVAL_ITEMS,
    )

    assert "待审批：`2` 项" in description
    for title in (
        "确认新建统计图",
        "历史场景缺老图",
        "缺改前提示样例",
        "请批准新建拼表",
        "动态关联名单未定",
        "缺无权限测试账号",
        "确认新建更多指标",
    ):
        assert f"**{title}**" in description, title
    assert "## 你需要处理" in description
    assert "## 系统要去造的数据（不用你审）" in description
    assert description.count("   - 要造什么：") == 7
    assert description.count("   - 请拍板：") == 2  # owner: historical + permission
    assert "这轮不造新图" not in description
    for code in (item["reason_code"] for item in A22_RUN_APPROVAL_ITEMS):
        assert code not in description, code
    assert "Provide a verified" not in description
    assert "fxops_query" not in description
    assert "recipe" not in description
    assert "existing_asset_discovery" not in description


def test_a22_two_section_format_is_locked() -> None:
    description = node_issue_description(
        "A22",
        "112 测试数据规划",
        input_name="a22-input.json",
        approval_issues=[
            {
                "requirement_id": "UR-02",
                "reason_code": "historical_pre_change_assets_missing",
                "severity": "blocking",
                "affected_case_ids": ["TC-BE-HIST"],
            },
            {
                "requirement_id": "UR-01",
                "reason_code": "stat_chart_integrity_probes_missing",
                "severity": "blocking",
                "affected_case_ids": ["TC-BE-CHART"],
            },
            {
                "requirement_id": "UR-09",
                "id": "never_seen_gap",
                "severity": "blocking",
                "affected_case_ids": ["TC-BE-NEW"],
            },
        ],
    )
    block = description[description.index("## 你需要处理") :]
    assert block.startswith("## 你需要处理")
    assert "## 系统要去造的数据（不用你审）" in block
    owner, system = block.split("## 系统要去造的数据（不用你审）", 1)
    assert "待审批：`2` 项" in owner
    assert "请拍板：" in owner
    assert "处置评论：`UR-02: confirmed/skip/return/need_evidence`" in owner
    assert "处置评论：`UR-09: confirmed/skip/return/need_evidence`" in owner
    assert "请拍板：" not in system.split("操作选项：", 1)[0]
    assert "处置评论：" not in system.split("操作选项：", 1)[0]
    assert "要测什么：" in owner
    assert "要造什么：" in owner
    assert "要测什么：" in system
    assert "要造什么：" in system
    assert "产品场景：" not in block
    assert "这轮不造新图" not in block
    assert "内部原因代码" in block


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
    ) == "[run-1] G02 用例设计确认 · 3 条已按冻结规则写完"
    assert g02_review_title(
        {
            "workflow_run_id": "run-1",
            "review_summary": {"parent_case_count": 11},
            "decision_items": [
                {"id": "PC-BE-006:human_review", "human_title": "没权限时不要改提示"}
            ],
        }
    ) == "[run-1] G02 用例设计确认 · 1 项待拍板"


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
    for heading in ("## 目标", "## 背景", "## 范围", "## 输入材料", "## 你需要拍板", "## 验收"):
        assert heading in description
    assert "置 **done**" in description and "置 **blocked**" in description
    assert "没有未冻结的产品口径" in description
    assert "## 待审核用例明细" not in description


def test_test_case_review_description_surfaces_uncertainties_not_every_case() -> None:
    description = g02_review_description(
        {
            "review_summary": {
                "parent_case_count": 2,
                "blocking_issue_count": 0,
                "warning_count": 0,
                "n04_valid": True,
            },
            "upstream_artifacts": [
                {"artifact_id": "n04-test-case-ir-validation", "artifact_hash": "sha256:n04"}
            ],
            "decision_items": [
                {
                    "id": "PC-BE-006:human_review",
                    "human_title": "没权限时不要改提示",
                    "product_scene": "没权限点查看明细应继续走原来的权限失败。",
                    "plain_summary": "权限失败用哪条错误码没有写死。",
                    "confirm_action": "接受维持原权限失败即可交付。",
                }
            ],
            "review_items": [
                {
                    "case_id": "PC-BE-001",
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
                },
                {
                    "case_id": "PC-BE-006",
                    "title": "没权限时不要改提示",
                    "layer": "backend",
                    "risk": "critical",
                    "priority": "P0",
                    "source_refs": ["RULE-PERMISSION-PRIORITY"],
                    "expected": [],
                },
            ],
        }
    )
    assert "## 你需要拍板" in description
    assert "本 Issue 附件 `case-cards.md`" in description
    assert "请打开该文件阅读测试场景 / 前置条件 / 测试步骤 / 预期结果。" in description
    assert "请打开附件 `case-cards.md` 阅读完整中文用例。" in description
    assert "没权限时不要改提示" in description
    assert "产品场景：没权限点查看明细应继续走原来的权限失败。" in description
    assert "设计不确定点：权限失败用哪条错误码没有写死。" in description
    assert "请拍板：接受维持原权限失败即可交付。" in description
    assert "## 已按冻结规则写完（不逐条审批）" in description
    assert "`PC-BE-001` 自定义维度三类位置的专用错误与双语提示" in description
    assert "## 待审核用例明细" not in description
    assert "**测试步骤**" not in description
    assert "请确认该用例的场景、步骤和预期结果可直接执行" not in description
    assert "deterministic · equals" not in description


def test_g02_description_shows_provider_case_ids() -> None:
    description = g02_review_description(
        {
            "review_summary": {
                "parent_case_count": 1,
                "blocking_issue_count": 0,
                "warning_count": 0,
                "n04_valid": True,
                "provider_case_count": 1,
            },
            "upstream_artifacts": [
                {"artifact_id": "n04-test-case-ir-validation", "artifact_hash": "sha256:n04"}
            ],
            "review_items": [
                {
                    "case_id": "PROVIDER-CASE-001",
                    "provider_case_id": "FS-20260910-001",
                    "title": "验证查看明细",
                    "human_title": "验证查看明细",
                }
            ],
        }
    )
    assert "其中 1 条来自 Case Provider" in description
    assert "`PROVIDER-CASE-001` （Provider `FS-20260910-001`） 验证查看明细" in description
