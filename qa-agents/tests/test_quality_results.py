from pathlib import Path

from qa_agents.card_copy import node_record_description
from qa_agents.quality_results import (
    build_case_outcomes,
    case_scene_zh,
    case_title_zh,
    human_failure_summary,
    render_quality_results_markdown,
)


def test_case_scene_uses_complete_chinese_scenario() -> None:
    assert case_title_zh("PC-BE-001-BACKEND") == "自定义维度三类位置拒绝查看明细"
    assert case_title_zh("PC-BE-006") == "没权限时保持原权限失败"
    assert "对象关系校验失败" in case_scene_zh("PC-BE-003-BACKEND")
    assert "批准模板" in case_scene_zh("PC-BE-003")
    assert case_scene_zh("PC-BE-099", "权限优先提示") == "权限优先提示"
    compiled = {"scenario": "基于多关联关系创建的统计指标查看明细应被拒绝并给出专用提示。"}
    assert case_scene_zh("PC-NEW-001", compiled=compiled) == compiled["scenario"]


def test_human_failure_summary_extracts_expected_and_missing_path() -> None:
    assert (
        human_failure_summary("AssertionError: E-BE-001-01: expected 's307011534', got 's307050002'")
        == "实际仍返回旧的通用提示「当前场景暂不支持查看明细」，没有返回专用提示「维度或数据范围中使用了自定义维度字段，暂不支持查看明细」"
    )
    assert (
        human_failure_summary("AssertionError: E-BE-003-01: expected 's307011536', got 's307050002'")
        == "实际仍返回旧的通用提示「当前场景暂不支持查看明细」，没有返回专用提示「基于多关联关系创建的统计指标，暂不支持查看明细」"
    )
    assert (
        human_failure_summary("AssertionError: E-BE-005-01: expected 1, got '此指标暂不支持查看明细。'")
        == "期望只返回一条专用提示，实际返回了「此指标暂不支持查看明细。」"
    )
    assert (
        human_failure_summary("Path 'Error.Params' does not exist at 'Params'")
        == "响应缺少指标名称参数，无法拼出带指标名的结果集筛选提示"
    )
    traceback = (
        "raise AssertionError(f\"Path '{path}' does not exist at '{name}'\")\n"
        "E                   AssertionError: Path 'Error.Code' does not exist at 'Error'"
    )
    assert human_failure_summary(traceback) == "响应缺少错误码，无法确认是否返回了专用错误"


def test_render_quality_results_groups_pass_fail_and_trace_ids() -> None:
    markdown = render_quality_results_markdown(
        [
            {
                "case_id": "PC-BE-006-BACKEND",
                "scene": "没权限时保持原权限失败",
                "status": "passed",
                "reason": "",
                "requests": [{"name": "perm_zh", "trace_id": "QA-pass-1"}],
            },
            {
                "case_id": "PC-BE-003-BACKEND",
                "title": "多关联关系拒绝查看明细",
                "scene": "基于多关联关系创建的统计指标，在对象关系校验失败时拒绝查看明细：返回专用错误码 s307011536，中英文提示精确为批准模板。",
                "status": "failed",
                "reason": "实际仍返回旧的通用提示「当前场景暂不支持查看明细」，没有返回专用提示「基于多关联关系创建的统计指标，暂不支持查看明细」",
                "requests": [
                    {"name": "detail_dimension_zh", "trace_id": "QA-fail-1"},
                    {"name": "detail_data_range_zh", "trace_id": ""},
                ],
            },
            {
                "case_id": "PC-E2E-001",
                "scene": "Web 统计图与拼表明细提示一致",
                "status": "skipped",
                "reason": "E2E 尚未接入，已按策略跳过",
                "requests": [],
            },
        ],
        summary="服务端测试完成（有缺陷）：执行 7，通过 1，失败 6",
    )
    assert markdown.startswith("## 服务端测试结果")
    assert "### 通过" in markdown
    assert "`PC-BE-006-BACKEND` 没权限时保持原权限失败" in markdown
    assert "`perm_zh`：`QA-pass-1`" in markdown
    assert "### 不通过" in markdown
    assert "`PC-BE-003-BACKEND` 多关联关系拒绝查看明细" in markdown
    assert "测试场景：基于多关联关系创建的统计指标，在对象关系校验失败时拒绝查看明细" in markdown
    assert "原因：实际仍返回旧的通用提示「当前场景暂不支持查看明细」，没有返回专用提示「基于多关联关系创建的统计指标，暂不支持查看明细」" in markdown
    assert "`detail_dimension_zh`：`QA-fail-1`" in markdown
    assert "`detail_data_range_zh`：`未记录`" in markdown
    assert "### 未执行" in markdown
    assert "E2E 尚未接入，已按策略跳过" in markdown
    assert "issue_code" not in markdown


def test_node_record_description_appends_n11_results() -> None:
    text = node_record_description(
        "N11",
        "服务端准出判定",
        artifact_name="n11-quality-decision.json",
        quality_results=[
            {
                "case_id": "PC-BE-006-BACKEND",
                "scene": "没权限时保持原权限失败",
                "status": "passed",
                "requests": [{"name": "perm_zh", "trace_id": "QA-1"}],
            }
        ],
        quality_summary="服务端测试完成（有缺陷）：执行 1，通过 1，失败 0",
    )
    assert "## 产出" in text
    assert "## 服务端测试结果" in text
    assert text.index("## 服务端测试结果") > text.index("## 产出")
    assert "`PC-BE-006-BACKEND` 没权限时保持原权限失败" in text
    assert "`perm_zh`：`QA-1`" in text


def test_build_case_outcomes_reads_lifecycle_trace_ids(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence" / "N08-S001"
    evidence.mkdir(parents=True)
    (evidence / "lifecycle.json").write_text(
        (
            '{"schema_version":"shard-lifecycle-evidence/1.0","cases":[{'
            '"case_id":"PC-BE-001-BACKEND","phases":{"test":[{'
            '"name":"detail_dimension_zh","status":"completed",'
            '"trace_id":"QA-live-1","operation":"fs_bi_stat.stat_base.data_query_da655ba1"'
            '}]}}]}'
        ),
        encoding="utf-8",
    )
    execution_path = tmp_path / "artifacts" / "n08-automation-execution.json"
    execution_path.parent.mkdir(parents=True)
    execution = {
        "payload": {
            "shards": [
                {
                    "shard_id": "N08-S001",
                    "case_ids": ["PC-BE-001-BACKEND"],
                    "outcome": "failed",
                    "stdout": "AssertionError: expected 's307011534', got 's307050002'",
                    "lifecycle_evidence_path": "evidence/N08-S001/lifecycle.json",
                }
            ]
        }
    }
    outcomes = build_case_outcomes(
        case_results=[{"case_id": "PC-BE-001-BACKEND", "status": "failed"}],
        cases_by_id={"PC-BE-001-BACKEND": {"title": "Backend custom dimension"}},
        executions=[execution],
        execution_paths=[execution_path],
        skipped_ids=["PC-E2E-001"],
        failures=[],
    )
    assert outcomes[0]["title"] == "自定义维度三类位置拒绝查看明细"
    assert "维度、数据范围、下钻" in outcomes[0]["scene"]
    assert outcomes[0]["reason"] == (
        "实际仍返回旧的通用提示「当前场景暂不支持查看明细」，"
        "没有返回专用提示「维度或数据范围中使用了自定义维度字段，暂不支持查看明细」"
    )
    assert outcomes[0]["requests"][0]["trace_id"] == "QA-live-1"
    assert outcomes[1]["case_id"] == "PC-E2E-001"
    assert outcomes[1]["status"] == "skipped"


def test_build_case_outcomes_prefers_failed_over_earlier_pass() -> None:
    outcomes = build_case_outcomes(
        case_results=[
            {"case_id": "CASE-AUTO", "status": "passed"},
            {"case_id": "CASE-AUTO", "status": "failed"},
        ],
        cases_by_id={"CASE-AUTO": {"title": "权限优先提示"}},
        executions=[],
        failures=[
            {
                "case_ids": ["CASE-AUTO"],
                "summary": "AssertionError: expected 's307011534', got 's307050002'",
                "classification": "product_defect",
            }
        ],
    )
    assert len(outcomes) == 1
    assert outcomes[0]["case_id"] == "CASE-AUTO"
    assert outcomes[0]["status"] == "failed"
    assert outcomes[0]["title"] == "权限优先提示"
    assert outcomes[0]["scene"] == "权限优先提示"
    assert outcomes[0]["reason"] == (
        "实际仍返回旧的通用提示「当前场景暂不支持查看明细」，"
        "没有返回专用提示「维度或数据范围中使用了自定义维度字段，暂不支持查看明细」"
    )


def test_build_case_outcomes_explains_skipped_contract_and_e2e() -> None:
    outcomes = build_case_outcomes(
        case_results=[],
        cases_by_id={
            "PC-CT-001-CONTRACT": {"title": "错误码透传并绑定中英文模板", "layer": "contract"},
            "PC-E2E-001-E2E": {"title": "Web 统计图与拼表明细提示一致", "layer": "e2e"},
        },
        executions=[],
        skipped_ids=["PC-CT-001-CONTRACT", "PC-E2E-001-E2E"],
    )
    by_id = {item["case_id"]: item for item in outcomes}
    assert by_id["PC-CT-001-CONTRACT"]["reason"] == "契约用例未绑定接口契约，本轮未执行"
    assert by_id["PC-E2E-001-E2E"]["reason"] == "E2E 尚未接入，已按策略跳过"
