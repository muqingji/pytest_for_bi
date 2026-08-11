"""N07 environment precheck and N16 environment fix deterministic nodes.

N07 records an environment fingerprint and checks, before any real Case
execution, that the target environment matches the frozen snapshot: deployment
commits, dependency health, test accounts, feature flags/tenant config, test
data prerequisites, runtime locale/time, test namespace availability and shared
resource locks. Any failed check blocks Case execution and routes to N16.

N16 performs explicit recoverable fix actions. Every action records its
expected state, pre state, result, compensation cleanup and idempotency key.
A fix that claims a state change while pre_state equals expected_state is
rejected (no state change, no silent re-precheck in place).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from .errors import ContractError
from .security import SecurityPolicy
from .storage import ArtifactStore


N07_CONTRACT = "n07-environment-precheck/1.0"
N16_CONTRACT = "n16-environment-fix/1.0"
FINGERPRINT_FIELDS = ("environment", "deployment_commits", "runtime")

CHECK_CATEGORIES = {
    "deployment_commit",
    "dependency_health",
    "test_account",
    "feature_flag",
    "test_data",
    "runtime_environment",
    "test_namespace",
    "resource_lock",
}
CHECK_STATUSES = {"passed", "warning", "failed", "not_applicable"}
LOCK_MODES = {"exclusive", "shared"}
FIX_RESULTS = {"performed", "not_required", "failed"}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object: {path}")
    return value


def _as_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{label} must be a list")
    return value


def _require(value: Any, label: str) -> Any:
    if value is None:
        raise ContractError(f"{label} is required")
    return value


def _validate_target(target: Mapping[str, Any]) -> None:
    if target.get("schema_version") != "environment-target/1.0":
        raise ContractError("N07 target schema_version must be environment-target/1.0")
    expected = target.get("expected")
    if not isinstance(expected, Mapping):
        raise ContractError("N07 target expected state is missing")
    for category in (
        "deployment_commits",
        "dependencies",
        "test_accounts",
        "feature_flags",
        "tenant_configs",
        "test_data_requirements",
    ):
        _as_list(expected.get(category, []), f"expected.{category}")
    runtime = expected.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ContractError("N07 target expected.runtime is missing")
    for field in ("timezone", "language"):
        if not str(runtime.get(field, "")).strip():
            raise ContractError(f"N07 target expected.runtime.{field} is required")
    namespace = expected.get("namespace_policy")
    if not isinstance(namespace, Mapping):
        raise ContractError("N07 target expected.namespace_policy is missing")
    if not str(namespace.get("prefix", "")).strip():
        raise ContractError("N07 target namespace_policy.prefix is required")
    locks = _as_list(expected.get("required_locks", []), "expected.required_locks")
    for index, lock in enumerate(locks):
        if not isinstance(lock, Mapping):
            raise ContractError(f"N07 required_locks[{index}] must be an object")
        if not str(lock.get("resource", "")).strip():
            raise ContractError(f"N07 required_locks[{index}].resource is required")
        if lock.get("mode") not in LOCK_MODES:
            raise ContractError(f"N07 required_locks[{index}].mode is invalid")


def _validate_observed(observed: Mapping[str, Any]) -> None:
    if observed.get("schema_version") != "environment-observation/1.0":
        raise ContractError("N07 observed schema_version must be environment-observation/1.0")
    for field in ("deployment_commits", "dependencies", "test_accounts", "feature_flags",
                  "tenant_configs", "test_data", "test_namespaces", "resource_locks"):
        _as_list(observed.get(field, []), f"observed.{field}")
    runtime = observed.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ContractError("N07 observed runtime is missing")


def _observed_map(observed: Mapping[str, Any], field: str, key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in _as_list(observed.get(field, []), f"observed.{field}"):
        if not isinstance(item, Mapping):
            continue
        result[str(item.get(key, ""))] = item
    return result


def _check(
    category: str,
    check_id: str,
    name: str,
    status: str,
    message: str,
    *,
    evidence: list[Any],
    source_refs: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "category": category,
        "name": name,
        "status": status,
        "message": message,
        "evidence": evidence,
        "source_refs": source_refs or [],
    }


def _evaluate_checks(target: Mapping[str, Any], observed: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected = target["expected"]
    checks: list[dict[str, Any]] = []
    index = 0

    def next_id() -> str:
        nonlocal index
        index += 1
        return f"N07-C{index:03d}"

    observed_commits = _observed_map(observed, "deployment_commits", "component")
    for item in _as_list(expected.get("deployment_commits", []), "expected.deployment_commits"):
        component = str(item.get("component", ""))
        wanted = str(item.get("commit", ""))
        seen = observed_commits.get(component)
        actual = str(seen.get("commit", "")) if seen else ""
        status = "passed" if actual == wanted else "failed"
        checks.append(
            _check(
                "deployment_commit",
                next_id(),
                f"deploy:{component}",
                status,
                f"{component} commit {actual or 'unknown'} vs target {wanted}",
                evidence=[{"observed": actual, "expected": wanted}],
                source_refs=[{"type": "target", "id": component}],
            )
        )

    observed_deps = _observed_map(observed, "dependencies", "name")
    for item in _as_list(expected.get("dependencies", []), "expected.dependencies"):
        name = str(item.get("name", ""))
        required = str(item.get("health_required", "ready"))
        seen = observed_deps.get(name)
        status = str(seen.get("status", "unknown")) if seen else "unknown"
        if status == required:
            check_status = "passed"
        elif status in {"degraded", "unknown", ""}:
            check_status = "warning"
        else:
            check_status = "failed"
        checks.append(
            _check(
                "dependency_health",
                next_id(),
                f"dep:{name}",
                check_status,
                f"{name} status {status or 'unknown'} (required {required})",
                evidence=[{"observed": status, "required": required}],
                source_refs=[{"type": "target", "id": name}],
            )
        )

    observed_accounts = _observed_map(observed, "test_accounts", "account")
    for item in _as_list(expected.get("test_accounts", []), "expected.test_accounts"):
        account = str(item.get("account", ""))
        wanted_perms = set(map(str, _as_list(item.get("permissions", []), "permissions")))
        seen = observed_accounts.get(account)
        if not seen or seen.get("exists") is not True:
            check_status, message = "failed", f"test account {account} missing"
        else:
            actual_perms = set(map(str, _as_list(seen.get("permissions", []), "permissions")))
            if wanted_perms <= actual_perms:
                check_status, message = "passed", f"test account {account} ready"
            else:
                check_status, message = (
                    "failed",
                    f"test account {account} missing permissions {sorted(wanted_perms - actual_perms)}",
                )
        checks.append(
            _check(
                "test_account",
                next_id(),
                f"account:{account}",
                check_status,
                message,
                evidence=[{"observed": seen or {}, "required_permissions": sorted(wanted_perms)}],
                source_refs=[{"type": "target", "id": account}],
            )
        )

    observed_flags = _observed_map(observed, "feature_flags", "flag")
    for item in _as_list(expected.get("feature_flags", []), "expected.feature_flags"):
        flag = str(item.get("flag", ""))
        wanted = str(item.get("expected", ""))
        seen = observed_flags.get(flag)
        actual = str(seen.get("value", "")) if seen else ""
        check_status = "passed" if actual == wanted else "failed"
        checks.append(
            _check(
                "feature_flag",
                next_id(),
                f"flag:{flag}",
                check_status,
                f"feature flag {flag}={actual or 'unset'} (expected {wanted})",
                evidence=[{"observed": actual, "expected": wanted}],
                source_refs=[{"type": "target", "id": flag}],
            )
        )

    observed_tenants = _observed_map(observed, "tenant_configs", "tenant")
    for item in _as_list(expected.get("tenant_configs", []), "expected.tenant_configs"):
        tenant = str(item.get("tenant", ""))
        field = str(item.get("field", "language"))
        wanted = str(item.get("value", ""))
        seen = observed_tenants.get(tenant)
        actual = str(seen.get(field, "")) if seen else ""
        check_status = "passed" if actual == wanted else "failed"
        checks.append(
            _check(
                "feature_flag",
                next_id(),
                f"tenant:{tenant}:{field}",
                check_status,
                f"tenant {tenant} {field}={actual or 'unset'} (expected {wanted})",
                evidence=[{"observed": actual, "expected": wanted}],
                source_refs=[{"type": "target", "id": tenant}],
            )
        )

    observed_data = _observed_map(observed, "test_data", "key")
    for item in _as_list(
        expected.get("test_data_requirements", []), "expected.test_data_requirements"
    ):
        key = str(item.get("key", ""))
        wanted = str(item.get("expected_state", "ready"))
        seen = observed_data.get(key)
        actual = str(seen.get("state", "missing")) if seen else "missing"
        check_status = "passed" if actual == wanted else "failed"
        checks.append(
            _check(
                "test_data",
                next_id(),
                f"data:{key}",
                check_status,
                f"test data {key} state {actual} (expected {wanted})",
                evidence=[{"observed": actual, "expected": wanted}],
                source_refs=[{"type": "target", "id": key}],
            )
        )

    expected_runtime = expected["runtime"]
    observed_runtime = observed.get("runtime", {})
    for field in ("timezone", "language"):
        wanted = str(expected_runtime.get(field, ""))
        actual = str(observed_runtime.get(field, ""))
        check_status = "passed" if actual == wanted else "failed"
        checks.append(
            _check(
                "runtime_environment",
                next_id(),
                f"runtime:{field}",
                check_status,
                f"runtime {field}={actual or 'unset'} (expected {wanted})",
                evidence=[{"observed": actual, "expected": wanted}],
                source_refs=[{"type": "target", "id": field}],
            )
        )
    if observed_runtime.get("system_time_skew_seconds") not in (None, 0):
        checks.append(
            _check(
                "runtime_environment",
                next_id(),
                "runtime:system_time_skew",
                "warning",
                f"system time skew {observed_runtime.get('system_time_skew_seconds')}s",
                evidence=[{"observed": observed_runtime.get("system_time_skew_seconds")}],
                source_refs=[{"type": "observed", "id": "system_time_skew_seconds"}],
            )
        )

    namespace_policy = expected["namespace_policy"]
    observed_namespaces = _as_list(observed.get("test_namespaces", []), "observed.test_namespaces")
    if observed_namespaces:
        namespace = observed_namespaces[0]
        prefix_ok = str(namespace.get("namespace", "")).startswith(
            str(namespace_policy.get("prefix", ""))
        )
        cleanup = namespace.get("cleanup_policy")
        if not prefix_ok:
            check_status, message = "failed", "test namespace does not match required prefix"
        elif not isinstance(cleanup, Mapping) or cleanup.get("required") is not True:
            check_status, message = "warning", "test namespace lacks a cleanup policy"
        else:
            check_status, message = "passed", "test namespace available with cleanup policy"
        checks.append(
            _check(
                "test_namespace",
                next_id(),
                "namespace:available",
                check_status,
                message,
                evidence=[{"observed": namespace}],
                source_refs=[{"type": "target", "id": "namespace_policy"}],
            )
        )
    else:
        checks.append(
            _check(
                "test_namespace",
                next_id(),
                "namespace:available",
                "failed",
                "no test namespace observed",
                evidence=[],
                source_refs=[{"type": "target", "id": "namespace_policy"}],
            )
        )

    observed_locks = _observed_map(observed, "resource_locks", "resource")
    for item in _as_list(expected.get("required_locks", []), "expected.required_locks"):
        resource = str(item.get("resource", ""))
        mode = str(item.get("mode", ""))
        reason = str(item.get("reason", ""))
        seen = observed_locks.get(resource)
        if not seen or seen.get("acquired") is not True:
            check_status, message = "failed", f"resource lock {resource} not acquired"
        elif str(seen.get("mode", "")) != mode:
            check_status, message = (
                "failed",
                f"resource lock {resource} mode {seen.get('mode')} != required {mode}",
            )
        elif str(seen.get("holder", "")) != str(observed.get("requester_id", "")):
            check_status, message = "failed", f"resource lock {resource} held by another holder"
        else:
            check_status, message = "passed", f"resource lock {resource} acquired ({mode})"
        checks.append(
            _check(
                "resource_lock",
                next_id(),
                f"lock:{resource}",
                check_status,
                message,
                evidence=[{"observed": seen or {}, "required_mode": mode, "reason": reason}],
                source_refs=[{"type": "target", "id": resource}],
            )
        )
    return checks


def _fingerprint(target: Mapping[str, Any], observed: Mapping[str, Any]) -> str:
    target_expected = target.get("expected", {})
    return content_hash(
        {
            "environment": observed.get("environment"),
            "deployment_commits": observed.get("deployment_commits", []),
            "runtime": observed.get("runtime", {}),
            "expected_runtime": target_expected.get("runtime", {}),
            "expected_commits": target_expected.get("deployment_commits", []),
        }
    )


def run_n07_env_precheck(
    target_path: Path,
    observed_path: Path,
    output_dir: Path,
    *,
    workflow_run_id: str,
    source_snapshot_id: str,
    workflow_mode: str = "environment_precheck",
    previous_fingerprint: str = "",
    throttle_reason: str = "",
    test_data_validation_path: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Run the deterministic N07 environment precheck and persist its Artifact."""

    security = security or SecurityPolicy()
    target = _read_json(target_path, "N07 target")
    observed = _read_json(observed_path, "N07 observed")
    for value in (target, observed):
        security.assert_no_secret_values(value)
    _validate_target(target)
    _validate_observed(observed)

    fingerprint = _fingerprint(target, observed)
    if previous_fingerprint and previous_fingerprint == fingerprint:
        if not throttle_reason.strip():
            raise ContractError(
                "N07 environment state is unchanged; re-precheck is throttled unless a reason is recorded"
            )
    checks = _evaluate_checks(target, observed)
    data_validation: dict[str, Any] | None = None
    data_evidence: tuple[EvidenceRef, ...] = ()
    if test_data_validation_path is not None:
        data_validation = _read_json(test_data_validation_path, "N27 data validation")
        security.assert_no_secret_values(data_validation)
        if data_validation.get("schema_version") != "artifact-envelope/1.0":
            raise ContractError("N07 N27 data validation is not an Artifact Envelope")
        if data_validation.get("artifact_hash") != artifact_hash_from_mapping(data_validation):
            raise ContractError("N07 N27 data validation Artifact hash is invalid")
        producer = data_validation.get("producer")
        payload = data_validation.get("payload")
        if (
            data_validation.get("artifact_id") != "n27-test-data-plan-validation"
            or not isinstance(producer, Mapping)
            or producer.get("component_id") != "N27"
            or not isinstance(payload, Mapping)
        ):
            raise ContractError("N07 requires an N27 data validation Artifact")
        if (
            data_validation.get("workflow_run_id") != workflow_run_id
            or data_validation.get("source_snapshot_id") != source_snapshot_id
        ):
            raise ContractError("N07 and N27 workflow bindings do not match")
        accepted = (
            data_validation.get("status") == "completed" and payload.get("valid") is True
        ) or (
            data_validation.get("status") == "skipped_by_policy"
            and payload.get("valid") is True
            and payload.get("decision") == "skipped_by_policy"
            and payload.get("next_node") == "N07"
        )
        if not accepted:
            raise ContractError("N07 requires completed or policy-skipped valid N27 evidence")
        checks.append(
            _check(
                "test_data",
                f"N07-C{len(checks) + 1:03d}",
                "test-data-plan:route",
                "passed",
                f"N27 decision={payload.get('decision', 'validated')}",
                evidence=[
                    {
                        "artifact_hash": data_validation["artifact_hash"],
                        "decision": payload.get("decision", "validated"),
                        "deferred_case_count": len(payload.get("deferred_cases", [])),
                    }
                ],
                source_refs=[{"type": "artifact", "id": "n27-test-data-plan-validation"}],
            )
        )
        data_evidence = (
            EvidenceRef(
                source_type="artifact",
                source_id="n27-test-data-plan-validation",
                location=test_data_validation_path.name,
                content_hash=str(data_validation["artifact_hash"]),
            ),
        )
    summary = {
        "passed": sum(item["status"] == "passed" for item in checks),
        "warning": sum(item["status"] == "warning" for item in checks),
        "failed": sum(item["status"] == "failed" for item in checks),
        "not_applicable": sum(item["status"] == "not_applicable" for item in checks),
    }
    if summary["failed"]:
        decision, status, next_node = "blocked", "blocked", "N16"
    elif summary["warning"]:
        decision, status, next_node = "passed_with_warnings", "completed_with_gaps", "N08"
    else:
        decision, status, next_node = "passed", "completed", "N08"

    payload = {
        "schema_version": N07_CONTRACT,
        "workflow_run_id": workflow_run_id,
        "source_snapshot_id": source_snapshot_id,
        "environment_class": str(target.get("environment_class", "unspecified")),
        "production_isolation": bool(target.get("production_isolation", False)),
        "environment_fingerprint": fingerprint,
        "target_hash": content_hash(target),
        "observed_hash": content_hash(observed),
        "throttled": bool(previous_fingerprint and previous_fingerprint == fingerprint),
        "throttle_reason": throttle_reason,
        "checks": checks,
        "summary": summary,
        "decision": decision,
        "next_node": next_node,
        "test_data_validation_hash": (
            str(data_validation["artifact_hash"]) if data_validation is not None else None
        ),
    }
    security.assert_no_secret_values(payload)
    artifact = ArtifactEnvelope(
        workflow_run_id=workflow_run_id,
        workflow_mode=workflow_mode,
        artifact_id="n07-environment-precheck",
        source_snapshot_id=source_snapshot_id,
        producer=Producer(component_id="N07", runtime="deterministic"),
        payload=payload,
        status=ArtifactStatus(status),
        evidence_refs=(
            EvidenceRef(
                source_type="target",
                source_id="environment-target",
                location=target_path.name,
                content_hash=content_hash(target),
            ),
            EvidenceRef(
                source_type="observed",
                source_id="environment-observation",
                location=observed_path.name,
                content_hash=content_hash(observed),
            ),
            *data_evidence,
        ),
        reason_code="environment_precheck_blocked" if status == "blocked" else None,
    )
    store = ArtifactStore(output_dir)
    store.write_artifact(artifact)
    return artifact.to_dict()


def _verified_precheck(precheck_path: Path, security: SecurityPolicy) -> dict[str, Any]:
    artifact = _read_json(precheck_path, "N07 precheck Artifact")
    if artifact.get("artifact_id") != "n07-environment-precheck":
        raise ContractError(f"Expected n07-environment-precheck Artifact: {precheck_path}")
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError("N07 precheck Artifact hash is invalid")
    security.assert_no_secret_values(artifact)
    return artifact


def run_n16_env_fix(
    precheck_path: Path,
    fix_plan_path: Path,
    output_dir: Path,
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Execute the deterministic N16 fix gate against a failed N07 precheck."""

    security = security or SecurityPolicy()
    precheck = _verified_precheck(precheck_path, security)
    payload = precheck.get("payload", {})
    failed_checks = [
        item for item in payload.get("checks", []) if item.get("status") == "failed"
    ]
    if payload.get("decision") != "blocked" or not failed_checks:
        raise ContractError("N16 requires a blocked N07 precheck with failed checks")

    plan = _read_json(fix_plan_path, "N16 fix plan")
    security.assert_no_secret_values(plan)
    if plan.get("schema_version") != "environment-fix-plan/1.0":
        raise ContractError("N16 fix plan schema_version must be environment-fix-plan/1.0")
    actions = _as_list(plan.get("actions", []), "N16 fix plan actions")
    if not actions:
        raise ContractError("N16 fix plan has no actions")
    addressed: dict[str, list[str]] = {}
    action_ids: list[str] = []
    for index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            raise ContractError(f"N16 fix action[{index}] must be an object")
        action_id = str(action.get("id", ""))
        action_ids.append(action_id)
        target_check = str(action.get("target_check", ""))
        result = str(action.get("result", ""))
        if not action_id or not target_check:
            raise ContractError(f"N16 fix action[{index}] id/target_check are required")
        if result not in FIX_RESULTS:
            raise ContractError(f"N16 fix action[{index}] has an invalid result")
        for field in ("expected_state", "pre_state", "compensation"):
            if action.get(field) in (None, ""):
                raise ContractError(f"N16 fix action[{index}] {field} is required")
        idempotency_key = str(action.get("idempotency_key", ""))
        unhashed = {
            key: value
            for key, value in action.items()
            if key not in {"idempotency_key"}
        }
        if idempotency_key != content_hash(unhashed):
            raise ContractError(f"N16 fix action[{index}] idempotency_key is invalid")
        if result == "performed" and action["pre_state"] == action["expected_state"]:
            raise ContractError(
                f"N16 fix action[{index}] claims a state change without any state change"
            )
        addressed.setdefault(target_check, []).append(action_id)
    if len(action_ids) != len(set(action_ids)):
        raise ContractError("N16 fix action IDs must be unique")

    failed_check_ids = {item.get("id") for item in failed_checks}
    unaddressed = sorted(failed_check_ids - set(addressed))
    if unaddressed:
        raise ContractError(f"N16 fix plan does not address failed checks: {unaddressed}")

    performed = [item for item in actions if item["result"] == "performed"]
    failed_actions = [item for item in actions if item["result"] == "failed"]
    payload_out = {
        "schema_version": N16_CONTRACT,
        "workflow_run_id": payload.get("workflow_run_id"),
        "source_snapshot_id": payload.get("source_snapshot_id"),
        "precheck_hash": precheck["artifact_hash"],
        "environment_fingerprint": payload.get("environment_fingerprint"),
        "addressed_checks": sorted(addressed),
        "summary": {
            "actions": len(actions),
            "performed": len(performed),
            "not_required": sum(item["result"] == "not_required" for item in actions),
            "failed": len(failed_actions),
        },
        "actions": [dict(item) for item in actions],
    }
    if failed_actions:
        payload_out["decision"] = "blocked"
        payload_out["next_node"] = "human"
        payload_out["status"] = "blocked"
    else:
        payload_out["decision"] = "fixed"
        payload_out["next_node"] = "N07"
        payload_out["status"] = "completed"
    security.assert_no_secret_values(payload_out)
    artifact = ArtifactEnvelope(
        workflow_run_id=payload_out["workflow_run_id"] or "unknown",
        workflow_mode="environment_fix",
        artifact_id="n16-environment-fix",
        source_snapshot_id=payload_out["source_snapshot_id"] or "unknown",
        producer=Producer(component_id="N16", runtime="deterministic"),
        payload=payload_out,
        status=ArtifactStatus(payload_out["status"]),
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="n07-environment-precheck",
                location=precheck_path.name,
                content_hash=precheck["artifact_hash"],
            ),
        ),
        reason_code="environment_fix_blocked" if payload_out["status"] == "blocked" else None,
    )
    ArtifactStore(output_dir).write_artifact(artifact)
    return artifact.to_dict()
