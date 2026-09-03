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
        identity = (
            str(declared["workflow_run_id"]), str(declared["workflow_mode"]),
            str(declared["source_snapshot_id"]),
        )
        blocked = not bool(plan.get("ready_for_execution"))
        a22 = ArtifactEnvelope(
            workflow_run_id=identity[0], workflow_mode=identity[1],
            artifact_id="a22-test-data-plan", source_snapshot_id=identity[2],
            producer=Producer("A22", runtime="deterministic-resource-compiler"),
            payload=plan, status=ArtifactStatus.BLOCKED if blocked else ArtifactStatus.COMPLETED,
            reason_code="test_data_capability_incomplete" if blocked else None,
            evidence_refs=(EvidenceRef("artifact", "a22-test-data-plan-declaration", str(args.declared_plan), str(declared["artifact_hash"])),),
        )
        validation = validate_test_data_plan(plan, policy)
        n27 = ArtifactEnvelope(
            workflow_run_id=identity[0], workflow_mode=identity[1],
            artifact_id="n27-test-data-plan-validation", source_snapshot_id=identity[2],
            producer=Producer("N27", runtime="deterministic"),
            payload={**validation, "a22_artifact_hash": a22.artifact_hash},
            status=ArtifactStatus.BLOCKED if blocked else ArtifactStatus.COMPLETED,
            reason_code="test_data_capability_incomplete" if blocked else None,
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
