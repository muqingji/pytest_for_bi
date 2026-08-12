#!/usr/bin/env python3
"""Prepare the hash-bound first backend chain from frozen repository evidence."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

from qa_agents.contracts import ArtifactEnvelope, EvidenceRef, Producer, artifact_hash_from_mapping, content_hash


CASE_ID = "PC-002-BACKEND"
OPERATION_ID = "fs_bi_stat.stat_base.data_query_da655ba1"
OPERATION_PATH = "/FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/query"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--openapi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compiled, openapi = _read(args.compiled), _read(args.openapi)
    if compiled.get("artifact_hash") != artifact_hash_from_mapping(compiled):
        raise ValueError("compiled Artifact hash is invalid")
    operation = openapi["paths"][OPERATION_PATH]["post"]
    if operation.get("operationId") != OPERATION_ID:
        raise ValueError("frozen OpenAPI operation does not match the first-chain operation")
    source = openapi.get("x-contract-source", {})
    commit = str(source.get("ref", ""))
    case = next(
        deepcopy(item) for item in compiled["payload"]["compiled_cases"]
        if item.get("id") == CASE_ID
    )
    automatic = [
        item for item in case.get("expected", [])
        if item.get("oracle", {}).get("matcher") != "manual_confirmation"
    ]
    if not automatic:
        raise ValueError("first-chain Case has no deterministic Oracle")
    case.update({
        "title": "结果集筛选聚合指标查看明细返回专用错误",
        "test_level": "functional",
        "expected": automatic,
        "execution_policy": {"allowed_modes": ["automated"], "automation_review": "required"},
        "test_data": {
            "dataset": "result_set_metric_types",
            "data_intent": "metric.result_set_filter.detail_unsupported",
            "variants": ["聚合指标"],
            "contract_ref": f"openapi:fs-bi@{commit}:idl/http/generated/fs-bi/fs-bi-stat.openapi.json",
            "contract_source_commit": commit,
            "method": "POST", "path": OPERATION_PATH, "operation_id": OPERATION_ID,
        },
        "steps": [{
            "name": "调用真实查看明细接口验证结果集筛选限制",
            "request": {"protocol": "http", "api": OPERATION_ID, "json": {
                "id": "{{ schema_id }}", "isView": 0,
                "measureFieldID": "{{ metric_field_id }}",
                "measureFieldIDs": ["{{ metric_field_id }}"],
                "pageNumber": 1, "pageSize": 20,
                "filterLists": [{"filters": [{
                    "displayNumber": 1, "fieldId": "{{ metric_field_id }}",
                    "fieldID": "{{ metric_field_id }}", "fieldName": "{{ metric_name }}",
                    "fieldType": "Number", "operator": 1, "operatorLabel": "等于",
                    "value1": "{{ numeric_filter_value }}", "value2": "",
                    "value_kind": "numeric", "aggDimType": "agg",
                    "filterConfig": {"showAppointLevelSwitch": 0, "switchStatus": 0,
                                     "filterGroupType": 1, "aggrType": "2", "ratioType": "0"},
                }]}], "timeZone": "Asia/Shanghai", "lan": "zh-CN",
            }},
            "expect": {"status_code": 200, "body_contains_keys": ["s307011535"]},
        }],
        "cleanup": [],
    })
    identity = (compiled["workflow_run_id"], compiled["workflow_mode"], compiled["source_snapshot_id"])
    evidence = (
        EvidenceRef("artifact", compiled["artifact_id"], str(args.compiled), compiled["artifact_hash"]),
        EvidenceRef("openapi", OPERATION_ID, str(args.openapi), content_hash(openapi)),
    )
    n25 = ArtifactEnvelope(
        workflow_run_id=identity[0], workflow_mode=identity[1],
        artifact_id="n25-compiled-test-cases", source_snapshot_id=identity[2],
        producer=Producer("N25", profile_version="1.2.0", runtime="deterministic"),
        payload={"schema_version": "n25-compiled-test-cases/1.0", "compiled_cases": [case],
                 "first_chain_projection": {"source_artifact_hash": compiled["artifact_hash"],
                                            "openapi_hash": content_hash(openapi),
                                            "operation_id": OPERATION_ID}},
        evidence_refs=evidence,
    )
    n15 = ArtifactEnvelope(
        workflow_run_id=identity[0], workflow_mode=identity[1],
        artifact_id="n15-execution-plan", source_snapshot_id=identity[2],
        producer=Producer("N15", runtime="deterministic"),
        payload={"schema_version": "execution-plan/1.0", "actions": [
            {"case_id": CASE_ID, "action": "generate_new", "automation_ref": None,
             "reason_code": "first_registered_backend_chain"}
        ]},
        evidence_refs=(EvidenceRef("artifact", n25.artifact_id, "artifacts/n25-compiled-test-cases.json", n25.artifact_hash),),
    )
    _write(args.output / "artifacts/n25-compiled-test-cases.json", n25.to_dict())
    _write(args.output / "artifacts/n15-execution-plan.json", n15.to_dict())
    _write(args.output / "first-chain-input.json", {
        "schema_version": "backend-first-chain-input/1.0", "case_id": CASE_ID,
        "n25_artifact_hash": n25.artifact_hash, "n15_artifact_hash": n15.artifact_hash,
        "source_artifact_hash": compiled["artifact_hash"], "openapi_hash": content_hash(openapi),
    })


if __name__ == "__main__":
    main()
