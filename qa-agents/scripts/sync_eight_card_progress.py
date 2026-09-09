#!/usr/bin/env python3
"""Auto-ingest completed Multica node runs and refresh the 8-card projection."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping
from datetime import datetime, timezone

from qa_agents.autopilot import (
    ARTIFACT_NODE_MAP,
    SERVER_NODE_DEFINITIONS,
    _confirmation_binds,
    reconcile_autopilot,
)
from qa_agents.card_copy import node_issue_description, node_issue_title, node_record_description
from qa_agents.constructed_assets import INVENTORY_FILENAME, discover_constructed_assets
from qa_agents.change_set import normalize_change_set
from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, EvidenceRef, Producer
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
from qa_agents.g03_review import (
    open_multica_automation_code_review,
    prepare_automation_code_review_request,
    sync_multica_automation_code_review,
)
from qa_agents.automation import AutomationPolicy, check_automation_generation
from qa_agents.env_precheck import run_n07_env_precheck
from qa_agents.existing_asset_discovery import discover_live_112_assets
from qa_agents.execution import run_n08_automation
from qa_agents.quality_pipeline import (
    quality_tail_needs_refresh,
    remove_quality_tail_after_n17,
    run_server_quality_tail,
)
from qa_agents.test_data import record_constructed_test_data, validate_test_data_plan
from qa_agents.human_correction import (
    open_multica_human_correction,
    prepare_human_correction_request,
    sync_multica_human_correction,
)
from qa_agents.multica import (
    PROFILE_OUTPUTS,
    ContractError,
    extract_multica_model_output,
    ingest_multica_output,
    prepare_multica_alignment_input,
    prepare_multica_automation_generation_input,
    prepare_multica_automation_review_input,
    prepare_multica_oracle_review_input,
    prepare_multica_split_review_input,
    prepare_multica_test_data_plan_input,
    prepare_multica_test_data_plan_revision_input,
    prepare_multica_test_design_correction_input,
    prepare_multica_test_design_input,
)
from qa_agents.multica_cli import resolve_multica_binary
from qa_agents.reporting import render_scope_review_markdown
from qa_agents.risk import run_risk_strategy_after_g01
from qa_agents.security import SecurityPolicy
from qa_agents.stage_two_nodes import (
    run_n15_after_n26,
    run_n25_after_g02,
    run_n26_after_a11,
)
from qa_agents.agents import BackendAutomationReviewAgent
from qa_agents.agents.base import AgentContext
from qa_agents.storage import ArtifactStore
from qa_agents.test_case_gate import run_n04_after_a09
from qa_agents.workflow_center import sync_multica_workflow_center


_DISPATCH_AUTHORIZATION: dict[str, Any] | None = None


def _dispatch_supervision(value: Any) -> dict[str, Any]:
    eligible: set[str] = set()
    dispatched: set[str] = set()

    def visit(item: Any, label: str) -> None:
        if isinstance(item, Mapping):
            action = str(item.get("action", ""))
            node_id = str(item.get("node_id") or label).upper()
            if action in {"dispatch_ready", "g02_correction_dispatch_ready", "dispatch_revision_ready"}:
                eligible.add(node_id)
            if action in {"dispatched", "g02_correction_dispatched"}:
                eligible.add(node_id)
                dispatched.add(node_id)
            for key, child in item.items():
                visit(child, str(key))
        elif isinstance(item, list):
            for child in item:
                visit(child, label)

    visit(value, "unknown")
    return {
        "schema_version": "dispatch-supervision/1.0",
        "eligible_nodes": sorted(eligible),
        "dispatched_nodes": sorted(dispatched),
    }


def _load_dispatch_authorization(path: Path | None, run_id: str) -> None:
    global _DISPATCH_AUTHORIZATION
    if path is None:
        _DISPATCH_AUTHORIZATION = None
        return
    authorization = _read(path)
    unhashed = {key: value for key, value in authorization.items() if key != "plan_hash"}
    if authorization.get("plan_hash") != content_hash(unhashed):
        raise ContractError("Dispatch authorization plan hash is invalid")
    if authorization.get("schema_version") != "dispatch-authorization/1.0":
        raise ContractError("Dispatch authorization schema_version is invalid")
    if authorization.get("workflow_run_id") != run_id:
        raise ContractError("Dispatch authorization belongs to another workflow run")
    allowed = authorization.get("allowed_nodes")
    if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
        raise ContractError("Dispatch authorization allowed_nodes must be a string list")
    _DISPATCH_AUTHORIZATION = authorization


def _assert_dispatch_authorized(run_id: str, node_id: str) -> None:
    if _DISPATCH_AUTHORIZATION is None:
        return
    if _DISPATCH_AUTHORIZATION.get("workflow_run_id") != run_id:
        raise ContractError("Dispatch authorization run changed during sync")
    if node_id not in _DISPATCH_AUTHORIZATION.get("allowed_nodes", []):
        raise ContractError(f"Dispatch of {node_id} was not authorized by the monitor plan")


@contextmanager
def _sync_run_lock(lock_path: Path):
    """Serialize whole sync passes so an unattended timer never overlaps.

    The holder records its PID and start time inside the lock file so a
    starved timer can report who is holding the pass instead of failing
    silently. A hung holder self-heals because every multica call has a
    timeout; the lock is never held by a dead process (flock is released with
    the file descriptor).
    """

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.seek(0)
        holder = lock_file.read().strip() or "unknown"
        lock_file.close()
        raise OSError(f"sync pass already running (lock holder: {holder})")
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(
        f"pid={os.getpid()} since={datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    )
    lock_file.flush()
    try:
        yield
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


_NODE_LABELS = {
    node_id: label
    for node_id, label, _stage in SERVER_NODE_DEFINITIONS
}


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


_MULTICA_BINARY: str | None = None


def _multica_binary() -> str:
    """Resolve the multica CLI, including under launchd's minimal PATH.

    launchd LaunchAgents inherit PATH=/usr/bin:/bin:/usr/sbin:/sbin, which does
    not include /usr/local/bin or /opt/homebrew/bin. Without this fallback the
    unattended timer dies on FileNotFoundError at the very first call and the
    workflow only advances when someone runs the sync manually from a shell.
    """

    global _MULTICA_BINARY
    if _MULTICA_BINARY:
        return _MULTICA_BINARY
    resolved = resolve_multica_binary()
    _MULTICA_BINARY = resolved
    return resolved


def _multica(*args: str, cwd: Path | None = None) -> Any:
    timeout_seconds = float(os.environ.get("SYNC_MULTICA_TIMEOUT_SECONDS", "180"))
    try:
        result = subprocess.run(
            [_multica_binary(), *args, "--output", "json"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        # A hung multica call must fail the pass and release the sync lock;
        # otherwise the launchd timer only ever logs "another sync pass is
        # already running" and the workflow silently stops advancing.
        raise RuntimeError(
            f"multica timed out after {timeout_seconds:.0f}s: {' '.join(args[:2])}"
        ) from error
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
    completed = [
        run
        for run in runs
        if str(run.get("status", "")) == "completed" and run.get("result")
    ]
    if not completed:
        return None
    return max(
        completed,
        key=lambda run: str(run.get("completed_at") or run.get("created_at") or ""),
    )


_DETERMINISTIC_PRODUCER_RUNTIMES = frozenset(
    {
        "human-recovery",
        "deterministic-node",
        "automation-review-runtime",
    }
)


def _already_ingested(auto_dir: Path, bundle_path: Path, run_id: str) -> bool:
    """Whether the latest completed run already produced the current Artifact.

    Deterministic producers (human recovery, in-repo nodes, A18-BE reviewer)
    are the source of truth. A later LLM run of the same node must not keep
    the Issue blocked just because that LLM output failed ingest.
    """

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
    runtime = str(producer.get("runtime", ""))
    if runtime in _DETERMINISTIC_PRODUCER_RUNTIMES:
        return True
    if str(producer.get("tool_bundle_version", "")) != f"multica-task:{run_id}":
        return False
    payload = artifact.get("payload", {})
    if not isinstance(payload, dict):
        return False
    return str(payload.get("input_bundle_hash", "")) == str(bundle.get("bundle_hash", ""))


def _completed_run_ingest_action(
    *,
    auto_dir: Path,
    bundle_path: Path,
    run_id: str,
    ingest_failures: dict[str, list[dict[str, Any]]],
    node_id: str,
    issue_id: str,
) -> str:
    """Decide how to handle one completed Agent run.

    A deterministic Artifact written after a failed LLM ingest (A18-BE) must
    close the Issue. Checking ingest-failure first left QAA-451 blocked even
    though the in-repo reviewer had already approved the current A14 payload.
    """

    if _already_ingested(auto_dir, bundle_path, run_id):
        return "mark_done"
    if _ingest_already_failed(ingest_failures, node_id, issue_id, run_id):
        return "keep_blocked"
    return "ingest"


def _close_agent_issues_for_node(
    issues_by_node: dict[str, list[dict[str, Any]]],
    node_id: str,
    *,
    apply: bool,
) -> list[str]:
    """Mark leftover Agent Issues done once a deterministic Artifact is truth."""

    closed: list[str] = []
    for issue in issues_by_node.get(node_id, []):
        if not isinstance(issue, dict):
            continue
        status = str(issue.get("status", "")).strip()
        if status in {"done", "cancelled"}:
            continue
        issue_id = str(issue.get("id", "")).strip()
        if not issue_id:
            continue
        if apply:
            _multica("issue", "status", issue_id, "done")
        issue["status"] = "done"
        closed.append(issue_id)
    return closed


def _artifact_output(output_dir: Path, artifact_id: str) -> Path:
    return output_dir / "artifacts" / f"{artifact_id}.json"


def _local_codex_default_model() -> tuple[str, str]:
    """Read the model/provider from the local Codex CLI config.

    Agents with an empty ``--model`` inherit the runtime default, which is the
    model pinned in ``~/.codex/config.toml``. The sync must record the same
    model that actually executed the task, not a stale hardcoded fallback.
    """

    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.is_file():
        return "", ""
    try:
        try:
            import tomllib
        except ModuleNotFoundError:
            return "", ""
        with config_path.open("rb") as fh:
            config = tomllib.load(fh)
    except (OSError, ValueError):
        return "", ""
    provider = str(config.get("model_provider", "")).strip()
    model = str(config.get("model", "")).strip()
    return provider, model


def _run_model_metadata(run: dict[str, Any]) -> tuple[str, str]:
    """Read the actual model/provider from a completed Multica run.

    Multica records one usage entry per model call; the last entry is the one
    that produced the final output. Falls back to the local Codex CLI default
    model (``~/.codex/config.toml``) when usage metadata is unavailable, so
    the recorded model always matches the runtime that actually ran the task.
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
    # A local CLI default is not evidence of the model used by the remote run.
    return "unknown", "unknown"


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
    bundle = _read(bundle_path)
    raw_output = run.get("result", {}).get("output") if isinstance(run.get("result"), dict) else None
    if not isinstance(raw_output, str) or not raw_output.strip():
        raw_output = _comment_artifact_output(
            issue, run, str(bundle.get("output_contract", ""))
        )
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise ContractError(f"{node_id} completed run has no ingestible output")
    try:
        extract_multica_model_output(raw_output)
    except ContractError:
        comment_output = _comment_artifact_output(
            issue, run, str(bundle.get("output_contract", ""))
        )
        if comment_output:
            raw_output = comment_output
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


def _comment_artifact_output(
    issue: dict[str, Any],
    run: dict[str, Any],
    expected_contract: str,
) -> str | None:
    """Return the latest issue comment that looks like a model JSON Artifact.

    Multica posts a run's final output as a comment when the output is too
    large to keep in ``result.output``. Only comments whose content is a JSON
    object matching the expected output contract are accepted.
    """

    comments = _multica("issue", "comment", "list", str(issue.get("id", "")))
    if not isinstance(comments, list) or not comments:
        return None
    task_id = str(run.get("id", ""))
    candidates: list[dict[str, Any]] = []
    for comment in comments:
        if not isinstance(comment, Mapping):
            continue
        content = comment.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        source_task_id = str(comment.get("source_task_id", ""))
        if source_task_id and source_task_id != task_id:
            continue
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("schema_version") == expected_contract:
            candidates.append(dict(comment))
    if not candidates:
        return None
    candidates.sort(key=lambda item: str(item.get("created_at", "")))
    return str(candidates[-1]["content"])


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
    text = instruction_path.read_text(encoding="utf-8")
    # 对比完整指令内容而不是只看首行标题，保证指令文件内容更新
    # （例如补充 manifest schema_version 契约）一定能推送到已部署 Agent。
    if text.strip() == hosted.strip():
        return {"node_id": node_id, "profile_version": profile_version, "unchanged": True}
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


def _record_ingest_failure(
    failures: dict[str, list[dict[str, Any]]],
    node_id: str,
    issue_id: str,
    run_id: str,
    bundle_path: Path,
) -> None:
    """Append an ingest-failure record, pinning the bundle hash at failure time."""

    entry: dict[str, Any] = {"issue_id": str(issue_id), "run_id": str(run_id)}
    try:
        bundle = _read(bundle_path)
    except (OSError, json.JSONDecodeError):
        bundle = {}
    if isinstance(bundle, Mapping):
        entry["bundle_hash"] = str(bundle.get("bundle_hash", ""))
    failures.setdefault(node_id, []).append(entry)


def _cancel_duplicate_node_issues(
    issues: list[dict[str, Any]],
    prefix: str,
    node_id: str,
    *,
    keep_issue_id: str,
) -> None:
    """Cancel leftover Agent Issues after a completed run is ingested.

    Ingest failure used to re-dispatch A11 while the first Issue stayed
    blocked. The stage card then showed the dead card as running.
    """

    for other in issues:
        if not isinstance(other, dict):
            continue
        title = str(other.get("title", ""))
        if not title.startswith(prefix):
            continue
        other_node = title[len(prefix):].split(" ", 1)[0]
        if other_node != node_id or str(other.get("id", "")) == keep_issue_id:
            continue
        if _issue_running(other):
            _multica("issue", "status", str(other["id"]), "cancelled")


def _mark_issue_blocked(issue: dict[str, Any]) -> None:
    """Move a node Issue out of the running state after its run failed ingestion.

    A completed run whose output cannot be ingested must not keep the Issue
    ``in_progress`` forever: the state is projected as ``running`` on the stage
    card and blocks every re-dispatch attempt. ``blocked`` is the honest
    terminal state for a failed attempt (``failed`` is not a valid Multica
    status) and lets the rerun budget count the attempt.
    """

    status = str(issue.get("status", "")).strip()
    if status in {"blocked", "done", "cancelled"}:
        return
    _multica("issue", "status", str(issue.get("id", "")), "blocked")


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
    _assert_dispatch_authorized(run_id, node_id)
    project_id = str(config["internal_project_id"])
    workspace_id = str(config["workspace_id"])
    agent_id = str(config.get("node_agents", {}).get(node_id, ""))
    if not agent_id:
        raise RuntimeError(f"no node_agents binding for {node_id}")
    description = node_issue_description(node_id, label, input_name=input_path.name)
    description_path = input_path.with_name(f"{input_path.name}.card.md")
    description_path.write_text(description, encoding="utf-8")
    attachment_path = input_path.resolve()
    command = [
        "issue",
        "create",
        "--title",
        node_issue_title(run_id, node_id, label),
        "--description-file",
        description_path.name,
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
        str(attachment_path),
        # 上一轮尝试可能因摄入失败被置为 blocked（multica 仍视为 active），
        # 重派/修正时必须允许创建新的 Issue 才能推进，而不是永远卡住。
        "--allow-duplicate",
    ]
    created = _multica(*command, cwd=description_path.parent)
    if not isinstance(created, dict) or not created.get("id"):
        raise RuntimeError(f"multica did not create the {node_id} Issue")
    return {
        "node_id": node_id,
        "action": "dispatched",
        "issue_id": str(created["id"]),
        "issue_identifier": str(created.get("identifier", "")),
        "input": str(input_path),
        "attempt": int(_read(input_path).get("correction_attempt", 0)) + 1,
    }


def _refresh_waiting_node_cards(
    *,
    config: dict[str, Any],
    auto_dir: Path,
    node_entries: dict[str, dict[str, Any]],
    run_id: str,
    apply: bool,
) -> list[dict[str, Any]]:
    """Rebuild waiting node cards with approval details and move them to in_review.

    When N04 routes its issues to ``human`` (for example after the automatic
    correction budget is exhausted), every node card that surfaced the same
    issues must show exactly what must be approved. The card description is
    rebuilt from the five-section template plus an approval block, and the
    Issue status moves to ``in_review`` instead of staying blocked. Cards that
    already reached a terminal state (``done``/``cancelled``/``blocked``) are
    left untouched so an existing human decision is never overwritten.
    """

    n04_path = auto_dir / "artifacts" / "n04-test-case-ir-validation.json"
    if not n04_path.exists():
        return []
    n04 = _read(n04_path)
    n04_payload = n04.get("payload", {})
    if not isinstance(n04_payload, dict) or n04_payload.get("next_node") != "human":
        return []
    routed_ids = {
        str(item.get("id"))
        for item in n04_payload.get("issues", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    if not routed_ids:
        return []
    refreshed: list[dict[str, Any]] = []
    prefix = f"[{run_id}] "
    for artifact_path in (auto_dir / "artifacts").glob("*.json"):
        artifact = _read(artifact_path)
        node_id = ARTIFACT_NODE_MAP.get(str(artifact.get("artifact_id", "")))
        if not node_id or node_id not in node_entries:
            continue
        if artifact.get("status") != "needs_human":
            continue
        payload = artifact.get("payload", {})
        issues = payload.get("issues", []) if isinstance(payload, Mapping) else []
        blocking = [
            dict(item)
            for item in issues
            if isinstance(item, Mapping)
            and str(item.get("id")) in routed_ids
            and item.get("severity") in {"error", "blocking"}
        ]
        if not blocking:
            continue
        entry = node_entries[node_id]
        issue = entry["issue"]
        if str(issue.get("status", "")) in {"done", "cancelled", "blocked"}:
            continue
        title = str(issue.get("title", ""))
        label = ""
        if title.startswith(prefix):
            label = title[len(prefix):].split(" ", 1)[-1]
        bundle_path = Path(str(entry["bundle_path"]))
        description = node_issue_description(
            node_id,
            label or str(issue.get("label") or node_id),
            input_name=bundle_path.name,
            approval_issues=blocking,
        )
        refreshed.append(
            {
                "node_id": node_id,
                "issue_id": str(issue.get("id", "")),
                "issue_identifier": str(issue.get("identifier", "")),
                "approval_count": len(blocking),
            }
        )
        if not apply:
            continue
        description_path = bundle_path.with_name(f"{bundle_path.name}.card.md")
        description_path.write_text(description, encoding="utf-8")
        _multica(
            "issue", "update",
            str(issue["id"]),
            "--description-file", description_path.name,
            "--title", title,
            "--project", str(config["internal_project_id"]),
            "--status", "in_review",
            cwd=description_path.parent,
        )
    return refreshed



def ensure_a06_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
    ingest_failures: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any] | None:
    """Auto-dispatch A06 once A02/A03/A05 Artifacts are accepted."""

    if (auto_dir / "artifacts" / "a06-alignment-result.json").exists():
        return None
    existing_issues = issues_by_node.get("A06", [])
    failures = ingest_failures or {}
    failed_issue_ids = {
        str(item.get("issue_id", ""))
        for item in failures.get("A06", [])
        if isinstance(item, Mapping)
    }

    def _a06_open_and_viable(issue: dict[str, Any]) -> bool:
        # An Issue that already failed ingest must not block redispatch forever,
        # even if Multica still shows todo/in_progress before status flips.
        if str(issue.get("id", "")) in failed_issue_ids:
            return False
        return _issue_running(issue)

    if existing_issues:
        if any(_a06_open_and_viable(issue) for issue in existing_issues):
            active_issue = next(
                issue for issue in existing_issues if _a06_open_and_viable(issue)
            )
            existing_bundle = inputs_dir / "a06-input.json"
            if apply and existing_bundle.exists():
                bundles = _load_issue_bundles(inputs_dir)
                issue_id = str(active_issue.get("id", ""))
                if issue_id and issue_id not in bundles:
                    bundles[issue_id] = str(existing_bundle.resolve())
                    _save_issue_bundles(inputs_dir, bundles)
            return {
                "node_id": "A06",
                "action": "already_dispatched",
                "issue_id": str(active_issue.get("id", "")),
            }
        if not _rerun_budget_available(config, "A06", existing_issues):
            return {
                "node_id": "A06",
                "action": "rerun_budget_exhausted",
                "attempts": len(existing_issues),
            }
    artifact_dir = auto_dir / "artifacts"
    required = [
        artifact_dir / "a02-requirement-analysis.json",
        artifact_dir / "a03-technical-testability-analysis.json",
        artifact_dir / "a05-backend-change-analysis.json",
    ]
    if not all(path.exists() for path in required):
        return None
    inputs_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_alignment_input(artifact_dir, inputs_dir)
    result = {
        "node_id": "A06",
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "input": str(inputs_dir / "a06-input.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
    }
    if not apply:
        return result
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A06",
        label="需求与变更对齐",
        input_path=inputs_dir / "a06-input.json",
    )
    bundles = _load_issue_bundles(inputs_dir)
    bundles[str(created["issue_id"])] = str((inputs_dir / "a06-input.json").resolve())
    _save_issue_bundles(inputs_dir, bundles)
    result.update(created)
    return result


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
        and _issue_running(issue)
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
    bundles[str(created["issue_id"])] = str((correction_dir / "a08-input.json").resolve())
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
    g02_correction_pending = _g02_review_returned_with_corrected_a08(
        auto_dir, n04_payload
    )
    if n04_payload.get("valid") is not False and not g02_correction_pending:
        return None
    next_node = str(n04_payload.get("next_node", ""))
    if next_node == "A08":
        pass
    elif next_node == "human" and _directed_human_recovery_active(inputs_dir.parent):
        pass
    elif next_node == "G02" and g02_correction_pending:
        pass
    else:
        return None
    if n04_payload.get("g02_status") not in {"not_started", "pending"}:
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
        and _issue_running(issue)
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
    bundles[str(created["issue_id"])] = str((correction_dir / "a09-input.json").resolve())
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
    if str(n04_payload.get("test_design_artifact_hash", "")) != str(
        _read(a08_path).get("artifact_hash", "")
    ):
        return {
            "node_id": "A08",
            "action": "recovery_completed",
            "artifact_hash": str(_read(a08_path).get("artifact_hash", "")),
        }
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
    bundles[str(created["issue_id"])] = str((recovery_dir / "a08-input.json").resolve())
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
                live_status = str(details.get("status", "")).strip()
                if live_status in {"done", "cancelled"}:
                    # 人工决策已处理，旧授权卡不再是有效操作入口
                    issue_id = ""
                else:
                    status = live_status or status
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
        "review_items": request.get("review_items", []),
        "review_summary": request.get("review_summary", {}),
        "skipped_scenarios": request.get("skipped_scenarios", []),
        "decision_items": request.get("decision_items", []),
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


def _g02_round_frozen_inputs_stale(review_dir: Path, n04_path: Path) -> bool:
    request_path = review_dir / "g02-review-request.json"
    if not request_path.exists() or not n04_path.exists():
        return False
    try:
        request = _read(request_path)
        n04 = _read(n04_path)
    except (OSError, json.JSONDecodeError):
        return False
    upstream = request.get("upstream_artifacts")
    if not isinstance(upstream, list):
        return False
    bound = next(
        (
            item.get("artifact_hash")
            for item in upstream
            if isinstance(item, dict)
            and item.get("artifact_id") == "n04-test-case-ir-validation"
        ),
        None,
    )
    return bound is not None and bound != n04.get("artifact_hash")


def _archive_stale_g02_round(review_dir: Path, n04_path: Path) -> bool:
    """Archive a G02 round whose frozen N04 inputs changed so a fresh round opens."""

    if not _g02_round_frozen_inputs_stale(review_dir, n04_path):
        return False
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = review_dir.parent / f"g02-round-{stamp}"
    if archive.exists():
        raise RuntimeError(f"G02 round archive already exists: {archive}")
    review_dir.rename(archive)
    review_dir.mkdir(parents=True, exist_ok=True)
    return True


def _g02_returned_outcome(review_dir: Path) -> dict[str, Any] | None:
    outcome_path = review_dir / "g02-review-outcome.json"
    if not outcome_path.exists():
        return None
    try:
        outcome = _read(outcome_path)
    except (OSError, json.JSONDecodeError):
        return None
    if outcome.get("decision") != "request_changes":
        return None
    return outcome


def _g02_review_returned_with_corrected_a08(
    auto_dir: Path, n04_payload: Mapping[str, Any]
) -> bool:
    """Whether a returned G02 round is waiting on re-review of a corrected A08."""

    outcome = _g02_returned_outcome(auto_dir.parent / "g02-auto")
    if outcome is None:
        return False
    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    if not a08_path.exists():
        return False
    try:
        a08_hash = str(_read(a08_path).get("artifact_hash", ""))
    except (OSError, json.JSONDecodeError):
        return False
    return str(n04_payload.get("test_design_artifact_hash", "")) != a08_hash


def ensure_g02_review(
    config: dict[str, Any],
    auto_dir: Path,
    review_dir: Path,
    repo_root: Path,
    *,
    apply: bool,
    issue_id: str | None = None,
) -> dict[str, Any] | None:
    """Open the G02 Test Case IR human Gate once N04 validates the IR.

    When ``issue_id`` is the C3 stage card, G02 binds that card instead of
    creating a separate review Issue. Marking C3 done is then the G02 decision.
    """

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
    archived = _archive_stale_g02_round(review_dir, n04_path)
    request = prepare_test_case_review_request(
        a08_path, a09_path, n04_path, policy_path, review_dir
    )
    result = {
        "node_id": "G02",
        "action": "would_open" if not apply else "open_ready",
        "request_hash": str(request.get("request_hash", "")),
        "review_key": str(request.get("review_key", "")),
    }
    if archived:
        result["archived_round"] = True
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
        open_multica_test_case_review(
            request_path, policy_path, review_dir, issue_id=issue_id
        )
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
                returned = _publish_g02_review_artifact(
                    auto_dir, request, status=ArtifactStatus.BLOCKED_INPUT, decision=decision
                )
                result["returned_artifact"] = returned
    except Exception as error:
        result["error"] = str(error)
    return result


def ensure_g02_correction_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    review_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Dispatch the A08 v1.4.0 correction once the G02 reviewer requests changes.

    The G02 card comment becomes the fix direction: ``g02-review-decision.json``
    carries the reviewer comment, and ``prepare_multica_test_design_correction_input``
    binds it into the A08 input so the Agent fixes exactly the reported scenarios.
    """

    outcome = _g02_returned_outcome(review_dir)
    if outcome is None:
        return None
    decision_path = review_dir / "g02-review-decision.json"
    request_path = review_dir / "g02-review-request.json"
    if not request_path.exists() or not decision_path.exists():
        return {"node_id": "A08", "action": "g02_direction_missing"}
    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    a09_path = auto_dir / "artifacts" / "a09-oracle-coverage-review.json"
    n04_path = auto_dir / "artifacts" / "n04-test-case-ir-validation.json"
    if not all(path.exists() for path in (a08_path, a09_path, n04_path)):
        return None
    n04_payload = _read(n04_path).get("payload", {})
    if not isinstance(n04_payload, dict):
        return None
    a08_payload = _read(a08_path).get("payload", {})
    if not isinstance(a08_payload, dict):
        return None
    if (
        str(n04_payload.get("test_design_artifact_hash", ""))
        != str(_read(a08_path).get("artifact_hash", ""))
    ):
        return {
            "node_id": "A08",
            "action": "g02_correction_completed",
            "artifact_hash": str(_read(a08_path).get("artifact_hash", "")),
        }
    if n04_payload.get("g02_status") != "pending":
        return None
    marker_path = review_dir / "g02-correction-dispatched.json"
    if marker_path.exists():
        marker = _read(marker_path)
        if str(marker.get("outcome_hash", "")) == str(outcome.get("outcome_hash", "")):
            return {
                "node_id": "A08",
                "action": "g02_correction_dispatched",
                "issue_id": str(marker.get("issue_id", "")),
            }
    in_flight = [
        issue
        for issue in issues_by_node.get("A08", [])
        if "审核意见" in str(issue.get("title", "")) and _issue_running(issue)
    ]
    if in_flight:
        return {
            "node_id": "A08",
            "action": "g02_correction_in_flight",
            "issue_id": str(in_flight[0].get("id", "")),
        }
    a08_bundle_path = _artifact_bundle_path(a08_payload, inputs_dir, "A08")
    if a08_bundle_path is None:
        return {"node_id": "A08", "action": "g02_correction_missing_bundle"}
    next_attempt = int(n04_payload.get("correction_attempt", 1)) + 1
    correction_dir = inputs_dir / f"a08-correction-{next_attempt}"
    correction_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_test_design_correction_input(
        a08_path,
        a08_bundle_path,
        a09_path,
        n04_path,
        correction_dir,
        g02_review_request_path=request_path,
        g02_review_decision_path=decision_path,
    )
    result = {
        "node_id": "A08",
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "mode": "g02_reviewer_direction",
        "correction_attempt": next_attempt,
        "input": str(correction_dir / "a08-input.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
    }
    if not apply:
        return result
    _ensure_agent_instruction(config, "A08", "1.4.0", repo_root)
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A08",
        label="测试设计审核意见修正",
        input_path=correction_dir / "a08-input.json",
    )
    bundles = _load_issue_bundles(inputs_dir)
    bundles[str(created["issue_id"])] = str((correction_dir / "a08-input.json").resolve())
    _save_issue_bundles(inputs_dir, bundles)
    ArtifactStore(review_dir).write_json(
        "g02-correction-dispatched.json",
        {
            "outcome_hash": outcome.get("outcome_hash"),
            "decision_hash": outcome.get("decision_hash"),
            "issue_id": created["issue_id"],
            "input": str((correction_dir / "a08-input.json").resolve()),
        },
    )
    result.update(created)
    return result


def ensure_n25_compilation(auto_dir: Path, g02_dir: Path) -> dict[str, Any] | None:
    """Run deterministic N25 once G02 approval is published.

    N25 compiles the approved parent Test Case IR into layered child cases
    locally without an Agent, mirroring ensure_n24_test_strategy. The record
    Issue used for the stage-card link is created by ensure_node_record_issues
    on the same sync pass.
    """

    target = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    if target.exists():
        return None
    outcome_path = g02_dir / "g02-review-outcome.json"
    request_path = g02_dir / "g02-review-request.json"
    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    if not (outcome_path.exists() and request_path.exists() and a08_path.exists()):
        return None
    outcome = _read(outcome_path)
    if outcome.get("decision") != "approved" or outcome.get("next_node") != "N25":
        return None
    artifact = run_n25_after_g02(a08_path, request_path, outcome_path, output_dir=auto_dir)
    payload = artifact.get("payload", {})
    return {
        "node_id": "N25",
        "action": "compiled",
        "artifact_id": artifact.get("artifact_id"),
        "artifact_hash": artifact.get("artifact_hash"),
        "parent_count": payload.get("parent_count"),
        "child_count": payload.get("child_count"),
    }


def ensure_a11_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch the A11 split-coverage review Agent once N25 is accepted."""

    if (auto_dir / "artifacts" / "a11-split-coverage-review.json").exists():
        return None
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    a08_path = auto_dir / "artifacts" / "a08-test-design-ir.json"
    if not n25_path.exists() or not a08_path.exists():
        return None
    existing_issues = issues_by_node.get("A11", [])
    if existing_issues:
        if any(_issue_running(issue) for issue in existing_issues):
            return {
                "node_id": "A11",
                "action": "already_dispatched",
                "issue_id": str(
                    next(
                        (issue.get("id") for issue in existing_issues if _issue_running(issue)),
                        existing_issues[-1].get("id", ""),
                    )
                ),
            }
        blocked = [
            issue
            for issue in existing_issues
            if str(issue.get("status", "")) == "blocked"
        ]
        if blocked:
            # A completed A11 run that failed ingest must be consumed, not
            # replaced. A second Issue made C4 show "运行中" on a dead card.
            return {
                "node_id": "A11",
                "action": "awaiting_ingest",
                "issue_id": str(blocked[-1].get("id", "")),
            }
        if not _rerun_budget_available(config, "A11", existing_issues):
            return {
                "node_id": "A11",
                "action": "rerun_budget_exhausted",
                "attempts": len(existing_issues),
            }
    oracle_path = _config_path(config, "oracle_rule_library", repo_root)
    if not oracle_path:
        return None
    a08_payload = _read(a08_path).get("payload", {})
    a08_bundle_path = _artifact_bundle_path(a08_payload, inputs_dir, "A08")
    if a08_bundle_path is None:
        return None
    inputs_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_split_review_input(
        a08_path,
        a08_bundle_path,
        n25_path,
        oracle_path,
        inputs_dir,
    )
    result = {
        "node_id": "A11",
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "input": str(inputs_dir / "a11-input.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
    }
    if not apply:
        return result
    _ensure_agent_instruction(config, "A11", "1.1.0", repo_root)
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A11",
        label="拆分覆盖审查",
        input_path=inputs_dir / "a11-input.json",
    )
    bundles = _load_issue_bundles(inputs_dir)
    bundles[str(created["issue_id"])] = str((inputs_dir / "a11-input.json").resolve())
    _save_issue_bundles(inputs_dir, bundles)
    result.update(created)
    return result


def ensure_n26_selection(
    config: dict[str, Any],
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Run deterministic N26 once an approved A11 review is ingested."""

    a11_path = auto_dir / "artifacts" / "a11-split-coverage-review.json"
    if not a11_path.exists():
        return None
    a11 = _read(a11_path)
    a11_payload = a11.get("payload", {})
    if not isinstance(a11_payload, dict) or a11_payload.get("approved") is not True:
        return None
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    if not n25_path.exists():
        return None
    a11_bundle_path = _artifact_bundle_path(a11_payload, inputs_dir, "A11")
    if a11_bundle_path is None:
        return None
    target = auto_dir / "artifacts" / "n26-test-selection.json"
    if target.exists():
        existing = _read(target)
        existing_a11_hash = next(
            (
                str(item.get("content_hash", ""))
                for item in existing.get("evidence_refs", [])
                if isinstance(item, Mapping)
                and str(item.get("source_id", "")) == "a11-split-coverage-review"
            ),
            "",
        )
        if (
            str(existing.get("payload", {}).get("compiled_artifact_hash", ""))
            == _read(n25_path).get("artifact_hash")
            and existing_a11_hash == a11.get("artifact_hash")
        ):
            return None
    selection_policy_path = _config_path(config, "selection_policy", repo_root)
    artifact = run_n26_after_a11(
        n25_path,
        a11_path,
        a11_bundle_path,
        auto_dir,
        selection_policy_path=selection_policy_path,
    )
    payload = artifact.get("payload", {})
    unresolved = payload.get("unresolved_items", [])
    return {
        "node_id": "N26",
        "artifact_id": artifact.get("artifact_id"),
        "artifact_hash": artifact.get("artifact_hash"),
        "selected_count": len(payload.get("selected_cases", [])),
        "unresolved_count": len(unresolved),
        "status": artifact.get("status"),
        "next_node": "A12" if unresolved else "N15",
    }


def ensure_n15_execution_plan(auto_dir: Path) -> dict[str, Any] | None:
    """Compile the deterministic N15 execution plan once N26 selection is done."""

    n26_path = auto_dir / "artifacts" / "n26-test-selection.json"
    if not n26_path.exists():
        return None
    n26 = _read(n26_path)
    if str(n26.get("status", "")) != "completed":
        return None
    if n26.get("payload", {}).get("unresolved_items"):
        return None
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    if not n25_path.exists():
        return None
    target = auto_dir / "artifacts" / "n15-execution-plan.json"
    if target.exists():
        return None
    # TODO(e2e-generator): skip e2e until A16 is wired into 8-card C5.
    artifact = run_n15_after_n26(
        n26_path, n25_path, auto_dir, skip_layers={"e2e"}
    )
    return {
        "node_id": "N15",
        "artifact_id": artifact.get("artifact_id"),
        "artifact_hash": artifact.get("artifact_hash"),
        "action_count": len(artifact.get("payload", {}).get("actions", [])),
    }


C5_GENERATION_ARTIFACTS = {
    "A14": "a14-backend-automation-generation",
    "A15": "a15-contract-automation-generation",
}
C5_REVIEW_ARTIFACTS = {
    "A18-BE": "a18-be-backend-automation-review",
    "A18-CT": "a18-ct-contract-automation-review",
}
C5_REVIEW_GENERATOR = {
    "A18-BE": "A14",
    "A18-CT": "A15",
}
C5_GENERATION_REVIEWER = {
    "A14": "A18-BE",
    "A15": "A18-CT",
}


def _dispatch_c5_gate(
    config: dict[str, Any],
    node_id: str,
    issues_by_node: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Pre-dispatch gate: never regenerate an input bundle while a node attempt
    is in flight or the rerun budget is exhausted.

    ``ensure_a14/a15/a22_dispatch`` prepare the hash-bound input bundle before
    calling the shared dispatch helper. Regenerating that bundle when an Issue
    was already dispatched replaces the frozen input the running Agent bound to
    (hash mismatch at ingestion, permanent ``in_progress``). The gate mirrors
    the helper's own checks but runs *before* the bundle is (re)written.
    """

    existing = issues_by_node.get(node_id, [])
    if not existing:
        return None
    running = next((issue for issue in existing if _issue_running(issue)), None)
    if running is not None:
        return {
            "node_id": node_id,
            "action": "already_dispatched",
            "issue_id": str(running.get("id", "")),
            "issue_identifier": str(running.get("identifier", "")),
        }
    if not _rerun_budget_available(config, node_id, existing):
        return {
            "node_id": node_id,
            "action": "rerun_budget_exhausted",
            "attempts": len(existing),
        }
    return None


def _dispatch_c5_agent(
    config: dict[str, Any],
    run_id: str,
    node_id: str,
    label: str,
    input_path: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    repo_root: Path,
    apply: bool,
) -> dict[str, Any] | None:
    """Shared idempotent dispatch for C5 Multica Agent nodes."""

    existing_issues = issues_by_node.get(node_id, [])
    if existing_issues:
        if any(_issue_running(issue) for issue in existing_issues):
            return {
                "node_id": node_id,
                "action": "already_dispatched",
                "issue_id": str(
                    next(
                        (issue.get("id") for issue in existing_issues if _issue_running(issue)),
                        existing_issues[-1].get("id", ""),
                    )
                ),
            }
        if not _rerun_budget_available(config, node_id, existing_issues):
            return {
                "node_id": node_id,
                "action": "rerun_budget_exhausted",
                "attempts": len(existing_issues),
            }
    result = {
        "node_id": node_id,
        "action": "would_dispatch" if not apply else "dispatch_ready",
        "input": str(input_path),
    }
    if not apply:
        return result
    _ensure_agent_instruction(config, node_id, "1.0.0", repo_root)
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id=node_id,
        label=label,
        input_path=input_path,
    )
    bundles = _load_issue_bundles(input_path.parent)
    bundles[str(created["issue_id"])] = str(input_path.resolve())
    _save_issue_bundles(input_path.parent, bundles)
    result.update(created)
    return result


def _test_data_plan_valid(n27_path: Path) -> bool:
    """Whether N27 accepted the A22 plan (false when the file is absent)."""

    try:
        payload = _read(n27_path).get("payload", {})
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, Mapping) and payload.get("valid") is True


def _layer_cases_exist(compiled_path: Path, layer: str) -> bool:
    try:
        compiled = _read(compiled_path)
    except (OSError, json.JSONDecodeError):
        return False
    payload = compiled.get("payload")
    cases = (
        payload.get("compiled_cases", payload.get("child_cases"))
        if isinstance(payload, Mapping)
        else None
    )
    return isinstance(cases, list) and any(
        isinstance(item, Mapping) and str(item.get("layer", "")) == layer
        for item in cases
    )


def ensure_a14_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch A14 after N15/N25 and a valid N27 data plan are accepted."""

    target = auto_dir / "artifacts" / "a14-backend-automation-generation.json"
    if target.exists():
        return None
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    n15_path = auto_dir / "artifacts" / "n15-execution-plan.json"
    if not n25_path.exists() or not n15_path.exists():
        return None
    policy_path = _config_path(config, "automation_target_policy", repo_root)
    if not policy_path:
        return None
    if not _layer_cases_exist(n25_path, "backend"):
        return None
    a22_path = auto_dir / "artifacts" / "a22-test-data-plan.json"
    n27_path = auto_dir / "artifacts" / "n27-test-data-plan-validation.json"
    data_ready = _test_data_plan_valid(n27_path)
    if not data_ready or not a22_path.exists():
        return None
    gate = _dispatch_c5_gate(config, "A14", issues_by_node)
    if gate is not None:
        return gate
    inputs_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_automation_generation_input(
        n25_path,
        n15_path,
        policy_path,
        inputs_dir,
        profile_id="A14",
        test_data_plan_path=a22_path,
        test_data_validation_path=n27_path,
        regeneration_round=len(issues_by_node.get("A14", [])),
    )
    return _dispatch_c5_agent(
        config,
        run_id,
        "A14",
        _NODE_LABELS.get("A14", "服务端自动化生成"),
        inputs_dir / "a14-input.json",
        issues_by_node,
        repo_root=repo_root,
        apply=apply,
    )


def ensure_a15_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch the A15 contract automation Agent once N15/N25 are accepted."""

    target = auto_dir / "artifacts" / "a15-contract-automation-generation.json"
    if target.exists():
        return None
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    n15_path = auto_dir / "artifacts" / "n15-execution-plan.json"
    if not n25_path.exists() or not n15_path.exists():
        return None
    policy_path = _config_path(config, "automation_target_policy", repo_root)
    if not policy_path:
        return None
    if not _layer_cases_exist(n25_path, "contract"):
        return None
    n27_path = auto_dir / "artifacts" / "n27-test-data-plan-validation.json"
    if n27_path.exists() and not _test_data_plan_valid(n27_path):
        return None
    gate = _dispatch_c5_gate(config, "A15", issues_by_node)
    if gate is not None:
        return gate
    inputs_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_automation_generation_input(
        n25_path,
        n15_path,
        policy_path,
        inputs_dir,
        profile_id="A15",
        regeneration_round=len(issues_by_node.get("A15", [])),
    )
    return _dispatch_c5_agent(
        config,
        run_id,
        "A15",
        _NODE_LABELS.get("A15", "契约自动化生成"),
        inputs_dir / "a15-input.json",
        issues_by_node,
        repo_root=repo_root,
        apply=apply,
    )


def ensure_a22_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch the A22 test-data plan Agent once N15/N25 are accepted."""

    target = auto_dir / "artifacts" / "a22-test-data-plan.json"
    if target.exists():
        return None
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    n15_path = auto_dir / "artifacts" / "n15-execution-plan.json"
    if not n25_path.exists() or not n15_path.exists():
        return None
    policy_path = _config_path(config, "test_data_policy", repo_root)
    if not policy_path:
        return None
    catalog_path = _config_path(config, "capability_catalog", repo_root)
    sources_path = _config_path(config, "knowledge_sources", repo_root)
    gate = _dispatch_c5_gate(config, "A22", issues_by_node)
    if gate is not None:
        return gate
    inputs_dir.mkdir(parents=True, exist_ok=True)
    discovery = None
    inventory_value = config.get("a22_existing_asset_inventory")
    inventory_path = (
        _config_path(config, "a22_existing_asset_inventory", repo_root)
        if inventory_value
        else auto_dir.parent / "current" / INVENTORY_FILENAME
    )
    if (
        config.get("a22_existing_asset_discovery_enabled", True)
        and inventory_path is not None
        and inventory_path.is_file()
    ):
        compiled = _read(n25_path)
        compiled_payload = compiled.get("payload", {})
        cases = compiled_payload.get("compiled_cases", compiled_payload.get("child_cases", []))
        if isinstance(cases, list):
            discovery = discover_live_112_assets(
                [item for item in cases if isinstance(item, Mapping)],
                inventory_path,
                repo_root=repo_root,
                bug_finder_root=(
                    _config_path(config, "a22_bug_finder_root", repo_root)
                    if config.get("a22_bug_finder_integrity_enabled", True)
                    and config.get("a22_bug_finder_root")
                    else None
                ),
            )
    bundle = prepare_multica_test_data_plan_input(
        n25_path,
        n15_path,
        policy_path,
        inputs_dir,
        capability_catalog_path=catalog_path,
        knowledge_sources_path=sources_path,
        existing_asset_discovery=discovery,
    )
    return _dispatch_c5_agent(
        config,
        run_id,
        "A22",
        _NODE_LABELS.get("A22", "测试数据规划"),
        inputs_dir / "a22-input.json",
        issues_by_node,
        repo_root=repo_root,
        apply=apply,
    )


def ensure_a22_correction_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Dispatch an A22 plan revision once N27 rejects the plan.

    Mirrors the A08/A09 correction loop: the revision bundle re-freezes the
    original scope and adds the rejected plan plus N27 validation error. The
    rerun budget caps how many revision attempts the automation may consume
    before the flow waits for a human.
    """

    n27_path = auto_dir / "artifacts" / "n27-test-data-plan-validation.json"
    a22_path = auto_dir / "artifacts" / "a22-test-data-plan.json"
    if not n27_path.exists() or not a22_path.exists():
        return None
    n27_payload = _read(n27_path).get("payload", {})
    if not isinstance(n27_payload, Mapping):
        return None
    if n27_payload.get("valid") is not False or n27_payload.get("decision") != "rejected":
        return None
    previous_input_path = inputs_dir / "a22-input.json"
    if not previous_input_path.exists():
        return None

    in_flight = [
        issue
        for issue in issues_by_node.get("A22", [])
        if "修正" in str(issue.get("title", "")) and _issue_running(issue)
    ]
    if in_flight:
        return {
            "node_id": "A22",
            "action": "correction_in_flight",
            "issue_id": str(in_flight[0].get("id", "")),
        }
    revision_issues = [
        issue
        for issue in issues_by_node.get("A22", [])
        if "修正" in str(issue.get("title", ""))
    ]
    completed_revisions = sum(
        1 for issue in revision_issues if not _issue_running(issue)
    )
    budget = int(config.get("agent_rerun_budget", 1))
    if completed_revisions >= budget:
        return {
            "node_id": "A22",
            "action": "rerun_budget_exhausted",
            "attempts": completed_revisions,
        }
    revision_attempt = completed_revisions + 1
    correction_dir = inputs_dir / f"a22-correction-{revision_attempt}"
    correction_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_test_data_plan_revision_input(
        a22_path,
        n27_path,
        previous_input_path,
        correction_dir,
        revision_attempt=revision_attempt,
    )
    result = {
        "node_id": "A22",
        "action": "would_dispatch_revision" if not apply else "dispatch_revision_ready",
        "revision_attempt": revision_attempt,
        "input": str(correction_dir / f"a22-input-revision-{revision_attempt}.json"),
        "bundle_hash": str(bundle.get("bundle_hash", "")),
    }
    if not apply:
        return result
    _ensure_agent_instruction(config, "A22", "1.0.0", repo_root)
    created = _create_node_issue(
        config=config,
        run_id=run_id,
        node_id="A22",
        label="测试数据规划修正",
        input_path=correction_dir / f"a22-input-revision-{revision_attempt}.json",
    )
    bundles = _load_issue_bundles(inputs_dir)
    bundles[str(created["issue_id"])] = str(
        (correction_dir / f"a22-input-revision-{revision_attempt}.json").resolve()
    )
    _save_issue_bundles(inputs_dir, bundles)
    result.update(created)
    return result


def _ensure_reviewer_skipped_for_not_applicable_generation(
    auto_dir: Path,
    reviewer: str,
    generation: Mapping[str, Any],
    generation_payload: Mapping[str, Any],
    target: Path,
) -> dict[str, Any] | None:
    """Record a deterministic ``not_applicable`` reviewer Artifact.

    When a generation branch is not applicable (for example A15 without any
    contract Case), the paired A18 reviewer is never dispatched. Without a
    terminal marker the reviewer node stays ``not_started`` forever and the
    stage card can never reach ``done``, so the next stage never starts. The
    deterministic marker keeps the "unselected branch is skipped" invariant
    from the flow design: merge nodes and stage cards must not wait forever on
    a branch that was not selected.
    """

    generation_hash = content_hash(dict(generation_payload))
    if target.exists():
        try:
            existing = _read(target)
        except (OSError, json.JSONDecodeError):
            existing = {}
        existing_payload = existing.get("payload", {})
        if (
            existing.get("status") == ArtifactStatus.NOT_APPLICABLE.value
            and isinstance(existing_payload, Mapping)
            and str(existing_payload.get("generation_hash", "")) == generation_hash
        ):
            return None
    identity = (
        str(generation.get("workflow_run_id", "")),
        str(generation.get("workflow_mode", "")),
        str(generation.get("source_snapshot_id", "")),
    )
    review = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id=C5_REVIEW_ARTIFACTS[reviewer],
        source_snapshot_id=identity[2],
        producer=Producer(
            component_id=reviewer,
            component_version="1.0.0",
            runtime="deterministic-node",
            profile_version="1.0.0",
            model_provider="deterministic",
            model_snapshot="none",
            prompt_version="none",
            tool_bundle_version="none",
        ),
        payload={
            "schema_version": "automation-review/1.0",
            "workflow_run_id": identity[0],
            "source_snapshot_id": identity[2],
            "generation_hash": generation_hash,
            "decision": "not_applicable",
            "reason": "generation branch is not applicable; review not required",
        },
        status=ArtifactStatus.NOT_APPLICABLE,
        reason_code="generation_not_applicable",
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id=str(generation.get("artifact_id", "")),
                location=f"{generation.get('artifact_id', '')}.json",
                content_hash=str(generation.get("artifact_hash", "")),
            ),
        ),
    )
    ArtifactStore(auto_dir).write_artifact(review)
    return {
        "node_id": reviewer,
        "action": "skipped_not_applicable",
        "artifact_id": review.artifact_id,
        "artifact_hash": review.artifact_hash,
    }


def ensure_a18_dispatch(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    reviewer: str,
    apply: bool,
) -> dict[str, Any] | None:
    """Auto-dispatch the A18-BE / A18-CT reviewer once its generation is ingested."""

    if reviewer not in C5_REVIEW_ARTIFACTS:
        raise RuntimeError(f"unsupported A18 reviewer: {reviewer}")
    target = auto_dir / "artifacts" / f"{C5_REVIEW_ARTIFACTS[reviewer]}.json"
    generator = C5_REVIEW_GENERATOR[reviewer]
    generation_path = auto_dir / "artifacts" / f"{C5_GENERATION_ARTIFACTS[generator]}.json"
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    if not generation_path.exists() or not n25_path.exists():
        return None
    generation = _read(generation_path)
    generation_payload = generation.get("payload", {})
    if not isinstance(generation_payload, Mapping) or not isinstance(
        generation_payload.get("manifest"), Mapping
    ):
        if generation.get("status") in {
            ArtifactStatus.NOT_APPLICABLE.value,
            ArtifactStatus.SKIPPED_BY_POLICY.value,
        }:
            return _ensure_reviewer_skipped_for_not_applicable_generation(
                auto_dir, reviewer, generation, generation_payload, target
            )
        return None
    if target.exists():
        # 复核必须绑定当前生成载荷：A14/A15 重生成后旧复核自动失效。移除
        # 陈旧 artifact 触发复核重派，避免用旧复核放行新候选代码。
        try:
            review = _read(target)
        except (OSError, json.JSONDecodeError):
            review = {}
        review_payload = review.get("payload", {})
        if isinstance(review_payload, Mapping) and str(
            review_payload.get("generation_hash", "")
        ) == content_hash(generation_payload):
            return None
    # 在途/预算 gate 必须先于 bundle 重建与 stale 清理：复核输入 bundle 的
    # 哈希会被 run 冻结绑定，若在途时重写文件，run 完成后摄入时哈希不匹配
    # 会永久 in_progress/blocked。gate 返回非 None 时不得改动任何状态。
    gate = _dispatch_c5_gate(config, reviewer, issues_by_node)
    if gate is not None:
        return gate
    if target.exists():
        target.unlink()
        record = target.with_name(f"{target.name}.record.md")
        if record.exists():
            record.unlink()
    bundle_path = _artifact_bundle_path(generation_payload, inputs_dir, generator)
    if bundle_path is None:
        return None
    policy_path = _config_path(config, "automation_target_policy", repo_root)
    if not policy_path:
        return None
    inputs_dir.mkdir(parents=True, exist_ok=True)
    bundle = prepare_multica_automation_review_input(
        generation_path,
        bundle_path,
        n25_path,
        policy_path,
        inputs_dir,
        profile_id=reviewer,
        regeneration_round=len(issues_by_node.get(reviewer, [])),
    )
    return _dispatch_c5_agent(
        config,
        run_id,
        reviewer,
        _NODE_LABELS.get(reviewer, reviewer),
        inputs_dir / f"{reviewer.casefold()}-input.json",
        issues_by_node,
        repo_root=repo_root,
        apply=apply,
    )


def ensure_a18_be_deterministic_review(
    auto_dir: Path,
    issues_by_node: dict[str, list[dict[str, Any]]] | None = None,
    *,
    apply: bool = False,
) -> dict[str, Any] | None:
    """Keep A18-BE aligned with the in-repo reviewer after Multica ingest.

    The LLM A18-BE card has treated unique dotted extract keys as overwrite and
    missing readiness as needs_human. That reopened a C5 blocked/in-review gate
    after G03 was removed. The deterministic A18-BE reviewer is the contract;
    when it approves the current A14 payload, replace a stale LLM rejection and
    close leftover Multica Issues so the card is not stuck on 等待同步入库.
    """

    generation_path = auto_dir / "artifacts" / "a14-backend-automation-generation.json"
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    if not generation_path.exists() or not n25_path.exists():
        return None
    generation = _read(generation_path)
    n25 = _read(n25_path)
    generation_payload = generation.get("payload", {})
    n25_payload = n25.get("payload", {})
    if not isinstance(generation_payload, Mapping) or not isinstance(
        generation_payload.get("manifest"), Mapping
    ):
        return None
    cases = [
        item
        for item in n25_payload.get("compiled_cases", n25_payload.get("child_cases", []))
        if isinstance(item, Mapping) and str(item.get("id") or "").endswith("-BACKEND")
    ]
    if not cases:
        return None
    context = AgentContext(
        str(generation.get("workflow_run_id", "")),
        str(generation.get("workflow_mode", "")),
        str(generation.get("source_snapshot_id", "")),
        (str(generation_path),),
    )
    review = BackendAutomationReviewAgent().run(
        context,
        {"cases": cases, "generation": generation_payload},
        SecurityPolicy(),
    )
    target = auto_dir / "artifacts" / "a18-be-backend-automation-review.json"
    wrote = True
    if target.exists() and _read(target).get("artifact_hash") == review.artifact_hash:
        wrote = False
    else:
        ArtifactStore(auto_dir).write_artifact(review)
    closed_issues: list[str] = []
    approved = bool(review.payload.get("approved"))
    if (
        review.status == ArtifactStatus.COMPLETED
        and approved
        and issues_by_node
    ):
        closed_issues = _close_agent_issues_for_node(
            issues_by_node, "A18-BE", apply=apply
        )
    if not wrote and not closed_issues:
        return None
    result = {
        "node_id": "A18-BE",
        "action": "deterministic_review",
        "artifact_id": review.artifact_id,
        "artifact_hash": review.artifact_hash,
        "status": review.status.value,
        "approved": approved,
    }
    if closed_issues:
        result["closed_issues"] = closed_issues
        result["action"] = "deterministic_review_closed_issues" if not wrote else result["action"]
    return result


def ensure_n27_validation(
    config: dict[str, Any],
    auto_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Run deterministic N27 on the ingested A22 test-data plan."""

    a22_path = auto_dir / "artifacts" / "a22-test-data-plan.json"
    if not a22_path.exists():
        return None
    a22 = _read(a22_path)
    a22_payload = a22.get("payload", {})
    if not isinstance(a22_payload, Mapping):
        return None
    policy_path = _config_path(config, "test_data_policy", repo_root)
    if not policy_path:
        return None
    target = auto_dir / "artifacts" / "n27-test-data-plan-validation.json"
    if target.exists():
        existing = _read(target)
        bound = next(
            (
                str(item.get("content_hash", ""))
                for item in existing.get("evidence_refs", [])
                if isinstance(item, Mapping)
                and str(item.get("source_id", "")) == "a22-test-data-plan"
            ),
            "",
        )
        if bound == a22.get("artifact_hash"):
            return None
    policy = _read(policy_path)
    deferred_cases = [
        {
            "case_id": str(item.get("case_id", "")),
            "reason_code": str(item.get("reason_code", "paused_by_plan")),
            "route": "deferred_data_construction",
        }
        for item in a22_payload.get("paused_cases", [])
        if isinstance(item, Mapping) and str(item.get("case_id", ""))
    ]
    try:
        validation = validate_test_data_plan(a22_payload, policy)
        if a22.get("status") == ArtifactStatus.NEEDS_HUMAN.value:
            # A22 把无法自动验证的数据语义（图表创建接口、权限夹具、历史种子、
            # 故障注入等）路由给人工确认是合法输出。N27 对这类计划做结构安全校验
            # （环境/命名空间/无密钥/资源类型/操作对），通过后以
            # completed_with_gaps 放行，等待人工在 A22 节点处理未决需求，
            # 而不是把 C5 整条链路死锁在 rejected。
            n27_status = ArtifactStatus.COMPLETED_WITH_GAPS
            reason_code = "test_data_plan_pending_human"
            validation = {
                **validation,
                "pending_human": True,
                "deferred_cases": deferred_cases,
            }
        else:
            n27_status = ArtifactStatus.COMPLETED
            reason_code = None
            validation = {**validation, "deferred_cases": deferred_cases}
    except Exception as error:
        validation = {
            "schema_version": "test-data-plan-validation/1.0",
            "valid": False,
            "decision": "rejected",
            "validation_error": str(error),
        }
        n27_status = ArtifactStatus.BLOCKED
        reason_code = "test_data_plan_invalid"
    identity = (
        str(a22.get("workflow_run_id", "")),
        str(a22.get("workflow_mode", "")),
        str(a22.get("source_snapshot_id", "")),
    )
    n27 = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id=identity[2],
        producer=Producer(
            component_id="N27",
            component_version="1.0.0",
            runtime="deterministic-node",
            profile_version="1.0.0",
            model_provider="deterministic",
            model_snapshot="none",
            prompt_version="none",
            tool_bundle_version="none",
        ),
        payload={
            **validation,
            "a22_artifact_id": "a22-test-data-plan",
            "a22_artifact_hash": a22.get("artifact_hash", ""),
        },
        status=n27_status,
        reason_code=reason_code,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a22-test-data-plan",
                location="a22-test-data-plan.json",
                content_hash=str(a22.get("artifact_hash", "")),
            ),
        ),
    )
    ArtifactStore(auto_dir).write_artifact(n27)
    return {
        "node_id": "N27",
        "artifact_id": n27.artifact_id,
        "artifact_hash": n27.artifact_hash,
        "status": n27.status.value,
        "valid": validation.get("valid"),
        "decision": validation.get("decision"),
    }


def _review_binds_generation(review: Mapping[str, Any], generation_payload: Mapping[str, Any]) -> bool:
    """Whether an A18 review actually reviewed the current generation payload.

    A14/A15 regeneration replaces the generation Artifact; any review left over
    from a previous round binds an older ``generation_hash`` and must not count
    as evidence for the new candidates. Without this check N05 would aggregate
    the stale approval and G03 would open a human review card that claims
    machine review passed for code the reviewer never saw.
    """

    if review.get("status") in {
        ArtifactStatus.NOT_APPLICABLE.value,
        ArtifactStatus.SKIPPED_BY_POLICY.value,
    }:
        return True
    review_payload = review.get("payload")
    if not isinstance(review_payload, Mapping):
        return False
    return str(review_payload.get("generation_hash", "")) == content_hash(generation_payload)


def ensure_n05_aggregation(
    config: dict[str, Any],
    auto_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Run deterministic N05 by aggregating A14/A15 generation and A18 reviews."""

    generation_branches: list[dict[str, Any]] = []
    generations: list[dict[str, Any]] = []
    reviews: dict[str, dict[str, Any]] = {}
    for generator_id, artifact_id in C5_GENERATION_ARTIFACTS.items():
        path = auto_dir / "artifacts" / f"{artifact_id}.json"
        if not path.exists():
            continue
        generation = _read(path)
        payload = generation.get("payload", {})
        if not isinstance(payload, Mapping):
            continue
        generation_branches.append(generation)
        reviewer = C5_GENERATION_REVIEWER[generator_id]
        review_path = auto_dir / "artifacts" / f"{C5_REVIEW_ARTIFACTS[reviewer]}.json"
        if review_path.exists():
            review = _read(review_path)
            if _review_binds_generation(review, payload):
                reviews[reviewer] = review
        if not isinstance(payload.get("manifest"), Mapping):
            continue
        generations.append(generation)
    if not generation_branches:
        return None
    if not generations:
        terminal_skip_statuses = {
            ArtifactStatus.NOT_APPLICABLE.value,
            ArtifactStatus.SKIPPED_BY_POLICY.value,
        }
        if any(
            str(item.get("status", "")) not in terminal_skip_statuses
            for item in generation_branches
        ):
            return None
        target = auto_dir / "artifacts" / "n05-automation-code-check.json"
        evidence = [*generation_branches, *reviews.values()]
        current_hashes = {str(item.get("artifact_hash", "")) for item in evidence}
        if target.exists():
            existing = _read(target)
            existing_hashes = {
                str(item.get("content_hash", ""))
                for item in existing.get("evidence_refs", [])
                if isinstance(item, Mapping)
            }
            if (
                existing.get("status") == ArtifactStatus.NOT_APPLICABLE.value
                and current_hashes == existing_hashes
            ):
                return None
        first = generation_branches[0]
        rejected = sorted(
            {
                str(item.get("case_id"))
                for generation in generation_branches
                for item in generation.get("payload", {}).get("rejected_cases", [])
                if isinstance(item, Mapping) and item.get("case_id")
            }
        )
        n05 = ArtifactEnvelope(
            workflow_run_id=str(first.get("workflow_run_id", "")),
            workflow_mode=str(first.get("workflow_mode", "")),
            artifact_id="n05-automation-code-check",
            source_snapshot_id=str(first.get("source_snapshot_id", "")),
            producer=Producer(
                component_id="N05",
                component_version="1.0.0",
                runtime="deterministic-node",
                profile_version="1.0.0",
                model_provider="deterministic",
                model_snapshot="none",
                prompt_version="none",
                tool_bundle_version="none",
            ),
            payload={
                "schema_version": "automation-code-check/1.0",
                "input_bindings": [],
                "passed": False,
                "fatal_security_violation": False,
                "issues": [],
                "repair_routes": [],
                "generation_count": 0,
                "planned_generation_count": 0,
                "rejected_cases": rejected,
            },
            status=ArtifactStatus.NOT_APPLICABLE,
            reason_code="no_machine_executable_automation_candidate",
            evidence_refs=tuple(
                EvidenceRef(
                    source_type="artifact",
                    source_id=str(item.get("artifact_id", "")),
                    location=f"{item.get('artifact_id', '')}.json",
                    content_hash=str(item.get("artifact_hash", "")),
                )
                for item in evidence
            ),
        )
        ArtifactStore(auto_dir).write_artifact(n05)
        return {
            "node_id": "N05",
            "artifact_id": n05.artifact_id,
            "artifact_hash": n05.artifact_hash,
            "status": n05.status.value,
            "passed": False,
            "fatal": False,
        }
    policy_path = _config_path(config, "automation_target_policy", repo_root)
    if not policy_path:
        return None
    policy = AutomationPolicy.from_file(policy_path)
    target = auto_dir / "artifacts" / "n05-automation-code-check.json"
    if target.exists():
        existing = _read(target)
        existing_hashes = {
            str(item.get("content_hash", ""))
            for item in existing.get("evidence_refs", [])
            if isinstance(item, Mapping)
        }
        # 生成或复核任一 Artifact 变化（A14/A15 重生成、A18 重复核、陈旧复核被
        # 排除/移除）都必须重算，否则会用旧复核/旧生成的结果放行新代码。子集
        # 判断只覆盖"新增"，复核被移除后必须显式重算（无复核不得 passed）。
        current_hashes = {
            str(item.get("artifact_hash", "")) for item in generations
        } | {str(item.get("artifact_hash", "")) for item in reviews.values()}
        if current_hashes and current_hashes == existing_hashes:
            return None
    checks = [check_automation_generation(item.get("payload", {}), policy) for item in generations]
    issues = [item for check in checks for item in check["issues"]]
    bindings = [
        {
            "generation_hash": check["generation_hash"],
            "manifest_hash": check["manifest_hash"],
            "candidate_hashes": check["candidate_hashes"],
        }
        for check in checks
    ]
    passed = bool(checks) and all(check["passed"] for check in checks)
    fatal = any(check["fatal_security_violation"] for check in checks)
    rejected = sorted(
        {
            str(item.get("case_id"))
            for generation in generations
            for item in generation.get("payload", {}).get("rejected_cases", [])
            if isinstance(item, Mapping) and item.get("case_id")
        }
    )
    required_reviews = {
        reviewer: review
        for reviewer, review in reviews.items()
        if str(review.get("status", ""))
        not in {
            ArtifactStatus.NOT_APPLICABLE.value,
            ArtifactStatus.SKIPPED_BY_POLICY.value,
        }
    }
    review_passed = bool(required_reviews) and all(
        isinstance(item.get("payload", {}), Mapping) and item["payload"].get("approved") is True
        for item in required_reviews.values()
    )
    identity = (
        str(generations[0].get("workflow_run_id", "")),
        str(generations[0].get("workflow_mode", "")),
        str(generations[0].get("source_snapshot_id", "")),
    )
    n05_payload = {
        "schema_version": "automation-code-check/1.0",
        "input_bindings": bindings,
        "passed": passed,
        "review_passed": review_passed,
        "fatal_security_violation": fatal,
        "issues": issues,
        "repair_routes": sorted(
            {route for check in checks for route in check["repair_routes"]}
        ),
        "generation_count": len(checks),
        "planned_generation_count": sum(len(item.get("payload", {}).get("code_candidates", [])) for item in generations),
        "rejected_cases": rejected,
    }
    if fatal:
        n05_status = ArtifactStatus.FAILED_FATAL
        n05_reason = "security_policy_violation"
    elif passed:
        # N05 is the deterministic code check only. A18-BE/A18-CT remain
        # independent nodes; folding their approval into needs_human reopened
        # a C5 human-review gate after G03 was removed.
        n05_status = ArtifactStatus.COMPLETED
        n05_reason = None
    else:
        n05_status = ArtifactStatus.NEEDS_HUMAN
        n05_reason = "automation_code_check_failed"
    n05 = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="n05-automation-code-check",
        source_snapshot_id=identity[2],
        producer=Producer(
            component_id="N05",
            component_version="1.0.0",
            runtime="deterministic-node",
            profile_version="1.0.0",
            model_provider="deterministic",
            model_snapshot="none",
            prompt_version="none",
            tool_bundle_version="none",
        ),
        payload=n05_payload,
        status=n05_status,
        reason_code=n05_reason,
        evidence_refs=tuple(
            EvidenceRef(
                source_type="artifact",
                source_id=str(item["artifact_id"]),
                location=f"{item['artifact_id']}.json",
                content_hash=str(item["artifact_hash"]),
            )
            for item in generations
        )
        + tuple(
            EvidenceRef(
                source_type="artifact",
                source_id=str(item["artifact_id"]),
                location=f"{item['artifact_id']}.json",
                content_hash=str(item["artifact_hash"]),
            )
            for item in reviews.values()
        ),
    )
    ArtifactStore(auto_dir).write_artifact(n05)
    return {
        "node_id": "N05",
        "artifact_id": n05.artifact_id,
        "artifact_hash": n05.artifact_hash,
        "status": n05.status.value,
        "passed": n05_payload["passed"],
        "fatal": fatal,
    }


def _publish_g03_review_artifact(
    auto_dir: Path,
    request: dict[str, Any],
    *,
    status: ArtifactStatus,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish the G03 Gate Artifact that drives the workflow projection."""

    payload: dict[str, Any] = {
        "schema_version": str(request.get("schema_version", "automation-code-review-request/1.0")),
        "gate_id": "G03",
        "workflow_run_id": str(request["workflow_run_id"]),
        "source_snapshot_id": str(request["source_snapshot_id"]),
        "request_hash": str(request.get("request_hash", "")),
        "review_key": str(request.get("review_key", "")),
        "upstream_artifacts": request.get("upstream_artifacts", []),
        "summary": request.get("summary", {}),
        "issue_items": request.get("issue_items", []),
        "review_policy": request.get("review_policy", {}),
    }
    if decision is not None:
        payload.update(
            {
                "decision": decision.get("decision"),
                "decision_hash": decision.get("decision_hash"),
                "decided_at": decision.get("decided_at"),
                "reason": decision.get("reason", ""),
            }
        )
    envelope = ArtifactEnvelope(
        workflow_run_id=str(request["workflow_run_id"]),
        workflow_mode=str(request.get("workflow_mode", "new_requirement")),
        artifact_id="g03-automation-code-review",
        source_snapshot_id=str(request["source_snapshot_id"]),
        producer=Producer(
            component_id="G03-AUTO",
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
    target = auto_dir / "artifacts" / "g03-automation-code-review.json"
    if target.exists():
        existing = _read(target)
        if existing.get("artifact_hash") == envelope.artifact_hash:
            return {"artifact_id": "g03-automation-code-review", "status": status.value, "reused": True}
    ArtifactStore(auto_dir).write_artifact(envelope)
    return {"artifact_id": "g03-automation-code-review", "status": status.value, "reused": False}


def _g03_round_frozen_inputs_stale(review_dir: Path, n05_path: Path) -> bool:
    request_path = review_dir / "g03-review-request.json"
    if not request_path.exists() or not n05_path.exists():
        return False
    try:
        request = _read(request_path)
        n05 = _read(n05_path)
    except (OSError, json.JSONDecodeError):
        return False
    upstream = request.get("upstream_artifacts")
    if not isinstance(upstream, list):
        return False
    bound = next(
        (
            item.get("artifact_hash")
            for item in upstream
            if isinstance(item, dict)
            and item.get("artifact_id") == "n05-automation-code-check"
        ),
        None,
    )
    return bound is not None and bound != n05.get("artifact_hash")


def ensure_g03_review(
    config: dict[str, Any],
    auto_dir: Path,
    review_dir: Path,
    repo_root: Path,
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Close G03 without a human card once N05 has a terminal conclusion.

    Automation-code human review is no longer a workflow checkpoint. N05 pass
    (or N05 not-applicable) is enough for C5 to become terminal and N07/N08
    to continue.
    """

    policy_path = _config_path(config, "g03_policy", repo_root)
    if not policy_path:
        return None
    n05_path = auto_dir / "artifacts" / "n05-automation-code-check.json"
    if not n05_path.exists():
        return None
    n05 = _read(n05_path)
    n05_payload = n05.get("payload", {})
    if n05.get("status") in {
        ArtifactStatus.NOT_APPLICABLE.value,
        ArtifactStatus.SKIPPED_BY_POLICY.value,
    }:
        envelope = ArtifactEnvelope(
            workflow_run_id=str(n05.get("workflow_run_id", "")),
            workflow_mode=str(n05.get("workflow_mode", "")),
            artifact_id="g03-automation-code-review",
            source_snapshot_id=str(n05.get("source_snapshot_id", "")),
            producer=Producer(
                component_id="G03-AUTO",
                component_version="1.0.0",
                runtime="deterministic-node",
                profile_version="1.0.0",
                model_provider="deterministic",
                model_snapshot="none",
                prompt_version="none",
                tool_bundle_version="none",
            ),
            payload={
                "schema_version": "automation-code-review/1.0",
                "gate_id": "G03",
                "decision": "not_applicable",
                "reason": "no machine-executable automation candidate requires review",
                "n05_artifact_hash": str(n05.get("artifact_hash", "")),
            },
            status=ArtifactStatus.NOT_APPLICABLE,
            reason_code="automation_generation_not_applicable",
            evidence_refs=(
                EvidenceRef(
                    source_type="artifact",
                    source_id="n05-automation-code-check",
                    location="n05-automation-code-check.json",
                    content_hash=str(n05.get("artifact_hash", "")),
                ),
            ),
        )
        target = auto_dir / "artifacts" / "g03-automation-code-review.json"
        if target.exists() and _read(target).get("artifact_hash") == envelope.artifact_hash:
            return None
        ArtifactStore(auto_dir).write_artifact(envelope)
        return {
            "node_id": "G03",
            "action": "skipped_not_applicable",
            "artifact_id": envelope.artifact_id,
            "artifact_hash": envelope.artifact_hash,
        }
    if not isinstance(n05_payload, Mapping) or n05_payload.get("passed") is not True:
        return None
    envelope = ArtifactEnvelope(
        workflow_run_id=str(n05.get("workflow_run_id", "")),
        workflow_mode=str(n05.get("workflow_mode", "")),
        artifact_id="g03-automation-code-review",
        source_snapshot_id=str(n05.get("source_snapshot_id", "")),
        producer=Producer(
            component_id="G03-AUTO",
            component_version="1.0.0",
            runtime="deterministic-node",
            profile_version="1.0.0",
            model_provider="deterministic",
            model_snapshot="none",
            prompt_version="none",
            tool_bundle_version="none",
        ),
        payload={
            "schema_version": "automation-code-review/1.0",
            "gate_id": "G03",
            "decision": "skipped_by_policy",
            "reason": "automation-code human review is no longer a required checkpoint",
            "n05_artifact_hash": str(n05.get("artifact_hash", "")),
        },
        status=ArtifactStatus.SKIPPED_BY_POLICY,
        reason_code="automation_code_human_review_removed",
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="n05-automation-code-check",
                location="n05-automation-code-check.json",
                content_hash=str(n05.get("artifact_hash", "")),
            ),
        ),
    )
    target = auto_dir / "artifacts" / "g03-automation-code-review.json"
    if target.exists():
        existing = _read(target)
        if existing.get("artifact_hash") == envelope.artifact_hash:
            return None
        existing_payload = existing.get("payload", {})
        bound_n05 = ""
        if isinstance(existing_payload, Mapping):
            bound_n05 = str(existing_payload.get("n05_artifact_hash") or "")
        # Rebind when N05 changed. A leftover not_applicable from "no
        # candidates" must not keep G03 skipped for the wrong reason after
        # A14 actually generated code.
        if bound_n05 == str(n05.get("artifact_hash", "")) and str(existing.get("status") or "") in {
            ArtifactStatus.COMPLETED.value,
            ArtifactStatus.COMPLETED_WITH_GAPS.value,
            ArtifactStatus.SKIPPED_BY_POLICY.value,
            ArtifactStatus.NOT_APPLICABLE.value,
            ArtifactStatus.CANCELLED.value,
        }:
            return None
    ArtifactStore(auto_dir).write_artifact(envelope)
    return {
        "node_id": "G03",
        "action": "skipped_human_gate_removed",
        "artifact_id": envelope.artifact_id,
        "artifact_hash": envelope.artifact_hash,
    }

def _policy_path(config: dict[str, Any], key: str, repo_root: Path) -> Path | None:
    """Resolve a policy path from config, falling back to the repo policies dir."""

    configured = _config_path(config, key, repo_root)
    if configured is not None:
        return configured
    # Policy files use hyphenated names (execution-policy.json) while config
    # keys are underscore-separated (execution_policy). Try both spellings so
    # a run config that omits the key still resolves the bundled default.
    # Also accept either repo layout (repo-root/qa-agents/policies or a bare
    # qa-agents root) because tests and deployments pass different roots.
    candidates = (
        repo_root / "qa-agents" / "policies" / f"{key}.json",
        repo_root / "qa-agents" / "policies" / f"{key.replace('_', '-')}.json",
        repo_root / "policies" / f"{key}.json",
        repo_root / "policies" / f"{key.replace('_', '-')}.json",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None



C5_REQUIRED_LAYER_GENERATORS = {
    "backend": "a14-backend-automation-generation",
}


def _manifest_mapped_case_ids(auto_dir: Path, artifact_id: str) -> set[str]:
    path = auto_dir / "artifacts" / f"{artifact_id}.json"
    if not path.exists():
        return set()
    payload = _read(path).get("payload")
    if not isinstance(payload, Mapping):
        return set()
    manifest = payload.get("manifest")
    if not isinstance(manifest, Mapping):
        return set()
    return {
        str(item.get("case_id"))
        for item in manifest.get("case_mappings") or []
        if isinstance(item, Mapping) and str(item.get("case_id") or "").strip()
    }


def _c5_required_generation_complete(auto_dir: Path) -> bool:
    """Backend generate_new cases must be in the A14 manifest before C6 starts.

    ``completed_with_gaps`` used to let 1/N generated cases open N07/N08 and dump
    the rest onto N17 as manual work. Missing backend automation is a C5 failure,
    not a human-test gap. Layers without a generator in this 8-card flow (e2e)
    do not block C5.
    """

    n15_path = auto_dir / "artifacts" / "n15-execution-plan.json"
    n25_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    if not n15_path.exists() or not n25_path.exists():
        return True
    n15_payload = _read(n15_path).get("payload")
    n25_payload = _read(n25_path).get("payload")
    if not isinstance(n15_payload, Mapping) or not isinstance(n25_payload, Mapping):
        return True
    cases = n25_payload.get("compiled_cases", n25_payload.get("child_cases"))
    actions = n15_payload.get("actions")
    if not isinstance(cases, list) or not isinstance(actions, list):
        return True
    layer_by_id = {
        str(item.get("id")): str(item.get("layer") or "").strip().lower()
        for item in cases
        if isinstance(item, Mapping) and item.get("id")
    }
    generated = {
        artifact_id: _manifest_mapped_case_ids(auto_dir, artifact_id)
        for artifact_id in C5_REQUIRED_LAYER_GENERATORS.values()
    }
    for action in actions:
        if not isinstance(action, Mapping) or action.get("action") != "generate_new":
            continue
        case_id = str(action.get("case_id") or "").strip()
        if not case_id:
            continue
        artifact_id = C5_REQUIRED_LAYER_GENERATORS.get(layer_by_id.get(case_id, ""))
        if not artifact_id:
            continue
        if case_id not in generated.get(artifact_id, set()):
            return False
    return True


def _c5_terminal(auto_dir: Path) -> bool:
    """Whether every C5 node reached a terminal state (A22 confirmation included)."""

    required = [
        "a14-backend-automation-generation",
        "a15-contract-automation-generation",
        "a18-be-backend-automation-review",
        "n27-test-data-plan-validation",
        "n05-automation-code-check",
        "g03-automation-code-review",
    ]
    blocked_statuses = {
        ArtifactStatus.NEEDS_HUMAN.value,
        ArtifactStatus.BLOCKED.value,
        ArtifactStatus.BLOCKED_INPUT.value,
        ArtifactStatus.FAILED_FATAL.value,
    }
    for name in required:
        path = auto_dir / "artifacts" / f"{name}.json"
        if not path.exists():
            return False
        if _read(path).get("status") in blocked_statuses:
            return False
    a22_path = auto_dir / "artifacts" / "a22-test-data-plan.json"
    if not a22_path.exists():
        return False
    a22 = _read(a22_path)
    if a22.get("status") != ArtifactStatus.NEEDS_HUMAN.value:
        return _c5_required_generation_complete(auto_dir)
    confirmation_path = auto_dir / "artifacts" / "a22-human-confirmation.json"
    if not confirmation_path.exists():
        return False
    return _confirmation_binds(_read(confirmation_path), a22) and _c5_required_generation_complete(
        auto_dir
    )


def ensure_a22_human_confirmation(
    run_id: str,
    auto_dir: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Record a human confirmation once the A22 review Issue is set to done.

    A22 plans with unresolved data requirements are ``needs_human`` by design.
    The owner must review every unresolved requirement on the card and post a
    disposition comment (``UR-xx: confirmed/skip/return/need_evidence``). Only
    an Issue with a complete disposition comment becomes a confirmation
    Artifact; flipping the card to ``done`` alone no longer records one.
    ``skip`` and ``need_evidence`` are valid review outcomes that release the
    workflow with gaps (their requirements are recorded as deferred); only
    ``return`` keeps the gate open and routes the plan to correction. This
    mirrors the G01/G02 review gates: a status transition is not a review.
    """

    a22_path = auto_dir / "artifacts" / "a22-test-data-plan.json"
    if not a22_path.exists():
        return None
    a22 = _read(a22_path)
    if a22.get("status") != ArtifactStatus.NEEDS_HUMAN.value:
        return None
    target = auto_dir / "artifacts" / "a22-human-confirmation.json"
    if target.exists():
        existing = _read(target)
        if _confirmation_binds(existing, a22):
            return None
    issues = issues_by_node.get("A22", [])
    done_issues = [
        issue for issue in issues if str(issue.get("status", "")).strip() == "done"
    ]
    if not done_issues:
        return None
    payload = a22.get("payload", {})
    unresolved = payload.get("unresolved_requirements", [])
    dispositions = _parse_a22_dispositions(done_issues[0], unresolved)
    if dispositions is None:
        return {
            "node_id": "A22",
            "action": "review_pending",
            "issue_id": str(done_issues[0].get("id", "")),
            "issue_identifier": str(done_issues[0].get("identifier", "")),
            "reason": (
                "A22 审核卡已置 done，但缺少覆盖全部未决数据需求的逐项处置评论"
                "（格式：UR-xx: confirmed/skip/return/need_evidence），未形成确认"
            ),
        }
    if any(item["disposition"] == "return" for item in dispositions):
        return {
            "node_id": "A22",
            "action": "review_pending",
            "issue_id": str(done_issues[0].get("id", "")),
            "issue_identifier": str(done_issues[0].get("identifier", "")),
            "reason": (
                "A22 审核存在 return 处置，测试数据计划需修正后重新确认"
            ),
        }
    confirmed_ids = [
        item["requirement_id"]
        for item in dispositions
        if item["disposition"] == "confirmed"
    ]
    deferred_ids = [
        item["requirement_id"]
        for item in dispositions
        if item["disposition"] in {"skip", "need_evidence"}
    ]
    all_confirmed = len(confirmed_ids) == len(dispositions)
    decision = "confirmed" if all_confirmed else "confirmed_with_gaps"
    confirmation_status = (
        ArtifactStatus.COMPLETED
        if all_confirmed
        else ArtifactStatus.COMPLETED_WITH_GAPS
    )
    reason_code = (
        "unresolved_requirements_confirmed"
        if all_confirmed
        else "unresolved_requirements_confirmed_with_gaps"
    )
    identity = (
        str(a22.get("workflow_run_id", "")),
        str(a22.get("workflow_mode", "")),
        str(a22.get("source_snapshot_id", "")),
    )
    confirmation = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="a22-human-confirmation",
        source_snapshot_id=identity[2],
        producer=Producer(
            component_id="A22-HUMAN",
            component_version="1.0.0",
            runtime="human-confirmation",
            profile_version="1.0.0",
            model_provider="deterministic",
            model_snapshot="none",
            prompt_version="none",
            tool_bundle_version="none",
        ),
        payload={
            "schema_version": "human-confirmation/1.0",
            "gate_id": "A22",
            "decision": decision,
            "plan_artifact_id": "a22-test-data-plan",
            "plan_artifact_hash": str(a22.get("artifact_hash", "")),
            "confirmed_requirement_ids": confirmed_ids,
            "deferred_requirement_ids": deferred_ids,
            "dispositions": dispositions,
            "actor": {
                "type": "human",
                "issue_identifier": str(
                    done_issues[0].get("identifier", "")
                ),
            },
        },
        status=confirmation_status,
        reason_code=reason_code,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a22-test-data-plan",
                location="a22-test-data-plan.json",
                content_hash=str(a22.get("artifact_hash", "")),
            ),
        ),
    )
    ArtifactStore(auto_dir).write_artifact(confirmation)
    return {
        "node_id": "A22",
        "artifact_id": confirmation.artifact_id,
        "artifact_hash": confirmation.artifact_hash,
        "status": confirmation.status.value,
        "confirmed": len(confirmed_ids),
        "deferred": len(deferred_ids),
        "dispositions": dispositions,
    }


_A22_DISPOSITION_ALIASES = {
    "confirmed": "confirmed",
    "ok": "confirmed",
    "确认": "confirmed",
    "认可": "confirmed",
    "通过": "confirmed",
    "skip": "skip",
    "skipped": "skip",
    "跳过": "skip",
    "不测": "skip",
    "return": "return",
    "返回": "return",
    "需补充": "return",
    "need_evidence": "need_evidence",
    "need_env": "need_evidence",
    "待验证": "need_evidence",
    "需环境验证": "need_evidence",
    "保留": "need_evidence",
}



def _unresolved_requirement_id(item: Mapping[str, Any], index: int) -> str:
    """Resolve the review identifier for an unresolved data requirement.

    A22 plans should carry ``requirement_id`` (``UR-01``), but older or
    agent-regenerated plans sometimes only include ``requirement`` / ``reason``
    / ``case_id`` with no id-like field. Falling back to a stable 1-based
    ``UR-NN`` index keeps the review gate usable instead of permanently
    returning an empty id list that can never match a disposition comment.
    """

    raw = str(
        item.get("requirement_id")
        or item.get("reason_code")
        or item.get("id")
        or ""
    ).strip()
    if raw:
        return raw
    return f"UR-{index + 1:02d}"


def _parse_a22_dispositions(
    issue: Mapping[str, Any],
    unresolved: list[Any],
) -> list[dict[str, str]] | None:
    """Parse per-requirement dispositions from the review Issue comments.

    Every unresolved requirement must carry an explicit disposition line such
    as ``UR-01: confirmed`` or ``UR-03: 跳过``. Returns ``None`` when the
    comments are missing, empty, or do not cover every requirement so a bare
    ``done`` status can never be mistaken for a human review.
    """

    required_ids = [
        _unresolved_requirement_id(item, index)
        for index, item in enumerate(unresolved)
        if isinstance(item, Mapping)
    ]
    required_ids = [value for value in required_ids if value]
    if not required_ids:
        return None
    try:
        comments = _multica("issue", "comment", "list", str(issue.get("id", "")))
    except Exception:
        return None
    if not isinstance(comments, list):
        return None
    dispositions: dict[str, dict[str, str]] = {}
    for comment in comments:
        if not isinstance(comment, Mapping):
            continue
        content = str(comment.get("content", "") or "")
        if not content.strip():
            continue
        for requirement_id, disposition in _parse_disposition_lines(content).items():
            if requirement_id in required_ids:
                dispositions[requirement_id] = {
                    "requirement_id": requirement_id,
                    "disposition": disposition,
                }
    if set(dispositions) != set(required_ids):
        return None
    return [dispositions[requirement_id] for requirement_id in required_ids]


def _parse_disposition_lines(content: str) -> dict[str, str]:
    """Extract ``UR-xx: disposition`` lines from a review comment."""

    parsed: dict[str, str] = {}
    for line in content.splitlines():
        match = re.match(
            r"^\s*(UR-\d+)\s*[:：]?\s*([A-Za-z_\u4e00-\u9fa5]+)",
            line,
        )
        if not match:
            continue
        requirement_id, raw = match.group(1), match.group(2).lower()
        disposition = _A22_DISPOSITION_ALIASES.get(raw)
        if disposition is not None:
            parsed[requirement_id] = disposition
    return parsed


def _refresh_a22_waiting_card(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Render unresolved A22 data requirements onto the review card.

    An A22 plan with ``unresolved_requirements`` is ``needs_human`` by design.
    Before any confirmation can be recorded, the card must show every
    unresolved requirement so the owner reviews the actual questions instead of
    approving an invisible checklist.
    """

    a22_path = auto_dir / "artifacts" / "a22-test-data-plan.json"
    if not a22_path.exists():
        return None
    a22 = _read(a22_path)
    if a22.get("status") != ArtifactStatus.NEEDS_HUMAN.value:
        return None
    payload = a22.get("payload", {})
    unresolved = payload.get("unresolved_requirements", [])
    approval_items = [
        _unresolved_requirement_item(item, index)
        for index, item in enumerate(unresolved)
        if isinstance(item, Mapping)
    ]
    if not approval_items:
        return None
    issues = issues_by_node.get("A22", [])
    if not issues:
        return None
    issue = issues[-1]
    if str(issue.get("status", "")).strip() in {"done", "cancelled", "blocked"}:
        return None
    bundle_path = auto_dir.parent / "inputs" / "a22-input.json"
    description = node_issue_description(
        "A22",
        str(issue.get("label") or "A22 测试数据计划"),
        input_name=bundle_path.name,
        approval_issues=approval_items,
    )
    result = {
        "node_id": "A22",
        "action": "waiting_card_refreshed" if apply else "waiting_card_ready",
        "issue_id": str(issue.get("id", "")),
        "issue_identifier": str(issue.get("identifier", "")),
        "approval_count": len(approval_items),
    }
    if not apply:
        return result
    description_path = bundle_path.with_name(f"{bundle_path.name}.card.md")
    description_path.write_text(description, encoding="utf-8")
    _multica(
        "issue",
        "update",
        str(issue["id"]),
        "--description-file",
        description_path.name,
        "--title",
        str(issue.get("title", "")),
        "--project",
        str(config["internal_project_id"]),
        "--status",
        "in_review",
        cwd=description_path.parent,
    )
    return result


def _unresolved_requirement_item(
    item: Mapping[str, Any],
    index: int = 0,
) -> dict[str, str]:
    """Project an unresolved data requirement onto the approval card block."""

    requirement_id = _unresolved_requirement_id(item, index)
    requirement = str(item.get("requirement") or item.get("summary") or requirement_id)
    case_match = re.search(r"\bTC-[A-Z0-9-]+\b", requirement)
    return {
        "id": requirement_id,
        "title": "未决数据需求",
        "human_title": "未决数据需求",
        "summary": requirement,
        "category": "test_data_pending_human",
        "case_id": case_match.group(0) if case_match else "",
        "recommendation": str(item.get("recommendation") or ""),
        "severity": str(item.get("severity") or ""),
    }


def _ensure_n07_env_inputs(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
) -> tuple[Path, Path, bool]:
    """Resolve N07 env target/observed; synthesize minimal defaults when absent.

    A run that does not pin explicit environment fingerprints still gets a
    deterministic minimal target/observation derived from its own data (the
    A22 plan environment class and test namespace), so C6 can start without a
    manual environment-input handoff. Explicit ``n07_target``/``n07_observed``
    in the workflow config always win; synthesized files are written once and
    reused by later passes.
    """

    env_target = _config_path(config, "n07_target", repo_root)
    env_observed = _config_path(config, "n07_observed", repo_root)
    if env_target is None:
        env_target = inputs_dir / "env-target.json"
    if env_observed is None:
        env_observed = inputs_dir / "env-observed.json"
    if env_target.exists() and env_observed.exists():
        return env_target, env_observed, False
    environment = "test"
    namespace = f"qa-{run_id}"
    a22_path = auto_dir / "artifacts" / "a22-test-data-plan.json"
    if a22_path.exists():
        try:
            a22_payload = _read(a22_path).get("payload", {})
        except (OSError, json.JSONDecodeError):
            a22_payload = {}
        if isinstance(a22_payload, Mapping):
            environment = str(a22_payload.get("environment") or environment)
            namespace = str(a22_payload.get("namespace") or namespace)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    target_payload = {
        "schema_version": "environment-target/1.0",
        "environment_class": environment,
        "production_isolation": False,
        "expected": {
            "deployment_commits": [],
            "dependencies": [],
            "test_accounts": [],
            "feature_flags": [],
            "tenant_configs": [],
            "test_data_requirements": [],
            "runtime": {"timezone": "Asia/Shanghai", "language": "zh-CN"},
            "namespace_policy": {"prefix": "qa-", "cleanup": {"required": True}},
            "required_locks": [],
        },
    }
    observed_payload = {
        "schema_version": "environment-observation/1.0",
        "environment": environment,
        "requester_id": f"qa-sync-{run_id}",
        "deployment_commits": [],
        "dependencies": [],
        "test_accounts": [],
        "feature_flags": [],
        "tenant_configs": [],
        "test_data": [],
        "runtime": {"timezone": "Asia/Shanghai", "language": "zh-CN"},
        "test_namespaces": [
            {"namespace": namespace, "cleanup_policy": {"required": True}}
        ],
        "resource_locks": [],
    }
    env_target.write_text(
        json.dumps(target_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    env_observed.write_text(
        json.dumps(observed_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return env_target, env_observed, True


def ensure_n07_precheck(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    inputs_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Auto-run the deterministic N07 environment precheck once C5 is terminal."""

    if not _c5_terminal(auto_dir):
        return None
    target_path = auto_dir / "artifacts" / "n07-environment-precheck.json"
    n27_path = auto_dir / "artifacts" / "n27-test-data-plan-validation.json"
    if target_path.exists() and n27_path.exists():
        existing = _read(target_path)
        current_n27_hash = str(_read(n27_path).get("artifact_hash") or "")
        bound_n27_hash = next(
            (
                str(item.get("content_hash") or "")
                for item in existing.get("evidence_refs", [])
                if isinstance(item, Mapping)
                and item.get("source_id") == "n27-test-data-plan-validation"
            ),
            "",
        )
        if current_n27_hash and bound_n27_hash == current_n27_hash:
            return None
    a14_path = auto_dir / "artifacts" / "a14-backend-automation-generation.json"
    if not a14_path.exists():
        return None
    env_target, env_observed, synthesized = _ensure_n07_env_inputs(
        config, run_id, auto_dir, inputs_dir, repo_root
    )
    identity = _read(a14_path)
    artifact = run_n07_env_precheck(
        env_target,
        env_observed,
        auto_dir,
        workflow_run_id=str(identity.get("workflow_run_id", "")),
        source_snapshot_id=str(identity.get("source_snapshot_id", "")),
        workflow_mode=str(identity.get("workflow_mode", "new_requirement")),
        test_data_validation_path=n27_path if n27_path.exists() else None,
    )
    result = {
        "node_id": "N07",
        "artifact_id": str(artifact.get("artifact_id", "")),
        "artifact_hash": str(artifact.get("artifact_hash", "")),
        "status": str(artifact.get("status", "")),
        "decision": str(artifact.get("payload", {}).get("decision", "")),
    }
    if synthesized:
        result["env_input_synthesized"] = True
        result["target"] = str(env_target)
        result["observed"] = str(env_observed)
    return result


def ensure_n08_execution(
    config: dict[str, Any],
    auto_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Auto-run N08 controlled execution after a passed N07 precheck."""

    precheck_path = auto_dir / "artifacts" / "n07-environment-precheck.json"
    if not precheck_path.exists():
        return None
    precheck = _read(precheck_path)
    precheck_payload = precheck.get("payload", {})
    if not isinstance(precheck_payload, Mapping):
        return None
    if (
        precheck.get("status") not in {ArtifactStatus.COMPLETED.value, ArtifactStatus.COMPLETED_WITH_GAPS.value}
        or precheck_payload.get("decision") not in {"passed", "passed_with_warnings"}
        or precheck_payload.get("next_node") != "N08"
    ):
        return None
    target = auto_dir / "artifacts" / "n08-automation-execution.json"
    generation_path = auto_dir / "artifacts" / "a14-backend-automation-generation.json"
    review_path = auto_dir / "artifacts" / "a18-be-backend-automation-review.json"
    code_check_path = auto_dir / "artifacts" / "n05-automation-code-check.json"
    automation_policy = _policy_path(config, "automation_target_policy", repo_root)
    execution_policy = _policy_path(config, "execution_policy", repo_root)
    if (
        not all(path.exists() for path in (generation_path, review_path, code_check_path))
        or automation_policy is None
        or execution_policy is None
    ):
        return None
    if target.exists():
        existing_bindings = _read(target).get("payload", {}).get("input_bindings", {})
        current_bindings = {
            "generation_hash": str(_read(generation_path).get("artifact_hash") or ""),
            "review_hash": str(_read(review_path).get("artifact_hash") or ""),
            "code_check_hash": str(_read(code_check_path).get("artifact_hash") or ""),
            "environment_precheck_hash": str(precheck.get("artifact_hash") or ""),
        }
        if isinstance(existing_bindings, Mapping) and all(
            existing_bindings.get(key) == value
            for key, value in current_bindings.items()
        ):
            return None
    artifact = run_n08_automation(
        generation_path,
        review_path,
        code_check_path,
        precheck_path,
        automation_policy,
        execution_policy,
        auto_dir,
        bug_finder_root=(
            _config_path(config, "a22_bug_finder_root", repo_root)
            if config.get("a22_bug_finder_integrity_enabled", True)
            else None
        ),
    )
    return {
        "node_id": "N08",
        "artifact_id": str(artifact.get("artifact_id", "")),
        "artifact_hash": str(artifact.get("artifact_hash", "")),
        "status": str(artifact.get("status", "")),
        "decision": str(artifact.get("payload", {}).get("decision", "")),
    }


def ensure_quality_tail(
    config: dict[str, Any],
    auto_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Auto-run the C7/C8 quality tail after N08 execution evidence exists."""

    n08_path = auto_dir / "artifacts" / "n08-automation-execution.json"
    if not n08_path.exists():
        return None
    n17_path = auto_dir / "artifacts" / "n17-manual-execution.json"
    n17_unfinished = False
    n17_status = ArtifactStatus.BLOCKED.value
    if n17_path.exists():
        n17 = _read(n17_path)
        n17_status = str(n17.get("status") or ArtifactStatus.BLOCKED.value)
        if n17_status in {
            ArtifactStatus.NEEDS_HUMAN.value,
            ArtifactStatus.BLOCKED.value,
        }:
            n17_unfinished = True
            remove_quality_tail_after_n17(auto_dir)
    plan_path = auto_dir / "artifacts" / "n15-execution-plan.json"
    compiled_path = auto_dir / "artifacts" / "n25-compiled-test-cases.json"
    precheck_path = auto_dir / "artifacts" / "n07-environment-precheck.json"
    quality_policy = _policy_path(config, "quality_policy", repo_root)
    n18_path = auto_dir / "artifacts" / "n18-quality-signals.json"
    if (
        n18_path.exists()
        and not n17_unfinished
        and quality_policy is not None
        and not quality_tail_needs_refresh(auto_dir, quality_policy, n08_path)
    ):
        return None
    if (
        not all(path.exists() for path in (plan_path, compiled_path, precheck_path))
        or quality_policy is None
    ):
        if n17_unfinished:
            return {
                "node_id": "QUALITY_TAIL",
                "status": n17_status,
                "current_node": "N17",
                "next_node": "N17",
            }
        return None
    result = run_server_quality_tail(
        plan_path,
        compiled_path,
        precheck_path,
        auto_dir,
        test_data_validation_path=auto_dir / "artifacts" / "n27-test-data-plan-validation.json",
        automation_execution_paths=[n08_path],
        quality_policy_path=quality_policy,
    )
    return {
        "node_id": "QUALITY_TAIL",
        "status": str(result.get("decision") or result.get("status") or ""),
        "current_node": str(result.get("current_node", "")),
        "next_node": str(result.get("current_node", "")),
    }


_RECORD_ISSUE_STATUS = {
    "completed": "done",
    "completed_with_gaps": "done",
    "needs_human": "in_review",
    "blocked": "blocked",
    "blocked_input": "blocked",
    "not_applicable": "done",
    "skipped_by_policy": "done",
    "stale": "done",
    "inconclusive": "in_review",
    "failed_retryable": "in_review",
    "failed_fatal": "blocked",
    "cancelled": "cancelled",
}


def _retry_approval_block(
    artifact: Mapping[str, Any],
    retry_budget: Mapping[str, Any] | None,
) -> list[str] | None:
    """Build the human-decision block for a retryable-failure record card.

    A ``failed_retryable`` deterministic node (N08 execution or N10 retry
    budget) flips its record Issue to ``in_review``. The card must show what
    failed and what the retry budget allows, otherwise the user sees an empty
    "审核中" card with nothing to approve.
    """

    if str(artifact.get("status", "")) != ArtifactStatus.FAILED_RETRYABLE.value:
        return None
    payload = artifact.get("payload", {})
    if not isinstance(payload, Mapping):
        payload = {}
    artifact_id = str(artifact.get("artifact_id", ""))
    lines = [
        "本节点执行判定为可重试失败（`failed_retryable`），需要你决定是否批准重试。",
        "",
        "### 失败摘要",
        f"- 失败原因：`{artifact.get('reason_code') or '未说明'}`",
    ]
    if payload.get("decision"):
        lines.append(f"- 执行决策：`{payload['decision']}`")
    summary = payload.get("summary")
    if isinstance(summary, Mapping) and summary:
        lines.append(
            "- 执行摘要：" + "、".join(f"`{key}={value}`" for key, value in summary.items())
        )
    budget = retry_budget
    if budget is None and artifact_id == "n10-retry-budget":
        budget = artifact
    lines.extend(["", "### 重试预算"])
    if budget is None:
        lines.append("- 未生成重试预算 Artifact，无法自动重试。")
    else:
        budget_payload = budget.get("payload", {})
        if not isinstance(budget_payload, Mapping):
            budget_payload = {}
        lines.append(f"- 判定：`{budget_payload.get('decision') or budget.get('status')}`")
        if budget_payload.get("max_attempts") is not None:
            lines.append(f"- 允许重试：`{budget_payload['max_attempts']}` 次（当前 attempt=`{budget_payload.get('attempt', 0)}`）")
        if budget_payload.get("next_node"):
            lines.append(f"- 重试起点：从 `{budget_payload['next_node']}` 重新执行")
    lines.extend(
        [
            "",
            "### 决策动作",
            "- 置 **done**：批准重试，系统按上述预算从重试起点重新执行。",
            "- 置 **cancelled**：拒绝重试，终止当前执行路径。",
            "- 置 **blocked**：暂不处理，保持等待。",
        ]
    )
    return lines


def _ensure_node_record_issue(
    config: dict[str, Any],
    run_id: str,
    node_id: str,
    label: str,
    artifact_path: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> dict[str, Any] | None:
    """Create (idempotently) one record Issue for a deterministic node.

    The record Issue mirrors the deterministic Artifact state (例如 N27 从
    blocked 变为 completed_with_gaps 后，Issue 也必须同步为 done)，保证子任务
    状态回显与真实状态一致。
    """

    artifact = _read(artifact_path)
    expected_status = _RECORD_ISSUE_STATUS.get(str(artifact.get("status", "")), "done")
    retry_budget = None
    if str(artifact.get("artifact_id", "")) == "n08-automation-execution":
        budget_path = artifact_path.parent / "n10-retry-budget.json"
        if budget_path.exists():
            try:
                retry_budget = _read(budget_path)
            except (OSError, json.JSONDecodeError):
                retry_budget = None
    approval_block = _retry_approval_block(artifact, retry_budget)
    constructed_assets = []
    if node_id == "N08":
        constructed_assets = discover_constructed_assets(
            artifact_path.parent,
            artifact_path.parent.parent,
        )
    quality_results = []
    quality_summary = ""
    standard_quality_report = ""
    if node_id == "N11":
        payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
        quality_results = list(payload.get("case_outcomes") or [])
        quality_summary = str(payload.get("summary") or "").strip()
    if node_id == "N12":
        from qa_agents.quality_report import render_standard_quality_report

        n11_path = artifact_path.with_name("n11-quality-decision.json")
        n11_payload: Mapping[str, Any] = {}
        if n11_path.exists():
            n11_artifact = _read(n11_path)
            candidate = n11_artifact.get("payload")
            if isinstance(candidate, Mapping):
                n11_payload = candidate
        standard_quality_report = render_standard_quality_report(
            artifact,
            case_outcomes=list(n11_payload.get("case_outcomes") or []),
            quality_summary=str(n11_payload.get("summary") or "").strip(),
            constructed_assets=discover_constructed_assets(
                artifact_path.parent,
                artifact_path.parent.parent,
                artifact_path.parent.parent.parent / "current",
            ),
        )
    description = node_record_description(
        node_id,
        label,
        artifact_name=artifact_path.name,
        approval_block=approval_block,
        constructed_assets=constructed_assets,
        quality_results=quality_results,
        quality_summary=quality_summary,
        standard_quality_report=standard_quality_report,
    )
    existing = next(
        (issue for issue in issues_by_node.get(node_id, []) if issue.get("id")),
        None,
    )
    if existing is not None:
        live_status = str(existing.get("status", "")).strip()
        if not apply:
            return None
        expected_title = node_issue_title(run_id, node_id, label)
        live_title = str(existing.get("title", "")).strip()
        title_stale = bool(live_title) and live_title != expected_title
        refresh_description = (
            approval_block is not None
            or bool(constructed_assets)
            or bool(quality_results)
            or bool(standard_quality_report)
            or title_stale
        )
        if live_status == expected_status and not refresh_description:
            return None
        if refresh_description:
            description_path = artifact_path.with_name(f"{artifact_path.name}.record.md")
            description_path.write_text(description, encoding="utf-8")
            try:
                _multica(
                    "issue", "update",
                    str(existing["id"]),
                    "--description-file", description_path.name,
                    "--title", node_issue_title(run_id, node_id, label),
                    "--project", str(config["internal_project_id"]),
                    "--status", expected_status,
                    cwd=description_path.parent,
                )
            except Exception as error:
                raise RuntimeError(f"multica could not sync the {node_id} record Issue") from error
        else:
            try:
                _multica("issue", "status", str(existing["id"]), expected_status)
            except Exception as error:
                raise RuntimeError(f"multica could not sync the {node_id} record Issue status") from error
        return {
            "node_id": node_id,
            "label": label,
            "action": "synced",
            "issue_id": str(existing["id"]),
            "issue_identifier": str(existing.get("identifier", "")),
            "artifact": str(artifact_path),
            "status": expected_status,
            "approval_rendered": approval_block is not None,
        }
    if not apply:
        return {
            "node_id": node_id,
            "label": label,
            "action": "would_create",
            "artifact": str(artifact_path),
        }
    description_path = artifact_path.with_name(f"{artifact_path.name}.record.md")
    description_path.write_text(description, encoding="utf-8")
    command = [
        "issue",
        "create",
        "--title", node_issue_title(run_id, node_id, label),
        "--description-file", description_path.name,
        "--project", str(config["internal_project_id"]),
        "--workspace-id", str(config["workspace_id"]),
        "--status", _RECORD_ISSUE_STATUS.get(
            str(artifact.get("status", "")), "done"
        ),
        "--priority", "medium",
        "--attachment", str(artifact_path.resolve()),
    ]
    created = _multica(*command, cwd=description_path.parent)
    if not isinstance(created, dict) or not created.get("id"):
        raise RuntimeError(f"multica did not create the {node_id} record Issue")
    return {
        "node_id": node_id,
        "label": label,
        "action": "created",
        "issue_id": str(created["id"]),
        "issue_identifier": str(created.get("identifier", "")),
        "artifact": str(artifact_path),
        "status": expected_status,
        "approval_rendered": approval_block is not None,
    }


def ensure_node_record_issues(
    config: dict[str, Any],
    run_id: str,
    auto_dir: Path,
    issues_by_node: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
) -> list[dict[str, Any]]:
    """Create record Issues for deterministic nodes with accepted Artifacts.

    Deterministic nodes run locally and have no Agent Issue, so the stage-card
    detail page cannot link them. A lightweight record Issue (auto-created,
    Artifact attached, status synced) gives every subtask a clickable entry and
    archives the evidence; Agent nodes already carry their own Issues.
    """

    agent_nodes = {
        str(node_id) for node_id in (config.get("node_agents") or {}).keys()
    }
    gate_nodes = {"G01", "G02", "G03"}
    created: list[dict[str, Any]] = []
    for path in sorted((auto_dir / "artifacts").glob("*.json")):
        try:
            artifact = _read(path)
        except (OSError, json.JSONDecodeError):
            continue
        if str(artifact.get("schema_version", "")) != "artifact-envelope/1.0":
            continue
        node_id = ARTIFACT_NODE_MAP.get(str(artifact.get("artifact_id", "")))
        if not node_id or node_id in agent_nodes or node_id in gate_nodes:
            continue
        label = _NODE_LABELS.get(node_id, node_id)
        record = _ensure_node_record_issue(
            config,
            run_id,
            node_id,
            label,
            path,
            issues_by_node,
            apply=apply,
        )
        if record:
            created.append(record)
            issues_by_node.setdefault(node_id, []).append(
                {
                    "id": str(record.get("issue_id", "")),
                    "identifier": str(record.get("issue_identifier", "")),
                    "title": f"[{run_id}] {node_id} {label}",
                    "status": str(record.get("status", "done")),
                }
            )
    return created


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--sync-output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dispatch-authorization", type=Path)
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
    _load_dispatch_authorization(getattr(args, "dispatch_authorization", None), run_id)
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
        ingest_action = _completed_run_ingest_action(
            auto_dir=auto_dir,
            bundle_path=bundle_path,
            run_id=node_run_id,
            ingest_failures=ingest_failures,
            node_id=node_id,
            issue_id=str(issue["id"]),
        )
        if ingest_action == "keep_blocked":
            if args.apply:
                try:
                    _mark_issue_blocked(issue)
                except Exception as error:
                    errors.append(
                        {"node_id": node_id, "error": f"ingest-failed status: {error}"}
                    )
            continue
        if ingest_action == "mark_done":
            if args.apply:
                try:
                    _multica("issue", "status", str(issue["id"]), "done")
                    issue["status"] = "done"
                    _cancel_duplicate_node_issues(
                        issues,
                        prefix,
                        node_id,
                        keep_issue_id=str(issue["id"]),
                    )
                except Exception as error:
                    errors.append(
                        {"node_id": node_id, "error": f"status sync: {error}"}
                    )
            else:
                issue["status"] = "done"
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
                    _cancel_duplicate_node_issues(
                        issues,
                        prefix,
                        node_id,
                        keep_issue_id=str(issue["id"]),
                    )
        except Exception as error:  # keep other nodes progressing
            errors.append({"node_id": node_id, "error": str(error)})
            _record_ingest_failure(
                ingest_failures, node_id, str(issue["id"]), node_run_id, bundle_path
            )
            if args.apply:
                try:
                    _mark_issue_blocked(issue)
                except Exception as status_error:
                    errors.append(
                        {"node_id": node_id, "error": f"ingest-failed status: {status_error}"}
                    )
    _save_ingest_failures(artifact_root, ingest_failures)

    refreshed_node_cards = _refresh_waiting_node_cards(
        config=config,
        auto_dir=auto_dir,
        node_entries=node_entries,
        run_id=run_id,
        apply=args.apply,
    )

    g01_result = None
    g01_transition = None
    g01_published = None
    n24_result = None
    g01_policy = config.get("g01_policy")
    if g01_policy:
        policy_path = Path(str(g01_policy))
        if not policy_path.is_absolute():
            policy_path = repo_root / policy_path
        # G01 must be synced before N24/A08 in the same pass. Previously N24 ran
        # first, so a freshly approved C2 could not unlock C3 until the next
        # watch tick — and a dead watch left C3 stuck forever.
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
        try:
            n24_result = ensure_n24_test_strategy(
                config, auto_dir, artifact_root / "g01-auto", repo_root
            )
        except Exception as error:
            errors.append({"node_id": "N24", "error": str(error)})

    issues_by_node = _node_issues_by_id(issues, run_id)
    a06_result = None
    try:
        a06_result = ensure_a06_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
            ingest_failures=ingest_failures,
        )
    except Exception as error:
        errors.append({"node_id": "A06", "error": str(error)})
    if a06_result and a06_result.get("action") == "dispatched":
        issues_by_node.setdefault("A06", []).append(
            {
                "id": a06_result["issue_id"],
                "identifier": a06_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A06 需求与变更对齐",
                "status": "todo",
            }
        )
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
        c3 = next(
            (
                card
                for card in spec.get("stage_cards", [])
                if isinstance(card, dict) and card.get("stage_card_id") == "C3"
            ),
            None,
        )
        g02_result = ensure_g02_review(
            config,
            auto_dir,
            artifact_root / "g02-auto",
            repo_root,
            apply=args.apply,
            issue_id=(str(c3.get("issue_id") or "") or None) if c3 else None,
        )
    except Exception as error:
        errors.append({"node_id": "G02", "error": str(error)})
    g02_correction_result = None
    try:
        g02_correction_result = ensure_g02_correction_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "g02-auto",
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "G02", "error": f"correction: {error}"})

    n25_result = None
    a11_result = None
    n26_result = None
    n15_result = None
    node_records: list[dict[str, Any]] = []
    try:
        n25_result = ensure_n25_compilation(auto_dir, artifact_root / "g02-auto")
    except Exception as error:
        errors.append({"node_id": "N25", "error": str(error)})
    try:
        a11_result = ensure_a11_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A11", "error": str(error)})
    if a11_result and a11_result.get("action") == "dispatched":
        issues_by_node.setdefault("A11", []).append(
            {
                "id": a11_result["issue_id"],
                "identifier": a11_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A11 拆分覆盖审查",
                "status": "todo",
            }
        )
    try:
        n26_result = ensure_n26_selection(
            config, auto_dir, artifact_root / "inputs", repo_root
        )
    except Exception as error:
        errors.append({"node_id": "N26", "error": str(error)})
    try:
        n15_result = ensure_n15_execution_plan(auto_dir)
    except Exception as error:
        errors.append({"node_id": "N15", "error": str(error)})
    a14_result = None
    a15_result = None
    a22_result = None
    a18_be_result = None
    a18_ct_result = None
    n27_result = None
    n05_result = None
    g03_result = None
    a22_correction_result = None
    try:
        a14_result = ensure_a14_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A14", "error": str(error)})
    if a14_result and a14_result.get("action") == "dispatched":
        issues_by_node.setdefault("A14", []).append(
            {
                "id": a14_result["issue_id"],
                "identifier": a14_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A14 服务端自动化生成",
                "status": "todo",
            }
        )
    try:
        a15_result = ensure_a15_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A15", "error": str(error)})
    if a15_result and a15_result.get("action") == "dispatched":
        issues_by_node.setdefault("A15", []).append(
            {
                "id": a15_result["issue_id"],
                "identifier": a15_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A15 契约自动化生成",
                "status": "todo",
            }
        )
    try:
        a22_result = ensure_a22_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A22", "error": str(error)})
    if a22_result and a22_result.get("action") == "dispatched":
        issues_by_node.setdefault("A22", []).append(
            {
                "id": a22_result["issue_id"],
                "identifier": a22_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A22 测试数据规划",
                "status": "todo",
            }
        )
    try:
        a18_be_result = ensure_a18_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            reviewer="A18-BE",
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A18-BE", "error": str(error)})
    if a18_be_result and a18_be_result.get("action") == "dispatched":
        issues_by_node.setdefault("A18-BE", []).append(
            {
                "id": a18_be_result["issue_id"],
                "identifier": a18_be_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A18-BE 服务端自动化独立复核",
                "status": "todo",
            }
        )
    try:
        a18_be_code_review = ensure_a18_be_deterministic_review(
            auto_dir, issues_by_node, apply=args.apply
        )
    except Exception as error:
        errors.append({"node_id": "A18-BE", "error": f"deterministic review: {error}"})
        a18_be_code_review = None
    try:
        a18_ct_result = ensure_a18_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            reviewer="A18-CT",
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A18-CT", "error": str(error)})
    if a18_ct_result and a18_ct_result.get("action") == "dispatched":
        issues_by_node.setdefault("A18-CT", []).append(
            {
                "id": a18_ct_result["issue_id"],
                "identifier": a18_ct_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A18-CT 契约自动化独立复核",
                "status": "todo",
            }
        )
    try:
        n27_result = ensure_n27_validation(config, auto_dir, repo_root)
    except Exception as error:
        errors.append({"node_id": "N27", "error": str(error)})
    try:
        a22_correction_result = ensure_a22_correction_dispatch(
            config,
            run_id,
            auto_dir,
            artifact_root / "inputs",
            repo_root,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A22", "error": f"correction: {error}"})
    if a22_correction_result and a22_correction_result.get("action") == "dispatched":
        issues_by_node.setdefault("A22", []).append(
            {
                "id": a22_correction_result["issue_id"],
                "identifier": a22_correction_result.get("issue_identifier", ""),
                "title": f"[{run_id}] A22 测试数据规划修正",
                "status": "todo",
            }
        )
    try:
        n05_result = ensure_n05_aggregation(config, auto_dir, repo_root)
    except Exception as error:
        errors.append({"node_id": "N05", "error": str(error)})
    try:
        g03_result = ensure_g03_review(
            config, auto_dir, artifact_root / "g03-auto", repo_root, apply=args.apply
        )
    except Exception as error:
        errors.append({"node_id": "G03", "error": str(error)})
    a22_confirmation_result = None
    n07_result = None
    n08_result = None
    quality_tail_result = None
    try:
        a22_waiting_card_result = _refresh_a22_waiting_card(
            config,
            run_id,
            auto_dir,
            issues_by_node,
            apply=args.apply,
        )
    except Exception as error:
        errors.append({"node_id": "A22", "error": f"waiting card: {error}"})
    try:
        a22_confirmation_result = ensure_a22_human_confirmation(
            run_id, auto_dir, issues_by_node
        )
    except Exception as error:
        errors.append({"node_id": "A22", "error": f"human confirmation: {error}"})
    try:
        n07_result = ensure_n07_precheck(
            config, run_id, auto_dir, artifact_root / "inputs", repo_root
        )
    except Exception as error:
        errors.append({"node_id": "N07", "error": str(error)})
    try:
        n08_result = ensure_n08_execution(config, auto_dir, repo_root)
    except Exception as error:
        errors.append({"node_id": "N08", "error": str(error)})
    try:
        env_observed = _config_path(config, "n07_observed", repo_root)
        if env_observed is None:
            env_observed = artifact_root / "inputs" / "env-observed.json"
        n08_artifact_path = auto_dir / "artifacts" / "n08-automation-execution.json"
        registered = (
            record_constructed_test_data(
                auto_dir / "artifacts" / "a22-test-data-plan.json",
                n08_artifact_path,
                auto_dir,
                env_observed,
            )
            if n08_artifact_path.is_file()
            else {"registered": [], "inventory_count": 0, "skipped": "n08_not_available"}
        )
        inventory_src = auto_dir / "artifacts" / INVENTORY_FILENAME
        if inventory_src.exists():
            current_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(inventory_src, current_dir / INVENTORY_FILENAME)
        if registered.get("registered"):
            result_marker = {
                "registered_resources": len(registered["registered"]),
                "namespace": registered.get("namespace", ""),
            }
            if n08_result and isinstance(n08_result, dict):
                n08_result["constructed_test_data"] = result_marker
            else:
                n08_result = {"node_id": "N08", "constructed_test_data": result_marker}
    except Exception as error:
        errors.append({"node_id": "N08", "error": f"test-data registration: {error}"})
    try:
        quality_tail_result = ensure_quality_tail(config, auto_dir, repo_root)
    except Exception as error:
        errors.append({"node_id": "QUALITY_TAIL", "error": str(error)})
    try:
        node_records = ensure_node_record_issues(
            config, run_id, auto_dir, issues_by_node, apply=args.apply
        )
    except Exception as error:
        errors.append({"node_id": "RECORD", "error": str(error)})

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
        "refreshed_node_cards": refreshed_node_cards,
        "errors": errors,
        "a06": a06_result,
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
        "g02_correction": g02_correction_result,
        "n25": n25_result,
        "a11": a11_result,
        "n26": n26_result,
        "n15": n15_result,
        "a14": a14_result,
        "a15": a15_result,
        "a22": a22_result,
        "a18_be": a18_be_result,
        "a18_ct": a18_ct_result,
        "n27": n27_result,
        "a22_correction": a22_correction_result,
        "n05": n05_result,
        "g03": g03_result,
        "a22_confirmation": a22_confirmation_result,
        "n07": n07_result,
        "n08": n08_result,
        "quality_tail": quality_tail_result,
        "node_records": node_records,
        "reconciled": reconciled,
        "sync": sync_result,
    }
    result["dispatch_supervision"] = _dispatch_supervision(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    lock_path = args.artifact_root / ".sync-eight-card.lock"
    if not args.watch:
        try:
            with _sync_run_lock(lock_path):
                return _run_sync_once(args)
        except OSError as error:
            if "sync pass already running" not in str(error):
                # Real failures (for example the multica CLI missing) must not
                # be masked as a benign lock skip: report them loudly.
                print(json.dumps({"fatal": str(error)}, ensure_ascii=False))
                return 2
            print(
                json.dumps(
                    {
                        "skipped": "another sync pass is already running",
                        "lock_holder": str(error),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
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
            with _sync_run_lock(lock_path):
                code = _run_sync_once(args)
        except OSError as error:
            if "sync pass already running" not in str(error):
                print(json.dumps({"fatal": str(error)}, ensure_ascii=False))
                continue
            print(
                json.dumps(
                    {
                        "skipped": "another sync pass is running",
                        "lock_holder": str(error),
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as error:
            code = 2
            print(json.dumps({"fatal": str(error)}, ensure_ascii=False))
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
