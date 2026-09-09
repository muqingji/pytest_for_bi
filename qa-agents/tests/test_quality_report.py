from qa_agents.quality_report import render_standard_quality_report


def test_standard_quality_report_is_human_readable_and_consistent() -> None:
    artifact = {
        "workflow_run_id": "run-1",
        "payload": {
            "decision": "completed_with_defects",
            "release_disposition": "pending",
            "bug_draft_count": 1,
        },
    }
    report = render_standard_quality_report(
        artifact,
        quality_summary="执行 2，通过 1，失败 1",
        case_outcomes=[
            {"case_id": "C-1", "title": "正常路径", "scene": "正常请求返回明细。", "status": "passed", "requests": [{"name": "main", "trace_id": "FSW-1.2-abc"}]},
            {"case_id": "C-2", "title": "限制提示", "scene": "受限场景返回专用提示。", "status": "failed", "reason": "实际返回通用提示，本应返回专用提示", "requests": [{"name": "main", "trace_id": "FSW-1.2-def"}]},
            {"case_id": "C-3", "title": "端到端", "scene": "Web 展示后端提示。", "status": "skipped", "reason": "E2E 尚未接入", "requests": []},
        ],
        constructed_assets=[
            {"case_id": "C-1", "resource_type": "stat_chart", "display_name": "正常明细验证统计图", "resource_id": "BI_chart_1"},
            {"case_id": "C-2", "resource_type": "custom_dimension", "display_name": "客户等级自定义维度", "resource_id": "BI_dimension_1"},
            {"case_id": "C-2", "resource_type": "stat_chart", "display_name": "限制提示验证统计图", "resource_id": "BI_chart_2"},
        ],
    )
    for heading in ("### 1. 报告结论", "### 2. 测试概况", "### 3. 准出依据", "### 4. 用例执行明细", "### 5. 风险与后续动作"):
        assert heading in report
    assert "存在缺陷，暂不建议准出" in report
    assert "实际执行：`2` 条" in report
    assert "通过 `1` 条，不通过 `1` 条" in report
    assert "未执行：`1` 条" in report
    assert "FSW-1.2-def" in report
    assert "统计图：`限制提示验证统计图`（`BI_chart_2`）" in report
    assert "自定义维度：`客户等级自定义维度`（`BI_dimension_1`）" in report
    assert "本轮未执行，未使用实际测试数据" in report
    assert "completed_with_defects" not in report
