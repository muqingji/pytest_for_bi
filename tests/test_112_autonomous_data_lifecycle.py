from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.config.environment import load_cases
from qa_agents.data_planning import compile_resource_plan, extract_test_data_intents
from qa_agents.test_data import bind_plan_to_case, validate_test_data_plan


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_case_drives_autonomous_metric_lifecycle_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("real autonomous data lifecycle runs only with --env=112")
    case = next(
        item
        for item in load_cases("112")
        if item["id"] == "CASE-AUTO-RESULT-FILTER-DETAIL-112"
    )
    catalog = _load(ROOT / "qa-agents/knowledge/bi-data-capability-catalog.json")
    policy = _load(ROOT / "qa-agents/policies/test-data-policy.json")
    intent = extract_test_data_intents([case], catalog)
    plan = compile_resource_plan(
        intent,
        catalog,
        environment="112",
        namespace="qa-autonomous-detail-112",
    )
    validation = validate_test_data_plan(plan, policy)
    assert validation["write_authorized"] is True

    executable_case = bind_plan_to_case(case, plan)
    context = case_runner.execute(executable_case)

    assert context["__lifecycle__"]["setup"][0]["status"] == "completed"
    assert context["__lifecycle__"]["readiness"][0]["status"] == "completed"
    assert context["__lifecycle__"]["test"][0]["status"] == "completed"
    assert context["__lifecycle__"]["cleanup"][0]["status"] == "completed"
    assert "s307011535" in str(context["test_response"])
    assert context["metric_name"] in str(context["test_response"])

    remaining = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        body={"schemaId": context["schema_id"]},
    )
    assert remaining.status_code == 200
    assert context["metric_field_id"] not in str(remaining.body)
    assert context["metric_name"] not in str(remaining.body)
