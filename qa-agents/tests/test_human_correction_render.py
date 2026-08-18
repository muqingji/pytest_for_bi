from qa_agents.human_correction import render_human_correction_markdown


def test_human_correction_markdown_is_readable_chinese() -> None:
    request = {
        "workflow_run_id": "run-1",
        "budget": {"correction_attempt": 1, "max_correction_attempts": 1},
        "directives": [
            {
                "directive_id": "A09-ISSUE-007",
                "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE",
                "human_title": "预期结果写错了",
                "plain_summary": "预期结果指向不存在的字段，用例无法校验。",
                "message": "expected_value 指向 test_data.matrix.code_messages_and_parameters，路径不存在。",
                "recommendation": "改为可直接解析的期望矩阵。",
            }
        ],
    }
    markdown = render_human_correction_markdown(request)
    assert "测试设计人工修正" in markdown
    assert "请决定是否授权以下修正" in markdown
    assert "A09-ISSUE-007 - 预期结果写错了" in markdown
    assert "问题：预期结果指向不存在的字段，用例无法校验。" in markdown
    assert "修正方案：改为可直接解析的期望矩阵。" in markdown
    assert "技术细节：expected_value 指向 test_data.matrix" in markdown
    assert "置为 **done**" in markdown and "置为 **cancelled**" in markdown
    assert "Problem:" not in markdown and "Required correction:" not in markdown


def test_human_correction_markdown_falls_back_without_plain_summary() -> None:
    request = {
        "workflow_run_id": "run-1",
        "budget": {"correction_attempt": 1, "max_correction_attempts": 1},
        "directives": [
            {
                "directive_id": "A09-ISSUE-008",
                "issue_code": "LOCALE_NAME_PRECEDENCE_FIXTURE_CONFLICT",
                "human_title": "",
                "plain_summary": "",
                "message": "TC-BE-002 的中英文夹具冲突。",
                "recommendation": "按 locale 拆分数据。",
            }
        ],
    }
    markdown = render_human_correction_markdown(request)
    assert "A09-ISSUE-008 - LOCALE_NAME_PRECEDENCE_FIXTURE_CONFLICT" in markdown
    assert "问题：TC-BE-002 的中英文夹具冲突。" in markdown
