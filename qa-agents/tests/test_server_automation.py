"""Server-only A14/A15 automation preparation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.contracts import ArtifactEnvelope, Producer
from qa_agents.errors import ContractError
from qa_agents.server_automation import prepare_server_automation


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "server-automation-run"
SNAPSHOT_ID = "server-automation-snapshot"


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _artifact(path: Path, component_id: str, artifact_id: str, payload: dict) -> Path:
    return _write(
        path,
        ArtifactEnvelope(
            workflow_run_id=RUN_ID,
            workflow_mode="new_requirement",
            artifact_id=artifact_id,
            source_snapshot_id=SNAPSHOT_ID,
            producer=Producer(component_id, runtime="deterministic"),
            payload=payload,
        ).to_dict(),
    )


def _case(case_id: str, layer: str, *, contract_ref: str = "") -> dict:
    case = {
        "id": case_id,
        "title": f"{layer} server Case",
        "layer": layer,
        "test_level": "api",
        "automation_candidate": True,
        "source_refs": [{"type": "requirement", "id": "REQ-1"}],
        "preconditions": ["fixture ready"],
        "test_data": {},
        "steps": [{
            "name": "execute request",
            "request": {"protocol": "http", "api": "example.query", "json": {}},
        }],
        "expected": [
            {
                "id": "EXP-1",
                "description": "response matches",
                "oracle": {
                    "observation_point": "response.status",
                    "matcher": "equals",
                    "expected_value": 200,
                },
            }
        ],
        "cleanup": [],
        "execution_policy": {"allowed_modes": ["automated"]},
    }
    if contract_ref:
        case["test_data"]["contract_ref"] = contract_ref
    return case


def _inputs(tmp_path: Path, cases: list[dict], actions: list[dict]) -> dict[str, Path]:
    plan = _artifact(
        tmp_path / "n15.json",
        "N15",
        "n15-execution-plan",
        {"schema_version": "execution-plan/1.0", "actions": actions},
    )
    compiled = _artifact(
        tmp_path / "n25.json",
        "N25",
        "n25-compiled-test-cases",
        {"schema_version": "n25-compiled-test-cases/1.0", "compiled_cases": cases},
    )
    target = _write(
        tmp_path / "target.json",
        {
            "repository_id": "pytest_for_bi",
            "access_class": "approved_automation_repository",
            "timeout_seconds": 30,
            "network": False,
            "secrets": [],
        },
    )
    return {"plan": plan, "compiled": compiled, "target": target}


def _run(tmp_path: Path, inputs: dict[str, Path]) -> dict:
    return prepare_server_automation(
        inputs["plan"],
        inputs["compiled"],
        ROOT / "policies/automation-target-policy.json",
        inputs["target"],
        tmp_path / "out",
    )


def test_prepares_server_profiles_and_excludes_frontend(tmp_path: Path) -> None:
    cases = [
        _case("CASE-BE", "backend"),
        _case("CASE-CT", "contract", contract_ref="openapi:detail-api"),
        _case("CASE-FE", "frontend"),
    ]
    result = _run(
        tmp_path,
        _inputs(
            tmp_path,
            cases,
            [
                {"case_id": "CASE-BE", "action": "generate_new"},
                {"case_id": "CASE-CT", "action": "update_existing"},
                {"case_id": "CASE-FE", "action": "generate_new"},
            ],
        ),
    )

    assert result["ready_for_n08"] is True
    assert result["planned_generation_case_ids"] == ["CASE-BE", "CASE-CT"]
    assert result["excluded_non_server_case_ids"] == ["CASE-FE"]
    assert {item["component_id"] for item in result["generated_artifacts"]} == {"A14", "A15"}
    assert {item["component_id"] for item in result["review_artifacts"]} == {
        "A18-BE", "A18-CT"
    }
    n05 = json.loads((tmp_path / "out/artifacts/n05-automation-code-check.json").read_text())
    assert n05["status"] == "completed"
    assert len(n05["payload"]["input_bindings"]) == 2


def test_records_missing_contract_reference_without_fabricating_candidate(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        _inputs(
            tmp_path,
            [_case("CASE-CT", "contract")],
            [{"case_id": "CASE-CT", "action": "generate_new"}],
        ),
    )

    assert result["ready_for_n08"] is False
    assert result["rejected_cases"] == [
        {"case_id": "CASE-CT", "reason_code": "contract_ref_missing"}
    ]
    assert result["generated_artifacts"][0]["status"] == "not_applicable"
    assert result["review_artifacts"][0]["status"] == "not_applicable"
    assert result["n05_artifact"]["status"] == "not_applicable"


def test_rejects_tampered_execution_plan(tmp_path: Path) -> None:
    inputs = _inputs(
        tmp_path,
        [_case("CASE-BE", "backend")],
        [{"case_id": "CASE-BE", "action": "generate_new"}],
    )
    plan = json.loads(inputs["plan"].read_text())
    plan["payload"]["actions"][0]["case_id"] = "CASE-TAMPERED"
    _write(inputs["plan"], plan)

    with pytest.raises(ContractError, match="hash is invalid"):
        _run(tmp_path, inputs)


def test_pauses_explicit_unit_case_generation(tmp_path: Path) -> None:
    unit_case = _case("CASE-UNIT", "backend")
    unit_case["test_level"] = "unit"
    result = _run(
        tmp_path,
        _inputs(
            tmp_path,
            [unit_case],
            [{"case_id": "CASE-UNIT", "action": "generate_new"}],
        ),
    )

    assert result["ready_for_n08"] is False
    assert result["rejected_cases"] == [
        {
            "case_id": "CASE-UNIT",
            "reason_code": "paused_existing_developer_unit_coverage",
        }
    ]


def test_binds_validated_n28_lifecycle_into_server_candidate(tmp_path: Path) -> None:
    case = _case("CASE-BE", "backend")
    inputs = _inputs(tmp_path, [case], [{"case_id": "CASE-BE", "action": "generate_new"}])
    plan_payload = {
        "schema_version": "test-data-plan/1.0", "environment": "112",
        "namespace": "qa-server-bind-001", "case_plans": [{
            "case_id": "CASE-BE", "variables": {"resource_id": "logical"},
            "resources": [{
                "resource_key": "metric", "resource_type": "aggregate_metric",
                "resource_id_variable": "metric_id",
                "setup": {"request": {"api": "create", "json": {"name": "{{ namespace }}"}}},
                "readiness": [{"request": {"api": "query"}}],
                "cleanup": {"request": {"api": "delete", "json": {"id": "{{ metric_id }}"}}},
                "residue_checks": [{"request": {"api": "query"},
                                    "expect_absent": {"json_path": "Value.id", "value": "{{ metric_id }}"}}],
            }],
        }],
    }
    n28 = _artifact(tmp_path / "n28.json", "N28", "n28-test-data-resource-plan", plan_payload)
    n28_value = json.loads(n28.read_text())
    n27 = _artifact(
        tmp_path / "n27.json", "N27", "n27-test-data-plan-validation",
        {"schema_version": "test-data-plan-validation/1.0", "valid": True,
         "n28_artifact_hash": n28_value["artifact_hash"], "deferred_cases": []},
    )
    result = prepare_server_automation(
        inputs["plan"], inputs["compiled"], ROOT / "policies/automation-target-policy.json",
        inputs["target"], tmp_path / "out", test_data_validation_path=n27,
        test_data_resource_plan_path=n28,
    )
    generation = json.loads(
        (tmp_path / "out/artifacts/a14-backend-automation-generation.json").read_text()
    )["payload"]
    assert result["ready_for_n08"] is True
    assert "residue_checks" in generation["code_candidates"][0]["content"]
    assert result["test_data_resource_plan_hash"] == n28_value["artifact_hash"]
    assert generation["manifest"]["input_bindings"]["test_data_validation_hash"]
    assert generation["manifest"]["input_bindings"]["test_data_resource_plan_hash"] == n28_value["artifact_hash"]


def test_knowledge_readiness_defers_unready_case_and_binds_ready_packet(tmp_path: Path) -> None:
    cases = [_case("CASE-READY", "backend"), _case("CASE-DEFERRED", "backend")]
    inputs = _inputs(
        tmp_path, cases,
        [{"case_id": "CASE-READY", "action": "generate_new"},
         {"case_id": "CASE-DEFERRED", "action": "generate_new"}],
    )
    readiness = _write(tmp_path / "readiness.json", {
        "schema_version": "automation-knowledge-readiness/1.0",
        "packet_hash": "sha256:knowledge",
        "ready_case_ids": ["CASE-READY"],
        "deferred_case_ids": ["CASE-DEFERRED"],
        "cases": [],
    })
    result = prepare_server_automation(
        inputs["plan"], inputs["compiled"], ROOT / "policies/automation-target-policy.json",
        inputs["target"], tmp_path / "out", knowledge_readiness_path=readiness,
    )
    generation = json.loads(
        (tmp_path / "out/artifacts/a14-backend-automation-generation.json").read_text()
    )["payload"]
    assert result["planned_generation_case_ids"] == ["CASE-READY"]
    assert result["deferred_case_ids"] == ["CASE-DEFERRED"]
    assert generation["manifest"]["input_bindings"]["knowledge_packet_hash"] == "sha256:knowledge"
