from qa_agents.gates import (
    plain_text,
    scope_carry_forward,
    scope_followup_issues,
    scope_gate_issues,
)


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
    assert [item["category"] for item in issues[:3]] == ["待确认需求", "待确认技术方案", "待确认测试范围"]
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


def test_scope_gate_deduplicates_same_topic_across_agents() -> None:
    issues = scope_gate_issues(
        {"ambiguities": [{"id": "AMB-001", "message": "同时命中多个限制时提示优先级未规定"}]},
        {},
        {"findings": [{"id": "F-007", "summary": "多个受限条件同时命中时的提示优先级未确认"}]},
    )
    assert len(issues) == 1
    assert issues[0]["issue_id"] == "A02:AMB-001"
    assert issues[0]["related_issue_ids"] == ["A02:AMB-001", "A06:F-007"]
    assert issues[0]["sources"] == ["A02", "A06"]


def test_followup_keeps_only_returned_topic_and_uses_new_a06_explanation() -> None:
    previous = scope_gate_issues(
        {"ambiguities": [{"id": "AMB-1", "message": "特殊what/whatlist范围未明确"}]}, {}, {}
    )
    current = scope_gate_issues(
        {"ambiguities": [{"id": "AMB-1", "message": "特殊what/whatlist范围未明确"}]},
        {},
        {"findings": [{"id": "F-2", "type": "conflict", "summary": "whatlist 当前实现位置与方案不同"}]},
    )
    result = scope_followup_issues(
        current,
        {"issues": previous},
        {"resolutions": [{"issue_id": "A02:AMB-1", "disposition": "return_to_a06"}]},
    )
    assert len(result) == 1
    assert result[0]["issue_id"] == "A06:F-2"
    assert result[0]["category"] == "待确认测试范围"
    assert "当前实现位置" in result[0]["plain_summary"]


def test_carry_forward_drops_confirmed_scope_and_keeps_new_finding() -> None:
    fresh = scope_gate_issues(
        {"ambiguities": [{"id": "AMB-1", "message": "特殊what/whatlist范围未明确"}]},
        {},
        {
            "findings": [
                {"id": "F-2", "type": "conflict", "summary": "whatlist 当前实现位置与方案不同"},
                {"id": "F-12", "type": "out_of_scope_change", "summary": "员工或部门主题特殊分支将本地化消息改为空字符串"},
            ]
        },
    )
    prior = [
        {
            "resolutions": [
                {"issue_id": "A02:AMB-1", "disposition": "confirmed", "topic_key": "what_whatlist"},
            ]
        }
    ]

    kept = scope_carry_forward(fresh, prior)

    assert [item["issue_id"] for item in kept] == ["A06:F-12"]


def test_carry_forward_keeps_everything_without_prior_decisions() -> None:
    fresh = scope_gate_issues(
        {"ambiguities": [{"id": "AMB-1", "message": "特殊what/whatlist范围未明确"}]}, {}, {}
    )

    kept = scope_carry_forward(fresh, [])

    assert [item["issue_id"] for item in kept] == ["A02:AMB-1"]
