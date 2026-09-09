"""Read-only external evidence adapter for A22 test-data validity checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path
import subprocess
import re
from typing import Any

from .contracts import content_hash
from .errors import ContractError, SecurityPolicyError


INTEGRITY_CONTRACT = "test-data-integrity-evidence/1.0"
REQUIRED_CHART_CHECKS = frozenset({
    "source_data", "warehouse_dimension", "warehouse_aggregation", "chart_topology"
})
_DENIED_TOKENS = frozenset({
    "insert", "update", "delete", "drop", "alter", "truncate", "create", "replace",
    "grant", "revoke", "mutation", "command",
})


Runner = Callable[..., subprocess.CompletedProcess[str]]


def required_validity_contract(resource_type: str) -> dict[str, Any]:
    """Return the deterministic post-create checks A22 must request."""

    checks = ["configuration_readback", "baseline_query"]
    if resource_type in {"stat_chart", "report", "pivot_table", "joined_report"}:
        checks = [
            "configuration_readback", "source_data", "chart_topology",
            "warehouse_dimension", "warehouse_aggregation", "baseline_query",
        ]
    return {
        "schema_version": "test-data-validity-contract/1.0",
        "required_checks": checks,
        "decision_policy": "all_required_checks_pass",
        "failure_action": "reject_asset_and_reconstruct_or_diagnose",
    }


def validate_validity_contract(value: Any, *, resource_type: str, path: str) -> None:
    expected = required_validity_contract(resource_type)
    if not isinstance(value, Mapping):
        raise ContractError(f"{path}.validity_contract is required")
    if value.get("schema_version") != expected["schema_version"]:
        raise ContractError(f"{path}.validity_contract schema_version is invalid")
    checks = value.get("required_checks")
    if not isinstance(checks, list) or set(map(str, checks)) != set(expected["required_checks"]):
        raise SecurityPolicyError(f"{path}.validity_contract required checks are incomplete")
    if value.get("decision_policy") != "all_required_checks_pass":
        raise SecurityPolicyError(f"{path}.validity_contract must fail closed")


def _validate_probe(probe: Mapping[str, Any], index: int) -> tuple[str, list[str], int]:
    check = str(probe.get("check") or "").strip()
    argv = probe.get("argv")
    minimum_rows = probe.get("minimum_rows", 1)
    if check not in REQUIRED_CHART_CHECKS:
        raise ContractError(f"integrity_probes[{index}].check is unsupported")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise ContractError(f"integrity_probes[{index}].argv must be a non-empty string list")
    if argv[0] != "idp":
        raise SecurityPolicyError(f"integrity_probes[{index}] must use the fxops_query idp contract")
    if len(argv) < 3 or argv[1] != "query":
        raise SecurityPolicyError(f"integrity_probes[{index}] must use an idp query")
    if "-j" not in argv and "--json" not in argv:
        raise ContractError(f"integrity_probes[{index}] must request structured JSON")
    lowered = {token.casefold().strip(";,()") for token in argv}
    words = set(re.findall(r"[a-z]+", " ".join(argv).casefold()))
    if words & _DENIED_TOKENS:
        raise SecurityPolicyError(f"integrity_probes[{index}] is not read-only")
    if not any(token in {"query", "show", "get"} for token in lowered):
        raise SecurityPolicyError(f"integrity_probes[{index}] has no approved read operation")
    try:
        sql = argv[argv.index("--sql") + 1]
    except (ValueError, IndexError) as error:
        raise ContractError(f"integrity_probes[{index}] requires bounded SQL") from error
    normalized_sql = sql.casefold()
    if not normalized_sql.lstrip().startswith("select ") or " limit " not in normalized_sql:
        raise SecurityPolicyError(f"integrity_probes[{index}] SQL must be SELECT with LIMIT")
    if not any(marker in normalized_sql for marker in ("tenant_id", "tenantid", " ei", " ea")):
        raise SecurityPolicyError(f"integrity_probes[{index}] SQL requires an explicit tenant filter")
    if not isinstance(minimum_rows, int) or minimum_rows < 0:
        raise ContractError(f"integrity_probes[{index}].minimum_rows is invalid")
    return check, list(argv), minimum_rows


def validate_integrity_probe_plan(value: Any, *, path: str) -> None:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{path}.integrity_probes are required")
    checks = {
        _validate_probe(item, index)[0]
        for index, item in enumerate(value)
        if isinstance(item, Mapping)
    }
    if len(checks) != len(value) or not REQUIRED_CHART_CHECKS <= checks:
        raise SecurityPolicyError(f"{path}.integrity_probes do not cover all BI data layers")


def run_bug_finder_integrity_probes(
    probes: Sequence[Mapping[str, Any]], *, bug_finder_root: Path,
    runner: Runner = subprocess.run, timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Invoke bug-finder's registered fxops_query capability and freeze evidence."""

    cli = bug_finder_root / ".agents/skills/fx-ops/scripts/fx_ops_cli.py"
    if not cli.is_file():
        raise ContractError("bug-finder fx-ops public CLI is unavailable")
    results: list[dict[str, Any]] = []
    warehouse_view_id = ""
    materialized: bool | None = None
    ordered = sorted(probes, key=lambda item: 0 if item.get("check") == "chart_topology" else 1)
    for index, probe in enumerate(ordered):
        check, argv, minimum_rows = _validate_probe(probe, index)
        argv = [item.replace("__CHART_WAREHOUSE_VIEW_ID__", warehouse_view_id) for item in argv]
        command = ["uv", "run", "--no-sync", "python", str(cli), "run", "fxops_query", "--", *argv]
        completed = runner(
            command, cwd=bug_finder_root, text=True, capture_output=True,
            timeout=timeout_seconds, check=False,
        )
        payload: Any = None
        try:
            payload = json.loads(completed.stdout) if completed.stdout.strip() else None
        except json.JSONDecodeError:
            payload = None
        rows = payload.get("rows", []) if isinstance(payload, Mapping) else []
        if check == "chart_topology" and rows and isinstance(rows[0], Mapping):
            warehouse_view_id = str(rows[0].get("stat_view_unique_key") or "")
            latest_agg_time = str(rows[0].get("latest_agg_time") or "").strip()
            materialized = latest_agg_time not in {"", "0", "None", "null"}
        not_applicable = (
            check in {"warehouse_dimension", "warehouse_aggregation"}
            and materialized is False
        )
        passed = (
            completed.returncode == 0 and isinstance(payload, Mapping)
            and payload.get("ok") is True and isinstance(rows, list)
            and (len(rows) >= minimum_rows or not_applicable)
        )
        results.append({
            "check": check,
            "status": "not_applicable" if passed and not_applicable else ("passed" if passed else "failed"),
            "row_count": len(rows) if isinstance(rows, list) else 0,
            "minimum_rows": minimum_rows,
            "response_hash": content_hash(payload) if isinstance(payload, Mapping) else "",
            "error": "" if passed else (completed.stderr.strip()[:240] or "query evidence did not satisfy expectation"),
        })
    observed = {
        item["check"] for item in results
        if item["status"] in {"passed", "not_applicable"}
    }
    packet = {
        "schema_version": INTEGRITY_CONTRACT,
        "provider": "bug-finder/fxops_query",
        "required_checks": sorted(REQUIRED_CHART_CHECKS),
        "checks": results,
        "valid": REQUIRED_CHART_CHECKS <= observed,
    }
    packet["evidence_hash"] = content_hash(packet)
    return packet


def integrity_evidence_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or value.get("schema_version") != INTEGRITY_CONTRACT:
        return False
    expected_hash = content_hash({key: item for key, item in value.items() if key != "evidence_hash"})
    checks = value.get("checks", [])
    passed = {
        str(item.get("check")) for item in checks
        if isinstance(item, Mapping) and item.get("status") in {"passed", "not_applicable"}
    }
    return (
        value.get("valid") is True
        and str(value.get("evidence_hash") or "") == expected_hash
        and REQUIRED_CHART_CHECKS <= passed
    )
