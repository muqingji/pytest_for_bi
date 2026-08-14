from qa_agents.gates import plain_text, scope_gate_issues


def test_plain_text_replaces_overlapping_terms_once() -> None:
    assert plain_text("WhatList 与 What") == "WhatList 动态关联 与 What 动态关联"


def test_scope_gate_collects_all_sources_and_plain_chinese_fields() -> None:
    issues = scope_gate_issues(
        {"ambiguities": [{"id": "AMB-001", "issue_code": "requirement_missing", "message": "同时命中多个限制时提示优先级未规定"}]},
        {
            "blocking_items": [
                {
                    "id": "BI-001",
                    "issue_code": "product_acceptance_open_question",
                    "summary": "PRD 文案只写统计图，未说明拼表口径",
                    "recommendation": "确认端无关文案",
                }
            ]
        },
        {
            "findings": [
                {"id": "LOW", "severity": "low", "type": "scope_drift"},
                {"id": "HIGH", "severity": "high", "type": "implementation_gap", "summary": "filter.fieldName 未按 fieldId 解析名称"},
            ]
        },
    )
    assert [item["source"] for item in issues] == ["A02", "A03", "A06", "A06"]
    assert [item["issue_code"] for item in issues] == [
        "requirement_missing",
        "product_acceptance_open_question",
        "scope_drift",
        "implementation_gap",
    ]
    # 全量收集：A06 的全部 finding（含 low/medium）都进 G01，一次审批覆盖全部待确认项
    assert {item["severity"] for item in issues if item["source"] == "A06"} == {"low", "high"}
    assert issues[3]["issue_id"].startswith("A06:")
    # 通俗中文分类与描述
    assert [item["category"] for item in issues[:3]] == ["需求待确认", "技术方案待确认", "实现与测试范围待确认"]
    assert "需求文档里没有写清楚" in issues[0]["plain_summary"]
    assert "建议：确认端无关文案" in issues[1]["plain_summary"]
    assert "筛选字段名称" in issues[3]["plain_summary"]
    assert "字段 ID" in issues[3]["plain_summary"]
    assert issues[3]["plain_summary"] != issues[3]["detail"]["summary"]
    assert issues[0]["confirm_action"].startswith("请确认")
    assert issues[1]["confirm_action"].startswith("请确认")
    assert issues[3]["confirm_action"].startswith("请确认")
    assert all(item["route_to"] == item["source"] for item in issues)


def test_scope_gate_keeps_requirement_ids_from_findings() -> None:
    issues = scope_gate_issues(
        {},
        {},
        {"findings": [{"id": "FIND-004", "severity": "high", "type": "needs_human", "requirement_ids": ["REQ-005"]}]},
    )
    assert issues[0]["requirement_ids"] == ["REQ-005"]
    assert issues[0]["detail"]["requirement_ids"] == ["REQ-005"]
