#!/usr/bin/env python3
"""Build the executable A22 plan and N27 validation without an N28 node."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, EvidenceRef, Producer
from qa_agents.data_planning import compile_declared_a22_plan, prepare_autonomous_test_data_plan
from qa_agents.storage import ArtifactStore
from qa_agents.test_data import validate_test_data_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--environment", default="112")
    parser.add_argument("--namespace")
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--declared-plan", type=Path)
    parser.add_argument(
        "--defer-case",
        action="append",
        default=[],
        help="Defer an executable Case as CASE_ID=REASON_CODE for partial routing",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    namespace = args.namespace or f"qa-a22-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    if args.declared_plan:
        declared = json.loads(args.declared_plan.read_text(encoding="utf-8"))
        catalog = json.loads((root / "qa-agents/knowledge/bi-data-capability-catalog.json").read_text(encoding="utf-8"))
        policy = json.loads((root / "qa-agents/policies/test-data-policy.json").read_text(encoding="utf-8"))
        n25_path = args.artifact_dir / "artifacts/n25-compiled-test-cases.json"
        compiled_cases = []
        if n25_path.is_file():
            n25 = json.loads(n25_path.read_text(encoding="utf-8"))
            n25_payload = n25.get("payload", {})
            compiled_cases = n25_payload.get("compiled_cases", n25_payload.get("child_cases", []))
        plan = compile_declared_a22_plan(
            declared["payload"], catalog, environment=args.environment, namespace=namespace,
            compiled_cases=[item for item in compiled_cases if isinstance(item, dict)],
        )
        deferred_cases = []
        deferred_case_ids = set()
        for raw_item in args.defer_case:
            case_id, separator, reason_code = raw_item.partition("=")
            case_id = case_id.strip()
            if not separator or not case_id or not reason_code.strip():
                raise SystemExit("--defer-case must use CASE_ID=REASON_CODE")
            if not any(case.get("case_id") == case_id for case in plan["case_plans"]):
                raise SystemExit(f"Cannot defer unknown A22 Case: {case_id}")
            deferred_case_ids.add(case_id)
            deferred_cases.append({
                "case_id": case_id,
                "reason_code": reason_code.strip(),
                "route_to": "capability_catalog",
            })
        for case_plan in plan["case_plans"]:
            if case_plan["case_id"] in deferred_case_ids:
                case_plan["requires_data_construction"] = False
                case_plan["required_scene"] = ""
                case_plan["resources"] = []
                case_plan["recipe_refs"] = []
                case_plan["deferred_reason"] = next(
                    item["reason_code"] for item in deferred_cases
                    if item["case_id"] == case_plan["case_id"]
                )
        plan["deferred_cases"] = deferred_cases
        plan["unsupported_requirements"] = [
            item for item in plan.get("unsupported_requirements", [])
            if isinstance(item, dict) and item.get("case_id") not in deferred_case_ids
        ]
        plan["ready_for_execution"] = not plan["unsupported_requirements"] and all(
            (
                bool(resource.get("discovery"))
                and bool(resource.get("readiness"))
                and bool(resource.get("existing_asset_evidence"))
            )
            if resource.get("lifecycle_mode") == "existing_read_only"
            else bool(resource.get("residue_checks"))
            for case in plan["case_plans"]
            for resource in case["resources"]
        )
        identity = (
            str(declared["workflow_run_id"]), str(declared["workflow_mode"]),
            str(declared["source_snapshot_id"]),
        )
        executable_case_ids = [
            str(case["case_id"]) for case in plan["case_plans"]
            if str(case["case_id"]) not in deferred_case_ids
        ]
        partial_routing = bool(deferred_cases)
        a22 = ArtifactEnvelope(
            workflow_run_id=identity[0], workflow_mode=identity[1],
            artifact_id="a22-test-data-plan", source_snapshot_id=identity[2],
            producer=Producer("A22", runtime="deterministic-resource-compiler"),
            payload=plan,
            status=(
                ArtifactStatus.COMPLETED_WITH_GAPS
                if partial_routing
                else ArtifactStatus.COMPLETED
            ),
            reason_code="partial_capability_routing" if partial_routing else None,
            evidence_refs=(EvidenceRef("artifact", "a22-test-data-plan-declaration", str(args.declared_plan), str(declared["artifact_hash"])),),
        )
        validation = validate_test_data_plan(plan, policy)
        validation.update({
            "decision": "partial_capability_routing" if partial_routing else "full_capability_routing",
            "executable_case_ids": executable_case_ids,
            "deferred_cases": deferred_cases,
        })
        n27 = ArtifactEnvelope(
            workflow_run_id=identity[0], workflow_mode=identity[1],
            artifact_id="n27-test-data-plan-validation", source_snapshot_id=identity[2],
            producer=Producer("N27", runtime="deterministic"),
            payload={**validation, "a22_artifact_hash": a22.artifact_hash},
            status=(
                ArtifactStatus.COMPLETED_WITH_GAPS
                if partial_routing
                else ArtifactStatus.COMPLETED
            ),
            reason_code="partial_capability_routing" if partial_routing else None,
            evidence_refs=(EvidenceRef("artifact", a22.artifact_id, "a22-test-data-plan.json", a22.artifact_hash),),
        )
        store = ArtifactStore(args.artifact_dir)
        store.write_artifact(a22)
        store.write_artifact(n27)
        return
    prepare_autonomous_test_data_plan(
        args.artifact_dir / "artifacts/n25-compiled-test-cases.json",
        root / "qa-agents/knowledge/bi-knowledge-sources.json",
        root / "qa-agents/knowledge/bi-data-capability-catalog.json",
        root / "qa-agents/policies/test-data-policy.json",
        args.artifact_dir,
        environment=args.environment,
        namespace=namespace,
        inventory_path=args.inventory,
        integrated_a22=True,
    )


if __name__ == "__main__":
    main()
