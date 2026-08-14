#!/usr/bin/env python3
"""Audit Multica Issue state against an explicit workflow-node manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


def _multica(*args: str) -> Any:
    completed = subprocess.run(
        ["multica", *args, "--output", "json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "multica command failed")
    return json.loads(completed.stdout)


def audit(project_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    listed = _multica("issue", "list", "--project", project_id)
    issues = {issue["identifier"]: issue for issue in listed.get("issues", [])}
    findings: list[str] = []

    for node in manifest.get("nodes", []):
        identifier = node["identifier"]
        issue = issues.get(identifier)
        if issue is None:
            findings.append(f"{identifier}: missing from project")
            continue
        for field in ("status", "stage", "assignee_type"):
            expected = node.get(field)
            if expected is not None and issue.get(field) != expected:
                findings.append(
                    f"{identifier}: {field}={issue.get(field)!r}, expected {expected!r}"
                )
        if issue.get("project_id") != project_id:
            findings.append(f"{identifier}: belongs to another project")

        runs = _multica("issue", "runs", issue["id"])
        latest_run = max(runs, key=lambda item: str(item.get("created_at", ""))) if runs else None
        last_run_status = latest_run.get("status") if latest_run else None
        expected_run_status = node.get("last_run_status")
        if expected_run_status is not None and last_run_status != expected_run_status:
            findings.append(
                f"{identifier}: last_run_status={last_run_status!r}, "
                f"expected {expected_run_status!r}"
            )

        if node.get("kind") == "human_gate":
            if issue.get("status") not in {"in_review", "done", "cancelled", "blocked"}:
                findings.append(f"{identifier}: human gate has an invalid lifecycle state")
            if issue.get("assignee_type") != "member":
                findings.append(f"{identifier}: human gate must be assigned to a member")

    project = _multica("project", "get", project_id)
    # Multica's project done_count includes all terminal cards, including cancelled.
    expected_done = sum(
        1
        for node in manifest.get("nodes", [])
        if node.get("status") in {"done", "cancelled"}
    )
    if project.get("done_count") != expected_done:
        findings.append(
            f"project: done_count={project.get('done_count')!r}, expected {expected_done}"
        )
    expected_project_status = manifest.get("project_status")
    if expected_project_status and project.get("status") != expected_project_status:
        findings.append(
            f"project: status={project.get('status')!r}, expected {expected_project_status!r}"
        )

    return {
        "project_id": project_id,
        "status": "passed" if not findings else "failed",
        "checked_node_count": len(manifest.get("nodes", [])),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = audit(args.project, manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
