"""Requirement-level Autopilot lifecycle and Artifact-driven workflow reconciliation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import subprocess
from typing import Any

from .contracts import artifact_hash_from_mapping, content_hash
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


def _create_issue_command(
    *,
    title: str,
    project_id: str,
    workspace_id: str,
    assignee_id: str,
    parent_id: str | None = None,
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
        "todo",
        "--assignee-id",
        assignee_id,
        "--priority",
        "high",
        "--output",
        "json",
        "--workspace-id",
        workspace_id,
    ]
    if parent_id:
        command.extend(["--parent", parent_id])
    return command


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
        "只做 Artifact 驱动的 DAG 对账、节点状态推进和人工事项汇总；"
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
                    project_id=str(config["workflow_project_id"]),
                    workspace_id=str(config["workspace_id"]),
                    assignee_id=str(config["workflow_lead_id"]),
                ),
                str(config["workflow_project_id"]),
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
            run_issue = _issue(
                active_runner,
                _create_issue_command(
                    title=f"[{run_id}] 服务端 QA Run",
                    project_id=str(config["internal_project_id"]),
                    workspace_id=str(config["workspace_id"]),
                    assignee_id=str(config["workflow_lead_id"]),
                    parent_id=str(parent_issue["id"]),
                ),
                str(config["internal_project_id"]),
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
        "nodes": [
            {
                "execution_id": f"{node_id}-{run_id}",
                "node_id": node_id,
                "label": label,
                "stage": stage,
                "state": "queued" if node_id == "INPUT-FREEZE" else "not_started",
                "completion": "0/1",
                "result_summary": "等待上游节点",
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
    for field in ("decision", "summary", "status"):
        value = payload.get(field) if isinstance(payload, Mapping) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))[:500]
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
                status = str(artifact.get("status", ""))
                if status not in ARTIFACT_STATE_MAP:
                    raise ContractError(f"Autopilot Artifact status is unsupported: {status}")
                item["state"] = ARTIFACT_STATE_MAP[status]
                item["completion"] = "1/1"
                item["result_summary"] = _artifact_summary(artifact)
                item["artifact_id"] = artifact["artifact_id"]
                item["artifact_hash"] = artifact["artifact_hash"]
                item["artifact_path"] = artifact["_path"]
                if item["state"] == "waiting_human":
                    if not owner_id:
                        raise ContractError("Autopilot human_owner_member_id is required for actions")
                    actions.append(
                        {
                            "action_id": f"{node_id}-{run_id}",
                            "gate_id": node_id,
                            "title": f"{item.get('label', node_id)}处理",
                            "status": "open",
                            "owner_member_id": owner_id,
                            "item_count": _action_count(artifact),
                            "summary": item["result_summary"],
                            "issue_id": item.get("issue_id"),
                            "issue_identifier": item.get("issue_identifier"),
                        }
                    )
            nodes.append(item)
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
