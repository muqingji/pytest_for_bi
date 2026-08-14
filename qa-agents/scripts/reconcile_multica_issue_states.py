#!/usr/bin/env python3
"""Project Issue status projection from live runs and accepted Artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any


ACTIVE_RUN_STATES = {"queued", "dispatched", "deferred", "running"}
IMMUTABLE_ISSUE_STATES = {"cancelled", "done"}
COMPLETED_RESULT_STATES = {"completed", "completed_with_gaps", "inconclusive"}
BLOCKED_RESULT_STATES = {"needs_human", "blocked", "blocked_input", "failed_fatal"}


def run_failure_kind(run: dict[str, Any] | None) -> str:
    if not run:
        return ""
    detail = " ".join(
        str(run.get(field, "")) for field in ("failure_reason", "error")
    ).lower()
    if "subscription quota insufficient" in detail or "403 forbidden" in detail:
        return "provider_subscription_quota"
    if "provider_network" in detail or "stream disconnected" in detail:
        return "provider_network"
    return "agent_run_failed" if str(run.get("status", "")) in {"failed", "cancelled"} else ""


def run_result_status(run: dict[str, Any] | None) -> str:
    """Read the agent's JSON result status without treating transport completion as success."""
    if not run or not isinstance(run.get("result"), dict):
        return ""
    raw_output = run["result"].get("output")
    if not isinstance(raw_output, str) or not raw_output.strip():
        return ""
    try:
        value = json.loads(raw_output)
    except json.JSONDecodeError:
        return ""
    return str(value.get("status", "")) if isinstance(value, dict) else ""


def multica(*args: str) -> Any:
    result = subprocess.run(
        ["multica", *args, "--output", "json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def accepted_issue_ids(root: Path) -> set[str]:
    result: set[str] = set()
    for path in root.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or value.get("schema_version") != "artifact-envelope/1.0":
            continue
        for fact in value.get("facts", []):
            if fact.get("type") == "multica_tool_trace_audit" and fact.get("result") == "passed":
                issue_id = str(fact.get("issue_id", ""))
                if issue_id:
                    result.add(issue_id)
    return result


def latest_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(runs, key=lambda item: str(item.get("created_at", ""))) if runs else None


def expected_issue_state(
    issue: dict[str, Any], run: dict[str, Any] | None, accepted: bool
) -> tuple[str, str | None]:
    """Project a terminal remote run onto its bound Issue without guessing output."""
    current = str(issue.get("status", ""))
    if current in IMMUTABLE_ISSUE_STATES:
        return current, None
    run_state = str(run.get("status", "")) if run else ""
    result_state = run_result_status(run)
    if run_state in ACTIVE_RUN_STATES:
        return "in_progress", "active_agent_run"
    if accepted and current == "in_progress":
        return "done", "accepted_bound_artifact"
    if run_state in {"failed", "cancelled"}:
        return "blocked", run_failure_kind(run) or "agent_run_failed"
    if run_state == "completed" and current == "in_progress":
        if result_state in BLOCKED_RESULT_STATES:
            return "blocked", f"agent_result_{result_state}"
        if result_state in COMPLETED_RESULT_STATES:
            return "done", f"agent_result_{result_state}"
    return current, None


def reconcile(project_id: str, artifact_root: Path, *, apply: bool) -> dict[str, Any]:
    listing = multica("issue", "list", "--project", project_id, "--limit", "100")
    issues = listing.get("issues", listing)
    accepted = accepted_issue_ids(artifact_root)
    changes = []
    for issue in issues:
        if issue.get("assignee_type") != "agent":
            continue
        runs = multica("issue", "runs", issue["id"])
        current_run = latest_run(runs)
        expected, reason = expected_issue_state(issue, current_run, issue["id"] in accepted)
        if expected == issue.get("status"):
            continue
        if apply:
            multica("issue", "update", issue["id"], "--status", expected)
        changes.append({
            "identifier": issue.get("identifier"),
            "from": issue.get("status"),
            "to": expected,
            "reason": reason,
        })
    return {"project_id": project_id, "applied": apply, "changes": changes}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(reconcile(args.project, args.artifact_root, apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
