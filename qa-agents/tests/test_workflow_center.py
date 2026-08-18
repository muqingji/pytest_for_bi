import json
from pathlib import Path

import pytest

from qa_agents.errors import ContractError
from qa_agents.storage import ArtifactStore
from qa_agents.workflow_center import (
    _render_stage_card_markdown,
    _stage_cards,
    build_workflow_projection,
    render_workflow_center_markdown,
    sync_multica_workflow_center,
)


def test_stage_cards_do_not_report_downstream_done_after_upstream_block() -> None:
    projection = {
        "nodes": [
            {"node_id": "G03", "state": "blocked", "stage_card_id": "C5", "stage_card_title": "代码审核"},
            {"node_id": "N08", "state": "completed", "stage_card_id": "C6", "stage_card_title": "执行"},
            {"node_id": "N11", "state": "completed", "stage_card_id": "C7", "stage_card_title": "质量"},
            {"node_id": "N12", "state": "completed", "stage_card_id": "C8", "stage_card_title": "报告"},
        ]
    }

    cards = {card["stage_card_id"]: card for card in _stage_cards(projection)}
    assert cards["C5"]["status"] == "blocked"
    for card_id in ("C6", "C7", "C8"):
        assert cards[card_id]["status"] == "backlog"
        assert "等待 `C5` 解除" in cards[card_id]["description"]


WORKSPACE_ID = "workspace-1"
WORKFLOW_PROJECT_ID = "project-workflows"
INTERNAL_PROJECT_ID = "project-internal"
PARENT_ID = "issue-parent"
ACTION_ID = "issue-g01"


def workflow_spec() -> dict:
    return {
        "schema_version": "requirement-workflow/1.0",
        "workflow_id": "REQ-101",
        "requirement_id": "REQ-101",
        "workflow_run_id": "REQ-101-r003",
        "workflow_definition_version": "new-requirement/1.0",
        "revision": 1,
        "source_snapshot_id": "sha256:snapshot",
        "title": "查看明细提示优化",
        "parent_issue": {"id": PARENT_ID, "identifier": "QAA-101"},
        "run_issue": {"id": "issue-run", "identifier": "QAA-100"},
        "nodes": [
            {
                "execution_id": "A02-1",
                "node_id": "A02",
                "label": "需求分析",
                "stage": 1,
                "state": "completed",
                "completion": "7 条需求",
                "result_summary": "5 个歧义",
                "issue_id": "issue-a02",
                "issue_identifier": "QAA-102",
            },
            {
                "execution_id": "A03-1",
                "node_id": "A03",
                "label": "技术与可测性分析",
                "stage": 1,
                "state": "completed",
                "completion": "17 条事实",
                "result_summary": "5 个阻塞项",
                "issue_id": "issue-a03",
                "issue_identifier": "QAA-103",
            },
            {
                "execution_id": "A06-1",
                "node_id": "A06",
                "label": "需求实现对齐",
                "stage": 2,
                "state": "completed",
                "completion": "7 条映射",
                "result_summary": "9 个对齐问题",
                "issue_id": "issue-a06",
                "issue_identifier": "QAA-104",
            },
            {
                "execution_id": "G01-1",
                "node_id": "G01",
                "label": "范围与口径审核",
                "stage": 3,
                "state": "waiting_human",
                "completion": "0/15",
                "result_summary": "等待 QA Owner",
                "issue_id": ACTION_ID,
                "issue_identifier": "QAA-105",
            },
            {
                "execution_id": "N24-1",
                "node_id": "N24",
                "label": "风险策略",
                "stage": 4,
                "state": "not_started",
                "completion": "0/1",
                "result_summary": "等待 G01",
            },
        ],
        "actions": [
            {
                "action_id": "G01-review",
                "gate_id": "G01",
                "title": "范围与口径审核",
                "status": "open",
                "owner_member_id": "member-qa",
                "item_count": 15,
                "summary": "逐项确认处置、理由和负责人",
                "issue_id": ACTION_ID,
                "issue_identifier": "QAA-105",
            }
        ],
        "run_history": [
            {
                "workflow_run_id": "REQ-101-r002",
                "status": "历史运行",
                "summary": "已完成测试设计链",
            }
        ],
    }


def workflow_config() -> dict:
    return {
        "schema_version": "multica-workflow-center/1.0",
        "workspace_id": WORKSPACE_ID,
        "workflow_project_id": WORKFLOW_PROJECT_ID,
        "internal_project_id": INTERNAL_PROJECT_ID,
        "properties": {
            "item_type": "工作项类型",
            "workflow_status": "工作流状态",
            "progress": "完成进度",
            "current_node": "当前节点",
            "action_required": "需要我处理",
        },
    }


def test_projection_prioritizes_human_action_and_renders_one_cockpit() -> None:
    projection = build_workflow_projection(workflow_spec())
    markdown = render_workflow_center_markdown(projection)

    assert projection["overall_status"] == "needs_action"
    assert projection["multica_status"] == "in_review"
    assert projection["progress"] == {"completed": 3, "total": 5, "percent": 60}
    assert projection["action_count"] == 15
    assert "需要你处理" in markdown
    assert "范围与口径审核（QAA-105）" in markdown
    assert "| 2 | 需求实现对齐（QAA-104） | 已完成 |" in markdown
    assert "REQ-101-r002" in markdown
    assert projection["projection_hash"].startswith("sha256:")


def test_human_action_renders_approval_items_in_cockpit_and_stage_card() -> None:
    spec = workflow_spec()
    approval_items = [
        {
            "id": "A06:FIND-004",
            "title": "实现与测试范围待确认",
            "category": "实现与测试范围待确认",
            "summary": "需要人工确认：动态关联覆盖范围未冻结，需要产品确认。",
            "confirm_action": "请确认是接受当前实现口径还是补齐实现证据。",
            "severity": "high",
            "requirement_ids": ["REQ-005"],
            "source_refs": [],
        },
        {
            "id": "A02:AMB-001",
            "title": "需求待确认",
            "category": "需求待确认",
            "summary": "需求文档里没有写清楚：多限制命中时的提示优先级未确认。",
            "confirm_action": "请确认或补充需求口径。",
            "severity": "high",
            "requirement_ids": ["REQ-001"],
            "source_refs": [],
        },
    ]
    spec["actions"][0]["approval_items"] = approval_items
    spec["actions"][0]["item_count"] = len(approval_items)
    for node in spec["nodes"]:
        if node["node_id"] == "G01":
            node["approval_items"] = approval_items

    projection = build_workflow_projection(spec)
    markdown = render_workflow_center_markdown(projection)
    assert "#### 审批项（2）" in markdown
    assert "**实现与测试范围待确认**（`A06:FIND-004`）" in markdown
    assert "需要人工确认：动态关联覆盖范围未冻结，需要产品确认。" in markdown
    assert "需要确认：请确认是接受当前实现口径还是补齐实现证据。" in markdown
    assert "涉及需求：`REQ-005`" in markdown
    assert "**需求待确认**（`A02:AMB-001`）" in markdown

    g01_node = next(node for node in projection["nodes"] if node["node_id"] == "G01")
    stage_markdown = _render_stage_card_markdown("C1", "范围确认", [g01_node])
    assert "来源：`G01`" in stage_markdown
    assert "共 2 个待确认事项，请逐条确认后继续。" in stage_markdown
    assert "**实现与测试范围待确认**（`A06:FIND-004`）" in stage_markdown
    assert "需要确认：请确认是接受当前实现口径还是补齐实现证据。" in stage_markdown
    assert "涉及需求：`REQ-005`" in stage_markdown


def test_human_action_without_approval_items_renders_fallback_hint() -> None:
    projection = build_workflow_projection(workflow_spec())
    markdown = render_workflow_center_markdown(projection)
    assert "审批项：请打开审核入口查看具体审批项。" in markdown
    g01_node = next(node for node in projection["nodes"] if node["node_id"] == "G01")
    stage_markdown = _render_stage_card_markdown("C1", "范围确认", [g01_node])
    assert "审批项：请打开审核入口查看具体审批项。" in stage_markdown


def test_stage_card_renders_human_correction_issues_and_entry() -> None:
    node = {
        "node_id": "N04",
        "stage": 10,
        "stage_card_id": "C3",
        "stage_card_title": "测试设计与审核",
        "state": "waiting_human",
        "label": "Test Case IR 校验",
        "result_summary": "Artifact n04-test-case-ir-validation accepted",
        "approval_items": [
            {
                "id": "A09-ISSUE-007",
                "title": "oracle",
                "category": "oracle",
                "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE",
                "case_id": "TC-E2E-001",
                "expected_id": "EXP-E2E-001-01",
                "summary": "EXP-E2E-001-01 的 expected_value 指向不存在的 test_data 路径。",
                "recommendation": "改为可直接解析的结构化期望矩阵。",
                "severity": "blocking",
                "requirement_ids": ["REQ-006"],
                "source_refs": [],
            }
        ],
        "human_action_entry": {
            "issue_id": "7a6c629c-100b-4a8b-9eb2-1fab1f24635d",
            "issue_identifier": "QAA-325",
            "status": "in_review",
        },
    }
    markdown = _render_stage_card_markdown("C3", "测试设计与审核", [node])
    assert "1. **预期结果无法解析**（`A09-ISSUE-007`）" in markdown
    assert "审查发现 1 个问题，需你决策是否授权修正。" in markdown
    assert "问题：用例 `EXP-E2E-001-01` 的预期结果指向了一个不存在的字段路径" in markdown
    assert "建议修正：改为可直接解析的结构化期望矩阵。" in markdown
    assert "操作：打开 `QAA-325`（人工修正 Issue，状态 in_review）：" in markdown
    assert "置为 **done**：授权修正，系统自动修改用例并重新校验，流程自动继续。" in markdown
    assert "置为 **cancelled**：不修正，终止当前流程。" in markdown


def test_stage_card_prefers_human_title_and_plain_summary() -> None:
    node = {
        "node_id": "N04",
        "stage": 10,
        "stage_card_id": "C3",
        "stage_card_title": "测试设计与审核",
        "state": "waiting_human",
        "label": "Test Case IR 校验",
        "result_summary": "Artifact n04-test-case-ir-validation accepted",
        "approval_items": [
            {
                "id": "A09-ISSUE-007",
                "title": "oracle",
                "category": "oracle",
                "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE",
                "human_title": "预期结果写错了",
                "plain_summary": "预期结果指向一个不存在的字段，这条用例无法校验。",
                "case_id": "TC-E2E-001",
                "expected_id": "EXP-E2E-001-01",
                "summary": "EXP-E2E-001-01 的 expected_value 指向不存在的 test_data 路径。",
                "recommendation": "改为可直接解析的结构化期望矩阵。",
                "severity": "blocking",
                "requirement_ids": ["REQ-006"],
                "source_refs": [],
            }
        ],
        "human_action_entry": {
            "issue_id": "7a6c629c-100b-4a8b-9eb2-1fab1f24635d",
            "issue_identifier": "QAA-325",
            "status": "in_review",
        },
    }
    markdown = _render_stage_card_markdown("C3", "测试设计与审核", [node])
    assert "1. **预期结果写错了**（`A09-ISSUE-007`）" in markdown
    assert "问题：预期结果指向一个不存在的字段，这条用例无法校验。" in markdown
    assert "EXP-E2E-001-01 的 expected_value 指向不存在的 test_data 路径。" not in markdown


def test_stage_card_exception_section_points_to_human_entry() -> None:
    blocked = {
        "node_id": "A09",
        "stage": 8,
        "stage_card_id": "C3",
        "stage_card_title": "测试设计与审核",
        "state": "blocked",
        "label": "Oracle 与覆盖审查",
        "result_summary": "发现 2 个阻塞问题需人工定向修正（A09-ISSUE-007、A09-ISSUE-008）",
    }
    waiting = {
        "node_id": "N04",
        "stage": 9,
        "stage_card_id": "C3",
        "stage_card_title": "测试设计与审核",
        "state": "waiting_human",
        "label": "Test Case IR 校验",
        "result_summary": "Artifact n04-test-case-ir-validation accepted",
        "human_action_entry": {
            "issue_id": "7a6c629c-100b-4a8b-9eb2-1fab1f24635d",
            "issue_identifier": "QAA-325",
            "status": "in_review",
        },
    }
    markdown = _render_stage_card_markdown("C3", "测试设计与审核", [blocked, waiting])
    assert "A09" in markdown
    assert "发现 2 个阻塞问题需人工定向修正" in markdown
    assert "处理入口：`QAA-325`，见下方人工操作" in markdown
    assert "操作：打开 `QAA-325`（人工修正 Issue，状态 in_review）：" in markdown

    blocked["artifact_id"] = "a09-oracle-coverage-review"
    blocked["artifact_hash"] = "sha256:9c1345ccedccd16367ced8a057e95515387ca8e0db9bdc200ef5153daebbc712"
    waiting["artifact_id"] = "n04-test-case-ir-validation"
    waiting["artifact_hash"] = "sha256:4bce713d1297625be0fc5288847458b21baa08ab97a5ce7a5677ed151ccb5d09"
    markdown = _render_stage_card_markdown("C3", "测试设计与审核", [blocked, waiting])
    assert "`a09-oracle-coverage-review`（Oracle 与覆盖审查 · 阻塞）" in markdown
    assert "`n04-test-case-ir-validation`（Test Case IR 校验 · 等待人工）：待人工授权修正，见下方人工操作" in markdown


@pytest.mark.parametrize(
    ("node_states", "action_status", "expected"),
    [
        (["completed", "blocked"], "open", "blocked"),
        (["completed", "waiting_human"], "open", "needs_action"),
        (["completed", "running"], "completed", "running"),
        (["completed", "not_started"], "completed", "queued"),
        (["completed", "skipped"], "completed", "completed"),
        (["cancelled", "superseded"], "cancelled", "cancelled"),
    ],
)
def test_workflow_status_precedence(
    node_states: list[str], action_status: str, expected: str
) -> None:
    spec = workflow_spec()
    spec["nodes"] = [
        {
            "execution_id": f"node-{index}",
            "node_id": f"N{index}",
            "stage": index + 1,
            "state": state,
        }
        for index, state in enumerate(node_states)
    ]
    spec["actions"][0]["status"] = action_status

    assert build_workflow_projection(spec)["overall_status"] == expected


def test_projection_rejects_duplicate_execution_identity() -> None:
    spec = workflow_spec()
    spec["nodes"][1]["execution_id"] = spec["nodes"][0]["execution_id"]
    with pytest.raises(ContractError, match="duplicate execution_id"):
        build_workflow_projection(spec)


class FakeMultica:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, command: list[str], stdin: str | None) -> dict:
        self.calls.append((command, stdin))
        if command[1:3] == ["issue", "update"]:
            result = {
                "id": command[3],
                "project_id": command[command.index("--project") + 1],
            }
            if "--status" in command:
                result["status"] = command[command.index("--status") + 1]
            return result
        if command[1:4] == ["issue", "metadata", "set"]:
            return {"ok": True}
        if command[1:4] == ["issue", "property", "set"]:
            return []
        raise AssertionError(f"Unexpected command: {command}")


def test_sync_moves_only_parent_to_center_and_classifies_bound_nodes(
    tmp_path: Path,
) -> None:
    input_store = ArtifactStore(tmp_path / "input")
    spec_path = input_store.write_json("workflow.json", workflow_spec())
    config_path = input_store.write_json("config.json", workflow_config())
    multica = FakeMultica()

    result = sync_multica_workflow_center(
        spec_path,
        config_path,
        tmp_path / "output",
        runner=multica,
    )

    update, description = multica.calls[0]
    assert update[1:4] == ["issue", "update", PARENT_ID]
    assert update[update.index("--project") + 1] == INTERNAL_PROJECT_ID
    assert update[update.index("--status") + 1] == "in_review"
    assert description is not None and "15" in description
    assert result["overall_status"] == "needs_action"
    assert result["classified_node_count"] == 4
    metadata_values = [
        command[command.index("--value") + 1]
        for command, _ in multica.calls
        if command[1:4] == ["issue", "metadata", "set"]
        and command[command.index("--key") + 1] == "qa_item_type"
    ]
    assert metadata_values == [
        "workflow",
        "run_execution",
        "node_execution",
        "node_execution",
        "node_execution",
        "human_action",
    ]
    internal_moves = [
        command[3]
        for command, _ in multica.calls
        if command[1:3] == ["issue", "update"]
        and "--status" not in command
        and command[command.index("--project") + 1] == INTERNAL_PROJECT_ID
    ]
    assert internal_moves == [
        "issue-a02",
        "issue-a03",
        "issue-a06",
    ]
    run_updates = [
        command
        for command, _ in multica.calls
        if command[1:4] == ["issue", "update", "issue-run"]
    ]
    assert len(run_updates) == 1
    assert run_updates[0][run_updates[0].index("--status") + 1] == "in_progress"
    action_updates = [
        command
        for command, _ in multica.calls
        if command[1:4] == ["issue", "update", ACTION_ID]
    ]
    assert len(action_updates) == 1
    assert action_updates[0][action_updates[0].index("--status") + 1] == "in_review"
    projection = json.loads(
        (tmp_path / "output" / "workflow-projection.json").read_text(encoding="utf-8")
    )
    assert projection["parent_issue"]["id"] == PARENT_ID


def test_sync_rejects_unconfirmed_parent_update(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "input")
    spec_path = store.write_json("workflow.json", workflow_spec())
    config_path = store.write_json("config.json", workflow_config())

    with pytest.raises(ContractError, match="was not confirmed"):
        sync_multica_workflow_center(
            spec_path,
            config_path,
            tmp_path / "output",
            runner=lambda *_: {"id": PARENT_ID, "status": "todo"},
        )


def test_completed_human_action_keeps_audit_classification(tmp_path: Path) -> None:
    spec = workflow_spec()
    spec["actions"][0]["status"] = "completed"
    spec["nodes"][3]["state"] = "completed"
    store = ArtifactStore(tmp_path / "input")
    spec_path = store.write_json("workflow.json", spec)
    config_path = store.write_json("config.json", workflow_config())
    multica = FakeMultica()

    sync_multica_workflow_center(
        spec_path,
        config_path,
        tmp_path / "output",
        runner=multica,
    )

    action_types = [
        command[command.index("--value") + 1]
        for command, _ in multica.calls
        if command[1:4] == ["issue", "metadata", "set"]
        and command[command.index("--key") + 1] == "qa_item_type"
        and command[4] == ACTION_ID
    ]
    assert action_types == ["human_action"]


def test_projection_rejects_node_bound_to_parent_issue() -> None:
    spec = workflow_spec()
    spec["nodes"][0]["issue_id"] = PARENT_ID

    with pytest.raises(ContractError, match="cannot reuse a parent or Run Issue"):
        build_workflow_projection(spec)


def test_stage_card_shared_issue_is_aggregated_and_synced_once(tmp_path: Path) -> None:
    spec = workflow_spec()
    spec["nodes"] = [
        {
            "execution_id": "A08-run",
            "node_id": "A08",
            "label": "测试设计",
            "stage": 7,
            "state": "completed",
            "completion": "1/1",
            "result_summary": "设计完成",
            "artifact_id": "a08-test-design-ir",
            "artifact_hash": "sha256:a08",
            "stage_card_id": "C3",
            "stage_card_title": "测试设计与审核",
            "issue_id": "issue-a08-execution",
            "issue_identifier": "QAA-A08",
            "stage_issue_id": "issue-c3",
            "stage_issue_identifier": "QAA-C3",
        },
        {
            "execution_id": "G02-run",
            "node_id": "G02",
            "label": "人工审核",
            "stage": 10,
            "state": "waiting_human",
            "completion": "0/1",
            "result_summary": "等待 QA 审核",
            "stage_card_id": "C3",
            "stage_card_title": "测试设计与审核",
            "issue_id": "issue-g02-execution",
            "issue_identifier": "QAA-G02",
            "stage_issue_id": "issue-c3",
            "stage_issue_identifier": "QAA-C3",
        },
    ]
    spec["actions"] = []
    store = ArtifactStore(tmp_path / "input")
    multica = FakeMultica()
    result = sync_multica_workflow_center(
        store.write_json("workflow.json", spec),
        store.write_json("config.json", workflow_config()),
        tmp_path / "output",
        runner=multica,
    )

    card_updates = [
        (command, stdin)
        for command, stdin in multica.calls
        if command[1:4] == ["issue", "update", "issue-c3"]
    ]
    assert len(card_updates) == 1
    command, description = card_updates[0]
    assert command[command.index("--status") + 1] == "in_review"
    assert description is not None
    assert all(
        heading in description
        for heading in (
            "## 目标", "## 输入", "## 执行内容", "## 当前进度",
            "## 产出", "## 异常处理", "## 人工操作", "## 完成标准",
        )
    )
    assert "A08 -> G02" in description
    assert result["stage_card_count"] == 1
    assert result["classified_node_count"] == 2


def test_sync_rejects_conflicting_projection_at_same_revision(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "input")
    spec = workflow_spec()
    spec_path = store.write_json("workflow.json", spec)
    config_path = store.write_json("config.json", workflow_config())
    sync_multica_workflow_center(
        spec_path, config_path, tmp_path / "output", runner=FakeMultica()
    )
    spec["title"] = "同 revision 的冲突标题"
    store.write_json("workflow.json", spec)

    with pytest.raises(ContractError, match="conflicts with another projection"):
        sync_multica_workflow_center(
            spec_path, config_path, tmp_path / "output", runner=FakeMultica()
        )


def test_sync_accepts_newer_projection_revision(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "input")
    spec = workflow_spec()
    spec_path = store.write_json("workflow.json", spec)
    config_path = store.write_json("config.json", workflow_config())
    sync_multica_workflow_center(
        spec_path, config_path, tmp_path / "output", runner=FakeMultica()
    )
    spec["revision"] = 2
    spec["title"] = "新 revision 标题"
    store.write_json("workflow.json", spec)

    result = sync_multica_workflow_center(
        spec_path, config_path, tmp_path / "output", runner=FakeMultica()
    )
    assert result["overall_status"] == "needs_action"


def test_projection_renders_autopilot_execution_audit() -> None:
    spec = workflow_spec()
    spec["autopilot"] = {
        "id": "autopilot-1",
        "status": "active",
        "execution_mode": "run_only",
    }
    spec["autopilot_runs"] = [
        {
            "id": "run-2",
            "status": "completed",
            "triggered_at": "2026-08-11T08:00:00Z",
            "summary": "状态对账完成",
        },
        {
            "id": "run-1",
            "status": "failed",
            "triggered_at": "2026-08-11T07:00:00Z",
            "failure_reason": "runtime authentication failed",
        },
    ]

    projection = build_workflow_projection(spec)
    markdown = render_workflow_center_markdown(projection)

    assert projection["autopilot"]["id"] == "autopilot-1"
    assert projection["autopilot_runs"][0]["id"] == "run-2"
    assert "Autopilot 执行审计" in markdown
    assert "runtime authentication failed" in markdown


def test_projection_rejects_non_run_only_autopilot() -> None:
    spec = workflow_spec()
    spec["autopilot"] = {
        "id": "autopilot-1",
        "status": "active",
        "execution_mode": "create_issue",
    }

    with pytest.raises(ContractError, match="must use run_only"):
        build_workflow_projection(spec)
