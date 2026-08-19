"""Content-addressed G03 review flow controlled by a Multica issue."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from .card_copy import g03_review_description, g03_review_title
from .contracts import artifact_hash_from_mapping, content_hash
from .errors import ContractError, RetryableAgentError, SecurityPolicyError
from .security import SecurityPolicy
from .storage import ArtifactStore


CommandRunner = Callable[[list[str], Path], Mapping[str, Any]]
REQUEST_FILE = "g03-review-request.json"
DECISION_FILE = "g03-review-decision.json"
OUTCOME_FILE = "g03-review-outcome.json"
STATE_FILE = "g03-workflow-state.json"

REQUEST_CONTRACT = "automation-code-review-request/1.0"
DECISION_CONTRACT = "automation-code-review-decision/1.0"
OUTCOME_CONTRACT = "automation-code-review-outcome/1.0"

GENERATION_ARTIFACTS = {
    "A14": "a14-backend-automation-generation",
    "A15": "a15-contract-automation-generation",
}
REVIEW_ARTIFACTS = {
    "A18-BE": "a18-be-backend-automation-review",
    "A18-CT": "a18-ct-contract-automation-review",
}


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


def _verified_artifact(path: Path, artifact_id: str, security: SecurityPolicy) -> dict[str, Any]:
    artifact = _read_mapping(path, artifact_id)
    if artifact.get("artifact_id") != artifact_id:
        raise ContractError(f"Expected Artifact {artifact_id}: {path}")
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError(f"Artifact hash mismatch: {artifact_id}")
    security.assert_no_secret_values(artifact)
    return artifact


def _validate_hash(value: Mapping[str, Any], hash_field: str, label: str) -> None:
    unhashed = {key: item for key, item in value.items() if key != hash_field}
    if value.get(hash_field) != content_hash(unhashed):
        raise ContractError(f"{label} hash is invalid")


def _validate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    if policy.get("schema_version") != "g03-review-policy/1.0":
        raise ContractError("G03 policy schema_version is invalid")
    if policy.get("gate_id") != "G03":
        raise ContractError("G03 policy gate_id is invalid")
    if policy.get("temporary_policy") is True and policy.get(
        "production_release_authority"
    ) is not False:
        raise SecurityPolicyError(
            "Temporary G03 policy cannot grant production release authority"
        )
    actor_ids = policy.get("allowed_actor_ids")
    roles = policy.get("allowed_roles")
    member_ids = policy.get("allowed_multica_member_ids")
    if not isinstance(actor_ids, list) or not actor_ids or not all(actor_ids):
        raise ContractError("G03 policy allowed_actor_ids are invalid")
    if not isinstance(roles, list) or not roles or not all(roles):
        raise ContractError("G03 policy allowed_roles are invalid")
    if not isinstance(member_ids, list) or not member_ids or not all(member_ids):
        raise ContractError("G03 policy allowed_multica_member_ids are invalid")
    multica = policy.get("multica")
    if not isinstance(multica, Mapping):
        raise ContractError("G03 policy multica configuration is missing")
    required = ("workspace_id", "project_id", "assignee_member_id", "initial_status")
    if any(not str(multica.get(field, "")) for field in required):
        raise ContractError("G03 policy Multica identity fields are incomplete")
    if multica.get("assignee_member_id") not in member_ids:
        raise SecurityPolicyError("G03 Multica assignee is not an allowed reviewer")
    if multica.get("initial_status") != "in_review":
        raise ContractError("G03 Multica initial status must be in_review")
    decision_statuses = multica.get("decision_statuses")
    if decision_statuses != {
        "done": "approved",
        "blocked": "request_changes",
        "cancelled": "rejected",
    }:
        raise ContractError("G03 Multica decision status mapping is invalid")
    if policy.get("require_human_actor") is not True:
        raise SecurityPolicyError("G03 policy must require a human actor")
    if policy.get("require_n05_valid") is not True:
        raise SecurityPolicyError("G03 policy must require a valid N05 Artifact")
    return dict(policy)


def _request_core(
    n05: Mapping[str, Any],
    generations: dict[str, Mapping[str, Any]],
    reviews: dict[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    identities = {
        (
            str(item.get("workflow_run_id", "")),
            str(item.get("workflow_mode", "")),
            str(item.get("source_snapshot_id", "")),
        )
        for item in (n05, *generations.values(), *reviews.values())
    }
    if len(identities) != 1 or not all(next(iter(identities))):
        raise ContractError("G03 upstream Artifacts belong to different runs")
    workflow_run_id, workflow_mode, source_snapshot_id = identities.pop()
    n05_payload = n05.get("payload")
    if not isinstance(n05_payload, Mapping):
        raise ContractError("G03 N05 payload is invalid")
    if (
        n05_payload.get("schema_version") != "automation-code-check/1.0"
        or n05_payload.get("passed") is not True
    ):
        raise ContractError("G03 requires a passed N05 automation code check")
    upstream_artifacts = [
        {
            "artifact_id": str(artifact["artifact_id"]),
            "artifact_hash": str(artifact["artifact_hash"]),
            "status": str(artifact["status"]),
            "reason_code": artifact.get("reason_code"),
        }
        for artifact in (n05, *generations.values(), *reviews.values())
    ]
    issue_items: list[dict[str, Any]] = []
    candidate_count = 0
    review_issue_count = 0
    for generator_id, generation in generations.items():
        payload = generation.get("payload")
        if not isinstance(payload, Mapping):
            continue
        candidates = payload.get("code_candidates", [])
        candidate_count += len(candidates) if isinstance(candidates, list) else 0
        rejected = payload.get("rejected_cases", [])
        issue_items.append(
            {
                "generator_id": generator_id,
                "artifact_id": generation["artifact_id"],
                "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
                "rejected_count": len(rejected) if isinstance(rejected, list) else 0,
                "manifest_id": (
                    payload.get("manifest", {}).get("manifest_id")
                    if isinstance(payload.get("manifest"), Mapping)
                    else None
                ),
            }
        )
    for reviewer_id, review in reviews.items():
        payload = review.get("payload")
        if not isinstance(payload, Mapping):
            continue
        issues = payload.get("issues", [])
        review_issue_count += len(issues) if isinstance(issues, list) else 0
        issue_items.append(
            {
                "reviewer_id": reviewer_id,
                "artifact_id": review["artifact_id"],
                "approved": payload.get("approved"),
                "issue_count": len(issues) if isinstance(issues, list) else 0,
            }
        )
    review_key = content_hash(
        {
            "gate_id": "G03",
            "workflow_run_id": workflow_run_id,
            "source_snapshot_id": source_snapshot_id,
            "n05_artifact_hash": n05["artifact_hash"],
            "upstream_artifacts": [
                {"artifact_id": item["artifact_id"], "artifact_hash": item["artifact_hash"]}
                for item in upstream_artifacts
            ],
        }
    )
    return {
        "schema_version": REQUEST_CONTRACT,
        "gate_id": "G03",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": source_snapshot_id,
        "review_key": review_key,
        "upstream_artifacts": upstream_artifacts,
        "n05_payload": {
            key: n05_payload.get(key)
            for key in (
                "passed",
                "fatal_security_violation",
                "generation_count",
                "planned_generation_count",
                "issues",
                "repair_routes",
                "rejected_cases",
            )
        },
        "issue_items": issue_items,
        "summary": {
            "generation_count": len(generations),
            "review_count": len(reviews),
            "candidate_count": candidate_count,
            "review_issue_count": review_issue_count,
            "n05_passed": n05_payload.get("passed") is True,
        },
        "review_policy": {"policy_hash": content_hash(policy), "gate_id": "G03"},
    }


def automation_code_review_decision_template(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": DECISION_CONTRACT,
        "gate_id": "G03",
        "workflow_run_id": request.get("workflow_run_id"),
        "source_snapshot_id": request.get("source_snapshot_id"),
        "request_hash": request.get("request_hash"),
        "review_key": request.get("review_key"),
        "decision": "",
        "decided_at": "",
        "actor": {"type": "human", "id": "", "role": "", "multica_member_id": ""},
        "multica_event": {"issue_id": "", "event_id": "", "status": ""},
        "reason": "",
    }


def render_automation_code_review_markdown(request: Mapping[str, Any]) -> str:
    return g03_review_description(request)


def prepare_automation_code_review_request(
    n05_artifact_path: Path,
    generation_artifact_paths: dict[str, Path],
    review_artifact_paths: dict[str, Path],
    policy_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    security = security or SecurityPolicy()
    policy = _validate_policy(_read_mapping(policy_path, "G03 policy"))
    security.assert_no_secret_values(policy)
    n05 = _verified_artifact(n05_artifact_path, "n05-automation-code-check", security)
    generations: dict[str, Mapping[str, Any]] = {}
    for generator_id, path in generation_artifact_paths.items():
        generations[generator_id] = _verified_artifact(
            path, GENERATION_ARTIFACTS[generator_id], security
        )
    reviews: dict[str, Mapping[str, Any]] = {}
    for reviewer_id, path in review_artifact_paths.items():
        reviews[reviewer_id] = _verified_artifact(
            path, REVIEW_ARTIFACTS[reviewer_id], security
        )
    core = _request_core(n05, generations, reviews, policy)
    store = ArtifactStore(output_dir)
    request_path = output_dir / REQUEST_FILE
    if request_path.exists():
        existing = _read_mapping(request_path, "G03 review request")
        _validate_hash(existing, "request_hash", "G03 review request")
        comparable = {
            key: value
            for key, value in existing.items()
            if key not in {"request_hash", "created_at"}
        }
        if comparable != core:
            raise ContractError("Existing G03 request belongs to different frozen inputs")
        return existing

    request = {
        **core,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    request["request_hash"] = content_hash(request)
    security.assert_no_secret_values(request)
    store.write_json(REQUEST_FILE, request)
    store.write_json(
        "g03-decision-template.json", automation_code_review_decision_template(request)
    )
    store.write_text(
        "g03-review-request.md", render_automation_code_review_markdown(request)
    )
    state = {
        "schema_version": "workflow-gate-state/1.0",
        "gate_id": "G03",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "review_key": request["review_key"],
        "state": "prepared",
        "issue_id": None,
        "observed_multica_status": None,
        "processed_event_id": None,
        "next_node": None,
    }
    state["state_hash"] = content_hash(state)
    store.write_json(STATE_FILE, state)
    return request


def _default_runner(args: list[str], cwd: Path) -> Mapping[str, Any]:
    completed = subprocess.run(
        ["multica", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "Multica command failed"
        raise RetryableAgentError(detail)
    if not completed.stdout.strip():
        return {}
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ContractError("Multica command returned invalid JSON") from error
    if not isinstance(value, Mapping):
        raise ContractError("Multica command must return a JSON object")
    return value


def _write_state(store: ArtifactStore, state: Mapping[str, Any]) -> dict[str, Any]:
    value = {key: item for key, item in state.items() if key != "state_hash"}
    value["state_hash"] = content_hash(value)
    store.write_json(STATE_FILE, value)
    return value


def _comment_values(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        for field in ("comments", "data", "items"):
            items = value.get(field)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, Mapping)]
    raise ContractError("Multica comment list returned an invalid payload")


def _load_bound_request_policy(
    request_path: Path, policy_path: Path, security: SecurityPolicy
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = _read_mapping(request_path, "G03 review request")
    _validate_hash(request, "request_hash", "G03 review request")
    policy = _validate_policy(_read_mapping(policy_path, "G03 policy"))
    if request.get("review_policy", {}).get("policy_hash") != content_hash(policy):
        raise ContractError("G03 request policy binding is stale")
    security.assert_no_secret_values(request)
    security.assert_no_secret_values(policy)
    return request, policy


def open_multica_automation_code_review(
    request_path: Path,
    policy_path: Path,
    output_dir: Path,
    *,
    runner: CommandRunner | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    security = security or SecurityPolicy()
    request, policy = _load_bound_request_policy(request_path, policy_path, security)
    runner = runner or _default_runner
    store = ArtifactStore(output_dir)
    state_path = output_dir / STATE_FILE
    if not state_path.exists():
        raise ContractError("G03 workflow state is missing")
    state = _read_mapping(state_path, "G03 workflow state")
    _validate_hash(state, "state_hash", "G03 workflow state")
    if state.get("request_hash") != request["request_hash"]:
        raise ContractError("G03 workflow state belongs to another request")
    if state.get("issue_id") and state.get("state") != "opening_review":
        return state

    multica = policy["multica"]
    workspace_args = ["--workspace-id", multica["workspace_id"]]
    if not state.get("issue_id"):
        created = runner(
            [
                "issue",
                "create",
                "--title",
                g03_review_title(request),
                "--description-file",
                "g03-review-request.md",
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
        issue_id = str(created.get("id", ""))
        if not issue_id or created.get("workspace_id") != multica["workspace_id"]:
            raise ContractError("Multica did not create the expected G03 issue")
        state = _write_state(
            store,
            {
                **state,
                "state": "opening_review",
                "issue_id": issue_id,
                "observed_multica_status": str(created.get("status", "todo")),
            },
        )

    issue_id = str(state["issue_id"])
    metadata = {
        "qa_gate_id": "G03",
        "qa_review_key": request["review_key"],
        "qa_request_hash": request["request_hash"],
        "qa_policy_hash": request["review_policy"]["policy_hash"],
        "qa_workflow_run_id": request["workflow_run_id"],
    }
    for key, value in metadata.items():
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
        [
            "issue",
            "status",
            issue_id,
            "in_review",
            "--output",
            "json",
            *workspace_args,
        ],
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


def _validate_current_n05(request: Mapping[str, Any], n05_path: Path) -> dict[str, Any]:
    n05 = _verified_artifact(n05_path, "n05-automation-code-check", SecurityPolicy())
    expected_hash = next(
        (
            item["artifact_hash"]
            for item in request["upstream_artifacts"]
            if item["artifact_id"] == "n05-automation-code-check"
        ),
        None,
    )
    if n05.get("artifact_hash") != expected_hash:
        raise ContractError("G03 approval is stale because the current N05 Artifact changed")
    if n05.get("payload", {}).get("passed") is not True:
        raise ContractError("G03 approval cannot resume from a failed N05 Artifact")
    return n05


def _event_decision(
    request: Mapping[str, Any],
    policy: Mapping[str, Any],
    issue: Mapping[str, Any],
    comment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    multica = policy["multica"]
    if issue.get("workspace_id") != multica["workspace_id"]:
        raise SecurityPolicyError("G03 issue belongs to another Multica workspace")
    if issue.get("project_id") != multica["project_id"]:
        raise SecurityPolicyError("G03 issue belongs to another Multica project")
    if issue.get("assignee_type") != "member":
        raise SecurityPolicyError("G03 issue must be assigned to a human member")
    member_id = str(issue.get("assignee_id", ""))
    if member_id not in policy["allowed_multica_member_ids"]:
        raise SecurityPolicyError("G03 issue is not assigned to an authorized reviewer")
    metadata = issue.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ContractError("G03 issue metadata is missing")
    expected_metadata = {
        "qa_gate_id": "G03",
        "qa_review_key": request["review_key"],
        "qa_request_hash": request["request_hash"],
        "qa_policy_hash": request["review_policy"]["policy_hash"],
        "qa_workflow_run_id": request["workflow_run_id"],
    }
    if any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise ContractError("G03 issue metadata does not match the review request")
    status = str(issue.get("status", ""))
    decision = multica["decision_statuses"].get(status)
    if not decision:
        raise ContractError("G03 issue has no terminal review decision")
    updated_at = str(issue.get("updated_at", ""))
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("G03 issue updated_at is invalid") from error
    if parsed.tzinfo is None:
        raise ContractError("G03 issue updated_at must include a timezone")
    event_id = content_hash(
        {
            "issue_id": issue.get("id"),
            "status": status,
            "updated_at": updated_at,
            "request_hash": request["request_hash"],
        }
    )
    reason = str(metadata.get("qa_review_reason", "")).strip()
    reviewer_comment: dict[str, Any] | None = None
    if comment is not None:
        creator_type = comment.get("creator_type", comment.get("author_type"))
        creator_id = str(comment.get("creator_id", comment.get("author_id", "")))
        if creator_type != "member" or creator_id not in policy["allowed_multica_member_ids"]:
            raise SecurityPolicyError("G03 decision comment was not authored by an authorized reviewer")
        comment_id = str(comment.get("id", ""))
        comment_content = str(comment.get("content", "")).strip()
        comment_created_at = str(comment.get("created_at", ""))
        if not comment_id or not comment_created_at:
            raise ContractError("G03 decision comment id and created_at are required")
        reviewer_comment = {
            "id": comment_id,
            "created_at": comment_created_at,
            "content": comment_content,
        }
        if comment_content:
            reason = comment_content
    if not reason:
        reason = f"G03 decision recorded by Multica status transition to {status}"
    raw = {
        "schema_version": DECISION_CONTRACT,
        "gate_id": "G03",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "review_key": request["review_key"],
        "decision": decision,
        "decided_at": parsed.isoformat(),
        "actor": {
            "type": "human",
            "id": policy["allowed_actor_ids"][0],
            "role": policy["allowed_roles"][0],
            "multica_member_id": member_id,
        },
        "multica_event": {
            "workspace_id": issue["workspace_id"],
            "issue_id": issue["id"],
            "event_id": event_id,
            "status": status,
            "comment_id": reviewer_comment["id"] if reviewer_comment else "",
            "identity_evidence_mode": multica["identity_evidence_mode"],
        },
        "reviewer_comment": reviewer_comment,
        "reason": reason,
    }
    raw["decision_hash"] = content_hash(raw)
    return raw


def _build_outcome(
    request: Mapping[str, Any], decision: Mapping[str, Any]
) -> dict[str, Any]:
    decision_value = decision["decision"]
    if decision_value == "approved":
        status, action, next_node, resume_at = "completed", "continue", "N08", "N08"
    elif decision_value == "request_changes":
        status, action, next_node, resume_at = "blocked_input", "return_upstream", "N05", "N05"
    else:
        status, action, next_node, resume_at = "cancelled", "terminate", None, None
    raw = {
        "schema_version": OUTCOME_CONTRACT,
        "gate_id": "G03",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "review_key": request["review_key"],
        "decision_hash": decision["decision_hash"],
        "decision": decision_value,
        "status": status,
        "action": action,
        "next_node": next_node,
        "resume_at": resume_at,
        "invalidation": {
            "roots": ["A14", "A15", "A18-BE", "A18-CT", "N05"]
            if decision_value == "request_changes"
            else [],
            "include_all_descendants": decision_value == "request_changes",
        },
        "idempotency_key": content_hash(
            {
                "gate_id": "G03",
                "request_hash": request["request_hash"],
                "decision_hash": decision["decision_hash"],
            }
        ),
    }
    raw["outcome_hash"] = content_hash(raw)
    return raw


def sync_multica_automation_code_review(
    request_path: Path,
    current_n05_artifact_path: Path,
    policy_path: Path,
    output_dir: Path,
    *,
    runner: CommandRunner | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    security = security or SecurityPolicy()
    request, policy = _load_bound_request_policy(request_path, policy_path, security)
    _validate_current_n05(request, current_n05_artifact_path)
    runner = runner or _default_runner
    store = ArtifactStore(output_dir)
    state = _read_mapping(output_dir / STATE_FILE, "G03 workflow state")
    _validate_hash(state, "state_hash", "G03 workflow state")
    if state.get("request_hash") != request["request_hash"] or not state.get("issue_id"):
        raise ContractError("G03 workflow state is not bound to an open review issue")

    existing_decision_path = output_dir / DECISION_FILE
    existing_outcome_path = output_dir / OUTCOME_FILE
    if existing_decision_path.exists():
        existing_decision = _read_mapping(existing_decision_path, "G03 review decision")
        _validate_hash(existing_decision, "decision_hash", "G03 review decision")
        if existing_outcome_path.exists():
            existing_outcome = _read_mapping(existing_outcome_path, "G03 review outcome")
            _validate_hash(existing_outcome, "outcome_hash", "G03 review outcome")
            if existing_outcome.get("decision_hash") != existing_decision["decision_hash"]:
                raise ContractError("G03 outcome does not bind the recorded decision")
            return existing_outcome
        recovered = _build_outcome(request, existing_decision)
        store.write_json(OUTCOME_FILE, recovered)
        terminal_state = {
            "approved": "resumed",
            "request_changes": "returned",
            "rejected": "terminated",
        }[existing_decision["decision"]]
        _write_state(
            store,
            {
                **state,
                "state": terminal_state,
                "observed_multica_status": existing_decision["multica_event"]["status"],
                "processed_event_id": existing_decision["multica_event"]["event_id"],
                "decision_hash": existing_decision["decision_hash"],
                "outcome_hash": recovered["outcome_hash"],
                "next_node": recovered["next_node"],
            },
        )
        return recovered

    multica = policy["multica"]
    issue = runner(
        [
            "issue",
            "get",
            str(state["issue_id"]),
            "--output",
            "json",
            "--workspace-id",
            multica["workspace_id"],
        ],
        request_path.parent,
    )
    if issue.get("id") != state["issue_id"]:
        raise SecurityPolicyError("Multica returned a different G03 issue")
    status = str(issue.get("status", ""))
    if status in {"todo", "in_progress", "in_review"}:
        return _write_state(
            store,
            {
                **state,
                "state": "waiting_for_review",
                "observed_multica_status": status,
            },
        )

    reviewer_comment: Mapping[str, Any] | None = None
    try:
        comment_payload = runner(
            [
                "issue",
                "comment",
                "list",
                str(state["issue_id"]),
                "--output",
                "json",
                "--compact",
                "--workspace-id",
                multica["workspace_id"],
            ],
            request_path.parent,
        )
        comments = [
            item
            for item in _comment_values(comment_payload)
            if item.get("creator_type", item.get("author_type")) == "member"
            and str(item.get("creator_id", item.get("author_id", "")))
            in policy["allowed_multica_member_ids"]
        ]
        if comments:
            reviewer_comment = max(
                comments,
                key=lambda item: (
                    str(item.get("created_at", "")),
                    str(item.get("id", "")),
                ),
            )
    except (ContractError, RetryableAgentError, SecurityPolicyError):
        reviewer_comment = None

    decision = _event_decision(request, policy, issue, reviewer_comment)
    outcome = _build_outcome(request, decision)
    security.assert_no_secret_values(decision)
    security.assert_no_secret_values(outcome)
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
            "observed_multica_status": status,
            "processed_event_id": decision["multica_event"]["event_id"],
            "decision_hash": decision["decision_hash"],
            "outcome_hash": outcome["outcome_hash"],
            "next_node": outcome["next_node"],
        },
    )
    return outcome
