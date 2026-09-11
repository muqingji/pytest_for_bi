"""Registry-driven monitor for active eight-card workflows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from concurrent.futures import Future, ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from .contracts import content_hash
from .errors import ContractError
from .workflow_center import NODE_DIRECT_DEPENDENCIES


REGISTRY_SCHEMA = "active-workflow-registry/1.0"
AUDIT_SCHEMA = "workflow-monitor-audit/1.0"
ACTIVE_STATUSES = frozenset({"active", "running", "needs_action"})
TERMINAL_SYNC_STATUSES = frozenset({"completed", "cancelled"})
Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Invalid JSON file: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"JSON file must contain an object: {path}")
    return value


def _hashed(value: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    result = {key: item for key, item in value.items() if key != hash_field}
    result[hash_field] = content_hash(result)
    return result


def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        temporary = Path(handle.name)
    temporary.replace(path)


@contextmanager
def _try_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def empty_registry() -> dict[str, Any]:
    return _hashed(
        {
            "schema_version": REGISTRY_SCHEMA,
            "revision": 0,
            "updated_at": _now(),
            "workflows": {},
        },
        "registry_hash",
    )


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_registry()
    registry = _read(path)
    if registry.get("schema_version") != REGISTRY_SCHEMA:
        raise ContractError("Active workflow registry schema_version is invalid")
    expected = _hashed(registry, "registry_hash")["registry_hash"]
    if registry.get("registry_hash") != expected:
        raise ContractError("Active workflow registry hash is invalid")
    if not isinstance(registry.get("workflows"), dict):
        raise ContractError("Active workflow registry workflows must be an object")
    return registry


def _resolve_inside(path_value: str, repo_root: Path, label: str) -> Path:
    path = Path(path_value)
    resolved = (path if path.is_absolute() else repo_root / path).resolve()
    root = repo_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ContractError(f"{label} must stay inside repository root")
    return resolved


def validate_workflow_registration(
    config_path: Path, artifact_root: Path, spec_path: Path, repo_root: Path
) -> dict[str, Any]:
    config_path = config_path.resolve()
    artifact_root = artifact_root.resolve()
    spec_path = spec_path.resolve()
    for path, label in (
        (config_path, "config"),
        (artifact_root, "artifact root"),
        (spec_path, "workflow spec"),
    ):
        root = repo_root.resolve()
        if path != root and root not in path.parents:
            raise ContractError(f"Workflow {label} must stay inside repository root")
    config = _read(config_path)
    spec = _read(spec_path)
    run_id = str(spec.get("workflow_run_id", "")).strip()
    workflow_id = str(spec.get("workflow_id", "")).strip()
    if not run_id or not workflow_id:
        raise ContractError("Workflow spec requires workflow_id and workflow_run_id")
    request_path = artifact_root / "autopilot-request.json"
    if request_path.exists():
        request = _read(request_path)
        request_run = str(request.get("workflow_run_id", "")).strip()
        if request_run and request_run != run_id:
            raise ContractError("Autopilot request belongs to another workflow run")
    if config.get("g01_policy") and not config.get("g01_adapter_policy"):
        raise ContractError("G01 adapter policy is required")
    for gate in ("g01", "g02", "g03"):
        adapter_value = config.get(f"{gate}_adapter_policy")
        if adapter_value:
            adapter_path = _resolve_inside(str(adapter_value), repo_root, f"{gate.upper()} adapter")
            adapter = _read(adapter_path)
            if adapter.get("gate_id") != gate.upper():
                raise ContractError(f"{gate.upper()} adapter gate_id is invalid")
    for gate in ("g01", "g02", "g03"):
        policy_value = config.get(f"{gate}_policy")
        if not policy_value:
            continue
        policy_path = _resolve_inside(str(policy_value), repo_root, f"{gate.upper()} policy")
        policy = _read(policy_path)
        schema_gate = str(policy.get("schema_version", "")).split("-", 1)[0]
        if policy.get("gate_id", schema_gate.upper()) != gate.upper():
            raise ContractError(f"{gate.upper()} policy gate_id is invalid")
        if gate != "g01" and policy.get("require_human_actor") is True:
            actors = policy.get("allowed_actor_ids")
            members = policy.get("allowed_multica_member_ids")
            if not isinstance(actors, list) or not actors or not isinstance(members, list) or not members:
                raise ContractError(f"{gate.upper()} human policy requires authorized actors and members")
        multica = policy.get("multica")
        if gate in {"g01", "g02"} and isinstance(multica, Mapping):
            if multica.get("workspace_id") != config.get("workspace_id"):
                raise ContractError(f"{gate.upper()} policy workspace does not match workflow")
    if config.get("g01_adapter_policy"):
        adapter = _read(_resolve_inside(str(config["g01_adapter_policy"]), repo_root, "G01 adapter"))
        policy = _read(_resolve_inside(str(config["g01_policy"]), repo_root, "G01 policy"))
        if adapter.get("gate_policy_hash") != str(policy.get("policy_hash") or content_hash(policy)):
            raise ContractError("G01 adapter is not bound to the configured policy")
        adapter_members = set(map(str, adapter.get("allowed_multica_member_ids", [])))
        policy_members = set(map(str, policy.get("allowed_multica_member_ids", [])))
        if not adapter_members or (policy_members and adapter_members != policy_members):
            raise ContractError("G01 adapter authorized members do not match policy")
    stage_cards = spec.get("stage_cards")
    if not isinstance(stage_cards, list):
        raise ContractError("Workflow spec stage_cards must be a list")
    card_ids = [str(item.get("stage_card_id", "")) for item in stage_cards if isinstance(item, dict)]
    if sorted(card_ids) != [f"C{index}" for index in range(1, 9)]:
        raise ContractError("Workflow spec must bind exactly C1-C8")
    if not isinstance(config.get("node_agents"), dict) or not config["node_agents"]:
        raise ContractError("Workflow config requires node_agents")
    return {
        "workflow_id": workflow_id,
        "workflow_run_id": run_id,
        "config_path": str(config_path),
        "artifact_root": str(artifact_root),
        "spec_path": str(spec_path),
        "sync_output": str((artifact_root / "sync-auto").resolve()),
    }


def register_workflow(
    registry_path: Path,
    config_path: Path,
    artifact_root: Path,
    spec_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    validated = validate_workflow_registration(config_path, artifact_root, spec_path, repo_root)
    lock_path = registry_path.with_suffix(registry_path.suffix + ".lock")
    with _try_lock(lock_path) as acquired:
        if not acquired:
            raise ContractError("Active workflow registry is busy")
        registry = load_registry(registry_path)
        workflows = dict(registry["workflows"])
        run_id = validated["workflow_run_id"]
        existing = workflows.get(run_id, {})
        workflows[run_id] = {
            **existing,
            **validated,
            "status": str(existing.get("status", "active")),
            "registered_at": str(existing.get("registered_at", _now())),
            "last_attempt_at": existing.get("last_attempt_at"),
            "last_success_at": existing.get("last_success_at"),
            "last_error": existing.get("last_error"),
            "consecutive_failures": int(existing.get("consecutive_failures", 0)),
        }
        updated = _hashed(
            {
                **registry,
                "revision": int(registry.get("revision", 0)) + 1,
                "updated_at": _now(),
                "workflows": workflows,
            },
            "registry_hash",
        )
        _write_atomic(registry_path, updated)
        return workflows[run_id]


def discover_workflows(registry_path: Path, repo_root: Path) -> dict[str, Any]:
    """Register valid generated workflows without letting one invalid run stop discovery."""

    existing = load_registry(registry_path)["workflows"]
    registered: list[str] = []
    rejected: list[dict[str, str]] = []
    for config_path in sorted((repo_root / "generated").glob("*/workflow-config.json")):
        artifact_root = config_path.parent
        spec_path = artifact_root / "current/workflow-center-spec.json"
        if not spec_path.exists():
            continue
        try:
            spec = _read(spec_path)
            run_id = str(spec.get("workflow_run_id", ""))
            if run_id in existing:
                continue
            entry = register_workflow(
                registry_path, config_path, artifact_root, spec_path, repo_root
            )
            registered.append(str(entry["workflow_run_id"]))
            existing = load_registry(registry_path)["workflows"]
        except Exception as error:
            rejected.append({"config_path": str(config_path), "error": str(error)})
    return {"registered": registered, "rejected": rejected}


def resume_workflow(
    registry_path: Path, run_id: str, *, acknowledge_accuracy_violation: bool = False
) -> dict[str, Any]:
    lock_path = registry_path.with_suffix(registry_path.suffix + ".lock")
    with _try_lock(lock_path) as acquired:
        if not acquired:
            raise ContractError("Active workflow registry is busy")
        registry = load_registry(registry_path)
        workflows = dict(registry["workflows"])
        if run_id not in workflows:
            raise ContractError(f"Workflow run is not registered: {run_id}")
        entry = dict(workflows[run_id])
        if entry.get("status") == "suspended_accuracy_violation" and not acknowledge_accuracy_violation:
            raise ContractError("Accuracy suspension requires explicit acknowledgement")
        if entry.get("status") not in {"blocked", "suspended_accuracy_violation", "needs_action"}:
            raise ContractError(f"Workflow run cannot be resumed from {entry.get('status')}")
        entry.update(
            {
                "status": "active",
                "consecutive_failures": 0,
                "last_error": None,
                "resumed_at": _now(),
                "accuracy_violation_acknowledged": bool(acknowledge_accuracy_violation),
            }
        )
        workflows[run_id] = entry
        updated = _hashed(
            {
                **registry,
                "revision": int(registry.get("revision", 0)) + 1,
                "updated_at": _now(),
                "workflows": workflows,
            },
            "registry_hash",
        )
        _write_atomic(registry_path, updated)
        return entry


def check_heartbeat(registry_path: Path, *, max_age_seconds: int = 90) -> dict[str, Any]:
    heartbeat_path = registry_path.with_name("workflow-monitor-heartbeat.json")
    heartbeat = _read(heartbeat_path)
    updated_at = str(heartbeat.get("updated_at", ""))
    try:
        observed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("Workflow monitor heartbeat timestamp is invalid") from error
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if age > max_age_seconds:
        raise ContractError(f"Workflow monitor heartbeat is stale: {age:.0f}s")
    return {"status": "healthy", "age_seconds": max(0, int(age)), **heartbeat}


def watchdog_status(registry_path: Path, *, max_age_seconds: int = 90) -> dict[str, Any]:
    """Persist an operator-visible alert; watchdog never receives dispatch authority."""
    alert_path = registry_path.with_name("workflow-monitor-alert.json")
    try:
        healthy = check_heartbeat(registry_path, max_age_seconds=max_age_seconds)
    except Exception as error:
        alert = {
            "schema_version": "workflow-monitor-alert/1.0",
            "status": "unhealthy",
            "observed_at": _now(),
            "error": str(error),
            "dispatch_authority": False,
        }
        _write_atomic(alert_path, alert)
        return alert
    if alert_path.exists():
        alert_path.unlink()
    return healthy


def _default_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, cwd=cwd, text=True, capture_output=True, check=False, timeout=180
        )
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            command, 124, error.stdout or "", "workflow sync timed out"
        )


def _dispatch_receipts(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []

    def visit(value: Any, label: str) -> None:
        if isinstance(value, Mapping):
            if value.get("action") in {"dispatched", "g02_correction_dispatched"}:
                node_id = str(value.get("node_id") or label).upper()
                bundle_hash = str(value.get("bundle_hash", ""))
                issue_id = str(value.get("issue_id", ""))
                attempt = int(value.get("attempt", value.get("correction_attempt", 1)))
                if not node_id or not bundle_hash or not issue_id or attempt < 1:
                    raise ContractError(f"Dispatched {node_id or label} is missing its binding receipt")
                receipts.append(
                    {
                        "node_id": node_id,
                        "bundle_hash": bundle_hash,
                        "issue_id": issue_id,
                        "attempt": attempt,
                    }
                )
                return
            for key, item in value.items():
                visit(item, str(key))
        elif isinstance(value, list):
            for item in value:
                visit(item, label)

    visit(result, "unknown")
    return receipts


def _eligible_dispatch_nodes(result: Mapping[str, Any]) -> list[str]:
    supervision = result.get("dispatch_supervision")
    if not isinstance(supervision, Mapping):
        return []
    nodes = supervision.get("eligible_nodes", [])
    if not isinstance(nodes, list) or any(not isinstance(item, str) for item in nodes):
        raise ContractError("Dispatch supervision eligible_nodes must be a string list")
    return sorted(set(nodes))


def _audit_path(registry_path: Path) -> Path:
    return registry_path.with_name("workflow-monitor-audit.json")


def _load_audit(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": AUDIT_SCHEMA,
            "events": [],
            "dispatches": {},
            "head_hash": None,
        }
    audit = _read(path)
    if audit.get("schema_version") != AUDIT_SCHEMA:
        raise ContractError("Workflow monitor audit schema_version is invalid")
    if not isinstance(audit.get("events"), list) or not isinstance(audit.get("dispatches"), dict):
        raise ContractError("Workflow monitor audit structure is invalid")
    if "head_hash" not in audit:
        legacy_snapshot_hash = content_hash(
            {"events": audit["events"], "dispatches": audit["dispatches"]}
        )
        previous = None
        migrated = []
        for legacy in audit["events"]:
            event = {
                **legacy,
                "previous_event_hash": previous,
                "migration": "legacy-monitor-audit-v1",
            }
            event["event_hash"] = content_hash(event)
            previous = event["event_hash"]
            migrated.append(event)
        audit = {
            **audit,
            "events": migrated,
            "head_hash": previous,
            "migration_receipt": {
                "source_schema": AUDIT_SCHEMA,
                "source_snapshot_hash": legacy_snapshot_hash,
                "migrated_at": _now(),
                "event_count": len(migrated),
            },
        }
    previous = None
    for event in audit["events"]:
        if not isinstance(event, Mapping) or event.get("previous_event_hash") != previous:
            raise ContractError("Workflow monitor audit chain is invalid")
        expected = content_hash(
            {key: value for key, value in event.items() if key != "event_hash"}
        )
        if event.get("event_hash") != expected:
            raise ContractError("Workflow monitor audit event hash is invalid")
        previous = expected
    if audit.get("head_hash") != previous:
        raise ContractError("Workflow monitor audit head hash is invalid")
    return audit



def _load_sync_output(stdout: str, run_id: str) -> tuple[str, dict[str, Any]]:
    """Parse one sync process stdout without treating lock skips as cross-run."""

    try:
        output = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ContractError("Workflow sync returned invalid JSON") from error
    if not isinstance(output, dict):
        raise ContractError("Workflow sync returned another workflow run")
    if output.get("skipped"):
        return "skipped", output
    if output.get("fatal") and output.get("workflow_run_id") not in {None, "", run_id}:
        raise ContractError("Workflow sync returned another workflow run")
    if output.get("fatal"):
        raise ContractError(str(output.get("fatal") or "Workflow sync process failed"))
    if output.get("workflow_run_id") != run_id:
        raise ContractError("Workflow sync returned another workflow run")
    return "result", output


def _sync_command(
    entry: Mapping[str, Any], sync_script: Path, plan_path: Path
) -> list[str]:
    return [
        sys.executable,
        str(sync_script),
        "--config",
        str(entry["config_path"]),
        "--artifact-root",
        str(entry["artifact_root"]),
        "--spec",
        str(entry["spec_path"]),
        "--sync-output",
        str(entry["sync_output"]),
        "--apply",
        "--dispatch-authorization",
        str(plan_path),
    ]


def _authorization_evidence(entry: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    artifact_root = Path(str(entry["artifact_root"]))
    artifacts = artifact_root / "artifacts-auto/artifacts"
    artifact_hashes: dict[str, str] = {}
    if artifacts.exists():
        for path in sorted(artifacts.glob("*.json")):
            value = _read(path)
            artifact_hashes[path.name] = str(value.get("artifact_hash") or content_hash(value))
    gate_hashes: dict[str, str] = {}
    gate_state_hashes: dict[str, str] = {}
    for gate in ("g01", "g02", "g03"):
        for base in (artifact_root / f"{gate}-auto", artifact_root / f"{gate}-live"):
            decision = base / f"{gate}-review-decision.json"
            if decision.exists():
                gate_hashes[gate.upper()] = content_hash(_read(decision))
            state = base / f"{gate}-workflow-state.json"
            if state.exists():
                gate_state_hashes[gate.upper()] = content_hash(_read(state))
    return {
        "spec_revision": spec.get("revision"),
        "artifact_hashes": artifact_hashes,
        "gate_decision_hashes": gate_hashes,
        "gate_state_hashes": gate_state_hashes,
    }


def _gate_event_cursors(entry: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(str(entry["artifact_root"]))
    cursors: dict[str, Any] = {}
    for gate in ("g01", "g02", "g03"):
        paths = [root / f"{gate}-auto" / f"{gate}-workflow-state.json", root / f"{gate}-live" / f"{gate}-workflow-state.json"]
        state_path = next((path for path in paths if path.exists()), None)
        if state_path is None:
            continue
        state = _read(state_path)
        cursors[gate.upper()] = {
            "state_hash": content_hash(state),
            "candidate_comment_id": state.get("candidate_comment_id"),
            "processed_event_id": state.get("processed_event_id"),
        }
    return cursors


_RETRYABLE_DISPATCH_STATES = {"queued", "blocked", "failed"}
_SATISFIED_DEPENDENCY_STATES = {"completed", "skipped"}
_AUTO_RETURN_SKIP_NODES = {"", "human", "G01", "G02", "G03"}


def _allowed_dispatch_nodes(spec: Mapping[str, Any]) -> list[str]:
    """Authorize retryable nodes and the agent they auto-return to.

    N04 can be blocked on the first Test Case IR failure while A08 is still
    completed. The correction dispatch targets A08, so the plan must include
    that next_node or the monitor refuses the only recovery path.
    """

    nodes = spec.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    known = {
        str(item.get("node_id"))
        for item in nodes
        if isinstance(item, Mapping) and item.get("node_id")
    }
    allowed: set[str] = set()
    states = {
        node_id: state
        for node_id, state in (
            (str(item.get("node_id") or ""), item.get("state"))
            for item in nodes
            if isinstance(item, Mapping)
        )
        if node_id
    }
    for item in nodes:
        if not isinstance(item, Mapping):
            continue
        node_id = item.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            continue
        retryable = item.get("state") in _RETRYABLE_DISPATCH_STATES
        if item.get("state") == "not_started":
            direct_dependencies = NODE_DIRECT_DEPENDENCIES.get(node_id)
            dependency_closure = set()
            pending_dependencies = list(direct_dependencies or ())
            while pending_dependencies:
                dependency = pending_dependencies.pop()
                if dependency in dependency_closure:
                    continue
                dependency_closure.add(dependency)
                pending_dependencies.extend(
                    NODE_DIRECT_DEPENDENCIES.get(dependency, ())
                )
            if node_id.startswith("A") and direct_dependencies and all(
                states.get(dependency) in _SATISFIED_DEPENDENCY_STATES
                for dependency in dependency_closure
            ):
                allowed.add(node_id)
            continue
        if not retryable and item.get("state") != "waiting_human":
            continue
        if retryable:
            allowed.add(node_id)
        path = item.get("artifact_path")
        if not path:
            continue
        try:
            artifact = _read(Path(str(path)))
        except (OSError, ContractError):
            continue
        payload = artifact.get("payload") if isinstance(artifact, Mapping) else None
        if not isinstance(payload, Mapping):
            continue
        next_node = str(payload.get("next_node") or "").strip()
        if next_node in known and next_node not in _AUTO_RETURN_SKIP_NODES:
            allowed.add(next_node)
        issues = payload.get("issues")
        if isinstance(issues, list):
            for issue in issues:
                if not isinstance(issue, Mapping):
                    continue
                route = str(issue.get("route_to") or "").strip()
                issue_id = str(issue.get("id") or "").strip()
                if (
                    issue_id
                    and route in known
                    and route not in _AUTO_RETURN_SKIP_NODES
                ):
                    allowed.add(route)
    return sorted(allowed)


def _dispatch_plan(entry: Mapping[str, Any], registry_revision: int) -> dict[str, Any]:
    spec = _read(Path(str(entry["spec_path"])))
    run_id = str(entry["workflow_run_id"])
    if spec.get("workflow_run_id") != run_id:
        raise ContractError("Planner spec belongs to another workflow run")
    allowed_nodes = _allowed_dispatch_nodes(spec)
    return _hashed(
        {
            "schema_version": "dispatch-authorization/1.0",
            "workflow_run_id": run_id,
            "workflow_id": entry["workflow_id"],
            "registry_revision": registry_revision,
            "spec_hash": content_hash(spec),
            "allowed_nodes": allowed_nodes,
            "authorization_evidence": _authorization_evidence(entry, spec),
            "created_at": _now(),
        },
        "plan_hash",
    )


def _verify_dispatch_plan(plan: Mapping[str, Any], entry: Mapping[str, Any]) -> None:
    """Independently derive authorization instead of calling the primary planner."""
    spec = _read(Path(str(entry["spec_path"])))
    nodes = spec.get("nodes")
    if not isinstance(nodes, list):
        raise ContractError("Shadow validator requires a node list")
    expected = {
        "schema_version": "dispatch-authorization/1.0",
        "workflow_run_id": str(entry["workflow_run_id"]),
        "workflow_id": entry["workflow_id"],
        "registry_revision": int(plan.get("registry_revision", -1)),
        "spec_hash": content_hash(spec),
        "allowed_nodes": _allowed_dispatch_nodes(spec),
        "authorization_evidence": _authorization_evidence(entry, spec),
    }
    if any(plan.get(field) != value for field, value in expected.items()):
        raise ContractError("Dispatch plan no longer matches the current workflow state")
    unhashed = {key: value for key, value in plan.items() if key != "plan_hash"}
    if plan.get("plan_hash") != content_hash(unhashed):
        raise ContractError("Dispatch plan hash is invalid")


def _monitor_once_locked(
    registry_path: Path,
    repo_root: Path,
    sync_script: Path,
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    runner = runner or _default_runner
    registry = load_registry(registry_path)
    audit_path = _audit_path(registry_path)
    audit = _load_audit(audit_path)
    results: list[dict[str, Any]] = []
    workflows = dict(registry["workflows"])
    futures: dict[str, Future[subprocess.CompletedProcess[str]]] = {}
    active_entries = [
        (run_id, dict(workflows[run_id]))
        for run_id in sorted(workflows)
        if workflows[run_id].get("status") in ACTIVE_STATUSES
    ]
    executor = ThreadPoolExecutor(max_workers=max(1, min(4, len(active_entries))))
    for run_id, entry in active_entries:
        try:
            validate_workflow_registration(
                Path(entry["config_path"]), Path(entry["artifact_root"]),
                Path(entry["spec_path"]), repo_root,
            )
            plan = _dispatch_plan(entry, int(registry["revision"]))
            plan_path = (registry_path.parent / "plans" / f"{run_id}.json").resolve()
            _write_atomic(plan_path, plan)
            _verify_dispatch_plan(plan, entry)
            futures[run_id] = executor.submit(
                runner, _sync_command(entry, sync_script, plan_path), repo_root
            )
        except Exception:
            # The coordinator below records the authoritative per-run failure.
            continue
    for run_id in sorted(workflows):
        entry = dict(workflows[run_id])
        if entry.get("status") not in ACTIVE_STATUSES:
            continue
        lock = registry_path.parent / "locks" / f"{run_id}.lock"
        with _try_lock(lock) as acquired:
            if not acquired:
                results.append({"workflow_run_id": run_id, "status": "busy"})
                continue
            entry["last_attempt_at"] = _now()
            event: dict[str, Any] = {
                "event_id": content_hash(
                    {"workflow_run_id": run_id, "registry_revision": registry["revision"], "at": entry["last_attempt_at"]}
                ),
                "workflow_run_id": run_id,
                "registry_revision": registry["revision"],
                "started_at": entry["last_attempt_at"],
            }
            try:
                validated = validate_workflow_registration(
                    Path(entry["config_path"]),
                    Path(entry["artifact_root"]),
                    Path(entry["spec_path"]),
                    repo_root,
                )
                if validated["workflow_run_id"] != run_id:
                    raise ContractError("Registry key belongs to another workflow run")
                plan = _dispatch_plan(entry, int(registry["revision"]))
                plan_path = registry_path.parent / "plans" / f"{run_id}.json"
                _write_atomic(plan_path, plan)
                _verify_dispatch_plan(plan, entry)
                future = futures.get(run_id)
                completed = future.result() if future is not None else runner(
                    _sync_command(entry, sync_script, plan_path), repo_root
                )
                if completed.returncode not in {0, 2}:
                    raise ContractError(completed.stderr.strip() or "Workflow sync process failed")
                kind, output = _load_sync_output(completed.stdout, run_id)
                if kind == "skipped":
                    previous = str(entry.get("status") or "running")
                    overall = "needs_action" if previous == "needs_action" else "running"
                    event["skipped"] = str(output.get("skipped"))
                    output = {
                        "workflow_run_id": run_id,
                        "errors": [],
                        "sync": {"overall_status": overall},
                    }
                receipts = _dispatch_receipts(output)
                eligible_nodes = _eligible_dispatch_nodes(output)
                event["attempted_dispatches"] = receipts
                for receipt in receipts:
                    if receipt["node_id"] not in plan["allowed_nodes"]:
                        raise ContractError(
                            f"Dispatcher returned unauthorized node {receipt['node_id']}"
                        )
                    dispatch_key = content_hash(
                        {
                            "workflow_run_id": run_id,
                            "node_id": receipt["node_id"],
                            "input_bundle_hash": receipt["bundle_hash"],
                            "attempt": receipt["attempt"],
                        }
                    )
                    previous = audit["dispatches"].get(dispatch_key)
                    if previous and previous.get("issue_id") != receipt["issue_id"]:
                        raise ContractError(f"Duplicate dispatch detected for {receipt['node_id']}")
                    audit["dispatches"][dispatch_key] = {
                        **receipt,
                        "workflow_run_id": run_id,
                        "dispatch_key": dispatch_key,
                    }
                sync_errors = output.get("errors", [])
                if not isinstance(sync_errors, list):
                    raise ContractError("Workflow sync errors must be a list")
                sync_state = output.get("sync") if isinstance(output.get("sync"), Mapping) else {}
                overall = str(sync_state.get("overall_status", "running"))
                entry["status"] = "completed" if overall in TERMINAL_SYNC_STATUSES else (
                    "needs_action" if overall == "needs_action" else "running"
                )
                entry["last_success_at"] = _now()
                spec_now = _read(Path(str(entry["spec_path"])))
                issue_cursor = {
                    str(item.get("node_id") or item.get("stage_card_id")): {
                        "issue_id": item.get("issue_id"),
                        "state": item.get("state"),
                        "completion": item.get("completion"),
                    }
                    for group in (spec_now.get("nodes", []), spec_now.get("stage_cards", []))
                    for item in group if isinstance(item, Mapping) and item.get("issue_id")
                }
                entry["event_cursors"] = {
                    "spec_revision": spec_now.get("revision"),
                    "spec_hash": content_hash(spec_now),
                    "issue_projection_hash": content_hash(issue_cursor),
                    "sync_result_hash": content_hash(output),
                    "gate_events": _gate_event_cursors(entry),
                }
                if sync_errors:
                    entry["last_error"] = {"message": "Workflow sync reported node errors", "errors": sync_errors, "at": _now()}
                    entry["consecutive_failures"] = int(entry.get("consecutive_failures", 0)) + 1
                    entry["status"] = "needs_action"
                else:
                    entry["last_error"] = None
                    entry["consecutive_failures"] = 0
                event.update(
                    {
                        "status": "completed_with_errors" if sync_errors else "completed",
                        "overall_status": overall,
                        "dispatches": receipts,
                        "sync_errors": sync_errors,
                        "plan_hash": plan["plan_hash"],
                        "allowed_nodes": plan["allowed_nodes"],
                        "eligible_nodes": eligible_nodes,
                    }
                )
            except Exception as error:
                failures = int(entry.get("consecutive_failures", 0)) + 1
                entry["consecutive_failures"] = failures
                entry["last_error"] = {"message": str(error), "at": _now()}
                if any(
                    marker in str(error)
                    for marker in (
                        "Duplicate dispatch",
                        "another workflow run",
                        "unauthorized node",
                        "Dispatch plan",
                    )
                ):
                    entry["status"] = "suspended_accuracy_violation"
                elif failures >= 3:
                    entry["status"] = "blocked"
                event.update({"status": "failed", "error": str(error)})
            event["finished_at"] = _now()
            event["previous_event_hash"] = audit.get("head_hash")
            event["event_hash"] = content_hash(event)
            audit["events"].append(event)
            audit["head_hash"] = event["event_hash"]
            workflows[run_id] = entry
            results.append({"workflow_run_id": run_id, "status": entry["status"], "error": entry.get("last_error")})
    executor.shutdown(wait=True)
    updated = _hashed(
        {
            **registry,
            "revision": int(registry.get("revision", 0)) + 1,
            "updated_at": _now(),
            "workflows": workflows,
        },
        "registry_hash",
    )
    _write_atomic(registry_path, updated)
    _write_atomic(audit_path, audit)
    heartbeat = {
        "schema_version": "workflow-monitor-heartbeat/1.0",
        "updated_at": _now(),
        "registry_revision": updated["revision"],
        "active_count": sum(1 for item in workflows.values() if item.get("status") in ACTIVE_STATUSES),
        "result_count": len(results),
        "dispatch_total": len(audit["dispatches"]),
        "accuracy_violation_total": sum(
            1 for item in workflows.values()
            if item.get("status") == "suspended_accuracy_violation"
        ),
        "eligible_without_dispatch_total": sum(
            max(0, len(event.get("eligible_nodes", [])) - len(event.get("dispatches", [])))
            for event in audit["events"] if event.get("status") in {"completed", "completed_with_errors"}
        ),
        "duplicate_dispatch_total": sum("Duplicate dispatch" in str(event.get("error", "")) for event in audit["events"]),
        "cross_run_dispatch_total": sum("another workflow run" in str(event.get("error", "")) for event in audit["events"]),
        "gate_bypass_total": sum("unauthorized node G" in str(event.get("error", "")) for event in audit["events"]),
    }
    attempted = sum(len(event.get("attempted_dispatches", [])) for event in audit["events"])
    invalid_attempts = (
        heartbeat["duplicate_dispatch_total"]
        + heartbeat["gate_bypass_total"]
        + heartbeat["cross_run_dispatch_total"]
    )
    heartbeat["dispatch_attempt_total"] = attempted
    heartbeat["dispatch_precision"] = (
        1.0 if attempted == 0 else max(0, attempted - invalid_attempts) / attempted
    )
    _write_atomic(registry_path.with_name("workflow-monitor-heartbeat.json"), heartbeat)
    return {"registry_revision": updated["revision"], "results": results, "heartbeat": heartbeat}


def monitor_once(
    registry_path: Path,
    repo_root: Path,
    sync_script: Path,
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    scan_lock = registry_path.with_suffix(registry_path.suffix + ".lock")
    with _try_lock(scan_lock) as acquired:
        if not acquired:
            return {"skipped": "another monitor scan is running", "results": []}
        return _monitor_once_locked(
            registry_path, repo_root, sync_script, runner=runner
        )
