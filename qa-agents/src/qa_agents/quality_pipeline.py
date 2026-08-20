"""Deterministic server-side execution evidence, quality decision, and reporting tail."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re
from typing import Any

from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from .errors import ContractError, InputError
from .failure_triage import run_a19_failure_triage
from .security import SecurityPolicy
from .storage import ArtifactStore


MANUAL_RESULT_STATUSES = {"passed", "failed", "blocked", "not_executed"}
FAILURE_CLASSIFICATIONS = {
    "product_defect",
    "automation_defect",
    "test_data",
    "environment",
    "requirement_ambiguity",
    "needs_triage",
}
TERMINAL_TEST_RESULTS = {"passed", "failed", "blocked"}


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be a JSON object")
    return value


def _verified_artifact(
    path: Path,
    label: str,
    *,
    expected_id: str | None = None,
    expected_producer: str | None = None,
    security: SecurityPolicy,
) -> dict[str, Any]:
    artifact = _read_object(path, label)
    if artifact.get("schema_version") != "artifact-envelope/1.0":
        raise ContractError(f"{label} is not an Artifact Envelope")
    if artifact_hash_from_mapping(artifact) != artifact.get("artifact_hash"):
        raise ContractError(f"{label} artifact hash is invalid")
    if expected_id and artifact.get("artifact_id") != expected_id:
        raise ContractError(f"{label} must be Artifact {expected_id}")
    producer = artifact.get("producer")
    if not isinstance(producer, Mapping):
        raise ContractError(f"{label} producer is missing")
    if expected_producer and producer.get("component_id") != expected_producer:
        raise ContractError(f"{label} producer must be {expected_producer}")
    if not isinstance(artifact.get("payload"), Mapping):
        raise ContractError(f"{label} payload must be an object")
    security.assert_no_secret_values(artifact)
    return artifact


def _identity(artifact: Mapping[str, Any]) -> tuple[str, str, str]:
    identity = (
        str(artifact.get("workflow_run_id", "")).strip(),
        str(artifact.get("workflow_mode", "")).strip(),
        str(artifact.get("source_snapshot_id", "")).strip(),
    )
    if not all(identity):
        raise ContractError("Artifact workflow identity is incomplete")
    return identity


def _assert_same_identity(
    anchor: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]]
) -> tuple[str, str, str]:
    identity = _identity(anchor)
    for artifact in artifacts:
        if _identity(artifact) != identity:
            raise ContractError("Server quality inputs belong to different workflow runs")
    return identity


def _artifact(
    identity: tuple[str, str, str],
    node_id: str,
    artifact_id: str,
    payload: Mapping[str, Any],
    status: ArtifactStatus = ArtifactStatus.COMPLETED,
    reason_code: str | None = None,
    evidence: Sequence[Mapping[str, Any]] = (),
) -> ArtifactEnvelope:
    refs = tuple(
        EvidenceRef(
            source_type="artifact",
            source_id=str(item["artifact_id"]),
            location=str(item.get("location", item["artifact_id"])),
            content_hash=str(item["artifact_hash"]),
        )
        for item in evidence
    )
    return ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id=artifact_id,
        source_snapshot_id=identity[2],
        producer=Producer(node_id, runtime="deterministic"),
        payload=payload,
        status=status,
        reason_code=reason_code,
        evidence_refs=refs,
    )


def _binding(artifact: Mapping[str, Any], location: str) -> dict[str, str]:
    return {
        "artifact_id": str(artifact["artifact_id"]),
        "artifact_hash": str(artifact["artifact_hash"]),
        "location": location,
    }


def _manual_results(
    path: Path | None,
    identity: tuple[str, str, str],
    expected_case_ids: set[str],
    security: SecurityPolicy,
) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    value = _read_object(path, "manual test results")
    security.assert_no_secret_values(value)
    if value.get("schema_version") != "manual-test-results/1.0":
        raise ContractError("Manual results schema_version must be manual-test-results/1.0")
    if (
        str(value.get("workflow_run_id", "")) != identity[0]
        or str(value.get("source_snapshot_id", "")) != identity[2]
    ):
        raise ContractError("Manual results belong to another workflow run")
    results = value.get("results")
    if not isinstance(results, list):
        raise ContractError("Manual results.results must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(results):
        if not isinstance(item, Mapping):
            raise ContractError(f"Manual result {index} must be an object")
        case_id = str(item.get("case_id", "")).strip()
        status = str(item.get("status", "")).strip()
        if not case_id or case_id not in expected_case_ids:
            raise ContractError(f"Manual result is not bound to a manual plan action: {case_id}")
        if case_id in indexed:
            raise ContractError(f"Manual results contain duplicate case_id: {case_id}")
        if status not in MANUAL_RESULT_STATUSES:
            raise ContractError(f"Manual result {case_id} status is invalid")
        if status in TERMINAL_TEST_RESULTS:
            executor = item.get("executor")
            if not isinstance(executor, Mapping) or not str(executor.get("id", "")).strip():
                raise ContractError(f"Manual result {case_id} requires executor.id")
            if not str(item.get("actual_result", "")).strip():
                raise ContractError(f"Manual result {case_id} requires actual_result")
            evidence = item.get("evidence", [])
            if not isinstance(evidence, list) or not evidence:
                raise ContractError(f"Manual result {case_id} requires evidence")
        classification = item.get("classification")
        if status == "failed" and classification not in FAILURE_CLASSIFICATIONS:
            raise ContractError(f"Failed manual result {case_id} requires classification")
        indexed[case_id] = dict(item)
    return indexed


def _normalize_failure_text(value: str) -> str:
    value = re.sub(r"0x[0-9a-fA-F]+", "<hex>", value)
    value = re.sub(r"\b\d{2,}\b", "<n>", value)
    value = re.sub(r"/[^\s:]+", "<path>", value)
    return " ".join(value.lower().split())[:4000]


def _failure_detail(value: str) -> dict[str, Any] | None:
    match = re.search(
        r"(?P<oracle>[A-Za-z0-9_-]+): Oracle fields differ; "
        r"missing=(?P<missing>\[[^\]]*\]), mismatched=(?P<mismatched>\{[^\n]*\})",
        value,
    )
    if match is None:
        return None
    return {
        "failure_code": "oracle_fields_differ",
        "oracle_id": match.group("oracle"),
        "missing_fields": re.findall(r"['\"]([^'\"]+)['\"]", match.group("missing")),
        "mismatched_fields": match.group("mismatched"),
    }


def _auto_classification(shard: Mapping[str, Any]) -> str:
    outcome = str(shard.get("outcome", ""))
    if outcome in {"timed_out", "infrastructure_error"}:
        return "environment"
    text = f"{shard.get('stdout', '')}\n{shard.get('stderr', '')}".lower()
    if any(token in text for token in ("syntaxerror", "importerror", "fixture '")):
        return "automation_defect"
    return "needs_triage"


def _render_report_html(report: Mapping[str, Any]) -> str:
    decision = report["decision"]
    metrics = report["metrics"]
    reason_rows = "".join(
        f"<li>{escape(str(item))}</li>" for item in report.get("reasons", [])
    ) or "<li>None</li>"
    warning_rows = "".join(
        f"<li>{escape(str(item))}</li>" for item in report.get("warnings", [])
    ) or "<li>None</li>"
    failure_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('cluster_id', '')))}</td>"
        f"<td>{escape(str(item.get('classification', '')))}</td>"
        f"<td>{escape(', '.join(map(str, item.get('case_ids', []))))}</td>"
        f"<td>{escape(str(item.get('summary', '')))}</td>"
        "</tr>"
        for item in report.get("failure_clusters", [])
    ) or "<tr><td colspan='4'>No failure clusters</td></tr>"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA Server Quality Report</title><style>
body{{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#202124;margin:28px}}
main{{max-width:1180px;margin:auto}}h1{{font-size:24px}}h2{{font-size:17px;margin-top:26px}}
table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #dfe1e5;padding:8px;text-align:left;vertical-align:top}}
th{{background:#f8f9fa}}code{{background:#f1f3f4;padding:2px 4px}}
</style></head><body><main><h1>QA Server Quality Report</h1>
<p>Run: <code>{escape(str(report['workflow_run_id']))}</code> | Decision: <strong>{escape(str(decision))}</strong></p>
<h2>Execution</h2><p>{metrics['executed']} executed / {metrics['planned']} planned; {metrics['passed']} passed; {metrics['failed']} failed; {metrics['pending']} pending.</p>
<h2>Reasons</h2><ul>{reason_rows}</ul><h2>Warnings</h2><ul>{warning_rows}</ul>
<h2>Failure Clusters</h2><table><thead><tr><th>Cluster</th><th>Classification</th><th>Cases</th><th>Summary</th></tr></thead><tbody>{failure_rows}</tbody></table>
</main></body></html>"""


def _render_report_markdown(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# QA Server Quality Report",
        "",
        f"- Workflow Run: `{report['workflow_run_id']}`",
        f"- Decision: **{report['decision']}**",
        f"- Release disposition: `{report['release_disposition']}`",
        f"- Execution: `{metrics['executed']}/{metrics['planned']}`",
        f"- Passed / failed / pending: `{metrics['passed']} / {metrics['failed']} / {metrics['pending']}`",
        "",
        "## Reasons",
        "",
    ]
    lines.extend(f"- {item}" for item in report.get("reasons", []))
    if not report.get("reasons"):
        lines.append("- None")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in report.get("warnings", []))
    if not report.get("warnings"):
        lines.append("- None")
    lines.extend(["", "## Failure Clusters", ""])
    for item in report.get("failure_clusters", []):
        lines.append(
            f"- `{item['cluster_id']}` {item['classification']}: "
            f"{', '.join(item.get('case_ids', []))} - {item.get('summary', '')}"
        )
    if not report.get("failure_clusters"):
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def run_server_quality_tail(
    execution_plan_path: Path,
    compiled_cases_path: Path,
    environment_precheck_path: Path,
    output_dir: Path,
    *,
    test_data_validation_path: Path | None = None,
    automation_execution_paths: Sequence[Path] = (),
    manual_results_path: Path | None = None,
    bug_history_path: Path | None = None,
    flaky_quarantine_path: Path | None = None,
    quality_policy_path: Path,
    retry_attempt: int = 0,
    run_manifest_path: Path | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Run N10/N17/N18/N09/A19/N20/N11/N12 for one server workflow run."""

    security = security or SecurityPolicy()
    plan = _verified_artifact(
        execution_plan_path,
        "N15 execution plan",
        expected_id="n15-execution-plan",
        expected_producer="N15",
        security=security,
    )
    compiled = _verified_artifact(
        compiled_cases_path,
        "N25 compiled cases",
        expected_id="n25-compiled-test-cases",
        expected_producer="N25",
        security=security,
    )
    precheck = _verified_artifact(
        environment_precheck_path,
        "N07 environment precheck",
        expected_id="n07-environment-precheck",
        expected_producer="N07",
        security=security,
    )
    executions = [
        _verified_artifact(
            path,
            f"N08 automation execution {index}",
            expected_id="n08-automation-execution",
            expected_producer="N08",
            security=security,
        )
        for index, path in enumerate(automation_execution_paths, start=1)
    ]
    data_validation = (
        _verified_artifact(
            test_data_validation_path,
            "N27 test-data validation",
            expected_id="n27-test-data-plan-validation",
            expected_producer="N27",
            security=security,
        )
        if test_data_validation_path is not None
        else None
    )
    identity = _assert_same_identity(
        plan, [compiled, precheck, *executions, *([data_validation] if data_validation else [])]
    )
    run_manifest: dict[str, Any] | None = None
    if run_manifest_path is not None:
        run_manifest = _read_object(run_manifest_path, "run manifest")
        if (
            run_manifest.get("workflow_run_id") != identity[0]
            or run_manifest.get("source_snapshot_id") != identity[2]
        ):
            raise ContractError("Server quality checkpoint belongs to another workflow run")
    if precheck["payload"].get("next_node") != "N08":
        raise ContractError("Server quality tail requires N07 routed to N08")
    if plan["payload"].get("schema_version") != "execution-plan/1.0":
        raise ContractError("N15 execution plan payload contract is invalid")
    if compiled["payload"].get("schema_version") != "n25-compiled-test-cases/1.0":
        raise ContractError("N25 compiled cases payload contract is invalid")

    policy = _read_object(quality_policy_path, "quality policy")
    security.assert_no_secret_values(policy)
    if policy.get("schema_version") != "quality-policy/1.0":
        raise ContractError("Quality policy schema_version must be quality-policy/1.0")
    max_retry_attempts = int(policy.get("max_environment_retry_attempts", 1))
    require_production_isolation = policy.get("require_production_isolation_for_release")
    if not isinstance(require_production_isolation, bool):
        raise ContractError(
            "Quality policy require_production_isolation_for_release must be boolean"
        )
    if retry_attempt < 0:
        raise ContractError("retry_attempt cannot be negative")

    actions = plan["payload"].get("actions")
    cases = compiled["payload"].get("compiled_cases")
    if not isinstance(actions, list) or not all(isinstance(item, Mapping) for item in actions):
        raise ContractError("N15 actions must be a list of objects")
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N25 compiled_cases must be a list of objects")
    cases_by_id = {str(item.get("id", "")): dict(item) for item in cases}
    action_case_ids = [str(item.get("case_id", "")) for item in actions]
    if not all(action_case_ids) or len(set(action_case_ids)) != len(action_case_ids):
        raise ContractError("N15 actions require unique case_id values")
    missing_cases = sorted(set(action_case_ids) - set(cases_by_id))
    if missing_cases:
        raise ContractError(f"N15 actions reference unknown compiled cases: {missing_cases}")
    deferred_data_case_ids: set[str] = set()
    deferred_frontend_case_ids: set[str] = set()
    policy_deferred_case_ids: set[str] = set()
    if data_validation is not None:
        data_payload = data_validation["payload"]
        if data_payload.get("valid") is not True or data_validation.get("status") not in {
            "completed", "completed_with_gaps", "skipped_by_policy"
        }:
            raise ContractError("Server quality requires valid N27 data routing")
        pending_human_evidence = (
            data_validation.get("status") == "completed_with_gaps"
            and data_payload.get("valid") is True
            and data_payload.get("pending_human") is True
        )
        partial_routing_evidence = (
            data_validation.get("status") == "completed_with_gaps"
            and data_payload.get("decision") == "partial_capability_routing"
            and isinstance(data_payload.get("executable_case_ids"), list)
            and isinstance(data_payload.get("deferred_cases"), list)
        )
        if data_validation.get("status") == "completed_with_gaps" and not (
            partial_routing_evidence or pending_human_evidence
        ):
            raise ContractError("Partial N27 routing contract is invalid")
        deferred_routes = {
            str(item.get("case_id", "")): str(item.get("route", ""))
            for item in data_payload.get("deferred_cases", [])
            if isinstance(item, Mapping) and str(item.get("case_id", ""))
        }
        policy_deferred_case_ids = set(deferred_routes)
        deferred_data_case_ids = {
            case_id
            for case_id, route in deferred_routes.items()
            if route == "deferred_data_construction"
        }
        deferred_frontend_case_ids = {
            case_id for case_id, route in deferred_routes.items() if route == "deferred_frontend"
        }
        unknown_deferred = sorted(policy_deferred_case_ids - set(action_case_ids))
        if unknown_deferred:
            raise ContractError(f"N27 defers Cases outside the N15 plan: {unknown_deferred}")

    store = ArtifactStore(output_dir)
    upstream = [
        _binding(plan, execution_plan_path.name),
        _binding(compiled, compiled_cases_path.name),
        _binding(precheck, environment_precheck_path.name),
    ]

    retryable = [
        artifact
        for artifact in executions
        if artifact["payload"].get("next_node") == "N10"
    ]
    retry_allowed = bool(retryable) and retry_attempt < max_retry_attempts
    n10_payload = {
        "schema_version": "n10-retry-budget/1.0",
        "attempt": retry_attempt,
        "max_attempts": max_retry_attempts,
        "retryable_execution_hashes": [item["artifact_hash"] for item in retryable],
        "decision": "retry_allowed" if retry_allowed else (
            "budget_exhausted" if retryable else "not_required"
        ),
        "next_node": "N07" if retry_allowed else "N09",
        "policy_hash": content_hash(policy),
    }
    n10 = _artifact(
        identity,
        "N10",
        "n10-retry-budget",
        n10_payload,
        ArtifactStatus.FAILED_RETRYABLE if retry_allowed else ArtifactStatus.COMPLETED,
        "environment_retry_allowed" if retry_allowed else None,
        [_binding(item, "n08-automation-execution.json") for item in retryable],
    )
    store.write_artifact(n10)

    manual_ids = {
        str(item["case_id"])
        for item in actions
        if item.get("action") == "manual_run"
        and str(item.get("case_id", "")) not in policy_deferred_case_ids
    }
    provided_manual = _manual_results(
        manual_results_path, identity, manual_ids, security
    )
    manual_tasks: list[dict[str, Any]] = []
    for case_id in sorted(manual_ids):
        case = cases_by_id[case_id]
        result = provided_manual.get(case_id)
        manual_tasks.append(
            {
                "case_id": case_id,
                "title": case.get("title", case_id),
                "priority": case.get("priority", "P2"),
                "risk": case.get("risk", "medium"),
                "steps": case.get("steps", []),
                "expected": case.get("expected", []),
                "status": result.get("status") if result else "pending",
                "result": result,
            }
        )
    pending_manual = sum(item["status"] in {"pending", "not_executed"} for item in manual_tasks)
    n17_payload = {
        "schema_version": "n17-manual-execution/1.0",
        "execution_plan_hash": plan["artifact_hash"],
        "task_count": len(manual_tasks),
        "completed_count": sum(item["status"] in TERMINAL_TEST_RESULTS for item in manual_tasks),
        "pending_count": pending_manual,
        "tasks": manual_tasks,
        "next_node": "N09",
    }
    n17 = _artifact(
        identity,
        "N17",
        "n17-manual-execution",
        n17_payload,
        ArtifactStatus.NEEDS_HUMAN if pending_manual else ArtifactStatus.COMPLETED,
        "manual_results_pending" if pending_manual else None,
        [_binding(plan, execution_plan_path.name)],
    )
    store.write_artifact(n17)
    if manual_tasks:
        store.write_json(
            "manual-test-tasks.json",
            {
                "schema_version": "manual-test-task-list/1.0",
                "workflow_run_id": identity[0],
                "source_snapshot_id": identity[2],
                "tasks": manual_tasks,
                "input_hash": content_hash(manual_tasks),
            },
        )

    shard_count = sum(len(item["payload"].get("shards", [])) for item in executions)
    junit_tests = sum(
        int(shard.get("junit_summary", {}).get("tests", 0))
        for item in executions
        for shard in item["payload"].get("shards", [])
        if isinstance(shard, Mapping)
    )
    total_duration = sum(
        int(shard.get("duration_ms", 0))
        for item in executions
        for shard in item["payload"].get("shards", [])
        if isinstance(shard, Mapping)
    )
    coverage_values: list[float] = []
    for item in executions:
        for shard in item["payload"].get("shards", []):
            if not isinstance(shard, Mapping):
                continue
            summary = shard.get("coverage_summary")
            if not isinstance(summary, Mapping):
                continue
            percent = summary.get("statement_coverage_percent")
            if isinstance(percent, (int, float)):
                coverage_values.append(float(percent))
    statement_coverage = (
        round(sum(coverage_values) / len(coverage_values), 4) if coverage_values else None
    )
    lifecycle_evidence_bindings: list[dict[str, Any]] = []
    execution_integrity_gaps: list[str] = []
    for execution in executions:
        for shard in execution["payload"].get("shards", []):
            if not isinstance(shard, Mapping):
                continue
            if shard.get("collection_complete") is False:
                execution_integrity_gaps.append(
                    f"pytest_collection_incomplete:{shard.get('shard_id', '')}"
                )
            if (
                shard.get("lifecycle_evidence_required") is True
                and shard.get("lifecycle_evidence_present") is not True
            ):
                execution_integrity_gaps.append(
                    f"lifecycle_evidence_missing:{shard.get('shard_id', '')}"
                )
            evidence_path = shard.get("lifecycle_evidence_path")
            evidence_hash = shard.get("lifecycle_evidence_hash")
            if evidence_path is None and evidence_hash is None:
                continue
            if not isinstance(evidence_path, str) or not evidence_path.strip():
                raise ContractError("N08 lifecycle evidence path must be a non-empty string")
            if not isinstance(evidence_hash, str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", evidence_hash
            ):
                raise ContractError("N08 lifecycle evidence hash must be a SHA-256 binding")
            lifecycle_evidence_bindings.append(
                {
                    "automation_execution_hash": execution["artifact_hash"],
                    "shard_id": str(shard.get("shard_id", "")),
                    "case_ids": [str(item) for item in shard.get("case_ids", []) if str(item)],
                    "path": evidence_path,
                    "content_hash": evidence_hash,
                }
            )
    coverage_gap = None
    if not executions:
        coverage_gap = "no_automation_execution"
    elif statement_coverage is None:
        coverage_gap = "code_coverage_not_collected"
    n18_payload = {
        "schema_version": "n18-quality-signals/1.0",
        "execution_hashes": [item["artifact_hash"] for item in executions],
        "signals": {
            "automation_shards": shard_count,
            "junit_tests": junit_tests,
            "duration_ms": total_duration,
            "lifecycle_evidence_count": len(lifecycle_evidence_bindings),
            "statement_coverage_percent": statement_coverage,
            "branch_coverage_percent": None,
            "coverage_shard_count": len(coverage_values),
        },
        "gaps": [*([coverage_gap] if coverage_gap else []), *execution_integrity_gaps],
        "lifecycle_evidence_bindings": lifecycle_evidence_bindings,
        "next_node": "N09",
    }
    n18 = _artifact(
        identity,
        "N18",
        "n18-quality-signals",
        n18_payload,
        ArtifactStatus.COMPLETED_WITH_GAPS if coverage_gap else ArtifactStatus.COMPLETED,
        "quality_signal_gaps" if coverage_gap else None,
        [_binding(item, "n08-automation-execution.json") for item in executions],
    )
    store.write_artifact(n18)

    case_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    auto_case_ids: set[str] = set()
    for execution in executions:
        for shard in execution["payload"].get("shards", []):
            if not isinstance(shard, Mapping):
                continue
            case_ids = [str(item) for item in shard.get("case_ids", []) if str(item)]
            auto_case_ids.update(case_ids)
            outcome = str(shard.get("outcome", ""))
            result = "passed" if outcome == "passed" else "failed"
            for case_id in case_ids:
                case_results.append(
                    {
                        "case_id": case_id,
                        "mode": "automated",
                        "status": result,
                        "evidence_id": shard.get("shard_id"),
                    }
                )
            if outcome != "passed":
                raw_failure = f"{shard.get('stdout', '')}\n{shard.get('stderr', '')}"
                normalized = _normalize_failure_text(raw_failure)
                classification = _auto_classification(shard)
                failures.append(
                    {
                        "source": "N08",
                        "case_ids": case_ids,
                        "classification": classification,
                        "summary": normalized[:500] or outcome,
                        "detail": _failure_detail(raw_failure),
                        "fingerprint": content_hash(
                            {
                                "classification": classification,
                                "outcome": outcome,
                                "normalized": normalized,
                                "environment": execution["payload"].get(
                                    "environment_fingerprint"
                                ),
                            }
                        ),
                    }
                )
    for item in manual_tasks:
        status = str(item["status"])
        case_results.append(
            {
                "case_id": item["case_id"],
                "mode": "manual",
                "status": status,
                "evidence_id": item.get("result", {}).get("evidence", []) if item.get("result") else [],
            }
        )
        if status in {"failed", "blocked"}:
            result = item.get("result") or {}
            classification = str(result.get("classification", "needs_triage"))
            normalized = _normalize_failure_text(str(result.get("actual_result", status)))
            failures.append(
                {
                    "source": "N17",
                    "case_ids": [item["case_id"]],
                    "classification": classification,
                    "summary": normalized[:500],
                    "fingerprint": content_hash(
                        {
                            "classification": classification,
                            "normalized": normalized,
                            "environment": precheck["payload"].get("environment_fingerprint"),
                        }
                    ),
                }
            )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for failure in failures:
        grouped[failure["fingerprint"]].append(failure)
    clusters = []
    for index, fingerprint in enumerate(sorted(grouped), start=1):
        members = grouped[fingerprint]
        clusters.append(
            {
                "cluster_id": f"FAIL-{index:03d}",
                "fingerprint": fingerprint,
                "classification": members[0]["classification"],
                "case_ids": sorted(
                    {case_id for member in members for case_id in member["case_ids"]}
                ),
                "evidence_count": len(members),
                "summary": members[0]["summary"],
                "detail": members[0].get("detail"),
                "route_to": {
                    "product_defect": "N20",
                    "automation_defect": "G04",
                    "test_data": (
                        "deferred_data_construction"
                        if data_validation is not None
                        and data_validation.get("status") == "skipped_by_policy"
                        else "N16"
                    ),
                    "environment": "N10",
                    "requirement_ambiguity": "G01",
                    "needs_triage": "A19",
                }[members[0]["classification"]],
            }
        )
    n09_payload = {
        "schema_version": "n09-evidence/1.0",
        "input_bindings": {
            "execution_plan_hash": plan["artifact_hash"],
            "environment_precheck_hash": precheck["artifact_hash"],
            "automation_execution_hashes": [item["artifact_hash"] for item in executions],
            "lifecycle_evidence_bindings": lifecycle_evidence_bindings,
            "manual_execution_hash": n17.artifact_hash,
            "quality_signals_hash": n18.artifact_hash,
        },
        "case_results": case_results,
        "failure_clusters": clusters,
        "summary": {
            "result_count": len(case_results),
            "failure_count": len(failures),
            "cluster_count": len(clusters),
            "pending_manual": pending_manual,
        },
        "next_nodes": sorted({item["route_to"] for item in clusters} or {"N11"}),
    }
    n09 = _artifact(
        identity,
        "N09",
        "n09-evidence",
        n09_payload,
        ArtifactStatus.COMPLETED_WITH_GAPS if clusters or pending_manual else ArtifactStatus.COMPLETED,
        "execution_evidence_has_gaps" if clusters or pending_manual else None,
        [
            *[_binding(item, "n08-automation-execution.json") for item in executions],
            _binding(n17.to_dict(), "n17-manual-execution.json"),
            _binding(n18.to_dict(), "n18-quality-signals.json"),
        ],
    )
    store.write_artifact(n09)

    a19_min_confidence = float(policy.get("a19_min_confidence", 0.7))
    a19_payload = run_a19_failure_triage(clusters, min_confidence=a19_min_confidence)
    clusters = list(a19_payload.get("updated_clusters", clusters))
    n09_payload["failure_clusters"] = clusters
    n09_payload["next_nodes"] = sorted({item["route_to"] for item in clusters} or {"N11"})
    n09_payload["a19_triage_hash"] = a19_payload.get("triage_hash")
    n09 = _artifact(
        identity,
        "N09",
        "n09-evidence",
        n09_payload,
        ArtifactStatus.COMPLETED_WITH_GAPS if clusters or pending_manual else ArtifactStatus.COMPLETED,
        "execution_evidence_has_gaps" if clusters or pending_manual else None,
        [
            *[_binding(item, "n08-automation-execution.json") for item in executions],
            _binding(n17.to_dict(), "n17-manual-execution.json"),
            _binding(n18.to_dict(), "n18-quality-signals.json"),
        ],
    )
    store.write_artifact(n09)
    a19_status = {
        ArtifactStatus.COMPLETED.value: ArtifactStatus.COMPLETED,
        ArtifactStatus.COMPLETED_WITH_GAPS.value: ArtifactStatus.COMPLETED_WITH_GAPS,
        ArtifactStatus.NOT_APPLICABLE.value: ArtifactStatus.NOT_APPLICABLE,
    }.get(str(a19_payload.get("status")), ArtifactStatus.COMPLETED_WITH_GAPS)
    a19 = _artifact(
        identity,
        "A19",
        "a19-failure-triage",
        {
            "schema_version": "a19-failure-triage/1.0",
            "profile": a19_payload.get("profile"),
            "min_confidence": a19_payload.get("min_confidence"),
            "input_cluster_count": a19_payload.get("input_cluster_count"),
            "decisions": a19_payload.get("decisions"),
            "reclassified_count": a19_payload.get("reclassified_count"),
            "needs_human_count": a19_payload.get("needs_human_count"),
            "triage_hash": a19_payload.get("triage_hash"),
            "evidence_hash": n09.artifact_hash,
            "next_node": "N20",
        },
        a19_status,
        None if a19_status != ArtifactStatus.NOT_APPLICABLE else "no_needs_triage_clusters",
        [_binding(n09.to_dict(), "n09-evidence.json")],
    )
    store.write_artifact(a19)

    quarantine_records: list[Mapping[str, Any]] = []
    if flaky_quarantine_path is not None:
        quarantine = _read_object(flaky_quarantine_path, "flaky quarantine")
        security.assert_no_secret_values(quarantine)
        if quarantine.get("schema_version") != "flaky-quarantine/1.0":
            raise ContractError("Flaky quarantine schema_version must be flaky-quarantine/1.0")
        cases = quarantine.get("cases")
        if not isinstance(cases, list):
            raise ContractError("Flaky quarantine cases must be a list")
        quarantine_records = [item for item in cases if isinstance(item, Mapping)]
    quarantined_ids = {
        str(item.get("case_id", ""))
        for item in quarantine_records
        if item.get("status") == "quarantined" and item.get("case_id")
    }
    critical_quarantined = []
    for case_id in sorted(quarantined_ids):
        case = cases_by_id.get(case_id, {})
        priority = str(case.get("priority", "P2"))
        risk = str(case.get("risk", "medium"))
        if priority in set(policy.get("required_case_priorities", ["P0", "P1"])) or risk in {
            "high",
            "critical",
        }:
            critical_quarantined.append(case_id)

    bug_history: list[Mapping[str, Any]] = []
    if bug_history_path is not None:
        history = _read_object(bug_history_path, "bug history")
        if history.get("schema_version") != "bug-history/1.0" or not isinstance(
            history.get("bugs"), list
        ):
            raise ContractError("Bug history contract is invalid")
        bug_history = [item for item in history["bugs"] if isinstance(item, Mapping)]
    historical = {str(item.get("fingerprint", "")): item for item in bug_history}
    dedup = []
    for cluster in clusters:
        if cluster["classification"] != "product_defect":
            continue
        existing = historical.get(cluster["fingerprint"])
        if not existing:
            disposition = "create_new"
        elif existing.get("status") in {"resolved", "closed"}:
            disposition = "reopen"
        else:
            disposition = "link_existing"
        dedup.append(
            {
                "cluster_id": cluster["cluster_id"],
                "fingerprint": cluster["fingerprint"],
                "disposition": disposition,
                "existing_bug_id": existing.get("bug_id") if existing else None,
            }
        )
    n20_payload = {
        "schema_version": "n20-defect-dedup/1.0",
        "evidence_hash": n09.artifact_hash,
        "history_hash": content_hash(bug_history),
        "decisions": dedup,
        "next_node": "N11",
    }
    n20 = _artifact(
        identity,
        "N20",
        "n20-defect-dedup",
        n20_payload,
        evidence=[_binding(n09.to_dict(), "n09-evidence.json")],
    )
    store.write_artifact(n20)

    deferred_actions = {
        "deferred_frontend",
        "deferred_data_construction",
        "deferred_by_policy",
    }
    actionable = [
        item
        for item in actions
        if item.get("action") != "skip"
        and item.get("action") not in deferred_actions
        and str(item.get("case_id", "")) not in policy_deferred_case_ids
    ]
    executed_ids = {
        str(item["case_id"])
        for item in case_results
        if item.get("status") in TERMINAL_TEST_RESULTS
    }
    passed_ids = {
        str(item["case_id"]) for item in case_results if item.get("status") == "passed"
    }
    failed_ids = {
        str(item["case_id"])
        for item in case_results
        if item.get("status") in {"failed", "blocked"}
    }
    non_required_ids = {
        str(item["case_id"])
        for item in actions
        if item.get("action") == "skip" or item.get("action") in deferred_actions
    }
    non_required_ids.update(policy_deferred_case_ids)
    pending_ids = {str(item["case_id"]) for item in actionable} - executed_ids
    reasons: list[str] = []
    warnings: list[str] = []
    deferred_data_clusters = [
        item for item in clusters if item["route_to"] == "deferred_data_construction"
    ]
    blocking_clusters = [
        item
        for item in clusters
        if item["classification"] in {
            "product_defect", "automation_defect", "test_data", "environment"
        }
        and item["route_to"] != "deferred_data_construction"
    ]
    triage_clusters = [item for item in clusters if item["classification"] in {
        "needs_triage", "requirement_ambiguity"
    }]
    if retry_allowed:
        reasons.append("Environment retry is required before a final quality decision")
    if blocking_clusters:
        reasons.append(f"{len(blocking_clusters)} classified failure cluster(s) block quality")
    if triage_clusters:
        reasons.append(f"{len(triage_clusters)} failure cluster(s) still require triage")
    if deferred_data_clusters:
        reasons.append(
            f"{len(deferred_data_clusters)} test-data cluster(s) were deferred by the active policy"
        )
    if pending_ids:
        reasons.append(f"{len(pending_ids)} required Case(s) have no completed result")
    if not executed_ids:
        reasons.append("No required Case has completed execution")
    if n18_payload["gaps"]:
        warnings.extend(n18_payload["gaps"])
    production_isolated = precheck["payload"].get("production_isolation") is True
    if require_production_isolation and not production_isolated:
        reasons.append("Production-isolated environment evidence is required for release")
        warnings.append("environment_not_production_isolated")
    if any(item.get("action") == "skip" for item in actions):
        warnings.append("Execution plan contains skipped Cases")
    if non_required_ids - {
        str(item["case_id"]) for item in actions if item.get("action") == "skip"
    }:
        warnings.append("Execution plan contains policy-deferred Cases")
    partial_case_ids = plan["payload"].get("scope_summary", {}).get("partial_case_ids", [])
    if partial_case_ids:
        warnings.append(f"partial_case_coverage:{','.join(map(str, partial_case_ids))}")
    if deferred_data_case_ids:
        reasons.append(
            f"{len(deferred_data_case_ids)} Case(s) await a registered test-data construction capability"
        )
        warnings.append("test_data_construction_deferred")
    if deferred_frontend_case_ids:
        warnings.append("frontend_scope_deferred")
    if quarantined_ids:
        warnings.append(f"{len(quarantined_ids)} Case(s) are flaky-quarantined")
        for case_id in sorted(quarantined_ids):
            # Quarantined Cases remain coverage gaps and cannot silently pass.
            pending_ids.add(case_id)
            executed_ids.discard(case_id)
            passed_ids.discard(case_id)
    if critical_quarantined and policy.get("quarantined_critical_blocks_release", True):
        reasons.append(
            f"{len(critical_quarantined)} required or high-risk Case(s) are flaky-quarantined"
        )

    if (
        retry_allowed
        or blocking_clusters
        or (
            critical_quarantined
            and policy.get("quarantined_critical_blocks_release", True)
        )
    ):
        decision = "blocked"
    elif (
        triage_clusters
        or deferred_data_clusters
        or pending_ids
        or not executed_ids
        or policy_deferred_case_ids
        or (require_production_isolation and not production_isolated)
    ):
        decision = "inconclusive"
    elif warnings:
        decision = "passed_with_warning"
    else:
        decision = "passed"
    release_disposition = "eligible" if decision in {"passed", "passed_with_warning"} else "pending"
    metrics = {
        "scope_total": len(actions),
        "planned": len(actionable),
        "executed": len(executed_ids),
        "passed": len(passed_ids),
        "failed": len(failed_ids),
        "pending": len(pending_ids),
        "skipped": sum(item.get("action") == "skip" for item in actions),
        "deferred": len(
            {
                str(item["case_id"])
                for item in actions
                if item.get("action") in deferred_actions
            }
            | policy_deferred_case_ids
        ),
        "quarantined": len(quarantined_ids),
    }
    n11_payload = {
        "schema_version": "n11-quality-decision/1.0",
        "policy_version": str(policy.get("policy_version", "quality-policy-v1")),
        "policy_hash": content_hash(policy),
        "input_bindings": {
            "execution_plan_hash": plan["artifact_hash"],
            "compiled_cases_hash": compiled["artifact_hash"],
            "environment_precheck_hash": precheck["artifact_hash"],
            "retry_budget_hash": n10.artifact_hash,
            "evidence_hash": n09.artifact_hash,
            "defect_dedup_hash": n20.artifact_hash,
            "failure_triage_hash": a19.artifact_hash,
            "test_data_validation_hash": (
                data_validation["artifact_hash"] if data_validation is not None else None
            ),
        },
        "flaky_quarantine": {
            "case_ids": sorted(quarantined_ids),
            "critical_case_ids": list(critical_quarantined),
        },
        "decision": decision,
        "release_disposition": release_disposition,
        "environment": {
            "class": str(precheck["payload"].get("environment_class", "unspecified")),
            "production_isolation": production_isolated,
        },
        "reasons": reasons,
        "warnings": sorted(set(warnings)),
        "metrics": metrics,
        "next_node": "N12",
    }
    n11_status = {
        "passed": ArtifactStatus.COMPLETED,
        "passed_with_warning": ArtifactStatus.COMPLETED_WITH_GAPS,
        "blocked": ArtifactStatus.BLOCKED,
        "inconclusive": ArtifactStatus.INCONCLUSIVE,
    }[decision]
    n11 = _artifact(
        identity,
        "N11",
        "n11-quality-decision",
        n11_payload,
        n11_status,
        None if decision == "passed" else f"quality_{decision}",
        [
            _binding(n09.to_dict(), "n09-evidence.json"),
            _binding(n20.to_dict(), "n20-defect-dedup.json"),
        ],
    )
    store.write_artifact(n11)

    report = {
        "schema_version": "server-quality-report/1.0",
        "workflow_run_id": identity[0],
        "source_snapshot_id": identity[2],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "decision": decision,
        "release_disposition": release_disposition,
        "environment": {
            "class": str(precheck["payload"].get("environment_class", "unspecified")),
            "production_isolation": production_isolated,
        },
        "metrics": metrics,
        "reasons": reasons,
        "warnings": sorted(set(warnings)),
        "failure_clusters": clusters,
        "defect_dedup": dedup,
        "artifact_bindings": {
            "n09": n09.artifact_hash,
            "n11": n11.artifact_hash,
            "n17": n17.artifact_hash,
            "n18": n18.artifact_hash,
            "n20": n20.artifact_hash,
            "a19": a19.artifact_hash,
        },
        "flaky_quarantine": {
            "case_ids": sorted(quarantined_ids),
            "critical_case_ids": list(critical_quarantined),
        },
    }
    report["report_hash"] = content_hash(report)
    n12_payload = {
        "schema_version": "n12-quality-report/1.0",
        "quality_decision_hash": n11.artifact_hash,
        "report_hash": report["report_hash"],
        "decision": decision,
        "release_disposition": release_disposition,
        "published_outputs": [
            "server-quality-report.json",
            "server-quality-report.md",
            "server-quality-report.html",
        ],
        "bug_draft_count": sum(item["disposition"] == "create_new" for item in dedup),
        "next_node": "N13",
    }
    n12 = _artifact(
        identity,
        "N12",
        "n12-quality-report",
        n12_payload,
        ArtifactStatus.COMPLETED,
        evidence=[_binding(n11.to_dict(), "n11-quality-decision.json")],
    )
    store.write_artifact(n12)
    store.write_json("server-quality-report.json", report)
    store.write_text("server-quality-report.md", _render_report_markdown(report))
    store.write_text("server-quality-report.html", _render_report_html(report))
    store.write_json(
        "bug-drafts.json",
        {
            "schema_version": "bug-drafts/1.0",
            "workflow_run_id": identity[0],
            "drafts": [
                {
                    "cluster_id": item["cluster_id"],
                    "fingerprint": item["fingerprint"],
                    "status": "draft",
                }
                for item in dedup
                if item["disposition"] == "create_new"
            ],
        },
    )

    audit_artifacts: dict[str, ArtifactEnvelope] = {}
    for node_id, artifact_id, payload, reason in (
        (
            "N19",
            "n19-quality-waiver",
            {"schema_version": "n19-quality-waiver/1.0", "decision": "not_requested"},
            "quality_waiver_not_requested",
        ),
        (
            "N23",
            "n23-post-release-verification",
            {"schema_version": "n23-post-release-verification/1.0", "decision": "not_authorized"},
            "post_release_not_authorized",
        ),
    ):
        audit_artifact = _artifact(
            identity,
            node_id,
            artifact_id,
            payload,
            ArtifactStatus.SKIPPED_BY_POLICY,
            reason,
        )
        store.write_artifact(audit_artifact)
        audit_artifacts[node_id] = audit_artifact
    n13 = _artifact(
        identity,
        "N13",
        "n13-feedback-capture",
        {
            "schema_version": "n13-feedback-capture/1.0",
            "status": "ready_for_feedback",
            "quality_report_hash": n12.artifact_hash,
        },
    )
    store.write_artifact(n13)

    result = {
        "schema_version": "server-quality-tail-result/1.0",
        "workflow_run_id": identity[0],
        "decision": decision,
        "release_disposition": release_disposition,
        "metrics": metrics,
        "quality_decision_hash": n11.artifact_hash,
        "quality_report_hash": n12.artifact_hash,
        "report_hash": report["report_hash"],
        "stopped_at": "N12",
        "current_node": "N17" if metrics["pending"] else "N13",
        "reached_nodes": ["A19", "N12", "N13", "N19", "N23"],
        "external_adapter_dispositions": {
            "mr": "not_requested_no_code_commit",
            "bug": (
                "draft_ready_not_sent"
                if any(item["disposition"] == "create_new" for item in dedup)
                else ("dedup_decision_ready_not_sent" if dedup else "not_applicable_no_product_defect")
            ),
            "release": "not_authorized_quality_not_passed",
        },
    }
    result["result_hash"] = content_hash(result)
    store.write_json("server-quality-tail-result.json", result)
    if run_manifest_path is not None and run_manifest is not None:
        run_manifest["server_quality"] = {
            "status": decision,
            "release_disposition": release_disposition,
            "metrics": metrics,
            "execution_environment": str(
                precheck["payload"].get("environment_class", "unspecified")
            ),
            "production_isolation": production_isolated,
            "n11_artifact_hash": n11.artifact_hash,
            "n12_artifact_hash": n12.artifact_hash,
            "n13_artifact_hash": n13.artifact_hash,
            "n19_artifact_hash": audit_artifacts["N19"].artifact_hash,
            "n23_artifact_hash": audit_artifacts["N23"].artifact_hash,
            "report_hash": report["report_hash"],
            "result_hash": result["result_hash"],
            "next_node": result["current_node"],
        }
        run_manifest["current_node"] = result["current_node"]
        run_manifest["next_gate"] = result["current_node"]
        ArtifactStore(run_manifest_path.parent).write_json(run_manifest_path.name, run_manifest)
    return result
