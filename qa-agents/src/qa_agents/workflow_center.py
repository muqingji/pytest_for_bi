"""Requirement-level workflow projection and Multica control-plane synchronization."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import subprocess
from typing import Any

from .contracts import content_hash
from .errors import ContractError, InputError, RetryableAgentError
from .security import SecurityPolicy
from .storage import ArtifactStore


CommandRunner = Callable[[list[str], str | None], Any]

NODE_STATES = {
    "not_started",
    "queued",
    "running",
    "waiting_human",
    "blocked",
    "failed",
    "completed",
    "skipped",
    "cancelled",
    "superseded",
}
TERMINAL_NODE_STATES = {"completed", "skipped", "cancelled", "superseded"}
WORKFLOW_STATUS_LABELS = {
    "blocked": "阻塞",
    "needs_action": "待我处理",
    "running": "系统运行中",
    "queued": "排队中",
    "completed": "已完成",
    "cancelled": "已取消",
}
NODE_STATUS_LABELS = {
    "not_started": "未开始",
    "queued": "排队中",
    "running": "运行中",
    "waiting_human": "等待人工",
    "blocked": "阻塞",
    "failed": "失败",
    "completed": "已完成",
    "skipped": "已跳过",
    "cancelled": "已取消",
    "superseded": "已替代",
}
MULTICA_STATUS = {
    "blocked": "blocked",
    "needs_action": "in_review",
    "running": "in_progress",
    "queued": "todo",
    "completed": "done",
    "cancelled": "cancelled",
}
RUN_MULTICA_STATUS = {
    **MULTICA_STATUS,
    # The Run wrapper is operational state. Marking it in_review makes Multica's
    # stage automation complete its active human-gate child.
    "needs_action": "in_progress",
}

NODE_MULTICA_STATUS = {
    "not_started": "backlog",
    "queued": "todo",
    "running": "in_progress",
    "waiting_human": "in_review",
    "blocked": "blocked",
    "failed": "blocked",
    "completed": "done",
    "skipped": "done",
    "cancelled": "cancelled",
    "superseded": "cancelled",
}

SERVER_NODE_DETAILS = {
    "INPUT-FREEZE": "冻结需求、技术方案和 ChangeSet，校验输入完整性与权限边界。",
    "N00": "按触发类型和组织策略确定工作流模板、执行深度与节点路由。",
    "A02": "把冻结需求拆成原子需求、验收条件、歧义和需要人工确认的事项。",
    "A03": "分析技术方案、组件依赖、可测性缺口、阻塞项和测试能力边界。",
    "A05": "分析后端 ChangeSet 的事实、影响范围、变更归属和实现偏差。",
    "A06": "对需求、技术方案与后端变更做映射对齐，输出遗漏、冲突和未实现项。",
    "G01": "人工审核测试范围、风险等级、必测内容和需求口径。",
    "N24": "确定性生成测试策略、风险等级、必测层级与 Gate 策略。",
    "A08": "按冻结需求和测试策略设计 Test Case IR 与覆盖矩阵。",
    "A09": "审查 Oracle 规则、测试防范覆盖、遗漏和修正建议。",
    "N04": "确定性校验 Test Case IR 的结构、来源、Oracle 和覆盖规则。",
    "G02": "人工审核 Test Case IR 的预期结果和测试覆盖。",
    "N25": "把父级 Case 编译成可执行子 Case，并建立父子与能力映射。",
    "A11": "审查父子 Case 拆分后的覆盖完整性、冲突和遗漏。",
    "N26": "按资产、风险和策略确定本次要执行的测试 Case。",
    "N15": "编译生成、更新、直接执行、人工执行或跳过的执行计划。",
    "A14": "生成后端 API、集成和功能自动化测试候选。",
    "A15": "基于冻结 OpenAPI 生成契约自动化测试候选。",
    "A22": "从 Case 提取测试数据意图、业务状态和资源目标。",
    "A18-BE": "独立审查后端自动化候选的断言、隔离、清理和权限。",
    "A18-CT": "独立审查契约自动化候选的 Schema、操作和兼容判断。",
    "N27": "校验测试数据计划的安全性、可复现性和能力边界。",
    "N05": "对自动化候选执行格式、lint、编译和安全扫描。",
    "G03": "人工审核自动化代码质量、风险和发布边界。",
    "N07": "检查测试环境、账号、数据和资源是否满足执行条件。",
    "N08": "受控执行自动化测试并收集运行证据。",
    "N17": "执行人工与探索测试，并记录过程和结果。",
    "N10": "按重试预算处理环境失败，给出继续、暂停或阻塞结论。",
    "N18": "采集自动化与人工执行的运行质量信号。",
    "N09": "标准化执行证据并对失败做聚类和根因归纳。",
    "N20": "跨运行识别和合并重复缺陷。",
    "N11": "根据证据、缺陷和风险确定性生成质量结论。",
    "N19": "审计质量豁免申请及授权范围。",
    "N12": "发布质量报告并留存发布证据。",
    "N13": "记录报告反馈并归档后续动作。",
    "N23": "按授权执行上线后验证并记录审计结论。",
}


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except OSError as error:
        raise InputError(f"Required {label} cannot be read: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be a JSON object")
    return value


def _required_text(value: Mapping[str, Any], field: str, label: str) -> str:
    result = str(value.get(field, "")).strip()
    if not result:
        raise ContractError(f"{label} requires {field}")
    return result


def _validated_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    if spec.get("schema_version") != "requirement-workflow/1.0":
        raise ContractError("Requirement workflow schema_version is invalid")
    for field in (
        "workflow_id",
        "requirement_id",
        "workflow_run_id",
        "workflow_definition_version",
        "source_snapshot_id",
        "title",
    ):
        _required_text(spec, field, "Requirement workflow")
    revision = spec.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise ContractError("Requirement workflow revision must be a positive integer")
    parent = spec.get("parent_issue")
    if not isinstance(parent, Mapping):
        raise ContractError("Requirement workflow parent_issue is missing")
    _required_text(parent, "id", "Requirement workflow parent_issue")
    _required_text(parent, "identifier", "Requirement workflow parent_issue")
    run_issue = spec.get("run_issue")
    parent_issue_id = str(parent["id"])
    run_issue_id: str | None = None
    if run_issue is not None:
        if not isinstance(run_issue, Mapping):
            raise ContractError("Requirement workflow run_issue must be an object")
        run_issue_id = _required_text(run_issue, "id", "Requirement workflow run_issue")
        _required_text(run_issue, "identifier", "Requirement workflow run_issue")
        if run_issue_id == parent_issue_id:
            raise ContractError("Requirement workflow run_issue cannot reuse the parent Issue")
    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ContractError("Requirement workflow requires at least one node")
    execution_ids: set[str] = set()
    bound_issue_cards: dict[str, str] = {}
    normalized_nodes: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            raise ContractError(f"Requirement workflow node {index} must be an object")
        execution_id = _required_text(node, "execution_id", f"Workflow node {index}")
        if execution_id in execution_ids:
            raise ContractError(f"Requirement workflow has duplicate execution_id: {execution_id}")
        execution_ids.add(execution_id)
        state = _required_text(node, "state", f"Workflow node {execution_id}")
        if state not in NODE_STATES:
            raise ContractError(f"Workflow node {execution_id} has invalid state: {state}")
        stage = node.get("stage")
        if not isinstance(stage, int) or stage < 1:
            raise ContractError(f"Workflow node {execution_id} stage must be a positive integer")
        issue_id = str(node.get("issue_id", "")).strip()
        if issue_id:
            if issue_id in {parent_issue_id, run_issue_id}:
                raise ContractError(
                    f"Workflow node {execution_id} cannot reuse a parent or Run Issue"
                )
            if issue_id in bound_issue_cards:
                raise ContractError(f"Requirement workflow has duplicate node issue_id: {issue_id}")
            bound_issue_cards[issue_id] = str(node.get("stage_card_id", ""))
        normalized_nodes.append(dict(node))
    actions = spec.get("actions", [])
    if not isinstance(actions, list):
        raise ContractError("Requirement workflow actions must be a list")
    action_ids: set[str] = set()
    normalized_actions: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            raise ContractError(f"Requirement workflow action {index} must be an object")
        action_id = _required_text(action, "action_id", f"Workflow action {index}")
        if action_id in action_ids:
            raise ContractError(f"Requirement workflow has duplicate action_id: {action_id}")
        action_ids.add(action_id)
        status = _required_text(action, "status", f"Workflow action {action_id}")
        if status not in {"open", "completed", "cancelled"}:
            raise ContractError(f"Workflow action {action_id} status is invalid")
        for field in ("title", "owner_member_id"):
            _required_text(action, field, f"Workflow action {action_id}")
        item_count = action.get("item_count")
        if not isinstance(item_count, int) or item_count < 1:
            raise ContractError(f"Workflow action {action_id} item_count must be positive")
        approval_items = action.get("approval_items")
        if approval_items is not None:
            if not isinstance(approval_items, list):
                raise ContractError(f"Workflow action {action_id} approval_items must be a list")
            for item_index, approval in enumerate(approval_items):
                if not isinstance(approval, Mapping):
                    raise ContractError(
                        f"Workflow action {action_id} approval_items[{item_index}] must be an object"
                    )
                for field in ("id", "title", "summary"):
                    _required_text(
                        approval,
                        field,
                        f"Workflow action {action_id} approval_items[{item_index}]",
                    )
        normalized_actions.append(dict(action))
    run_history = spec.get("run_history", [])
    if not isinstance(run_history, list) or not all(
        isinstance(item, Mapping) for item in run_history
    ):
        raise ContractError("Requirement workflow run_history must be a list of objects")
    for index, item in enumerate(run_history):
        for field in ("workflow_run_id", "status", "summary"):
            _required_text(item, field, f"Workflow run history {index}")
    autopilot = spec.get("autopilot")
    if autopilot is not None:
        if not isinstance(autopilot, Mapping):
            raise ContractError("Requirement workflow autopilot must be an object")
        for field in ("id", "status", "execution_mode"):
            _required_text(autopilot, field, "Requirement workflow autopilot")
        if autopilot.get("execution_mode") != "run_only":
            raise ContractError("Requirement workflow autopilot must use run_only")
    autopilot_runs = spec.get("autopilot_runs", [])
    if not isinstance(autopilot_runs, list) or not all(
        isinstance(item, Mapping) for item in autopilot_runs
    ):
        raise ContractError("Requirement workflow autopilot_runs must be a list of objects")
    for index, item in enumerate(autopilot_runs):
        for field in ("id", "status", "triggered_at"):
            _required_text(item, field, f"Autopilot run {index}")
    return {
        **dict(spec),
        "nodes": normalized_nodes,
        "actions": normalized_actions,
        "run_history": [dict(item) for item in run_history],
        "autopilot": dict(autopilot) if isinstance(autopilot, Mapping) else None,
        "autopilot_runs": [dict(item) for item in autopilot_runs],
    }


def _derive_status(nodes: list[Mapping[str, Any]], actions: list[Mapping[str, Any]]) -> str:
    states = {str(node["state"]) for node in nodes}
    if states & {"blocked", "failed"}:
        return "blocked"
    if any(action.get("status") == "open" for action in actions):
        return "needs_action"
    if states & {"running", "waiting_human"}:
        return "running"
    if states & {"queued", "not_started"}:
        return "queued"
    if states <= {"cancelled", "superseded", "skipped"}:
        return "cancelled"
    if states <= TERMINAL_NODE_STATES:
        return "completed"
    raise ContractError("Requirement workflow state cannot be derived")


def build_workflow_projection(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Build the single user-facing state from node executions and human actions."""

    value = _validated_spec(spec)
    nodes = value["nodes"]
    actions = value["actions"]
    status = _derive_status(nodes, actions)
    completed = sum(node["state"] in TERMINAL_NODE_STATES for node in nodes)
    open_actions = [dict(action) for action in actions if action["status"] == "open"]
    active_nodes = [
        dict(node)
        for node in nodes
        if node["state"] in {"running", "waiting_human", "blocked", "failed"}
    ]
    if not active_nodes and status == "queued":
        active_nodes = [
            dict(node) for node in nodes if node["state"] in {"queued", "not_started"}
        ][:1]
    core = {
        "schema_version": "requirement-workflow-projection/1.0",
        "workflow_id": value["workflow_id"],
        "requirement_id": value["requirement_id"],
        "workflow_run_id": value["workflow_run_id"],
        "workflow_definition_version": value["workflow_definition_version"],
        "revision": value["revision"],
        "source_snapshot_id": value["source_snapshot_id"],
        "title": value["title"],
        "parent_issue": dict(value["parent_issue"]),
        "run_issue": dict(value["run_issue"]) if value.get("run_issue") else None,
        "overall_status": status,
        "overall_status_label": WORKFLOW_STATUS_LABELS[status],
        "multica_status": MULTICA_STATUS[status],
        "progress": {
            "completed": completed,
            "total": len(nodes),
            "percent": round(completed * 100 / len(nodes)),
        },
        "current_nodes": active_nodes,
        "open_actions": open_actions,
        "action_required": bool(open_actions),
        "action_count": sum(action["item_count"] for action in open_actions),
        "nodes": nodes,
        "actions": actions,
        "run_history": value["run_history"],
        "autopilot": value["autopilot"],
        "autopilot_runs": value["autopilot_runs"],
    }
    core["projection_hash"] = content_hash(core)
    return core


def render_workflow_center_markdown(projection: Mapping[str, Any]) -> str:
    """Render one requirement as a compact workflow cockpit."""

    if projection.get("schema_version") != "requirement-workflow-projection/1.0":
        raise ContractError("Expected a requirement workflow projection")
    progress = projection["progress"]
    lines = [
        f"# {projection['requirement_id']} {projection['title']}",
        "",
        "## 工作流概览",
        "",
        f"- 总状态：**{projection['overall_status_label']}**",
        f"- 完成进度：`{progress['completed']}/{progress['total']}`（{progress['percent']}%）",
        f"- 当前运行：`{projection['workflow_run_id']}`",
        f"- 流程版本：`{projection['workflow_definition_version']}`",
        f"- 来源快照：`{projection['source_snapshot_id']}`",
        "",
    ]
    autopilot = projection.get("autopilot")
    if isinstance(autopilot, Mapping):
        autopilot_runs = projection.get("autopilot_runs", [])
        latest = autopilot_runs[0] if autopilot_runs else None
        latest_line = "- 最近执行：尚未触发"
        if latest:
            latest_line = f"- 最近执行：`{latest['status']}`（`{latest['id']}`）"
        lines.extend(
            [
                "## Autopilot",
                "",
                f"- Autopilot ID：`{autopilot['id']}`",
                f"- 状态：`{autopilot['status']}`",
                f"- 模式：`{autopilot['execution_mode']}`",
                latest_line,
                "",
            ]
        )
    open_actions = projection.get("open_actions", [])
    if open_actions:
        lines.extend(["## 需要你处理", ""])
        for action in open_actions:
            issue = str(action.get("issue_identifier", "")).strip()
            issue_text = f"（{issue}）" if issue else ""
            lines.extend(
                [
                    f"### {action['title']}{issue_text}",
                    "",
                    f"- 待处理：`{action['item_count']}` 项",
                    f"- 当前 Gate：`{action.get('gate_id', 'human')}`",
                    f"- 摘要：{action.get('summary', '请打开审核入口处理。')}",
                    "",
                ]
            )
            approval_items = action.get("approval_items")
            if approval_items:
                lines.extend([f"#### 审批项（{len(approval_items)}）", ""])
                for index, approval in enumerate(approval_items, start=1):
                    lines.extend(_approval_lines(approval, index))
                    lines.append("")
            else:
                lines.append("- 审批项：请打开审核入口查看具体审批项。")
                lines.append("")
    else:
        lines.extend(["## 需要你处理", "", "当前没有需要你处理的事项。", ""])

    lines.extend(
        [
            "## 节点进度",
            "",
            "| 阶段 | 节点 | 状态 | 完成情况 | 结果 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for node in projection["nodes"]:
        grouped[int(node["stage"])].append(node)
    for stage in sorted(grouped):
        for node in grouped[stage]:
            issue = str(node.get("issue_identifier", "")).strip()
            node_label = str(node.get("label") or node.get("node_id") or node["execution_id"])
            if issue:
                node_label = f"{node_label}（{issue}）"
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(stage),
                        node_label.replace("|", "/"),
                        NODE_STATUS_LABELS[str(node["state"])],
                        str(node.get("completion", "-")),
                        str(node.get("result_summary", "-")).replace("|", "/").replace("\n", " "),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
        ]
    )
    history = projection.get("run_history", [])
    if history:
        lines.extend(
            [
                "## 历史运行",
                "",
                "| Workflow Run | 状态 | 结果 |",
                "| --- | --- | --- |",
            ]
        )
        for item in history:
            lines.append(
                f"| `{item['workflow_run_id']}` | {item['status']} | "
                f"{str(item['summary']).replace('|', '/')} |"
            )
        lines.append("")
    autopilot_runs = projection.get("autopilot_runs", [])
    if autopilot_runs:
        lines.extend(
            [
                "## Autopilot 执行审计",
                "",
                "| Run ID | 状态 | 触发时间 | 结果 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in autopilot_runs:
            detail = str(item.get("summary") or item.get("failure_reason") or "-")
            lines.append(
                f"| `{item['id']}` | {item['status']} | `{item['triggered_at']}` | "
                f"{detail.replace('|', '/').replace(chr(10), ' ')} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 审计绑定",
            "",
            f"- Workflow ID：`{projection['workflow_id']}`",
            f"- Parent Issue：`{projection['parent_issue']['identifier']}`",
            f"- Projection：`{projection['projection_hash']}`",
            "",
            "节点任务和重跑记录保留在内部执行项目；本卡只展示需求级总体状态、进度和人工事项。",
        ]
    )
    return "\n".join(lines)


def _default_runner(command: list[str], stdin: str | None) -> Any:
    completed = subprocess.run(
        command,
        input=stdin,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RetryableAgentError(f"Multica workflow-center command failed: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ContractError("Multica workflow-center command returned invalid JSON") from error


def _run_object(
    runner: CommandRunner, command: list[str], stdin: str | None, label: str
) -> Mapping[str, Any]:
    result = runner(command, stdin)
    if not isinstance(result, Mapping):
        raise ContractError(f"Multica {label} did not return an object")
    return result


def _metadata_commands(
    issue_id: str, metadata: Mapping[str, str], workspace_id: str
) -> list[list[str]]:
    return [
        [
            "multica",
            "issue",
            "metadata",
            "set",
            issue_id,
            "--key",
            key,
            "--value",
            value,
            "--type",
            "string",
            "--output",
            "json",
            "--workspace-id",
            workspace_id,
        ]
        for key, value in metadata.items()
    ]


def _property_command(
    issue_id: str, name: str, value: str, workspace_id: str
) -> list[str]:
    return [
        "multica",
        "issue",
        "property",
        "set",
        issue_id,
        "--name",
        name,
        "--value",
        value,
        "--output",
        "json",
        "--workspace-id",
        workspace_id,
    ]


def _ensure_issue_project(
    runner: CommandRunner,
    issue_id: str,
    project_id: str,
    workspace_id: str,
) -> None:
    issue = _run_object(
        runner,
        [
            "multica",
            "issue",
            "update",
            issue_id,
            "--project",
            project_id,
            "--output",
            "json",
            "--workspace-id",
            workspace_id,
        ],
        None,
        "internal Issue project update",
    )
    if issue.get("id") != issue_id or issue.get("project_id") != project_id:
        raise ContractError("Workflow center internal Issue project update was not confirmed")


def _ensure_run_issue_state(
    runner: CommandRunner,
    issue_id: str,
    project_id: str,
    status: str,
    workspace_id: str,
) -> None:
    """Keep the current Run wrapper aligned with its requirement projection."""

    issue = _run_object(
        runner,
        [
            "multica",
            "issue",
            "update",
            issue_id,
            "--project",
            project_id,
            "--status",
            status,
            "--output",
            "json",
            "--workspace-id",
            workspace_id,
        ],
        None,
        "Run Issue state update",
    )
    if (
        issue.get("id") != issue_id
        or issue.get("project_id") != project_id
        or issue.get("status") != status
    ):
        raise ContractError("Workflow center Run Issue state update was not confirmed")


def _stage_card_status(nodes: list[Mapping[str, Any]]) -> str:
    states = {str(node.get("state", "")) for node in nodes}
    if states & {"queued", "running"}:
        return "in_progress"
    if "waiting_human" in states:
        return "in_review"
    if states & {"blocked", "failed"}:
        return "blocked"
    if states and states <= TERMINAL_NODE_STATES:
        if states <= {"cancelled", "superseded"}:
            return "cancelled"
        return "done"
    return "backlog"


_HUMAN_ISSUE_TITLES = {
    "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE": "预期结果无法解析",
    "LOCALE_NAME_PRECEDENCE_FIXTURE_CONFLICT": "中英文测试数据冲突",
    "RULE_CONFLICT": "规则冲突",
    "MISSING_EXPECTATION": "缺少期望值",
    "AMBIGUOUS_REQUIREMENT": "需求表述歧义",
    "COVERAGE_GAP": "覆盖缺口",
    "BLOCKING_GAP": "阻塞性缺口",
}

_HUMAN_CATEGORY_LABELS = {
    "oracle": "Oracle 期望值",
    "test_data": "测试数据",
    "ambiguity": "需求歧义",
    "ambiguities": "需求歧义",
    "coverage": "覆盖缺口",
    "conflict": "规则冲突",
    "missing": "缺失项",
    "blocker": "阻塞项",
    "question": "待确认事项",
    "needs_human": "待确认事项",
}

_RESULT_SUMMARY_LABELS = {
    "completed": "已完成",
    "completed_with_gaps": "已完成，存在缺口（由下游审查修正）",
    "needs_human": "需人工确认",
    "accepted": "已验收",
}


def _first_sentence(text: str, limit: int = 120) -> str:
    """Keep the leading sentence so long technical messages stay readable."""
    if len(text) <= limit:
        return text
    for separator in ("。", "；", "；", "\n", ". "):
        position = text.find(separator)
        if 0 < position <= limit:
            return text[: position + len(separator)]
    return text[:limit].rstrip() + "…"


def _issue_plain_problem(approval: Mapping[str, Any]) -> str:
    """Human-friendly one-liner for known issue codes; empty when unknown."""
    issue_code = str(approval.get("issue_code") or "").strip()
    case_id = str(approval.get("case_id") or "").strip()
    expected_id = str(approval.get("expected_id") or "").strip()
    if issue_code == "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE":
        return (
            f"用例 `{expected_id or 'EXP-*'}` 的预期结果指向了一个不存在的字段路径，"
            "自动执行时拿不到明确期望值，这条用例目前无法完成校验。"
        )
    if issue_code == "LOCALE_NAME_PRECEDENCE_FIXTURE_CONFLICT":
        return (
            f"用例 `{case_id or 'TC-*'}` 同时用中英文执行，但测试数据固定写死了中文名称，"
            "英文场景也会取到中文结果，和期望的英文名称对不上。"
        )
    return ""


def _approval_title(approval: Mapping[str, Any]) -> str:
    human_title = str(approval.get("human_title") or "").strip()
    if human_title:
        return human_title
    issue_code = str(approval.get("issue_code") or "").strip()
    if issue_code:
        category = str(approval.get("category") or "").strip()
        label = _HUMAN_CATEGORY_LABELS.get(
            category.lower(), category or "问题"
        )
        return _HUMAN_ISSUE_TITLES.get(issue_code, f"{label}问题（{issue_code}）")
    category = str(approval.get("category") or approval.get("title") or "待确认").strip()
    return _HUMAN_CATEGORY_LABELS.get(category.lower(), category)


def _approval_lines(approval: Mapping[str, Any], index: int) -> list[str]:
    lines = [f"{index}. **{_approval_title(approval)}**（`{approval['id']}`）"]
    problem = str(approval.get("plain_summary") or "").strip()
    if not problem:
        problem = _issue_plain_problem(approval)
    if not problem:
        summary = str(approval.get("summary") or "").strip()
        if summary:
            problem = _first_sentence(summary)
    if problem:
        lines.append(f"   - 问题：{problem}")
    recommendation = str(approval.get("recommendation") or "").strip()
    if recommendation:
        lines.append(f"   - 建议修正：{recommendation}")
    confirm_action = str(approval.get("confirm_action") or "").strip()
    if confirm_action:
        lines.append(f"   - 需要确认：{confirm_action}")
    requirement_ids = approval.get("requirement_ids") or []
    if requirement_ids:
        lines.append("   - 涉及需求：" + "、".join(f"`{value}`" for value in requirement_ids))
    return lines


def _render_stage_card_markdown(
    card_id: str, title: str, nodes: list[Mapping[str, Any]]
) -> str:
    counts: dict[str, int] = defaultdict(int)
    for node in nodes:
        counts[str(node.get("state", "not_started"))] += 1
    active = [
        str(node.get("node_id") or node.get("execution_id"))
        for node in nodes
        if node.get("state") in {"queued", "running", "waiting_human", "blocked", "failed"}
    ]
    artifacts: list[str] = []
    for node in nodes:
        if not (node.get("artifact_id") and node.get("artifact_hash")):
            continue
        label = str(node.get("label") or node.get("node_id") or "")
        state_label = NODE_STATUS_LABELS.get(
            str(node.get("state")), str(node.get("state"))
        )
        summary = str(node.get("result_summary") or "").strip()
        if node.get("state") == "waiting_human":
            summary = "待人工授权修正，见下方人工操作"
        elif summary in _RESULT_SUMMARY_LABELS:
            summary = _RESULT_SUMMARY_LABELS[summary]
        line = f"- `{node.get('artifact_id')}`（{label} · {state_label}）"
        if summary:
            line += f"：{summary}"
        line += f"  `{node.get('artifact_hash')}`"
        artifacts.append(line)
    human_entries = {
        str(entry.get("issue_identifier") or entry.get("issue_id") or "").strip()
        for node in nodes
        if node.get("state") == "waiting_human"
        if isinstance(node.get("human_action_entry"), Mapping)
        for entry in [node["human_action_entry"]]
        if str(entry.get("issue_identifier") or entry.get("issue_id") or "").strip()
    }
    failures = []
    for node in nodes:
        if node.get("state") not in {"blocked", "failed"}:
            continue
        line = f"- `{node.get('node_id')}`：{node.get('result_summary', '等待处理')}"
        if human_entries:
            line += f"（处理入口：{'、'.join(f'`{entry}`' for entry in sorted(human_entries))}，见下方人工操作）"
        failures.append(line)
    human_lines: list[str] = []
    for node in nodes:
        if node.get("state") != "waiting_human":
            continue
        approval_items = node.get("approval_items") or []
        if approval_items:
            label = str(node.get("label") or "").strip()
            label_text = f"（{label}）" if label else ""
            if isinstance(node.get("human_action_entry"), Mapping):
                human_lines.append(
                    f"- 来源：`{node.get('node_id')}`{label_text} 审查发现 "
                    f"{len(approval_items)} 个问题，需你决策是否授权修正。"
                )
            else:
                human_lines.append(
                    f"- 来源：`{node.get('node_id')}`{label_text}，共 "
                    f"{len(approval_items)} 个待确认事项，请逐条确认后继续。"
                )
            for index, approval in enumerate(approval_items, start=1):
                human_lines.extend(_approval_lines(approval, index))
        else:
            human_lines.append(
                f"- 审核 `{node.get('node_id')}`：{node.get('result_summary', '请完成审核')}"
            )
            human_lines.append("  - 审批项：请打开审核入口查看具体审批项。")
        entry = node.get("human_action_entry")
        if isinstance(entry, Mapping):
            identifier = str(entry.get("issue_identifier") or entry.get("issue_id") or "").strip()
            if identifier:
                status = str(entry.get("status") or "待处理")
                human_lines.append(f"- 操作：打开 `{identifier}`（人工修正 Issue，状态 {status}）：")
                human_lines.append(
                    "  - 置为 **done**：授权修正，系统自动修改用例并重新校验，流程自动继续。"
                )
                human_lines.append(
                    "  - 置为 **cancelled**：不修正，终止当前流程。"
                )
    human = human_lines
    progress = "、".join(
        f"{NODE_STATUS_LABELS.get(state, state)} {count}"
        for state, count in sorted(counts.items())
    )
    node_list = " -> ".join(str(node.get("node_id")) for node in nodes)
    node_details = [
        f"- `{node.get('node_id')}`："
        f"{SERVER_NODE_DETAILS.get(str(node.get('node_id')), str(node.get('label', '')))}"
        for node in nodes
    ]
    return "\n".join(
        [
            f"# {card_id} {title}",
            "",
            "## 目标",
            f"完成“{title}”阶段并保留全部内部节点审计。",
            "",
            "## 输入",
            "上游已验收 Artifact、当前需求快照和本阶段节点依赖。",
            "",
            "## 执行内容",
            node_list,
            "",
            *node_details,
            "",
            "## 当前进度",
            f"共 {len(nodes)} 个内部节点：{progress}。",
            f"当前节点：{'、'.join(active) if active else '无'}。",
            "",
            "## 产出",
            *(artifacts or ["暂无已验收 Artifact。"]),
            "",
            "## 异常处理",
            *(failures or ["当前无阻塞异常；回流和重试只更新本卡。"]),
            "",
            "## 人工操作",
            *(human or ["当前无需人工操作。"]),
            "",
            "## 完成标准",
            "本阶段所有已路由节点完成或按策略跳过；人工 Gate 必须具有有效 Decision Artifact。",
        ]
    )


def _stage_cards(projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    titles: dict[str, str] = {}
    issues: dict[str, tuple[str, str]] = {}
    for node in projection["nodes"]:
        card_id = str(node.get("stage_card_id", "")).strip()
        if not card_id:
            continue
        grouped[card_id].append(node)
        titles[card_id] = str(node.get("stage_card_title") or card_id)
        issue_id = str(node.get("stage_issue_id", "")).strip()
        if issue_id:
            issues[card_id] = (issue_id, str(node.get("stage_issue_identifier", "")))
    cards: list[dict[str, Any]] = []
    upstream_blocker = ""
    for card_id, nodes in sorted(grouped.items()):
        status = _stage_card_status(nodes)
        description = _render_stage_card_markdown(card_id, titles[card_id], nodes)
        if upstream_blocker:
            status = "backlog"
            description += (
                "\n\n## 上游阻塞\n"
                f"等待 `{upstream_blocker}` 解除；本阶段尚未形成可验收完成态。"
            )
        cards.append({
            "stage_card_id": card_id,
            "title": titles[card_id],
            "nodes": nodes,
            "status": status,
            "description": description,
            "issue_id": issues.get(card_id, ("", ""))[0],
            "issue_identifier": issues.get(card_id, ("", ""))[1],
        })
        if status == "blocked" and not upstream_blocker:
            upstream_blocker = card_id
    return cards


@contextmanager
def _workflow_sync_lock(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / ".workflow-center.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _assert_monotonic_projection(output_dir: Path, projection: Mapping[str, Any]) -> None:
    state_path = output_dir / "workflow-center-sync-state.json"
    if not state_path.exists():
        return
    state = _read_object(state_path, "workflow center sync state")
    if state.get("schema_version") != "workflow-center-sync-state/1.0":
        raise ContractError("Workflow center sync state schema_version is invalid")
    if state.get("workflow_id") != projection["workflow_id"]:
        raise ContractError("Workflow center output directory belongs to another workflow")
    previous_revision = state.get("revision")
    if not isinstance(previous_revision, int):
        raise ContractError("Workflow center sync state revision is invalid")
    revision = int(projection["revision"])
    if revision < previous_revision:
        raise ContractError("Workflow center projection revision would move backwards")
    if (
        revision == previous_revision
        and state.get("projection_hash") != projection["projection_hash"]
    ):
        raise ContractError("Workflow center revision conflicts with another projection")


def _sync_multica_workflow_center_unlocked(
    spec_path: Path,
    config_path: Path,
    output_dir: Path,
    *,
    runner: CommandRunner | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Project one requirement workflow into its parent Issue and classify bound nodes."""

    security = security or SecurityPolicy()
    spec = _read_object(spec_path, "requirement workflow spec")
    config = _read_object(config_path, "workflow center config")
    if config.get("schema_version") != "multica-workflow-center/1.0":
        raise ContractError("Workflow center config schema_version is invalid")
    for field in ("workspace_id", "workflow_project_id", "internal_project_id"):
        _required_text(config, field, "Workflow center config")
    properties = config.get("properties")
    if not isinstance(properties, Mapping):
        raise ContractError("Workflow center property mapping is missing")
    for field in ("item_type", "workflow_status", "progress", "current_node", "action_required"):
        _required_text(properties, field, "Workflow center properties")
    security.assert_no_secret_values(spec)
    security.assert_no_secret_values(config)
    projection = build_workflow_projection(spec)
    markdown = render_workflow_center_markdown(projection)
    security.assert_no_secret_values(projection)
    store = ArtifactStore(output_dir)
    store.write_json("workflow-projection.json", projection)
    store.write_text("workflow-center.md", markdown)

    active_runner = runner or _default_runner
    workspace_id = str(config["workspace_id"])
    parent_id = str(projection["parent_issue"]["id"])
    parent = _run_object(
        active_runner,
        [
            "multica",
            "issue",
            "update",
            parent_id,
            "--description-stdin",
            "--title",
            f"[{projection['requirement_id']}] {projection['title']}",
            "--project",
            str(config["internal_project_id"]),
            "--status",
            str(projection["multica_status"]),
            "--output",
            "json",
            "--workspace-id",
            workspace_id,
        ],
        markdown,
        "parent Issue update",
    )
    if parent.get("id") != parent_id or parent.get("status") != projection["multica_status"]:
        raise ContractError("Workflow center parent Issue update was not confirmed")

    current_node = ", ".join(
        str(node.get("node_id") or node["execution_id"])
        for node in projection["current_nodes"]
    ) or "-"
    parent_metadata = {
        "qa_item_type": "workflow",
        "qa_workflow_id": str(projection["workflow_id"]),
        "qa_requirement_id": str(projection["requirement_id"]),
        "qa_active_run_id": str(projection["workflow_run_id"]),
        "qa_workflow_status": str(projection["overall_status"]),
        "qa_action_required": "true" if projection["action_required"] else "false",
        "qa_projection_hash": str(projection["projection_hash"]),
    }
    for command in _metadata_commands(parent_id, parent_metadata, workspace_id):
        active_runner(command, None)
    parent_properties = {
        str(properties["item_type"]): "需求工作流",
        str(properties["workflow_status"]): str(projection["overall_status_label"]),
        str(properties["progress"]): (
            f"{projection['progress']['completed']}/{projection['progress']['total']}"
        ),
        str(properties["current_node"]): current_node,
        str(properties["action_required"]): (
            "true" if projection["action_required"] else "false"
        ),
    }
    for name, value in parent_properties.items():
        active_runner(_property_command(parent_id, name, value, workspace_id), None)

    classified_nodes = 0
    internal_project_id = str(config["internal_project_id"])
    run_project_id = str(config.get("run_project_id") or internal_project_id)
    run_issue = projection.get("run_issue")
    if isinstance(run_issue, Mapping):
        run_issue_id = str(run_issue["id"])
        _ensure_run_issue_state(
            active_runner,
            run_issue_id,
            run_project_id,
            RUN_MULTICA_STATUS[str(projection["overall_status"])],
            workspace_id,
        )
        run_metadata = {
            "qa_item_type": "run_execution",
            "qa_workflow_id": str(projection["workflow_id"]),
            "qa_workflow_run_id": str(projection["workflow_run_id"]),
            "qa_visible_in_workflow_center": "false",
        }
        for command in _metadata_commands(run_issue_id, run_metadata, workspace_id):
            active_runner(command, None)
        active_runner(
            _property_command(
                run_issue_id, str(properties["item_type"]), "内部节点", workspace_id
            ),
            None,
        )
    stage_cards = _stage_cards(projection)
    if not stage_cards:
        action_issue_ids = {
            str(action.get("issue_id"))
            for action in projection["actions"]
            if action.get("issue_id")
        }
        for node in projection["nodes"]:
            issue_id = str(node.get("issue_id", "")).strip()
            if not issue_id:
                continue
            item_type = "human_action" if issue_id in action_issue_ids else "node_execution"
            status = NODE_MULTICA_STATUS[str(node["state"])]
            if item_type == "human_action":
                action = next(
                    item for item in projection["actions"]
                    if str(item.get("issue_id")) == issue_id
                )
                status = "in_review" if action["status"] == "open" else "done"
            else:
                _ensure_issue_project(
                    active_runner, issue_id, internal_project_id, workspace_id
                )
            _ensure_run_issue_state(
                active_runner, issue_id, internal_project_id, status, workspace_id
            )
            metadata = {
                "qa_item_type": item_type,
                "qa_workflow_id": str(projection["workflow_id"]),
                "qa_workflow_run_id": str(projection["workflow_run_id"]),
                "qa_node_id": str(node.get("node_id") or node["execution_id"]),
                "qa_visible_in_workflow_center": "false",
            }
            for command in _metadata_commands(issue_id, metadata, workspace_id):
                active_runner(command, None)
            item_label = "人工处理" if item_type == "human_action" else "内部节点"
            active_runner(
                _property_command(
                    issue_id, str(properties["item_type"]), item_label, workspace_id
                ),
                None,
            )
            classified_nodes += 1
    if stage_cards:
        action_issue_ids = {
            str(action.get("issue_id"))
            for action in projection["actions"]
            if action.get("issue_id")
        }
        for node in projection["nodes"]:
            issue_id = str(node.get("issue_id", "")).strip()
            if not issue_id:
                continue
            item_type = "human_action" if issue_id in action_issue_ids else "node_execution"
            node_state = str(node["state"])
            status = "in_progress" if node_state == "queued" else NODE_MULTICA_STATUS[node_state]
            _ensure_run_issue_state(
                active_runner, issue_id, run_project_id, status, workspace_id
            )
            metadata = {
                "qa_item_type": item_type,
                "qa_workflow_id": str(projection["workflow_id"]),
                "qa_workflow_run_id": str(projection["workflow_run_id"]),
                "qa_node_id": str(node.get("node_id") or node["execution_id"]),
                "qa_stage_card_id": str(node.get("stage_card_id", "")),
                "qa_visible_in_workflow_center": "false",
            }
            for command in _metadata_commands(issue_id, metadata, workspace_id):
                active_runner(command, None)
            active_runner(
                _property_command(
                    issue_id,
                    str(properties["item_type"]),
                    "人工处理" if item_type == "human_action" else "内部节点",
                    workspace_id,
                ),
                None,
            )
            classified_nodes += 1
    for card in stage_cards:
        issue_id = str(card["issue_id"]).strip()
        if not issue_id:
            continue
        updated = _run_object(
            active_runner,
            [
                "multica", "issue", "update", issue_id,
                "--description-stdin",
                "--title", f"[{projection['workflow_run_id']}] {card['stage_card_id']} {card['title']}",
                "--project", str(config["workflow_project_id"]),
                "--status", str(card["status"]),
                "--output", "json",
                "--workspace-id", workspace_id,
            ],
            str(card["description"]),
            "stage-card update",
        )
        if updated.get("id") != issue_id or updated.get("status") != card["status"]:
            raise ContractError("Workflow center stage-card update was not confirmed")
        metadata = {
            "qa_item_type": "stage_card",
            "qa_workflow_id": str(projection["workflow_id"]),
            "qa_workflow_run_id": str(projection["workflow_run_id"]),
            "qa_stage_card_id": str(card["stage_card_id"]),
            "qa_node_ids": ",".join(str(node.get("node_id")) for node in card["nodes"]),
            "qa_visible_in_workflow_center": "true",
        }
        for command in _metadata_commands(issue_id, metadata, workspace_id):
            active_runner(command, None)
        active_runner(
            _property_command(issue_id, str(properties["item_type"]), "内部节点", workspace_id),
            None,
        )

    result = {
        "schema_version": "workflow-center-sync-result/1.0",
        "workflow_id": projection["workflow_id"],
        "workflow_run_id": projection["workflow_run_id"],
        "parent_issue_id": parent_id,
        "parent_status": projection["multica_status"],
        "overall_status": projection["overall_status"],
        "progress": dict(projection["progress"]),
        "action_required": projection["action_required"],
        "action_count": projection["action_count"],
        "classified_node_count": classified_nodes,
        "stage_card_count": len(stage_cards),
        "projection_hash": projection["projection_hash"],
    }
    result["result_hash"] = content_hash(result)
    store.write_json("workflow-center-sync-result.json", result)
    store.write_json(
        "workflow-center-sync-state.json",
        {
            "schema_version": "workflow-center-sync-state/1.0",
            "workflow_id": projection["workflow_id"],
            "workflow_run_id": projection["workflow_run_id"],
            "revision": projection["revision"],
            "projection_hash": projection["projection_hash"],
            "result_hash": result["result_hash"],
        },
    )
    return result


def sync_multica_workflow_center(
    spec_path: Path,
    config_path: Path,
    output_dir: Path,
    *,
    runner: CommandRunner | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Synchronize one monotonic Projection while serializing concurrent writers."""

    with _workflow_sync_lock(output_dir):
        spec = _read_object(spec_path, "requirement workflow spec")
        projection = build_workflow_projection(spec)
        _assert_monotonic_projection(output_dir, projection)
        return _sync_multica_workflow_center_unlocked(
            spec_path,
            config_path,
            output_dir,
            runner=runner,
            security=security,
        )
