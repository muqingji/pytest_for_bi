"""N00 deterministic routing and A01 advice-only fallback."""

import json
from pathlib import Path
import shutil

from qa_agents.agents import WorkflowRouteAdvisorAgent
from qa_agents.agents.base import AgentContext
from qa_agents.contracts import ArtifactStatus
from qa_agents.security import SecurityPolicy
from qa_agents.workflow import PhaseOneWorkflow, resolve_workflow_route


ROOT = Path(__file__).resolve().parents[1]
PILOT_INPUT = ROOT / "eval" / "workflows" / "pilot-001-detail-drill-message-i18n" / "input"


def context() -> AgentContext:
    return AgentContext("run-1", "new_requirement", "snapshot-1", ("input/workflow-input.json",))


def test_known_template_is_deterministic() -> None:
    route = resolve_workflow_route(
        {"workflow_mode": "new_requirement", "trigger": {"kind": "commit_validation"}}
    )
    assert route["template"] == "new_requirement"
    assert route["execution_depth"] == "L2"
    assert route["route_source"] == "deterministic"
    assert route["unresolved_items"] == []


def test_unknown_mode_with_hint_is_advised_then_validated_by_n00() -> None:
    route = resolve_workflow_route(
        {
            "workflow_mode": "custom-drill-flow",
            "route_hint": "bug_reproduction",
            "trigger": {"kind": "bug"},
        }
    )
    assert route["route_source"] == "ambiguous"
    assert route["unresolved_items"][0]["requested_template"] == "bug_reproduction"

    advice = WorkflowRouteAdvisorAgent().run(
        context(),
        {
            "unresolved_items": route["unresolved_items"],
            "candidate_templates": ["bug_reproduction", "new_requirement"],
        },
        SecurityPolicy(),
    )
    assert advice.status == ArtifactStatus.COMPLETED
    assert advice.payload["recommended_template"] == "bug_reproduction"
    assert advice.payload["advisor_authority"] == "advice_only"


def test_unknown_mode_without_hint_escalates_to_human() -> None:
    route = resolve_workflow_route(
        {"workflow_mode": "custom-drill-flow", "trigger": {"kind": "commit_validation"}}
    )
    assert route["unresolved_items"][0]["requested_template"] is None
    advice = WorkflowRouteAdvisorAgent().run(
        context(),
        {
            "unresolved_items": route["unresolved_items"],
            "candidate_templates": ["new_requirement"],
        },
        SecurityPolicy(),
    )
    assert advice.status == ArtifactStatus.NEEDS_HUMAN
    assert advice.payload["recommended_template"] is None
    assert advice.reason_code == "route_ambiguity"


def test_trigger_mismatch_suggests_single_matching_template() -> None:
    route = resolve_workflow_route(
        {"workflow_mode": "new_requirement", "trigger": {"kind": "bug"}}
    )
    assert route["unresolved_items"][0]["issue_code"] == "trigger_template_mismatch"
    assert route["unresolved_items"][0]["requested_template"] == "bug_reproduction"


def test_ambiguous_trigger_kind_escalates_to_human() -> None:
    route = resolve_workflow_route(
        {"workflow_mode": "release_regression", "trigger": {"kind": "commit_validation"}}
    )
    assert route["unresolved_items"][0]["requested_template"] is None
    advice = WorkflowRouteAdvisorAgent().run(
        context(),
        {
            "unresolved_items": route["unresolved_items"],
            "candidate_templates": ["change_incremental", "new_requirement"],
        },
        SecurityPolicy(),
    )
    assert advice.status == ArtifactStatus.NEEDS_HUMAN


def _workflow_input(tmp_path: Path, *, mode: str, route_hint: str | None) -> Path:
    input_dir = tmp_path / "input"
    shutil.copytree(PILOT_INPUT, input_dir)
    path = input_dir / "workflow-input.json"
    with path.open(encoding="utf-8") as file:
        value = json.load(file)
    value["workflow_mode"] = mode
    if route_hint is not None:
        value["route_hint"] = route_hint
    else:
        value.pop("route_hint", None)
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
    return input_dir


def test_workflow_runs_to_n04_with_validated_advice(tmp_path: Path) -> None:
    input_dir = _workflow_input(tmp_path, mode="custom-drill-flow", route_hint="new_requirement")
    result = PhaseOneWorkflow(ROOT).run(
        input_dir,
        tmp_path / "run",
        run_id="route-advice",
        stop_after="N04",
        approve_g01=True,
    )
    assert result.status == "completed_with_gaps"
    assert result.stopped_at == "N04"
    nodes = {item["id"]: item for item in result.summary["nodes"]}
    assert nodes["A01"]["status"] == "completed"
    assert nodes["N04"]["status"] == "completed"
    with (tmp_path / "run" / "artifacts" / "n00-workflow-route-validated.json").open(
        encoding="utf-8"
    ) as file:
        validated = json.load(file)["payload"]
    assert validated["route_source"] == "advisor_validated"
    assert validated["workflow_template"] == "new_requirement"


def test_workflow_stops_at_a01_when_route_is_ambiguous(tmp_path: Path) -> None:
    input_dir = _workflow_input(tmp_path, mode="custom-drill-flow", route_hint=None)
    result = PhaseOneWorkflow(ROOT).run(
        input_dir,
        tmp_path / "run",
        run_id="route-blocked",
        stop_after="N04",
        approve_g01=True,
    )
    assert result.status == "needs_human"
    assert result.stopped_at == "A01"
    nodes = {item["id"]: item for item in result.summary["nodes"]}
    assert nodes["A01"]["status"] == "needs_human"
    assert nodes["A01"]["reason_code"] == "route_ambiguity"
    assert "A02" not in nodes
