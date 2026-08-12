#!/usr/bin/env python3
"""Project the complete reviewed Case scope into an honest backend execution plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_agents.contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
)
from qa_agents.case_compiler import project_capability_atoms


FRONTEND_CASES = {"PC-002-E2E", "PC-006-E2E", "PC-007-E2E"}
CAPABILITIES = {
    "aggregate": {
        "allowed_layers": ["backend"],
        "label": "聚合指标",
        "dataset": "result_set_metric_types",
        "data_intent": "metric.aggregate_result_set_filter.detail_unsupported",
        "recipe_id": "aggregate-metric-result-set-filter",
    },
    "calculated": {
        "allowed_layers": ["backend"],
        "label": "计算指标",
        "dataset": "calculated_result_filter_metric",
        "data_intent": "metric.calculated_result_set_filter.detail_unsupported",
        "recipe_id": "calculated-metric-result-set-filter",
    },
}


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("artifact_hash") != artifact_hash_from_mapping(value):
        raise ValueError(f"invalid Artifact hash: {path}")
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--data-validation", type=Path, required=True)
    parser.add_argument("--executed-case-id", action="append", default=[])
    parser.add_argument("--executed-atom-id", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    compiled = _read(args.compiled)
    data_validation = _read(args.data_validation)
    cases = compiled["payload"]["compiled_cases"]
    atomic = project_capability_atoms(cases, CAPABILITIES)
    case_ids = [str(item["id"]) for item in cases]
    executed = set(args.executed_case_id)
    executed_atoms = set(args.executed_atom_id)
    unknown = sorted(executed - set(case_ids))
    if unknown:
        raise ValueError(f"executed Case IDs are outside N25: {unknown}")
    atom_ids = {str(item["id"]) for item in atomic["atoms"]}
    unknown_atoms = sorted(executed_atoms - atom_ids)
    if unknown_atoms:
        raise ValueError(f"executed atom IDs are outside N25 projection: {unknown_atoms}")

    actions = []
    deferred = []
    for case_id in case_ids:
        if case_id in executed:
            action = "generate_new"
            reason = "registered_backend_capability_partially_executed"
        elif case_id in FRONTEND_CASES:
            action = "deferred_frontend"
            reason = "frontend_scope_excluded_by_user"
        else:
            action = "deferred_data_construction"
            reason = "data_capability_not_registered"
        actions.append({"case_id": case_id, "action": action, "reason_code": reason})
        if action.startswith("deferred_"):
            deferred.append({"case_id": case_id, "route": action, "reason_code": reason})

    identity = (
        compiled["workflow_run_id"], compiled["workflow_mode"], compiled["source_snapshot_id"]
    )
    plan = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="n15-execution-plan",
        source_snapshot_id=identity[2],
        producer=Producer("N15", runtime="deterministic"),
        payload={
            "schema_version": "execution-plan/1.0",
            "actions": actions,
            "scope_summary": {
                "total": len(case_ids),
                "executable": len(executed),
                "deferred_data": sum(item["action"] == "deferred_data_construction" for item in actions),
                "deferred_frontend": sum(item["action"] == "deferred_frontend" for item in actions),
                "partial_case_ids": sorted(executed),
                "atomic_scope_total": len(atom_ids),
                "executable_atom_ids": sorted(
                    item["id"]
                    for item in atomic["atoms"]
                    if item["capability_status"] == "registered"
                ),
                "executed_atom_ids": sorted(executed_atoms),
            },
            "data_validation_hash": data_validation["artifact_hash"],
        },
        evidence_refs=(
            EvidenceRef("artifact", compiled["artifact_id"], str(args.compiled), compiled["artifact_hash"]),
            EvidenceRef("artifact", data_validation["artifact_id"], str(args.data_validation), data_validation["artifact_hash"]),
        ),
    )
    validation_payload = dict(data_validation["payload"])
    validation_payload.update(
        {
            "valid": True,
            "decision": "partial_capability_routing",
            "next_node": "N07",
            "executable_case_ids": sorted(executed),
            "executable_atom_ids": plan.payload["scope_summary"]["executable_atom_ids"],
            "executed_atom_ids": sorted(executed_atoms),
            "atomic_projection_schema_version": atomic["schema_version"],
            "deferred_cases": deferred,
            "full_scope_case_count": len(case_ids),
        }
    )
    routed_validation = ArtifactEnvelope(
        workflow_run_id=identity[0],
        workflow_mode=identity[1],
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id=identity[2],
        producer=Producer("N27", runtime="deterministic"),
        payload=validation_payload,
        status=ArtifactStatus.COMPLETED_WITH_GAPS,
        reason_code="test_data_capability_partial",
        evidence_refs=(
            EvidenceRef("artifact", data_validation["artifact_id"], str(args.data_validation), data_validation["artifact_hash"]),
        ),
    )
    _write(args.output / "artifacts/n15-execution-plan.json", plan.to_dict())
    _write(args.output / "artifacts/n25-capability-atoms.json", atomic)
    _write(args.output / "artifacts/n27-test-data-plan-validation.json", routed_validation.to_dict())
    _write(
        args.output / "full-scope-summary.json",
        {
            "schema_version": "backend-full-scope/1.0",
            **plan.payload["scope_summary"],
            "case_ids": case_ids,
            "executed_case_ids": sorted(executed),
            "executed_atom_ids": sorted(executed_atoms),
            "n15_artifact_hash": plan.artifact_hash,
            "n27_artifact_hash": routed_validation.artifact_hash,
        },
    )


if __name__ == "__main__":
    main()
