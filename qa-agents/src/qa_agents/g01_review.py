"""Content-addressed G01 human review flow controlled by a Multica comment."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
import json
from pathlib import Path
import subprocess
from typing import Any

from .card_copy import scope_review_title
from .contracts import content_hash
from .multica_cli import resolve_multica_binary
from .errors import ContractError, RetryableAgentError, SecurityPolicyError
from .gates import build_scope_review_outcome, validate_scope_review_decision
from .security import SecurityPolicy
from .storage import ArtifactStore


CommandRunner = Callable[[list[str], Path], Any]
REQUEST_FILE = "g01-review-request.json"
DECISION_FILE = "g01-review-decision.json"
OUTCOME_FILE = "g01-review-outcome.json"
STATE_FILE = "g01-workflow-state.json"
PROTOCOL_MARKER = "G01 Decision Protocol"
PROTOCOL_VERSION = "1.0"


def _read_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"Missing {label}: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Invalid {label}: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object")
    return value


def _validate_hash(value: Mapping[str, Any], field: str, label: str) -> None:
    unhashed = {key: item for key, item in value.items() if key != field}
    if value.get(field) != content_hash(unhashed):
        raise ContractError(f"{label} hash is invalid")


def _validate_adapter_policy(
    adapter: Mapping[str, Any], gate_policy: Mapping[str, Any]
) -> dict[str, Any]:
    if adapter.get("schema_version") != "g01-multica-adapter-policy/1.0":
        raise ContractError("G01 Multica adapter policy schema_version is invalid")
    if adapter.get("gate_id") != "G01":
        raise ContractError("G01 Multica adapter policy gate_id is invalid")
    if adapter.get("gate_policy_hash") != content_hash(gate_policy):
        raise ContractError("G01 Multica adapter policy is bound to another Gate policy")
    if adapter.get("require_human_comment") is not True:
        raise SecurityPolicyError("G01 Multica adapter must require a human comment")
    actor_ids = adapter.get("allowed_actor_ids")
    roles = adapter.get("allowed_roles")
    member_ids = adapter.get("allowed_multica_member_ids")
    if not isinstance(actor_ids, list) or len(actor_ids) != 1 or not actor_ids[0]:
        raise ContractError("G01 Multica adapter requires one allowed actor ID")
    if not isinstance(roles, list) or len(roles) != 1 or roles[0] not in gate_policy.get(
        "allowed_roles", []
    ):
        raise ContractError("G01 Multica adapter requires one allowed Gate role")
    if not isinstance(member_ids, list) or len(member_ids) != 1 or not member_ids[0]:
        raise ContractError("G01 Multica adapter requires one allowed member ID")
    multica = adapter.get("multica")
    if not isinstance(multica, Mapping):
        raise ContractError("G01 Multica adapter configuration is missing")
    required = ("workspace_id", "project_id", "assignee_member_id", "initial_status")
    if any(not str(multica.get(field, "")) for field in required):
        raise ContractError("G01 Multica adapter identity fields are incomplete")
    if multica.get("assignee_member_id") not in member_ids:
        raise SecurityPolicyError("G01 Multica assignee is not an allowed reviewer")
    if multica.get("initial_status") != "in_review":
        raise ContractError("G01 Multica initial status must be in_review")
    if multica.get("decision_statuses") != {
        "approved": "done",
        "request_changes": "blocked",
        "rejected": "cancelled",
    }:
        raise ContractError("G01 Multica decision status mapping is invalid")
    return dict(adapter)


def _load_bound_inputs(
    request_path: Path,
    gate_policy_path: Path,
    adapter_policy_path: Path,
    security: SecurityPolicy,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request = _read_mapping(request_path, "G01 review request")
    _validate_hash(request, "request_hash", "G01 review request")
    if request.get("gate_id") != "G01" or request.get("decision") != "pending":
        raise ContractError("G01 Multica review requires a pending G01 request")
    gate_policy = _read_mapping(gate_policy_path, "G01 Gate policy")
    if request.get("review_policy", {}).get("policy_hash") != content_hash(gate_policy):
        raise ContractError("G01 review request policy binding is stale")
    adapter = _validate_adapter_policy(
        _read_mapping(adapter_policy_path, "G01 Multica adapter policy"), gate_policy
    )
    security.assert_no_secret_values(request)
    security.assert_no_secret_values(gate_policy)
    security.assert_no_secret_values(adapter)
    return request, gate_policy, adapter


def _default_runner(args: list[str], cwd: Path) -> Any:
    completed = subprocess.run(
        [resolve_multica_binary(), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RetryableAgentError(f"Multica command failed: {message}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ContractError("Multica command returned invalid JSON") from error


def _write_state(store: ArtifactStore, state: Mapping[str, Any]) -> dict[str, Any]:
    value = {key: item for key, item in state.items() if key != "state_hash"}
    value["state_hash"] = content_hash(value)
    store.write_json(STATE_FILE, value)
    return value


def _validate_issue(
    issue: Mapping[str, Any], adapter: Mapping[str, Any], *, require_metadata: bool
) -> None:
    multica = adapter["multica"]
    if issue.get("workspace_id") != multica["workspace_id"]:
        raise SecurityPolicyError("G01 issue belongs to another Multica workspace")
    allowed_project_ids = set(multica.get("review_project_ids", [multica["project_id"]]))
    if issue.get("project_id") not in allowed_project_ids:
        raise SecurityPolicyError("G01 issue belongs to another Multica project")
    if issue.get("assignee_type") != "member":
        raise SecurityPolicyError("G01 issue must be assigned to a human member")
    if issue.get("assignee_id") not in adapter["allowed_multica_member_ids"]:
        raise SecurityPolicyError("G01 issue is not assigned to an authorized reviewer")
    if require_metadata and not isinstance(issue.get("metadata"), Mapping):
        raise ContractError("G01 issue metadata is missing")


def _expected_metadata(
    request: Mapping[str, Any], adapter: Mapping[str, Any]
) -> dict[str, str]:
    return {
        "qa_gate_id": "G01",
        "qa_request_hash": str(request["request_hash"]),
        "qa_policy_hash": str(request["review_policy"]["policy_hash"]),
        "qa_adapter_policy_hash": content_hash(adapter),
        "qa_workflow_run_id": str(request["workflow_run_id"]),
        "qa_decision_protocol": f"g01-comment-table/{PROTOCOL_VERSION}",
    }


def open_multica_scope_review(
    request_path: Path,
    gate_policy_path: Path,
    adapter_policy_path: Path,
    output_dir: Path,
    *,
    issue_id: str | None = None,
    runner: CommandRunner | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Create or bind exactly one Multica issue for a pending G01 request."""

    security = security or SecurityPolicy()
    request, _, adapter = _load_bound_inputs(
        request_path, gate_policy_path, adapter_policy_path, security
    )
    runner = runner or _default_runner
    store = ArtifactStore(output_dir)
    state_path = output_dir / STATE_FILE
    if state_path.exists():
        state = _read_mapping(state_path, "G01 workflow state")
        _validate_hash(state, "state_hash", "G01 workflow state")
        if state.get("request_hash") != request["request_hash"]:
            raise ContractError("G01 workflow state belongs to another request")
        if issue_id and state.get("issue_id") != issue_id:
            raise ContractError("G01 workflow state is already bound to another issue")
        if state.get("issue_id") and state.get("state") != "opening_review":
            return state
    else:
        state = _write_state(
            store,
            {
                "schema_version": "workflow-gate-state/1.0",
                "gate_id": "G01",
                "workflow_run_id": request["workflow_run_id"],
                "source_snapshot_id": request["source_snapshot_id"],
                "request_hash": request["request_hash"],
                "adapter_policy_hash": content_hash(adapter),
                "state": "prepared",
                "issue_id": None,
                "observed_multica_status": None,
                "processed_event_id": None,
                "next_node": None,
            },
        )

    multica = adapter["multica"]
    workspace_args = ["--workspace-id", multica["workspace_id"]]
    if not state.get("issue_id"):
        if issue_id:
            bound = runner(
                ["issue", "get", issue_id, "--output", "json", *workspace_args],
                request_path.parent,
            )
            if not isinstance(bound, Mapping) or bound.get("id") != issue_id:
                raise ContractError("Multica did not return the requested G01 issue")
            if bound.get("assignee_type") != "member" or bound.get("assignee_id") not in adapter["allowed_multica_member_ids"]:
                runner(
                    ["issue", "assign", issue_id, "--to-id", multica["assignee_member_id"], "--output", "json", *workspace_args],
                    request_path.parent,
                )
                bound = {**bound, "assignee_type": "member", "assignee_id": multica["assignee_member_id"]}
            _validate_issue(bound, adapter, require_metadata=False)
            created = bound
        else:
            created = runner(
                [
                    "issue",
                    "create",
                    "--title",
                    scope_review_title(request),
                    "--description-file",
                    "g01-review-request.md",
                    "--attachment",
                    REQUEST_FILE,
                    "--assignee-id",
                    multica["assignee_member_id"],
                    "--project",
                    multica["project_id"],
                    "--status",
                    "todo",
                    "--output",
                    "json",
                    *workspace_args,
                ],
                request_path.parent,
            )
            if not isinstance(created, Mapping):
                raise ContractError("Multica did not create a G01 issue")
            issue_id = str(created.get("id", ""))
            if not issue_id:
                raise ContractError("Multica did not return a G01 issue ID")
            _validate_issue(created, adapter, require_metadata=False)
        state = _write_state(
            store,
            {
                **state,
                "state": "opening_review",
                "issue_id": str(created["id"]),
                "observed_multica_status": str(created.get("status", "todo")),
            },
        )

    issue_id = str(state["issue_id"])
    # Binding an existing pilot card also replaces its hand-maintained body with the
    # deterministic request and copyable decision form.
    runner(
        [
            "issue",
            "update",
            issue_id,
            "--description-file",
            "g01-review-request.md",
            "--output",
            "json",
            *workspace_args,
        ],
        request_path.parent,
    )
    for key, value in _expected_metadata(request, adapter).items():
        runner(
            [
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
                *workspace_args,
            ],
            request_path.parent,
        )
    runner(
        ["issue", "status", issue_id, "in_review", "--output", "json", *workspace_args],
        request_path.parent,
    )
    return _write_state(
        store,
        {
            **state,
            "state": "waiting_for_review",
            "observed_multica_status": "in_review",
        },
    )


def _comment_values(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        for field in ("comments", "data", "items"):
            items = value.get(field)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, Mapping)]
    raise ContractError("Multica comment list returned an invalid payload")


def _is_protocol_comment(comment: Mapping[str, Any]) -> bool:
    content = str(comment.get("content", ""))
    return any(
        PROTOCOL_MARKER in line and PROTOCOL_VERSION in line
        for line in content.splitlines()
    )


_UNCLEAR_MARKERS = ("没看明白", "看不明白", "不清楚", "未看明白")

_BLANKET_CONFIRM_MARKERS = (
    "都忽略",
    "先都忽略",
    "全部忽略",
    "其余忽略",
    "其他忽略",
    "剩下忽略",
    "剩余忽略",
    "先忽略",
    "不用关注",
    "先都按",
    "技术问题以目前实现为准",
)

_VALIDATION_FEEDBACK_PREFIX = "G01 审核提交未通过校验"
_NON_DECISION_MARKERS = (
    "待 QA Owner 确认",
    "待 QA Owner 明确",
    "当前状态：待",
)



def _is_concise_comment(comment: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    content = str(comment.get("content", ""))
    if content.lstrip().startswith(_VALIDATION_FEEDBACK_PREFIX):
        return False
    if any(marker in content for marker in _NON_DECISION_MARKERS):
        return False
    return any(str(item.get("issue_id", "")) in content for item in request.get("issues", []))




def _blanket_confirmation_rationale(content: str, rows: list[dict[str, str]]) -> str | None:
    """Detect a human blanket confirmation that covers unanswered G01 items.

    Real reviewers often answer the main ambiguities one-by-one, then write a
    short trailing note such as "技术问题以目前实现为准，你先都忽略" for the
    remaining technical/findings items. Without this, C2 stays done in Multica
    while the workflow never leaves G01 because some issue IDs were omitted.
    """

    candidates: list[str] = []
    if rows:
        candidates.append(str(rows[-1].get("rationale", "")))
    candidates.append(content)
    for text_value in candidates:
        if any(marker in text_value for marker in _BLANKET_CONFIRM_MARKERS):
            cleaned = text_value.strip()
            if cleaned:
                return cleaned
    return None


def _parse_concise_responses(content: str, request: Mapping[str, Any]) -> list[dict[str, str]]:
    issue_ids = [str(item["issue_id"]) for item in request.get("issues", [])]
    occurrences: list[tuple[int, str]] = []
    for issue_id in issue_ids:
        start = content.find(issue_id)
        if start >= 0:
            occurrences.append((start, issue_id))
    occurrences.sort()
    found = {issue_id for _, issue_id in occurrences}
    missing = [issue_id for issue_id in issue_ids if issue_id not in found]
    rows: list[dict[str, str]] = []
    strip_chars = " `:-" + chr(10) + chr(9) + "："
    for index, (start, issue_id) in enumerate(occurrences):
        reply_start = start + len(issue_id)
        reply_end = occurrences[index + 1][0] if index + 1 < len(occurrences) else len(content)
        reply = content[reply_start:reply_end].strip(strip_chars)
        if not reply:
            raise ContractError(f"G01 concise review has a blank response: {issue_id}")
        unclear = any(marker in reply for marker in _UNCLEAR_MARKERS)
        rows.append({
            "issue_id": issue_id,
            "disposition": "return_to_a06" if unclear else "confirmed",
            "rationale": reply,
            "owner": "A06 需求与变更对齐" if unclear else "QA Owner",
        })
    if missing:
        blanket = _blanket_confirmation_rationale(content, rows)
        if not blanket:
            descriptions = []
            by_id = {str(item.get("issue_id")): item for item in request.get("issues", [])}
            for number, issue_id in enumerate(missing, start=1):
                item = by_id.get(issue_id, {})
                summary = str(item.get("plain_summary") or item.get("summary") or "待确认项")
                action = str(item.get("confirm_action") or "请明确审核结论")
                category = str(item.get("title") or item.get("issue_type") or "待确认审核项")
                requirements = item.get("related_requirements") or item.get("requirements") or []
                req_text = "、".join(str(x) for x in requirements) if requirements else "未关联具体需求"
                descriptions.append(
                    f"{number}. **{category}**（`{issue_id}`）\n"
                    f"   - 问题：{summary}\n"
                    f"   - 需要确认：{action}\n"
                    f"   - 涉及需求：{req_text}"
                )
            raise ContractError(
                "G01 审核评论未覆盖以下审核项（共 " + str(len(descriptions)) + " 条）：\n\n"
                + "\n".join(descriptions)
                + "\n\n本次只需审核以上缺失项，其他已提交审核项无需重复审核。"
            )
        for issue_id in missing:
            rows.append(
                {
                    "issue_id": issue_id,
                    "disposition": "confirmed",
                    "rationale": blanket,
                    "owner": "QA Owner",
                }
            )
    order = {issue_id: index for index, issue_id in enumerate(issue_ids)}
    rows.sort(key=lambda item: order.get(str(item.get("issue_id", "")), 10**9))
    return rows

def _parse_comment_table(content: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    aliases = {
        "G01 Decision Protocol": "protocol",
        "G01 决策协议": "protocol",
        "Request Hash": "request_hash",
        "请求哈希": "request_hash",
        "Decision": "decision",
        "决策": "decision",
        "Overall Reason": "reason",
        "总体理由": "reason",
        "Test Rules": "test_rules",
        "测试规则": "test_rules",
    }
    headers: dict[str, Any] = {}
    resolutions: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if "|" not in line:
            continue
        columns = [part.strip() for part in line.strip("|").split("|")]
        if all(not part or set(part) <= {"-", ":"} for part in columns):
            continue
        if len(columns) == 2 and columns[0] in aliases:
            key = aliases[columns[0]]
            if key in headers:
                raise ContractError(f"G01 review comment repeats field: {columns[0]}")
            value: Any = columns[1]
            if key == "test_rules" and value.lstrip().startswith("{"):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as error:
                    raise ContractError("G01 review Test Rules must be valid JSON") from error
                if not isinstance(value, dict):
                    raise ContractError("G01 review Test Rules JSON must be an object")
            headers[key] = value
            continue
        if len(columns) == 4 and columns[0] not in {"Issue ID", "问题 ID"}:
            issue_id, disposition, rationale, owner = columns
            if not all((issue_id, disposition, rationale, owner)):
                raise ContractError("G01 review resolution rows cannot contain blank fields")
            if issue_id in seen_ids:
                raise ContractError(f"G01 review comment repeats issue: {issue_id}")
            seen_ids.add(issue_id)
            resolutions.append(
                {
                    "issue_id": issue_id,
                    "disposition": disposition,
                    "rationale": rationale,
                    "owner": owner,
                }
            )
    required = {"protocol", "request_hash", "decision", "reason"}
    missing = sorted(required - headers.keys())
    if missing:
        raise ContractError(f"G01 review comment is missing fields: {', '.join(missing)}")
    blank = sorted(
        key for key in required
        if not isinstance(headers[key], str) or not headers[key].strip()
    )
    if blank:
        raise ContractError(f"G01 review comment has blank fields: {', '.join(blank)}")
    if headers["protocol"] != PROTOCOL_VERSION:
        raise ContractError("G01 review comment protocol version is invalid")
    return headers, resolutions


def _comment_decision(
    request: Mapping[str, Any],
    gate_policy: Mapping[str, Any],
    adapter: Mapping[str, Any],
    issue: Mapping[str, Any],
    comment: Mapping[str, Any],
) -> dict[str, Any]:
    creator_type = comment.get("creator_type", comment.get("author_type"))
    creator_id = str(comment.get("creator_id", comment.get("author_id", "")))
    if creator_type != "member" or creator_id not in adapter["allowed_multica_member_ids"]:
        raise SecurityPolicyError("G01 decision comment was not authored by an authorized human")
    comment_id = str(comment.get("id", ""))
    if not comment_id:
        raise ContractError("G01 decision comment ID is missing")
    created_at = str(comment.get("created_at", ""))
    try:
        parsed_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("G01 decision comment created_at is invalid") from error
    if parsed_at.tzinfo is None:
        raise ContractError("G01 decision comment created_at must include a timezone")
    content = str(comment.get("content", ""))
    if _is_protocol_comment(comment):
        headers, rows = _parse_comment_table(content)
        if headers["request_hash"] != request["request_hash"]:
            raise ContractError("G01 decision comment request hash is stale")
    else:
        rows = _parse_concise_responses(content, request)
        has_return = any(row["disposition"] == "return_to_a06" for row in rows)
        headers = {
            "decision": "request_changes" if has_return else "approved",
            "reason": "存在未理解问题，自动回流 A06 重新对齐" if has_return else "已逐项回复并确认",
            "test_rules": "按逐项回复冻结的口径执行测试设计",
        }
    actor = {
        "type": "human",
        "id": adapter["allowed_actor_ids"][0],
        "role": adapter["allowed_roles"][0],
        "multica_member_id": creator_id,
    }
    approvals = [
        {"type": "human", "id": actor["id"], "role": actor["role"]}
    ]
    request_issues = {
        str(item.get("issue_id", "")): item for item in request.get("issues", [])
    }
    resolutions = [
        {
            **row,
            "approvals": approvals,
            "topic_key": request_issues.get(row["issue_id"], {}).get("dedupe_key", row["issue_id"]),
            "review_summary": request_issues.get(row["issue_id"], {}).get("plain_summary", ""),
        }
        for row in rows
    ]
    event_id = content_hash(
        {
            "issue_id": issue["id"],
            "comment_id": comment_id,
            "comment_hash": content_hash(str(comment.get("content", ""))),
            "request_hash": request["request_hash"],
        }
    )
    raw: dict[str, Any] = {
        "schema_version": "scope-review-decision/1.0",
        "gate_id": "G01",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "decision": headers["decision"],
        "decided_at": parsed_at.isoformat(),
        "actor": actor,
        "reason": headers["reason"],
        "test_rules": headers.get("test_rules", ""),
        "resolutions": resolutions,
        "multica_event": {
            "workspace_id": issue["workspace_id"],
            "issue_id": issue["id"],
            "comment_id": comment_id,
            "event_id": event_id,
        },
    }
    return validate_scope_review_decision(request, raw, gate_policy)


def sync_multica_scope_review(
    request_path: Path,
    gate_policy_path: Path,
    adapter_policy_path: Path,
    output_dir: Path,
    *,
    runner: CommandRunner | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile one authorized, request-bound review comment into a G01 outcome."""

    security = security or SecurityPolicy()
    request, gate_policy, adapter = _load_bound_inputs(
        request_path, gate_policy_path, adapter_policy_path, security
    )
    runner = runner or _default_runner
    store = ArtifactStore(output_dir)
    state = _read_mapping(output_dir / STATE_FILE, "G01 workflow state")
    _validate_hash(state, "state_hash", "G01 workflow state")
    if state.get("request_hash") != request["request_hash"] or not state.get("issue_id"):
        raise ContractError("G01 workflow state is not bound to an open review issue")

    decision_path = output_dir / DECISION_FILE
    outcome_path = output_dir / OUTCOME_FILE
    if decision_path.exists():
        decision = _read_mapping(decision_path, "G01 review decision")
        _validate_hash(decision, "decision_hash", "G01 review decision")
        validated = validate_scope_review_decision(
            request,
            {key: value for key, value in decision.items() if key != "decision_hash"},
            gate_policy,
        )
        if outcome_path.exists():
            outcome = _read_mapping(outcome_path, "G01 review outcome")
            _validate_hash(outcome, "outcome_hash", "G01 review outcome")
            if outcome.get("decision_hash") != validated["decision_hash"]:
                raise ContractError("G01 outcome does not bind the recorded decision")
        else:
            outcome = build_scope_review_outcome(request, validated, gate_policy)
            store.write_json(OUTCOME_FILE, outcome)
        terminal_state = {
            "approved": "resumed",
            "request_changes": "returned",
            "rejected": "terminated",
        }[validated["decision"]]
        event = validated.get("multica_event", {})
        _write_state(
            store,
            {
                **state,
                "state": terminal_state,
                "observed_multica_status": adapter["multica"]["decision_statuses"][
                    validated["decision"]
                ],
                "processed_event_id": event.get("event_id"),
                "decision_hash": validated["decision_hash"],
                "outcome_hash": outcome["outcome_hash"],
                "next_node": outcome["next_node"],
                "validation_message": None,
            },
        )
        return outcome

    multica = adapter["multica"]
    workspace_args = ["--workspace-id", multica["workspace_id"]]
    issue = runner(
        ["issue", "get", str(state["issue_id"]), "--output", "json", *workspace_args],
        request_path.parent,
    )
    if not isinstance(issue, Mapping) or issue.get("id") != state["issue_id"]:
        raise SecurityPolicyError("Multica returned a different G01 issue")
    _validate_issue(issue, adapter, require_metadata=True)
    metadata = issue["metadata"]
    expected_metadata = _expected_metadata(request, adapter)
    if any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise ContractError("G01 issue metadata does not match the review request")

    comment_payload = runner(
        [
            "issue",
            "comment",
            "list",
            str(state["issue_id"]),
            "--output",
            "json",
            "--compact",
            *workspace_args,
        ],
        request_path.parent,
    )
    processed_comment_id = str(metadata.get("qa_decision_comment_id", ""))
    processed_at = ""
    if processed_comment_id:
        for item in _comment_values(comment_payload):
            if str(item.get("id", "")) == processed_comment_id:
                processed_at = str(item.get("created_at", ""))
                break
    candidates = [
        item for item in _comment_values(comment_payload)
        if str(item.get("id", "")) != processed_comment_id
        and (not processed_at or str(item.get("created_at", "")) >= processed_at)
        and (_is_protocol_comment(item) or _is_concise_comment(item, request))
    ]
    if not candidates:
        observed_status = str(issue.get("status", ""))
        if observed_status in set(multica["decision_statuses"].values()):
            runner(
                [
                    "issue",
                    "status",
                    str(state["issue_id"]),
                    "in_review",
                    "--output",
                    "json",
                    *workspace_args,
                ],
                request_path.parent,
            )
            observed_status = "in_review"
        return _write_state(
            store,
            {
                **state,
                "state": "waiting_for_review",
                "observed_multica_status": observed_status,
                "validation_message": "No valid G01 decision comment exists; Issue status alone is ignored.",
            },
        )

    protocol_candidates = [item for item in candidates if _is_protocol_comment(item)]
    if protocol_candidates:
        comment = max(
            protocol_candidates,
            key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))),
        )
    else:
        ordered = sorted(
            candidates,
            key=lambda item: (str(item.get("created_at", "")), str(item.get("id", ""))),
        )
        latest = ordered[-1]
        comment = {
            **latest,
            "content": "\n\n".join(str(item.get("content", "")) for item in ordered),
        }
    try:
        decision = _comment_decision(request, gate_policy, adapter, issue, comment)
    except (ContractError, SecurityPolicyError) as error:
        candidate_comment_id = str(comment.get("id", ""))
        already_reported = (
            state.get("state") == "review_input_invalid"
            and state.get("candidate_comment_id") == candidate_comment_id
            and state.get("validation_message") == str(error)
        )
        _write_state(
            store,
            {
                **state,
                "state": "review_input_invalid",
                "observed_multica_status": str(issue.get("status", "")),
                "candidate_comment_id": candidate_comment_id,
                "validation_message": str(error),
            },
        )
        if not already_reported:
            runner(
                [
                    "issue",
                    "comment",
                    "add",
                    str(state["issue_id"]),
                    "--content",
                    (
                        "G01 审核提交未通过校验，流程仍保持 in_review。\n\n"
                        f"- 提交评论: `{candidate_comment_id}`\n"
                        f"- 原因: {error}\n\n"
                        "请修正后新增一条完整审核评论；系统不会使用不完整提交。"
                    ),
                    "--output",
                    "json",
                    *workspace_args,
                ],
                request_path.parent,
            )
        raise
    outcome = build_scope_review_outcome(request, decision, gate_policy)
    security.assert_no_secret_values(decision)
    security.assert_no_secret_values(outcome)

    for key, value in {
        "qa_decision_hash": decision["decision_hash"],
        "qa_outcome_hash": outcome["outcome_hash"],
        "qa_decision_comment_id": decision["multica_event"]["comment_id"],
        "qa_review_validation": "passed",
    }.items():
        runner(
            [
                "issue",
                "metadata",
                "set",
                str(state["issue_id"]),
                "--key",
                key,
                "--value",
                value,
                "--type",
                "string",
                "--output",
                "json",
                *workspace_args,
            ],
            request_path.parent,
        )
    target_status = multica["decision_statuses"][decision["decision"]]
    runner(
        [
            "issue",
            "status",
            str(state["issue_id"]),
            target_status,
            "--output",
            "json",
            *workspace_args,
        ],
        request_path.parent,
    )
    store.write_json(DECISION_FILE, decision)
    store.write_json(OUTCOME_FILE, outcome)
    terminal_state = {
        "approved": "resumed",
        "request_changes": "returned",
        "rejected": "terminated",
    }[decision["decision"]]
    _write_state(
        store,
        {
            **state,
            "state": terminal_state,
            "observed_multica_status": target_status,
            "processed_event_id": decision["multica_event"]["event_id"],
            "decision_hash": decision["decision_hash"],
            "outcome_hash": outcome["outcome_hash"],
            "next_node": outcome["next_node"],
            "validation_message": None,
        },
    )
    return outcome
