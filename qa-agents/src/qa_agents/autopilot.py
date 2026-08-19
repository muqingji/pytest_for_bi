"""Requirement-level Autopilot lifecycle and Artifact-driven workflow reconciliation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import subprocess
from typing import Any

from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from .errors import ContractError, InputError, RetryableAgentError
from .security import SecurityPolicy
from .storage import ArtifactStore


CommandRunner = Callable[[list[str], str | None], Any]

SERVER_NODE_DEFINITIONS = (
    ("INPUT-FREEZE", "需求、方案与 ChangeSet 冻结", 1),
    ("N00", "工作流模板与深度选择", 2),
    ("A02", "需求分析", 3),
    ("A03", "技术方案与可测性分析", 3),
    ("A05", "服务端变更分析", 3),
    ("A06", "需求与变更对齐", 4),
    ("G01", "范围与口径人工审核", 5),
    ("N24", "风险与测试策略", 6),
    ("A08", "测试设计", 7),
    ("A09", "Oracle 与覆盖审查", 8),
    ("N04", "Test Case IR 校验", 9),
    ("G02", "Test Case IR 人工审核", 10),
    ("N25", "父子 Case 编译", 11),
    ("A11", "拆分覆盖审查", 12),
    ("N26", "测试选择", 13),
    ("N15", "执行计划编译", 14),
    ("A14", "服务端自动化生成", 15),
    ("A15", "契约自动化生成", 15),
    ("A22", "112 测试数据规划", 15),
    ("A18-BE", "服务端自动化独立复核", 16),
    ("A18-CT", "契约自动化独立复核", 16),
    ("N27", "测试数据计划安全校验", 16),
    ("N05", "自动化确定性代码检查", 17),
    ("G03", "自动化代码人工审核", 18),
    ("N07", "环境、数据与资源预检", 19),
    ("N08", "受控自动化执行", 20),
    ("N17", "人工与探索测试执行", 20),
    ("N10", "环境失败重试预算", 21),
    ("N18", "运行质量信号采集", 21),
    ("N09", "执行证据标准化与失败聚类", 22),
    ("N20", "跨运行缺陷去重", 23),
    ("N11", "确定性质量决策", 24),
    ("N19", "质量豁免审计", 25),
    ("N12", "质量报告发布", 26),
    ("N13", "报告反馈入口", 27),
    ("N23", "上线后验证授权审计", 28),
)

STAGE_CARD_SCHEMA_VERSION = "server-stage-cards/1.0"
SERVER_STAGE_CARD_DEFINITIONS = (
    ("C1", "需求分析与变更对齐", ("INPUT-FREEZE", "N00", "A02", "A03", "A05", "A06")),
    ("C2", "范围确认与测试策略", ("G01", "N24")),
    ("C3", "测试设计与审核", ("A08", "A09", "N04", "G02")),
    ("C4", "Case 编译与执行计划", ("N25", "A11", "N26", "N15")),
    (
        "C5",
        "自动化与测试数据准备",
        ("A14", "A15", "A22", "A18-BE", "A18-CT", "N27", "N05", "G03"),
    ),
    ("C6", "环境预检与测试执行", ("N07", "N08", "N17", "N10")),
    ("C7", "证据归一与质量决策", ("N18", "N09", "N20", "N11", "N19")),
    ("C8", "报告与关闭", ("N12", "N13", "N23")),
)


def _stage_card_by_node() -> dict[str, tuple[str, str]]:
    node_ids = {node_id for node_id, _label, _stage in SERVER_NODE_DEFINITIONS}
    result: dict[str, tuple[str, str]] = {}
    for card_id, title, card_nodes in SERVER_STAGE_CARD_DEFINITIONS:
        for node_id in card_nodes:
            if node_id in result:
                raise ContractError(f"Server node is assigned to multiple stage cards: {node_id}")
            result[node_id] = (card_id, title)
    missing = node_ids - result.keys()
    unknown = result.keys() - node_ids
    if missing or unknown:
        raise ContractError(
            "Server stage-card mapping is incomplete: "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    return result

ARTIFACT_NODE_MAP = {
    "n00-workflow-route": "N00",
    "n00-workflow-route-validated": "N00",
    "n01-source-extraction-manifest": "INPUT-FREEZE",
    "a02-requirement-analysis": "A02",
    "a03-technical-testability-analysis": "A03",
    "a05-backend-change-analysis": "A05",
    "a06-alignment-result": "A06",
    "g01-scope-review": "G01",
    "n24-test-strategy": "N24",
    "a08-test-design-ir": "A08",
    "a09-oracle-coverage-review": "A09",
    "n04-test-case-ir-validation": "N04",
    "g02-test-case-ir-review": "G02",
    "n25-compiled-test-cases": "N25",
    "a11-split-coverage-review": "A11",
    "n26-test-selection": "N26",
    "n15-execution-plan": "N15",
    "a14-backend-automation-generation": "A14",
    "a15-contract-automation-generation": "A15",
    "a22-test-data-plan": "A22",
    "a18-be-backend-automation-review": "A18-BE",
    "a18-ct-contract-automation-review": "A18-CT",
    "n27-test-data-plan-validation": "N27",
    "n05-automation-code-check": "N05",
    "g03-automation-code-review": "G03",
    "n07-environment-precheck": "N07",
    "n08-automation-execution": "N08",
    "n17-manual-execution": "N17",
    "n10-retry-budget": "N10",
    "n18-quality-signals": "N18",
    "n09-evidence": "N09",
    "n20-defect-dedup": "N20",
    "n11-quality-decision": "N11",
    "n19-quality-waiver": "N19",
    "n12-quality-report": "N12",
    "n13-feedback-capture": "N13",
    "n23-post-release-verification": "N23",
}

ARTIFACT_STATE_MAP = {
    "completed": "completed",
    "completed_with_gaps": "completed",
    "needs_human": "waiting_human",
    "blocked": "blocked",
    "blocked_input": "blocked",
    "not_applicable": "skipped",
    "skipped_by_policy": "skipped",
    "stale": "superseded",
    "cancelled": "cancelled",
    "inconclusive": "completed",
    "failed_retryable": "blocked",
    "failed_fatal": "failed",
}

TERMINAL_NODE_STATES = {"completed", "skipped", "cancelled", "superseded"}
ACTIVE_NODE_STATES = {"queued", "running", "waiting_human", "blocked", "failed"}


def _artifact_state(artifact: Mapping[str, Any]) -> str:
    status = str(artifact.get("status", ""))
    if status != "needs_human":
        try:
            return ARTIFACT_STATE_MAP[status]
        except KeyError as error:
            raise ContractError(f"Autopilot Artifact status is unsupported: {status}") from error
    payload = artifact.get("payload", {})
    issues = payload.get("issues", []) if isinstance(payload, Mapping) else []
    routes = {
        str(item.get("route_to", ""))
        for item in issues
        if isinstance(item, Mapping) and item.get("route_to")
    }
    blocking_questions = artifact.get("blocking_questions", [])
    if (
        isinstance(payload, Mapping) and payload.get("next_node") == "human"
    ) or blocking_questions or "human" in routes or not routes:
        return "waiting_human"
    return "blocked"


def _propagate_human_routed_blocks(
    nodes: list[dict[str, Any]],
    selected: Mapping[str, Mapping[str, Any]],
    owner_id: str,
    run_id: str,
    actions: list[dict[str, Any]],
) -> None:
    """Route blocked nodes carrying human-routed issues to waiting_human.

    When a decision node (for example N04 after the automatic correction
    budget is exhausted) routes its issues to ``human``, every other node that
    surfaced the same issue ids must read as "waiting for human" instead of a
    dead-end "blocked", and get an approval entry so the human decision is
    actionable in the workflow center.
    """

    routed_issue_ids: set[str] = set()
    for node in nodes:
        if node.get("state") != "waiting_human":
            continue
        artifact = selected.get(str(node.get("node_id")))
        if not isinstance(artifact, Mapping):
            continue
        payload = artifact.get("payload")
        if not isinstance(payload, Mapping) or payload.get("next_node") != "human":
            continue
        for issue in payload.get("issues", []):
            if isinstance(issue, Mapping) and issue.get("id"):
                routed_issue_ids.add(str(issue["id"]))
    if not routed_issue_ids:
        return
    if not owner_id:
        raise ContractError("Autopilot human_owner_member_id is required for actions")
    for item in nodes:
        if item.get("state") != "blocked":
            continue
        artifact = selected.get(str(item.get("node_id")))
        if not isinstance(artifact, Mapping):
            continue
        payload = artifact.get("payload")
        if not isinstance(payload, Mapping):
            continue
        issue_ids = {
            str(issue.get("id"))
            for issue in payload.get("issues", [])
            if isinstance(issue, Mapping) and issue.get("id")
        }
        if not (issue_ids & routed_issue_ids):
            continue
        item["state"] = "waiting_human"
        item["result_summary"] = "阻塞问题已路由人工处置，等待定向修正或终止决策"
        approval_items = _approval_items(artifact)
        item["approval_items"] = approval_items
        actions.append(
            {
                "action_id": f"{item.get('node_id')}-{run_id}",
                "gate_id": str(item.get("node_id")),
                "title": f"{item.get('label', item.get('node_id'))}处理",
                "status": "open",
                "owner_member_id": owner_id,
                "item_count": (
                    len(approval_items)
                    if approval_items
                    else _action_count(artifact)
                ),
                "summary": item["result_summary"],
                "approval_items": approval_items,
                "issue_id": item.get("issue_id"),
                "issue_identifier": item.get("issue_identifier"),
            }
        )


def _advance_frontier(nodes: Sequence[dict[str, Any]]) -> None:
    """Queue the earliest unfinished stage after accepted Artifacts are projected."""

    unfinished = [
        item for item in nodes if str(item.get("state", "")) not in TERMINAL_NODE_STATES
    ]
    if not unfinished:
        return
    frontier_stage = min(int(item["stage"]) for item in unfinished)
    frontier = [item for item in unfinished if int(item["stage"]) == frontier_stage]
    if any(str(item.get("state", "")) in ACTIVE_NODE_STATES for item in frontier):
        return
    for item in frontier:
        if item.get("state") == "not_started":
            item["state"] = "queued"
            item["result_summary"] = "上游节点已完成，等待调度"


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be a JSON object")
    return value


def _text(value: Mapping[str, Any], field: str, label: str) -> str:
    result = str(value.get(field, "")).strip()
    if not result:
        raise ContractError(f"{label} requires {field}")
    return result


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
        raise RetryableAgentError(f"Multica Autopilot command failed: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ContractError("Multica Autopilot command returned invalid JSON") from error


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _validate_registry(registry: Mapping[str, Any]) -> None:
    if registry.get("schema_version") != "autopilot-registry/1.0":
        raise ContractError("Autopilot registry schema_version is invalid")
    unhashed = {key: value for key, value in registry.items() if key != "registry_hash"}
    if registry.get("registry_hash") != content_hash(unhashed):
        raise ContractError("Autopilot registry hash is invalid")
    if not isinstance(registry.get("workflows"), Mapping):
        raise ContractError("Autopilot registry workflows must be an object")


def _issue(
    runner: CommandRunner,
    command: list[str],
    expected_project_id: str,
) -> dict[str, str]:
    result = runner(command, None)
    if not isinstance(result, Mapping):
        raise ContractError("Multica Autopilot Issue create did not return an object")
    issue_id = str(result.get("id", "")).strip()
    identifier = str(result.get("identifier", "")).strip()
    if (
        not issue_id
        or not identifier
        or result.get("project_id") != expected_project_id
    ):
        raise ContractError("Multica Autopilot Issue creation was not confirmed")
    return {"id": issue_id, "identifier": identifier}


def _discover_node_issues(
    runner: CommandRunner, project_id: str, workspace_id: str, run_id: str
) -> dict[str, dict[str, str]]:
    result = runner(
        [
            "multica", "issue", "list", "--project", project_id,
            "--limit", "100", "--output", "json", "--workspace-id", workspace_id,
        ],
        None,
    )
    if not isinstance(result, Mapping):
        raise ContractError("Multica node Issue discovery did not return an object")
    issues = result.get("issues", [])
    if not isinstance(issues, list):
        raise ContractError("Multica node Issue discovery returned invalid issues")
    prefix = f"[{run_id}] "
    known = {node_id for node_id, _label, _stage in SERVER_NODE_DEFINITIONS}
    discovered: dict[str, dict[str, str]] = {}
    timestamps: dict[str, str] = {}
    for issue in issues:
        if not isinstance(issue, Mapping):
            continue
        title = str(issue.get("title", ""))
        if not title.startswith(prefix):
            continue
        node_id = title[len(prefix):].split(" ", 1)[0]
        created_at = str(issue.get("created_at", ""))
        if (
            node_id in known
            and issue.get("id")
            and issue.get("identifier")
            and created_at >= timestamps.get(node_id, "")
        ):
            discovered[node_id] = {
                "id": str(issue["id"]), "identifier": str(issue["identifier"])
            }
            timestamps[node_id] = created_at
    return discovered


def _create_issue_command(
    *,
    title: str,
    project_id: str,
    workspace_id: str,
    assignee_id: str | None,
    parent_id: str | None = None,
    status: str = "todo",
) -> list[str]:
    command = [
        "multica",
        "issue",
        "create",
        "--title",
        title,
        "--project",
        project_id,
        "--status",
        status,
        "--priority",
        "high",
        "--output",
        "json",
        "--workspace-id",
        workspace_id,
    ]
    if assignee_id:
        command.extend(["--assignee-id", assignee_id])
    if parent_id:
        command.extend(["--parent", parent_id])
    return command


def _create_node_issue_command(
    *, title: str, project_id: str, workspace_id: str, assignee_id: str | None,
    parent_id: str, stage: int | None = None, attachments: Sequence[str] = ()
) -> list[str]:
    command = _create_issue_command(
        title=title,
        project_id=project_id,
        workspace_id=workspace_id,
        assignee_id=assignee_id,
        parent_id=parent_id,
        status="backlog",
    )
    if stage is not None:
        command.extend(["--stage", str(stage)])
    for attachment in attachments:
        command.extend(["--attachment", attachment])
    return command


def _metadata_command(issue_id: str, key: str, value: str, workspace_id: str) -> list[str]:
    return [
        "multica", "issue", "metadata", "set", issue_id,
        "--key", key, "--value", value, "--type", "string",
        "--output", "json", "--workspace-id", workspace_id,
    ]


def _set_visibility_metadata(
    runner: CommandRunner, issue: Mapping[str, Any], visible: bool, workspace_id: str
) -> None:
    runner(_metadata_command(
        str(issue["id"]), "qa_visible_in_workflow_center", str(visible).lower(), workspace_id
    ), None)


def _create_autopilot_command(
    *,
    requirement_id: str,
    title: str,
    parent_identifier: str,
    project_id: str,
    workspace_id: str,
    agent_id: str,
) -> list[str]:
    description = (
        f"需求 {requirement_id} 的唯一 QA Autopilot。父工作流 {parent_identifier}。"
        "按 Artifact 和实时 Issue run 单步推进 DAG：每次只调度最早未完成 stage，"
        "同 stage 可并行但不得越过 blocked、failed 或人工 Gate；"
        "queued、dispatched、deferred、running 必须投影为 in_progress，"
        "全部尝试 failed 或 cancelled 必须投影为 blocked，完成或策略跳过后推进下一 stage；"
        "每轮先对账再调度，节点 Issue 必须幂等复用，不得重复创建；"
        "不得代签人工 Gate，不得提交代码、创建 MR、Bug 或发布。"
    )
    return [
        "multica", "autopilot", "create",
        "--title", f"{requirement_id} QA 全链路",
        "--description", description,
        "--mode", "run_only",
        "--agent", agent_id,
        "--project", project_id,
        "--priority", "high",
        "--output", "json",
        "--workspace-id", workspace_id,
    ]


def _autopilot(
    runner: CommandRunner,
    command: list[str],
    *,
    expected_agent_id: str,
    expected_project_id: str,
) -> dict[str, str]:
    result = runner(command, None)
    if not isinstance(result, Mapping):
        raise ContractError("Multica Autopilot create did not return an object")
    autopilot_id = str(result.get("id", "")).strip()
    if (
        not autopilot_id
        or result.get("assignee_id") != expected_agent_id
        or result.get("project_id") != expected_project_id
        or result.get("execution_mode") != "run_only"
        or result.get("status") != "active"
    ):
        raise ContractError("Multica requirement Autopilot creation was not confirmed")
    return {"id": autopilot_id, "status": "active", "execution_mode": "run_only"}


def initialize_autopilot(
    request_path: Path,
    config_path: Path,
    registry_dir: Path,
    output_dir: Path,
    *,
    runner: CommandRunner | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Create or reuse one requirement parent and create one idempotent Run Issue."""

    security = security or SecurityPolicy()
    request = _read_object(request_path, "Autopilot request")
    config = _read_object(config_path, "workflow center config")
    if request.get("schema_version") != "autopilot-request/1.0":
        raise ContractError("Autopilot request schema_version is invalid")
    if config.get("schema_version") != "multica-workflow-center/1.0":
        raise ContractError("Workflow center config schema_version is invalid")
    for field in (
        "workflow_id",
        "requirement_id",
        "workflow_run_id",
        "workflow_definition_version",
        "source_snapshot_id",
        "title",
        "human_owner_member_id",
    ):
        _text(request, field, "Autopilot request")
    for field in (
        "workspace_id",
        "workflow_project_id",
        "internal_project_id",
        "workflow_lead_id",
    ):
        _text(config, field, "Workflow center config")
    if request["workflow_id"] != request["requirement_id"]:
        raise ContractError("Autopilot workflow_id must equal its stable requirement_id")
    security.assert_no_secret_values(request)
    security.assert_no_secret_values(config)

    registry_path = registry_dir / "autopilot-registry.json"
    lock_path = registry_dir / ".autopilot-registry.lock"
    active_runner = runner or _default_runner
    with _exclusive_lock(lock_path):
        if registry_path.exists():
            registry = _read_object(registry_path, "Autopilot registry")
            _validate_registry(registry)
        else:
            registry = {
                "schema_version": "autopilot-registry/1.0",
                "revision": 0,
                "workflows": {},
            }
        workflows = dict(registry["workflows"])
        requirement_id = str(request["requirement_id"])
        workflow = dict(workflows.get(requirement_id, {}))
        if workflow and workflow.get("workflow_id") != request["workflow_id"]:
            raise ContractError("Requirement is already bound to another workflow_id")

        if workflow:
            parent_issue = dict(workflow["parent_issue"])
        else:
            parent_issue = _issue(
                active_runner,
                _create_issue_command(
                    title=f"[{requirement_id}] {request['title']}",
                    project_id=str(config["internal_project_id"]),
                    workspace_id=str(config["workspace_id"]),
                    assignee_id=str(config["workflow_lead_id"]),
                ),
                str(config["internal_project_id"]),
            )

        if workflow.get("autopilot"):
            requirement_autopilot = dict(workflow["autopilot"])
            autopilot_reused = True
        else:
            requirement_autopilot = _autopilot(
                active_runner,
                _create_autopilot_command(
                    requirement_id=requirement_id,
                    title=str(request["title"]),
                    parent_identifier=str(parent_issue["identifier"]),
                    project_id=str(config["workflow_project_id"]),
                    workspace_id=str(config["workspace_id"]),
                    agent_id=str(config["workflow_lead_id"]),
                ),
                expected_agent_id=str(config["workflow_lead_id"]),
                expected_project_id=str(config["workflow_project_id"]),
            )
            autopilot_reused = False

        runs = [dict(item) for item in workflow.get("runs", [])]
        run_id = str(request["workflow_run_id"])
        existing_run = next(
            (item for item in runs if item.get("workflow_run_id") == run_id), None
        )
        if existing_run:
            run_issue = dict(existing_run["run_issue"])
        else:
            run_project_id = str(
                config.get("run_project_id") or config["internal_project_id"]
            )
            run_issue = _issue(
                active_runner,
                _create_issue_command(
                    title=f"[{run_id}] 服务端 QA Run",
                    project_id=run_project_id,
                    workspace_id=str(config["workspace_id"]),
                    assignee_id=None,
                    parent_id=str(parent_issue["id"]),
                ),
                run_project_id,
            )
            for item in runs:
                if item.get("status") == "active":
                    item["status"] = "superseded"
            runs.append(
                {
                    "workflow_run_id": run_id,
                    "source_snapshot_id": request["source_snapshot_id"],
                    "status": "active",
                    "run_issue": run_issue,
                }
            )

        stage_issues = {
            str(card_id): dict(issue)
            for card_id, issue in (
                existing_run.get("stage_issues", {}) if existing_run else {}
            ).items()
            if isinstance(issue, Mapping)
        }
        node_issues = {
            str(node_id): dict(issue)
            for node_id, issue in (
                existing_run.get("node_issues", {}) if existing_run else {}
            ).items()
            if isinstance(issue, Mapping)
        }
        if config.get("recover_precreated_nodes", False):
            run_project_id = str(config.get("run_project_id") or config["internal_project_id"])
            discovered = _discover_node_issues(
                active_runner, run_project_id, str(config["workspace_id"]), run_id
            )
            node_issues = {**node_issues, **discovered}
        if config.get("precreate_nodes", False):
            for card_id, title, _node_ids in SERVER_STAGE_CARD_DEFINITIONS:
                if card_id in stage_issues:
                    continue
                stage_issues[card_id] = _issue(
                    active_runner,
                    _create_node_issue_command(
                        title=f"[{run_id}] {card_id} {title}",
                        project_id=str(config["workflow_project_id"]),
                        workspace_id=str(config["workspace_id"]),
                        # Stage cards are read-only projections. Assigning an Agent makes
                        # Multica execute the display card as a model task.
                        assignee_id=None,
                        parent_id=str(run_issue["id"]),
                    ),
                    str(config["workflow_project_id"]),
                )
            for item in runs:
                if item.get("workflow_run_id") == run_id:
                    item["stage_card_schema_version"] = STAGE_CARD_SCHEMA_VERSION
                    item["stage_issues"] = stage_issues
                    item["node_issues"] = node_issues
                    break

        # Apply visibility at creation/recovery time as well as during the
        # later workflow-center sync. This keeps partial initialization from
        # leaking hidden execution Issues into the project board.
        if config.get("initialize_visibility_metadata", False):
            _set_visibility_metadata(active_runner, parent_issue, False, str(config["workspace_id"]))
            _set_visibility_metadata(active_runner, run_issue, False, str(config["workspace_id"]))
            for issue in stage_issues.values():
                _set_visibility_metadata(active_runner, issue, True, str(config["workspace_id"]))
            for issue in node_issues.values():
                _set_visibility_metadata(active_runner, issue, False, str(config["workspace_id"]))

        stage_by_node = _stage_card_by_node()

        workflows[requirement_id] = {
            "workflow_id": request["workflow_id"],
            "requirement_id": requirement_id,
            "title": request["title"],
            "parent_issue": parent_issue,
            "autopilot": requirement_autopilot,
            "active_run_id": run_id,
            "runs": runs,
        }
        registry = {
            "schema_version": "autopilot-registry/1.0",
            "revision": int(registry.get("revision", 0)) + (0 if existing_run else 1),
            "workflows": workflows,
        }
        registry["registry_hash"] = content_hash(registry)
        ArtifactStore(registry_dir).write_json("autopilot-registry.json", registry)

    previous_runs = [item for item in runs if item["workflow_run_id"] != run_id]
    spec = {
        "schema_version": "requirement-workflow/1.0",
        "workflow_id": request["workflow_id"],
        "requirement_id": requirement_id,
        "workflow_run_id": run_id,
        "workflow_definition_version": request["workflow_definition_version"],
        "revision": 1,
        "source_snapshot_id": request["source_snapshot_id"],
        "title": request["title"],
        "human_owner_member_id": request["human_owner_member_id"],
        "parent_issue": parent_issue,
        "run_issue": run_issue,
        "autopilot": requirement_autopilot,
        "autopilot_runs": [],
        "stage_card_schema_version": STAGE_CARD_SCHEMA_VERSION,
        "stage_cards": [
            {
                "stage_card_id": card_id,
                "title": title,
                "node_ids": list(node_ids),
                **(
                    {
                        "issue_id": stage_issues[card_id]["id"],
                        "issue_identifier": stage_issues[card_id]["identifier"],
                    }
                    if card_id in stage_issues
                    else {}
                ),
            }
            for card_id, title, node_ids in SERVER_STAGE_CARD_DEFINITIONS
        ],
        "nodes": [
            {
                "execution_id": f"{node_id}-{run_id}",
                "node_id": node_id,
                "label": label,
                "stage": stage,
                "state": "queued" if node_id == "INPUT-FREEZE" else "not_started",
                "completion": "0/1",
                "result_summary": "等待上游节点",
                "stage_card_id": stage_by_node[node_id][0],
                "stage_card_title": stage_by_node[node_id][1],
                **({
                    "issue_id": node_issues[node_id]["id"],
                    "issue_identifier": node_issues[node_id]["identifier"],
                } if node_id in node_issues else {}),
                **({
                    "stage_issue_id": stage_issues[stage_by_node[node_id][0]]["id"],
                    "stage_issue_identifier": stage_issues[stage_by_node[node_id][0]]["identifier"],
                } if stage_by_node[node_id][0] in stage_issues else {}),
            }
            for node_id, label, stage in SERVER_NODE_DEFINITIONS
        ],
        "actions": [],
        "run_history": [
            {
                "workflow_run_id": item["workflow_run_id"],
                "status": item.get("status", "historical"),
                "summary": "Previous Autopilot Run retained for audit",
            }
            for item in previous_runs
        ],
    }
    store = ArtifactStore(output_dir)
    store.write_json("workflow-center-spec.json", spec)
    result = {
        "schema_version": "autopilot-initialization-result/1.0",
        "workflow_id": request["workflow_id"],
        "workflow_run_id": run_id,
        "parent_issue": parent_issue,
        "run_issue": run_issue,
        "autopilot": requirement_autopilot,
        "parent_reused": bool(workflow),
        "run_reused": existing_run is not None,
        "autopilot_reused": autopilot_reused,
        "registry_revision": registry["revision"],
        "spec_path": str(output_dir / "workflow-center-spec.json"),
    }
    result["result_hash"] = content_hash(result)
    store.write_json("autopilot-initialization-result.json", result)
    return result


def _artifact_summary(artifact: Mapping[str, Any]) -> str:
    payload = artifact.get("payload", {})
    for field in ("decision", "summary"):
        value = payload.get(field) if isinstance(payload, Mapping) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))[:500]
    status = str(payload.get("status") or "").strip()
    if status == "needs_human" and isinstance(payload, Mapping):
        issues = payload.get("issues")
        if isinstance(issues, list):
            codes = [
                str(item.get("id") or item.get("issue_code") or "").strip()
                for item in issues
                if isinstance(item, Mapping)
            ]
            codes = [code for code in codes if code]
            if codes:
                names = "、".join(codes[:4])
                if len(codes) > 4:
                    names += f" 等 {len(codes)} 项"
                return f"发现 {len(codes)} 个阻塞问题需人工定向修正（{names}）"
    if status:
        return status
    return f"Artifact {artifact['artifact_id']} accepted"


def _action_count(artifact: Mapping[str, Any]) -> int:
    payload = artifact.get("payload", {})
    if not isinstance(payload, Mapping):
        return 1
    for field in ("issues", "tasks", "unresolved_items"):
        value = payload.get(field)
        if isinstance(value, list) and value:
            return len(value)
    return 1


def _approval_items(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract structured approval items from a waiting-human Artifact.

    Every item keeps the upstream evidence id and a human-readable summary so
    the workflow center and stage cards can render exactly what must be
    approved instead of a bare status string.
    """

    payload = artifact.get("payload", {})
    if not isinstance(payload, Mapping):
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append(
        item: Mapping[str, Any],
        *,
        title: str,
        summary: str,
        confirm_action: str = "",
        category: str = "",
    ) -> None:
        item_id = str(item.get("issue_id") or item.get("id") or "").strip()
        if not item_id:
            item_id = f"{artifact['artifact_id']}-{len(items) + 1}"
        if item_id in seen:
            return
        seen.add(item_id)
        detail = item.get("detail")
        requirement_ids = item.get("requirement_ids")
        if not isinstance(requirement_ids, list) and isinstance(detail, Mapping):
            requirement_ids = detail.get("requirement_ids")
        items.append(
            {
                "id": item_id,
                "title": title,
                "summary": summary.strip() or title or "请查看 Artifact 获取详情",
                "confirm_action": confirm_action.strip(),
                "category": category.strip(),
                "severity": str(item.get("severity") or "").strip(),
                "issue_code": str(item.get("issue_code") or "").strip(),
                "human_title": str(item.get("human_title") or "").strip(),
                "plain_summary": str(item.get("plain_summary") or "").strip(),
                "case_id": str(item.get("case_id") or "").strip(),
                "expected_id": str(item.get("expected_id") or "").strip(),
                "recommendation": str(item.get("recommendation") or "").strip(),
                "requirement_ids": (
                    [str(value) for value in requirement_ids if str(value).strip()]
                    if isinstance(requirement_ids, list)
                    else []
                ),
                "source_refs": [
                    str(value) for value in item.get("source_refs", [])
                    if isinstance(item.get("source_refs"), list)
                ],
            }
        )

    for finding in payload.get("findings", []):
        if not isinstance(finding, Mapping):
            continue
        prefix = f"[{finding.get('type')}]" if finding.get("type") else ""
        append(
            finding,
            title=prefix or "发现项",
            summary=str(finding.get("summary") or "").strip(),
        )
    for item in payload.get("blocking_items", []):
        if not isinstance(item, Mapping):
            continue
        append(
            item,
            title="阻塞项",
            summary=str(item.get("summary") or item.get("recommendation") or "").strip(),
        )
    for field, label in (("ambiguities", "需求歧义"), ("needs_human", "需确认事项")):
        for item in payload.get(field, []):
            if not isinstance(item, Mapping):
                continue
            append(
                item,
                title=label,
                summary=str(item.get("message") or "").strip(),
            )
    for item in payload.get("issues", []):
        if not isinstance(item, Mapping):
            continue
        detail = item.get("detail")
        append(
            item,
            title=str(item.get("category") or item.get("type") or "问题").strip() or "问题",
            summary=str(
                item.get("plain_summary")
                or item.get("summary")
                or (detail.get("summary") if isinstance(detail, Mapping) else "")
                or (detail.get("message") if isinstance(detail, Mapping) else "")
                or item.get("message")
            ).strip(),
            confirm_action=str(item.get("confirm_action") or "").strip(),
            category=str(item.get("category") or "").strip(),
        )
    for field in ("tasks", "unresolved_items", "questions", "approval_items"):
        for item in payload.get(field, []):
            if not isinstance(item, Mapping):
                continue
            append(
                item,
                title=str(item.get("title") or "审批项").strip() or "审批项",
                summary=str(item.get("summary") or item.get("message") or "").strip(),
            )
    for item in artifact.get("blocking_questions", []):
        if not isinstance(item, Mapping):
            continue
        append(
            item,
            title="阻塞问题",
            summary=str(item.get("question") or item.get("summary") or "").strip(),
        )
    if not items:
        summary = _artifact_summary(artifact)
        items.append(
            {
                "id": f"{artifact['artifact_id']}-approval",
                "title": "审批确认",
                "summary": summary,
                "severity": "",
                "requirement_ids": [],
                "source_refs": [],
            }
        )
    return items


def reconcile_autopilot(
    spec_path: Path,
    artifact_roots: Sequence[Path],
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Derive node and human-action state from accepted Artifacts for one Run."""

    security = security or SecurityPolicy()
    lock_path = output_dir / ".autopilot-reconcile.lock"
    with _exclusive_lock(lock_path):
        spec = _read_object(spec_path, "Autopilot workflow spec")
        if spec.get("schema_version") != "requirement-workflow/1.0":
            raise ContractError("Autopilot workflow spec schema_version is invalid")
        run_id = _text(spec, "workflow_run_id", "Autopilot workflow spec")
        snapshot_id = _text(spec, "source_snapshot_id", "Autopilot workflow spec")

        # The registry is the durable binding source for execution Issues.  A
        # retry may replace an Issue after the spec was first published; refresh
        # those bindings before deriving node state so the projection cannot
        # keep pointing at a cancelled predecessor.
        registry_path = output_dir.parent / "registry" / "autopilot-registry.json"
        registry = None
        if registry_path.exists():
            registry = _read_object(registry_path, "Autopilot registry")
            _validate_registry(registry)
        if isinstance(registry, Mapping):
            workflow = registry.get("workflows", {}).get(str(spec.get("workflow_id")))
            if isinstance(workflow, Mapping):
                run = next(
                    (
                        item for item in workflow.get("runs", [])
                        if isinstance(item, Mapping)
                        and str(item.get("workflow_run_id")) == run_id
                    ),
                    None,
                )
                if isinstance(run, Mapping):
                    registry_nodes = run.get("node_issues", {})
                    registry_stages = run.get("stage_issues", {})
                    refreshed_stage_cards = []
                    for card in spec.get("stage_cards", []):
                        card_item = dict(card)
                        binding = (
                            registry_stages.get(str(card_item.get("stage_card_id")))
                            if isinstance(registry_stages, Mapping)
                            else None
                        )
                        if isinstance(binding, Mapping) and binding.get("id"):
                            card_item["issue_id"] = str(binding["id"])
                            card_item["issue_identifier"] = str(binding.get("identifier", ""))
                        refreshed_stage_cards.append(card_item)
                    if isinstance(registry_nodes, Mapping):
                        refreshed_nodes = []
                        for node in spec.get("nodes", []):
                            item = dict(node)
                            binding = registry_nodes.get(str(item.get("node_id")))
                            if isinstance(binding, Mapping) and binding.get("id"):
                                item["issue_id"] = str(binding["id"])
                                item["issue_identifier"] = str(
                                    binding.get("identifier", "")
                                )
                            stage_binding = (
                                registry_stages.get(str(item.get("stage_card_id")))
                                if isinstance(registry_stages, Mapping)
                                else None
                            )
                            if isinstance(stage_binding, Mapping) and stage_binding.get("id"):
                                item["stage_issue_id"] = str(stage_binding["id"])
                                item["stage_issue_identifier"] = str(
                                    stage_binding.get("identifier", "")
                                )
                            refreshed_nodes.append(item)
                        spec = {
                            **spec,
                            "nodes": refreshed_nodes,
                            "stage_cards": refreshed_stage_cards,
                        }
        selected: dict[str, dict[str, Any]] = {}
        for root in artifact_roots:
            if not root.exists():
                continue
            for path in root.rglob("*.json"):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(value, dict) or value.get("schema_version") != "artifact-envelope/1.0":
                    continue
                if (
                    value.get("workflow_run_id") != run_id
                    or value.get("source_snapshot_id") != snapshot_id
                ):
                    continue
                if artifact_hash_from_mapping(value) != value.get("artifact_hash"):
                    raise ContractError(f"Autopilot found a tampered Artifact: {path}")
                security.assert_no_secret_values(value)
                node_id = ARTIFACT_NODE_MAP.get(str(value.get("artifact_id", "")))
                if not node_id:
                    continue
                candidate = {**value, "_path": str(path)}
                current = selected.get(node_id)
                if current is None or (
                    str(candidate.get("created_at", "")), str(candidate.get("artifact_hash", ""))
                ) > (
                    str(current.get("created_at", "")), str(current.get("artifact_hash", ""))
                ):
                    selected[node_id] = candidate

        previous_core = {key: value for key, value in spec.items() if key != "revision"}
        nodes = []
        actions = []
        owner_id = str(spec.get("human_owner_member_id", "")).strip()
        for node in spec.get("nodes", []):
            if not isinstance(node, Mapping):
                raise ContractError("Autopilot workflow nodes must be objects")
            item = dict(node)
            node_id = str(item.get("node_id", ""))
            artifact = selected.get(node_id)
            if artifact:
                item["state"] = _artifact_state(artifact)
                if node_id == "G01" and artifact.get("status") == "needs_human":
                    # G01 issue.route_to records the upstream correction owner;
                    # it does not turn the Gate itself into an automatic return.
                    item["state"] = "waiting_human"
                item["completion"] = "1/1"
                item["result_summary"] = _artifact_summary(artifact)
                item["artifact_id"] = artifact["artifact_id"]
                item["artifact_hash"] = artifact["artifact_hash"]
                item["artifact_path"] = artifact["_path"]
                if node_id in {"A02", "A03", "A06"} and item["state"] == "waiting_human":
                    # Stage 1 的待确认项统一并入 G01 范围与口径审核，一次审批；
                    # 上游分析节点不生成独立人工 action，避免阻断 A06 和重复审核。
                    item["state"] = "completed"
                    item["result_summary"] = "发现待确认项，已并入 G01 汇总审批"
                if item["state"] == "waiting_human":
                    if not owner_id:
                        raise ContractError("Autopilot human_owner_member_id is required for actions")
                    approval_items = _approval_items(artifact)
                    item["approval_items"] = approval_items
                    actions.append(
                        {
                            "action_id": f"{node_id}-{run_id}",
                            "gate_id": node_id,
                            "title": f"{item.get('label', node_id)}处理",
                            "status": "open",
                            "owner_member_id": owner_id,
                            "item_count": (
                                len(approval_items)
                                if approval_items
                                else _action_count(artifact)
                            ),
                            "summary": item["result_summary"],
                            "approval_items": approval_items,
                            "issue_id": item.get("issue_id"),
                            "issue_identifier": item.get("issue_identifier"),
                        }
                    )
            nodes.append(item)
        _propagate_human_routed_blocks(nodes, selected, owner_id, run_id, actions)
        _advance_frontier(nodes)
        candidate = {**spec, "nodes": nodes, "actions": actions}
        candidate_core = {key: value for key, value in candidate.items() if key != "revision"}
        changed = candidate_core != previous_core
        if changed:
            candidate["revision"] = int(spec.get("revision", 0)) + 1
        ArtifactStore(output_dir).write_json("workflow-center-spec.json", candidate)
        result = {
            "schema_version": "autopilot-reconciliation-result/1.0",
            "workflow_id": candidate["workflow_id"],
            "workflow_run_id": run_id,
            "revision": candidate["revision"],
            "changed": changed,
            "artifact_node_count": len(selected),
            "open_action_count": len(actions),
            "spec_hash": content_hash(candidate),
            "spec_path": str(output_dir / "workflow-center-spec.json"),
        }
        result["result_hash"] = content_hash(result)
        ArtifactStore(output_dir).write_json("autopilot-reconciliation-result.json", result)
        return result


def run_deterministic_bootstrap(
    request_path: Path, input_dir: Path, output_dir: Path
) -> dict[str, Any]:
    """Run INPUT-FREEZE and unambiguous N00 locally without a model Runtime."""

    from .workflow import resolve_workflow_route

    request = _read_object(request_path, "Autopilot request")
    workflow_input = _read_object(input_dir / "workflow-input.json", "workflow input")
    source_snapshot = _read_object(input_dir / "source-snapshot.json", "source snapshot")
    run_id = _text(request, "workflow_run_id", "Autopilot request")
    snapshot_id = _text(request, "source_snapshot_id", "Autopilot request")
    if source_snapshot.get("snapshot_id") != snapshot_id:
        raise ContractError("Deterministic bootstrap source snapshot does not match the Run")
    route = resolve_workflow_route(workflow_input)
    if route["unresolved_items"]:
        raise ContractError("Deterministic bootstrap N00 requires A01 advice")
    workflow_mode = str(route["template"])
    store = ArtifactStore(output_dir)
    artifacts = [
        ArtifactEnvelope(
            workflow_run_id=run_id,
            workflow_mode=workflow_mode,
            artifact_id="n01-source-extraction-manifest",
            source_snapshot_id=snapshot_id,
            producer=Producer(component_id="INPUT-FREEZE", runtime="deterministic-node"),
            payload={
                "schema_version": "source-extraction-manifest/1.0",
                "files": ["workflow-input.json", "source-snapshot.json"],
                "source_material_available": (input_dir / "source-material.json").exists(),
                "oracle_available_to_agents": False,
            },
            status=ArtifactStatus.COMPLETED,
        ),
        ArtifactEnvelope(
            workflow_run_id=run_id,
            workflow_mode=workflow_mode,
            artifact_id="n00-workflow-route",
            source_snapshot_id=snapshot_id,
            producer=Producer(component_id="N00", runtime="deterministic-node"),
            payload={
                "schema_version": "workflow-route/1.0",
                "workflow_mode": workflow_mode,
                "workflow_template": route["template"],
                "execution_depth": route["execution_depth"],
                "route_source": route["route_source"],
            },
            status=ArtifactStatus.COMPLETED,
        ),
    ]
    for artifact in artifacts:
        store.write_artifact(artifact)
    result = {
        "schema_version": "deterministic-bootstrap-result/1.0",
        "workflow_run_id": run_id,
        "source_snapshot_id": snapshot_id,
        "completed_nodes": ["INPUT-FREEZE", "N00"],
        "artifact_hashes": {item.artifact_id: item.artifact_hash for item in artifacts},
    }
    result["result_hash"] = content_hash(result)
    store.write_json("deterministic-bootstrap-result.json", result)
    return result
