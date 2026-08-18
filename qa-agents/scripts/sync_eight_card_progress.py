#!/usr/bin/env python3
"""Auto-ingest completed Multica node runs and refresh the 8-card projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping
from datetime import datetime, timezone

from qa_agents.autopilot import reconcile_autopilot
from qa_agents.change_set import normalize_change_set
from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer
from qa_agents.contracts import content_hash
from qa_agents.gates import (
    prepare_scope_review_request,
    scope_carry_forward,
    scope_followup_issues,
    scope_review_decision_template,
)
from qa_agents.g01_review import open_multica_scope_review, sync_multica_scope_review
from qa_agents.g02_review import (
    open_multica_test_case_review,
    prepare_test_case_review_request,
    sync_multica_test_case_review,
)
from qa_agents.human_correction import (
    open_multica_human_correction,
    prepare_human_correction_request,
    sync_multica_human_correction,
)
from qa_agents.multica import (
    PROFILE_OUTPUTS,
    ingest_multica_output,
    prepare_multica_oracle_review_input,
    prepare_multica_test_design_correction_input,
    prepare_multica_test_design_input,
)
from qa_agents.reporting import render_scope_review_markdown
from qa_agents.risk import run_risk_strategy_after_g01
from qa_agents.security import SecurityPolicy
from qa_agents.storage import ArtifactStore
from qa_agents.test_case_gate import run_n04_after_a09
from qa_agents.workflow_center import sync_multica_workflow_center


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _config_path(config: dict[str, Any], key: str, repo_root: Path) -> Path | None:
    raw = config.get(key)
    if not raw:
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = repo_root / path
    return path if path.exists() else None


def _reconstruct_request_for_decision(
    decision: dict[str, Any],
    artifact_paths: dict[str, Path],
    policy: dict[str, Any],
    review_dir: Path,
    prior_decisions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Recreate the exact request a recorded decision was bound to.

    The review request is content-addressed and regenerable from the same upstream
    Artifacts, so an archived decision (whose co-located request was overwritten by
    a later carry-forward round) can still be bound by matching request hashes.
    """

    request = prepare_scope_review_request(
        artifact_paths["a02"],
        artifact_paths["a03"],
        artifact_paths["a06"],
        review_dir,
        policy=policy,
    )
    if request.get("workflow_run_id") != decision.get("workflow_run_id"):
        return None
    target_hash = str(decision.get("request_hash", ""))
    candidates: list[dict[str, Any]] = [dict(request)]
    prior = [
        item for item in prior_decisions if item.get("request_hash") != target_hash
    ]
    new_items = scope_carry_forward(request["issues"], prior)
    for item in new_items:
        item.setdefault("review_reason", "新增待确认项，此前未审核过；请确认口径。")
    carried = dict(request)
    carried["issues"] = new_items
    carried["issue_count"] = len(new_items)
    carried["status"] = "needs_human" if new_items else "completed"
    carried["decision"] = "pending" if new_items else "not_required"
    candidates.append(carried)
    for candidate in candidates:
        candidate["request_hash"] = content_hash(
            {key: value for key, value in candidate.items() if key != "request_hash"}
        )
        if candidate["request_hash"] == target_hash:
            return candidate
    return None


def _latest_approved_g01(
    review_dir: Path,
    artifact_paths: dict[str, Path],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], Path] | None:
    """Return (request, decision, decision_path) for the latest approved G01."""

    decision_paths: list[Path] = []
    live_decision = review_dir / "g01-review-decision.json"
    if live_decision.exists():
        decision_paths.append(live_decision)
    decision_paths.extend(
        sorted(
            review_dir.glob("history/*/g01-review-decision.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    )
    prior_decisions = [
        _read(path)
        for path in sorted(
            [
                *review_dir.parent.glob("g01*/g01-review-decision.json"),
                *review_dir.parent.glob("g01*/history/*/g01-review-decision.json"),
            ],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    ]
    for decision_path in decision_paths:
        decision = _read(decision_path)
        if str(decision.get("decision", "")) != "approved":
            continue
        request_path = decision_path.parent / "g01-review-request.json"
        if request_path.exists():
            request = _read(request_path)
            if request.get("request_hash") == decision.get("request_hash"):
                return request, decision, decision_path
        reconstructed = _reconstruct_request_for_decision(
            decision, artifact_paths, policy, review_dir, prior_decisions
        )
        if reconstructed is not None:
            return reconstructed, decision, decision_path
    return None


def ensure_n24_test_strategy(
    config: dict[str, Any],
    auto_dir: Path,
    review_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Run deterministic N24 once G01 is approved and no N24 Artifact exists.

    N24 is deterministic: after the human Gate approves, the risk strategy can be
    produced without another agent. Auto-running it here keeps the stage card from
    sitting queued at N24 until someone manually invokes ``run-n24-after-g01``.
    """

    target = auto_dir / "artifacts" / "n24-test-strategy.json"
    if target.exists():
        return None
    alignment_path = auto_dir / "artifacts" / "a06-alignment-result.json"
    if not alignment_path.exists():
        return None
    workflow_input_path = _config_path(config, "n24_workflow_input", repo_root)
    source_snapshot_path = _config_path(config, "n24_source_snapshot", repo_root)
    risk_policy_path = _config_path(config, "n24_risk_policy", repo_root)
    g01_policy_path = _config_path(config, "g01_policy", repo_root)
    if not (
        workflow_input_path
        and source_snapshot_path
        and risk_policy_path
        and g01_policy_path
    ):
        return None
    policy = _read(g01_policy_path)
    artifact_paths = {
        "a02": auto_dir / "artifacts" / "a02-requirement-analysis.json",
        "a03": auto_dir / "artifacts" / "a03-technical-testability-analysis.json",
        "a06": alignment_path,
    }
    if not all(path.exists() for path in artifact_paths.values()):
        return None
    binding = _latest_approved_g01(review_dir, artifact_paths, policy)
    if not binding:
        return None
    request, decision, _decision_path = binding
    source_snapshot = _read(source_snapshot_path)
    SecurityPolicy().validate_snapshot(source_snapshot)
    artifact = run_risk_strategy_after_g01(
        _read(workflow_input_path),
        normalize_change_set(source_snapshot),
        _read(alignment_path),
        request,
        decision,
        _read(risk_policy_path),
        policy,
        auto_dir,
    )
    return {
        "artifact_id": str(artifact.get("artifact_id", "n24-test-strategy")),
        "status": str(artifact.get("status", "")),
    }


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
    previous_request = None
    previous_decision = None
    prior_decisions: list[dict[str, Any]] = []
    candidates = sorted(
        [
            *output_dir.parent.glob("g01*/g01-review-decision.json"),
            *output_dir.parent.glob("g01*/history/*/g01-review-decision.json"),
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for decision_path in candidates:
        request_path = decision_path.with_name("g01-review-request.json")
        candidate_decision = _read(decision_path)
        prior_decisions.append(candidate_decision)
        if previous_decision is not None:
            continue
        if request_path.exists():
            candidate_request = _read(request_path)
        else:
            candidate_request = None
            context_path = output_dir.parent / "g01-followup-context.json"
            if context_path.exists():
                context = _read(context_path)
                if context.get("request_hash") == candidate_decision.get("request_hash"):
                    candidate_request = context
            returned_ids = {
                str(item.get("issue_id", ""))
                for item in candidate_decision.get("resolutions", [])
                if isinstance(item, dict)
            }
            for spec_path in (
                output_dir.parent / "initial" / "workflow-center-spec.json",
                output_dir.parent / "current" / "workflow-center-spec.json",
            ):
                if candidate_request or not spec_path.exists():
                    continue
                spec_value = _read(spec_path)
                g01_node = next(
                    (
                        node for node in spec_value.get("nodes", [])
                        if isinstance(node, dict) and node.get("node_id") == "G01"
                    ),
                    None,
                )
                approval_items = g01_node.get("approval_items", []) if g01_node else []
                if returned_ids <= {str(item.get("id", "")) for item in approval_items}:
                    candidate_request = {
                        "workflow_run_id": spec_value.get("workflow_run_id"),
                        "issues": [
                            {
                                "issue_id": item.get("id"),
                                "plain_summary": item.get("summary", ""),
                                "detail": {"summary": item.get("summary", "")},
                            }
                            for item in approval_items
                        ],
                    }
                    break
            if not candidate_request:
                # Fall back to the decision itself: its resolutions are the
                # issues the previous review round resolved. This also covers
                # followup rounds whose resolved ids no longer appear in the
                # current spec approval items.
                candidate_request = {
                    "workflow_run_id": candidate_decision.get("workflow_run_id"),
                    "issues": [
                        {
                            "issue_id": resolution.get("issue_id"),
                            "plain_summary": resolution.get("review_summary", ""),
                            "dedupe_key": resolution.get("topic_key", ""),
                            "detail": {
                                "summary": resolution.get("review_summary", "")
                            },
                        }
                        for resolution in candidate_decision.get("resolutions", [])
                        if isinstance(resolution, dict) and resolution.get("issue_id")
                    ],
                }
        if not candidate_request:
            continue
        if (
            previous_decision is None
            and candidate_request.get("workflow_run_id") == candidate_decision.get("workflow_run_id")
        ):
            previous_request = candidate_request
            previous_decision = candidate_decision

    request = prepare_scope_review_request(
        a02_path,
        a03_path,
        a06_path,
        output_dir,
        policy=policy,
    )
    if previous_request and previous_decision:
        prior = [
            decision for decision in prior_decisions
            if decision.get("workflow_run_id") == request.get("workflow_run_id")
        ]
        new_items = scope_carry_forward(request["issues"], prior)
        for item in new_items:
            item.setdefault(
                "review_reason", "新增待确认项，此前未审核过；请确认口径。"
            )
        if previous_decision.get("decision") == "request_changes":
            followups = scope_followup_issues(
                request["issues"], previous_request, previous_decision
            )
            kept_ids = {str(item.get("issue_id", "")) for item in followups}
            request["issues"] = [
                *followups,
                *(
                    item for item in new_items
                    if str(item.get("issue_id", "")) not in kept_ids
                ),
            ]
        else:
            request["issues"] = new_items
        request["issue_count"] = len(request["issues"])
        request["status"] = "needs_human" if request["issues"] else "completed"
        request["decision"] = "pending" if request["issues"] else "not_required"
        request["request_hash"] = content_hash(
            {key: value for key, value in request.items() if key != "request_hash"}
        )
        ArtifactStore(output_dir).write_json("g01-review-request.json", request)
    old_request_path = output_dir / "g01-review-request.json"
    old_request_hash = (
        _read(old_request_path).get("request_hash")
        if old_request_path.exists()
        else None
    )
    state_path = output_dir / "g01-workflow-state.json"
    if state_path.exists():
        stale_state = _read(state_path)
        if stale_state.get("request_hash") != request["request_hash"]:
            history_dir = output_dir / "history" / str(stale_state.get("request_hash", "unknown")).replace("sha256:", "")
            history_dir.mkdir(parents=True, exist_ok=True)
            if old_request_hash == stale_state.get("request_hash") and old_request_path.exists():
                history_request = history_dir / "g01-review-request.json"
                if not history_request.exists():
                    shutil.copyfile(old_request_path, history_request)
            for name in (
                "g01-workflow-state.json",
                "g01-review-decision.json",
                "g01-review-outcome.json",
            ):
                source = output_dir / name
                if source.exists():
                    source.replace(history_dir / name)
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
        existing_request = (
            existing.get("payload", {})
            if isinstance(existing.get("payload"), dict)
            else {}
        )
        if (
            existing_request.get("request_hash") == request.get("request_hash")
            and str(existing.get("status", "")) in {"completed", "cancelled"}
        ):
            # The Gate decision for this request was already published as a
            # terminal Artifact; do not regress it back to needs_human.
            return {
                "artifact_id": "g01-scope-review",
                "status": str(existing.get("status", "")),
                "reused": True,
                "issue_count": request["issue_count"],
            }
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


def publish_g01_decision_artifact(
    artifact_dir: Path,
    review_dir: Path,
) -> dict[str, Any] | None:
    """Publish a terminal g01-scope-review Artifact once the Gate decision is recorded.

    reconcile_autopilot derives the G01 state from accepted Artifacts only. If the
    scope-review Artifact stays needs_human after an approved or rejected decision,
    the Gate is re-derived as waiting_human and the C2 stage card is written back
    to in_review on every sync, so the decision must be published as a terminal
    Artifact to let the projection advance to N24.
    """

    request_path = review_dir / "g01-review-request.json"
    decision_path = review_dir / "g01-review-decision.json"
    if not request_path.exists() or not decision_path.exists():
        return None
    request = _read(request_path)
    decision = _read(decision_path)
    if decision.get("request_hash") != request.get("request_hash"):
        raise ValueError("G01 decision is not bound to the current review request")
    decision_value = str(decision.get("decision", ""))
    if decision_value not in {"approved", "rejected"}:
        return None
    status = (
        ArtifactStatus.COMPLETED
        if decision_value == "approved"
        else ArtifactStatus.CANCELLED
    )
    envelope = ArtifactEnvelope(
        workflow_run_id=str(request["workflow_run_id"]),
        workflow_mode=str(request.get("workflow_mode", "new_requirement")),
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
        payload={
            **request,
            "decision": decision_value,
            "decision_hash": decision.get("decision_hash"),
            "decided_at": decision.get("decided_at"),
            "resolutions": decision.get("resolutions", []),
        },
        status=status,
    )
    target = artifact_dir / "artifacts" / "g01-scope-review.json"
    if target.exists():
        existing = _read(target)
        if existing.get("artifact_hash") == envelope.artifact_hash:
            return {
                "artifact_id": "g01-scope-review",
                "status": status.value,
                "reused": True,
            }
    ArtifactStore(artifact_dir).write_artifact(envelope)
    return {
        "artifact_id": "g01-scope-review",
        "status": status.value,
        "reused": False,
    }


def _multica(*args: str, cwd: Path | None = None) -> Any:
    result = subprocess.run(
        ["multica", *args, "--output", "json"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "multica failed")
    return json.loads(result.stdout)


def _human_correction_runner(args: list[str], cwd: Path) -> dict[str, Any]:
    """Route human-correction Multica calls through the shared _multica helper."""

    cleaned = list(args)
    for index in range(len(cleaned) - 2, -1, -1):
        if cleaned[index] == "--output" and index + 1 < len(cleaned):
            del cleaned[index:index + 2]
            break
    result = _multica(*cleaned, cwd=cwd)
    return result if isinstance(result, dict) else {}


def _latest_completed(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for run in runs:
        if str(run.get("status", "")) == "completed" and run.get("result"):
            return run
    return None


def _already_ingested(auto_dir: Path, bundle_path: Path, run_id: str) -> bool:
    """Whether the latest completed run already produced the current Artifact."""

    bundle = _read(bundle_path)
    profile_id = str(bundle.get("profile_id", ""))
    artifact_id = PROFILE_OUTPUTS.get(profile_id, {}).get("artifact_id")
    if not artifact_id:
        return False
    artifact_path = auto_dir / "artifacts" / f"{artifact_id}.json"
    if not artifact_path.exists():
        return False
    artifact = _read(artifact_path)
    producer = artifact.get("producer", {})
    if not isinstance(producer, dict):
        return False
    if str(producer.get("tool_bundle_version", "")) != f"multica-task:{run_id}":
        return False
    payload = artifact.get("payload", {})
    if not isinstance(payload, dict):
        return False
    return str(payload.get("input_bundle_hash", "")) == str(bundle.get("bundle_hash", ""))


def _artifact_output(output_dir: Path, artifact_id: str) -> Path:
    return output_dir / "artifacts" / f"{artifact_id}.json"


def _run_model_metadata(run: dict[str, Any]) -> tuple[str, str]:
    """Read the actual model/provider from a completed Multica run.

    Multica records one usage entry per model call; the last entry is the one
    that produced the final output. Falls back to the configured default
    runtime when usage is unavailable.
    """

    usage = run.get("usage")
    if isinstance(usage, list) and usage:
        for entry in reversed(usage):
            if not isinstance(entry, dict):
                continue
            provider = str(entry.get("provider", "")).strip()
            model = str(entry.get("model", "")).strip()
            if provider and model:
                return provider, model
    return "deepseek", "deepseek-v4-flash"


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
    model_provider, model_snapshot = _run_model_metadata(run)
    return ingest_multica_output(
        bundle_path,
        raw_output,
        output_dir,
        task_id=str(run["id"]),
        issue_id=str(issue["id"]),
        attachment_id=str(attachment["id"]),
        model_provider=model_provider,
        model_snapshot=model_snapshot,
        prompt_version=str(_read(bundle_path).get("profile_version", "1.0.0")),
    )


def _ensure_agent_instruction(
    config: dict[str, Any],
    node_id: str,
    profile_version: str,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Make sure a node Agent hosts the instruction matching its dispatch round.

    A08 ships separate instruction sets for first design (1.1.0), automatic
    correction (1.2.1) and human recovery (1.3.0). The dispatch step updates the
    Agent before creating the Issue so the automation never submits a bundle the
    hosted instructions would reject.
    """

    mapping = config.get("node_instruction_files")
    if not isinstance(mapping, Mapping) or not isinstance(mapping.get(node_id), Mapping):
        return None
    instruction_map = mapping[node_id]
    raw = instruction_map.get(str(profile_version))
    if not raw:
        return None
    instruction_path = Path(str(raw))
    if not instruction_path.is_absolute():
        instruction_path = repo_root / instruction_path
    if not instruction_path.exists():
        raise RuntimeError(f"missing instruction file: {instruction_path}")
    agent_id = str(config.get("node_agents", {}).get(node_id, ""))
    if not agent_id:
        raise RuntimeError(f"no node_agents binding for {node_id}")
    current = _multica("agent", "get", agent_id)
    if not isinstance(current, dict):
        raise RuntimeError(f"multica agent get returned invalid data for {node_id}")
    hosted = str(current.get("instructions", ""))
    header = instruction_path.read_text(encoding="utf-8").splitlines()[0].strip()
    if header and header in hosted:
        return {"node_id": node_id, "profile_version": profile_version, "unchanged": True}
    text = instruction_path.read_text(encoding="utf-8")
    _multica("agent", "update", agent_id, "--instructions", text)
    return {"node_id": node_id, "profile_version": profile_version, "updated": True}


def _node_issues_by_id(
    issues: list[dict[str, Any]], run_id: str
) -> dict[str, list[dict[str, Any]]]:
    prefix = f"[{run_id}] "
    by_node: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        title = str(issue.get("title", ""))
        if not title.startswith(prefix):
            continue
        node_id = title[len(prefix):].split(" ", 1)[0]
        if node_id:
            by_node.setdefault(node_id, []).append(issue)
    return by_node


def _issue_running(issue: dict[str, Any]) -> bool:
    """True while a node Issue is queued or actively executing."""

    return str(issue.get("status", "")) in {
        "todo", "in_progress", "in_review", "queued", "backlog", "running",
    }


def _rerun_budget_available(
    config: dict[str, Any],
    node_id: str,
    issues: list[dict[str, Any]],
) -> bool:
    """Whether an Agent node may be re-dispatched after a failed ingestion."""

    budget = int(config.get("agent_rerun_budget", 1))
    completed_attempts = sum(
        1 for issue in issues if not _issue_running(issue)
    )
    return completed_attempts <= budget


def _load_ingest_failures(artifact_root: Path) -> dict[str, list[dict[str, Any]]]:
    path = artifact_root / ".ingest-failures.json"
    if not path.exists():
        return {}
    value = _read(path)
    return value if isinstance(value, dict) else {}


def _save_ingest_failures(artifact_root: Path, failures: dict[str, list[dict[str, Any]]]) -> None:
    path = artifact_root / ".ingest-failures.json"
    ArtifactStore(artifact_root).write_json(".ingest-failures.json", failures)
    return None


def _load_issue_bundles(inputs_dir: Path) -> dict[str, str]:
    """Per-Issue input bundle bindings recorded at dispatch time."""

    path = inputs_dir / ".issue-bundles.json"
    if not path.exists():
        return {}
    value = _read(path)
    return value if isinstance(value, dict) else {}


def _save_issue_bundles(inputs_dir: Path, bundles: dict[str, str]) -> None:
    path = inputs_dir / ".issue-bundles.json"
    ArtifactStore(inputs_dir).write_json(".issue-bundles.json", bundles)
    return None


def _artifact_bundle_path(
    artifact_payload: dict[str, Any],
    inputs_dir: Path,
    profile_id: str,
) -> Path | None:
    """Resolve the input bundle an Artifact bound, across correction rounds."""

    target_hash = str(artifact_payload.get("input_bundle_hash", ""))
    if not target_hash:
        return None
    prefix = profile_id.lower()
    candidates = [inputs_dir / f"{prefix}-input.json"]
    candidates.extend(
        sub / f"{prefix}-input.json"
        for sub in sorted(inputs_dir.glob(f"{prefix}-correction-*"))
        if sub.is_dir()
    )
    for candidate in candidates:
        if candidate.exists() and str(_read(candidate).get("bundle_hash", "")) == target_hash:
            return candidate
    return None


def _ingest_already_failed(
    failures: dict[str, list[dict[str, Any]]], node_id: str, issue_id: str, run_id: str
) -> bool:
    return any(
        str(item.get("issue_id", "")) == issue_id and str(item.get("run_id", "")) == run_id
        for item in failures.get(node_id, [])
    )


def _create_node_issue(
    *,
    config: dict[str, Any],
    run_id: str,
    node_id: str,
    label: str,
    input_path: Path,
) -> dict[str, Any]:
    project_id = str(config["internal_project_id"])
    workspace_id = str(config["workspace_id"])
    agent_id = str(config.get("node_agents", {}).get(node_id, ""))
    if not agent_id:
        raise RuntimeError(f"no node_agents binding for {node_id}")
    command = [
        "issue",
        "create",
        "--title",
        f"[{run_id}] {node_id} {label}",
        "--project",
        project_id,
        "--workspace-id",
        workspace_id,
        "--status",
        "todo",
        "--priority",
        "high",
        "--assignee-id",
        agent_id,
        "--attachment",
        str(input_path),
    ]
    created = _multica(*command)
    if not isinstance(created, dict) or not created.get("id"):
        raise RuntimeError(f"multica did not create the {node_id} Issue")
    return {
        "node_id": node_id,
        "action": "dispatched",
        "issue_id": str(created["id"]),
        "issue_identifier": str(created.get("identifier", "")),
        "input": str(input_path),
    }


def ensure_a08_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    review_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, dict[str, Any]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch the A08 test-design Agent once G01 and N24 are accepted."""

    if (auto_dir / "artifacts" / "a08-test-design-ir.json").exists():
        return None
    existing_issues = issues_by_node.get("A08", [])
    if existing_issues:
        if any(_issue_running(issue) for issue in existing_issues):
            return {
                "node_id": "A08",
                "action": "already_dispatched",
                "issue_id": str(
                    next(
                        (issue.get("id") for issue in existing_issues if _issue_running(issue)),
                        existing_issues[-1].get("id", ""),
                    )
                ),
            }
        if not _rerun_budget_available(config, "A08", existing_issues):
            return {
                "node_id": "A08",
                "action": "rerun_budget_exhausted",
                "attempts": len(existing_issues),
            }
    n24_path = auto_dir / "artifacts" / "n24-test-strategy.json"
    if not n24_path.exists():
        return None
    policy_path = _config_path(config, "g01_policy", repo_root)
    if not policy_path:
        return None
    artifact_paths = {
        "a02": auto_dir / "artifacts" / "a02-requirement-analysis.json",
        "a03": auto_dir / "artifacts" / "a03-technical-testability-analysis.json",
        "a06": auto_dir / "artifacts" / "a06-alignment-result.json",
    }
    if not all(path.exists() for path in artifact_paths.values()):
        return None
    policy = _read(policy_path)
    binding = _latest_approved_g01(review_dir, artifact_paths, policy)
    if not binding:
        return None
    request, decision, decision_path = binding
    request_path = decision_path.parent / "g01-review-request.json"
    if not request_path.exists():
        ArtifactStore(decision_path.parent).write_json("g01-review-request.json", request)
    prior_paths: list[Path] = []
    for raw in config.get("prior_test_rules_paths") or []:
        candidate = Path(str(raw))
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.exists():
            prior_paths.append(candidate)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_test_design_input(
        artifact_paths["a02"],
        artifact_paths["a03"],
        artifact_paths["a06"],
        n24_path,
        request_path,
        decision_path,
        policy_path,
        inputs_dir,
        prior_test_rules_paths=prior_paths,
    )
    result = {
        "node_id": "A08",
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "input": str(inputs_dir / "a08-input.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
        "request_hash": str(request.get("request_hash", "")),
        "decision_hash": str(decision.get("decision_hash", "")),
    }
    if not apply:
        return result
    _ensure_agent_instruction(config, "A08", "1.1.0", repo_root)
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A08",
        label="测试设计",
        input_path=inputs_dir / "a08-input.json",
    )
    result.update(created)
    return result


def ensure_a08_correction_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch a targeted A08 correction when N04 routes back to A08."""

    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    a09_path = auto_dir / "artifacts" / "a09-oracle-coverage-review.json"
    n04_path = auto_dir / "artifacts" / "n04-test-case-ir-validation.json"
    if not all(path.exists() for path in (a08_path, a09_path, n04_path)):
        return None
    n04_payload = _read(n04_path).get("payload", {})
    if not isinstance(n04_payload, dict):
        return None
    if n04_payload.get("valid") is not False:
        return None
    if n04_payload.get("next_node") != "A08":
        return {
            "node_id": "A08",
            "action": "no_auto_route",
            "next_node": str(n04_payload.get("next_node", "")),
        }
    if n04_payload.get("g02_status") != "not_started":
        return None
    attempt = n04_payload.get("correction_attempt")
    max_attempts = n04_payload.get("max_correction_attempts")
    if not isinstance(attempt, int) or not isinstance(max_attempts, int):
        return None
    if attempt >= max_attempts:
        return {
            "node_id": "A08",
            "action": "correction_budget_exhausted",
            "next_node": "human",
            "correction_attempt": attempt,
            "max_correction_attempts": max_attempts,
        }
    current_hash = str(_read(a08_path).get("artifact_hash", ""))
    if str(n04_payload.get("test_design_artifact_hash", "")) != current_hash:
        return None
    existing_issues = issues_by_node.get("A08", [])
    running = [issue for issue in existing_issues if _issue_running(issue)]
    if running:
        return {
            "node_id": "A08",
            "action": "already_dispatched",
            "issue_id": str(running[0].get("id", "")),
            "mode": "correction",
        }
    correction_issues = [
        issue
        for issue in existing_issues
        if "修正" in str(issue.get("title", ""))
    ]
    if correction_issues:
        return {
            "node_id": "A08",
            "action": "awaiting_ingest",
            "attempts": len(correction_issues),
        }
    a08_bundle_path = inputs_dir / "a08-input.json"
    if not a08_bundle_path.exists():
        return None
    correction_dir = inputs_dir / f"a08-correction-{attempt}"
    correction_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_test_design_correction_input(
        a08_path,
        a08_bundle_path,
        a09_path,
        n04_path,
        correction_dir,
    )
    result = {
        "node_id": "A08",
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "mode": "correction",
        "correction_attempt": attempt,
        "max_correction_attempts": max_attempts,
        "input": str(correction_dir / "a08-input.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
    }
    if not apply:
        return result
    _ensure_agent_instruction(config, "A08", "1.2.1", repo_root)
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A08",
        label="测试设计修正",
        input_path=correction_dir / "a08-input.json",
    )
    bundles = _load_issue_bundles(inputs_dir)
    bundles[str(created["issue_id"])] = str(correction_dir / "a08-input.json")
    _save_issue_bundles(inputs_dir, bundles)
    result.update(created)
    return result


def ensure_a09_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, dict[str, Any]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch the A09 Oracle review Agent once A08 is accepted."""

    if (auto_dir / "artifacts" / "a09-oracle-coverage-review.json").exists():
        return None
    existing_issues = issues_by_node.get("A09", [])
    if existing_issues:
        if any(_issue_running(issue) for issue in existing_issues):
            return {
                "node_id": "A09",
                "action": "already_dispatched",
                "issue_id": str(
                    next(
                        (issue.get("id") for issue in existing_issues if _issue_running(issue)),
                        existing_issues[-1].get("id", ""),
                    )
                ),
            }
        if not _rerun_budget_available(config, "A09", existing_issues):
            return {
                "node_id": "A09",
                "action": "rerun_budget_exhausted",
                "attempts": len(existing_issues),
            }
    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    a08_bundle_path = inputs_dir / "a08-input.json"
    if not a08_path.exists() or not a08_bundle_path.exists():
        return None
    oracle_rules_path = _config_path(config, "oracle_rule_library", repo_root)
    if not oracle_rules_path:
        return None
    inputs_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_oracle_review_input(
        a08_path, a08_bundle_path, oracle_rules_path, inputs_dir
    )
    result = {
        "node_id": "A09",
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "input": str(inputs_dir / "a09-input.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
    }
    if not apply:
        return result
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A09",
        label="Oracle 与覆盖审查",
        input_path=inputs_dir / "a09-input.json",
    )
    result.update(created)
    return result


def ensure_a09_correction_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch an A09 re-review once a corrected A08 design is ingested."""

    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    a09_path = auto_dir / "artifacts" / "a09-oracle-coverage-review.json"
    n04_path = auto_dir / "artifacts" / "n04-test-case-ir-validation.json"
    if not all(path.exists() for path in (a08_path, a09_path, n04_path)):
        return None
    n04_payload = _read(n04_path).get("payload", {})
    if not isinstance(n04_payload, dict):
        return None
    if n04_payload.get("valid") is not False:
        return None
    next_node = str(n04_payload.get("next_node", ""))
    if next_node == "A08":
        pass
    elif next_node == "human" and _directed_human_recovery_active(inputs_dir.parent):
        pass
    else:
        return None
    if n04_payload.get("g02_status") != "not_started":
        return None
    current_a08_hash = str(_read(a08_path).get("artifact_hash", ""))
    if str(n04_payload.get("test_design_artifact_hash", "")) == current_a08_hash:
        return None
    a08_payload = _read(a08_path).get("payload", {})
    a09_payload = _read(a09_path).get("payload", {})
    a08_bundle_path = _artifact_bundle_path(a08_payload, inputs_dir, "A08")
    a09_bundle_path = _artifact_bundle_path(a09_payload, inputs_dir, "A09")
    if a08_bundle_path is None or a09_bundle_path is None:
        return None
    a09_binds_current = any(
        str(item.get("artifact_id", "")) == "a08-test-design-ir"
        and str(item.get("artifact_hash", "")) == current_a08_hash
        for item in _read(a09_bundle_path).get("upstream_artifacts", [])
    )
    if a09_binds_current:
        return None
    existing_issues = issues_by_node.get("A09", [])
    running = [issue for issue in existing_issues if _issue_running(issue)]
    if running:
        return {
            "node_id": "A09",
            "action": "already_dispatched",
            "issue_id": str(running[0].get("id", "")),
            "mode": "correction",
        }
    correction_issues = [
        issue
        for issue in existing_issues
        if "修正" in str(issue.get("title", ""))
    ]
    if correction_issues:
        return {
            "node_id": "A09",
            "action": "awaiting_ingest",
            "attempts": len(correction_issues),
        }
    oracle_rules_path = _config_path(config, "oracle_rule_library", repo_root)
    if not oracle_rules_path:
        return None
    correction_dir = inputs_dir / f"a09-correction-{n04_payload.get('correction_attempt')}"
    correction_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_oracle_review_input(
        a08_path,
        a08_bundle_path,
        oracle_rules_path,
        correction_dir,
    )
    result = {
        "node_id": "A09",
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "mode": "correction",
        "input": str(correction_dir / "a09-input.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
    }
    if not apply:
        return result
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A09",
        label="Oracle 与覆盖审查修正",
        input_path=correction_dir / "a09-input.json",
    )
    bundles = _load_issue_bundles(inputs_dir)
    bundles[str(created["issue_id"])] = str(correction_dir / "a09-input.json")
    _save_issue_bundles(inputs_dir, bundles)
    result.update(created)
    return result


def ensure_n04_validation(auto_dir: Path, inputs_dir: Path) -> dict[str, Any] | None:
    """Run deterministic N04 once A08 and A09 Artifacts are accepted.

    Re-runs with an incremented correction attempt after a corrected A08
    test-design Artifact has been ingested, so the loop A09 -> N04 -> A08
    correction -> A09 review -> N04 converges without any manual step.
    """

    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    a09_path = auto_dir / "artifacts" / "a09-oracle-coverage-review.json"
    if not a08_path.exists() or not a09_path.exists():
        return None
    a08_payload = _read(a08_path).get("payload", {})
    a09_payload = _read(a09_path).get("payload", {})
    current_a08_hash = str(_read(a08_path).get("artifact_hash", ""))
    current_a09_hash = str(_read(a09_path).get("artifact_hash", ""))
    a09_bundle_path = _artifact_bundle_path(a09_payload, inputs_dir, "A09")
    if a09_bundle_path is None:
        return None
    a09_binds_current = any(
        str(item.get("artifact_id", "")) == "a08-test-design-ir"
        and str(item.get("artifact_hash", "")) == current_a08_hash
        for item in _read(a09_bundle_path).get("upstream_artifacts", [])
    )
    if not a09_binds_current:
        return None
    target = auto_dir / "artifacts" / "n04-test-case-ir-validation.json"
    correction_attempt = 1
    if target.exists():
        existing = _read(target).get("payload", {})
        if (
            str(existing.get("test_design_artifact_hash", "")) == current_a08_hash
            and str(existing.get("oracle_review_artifact_hash", "")) == current_a09_hash
        ):
            return None
        previous_attempt = existing.get("correction_attempt")
        if not isinstance(previous_attempt, int):
            return None
        correction_attempt = previous_attempt + 1
    artifact = run_n04_after_a09(
        a08_path,
        a09_path,
        a09_bundle_path,
        auto_dir,
        correction_attempt=correction_attempt,
    )
    payload = artifact.get("payload", {})
    return {
        "node_id": "N04",
        "artifact_id": artifact.get("artifact_id"),
        "valid": bool(payload.get("valid")),
        "next_node": payload.get("next_node"),
        "correction_attempt": correction_attempt,
    }


def _human_correction_request_binds_current_n04(
    request_path: Path, n04_path: Path
) -> bool:
    try:
        request = _read(request_path)
        n04 = _read(n04_path)
    except (OSError, json.JSONDecodeError):
        return False
    upstream = request.get("upstream_artifacts", [])
    if not isinstance(upstream, list):
        return False
    expected = next(
        (
            item.get("artifact_hash")
            for item in upstream
            if isinstance(item, dict)
            and item.get("artifact_id") == "n04-test-case-ir-validation"
        ),
        None,
    )
    return expected is not None and expected == n04.get("artifact_hash")


def _directed_human_recovery_active(artifact_root: Path) -> bool:
    """Whether a human-directed recovery is authorized but not yet revalidated."""

    correction_dir = artifact_root / "human-correction"
    outcome_path = correction_dir / "human-correction-outcome.json"
    request_path = correction_dir / "human-correction-request.json"
    n04_path = artifact_root / "artifacts-auto" / "artifacts" / "n04-test-case-ir-validation.json"
    if not outcome_path.exists() or not request_path.exists() or not n04_path.exists():
        return False
    try:
        outcome = _read(outcome_path)
    except (OSError, json.JSONDecodeError):
        return False
    return (
        outcome.get("decision") == "directed_correction"
        and _human_correction_request_binds_current_n04(request_path, n04_path)
    )


def _archive_human_correction_round(correction_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = correction_dir.parent / f"human-correction-{stamp}"
    if archive.exists():
        raise RuntimeError(f"human correction archive already exists: {archive}")
    correction_dir.rename(archive)
    return archive


def _dispatch_human_recovery(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    correction_dir: Path,
    policy_path: Path,
    *,
    apply: bool,
) -> dict[str, Any]:
    """Dispatch the A08 v1.3.0 recovery once a directed human decision is final."""

    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    a09_path = auto_dir / "artifacts" / "a09-oracle-coverage-review.json"
    n04_path = auto_dir / "artifacts" / "n04-test-case-ir-validation.json"
    request_path = correction_dir / "human-correction-request.json"
    decision_path = correction_dir / "human-correction-decision.json"
    if not request_path.exists() or not decision_path.exists():
        return {"node_id": "A08", "action": "recovery_missing_decision"}
    in_flight = [
        issue
        for issue in issues_by_node.get("A08", [])
        if "修正" in str(issue.get("title", "")) and _issue_running(issue)
    ]
    if in_flight:
        return {
            "node_id": "A08",
            "action": "recovery_in_flight",
            "issue_id": str(in_flight[0].get("id", "")),
        }
    a08_payload = _read(a08_path).get("payload", {})
    a08_bundle_path = _artifact_bundle_path(a08_payload, inputs_dir, "A08")
    if a08_bundle_path is None:
        return {"node_id": "A08", "action": "recovery_missing_bundle"}
    n04_payload = _read(n04_path).get("payload", {})
    next_attempt = int(n04_payload.get("correction_attempt", 1)) + 1
    recovery_dir = inputs_dir / f"a08-correction-{next_attempt}"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_test_design_correction_input(
        a08_path,
        a08_bundle_path,
        a09_path,
        n04_path,
        recovery_dir,
        human_correction_request_path=request_path,
        human_correction_decision_path=decision_path,
        human_correction_policy_path=policy_path,
    )
    result = {
        "node_id": "A08",
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "mode": "human_recovery",
        "correction_attempt": next_attempt,
        "input": str(recovery_dir / "a08-input.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
    }
    if not apply:
        return result
    _ensure_agent_instruction(config, "A08", "1.3.0", repo_root)
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A08",
        label="测试设计人工修正",
        input_path=recovery_dir / "a08-input.json",
    )
    bundles = _load_issue_bundles(inputs_dir)
    bundles[str(created["issue_id"])] = str(recovery_dir / "a08-input.json")
    _save_issue_bundles(inputs_dir, bundles)
    result.update(created)
    return result


def ensure_human_correction_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    artifact_root: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Open or advance the human-directed Test Case IR correction once N04 routes to human."""

    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    a09_path = auto_dir / "artifacts" / "a09-oracle-coverage-review.json"
    n04_path = auto_dir / "artifacts" / "n04-test-case-ir-validation.json"
    policy_path = _config_path(config, "human_correction_policy", repo_root)
    if policy_path is None:
        return None
    if not all(path.exists() for path in (a08_path, a09_path, n04_path)):
        return None
    n04_payload = _read(n04_path).get("payload", {})
    if not isinstance(n04_payload, dict):
        return None
    if n04_payload.get("valid") is not False or n04_payload.get("next_node") != "human":
        return None
    if n04_payload.get("g02_status") != "not_started":
        return None
    correction_dir = artifact_root / "human-correction"
    correction_dir.mkdir(parents=True, exist_ok=True)
    request_path = correction_dir / "human-correction-request.json"
    outcome_path = correction_dir / "human-correction-outcome.json"
    state_path = correction_dir / "human-correction-state.json"

    if not request_path.exists():
        try:
            prepare_human_correction_request(
                a08_path, a09_path, n04_path, policy_path, correction_dir
            )
        except Exception as error:
            return {"node_id": "HUMAN", "action": "prepare_failed", "error": str(error)}
        if not apply:
            return {
                "node_id": "HUMAN",
                "action": "would_open",
                "request": str(request_path),
            }
        try:
            open_multica_human_correction(
                request_path,
                policy_path,
                correction_dir,
                runner=_human_correction_runner,
            )
        except Exception as error:
            return {"node_id": "HUMAN", "action": "open_failed", "error": str(error)}
        state = _read(state_path) if state_path.exists() else {}
        issue_id = state.get("issue_id")
        identifier = ""
        if issue_id:
            try:
                identifier = str(_multica("issue", "get", str(issue_id)).get("identifier", ""))
            except Exception:
                pass
        return {
            "node_id": "HUMAN",
            "action": "opened",
            "issue_id": issue_id,
            "issue_identifier": identifier,
            "request_hash": _read(request_path).get("request_hash"),
        }

    if outcome_path.exists():
        outcome = _read(outcome_path)
        if outcome.get("decision") != "directed_correction":
            return {
                "node_id": "HUMAN",
                "action": "terminated",
                "decision": outcome.get("decision"),
            }
        return _dispatch_human_recovery(
            config,
            run_id,
            auto_dir,
            inputs_dir,
            repo_root,
            issues_by_node,
            correction_dir,
            policy_path,
            apply=apply,
        )

    if not apply:
        state = _read(state_path) if state_path.exists() else {}
        return {
            "node_id": "HUMAN",
            "action": "would_sync" if not state.get("issue_id") else "waiting_for_human",
            "issue_id": state.get("issue_id"),
        }
    state = _read(state_path) if state_path.exists() else {}
    if not state.get("issue_id"):
        try:
            open_multica_human_correction(
                request_path,
                policy_path,
                correction_dir,
                runner=_human_correction_runner,
            )
        except Exception as error:
            return {"node_id": "HUMAN", "action": "open_failed", "error": str(error)}
        state = _read(state_path) if state_path.exists() else {}
        issue_id = state.get("issue_id")
        identifier = ""
        if issue_id:
            try:
                identifier = str(_multica("issue", "get", str(issue_id)).get("identifier", ""))
            except Exception:
                pass
        return {
            "node_id": "HUMAN",
            "action": "opened",
            "issue_id": issue_id,
            "issue_identifier": identifier,
            "request_hash": _read(request_path).get("request_hash"),
        }
    try:
        synced = sync_multica_human_correction(
            request_path,
            n04_path,
            policy_path,
            correction_dir,
            runner=_human_correction_runner,
        )
    except Exception as error:
        if _human_correction_request_binds_current_n04(request_path, n04_path):
            return {"node_id": "HUMAN", "action": "sync_failed", "error": str(error)}
        archive = _archive_human_correction_round(correction_dir)
        fresh = ensure_human_correction_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root,
            inputs_dir,
            repo_root,
            issues_by_node,
            apply=apply,
        )
        if fresh is None:
            fresh = {"node_id": "HUMAN", "action": "no_route"}
        fresh["archived_round"] = str(archive)
        return fresh
    if synced.get("decision") is None:
        state = _read(state_path) if state_path.exists() else {}
        return {
            "node_id": "HUMAN",
            "action": "waiting_for_human",
            "issue_id": state.get("issue_id"),
            "observed_status": synced.get("observed_multica_status"),
        }
    if synced.get("decision") != "directed_correction":
        return {
            "node_id": "HUMAN",
            "action": "terminated",
            "decision": synced.get("decision"),
        }
    return _dispatch_human_recovery(
        config,
        run_id,
        auto_dir,
        inputs_dir,
        repo_root,
        issues_by_node,
        correction_dir,
        policy_path,
        apply=apply,
    )


def _inject_human_action_entry(spec_path: Path, artifact_root: Path) -> None:
    """Point waiting-human nodes at the open human-correction Issue, if any."""

    state_path = artifact_root / "human-correction" / "human-correction-state.json"
    spec = _read(spec_path)
    issue_id = ""
    identifier = ""
    status = ""
    if state_path.exists():
        state = _read(state_path)
        issue_id = str(state.get("issue_id") or "").strip()
        status = str(state.get("observed_multica_status") or state.get("state") or "")
        if issue_id:
            try:
                details = _multica("issue", "get", issue_id)
                identifier = str(details.get("identifier", ""))
            except Exception:
                pass
    changed = False
    for node in spec.get("nodes", []):
        if not isinstance(node, dict) or node.get("state") != "waiting_human":
            continue
        if issue_id:
            node["human_action_entry"] = {
                "issue_id": issue_id,
                "issue_identifier": identifier,
                "status": status,
            }
            changed = True
        elif "human_action_entry" in node:
            del node["human_action_entry"]
            changed = True
    if changed:
        ArtifactStore(spec_path.parent).write_json(spec_path.name, spec)


def _publish_g02_review_artifact(
    auto_dir: Path,
    request: dict[str, Any],
    *,
    status: ArtifactStatus,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish the G02 Gate Artifact that drives the workflow projection."""

    payload: dict[str, Any] = {
        "schema_version": str(request.get("schema_version", "test-case-ir-review-request/1.0")),
        "gate_id": "G02",
        "workflow_run_id": str(request["workflow_run_id"]),
        "source_snapshot_id": str(request["source_snapshot_id"]),
        "request_hash": str(request.get("request_hash", "")),
        "review_key": str(request.get("review_key", "")),
        "upstream_artifacts": request.get("upstream_artifacts", []),
        "issues": request.get("issues", []),
        "review_policy": request.get("review_policy", {}),
    }
    if decision is not None:
        payload.update(
            {
                "decision": decision.get("decision"),
                "decision_hash": decision.get("decision_hash"),
                "decided_at": decision.get("decided_at"),
                "resolutions": decision.get("resolutions", []),
            }
        )
    envelope = ArtifactEnvelope(
        workflow_run_id=str(request["workflow_run_id"]),
        workflow_mode=str(request.get("workflow_mode", "new_requirement")),
        artifact_id="g02-test-case-ir-review",
        source_snapshot_id=str(request["source_snapshot_id"]),
        producer=Producer(
            component_id="G02-AUTO",
            component_version="1.0.0",
            runtime="deterministic-node",
            profile_version="1.0.0",
            model_provider="deterministic",
            model_snapshot="none",
            prompt_version="none",
            tool_bundle_version="none",
        ),
        payload=payload,
        status=status,
    )
    target = auto_dir / "artifacts" / "g02-test-case-ir-review.json"
    if target.exists():
        existing = _read(target)
        if existing.get("artifact_hash") == envelope.artifact_hash:
            return {"artifact_id": "g02-test-case-ir-review", "status": status.value, "reused": True}
    ArtifactStore(auto_dir).write_artifact(envelope)
    return {"artifact_id": "g02-test-case-ir-review", "status": status.value, "reused": False}


def ensure_g02_review(
    config: dict[str, Any],
    auto_dir: Path,
    review_dir: Path,
    repo_root: Path,
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Open the G02 Test Case IR human Gate once N04 validates the IR."""

    policy_path = _config_path(config, "g02_policy", repo_root)
    if not policy_path:
        return None
    n04_path = auto_dir / "artifacts" / "n04-test-case-ir-validation.json"
    if not n04_path.exists():
        return None
    n04_payload = _read(n04_path).get("payload", {})
    if not isinstance(n04_payload, dict) or n04_payload.get("valid") is not True:
        return None
    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    a09_path = auto_dir / "artifacts" / "a09-oracle-coverage-review.json"
    if not a08_path.exists() or not a09_path.exists():
        return None
    review_dir.mkdir(parents=True, exist_ok=True)
    request = prepare_test_case_review_request(
        a08_path, a09_path, n04_path, policy_path, review_dir
    )
    result = {
        "node_id": "G02",
        "action": "would_open" if not apply else "open_ready",
        "request_hash": str(request.get("request_hash", "")),
        "review_key": str(request.get("review_key", "")),
    }
    try:
        published = _publish_g02_review_artifact(
            auto_dir, request, status=ArtifactStatus.NEEDS_HUMAN
        )
        result["artifact"] = published
    except Exception as error:
        result["artifact_error"] = str(error)
    if not apply:
        return result
    request_path = review_dir / "g02-review-request.json"
    try:
        open_multica_test_case_review(request_path, policy_path, review_dir)
        outcome = sync_multica_test_case_review(request_path, n04_path, policy_path, review_dir)
        result["state"] = str(outcome.get("state", outcome.get("schema_version", "")))
        decision_path = review_dir / "g02-review-decision.json"
        if decision_path.exists():
            decision = _read(decision_path)
            decision_value = str(decision.get("decision", ""))
            if decision_value == "approved":
                terminal = _publish_g02_review_artifact(
                    auto_dir, request, status=ArtifactStatus.COMPLETED, decision=decision
                )
                result["terminal_artifact"] = terminal
            elif decision_value == "rejected":
                terminal = _publish_g02_review_artifact(
                    auto_dir, request, status=ArtifactStatus.CANCELLED, decision=decision
                )
                result["terminal_artifact"] = terminal
            else:
                result["returned"] = True
    except Exception as error:
        result["error"] = str(error)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--sync-output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="run the sync loop forever so completed Agent runs are auto-ingested "
        "and the next node is dispatched without any manual step",
    )
    parser.add_argument("--watch-interval", type=int, default=60)
    return parser


def _run_sync_once(args: argparse.Namespace) -> int:
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
    ingest_failures = _load_ingest_failures(artifact_root)
    issue_bundles = _load_issue_bundles(artifact_root / "inputs")
    node_entries: dict[str, dict[str, Any]] = {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        title = str(issue.get("title", ""))
        if not title.startswith(prefix):
            continue
        node_id = title[len(prefix):].split(" ", 1)[0]
        if node_id not in node_agents:
            continue
        bundle_path = issue_bundles.get(str(issue.get("id", "")))
        if bundle_path is None:
            bundle_relative = node_input_files.get(node_id)
            if not isinstance(bundle_relative, list) or not bundle_relative:
                continue
            bundle_path = Path(str(bundle_relative[0]))
        else:
            bundle_path = Path(bundle_path)
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
        existing = node_entries.get(node_id)
        if existing is not None and str(existing["run"].get("created_at", "")) >= str(
            run.get("created_at", "")
        ):
            continue
        node_entries[node_id] = {
            "issue": issue,
            "run": run,
            "bundle_path": bundle_path,
        }
    for node_id, entry in node_entries.items():
        issue = entry["issue"]
        run = entry["run"]
        bundle_path = entry["bundle_path"]
        node_run_id = str(run["id"])
        if _ingest_already_failed(
            ingest_failures, node_id, str(issue["id"]), node_run_id
        ):
            continue
        if _already_ingested(auto_dir, bundle_path, node_run_id):
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
            ingest_failures.setdefault(node_id, []).append(
                {"issue_id": str(issue["id"]), "run_id": node_run_id}
            )
    _save_ingest_failures(artifact_root, ingest_failures)

    g01_result = None
    g01_transition = None
    g01_published = None
    n24_result = None
    g01_policy = config.get("g01_policy")
    if g01_policy:
        policy_path = Path(str(g01_policy))
        if not policy_path.is_absolute():
            policy_path = repo_root / policy_path
        try:
            n24_result = ensure_n24_test_strategy(
                config, auto_dir, artifact_root / "g01-auto", repo_root
            )
        except Exception as error:
            errors.append({"node_id": "N24", "error": str(error)})
        g01_result = ensure_g01_scope_review(
            auto_dir,
            policy_path,
            output_dir=artifact_root / "g01-auto",
        )
        adapter_value = config.get("g01_adapter_policy")
        if args.apply and g01_result and g01_result["status"] == "needs_human" and adapter_value:
            adapter_path = Path(str(adapter_value))
            if not adapter_path.is_absolute():
                adapter_path = repo_root / adapter_path
            c2 = next(
                (
                    card for card in spec.get("stage_cards", [])
                    if isinstance(card, dict) and card.get("stage_card_id") == "C2"
                ),
                None,
            )
            if not c2 or not c2.get("issue_id"):
                errors.append({"node_id": "G01", "error": "C2 stage card binding is missing"})
            else:
                review_dir = artifact_root / "g01-auto"
                try:
                    open_multica_scope_review(
                        review_dir / "g01-review-request.json",
                        policy_path,
                        adapter_path,
                        review_dir,
                        issue_id=str(c2["issue_id"]),
                    )
                    g01_transition = sync_multica_scope_review(
                        review_dir / "g01-review-request.json",
                        policy_path,
                        adapter_path,
                        review_dir,
                    )
                    g01_published = publish_g01_decision_artifact(auto_dir, review_dir)
                except Exception as error:
                    errors.append({"node_id": "G01", "error": str(error)})

    issues_by_node = _node_issues_by_id(issues, run_id)
    a08_result = None
    a08_correction_result = None
    a09_result = None
    a09_correction_result = None
    n04_result = None
    g02_result = None
    try:
        a08_result = ensure_a08_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            artifact_root / "g01-auto",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A08", "error": str(error)})
    if a08_result and a08_result.get("action") == "dispatched":
        issues_by_node.setdefault("A08", []).append(
            {
                "id": a08_result["issue_id"],
                "identifier": a08_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A08 测试设计",
                "status": "todo",
            }
        )
    try:
        a09_result = ensure_a09_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A09", "error": str(error)})
    if a09_result and a09_result.get("action") == "dispatched":
        issues_by_node.setdefault("A09", []).append(
            {
                "id": a09_result["issue_id"],
                "identifier": a09_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A09 Oracle 与覆盖审查",
                "status": "todo",
            }
        )
    try:
        a08_correction_result = ensure_a08_correction_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A08", "error": f"correction: {error}"})
    if a08_correction_result and a08_correction_result.get("action") == "dispatched":
        issues_by_node.setdefault("A08", []).append(
            {
                "id": a08_correction_result["issue_id"],
                "identifier": a08_correction_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A08 测试设计修正",
                "status": "todo",
            }
        )
    try:
        a09_correction_result = ensure_a09_correction_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A09", "error": f"correction: {error}"})
    if a09_correction_result and a09_correction_result.get("action") == "dispatched":
        issues_by_node.setdefault("A09", []).append(
            {
                "id": a09_correction_result["issue_id"],
                "identifier": a09_correction_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A09 Oracle 与覆盖审查修正",
                "status": "todo",
            }
        )
    try:
        n04_result = ensure_n04_validation(auto_dir, artifact_root / "inputs")
    except Exception as error:
        errors.append({"node_id": "N04", "error": str(error)})
    human_correction_result = None
    try:
        human_correction_result = ensure_human_correction_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "HUMAN", "error": str(error)})
    try:
        g02_result = ensure_g02_review(
            config, auto_dir, artifact_root / "g02-auto", repo_root, apply=args.apply
        )
    except Exception as error:
        errors.append({"node_id": "G02", "error": str(error)})

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
        _inject_human_action_entry(reconcile_out / "workflow-center-spec.json", artifact_root)
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
        "g01_transition": g01_transition,
        "g01_published": g01_published,
        "n24": n24_result,
        "a08": a08_result,
        "a08_correction": a08_correction_result,
        "a09": a09_result,
        "a09_correction": a09_correction_result,
        "n04": n04_result,
        "human_correction": human_correction_result,
        "g02": g02_result,
        "reconciled": reconciled,
        "sync": sync_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.watch:
        return _run_sync_once(args)
    import time

    interval = max(10, int(args.watch_interval))
    print(
        json.dumps(
            {
                "watch": True,
                "interval_seconds": interval,
                "note": "幂等推进：Agent 完成后自动摄入并派发下一节点，Ctrl+C 退出",
            },
            ensure_ascii=False,
        )
    )
    while True:
        try:
            code = _run_sync_once(args)
        except Exception as error:
            code = 2
            print(json.dumps({"fatal": str(error)}, ensure_ascii=False))
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
