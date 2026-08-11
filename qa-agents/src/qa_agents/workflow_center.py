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
    bound_issue_ids: set[str] = set()
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
            if issue_id in bound_issue_ids:
                raise ContractError(f"Requirement workflow has duplicate node issue_id: {issue_id}")
            bound_issue_ids.add(issue_id)
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
            str(config["workflow_project_id"]),
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

    action_issue_ids = {
        str(action.get("issue_id"))
        for action in projection["actions"]
        if action.get("issue_id")
    }
    classified_nodes = 0
    internal_project_id = str(config["internal_project_id"])
    run_issue = projection.get("run_issue")
    if isinstance(run_issue, Mapping):
        run_issue_id = str(run_issue["id"])
        _ensure_run_issue_state(
            active_runner,
            run_issue_id,
            internal_project_id,
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
    for node in projection["nodes"]:
        issue_id = str(node.get("issue_id", "")).strip()
        if not issue_id:
            continue
        item_type = "human_action" if issue_id in action_issue_ids else "node_execution"
        if item_type == "human_action":
            action = next(
                item for item in projection["actions"] if str(item.get("issue_id")) == issue_id
            )
            action_status = "in_review" if action["status"] == "open" else "done"
            _ensure_run_issue_state(
                active_runner,
                issue_id,
                internal_project_id,
                action_status,
                workspace_id,
            )
        else:
            _ensure_issue_project(
                active_runner, issue_id, internal_project_id, workspace_id
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
            _property_command(issue_id, str(properties["item_type"]), item_label, workspace_id),
            None,
        )
        classified_nodes += 1

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
