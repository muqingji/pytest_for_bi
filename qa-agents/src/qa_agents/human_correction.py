"""Human-directed recovery after the automatic Test Case IR budget is exhausted."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from .contracts import artifact_hash_from_mapping, content_hash
from .errors import ContractError, RetryableAgentError, SecurityPolicyError
from .security import SecurityPolicy
from .storage import ArtifactStore


CommandRunner = Callable[[list[str], Path], Mapping[str, Any]]
REQUEST_FILE = "human-correction-request.json"
DECISION_FILE = "human-correction-decision.json"
OUTCOME_FILE = "human-correction-outcome.json"
STATE_FILE = "human-correction-state.json"


def _first_plain_sentence(text: str, limit: int = 120) -> str:
    """Keep the leading sentence of a technical message for display."""
    if len(text) <= limit:
        return text
    for separator in ("。", "；", "；", "\n", ". "):
        position = text.find(separator)
        if 0 < position <= limit:
            return text[: position + len(separator)]
    return text[:limit].rstrip() + "…"


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Invalid or missing {label}: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object")
    return value


def _verify_hash(value: Mapping[str, Any], field: str, label: str) -> None:
    unhashed = {key: item for key, item in value.items() if key != field}
    if value.get(field) != content_hash(unhashed):
        raise ContractError(f"{label} hash is invalid")


def _artifact(path: Path, artifact_id: str, security: SecurityPolicy) -> dict[str, Any]:
    value = _read(path, artifact_id)
    if value.get("artifact_id") != artifact_id:
        raise ContractError(f"Expected Artifact {artifact_id}: {path}")
    if value.get("artifact_hash") != artifact_hash_from_mapping(value):
        raise ContractError(f"Artifact hash mismatch: {artifact_id}")
    security.assert_no_secret_values(value)
    return value


def _policy(path: Path) -> dict[str, Any]:
    value = _read(path, "human correction policy")
    if value.get("schema_version") != "human-test-design-correction-policy/1.0":
        raise ContractError("Human correction policy schema_version is invalid")
    if value.get("node_id") != "human_test_design_correction":
        raise ContractError("Human correction policy node_id is invalid")
    if value.get("automatic_budget_reset") is not False:
        raise SecurityPolicyError("Human correction must not reset the automatic budget")
    if value.get("required_revalidation") != ["A09", "N04"]:
        raise ContractError("Human correction must require A09 and N04 revalidation")
    if value.get("temporary_policy") is True and value.get(
        "production_release_authority"
    ) is not False:
        raise SecurityPolicyError("Temporary human correction cannot grant release authority")
    for field in ("allowed_actor_ids", "allowed_roles", "allowed_multica_member_ids"):
        if not isinstance(value.get(field), list) or not value[field]:
            raise ContractError(f"Human correction policy {field} is invalid")
    multica = value.get("multica")
    if not isinstance(multica, Mapping):
        raise ContractError("Human correction Multica policy is missing")
    if multica.get("assignee_member_id") not in value["allowed_multica_member_ids"]:
        raise SecurityPolicyError("Human correction assignee is unauthorized")
    if multica.get("initial_status") != "in_review":
        raise ContractError("Human correction must open in Multica in_review")
    if multica.get("decision_statuses") != {
        "done": "directed_correction",
        "cancelled": "terminate",
    }:
        raise ContractError("Human correction Multica status mapping is invalid")
    return value


def _bound_inputs(
    design: Mapping[str, Any],
    review: Mapping[str, Any],
    n04: Mapping[str, Any],
) -> tuple[str, str, str, list[dict[str, Any]]]:
    identities = {
        (
            str(item.get("workflow_run_id", "")),
            str(item.get("workflow_mode", "")),
            str(item.get("source_snapshot_id", "")),
        )
        for item in (design, review, n04)
    }
    if len(identities) != 1 or not all(next(iter(identities))):
        raise ContractError("Human correction Artifacts belong to different runs")
    workflow_run_id, workflow_mode, source_snapshot_id = identities.pop()
    payload = n04.get("payload")
    if not isinstance(payload, Mapping):
        raise ContractError("Human correction N04 payload is invalid")
    attempt = payload.get("correction_attempt")
    max_attempts = payload.get("max_correction_attempts")
    if (
        payload.get("valid") is not False
        or payload.get("next_node") != "human"
        or payload.get("g02_status") != "not_started"
        or not isinstance(attempt, int)
        or not isinstance(max_attempts, int)
        or attempt < max_attempts
    ):
        raise ContractError("Human correction requires an exhausted N04 human route")
    if payload.get("test_design_artifact_hash") != design.get("artifact_hash"):
        raise ContractError("Human correction N04 does not bind A08")
    if payload.get("oracle_review_artifact_hash") != review.get("artifact_hash"):
        raise ContractError("Human correction N04 does not bind A09")
    issues = payload.get("issues")
    if not isinstance(issues, list) or not issues:
        raise ContractError("Human correction requires unresolved N04 issues")
    directives = []
    for index, issue in enumerate(issues, 1):
        if not isinstance(issue, Mapping):
            raise ContractError("Human correction N04 issue is invalid")
        issue_id = str(issue.get("id") or f"N04-H{index:03d}")
        recommendation = str(issue.get("recommendation", "")).strip()
        if not recommendation:
            raise ContractError(f"Human correction issue {issue_id} has no recommendation")
        directives.append(
            {
                "directive_id": issue_id,
                "issue_code": issue.get("issue_code"),
                "human_title": issue.get("human_title"),
                "severity": issue.get("severity", "error"),
                "case_id": issue.get("case_id"),
                "expected_id": issue.get("expected_id"),
                "plain_summary": issue.get("plain_summary"),
                "message": issue.get("message"),
                "recommendation": recommendation,
                "source_refs": list(issue.get("source_refs", [])),
                "route_to": "A08",
            }
        )
    return workflow_run_id, workflow_mode, source_snapshot_id, directives


def render_human_correction_markdown(request: Mapping[str, Any]) -> str:
    directives = []
    for item in request["directives"]:
        title = str(item.get("human_title") or "").strip()
        headline = title or str(item.get("issue_code") or item["directive_id"])
        lines = [f"### {item['directive_id']} - {headline}", ""]
        plain = str(item.get("plain_summary") or "").strip()
        problem = plain or _first_plain_sentence(str(item.get("message") or ""))
        if problem:
            lines.append(f"- 问题：{problem}")
        if item.get("recommendation"):
            lines.append(f"- 修正方案：{item['recommendation']}")
        message = str(item.get("message") or "").strip()
        if message and message != problem:
            lines.append(f"- 技术细节：{message}")
        directives.append("\n".join(lines))
    return (
        "# 测试设计人工修正\n\n"
        f"- 工作流：`{request['workflow_run_id']}`\n"
        f"- 修正预算：`{request['budget']['correction_attempt']}/"
        f"{request['budget']['max_correction_attempts']}`（不重置）\n\n"
        "请决定是否授权以下修正：\n\n"
        "- 将本 Issue 置为 **done**：授权全部修正，系统将生成新的 A08 修正版并重新校验，"
        "流程自动继续。\n"
        "- 置为 **cancelled**：终止当前流程。\n"
        "- 保持 **in_review**：流程保持暂停。\n\n"
        + "\n\n".join(directives)
    )


def prepare_human_correction_request(
    design_path: Path,
    review_path: Path,
    n04_path: Path,
    policy_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
    multica_parent_issue_id: str | None = None,
) -> dict[str, Any]:
    security = security or SecurityPolicy()
    policy = _policy(policy_path)
    design = _artifact(design_path, "a08-test-design-ir", security)
    review = _artifact(review_path, "a09-oracle-coverage-review", security)
    n04 = _artifact(n04_path, "n04-test-case-ir-validation", security)
    workflow_run_id, workflow_mode, snapshot_id, directives = _bound_inputs(
        design, review, n04
    )
    n04_payload = n04["payload"]
    core = {
        "schema_version": "human-test-design-correction-request/1.0",
        "node_id": "human_test_design_correction",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": snapshot_id,
        "status": "needs_human",
        "decision": "pending",
        "upstream_artifacts": [
            {"artifact_id": item["artifact_id"], "artifact_hash": item["artifact_hash"]}
            for item in (design, review, n04)
        ],
        "budget": {
            "correction_attempt": n04_payload["correction_attempt"],
            "max_correction_attempts": n04_payload["max_correction_attempts"],
            "automatic_budget_reset": False,
            "next_attempt": n04_payload["correction_attempt"] + 1,
        },
        "directives": directives,
        "policy": {
            "policy_hash": content_hash(policy),
            "allowed_actor_ids": policy["allowed_actor_ids"],
            "allowed_roles": policy["allowed_roles"],
            "allowed_multica_member_ids": policy["allowed_multica_member_ids"],
            "required_revalidation": policy["required_revalidation"],
            "production_release_authority": policy["production_release_authority"],
        },
        "multica_control": dict(policy["multica"]),
        "decision_contract": "human-test-design-correction-decision/1.0",
        "outcome_contract": "human-test-design-correction-outcome/1.0",
    }
    if multica_parent_issue_id:
        core["multica_control"]["parent_issue_id"] = multica_parent_issue_id
    request_path = output_dir / REQUEST_FILE
    store = ArtifactStore(output_dir)
    if request_path.exists():
        existing = _read(request_path, "human correction request")
        _verify_hash(existing, "request_hash", "Human correction request")
        comparable = {
            key: value
            for key, value in existing.items()
            if key not in {"request_hash", "created_at"}
        }
        if comparable != core:
            raise ContractError("Existing human correction request is stale")
        return existing
    request = {
        **core,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    request["request_hash"] = content_hash(request)
    store.write_json(REQUEST_FILE, request)
    store.write_text("human-correction-request.md", render_human_correction_markdown(request))
    state = {
        "schema_version": "human-test-design-correction-state/1.0",
        "node_id": request["node_id"],
        "workflow_run_id": workflow_run_id,
        "request_hash": request["request_hash"],
        "state": "prepared",
        "issue_id": None,
        "observed_multica_status": None,
        "processed_event_id": None,
        "next_node": None,
    }
    state["state_hash"] = content_hash(state)
    store.write_json(STATE_FILE, state)
    return request


def _runner(args: list[str], cwd: Path) -> Mapping[str, Any]:
    completed = subprocess.run(
        ["multica", *args], cwd=cwd, check=False, capture_output=True, text=True
    )
    if completed.returncode != 0:
        raise RetryableAgentError(
            completed.stderr.strip() or completed.stdout.strip() or "Multica command failed"
        )
    try:
        value = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError as error:
        raise ContractError("Multica command returned invalid JSON") from error
    if not isinstance(value, Mapping):
        raise ContractError("Multica command must return an object")
    return value


def _state(store: ArtifactStore, value: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: item for key, item in value.items() if key != "state_hash"}
    result["state_hash"] = content_hash(result)
    store.write_json(STATE_FILE, result)
    return result


def _request_policy(
    request_path: Path, policy_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = _read(request_path, "human correction request")
    _verify_hash(request, "request_hash", "Human correction request")
    policy = _policy(policy_path)
    if request.get("policy", {}).get("policy_hash") != content_hash(policy):
        raise ContractError("Human correction request policy is stale")
    return request, policy


def open_multica_human_correction(
    request_path: Path,
    policy_path: Path,
    output_dir: Path,
    *,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    request, policy = _request_policy(request_path, policy_path)
    runner = runner or _runner
    store = ArtifactStore(output_dir)
    state = _read(output_dir / STATE_FILE, "human correction state")
    _verify_hash(state, "state_hash", "Human correction state")
    if state.get("request_hash") != request["request_hash"]:
        raise ContractError("Human correction state is stale")
    if state.get("issue_id") and state.get("state") != "opening_review":
        return state
    multica = policy["multica"]
    workspace = ["--workspace-id", multica["workspace_id"]]
    if not state.get("issue_id"):
        short_hash = request["request_hash"].removeprefix("sha256:")[:12]
        parent_args = []
        parent_issue_id = request["multica_control"].get("parent_issue_id")
        if parent_issue_id:
            parent_args = ["--parent", parent_issue_id]
        created = runner(
            [
                "issue", "create",
                "--title", f"Human A08 correction {request['workflow_run_id']} [{short_hash}]",
                "--description-file", "human-correction-request.md",
                "--attachment", REQUEST_FILE,
                "--assignee-id", multica["assignee_member_id"],
                "--project", multica["project_id"],
                "--status", "todo",
                "--priority", "high",
                *parent_args,
                "--output", "json",
                *workspace,
            ],
            request_path.parent,
        )
        if not str(created.get("id", "")) or created.get("workspace_id") != multica["workspace_id"]:
            raise ContractError("Multica did not create the human correction Issue")
        state = _state(
            store,
            {**state, "state": "opening_review", "issue_id": created["id"]},
        )
    issue_id = str(state["issue_id"])
    metadata = {
        "qa_item_type": "human_action",
        "qa_node_id": request["node_id"],
        "qa_action_required": "true",
        "qa_request_hash": request["request_hash"],
        "qa_policy_hash": request["policy"]["policy_hash"],
        "qa_visible_in_workflow_center": "false",
        "qa_workflow_run_id": request["workflow_run_id"],
    }
    for key, value in metadata.items():
        runner(
            [
                "issue", "metadata", "set", issue_id,
                "--key", key, "--value", value, "--type", "string",
                "--output", "json", *workspace,
            ],
            request_path.parent,
        )
    runner(
        ["issue", "status", issue_id, "in_review", "--output", "json", *workspace],
        request_path.parent,
    )
    return _state(
        store,
        {**state, "state": "waiting_for_review", "observed_multica_status": "in_review"},
    )


def _decision(
    request: Mapping[str, Any], policy: Mapping[str, Any], issue: Mapping[str, Any]
) -> dict[str, Any]:
    multica = policy["multica"]
    if (
        issue.get("workspace_id") != multica["workspace_id"]
        or issue.get("project_id") != multica["project_id"]
    ):
        raise SecurityPolicyError("Human correction Issue scope is invalid")
    if issue.get("assignee_type") != "member" or issue.get(
        "assignee_id"
    ) not in policy["allowed_multica_member_ids"]:
        raise SecurityPolicyError("Human correction Issue reviewer is unauthorized")
    metadata = issue.get("metadata")
    expected = {
        "qa_item_type": "human_action",
        "qa_node_id": request["node_id"],
        "qa_action_required": "true",
        "qa_request_hash": request["request_hash"],
        "qa_policy_hash": request["policy"]["policy_hash"],
        "qa_visible_in_workflow_center": "false",
        "qa_workflow_run_id": request["workflow_run_id"],
    }
    if not isinstance(metadata, Mapping) or any(
        metadata.get(key) != value for key, value in expected.items()
    ):
        raise ContractError("Human correction Issue metadata is stale")
    status = str(issue.get("status", ""))
    decision = multica["decision_statuses"].get(status)
    if decision not in policy["allowed_decisions"]:
        raise ContractError("Human correction Issue has no terminal decision")
    updated_at = str(issue.get("updated_at", ""))
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("Human correction Issue updated_at is invalid") from error
    event_id = content_hash(
        {
            "issue_id": issue["id"],
            "status": status,
            "updated_at": updated_at,
            "request_hash": request["request_hash"],
        }
    )
    value = {
        "schema_version": "human-test-design-correction-decision/1.0",
        "node_id": request["node_id"],
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "decision": decision,
        "decided_at": parsed.isoformat(),
        "actor": {
            "type": "human",
            "id": policy["allowed_actor_ids"][0],
            "role": policy["allowed_roles"][0],
            "multica_member_id": issue["assignee_id"],
        },
        "authorized_directive_ids": (
            [item["directive_id"] for item in request["directives"]]
            if decision == "directed_correction"
            else []
        ),
        "automatic_budget_reset": False,
        "required_revalidation": ["A09", "N04"],
        "multica_event": {
            "workspace_id": issue["workspace_id"],
            "issue_id": issue["id"],
            "event_id": event_id,
            "status": status,
            "identity_evidence_mode": multica["identity_evidence_mode"],
        },
    }
    value["decision_hash"] = content_hash(value)
    return value


def validate_human_correction_decision(
    request: Mapping[str, Any], decision: Mapping[str, Any], policy: Mapping[str, Any]
) -> None:
    _verify_hash(request, "request_hash", "Human correction request")
    _verify_hash(decision, "decision_hash", "Human correction decision")
    if request.get("policy", {}).get("policy_hash") != content_hash(policy):
        raise ContractError("Human correction policy binding is stale")
    for field in ("node_id", "workflow_run_id", "source_snapshot_id", "request_hash"):
        if decision.get(field) != request.get(field):
            raise ContractError(f"Human correction decision {field} is stale")
    actor = decision.get("actor")
    if not isinstance(actor, Mapping) or actor.get("type") != "human":
        raise SecurityPolicyError("Human correction decision requires a human actor")
    if actor.get("id") not in policy["allowed_actor_ids"]:
        raise SecurityPolicyError("Human correction actor is unauthorized")
    if actor.get("role") not in policy["allowed_roles"]:
        raise SecurityPolicyError("Human correction role is unauthorized")
    if actor.get("multica_member_id") not in policy["allowed_multica_member_ids"]:
        raise SecurityPolicyError("Human correction Multica member is unauthorized")
    if decision.get("automatic_budget_reset") is not False:
        raise SecurityPolicyError("Human correction decision cannot reset the budget")
    if decision.get("decision") == "directed_correction":
        required = {item["directive_id"] for item in request["directives"]}
        authorized = decision.get("authorized_directive_ids")
        if not isinstance(authorized, list) or set(authorized) != required:
            raise ContractError("Human correction must authorize every current directive")


def project_human_correction_state(
    request: Mapping[str, Any],
    outcome: Mapping[str, Any],
    state: Mapping[str, Any],
    run_manifest_path: Path,
    workspace_manifest_path: Path,
) -> None:
    """Project the authoritative correction outcome into both operational manifests."""
    run_manifest = _read(run_manifest_path, "Multica run manifest")
    workspace_manifest = _read(workspace_manifest_path, "Multica workspace manifest")
    workflow_run_id = request["workflow_run_id"]
    request_hash = request["request_hash"]
    if run_manifest.get("workflow_run_id") != workflow_run_id:
        raise ContractError("Human correction run manifest belongs to another workflow")
    run_correction = run_manifest.get("human_correction")
    if (
        not isinstance(run_correction, Mapping)
        or run_correction.get("request_hash") != request_hash
    ):
        raise ContractError("Human correction run manifest request binding is stale")
    pilot_state = workspace_manifest.get("pilot_state")
    workspace_correction = (
        pilot_state.get("human_correction") if isinstance(pilot_state, Mapping) else None
    )
    if (
        not isinstance(workspace_correction, Mapping)
        or workspace_correction.get("request_hash") != request_hash
    ):
        raise ContractError("Human correction workspace manifest request binding is stale")

    next_node = outcome.get("next_node")
    projected_status = (
        "done" if outcome.get("decision") == "directed_correction" else "cancelled"
    )
    projection = {
        "status": projected_status,
        "state": state.get("state"),
        "decision_hash": outcome.get("decision_hash"),
        "outcome_hash": outcome.get("outcome_hash"),
        "observed_multica_status": state.get("observed_multica_status"),
        "next_node": next_node,
    }
    run_manifest["human_correction"] = {**run_correction, **projection}
    run_manifest["current_node"] = next_node
    workspace_manifest["pilot_state"] = {
        **pilot_state,
        "current_node": next_node,
        "human_correction": {**workspace_correction, **projection},
    }

    ArtifactStore(run_manifest_path.parent).write_json(
        run_manifest_path.name, run_manifest
    )
    ArtifactStore(workspace_manifest_path.parent).write_json(
        workspace_manifest_path.name, workspace_manifest
    )


def sync_multica_human_correction(
    request_path: Path,
    current_n04_path: Path,
    policy_path: Path,
    output_dir: Path,
    *,
    runner: CommandRunner | None = None,
    run_manifest_path: Path | None = None,
    workspace_manifest_path: Path | None = None,
) -> dict[str, Any]:
    if (run_manifest_path is None) != (workspace_manifest_path is None):
        raise ContractError(
            "Human correction manifest projection requires both manifest paths"
        )
    request, policy = _request_policy(request_path, policy_path)
    n04 = _artifact(current_n04_path, "n04-test-case-ir-validation", SecurityPolicy())
    expected_n04 = next(
        item["artifact_hash"]
        for item in request["upstream_artifacts"]
        if item["artifact_id"] == "n04-test-case-ir-validation"
    )
    if n04["artifact_hash"] != expected_n04:
        raise ContractError("Human correction request is stale because N04 changed")
    runner = runner or _runner
    store = ArtifactStore(output_dir)
    state = _read(output_dir / STATE_FILE, "human correction state")
    _verify_hash(state, "state_hash", "Human correction state")
    if state.get("request_hash") != request["request_hash"] or not state.get("issue_id"):
        raise ContractError("Human correction state has no bound Multica Issue")
    outcome_path = output_dir / OUTCOME_FILE
    if outcome_path.exists():
        outcome = _read(outcome_path, "human correction outcome")
        _verify_hash(outcome, "outcome_hash", "Human correction outcome")
        if run_manifest_path is not None and workspace_manifest_path is not None:
            project_human_correction_state(
                request, outcome, state, run_manifest_path, workspace_manifest_path
            )
        return outcome
    issue = runner(
        [
            "issue", "get", str(state["issue_id"]), "--output", "json",
            "--workspace-id", policy["multica"]["workspace_id"],
        ],
        request_path.parent,
    )
    if issue.get("id") != state["issue_id"]:
        raise SecurityPolicyError("Multica returned another human correction Issue")
    status = str(issue.get("status", ""))
    if status in {"todo", "in_progress", "in_review", "blocked"}:
        return _state(
            store,
            {**state, "state": "waiting_for_review", "observed_multica_status": status},
        )
    decision = _decision(request, policy, issue)
    validate_human_correction_decision(request, decision, policy)
    if decision["decision"] == "directed_correction":
        action, next_node, terminal_state = "resume_with_human_direction", "A08", "authorized"
        status_value = "completed"
    else:
        action, next_node, terminal_state = "terminate", None, "terminated"
        status_value = "cancelled"
    outcome = {
        "schema_version": "human-test-design-correction-outcome/1.0",
        "node_id": request["node_id"],
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "decision_hash": decision["decision_hash"],
        "decision": decision["decision"],
        "status": status_value,
        "action": action,
        "next_node": next_node,
        "automatic_budget_reset": False,
        "next_correction_attempt": request["budget"]["next_attempt"],
        "required_revalidation": ["A09", "N04"],
        "idempotency_key": content_hash(
            {"request_hash": request["request_hash"], "decision_hash": decision["decision_hash"]}
        ),
    }
    outcome["outcome_hash"] = content_hash(outcome)
    store.write_json(DECISION_FILE, decision)
    store.write_json(OUTCOME_FILE, outcome)
    final_state = _state(
        store,
        {
            **state,
            "state": terminal_state,
            "observed_multica_status": status,
            "processed_event_id": decision["multica_event"]["event_id"],
            "decision_hash": decision["decision_hash"],
            "outcome_hash": outcome["outcome_hash"],
            "next_node": next_node,
        },
    )
    if run_manifest_path is not None and workspace_manifest_path is not None:
        project_human_correction_state(
            request, outcome, final_state, run_manifest_path, workspace_manifest_path
        )
    return outcome
