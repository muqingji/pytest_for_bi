#!/usr/bin/env python3
"""Auto-ingest completed Multica node runs and refresh the 8-card projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from qa_agents.autopilot import reconcile_autopilot
from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer
from qa_agents.gates import (
    prepare_scope_review_request,
    scope_review_decision_template,
)
from qa_agents.multica import ingest_multica_output
from qa_agents.reporting import render_scope_review_markdown
from qa_agents.storage import ArtifactStore
from qa_agents.workflow_center import sync_multica_workflow_center


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_reconcile_spec(
    requested_spec_path: Path,
    current_spec_path: Path,
    *,
    published_projection_path: Path | None = None,
) -> Path:
    """Merge recovered issue bindings without regressing live workflow state/revision."""

    requested = _read(requested_spec_path)
    if not current_spec_path.exists() or requested_spec_path.resolve() == current_spec_path.resolve():
        base = requested
    else:
        current = _read(current_spec_path)
        if current.get("workflow_run_id") != requested.get("workflow_run_id"):
            raise ValueError("Recovery spec and current spec belong to different workflow runs")
        base = current
        requested_nodes = {
            str(node.get("node_id")): node
            for node in requested.get("nodes", [])
            if isinstance(node, dict) and node.get("node_id")
        }
        for node in base.get("nodes", []):
            if not isinstance(node, dict):
                continue
            recovered = requested_nodes.get(str(node.get("node_id")))
            if not recovered:
                continue
            for field in ("issue_id", "issue_identifier"):
                if recovered.get(field):
                    node[field] = recovered[field]

    revision_floor = max(
        int(requested.get("revision", 0)),
        int(base.get("revision", 0)),
    )
    if published_projection_path and published_projection_path.exists():
        revision_floor = max(
            revision_floor,
            int(_read(published_projection_path).get("revision", 0)),
        )

    original = _read(current_spec_path) if current_spec_path.exists() else None
    original_core = (
        {key: value for key, value in original.items() if key != "revision"}
        if original
        else None
    )
    base_core = {key: value for key, value in base.items() if key != "revision"}
    binding_changed = original_core is not None and base_core != original_core
    base["revision"] = revision_floor + (1 if binding_changed else 0)

    recovery_path = current_spec_path.parent / "recovery-base-spec.json"
    ArtifactStore(recovery_path.parent).write_json(recovery_path.name, base)
    return recovery_path


def ensure_g01_scope_review(
    artifact_dir: Path,
    policy_path: Path,
    *,
    output_dir: Path,
) -> dict[str, Any] | None:
    """Auto-build the G01 scope review Artifact once A02/A03/A06 are accepted.

    A02/A03 open items and every A06 finding are folded into one G01 review so
    the human approves once. A run without review items gets a completed G01
    Artifact and can advance without a human action. Re-running with unchanged
    upstream Artifacts is idempotent.
    """

    artifacts_dir = artifact_dir / "artifacts"
    a02_path = artifacts_dir / "a02-requirement-analysis.json"
    a03_path = artifacts_dir / "a03-technical-testability-analysis.json"
    a06_path = artifacts_dir / "a06-alignment-result.json"
    if not all(path.exists() for path in (a02_path, a03_path, a06_path)):
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = _read(policy_path)
    request = prepare_scope_review_request(
        a02_path,
        a03_path,
        a06_path,
        output_dir,
        policy=policy,
    )
    review_store = ArtifactStore(output_dir)
    review_store.write_text("g01-review-request.md", render_scope_review_markdown(request))
    review_store.write_json(
        "g01-decision-template.json", scope_review_decision_template(request)
    )
    artifact_status = (
        ArtifactStatus.NEEDS_HUMAN
        if request["status"] == "needs_human"
        else ArtifactStatus.COMPLETED
    )
    envelope = ArtifactEnvelope(
        workflow_run_id=str(request["workflow_run_id"]),
        workflow_mode=str(request["workflow_mode"]),
        artifact_id="g01-scope-review",
        source_snapshot_id=str(request["source_snapshot_id"]),
        producer=Producer(
            component_id="G01-AUTO",
            component_version="1.0.0",
            runtime="deterministic-node",
            profile_version="1.0.0",
            model_provider="deterministic",
            model_snapshot="none",
            prompt_version="none",
            tool_bundle_version="none",
        ),
        payload=request,
        status=artifact_status,
    )
    envelope_value = envelope.to_dict()
    target = artifacts_dir / "g01-scope-review.json"
    if target.exists():
        existing = _read(target)
        if existing.get("artifact_hash") == envelope_value["artifact_hash"]:
            return {
                "artifact_id": "g01-scope-review",
                "status": artifact_status.value,
                "reused": True,
                "issue_count": request["issue_count"],
            }
    ArtifactStore(artifact_dir).write_artifact(envelope)
    return {
        "artifact_id": "g01-scope-review",
        "status": artifact_status.value,
        "reused": False,
        "issue_count": request["issue_count"],
    }


def _multica(*args: str) -> Any:
    result = subprocess.run(
        ["multica", *args, "--output", "json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "multica failed")
    return json.loads(result.stdout)


def _latest_completed(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for run in runs:
        if str(run.get("status", "")) == "completed" and run.get("result"):
            return run
    return None


def _artifact_output(output_dir: Path, artifact_id: str) -> Path:
    return output_dir / "artifacts" / f"{artifact_id}.json"


def _ingest_issue(
    *,
    issue: dict[str, Any],
    run: dict[str, Any],
    node_id: str,
    bundle_path: Path,
    output_dir: Path,
) -> dict[str, Any] | None:
    attachments = issue.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return None
    attachment = attachments[0]
    if not isinstance(attachment, dict) or not attachment.get("id"):
        return None
    raw_output = run.get("result", {}).get("output") if isinstance(run.get("result"), dict) else None
    if not isinstance(raw_output, str) or not raw_output.strip():
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    return ingest_multica_output(
        bundle_path,
        raw_output,
        output_dir,
        task_id=str(run["id"]),
        issue_id=str(issue["id"]),
        attachment_id=str(attachment["id"]),
        model_provider="openai",
        model_snapshot="gpt-5.6-sol",
        prompt_version=str(_read(bundle_path).get("profile_version", "1.0.0")),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--sync-output", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    config = _read(args.config)
    artifact_root = args.artifact_root
    current_dir = artifact_root / "current"
    current_dir.mkdir(parents=True, exist_ok=True)
    spec_path = args.spec or (current_dir / "workflow-center-spec.json")
    if not spec_path.exists():
        candidates = [
            artifact_root / "reconciled" / "workflow-center-spec.json",
            artifact_root / "initial" / "workflow-center-spec.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                shutil.copyfile(candidate, spec_path)
                break
        else:
            raise SystemExit(f"Missing workflow spec: {spec_path}")
    spec = _read(spec_path)
    run_id = str(spec.get("workflow_run_id", ""))
    prefix = f"[{run_id}] "
    node_agents = config.get("node_agents")
    node_input_files = config.get("node_input_files")
    if not isinstance(node_agents, dict) or not isinstance(node_input_files, dict):
        raise SystemExit("Config node_agents/node_input_files must be objects")
    repo_root = Path(__file__).resolve().parents[2]

    listing = _multica(
        "issue", "list",
        "--project", str(config["internal_project_id"]),
        "--limit", "200",
    )
    issues = listing.get("issues", listing)
    if not isinstance(issues, list):
        raise SystemExit("Issue list is invalid")

    ingested: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    auto_dir = artifact_root / "artifacts-auto"
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        title = str(issue.get("title", ""))
        if not title.startswith(prefix):
            continue
        node_id = title[len(prefix):].split(" ", 1)[0]
        if node_id not in node_agents:
            continue
        bundle_relative = node_input_files.get(node_id)
        if not isinstance(bundle_relative, list) or not bundle_relative:
            continue
        bundle_path = Path(str(bundle_relative[0]))
        if not bundle_path.is_absolute():
            bundle_path = repo_root / bundle_path
        if not bundle_path.exists():
            errors.append({"node_id": node_id, "error": f"missing bundle: {bundle_path}"})
            continue
        runs = _multica("issue", "runs", str(issue["id"]))
        if not isinstance(runs, list):
            continue
        run = _latest_completed(runs)
        if not run:
            continue
        details = _multica("issue", "get", str(issue["id"]))
        if not isinstance(details, dict):
            continue
        issue_with_attachment = {**issue, "attachments": details.get("attachments")}
        try:
            artifact = _ingest_issue(
                issue=issue_with_attachment,
                run=run,
                node_id=node_id,
                bundle_path=bundle_path,
                output_dir=auto_dir,
            )
            if artifact:
                ingested.append({"node_id": node_id, "artifact_id": artifact["artifact_id"]})
                if args.apply:
                    _multica("issue", "status", str(issue["id"]), "done")
        except Exception as error:  # keep other nodes progressing
            errors.append({"node_id": node_id, "error": str(error)})

    g01_result = None
    g01_policy = config.get("g01_policy")
    if g01_policy:
        policy_path = Path(str(g01_policy))
        if not policy_path.is_absolute():
            policy_path = repo_root / policy_path
        g01_result = ensure_g01_scope_review(
            auto_dir,
            policy_path,
            output_dir=artifact_root / "g01-auto",
        )

    reconcile_out = current_dir
    sync_out = args.sync_output or (artifact_root / "sync-auto")
    reconcile_spec_path = prepare_reconcile_spec(
        spec_path,
        current_dir / "workflow-center-spec.json",
        published_projection_path=sync_out / "workflow-projection.json" if args.apply else None,
    )
    artifact_roots = [
        artifact_root / "bootstrap" / "artifacts",
        artifact_root / "artifacts-stage1",
        auto_dir,
    ]
    reconciled = reconcile_autopilot(reconcile_spec_path, artifact_roots, reconcile_out)
    sync_result = None
    if args.apply:
        sync_result = sync_multica_workflow_center(
            reconcile_out / "workflow-center-spec.json",
            args.config,
            sync_out,
        )

    result = {
        "workflow_run_id": run_id,
        "ingested": ingested,
        "errors": errors,
        "g01": g01_result,
        "reconciled": reconciled,
        "sync": sync_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
