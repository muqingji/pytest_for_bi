import json
from pathlib import Path
import shutil

from qa_agents.agents.base import AgentOutput
from qa_agents.contracts import ArtifactStatus
from qa_agents.workflow import PhaseOneWorkflow


ROOT = Path(__file__).resolve().parents[1]
PILOT_INPUT = ROOT / "eval" / "workflows" / "pilot-001-detail-drill-message-i18n" / "input"


def test_pilot_stops_at_g01_when_product_acceptance_is_open(tmp_path: Path) -> None:
    output = tmp_path / "run"
    result = PhaseOneWorkflow(ROOT).run(
        PILOT_INPUT, output, run_id="pilot-test", stop_after="N04"
    )
    assert result.status == "needs_human"
    assert result.stopped_at == "G01"
    nodes = {item["id"]: item for item in result.summary["nodes"]}
    assert nodes["G01"]["status"] == "needs_human"
    assert nodes["G01"]["reason_code"] == "product_acceptance_open_questions"
    assert "A08" not in nodes


def test_approved_scope_runs_to_n04_without_oracle_access(tmp_path: Path) -> None:
    output = tmp_path / "run"
    result = PhaseOneWorkflow(ROOT).run(
        PILOT_INPUT,
        output,
        run_id="pilot-test-approved",
        stop_after="N04",
        approve_g01=True,
    )
    assert result.status == "completed_with_gaps"
    assert result.stopped_at == "N04"
    nodes = {item["id"]: item for item in result.summary["nodes"]}
    assert nodes["A01"]["status"] == "skipped_by_policy"
    assert nodes["N14"]["status"] == "completed_with_gaps"
    assert nodes["N14"]["reason_code"] == "asset_catalog_not_provided"
    assert nodes["A04"]["reason_code"] == "frontend_not_applicable"
    assert nodes["A07"]["reason_code"] == "risk_policy_is_deterministic"
    assert nodes["N24"]["status"] == "completed"
    assert nodes["N04"]["status"] == "completed"
    assert (output / "report.html").is_file()
    assert (output / "report.txt").is_file()
    assert not any(path.name.startswith("expected-") for path in (output / "artifacts").iterdir())
    with (output / "artifacts" / "a09-oracle-coverage-review.json").open(encoding="utf-8") as file:
        review = json.load(file)["payload"]
    assert review["evaluation_oracle_accessed"] is False
    with (output / "artifacts" / "a06-alignment-result.json").open(encoding="utf-8") as file:
        mappings = json.load(file)["payload"]["mappings"]
    assert all("CHANGE-BACKEND-001" not in item["change_fact_ids"] for item in mappings)


def test_approved_workflow_compiles_selects_and_plans(tmp_path: Path) -> None:
    output = tmp_path / "run"
    result = PhaseOneWorkflow(ROOT).run(
        PILOT_INPUT,
        output,
        run_id="pilot-full",
        stop_after="N15",
        approve_g01=True,
        approve_g02=True,
    )
    assert result.stopped_at == "N15"
    node_ids = [item["id"] for item in result.summary["nodes"]]
    assert "N25" in node_ids
    assert "A11" in node_ids
    assert "N26" in node_ids
    assert "N15" in node_ids
    with (output / "artifacts" / "n15-execution-plan.json").open(encoding="utf-8") as file:
        plan = json.load(file)["payload"]
    assert plan["actions"]
    assert {item["action"] for item in plan["actions"]} == {"manual_run"}


class AutomatedBackendDesigner:
    def run(self, context, inputs, security, model_runtime=None):
        requirements = inputs["requirement_analysis"]["requirements"]
        source_refs = requirements[0]["source_refs"]
        case = {
            "id": "CASE-AUTO-001",
            "parent_case_id": None,
            "intent_ids": ["INTENT-AUTO-001"],
            "title": "接口返回确定性错误码",
            "layer": "scenario",
            "required_layers": ["backend"],
            "risk": "high",
            "priority": "P1",
            "source_refs": source_refs,
            "preconditions": ["准备测试账号"],
            "test_data": {"request": {"method": "GET", "path": "/api/report"}},
            "steps": ["请求接口"],
            "expected": [
                {
                    "id": "EXP-01",
                    "description": "接口返回成功",
                    "oracle": {
                        "type": "deterministic",
                        "observation_point": "response.status",
                        "matcher": "equals:200",
                        "source_ref": "REQ:test",
                    },
                }
            ],
            "cleanup": [],
            "execution_policy": {
                "allowed_modes": ["automated"],
                "required_evidence": ["request_response"],
            },
            "automation_candidate": True,
        }
        output = AgentOutput(
            payload={
                "schema_version": "test-design-ir/1.0",
                "test_intents": [
                    {
                        "id": "INTENT-AUTO-001",
                        "objective": case["title"],
                        "risk": "high",
                        "required_layers": ["backend"],
                        "source_refs": source_refs,
                    }
                ],
                "parent_cases": [case],
                "provider_candidate_count": 0,
                "coverage_matrix": [
                    {"requirement_id": item["id"], "case_ids": [case["id"]]}
                    for item in requirements
                ],
            },
            status=ArtifactStatus.COMPLETED,
        )
        from qa_agents.agents.base import BaseAgent

        adapter = BaseAgent()
        adapter.agent_id = "A08"
        adapter.output_name = "test-design-ir"
        adapter.runtime = "test-design-runtime"
        adapter.analyze = lambda _: output
        return adapter.run(context, inputs, security, model_runtime)


def test_backend_automation_stops_at_g03_until_approved(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "input"
    shutil.copytree(PILOT_INPUT, input_dir)
    workflow_input_path = input_dir / "workflow-input.json"
    with workflow_input_path.open(encoding="utf-8") as file:
        workflow_input = json.load(file)
    workflow_input["component_applicability"] = {
        "frontend": {"status": "not_applicable"},
        "backend": {"status": "applicable"},
        "contract": {"status": "not_applicable"},
        "e2e": {"status": "not_applicable"},
    }
    workflow_input["automation_target"] = {
        "repository_id": "pytest_for_bi",
        "access_class": "approved_automation_repository",
        "timeout_seconds": 300,
        "network": False,
        "secrets": [],
    }
    with workflow_input_path.open("w", encoding="utf-8") as file:
        json.dump(workflow_input, file, ensure_ascii=False, indent=2)

    monkeypatch.setattr(
        "qa_agents.workflow.TestDesignerAgent", AutomatedBackendDesigner
    )
    pending = PhaseOneWorkflow(ROOT).run(
        input_dir,
        tmp_path / "pending",
        run_id="phase-two-pending",
        stop_after="G03",
        approve_g01=True,
        approve_g02=True,
    )
    assert pending.status == "needs_human"
    assert pending.stopped_at == "G03"
    pending_nodes = {item["id"]: item for item in pending.summary["nodes"]}
    assert pending_nodes["A14"]["status"] == "completed"
    assert pending_nodes["A18-BE"]["status"] == "completed"
    assert pending_nodes["N05"]["status"] == "completed"
    assert pending_nodes["G03"]["status"] == "needs_human"

    approved = PhaseOneWorkflow(ROOT).run(
        input_dir,
        tmp_path / "approved",
        run_id="phase-two-approved",
        stop_after="G03",
        approve_g01=True,
        approve_g02=True,
        approve_g03=True,
    )
    approved_nodes = {item["id"]: item for item in approved.summary["nodes"]}
    assert approved.stopped_at == "G03"
    assert approved_nodes["G03"]["status"] == "completed"
