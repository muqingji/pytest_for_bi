"""Deterministic existing-asset discovery evidence for the A22 component."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
import json
from pathlib import Path

from .contracts import content_hash
from .data_integrity import (
    integrity_evidence_valid,
    required_validity_contract,
    run_bug_finder_integrity_probes,
)


Verifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _required_resources(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = case.get("resource_requirements")
    test_data = case.get("test_data")
    nested = test_data.get("resource_requirements") if isinstance(test_data, Mapping) else None
    value = direct if isinstance(direct, list) else nested
    return [item for item in value or [] if isinstance(item, Mapping)]


def discover_existing_assets(
    cases: Sequence[Mapping[str, Any]],
    inventory: Sequence[Mapping[str, Any]],
    *,
    verifier: Verifier,
    environment: str = "112",
) -> dict[str, Any]:
    """Verify exact-lineage candidates; fuzzy names never authorize reuse."""

    candidates: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("id") or "").strip()
        requirements = _required_resources(case)
        selectors = [
            (
                str(requirement.get("resource_key") or "").strip(),
                str(requirement.get("resource_type") or "").strip(),
            )
            for requirement in requirements
        ]
        if not selectors:
            selectors = sorted({
                (
                    str(item.get("resource_key") or item.get("key") or "").strip(),
                    str(item.get("resource_type") or "").strip(),
                )
                for item in inventory
                if isinstance(item, Mapping)
                and str(item.get("case_id") or "").strip() == case_id
            })
        for key, resource_type in selectors:
            matches = [
                item for item in inventory
                if isinstance(item, Mapping)
                and str(item.get("case_id") or "").strip() == case_id
                and str(item.get("resource_key") or item.get("key") or "").strip() == key
                and str(item.get("resource_type") or "").strip() == resource_type
                and str(item.get("resource_id") or "").strip()
            ]
            for item in matches:
                resource_id = str(item.get("resource_id") or "").strip()
                base = {
                    "case_id": case_id,
                    "resource_key": key,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "display_name": str(item.get("display_name") or "").strip(),
                    "asset_folder_name": str(
                        item.get("asset_folder_name")
                        or case.get("requirement_name")
                        or case.get("title")
                        or case_id
                    ).strip(),
                    "match_basis": "exact_case_id_resource_key_type",
                }
                try:
                    verified = dict(verifier(base))
                except Exception as error:
                    candidates.append({**base, "decision": "rejected", "reason_code": "live_verification_failed", "detail": str(error)[:240]})
                    continue
                readback = verified.get("configuration")
                baseline = verified.get("baseline")
                readback_ok = verified.get("live_readback_status") == "succeeded" and isinstance(readback, Mapping)
                baseline_ok = verified.get("baseline_status") in {"passed", "target_condition_observed"} and isinstance(baseline, Mapping)
                evidence = {
                    "live_readback_status": verified.get("live_readback_status"),
                    "baseline_status": verified.get("baseline_status"),
                    "configuration_hash": content_hash(readback) if isinstance(readback, Mapping) else "",
                    "baseline_response_hash": content_hash(baseline) if isinstance(baseline, Mapping) else "",
                    "readback_operation": str(verified.get("readback_operation") or ""),
                    "baseline_operation": str(verified.get("baseline_operation") or ""),
                    "trace_ids": [str(item) for item in verified.get("trace_ids", []) if str(item)],
                }
                readback_operation = str(verified.get("readback_operation") or "")
                baseline_operation = str(verified.get("baseline_operation") or "")
                discovery_step = {
                    "name": f"discover existing {key}",
                    "request": {"api": readback_operation, "json": dict(verified.get("readback_request") or {})},
                    "expect": {"status_code": 200, "json_path": {"Result.FailureCode": 0}},
                }
                readiness_step = {
                    "name": f"verify existing {key} baseline",
                    "request": {"api": baseline_operation, "json": dict(verified.get("baseline_request") or {})},
                    "expect": {"status_code": 200, "json_path": {"Result.FailureCode": 0}},
                }
                integrity = verified.get("integrity_evidence")
                integrity_required = resource_type == "stat_chart"
                integrity_ok = not integrity_required or integrity_evidence_valid(integrity)
                if isinstance(integrity, Mapping):
                    evidence["integrity_evidence"] = dict(integrity)
                decision = "reusable" if readback_ok and baseline_ok and integrity_ok else "rejected"
                candidates.append({
                    **base,
                    "decision": decision,
                    "reason_code": "verified" if decision == "reusable" else (
                        "integrity_not_proven" if readback_ok and baseline_ok and not integrity_ok
                        else "readback_or_baseline_not_proven"
                    ),
                    "existing_asset_evidence": evidence,
                    "discovery": discovery_step,
                    "readiness": [readiness_step],
                    "validity_contract": required_validity_contract(resource_type),
                })
    packet = {
        "schema_version": "a22-existing-asset-discovery/1.0",
        "environment": environment,
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "matching_policy": "exact_lineage_and_live_verification",
        "candidates": candidates,
    }
    packet["discovery_hash"] = content_hash(packet)
    return packet


def reusable_candidates(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in packet.get("candidates", []) if isinstance(item, Mapping) and item.get("decision") == "reusable"]


_READBACK_OPERATIONS = {
    "stat_chart": "fs_bi_stat.stat_edit.get_chart_config",
    "aggregate_metric": "fs_bi_stat.agg_rule.query_agg_rule_by_field_id",
    "calculated_metric": "fs_bi_stat.agg_rule.query_agg_rule_by_field_id",
    "custom_dimension": "fs_bi_stat.custom_dimension.get_custom_dimension",
}


def discover_live_112_assets(
    cases: Sequence[Mapping[str, Any]],
    inventory_path: Path,
    *,
    repo_root: Path,
    bug_finder_root: Path | None = None,
) -> dict[str, Any]:
    """Run the A22 component's approved live read-only verification."""

    from framework.api.catalog import HttpApiCatalog
    from framework.auth import authenticate_fxiaoke, validate_credential_source
    from framework.clients.database import DatabaseClient
    from framework.clients.http import HttpClient
    from framework.clients.rpc import RpcClient
    from framework.config.environment import EnvironmentConfig
    from framework.core.runner import CaseRunner

    value = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory = value.get("assets", []) if isinstance(value, Mapping) else []
    if not isinstance(inventory, list):
        inventory = []
    validate_credential_source("112")
    env = EnvironmentConfig.load("112", root=repo_root)
    http = HttpClient(
        base_url=env.get("http.base_url", ""),
        headers=env.get("http.headers", {}),
        timeout=env.get("http.timeout", 60.0),
        verify=env.get("http.verify", True),
    )
    authenticate_fxiaoke(env, http)
    runner = CaseRunner(
        env,
        http,
        RpcClient(env.get("rpc", {}), http),
        DatabaseClient(env.get("databases", {})),
        HttpApiCatalog.load(repo_root / "idl" / "http"),
    )

    def verify(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
        resource_type = str(candidate.get("resource_type") or "")
        resource_id = str(candidate.get("resource_id") or "")
        operation = _READBACK_OPERATIONS.get(resource_type)
        if not operation:
            return {"live_readback_status": "unsupported", "baseline_status": "not_run"}
        if resource_type == "stat_chart":
            readback_body = {"id": resource_id, "isView": 1, "type": "edit", "querySource": "UNKNOWN", "cacheTime": 0, "refresh": 1}
            baseline_operation = "fs_bi_stat.stat_base.chart_query"
            baseline_body = {"id": resource_id, "isView": 1, "pageNumber": 1, "pageSize": 1}
        else:
            readback_body = {"fieldId": resource_id}
            baseline_operation = operation
            baseline_body = dict(readback_body)
        readback = runner.http_api.call(operation, body=readback_body).body
        baseline = runner.http_api.call(baseline_operation, body=baseline_body).body

        integrity_evidence = None
        probes = next((
            item.get("integrity_probes") for item in inventory
            if isinstance(item, Mapping)
            and str(item.get("resource_id") or "") == resource_id
        ), None)
        if resource_type == "stat_chart" and isinstance(probes, list) and bug_finder_root is not None:
            integrity_evidence = run_bug_finder_integrity_probes(
                [item for item in probes if isinstance(item, Mapping)],
                bug_finder_root=bug_finder_root,
            )

        def succeeded(body: Any) -> bool:
            return isinstance(body, Mapping) and int((body.get("Result") or {}).get("FailureCode", -1)) == 0

        return {
            "live_readback_status": "succeeded" if succeeded(readback) else "failed",
            "baseline_status": "passed" if succeeded(baseline) else "failed",
            "configuration": readback if isinstance(readback, Mapping) else {},
            "baseline": baseline if isinstance(baseline, Mapping) else {},
            "readback_operation": operation,
            "baseline_operation": baseline_operation,
            "trace_ids": [],
            "readback_request": readback_body,
            "baseline_request": baseline_body,
            "integrity_evidence": integrity_evidence,
        }

    return discover_existing_assets(cases, inventory, verifier=verify, environment="112")
