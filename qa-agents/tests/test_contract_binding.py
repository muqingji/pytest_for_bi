from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.contract_binding import bind_frozen_contract_refs
from qa_agents.contracts import ArtifactEnvelope, Producer
from qa_agents.errors import ContractError


COMMIT = "a" * 40
PATH = "/api/detail/query"


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-1",
        workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "compiled_cases": [
                {
                    "id": "CASE-CT",
                    "layer": "contract",
                    "automation_candidate": True,
                    "test_data": {"dataset": "detail"},
                }
            ],
        },
    )
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "test", "version": COMMIT},
        "x-contract-source": {"repository": "fs-bi", "ref": COMMIT},
        "paths": {PATH: {"post": {"operationId": "fs_bi_stat.stat_base.data_query"}}},
    }
    bindings = {
        "schema_version": "contract-case-bindings/1.0",
        "source_commit": COMMIT,
        "contract_location": "idl/fs-bi.openapi.json",
        "bindings": [
            {
                "case_id": "CASE-CT",
                "method": "POST",
                "path": PATH,
                "operation_id": "fs_bi_stat.stat_base.data_query",
            }
        ],
    }
    return (
        _write(tmp_path / "compiled.json", compiled.to_dict()),
        _write(tmp_path / "openapi.json", openapi),
        _write(tmp_path / "bindings.json", bindings),
    )


def test_binds_exact_frozen_openapi_operation(tmp_path: Path) -> None:
    compiled, openapi, bindings = _inputs(tmp_path)

    result = bind_frozen_contract_refs(compiled, openapi, bindings, tmp_path / "out")

    artifact = json.loads(Path(result["artifact_path"]).read_text())
    test_data = artifact["payload"]["compiled_cases"][0]["test_data"]
    assert test_data["operation_id"] == "fs_bi_stat.stat_base.data_query"
    assert test_data["contract_source_commit"] == COMMIT
    assert test_data["contract_ref"].endswith("#/paths/~1api~1detail~1query/post")


def test_rejects_binding_to_another_operation(tmp_path: Path) -> None:
    compiled, openapi, bindings = _inputs(tmp_path)
    value = json.loads(bindings.read_text())
    value["bindings"][0]["operation_id"] = "wrong.operation"
    _write(bindings, value)

    with pytest.raises(ContractError, match="does not match OpenAPI"):
        bind_frozen_contract_refs(compiled, openapi, bindings, tmp_path / "out")
