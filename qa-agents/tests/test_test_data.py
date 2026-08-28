from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.agents.base import AgentContext
from qa_agents.contracts import ArtifactStatus
from qa_agents.errors import SecurityPolicyError
from qa_agents.security import SecurityPolicy
from qa_agents.test_data import (
    TestDataPlannerAgent,
    bind_plan_to_case,
    prepare_test_data_plan,
    validate_test_data_plan,
)
from qa_agents.contracts import ArtifactEnvelope, Producer


ROOT = Path(__file__).resolve().parents[1]


def _resource() -> dict:
    return {
        "resource_key": "metric",
        "resource_type": "aggregate_metric",
        "retention_mode": "delete",
        "resource_id_variable": "metric_field_id",
        "setup": {
            "name": "create namespaced metric",
            "request": {
                "api": "fs_bi_stat.agg_rule.add_new_agg_rule",
                "json": {"displayName": "{{ namespace }}-metric"},
            },
            "extract": {"metric_field_id": "Value.fieldId"},
            "expect": {"status_code": 200},
        },
        "readiness": [
            {
                "name": "query metric",
                "request": {
                    "api": "fs_bi_stat.agg_rule.query_agg_rule_by_field_id",
                    "json": {"fieldId": "{{ metric_field_id }}"},
                },
                "expect": {"status_code": 200},
            }
        ],
        "cleanup": {
            "name": "delete metric",
            "request": {
                "api": "fs_bi_stat.agg_rule.delete_agg_rule",
                "json": {"fieldId": "{{ metric_field_id }}"},
            },
            "expect": {"status_code": 200},
        },
    }


def _case(test_level: str = "integration") -> dict:
    return {
        "id": "CASE-DETAIL",
        "test_level": test_level,
        "test_data": {"resource_requirements": [_resource()]},
        "steps": [{"request": {"api": "fs_bi_stat.stat_base.data_query_da655ba1"}}],
    }


def _run(cases: list[dict]) -> dict:
    artifact = TestDataPlannerAgent().run(
        AgentContext("run-1", "new_requirement", "snapshot-1"),
        {"environment": "112", "namespace": "qa-run-1-detail", "cases": cases},
        SecurityPolicy(),
    )
    return artifact.to_dict()


def _policy() -> dict:
    return json.loads((ROOT / "policies/test-data-policy.json").read_text())


def test_a22_plans_owned_112_resource_and_n27_validates_it() -> None:
    artifact = _run([_case()])

    assert artifact["status"] == "completed"
    validation = validate_test_data_plan(artifact["payload"], _policy())
    assert validation["validated_resource_count"] == 1
    assert validation["write_authorized"] is True
    assert validation["phase_permissions"] == {
        "setup": "write",
        "readiness": "read_only",
        "cleanup": "disabled",
        "retention_verification": "read_only",
    }
    bound = bind_plan_to_case(_case(), artifact["payload"])
    assert bound["environment"] == "112"
    assert bound["variables"]["namespace"] == "qa-run-1-detail"
    assert bound["cleanup"][0]["when_variable"] == "metric_field_id"


def test_a22_pauses_unit_cases_without_sending_them_to_data_construction() -> None:
    artifact = _run([_case("unit")])

    assert artifact["status"] == ArtifactStatus.COMPLETED.value
    assert artifact["payload"]["case_plans"] == []
    assert artifact["payload"]["paused_cases"] == [
        {
            "case_id": "CASE-DETAIL",
            "reason_code": "paused_existing_developer_unit_coverage",
        }
    ]


def test_n27_rejects_cross_environment_and_missing_cleanup_binding() -> None:
    plan = _run([_case()])["payload"]
    plan["environment"] = "online"
    with pytest.raises(SecurityPolicyError, match="not allowed"):
        validate_test_data_plan(plan, _policy())

    plan = _run([_case()])["payload"]
    plan["case_plans"][0]["resources"][0]["cleanup"]["request"]["json"] = {
        "fieldId": "unbounded"
    }
    with pytest.raises(SecurityPolicyError, match="extracted resource id"):
        validate_test_data_plan(plan, _policy())


def test_n27_rejects_inline_credentials() -> None:
    plan = _run([_case()])["payload"]
    plan["case_plans"][0]["resources"][0]["setup"]["request"]["token"] = "inline"
    with pytest.raises(SecurityPolicyError, match="inline credential"):
        validate_test_data_plan(plan, _policy())


def test_n27_rejects_write_operation_in_readiness_phase() -> None:
    plan = _run([_case()])["payload"]
    plan["case_plans"][0]["resources"][0]["readiness"][0]["request"]["api"] = (
        "fs_bi_stat.agg_rule.add_new_agg_rule"
    )

    with pytest.raises(SecurityPolicyError, match="read-only readiness operation"):
        validate_test_data_plan(plan, _policy())


def _enum_plan() -> dict:
    plan = _run([_case()])["payload"]
    setup = plan["case_plans"][0]["resources"][0]["setup"]
    setup["request"]["json"]["filterLists"] = [{"filters": [{
        "fieldId": "level-field", "fieldID": "level-field", "fieldType": "Enum",
        "fieldName": "客户级别",
        "value1": '[{"optionCode":"A","optionName":"重点客户"}]',
    }]}]
    return plan


def _bind_enum(plan: dict, **overrides: object) -> None:
    binding = {
        "field_id": "level-field", "field_api_name": "account_level",
        "option_query_operation": "fs_bi_stat.stat_edit.get_filters_result",
        "option_response_hash": "sha256:" + "a" * 64,
        "response_json_path": "$.Value.options[*]",
        "queried_option_codes": ["A", "B"], "selected_option_codes": ["A"],
    }
    binding.update(overrides)
    plan["case_plans"][0]["resources"][0]["setup"]["enum_option_bindings"] = [binding]


def test_n27_accepts_bound_enum_and_plain_numeric_filter() -> None:
    plan = _enum_plan()
    _bind_enum(plan)
    validate_test_data_plan(plan, _policy())
    numeric = _run([_case()])["payload"]
    numeric["case_plans"][0]["resources"][0]["setup"]["request"]["json"]["filterLists"] = [
        {"filters": [{"fieldId": "amount", "fieldType": "Number", "value1": "0"}]}
    ]
    validate_test_data_plan(numeric, _policy())


@pytest.mark.parametrize("mutation,message", [
    ("missing", "enum_option_bindings"), ("hash", "valid option response hash"),
    ("unknown", "not returned"), ("field", "exactly one binding"),
    ("label", "without optionCode"),
])
def test_n27_rejects_unproven_enum_values(mutation: str, message: str) -> None:
    plan = _enum_plan()
    if mutation != "missing":
        overrides: dict[str, object] = {}
        if mutation == "hash": overrides["option_response_hash"] = "sample"
        if mutation == "unknown": overrides["selected_option_codes"] = ["C"]
        if mutation == "field": overrides["field_id"] = "other-field"
        _bind_enum(plan, **overrides)
    if mutation == "label":
        plan["case_plans"][0]["resources"][0]["setup"]["request"]["json"]["filterLists"][0]["filters"][0]["value1"] = '[{"optionName":"重点客户"}]'
    with pytest.raises(SecurityPolicyError, match=message):
        validate_test_data_plan(plan, _policy())


def _custom_dimension_plan() -> dict:
    plan = _run([_case()])["payload"]
    resource = plan["case_plans"][0]["resources"][0]
    resource["resource_type"] = "custom_dimension"
    resource["setup"]["request"]["api"] = "fs_bi_stat.custom_dimension.create_custom_dimension"
    resource["setup"]["request"]["json"] = {
        "customType": "enum_group",
        "sourceDimension": {"fieldId": "source-level", "dimensionField": "account_level"},
        "dimensionConfig": '{"groups":[{"name":"等级组","values":["A"]}]}',
        "ownership": "{{ namespace }}",
    }
    resource["setup"]["enum_option_bindings"] = [{
        "field_id": "source-level", "field_api_name": "account_level",
        "option_query_operation": "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        "option_response_hash": "sha256:" + "b" * 64,
        "response_json_path": "$.Value[*].ui.data[*]",
        "queried_option_codes": ["A", "B"], "selected_option_codes": ["A"],
    }]
    resource["cleanup"]["request"]["api"] = "fs_bi_stat.custom_dimension.delete_custom_dimension"
    return plan


def test_n27_validates_enum_codes_hidden_in_custom_dimension_config() -> None:
    validate_test_data_plan(_custom_dimension_plan(), _policy())
    plan = _custom_dimension_plan()
    plan["case_plans"][0]["resources"][0]["setup"]["request"]["json"]["dimensionConfig"] = (
        '{"groups":[{"name":"等级组","values":["invented"]}]}'
    )
    with pytest.raises(SecurityPolicyError, match="not returned"):
        validate_test_data_plan(plan, _policy())


def _existing_historical_chart_plan() -> dict:
    plan = _run([_case()])["payload"]
    resource = plan["case_plans"][0]["resources"][0]
    resource.pop("setup")
    resource.pop("cleanup")
    resource["resource_type"] = "stat_chart"
    resource["lifecycle_mode"] = "existing_read_only"
    resource["discovery"] = {
        "request": {
            "api": "fs_bi_stat.view_data_query_api.get_chart_config",
            "json": {"viewId": "BI_existing"},
        }
    }
    resource["readiness"] = [resource["discovery"]]
    resource["existing_asset_evidence"] = {
        "historical_required": True,
        "evidence_level": "historical_candidate_verified_by_id_timestamp_and_live_readback",
        "observed_created_at": "2025-09-04T08:08:11Z",
        "requirement_baseline_at": "2026-08-07T11:42:44Z",
        "live_readback_status": "succeeded",
        "configuration_hash": "sha256:" + "c" * 64,
    }
    return plan


def test_n27_accepts_existing_historical_asset_without_fake_setup() -> None:
    plan = _existing_historical_chart_plan()
    validation = validate_test_data_plan(plan, _policy())
    bound = bind_plan_to_case(_case(), plan)

    assert validation["validated_resource_count"] == 1
    assert bound["setup"] == []
    assert [item["phase"] for item in bound["preparation"]] == [
        "discovery", "readiness"
    ]


@pytest.mark.parametrize("mutation,message", [
    ("write", "cannot define setup or cleanup"),
    ("hash", "valid configuration hash"),
    ("readback", "live readback is not proven"),
    ("level", "evidence level is insufficient"),
])
def test_n27_rejects_unproven_existing_historical_asset(
    mutation: str, message: str
) -> None:
    plan = _existing_historical_chart_plan()
    resource = plan["case_plans"][0]["resources"][0]
    evidence = resource["existing_asset_evidence"]
    if mutation == "write":
        resource["setup"] = _resource()["setup"]
    elif mutation == "hash":
        evidence["configuration_hash"] = "sample"
    elif mutation == "readback":
        evidence["live_readback_status"] = "unknown"
    else:
        evidence["evidence_level"] = "repository_reference_only"

    with pytest.raises(SecurityPolicyError, match=message):
        validate_test_data_plan(plan, _policy())


def test_prepare_test_data_plan_writes_hash_bound_a22_and_n27_artifacts(
    tmp_path: Path,
) -> None:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-1",
        workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "compiled_cases": [_case()],
        },
    )
    compiled_path = tmp_path / "n25.json"
    compiled_path.write_text(json.dumps(compiled.to_dict()), encoding="utf-8")

    result = prepare_test_data_plan(
        compiled_path,
        ROOT / "policies/test-data-policy.json",
        tmp_path / "out",
        environment="112",
        namespace="qa-run-1-detail",
    )

    assert result["ready_for_execution"] is True
    assert (tmp_path / "out/artifacts/a22-test-data-plan.json").exists()
    n27 = json.loads(
        (tmp_path / "out/artifacts/n27-test-data-plan-validation.json").read_text()
    )
    assert n27["payload"]["a22_artifact_hash"] == result["a22_artifact"]["artifact_hash"]


def test_policy_skip_defers_only_cases_that_need_missing_data(tmp_path: Path) -> None:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-1",
        workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "compiled_cases": [_case(), {"id": "CASE-EXISTING", "steps": []}],
        },
    )
    compiled_path = tmp_path / "n25.json"
    compiled_path.write_text(json.dumps(compiled.to_dict()), encoding="utf-8")

    result = prepare_test_data_plan(
        compiled_path,
        ROOT / "policies/test-data-policy.json",
        tmp_path / "out",
        environment="112",
        namespace="qa-run-1-detail",
        skip_by_policy=True,
    )

    assert result["ready_for_execution"] is True
    assert result["a22_artifact"]["status"] == "skipped_by_policy"
    assert result["n27_artifact"]["status"] == "skipped_by_policy"
    assert result["executable_case_ids"] == ["CASE-EXISTING"]
    assert result["deferred_cases"][0]["route"] == "deferred_data_construction"


def test_existing_automation_managed_plan_is_completed_and_hash_bound(tmp_path: Path) -> None:
    compiled = ArtifactEnvelope(
        workflow_run_id="run-1", workflow_mode="new_requirement",
        artifact_id="n25-compiled-test-cases", source_snapshot_id="snapshot-1",
        producer=Producer("N25", runtime="deterministic"),
        payload={"schema_version": "n25-compiled-test-cases/1.0", "compiled_cases": [_case()]},
    )
    execution = ArtifactEnvelope(
        workflow_run_id="run-1", workflow_mode="new_requirement",
        artifact_id="n15-execution-plan", source_snapshot_id="snapshot-1",
        producer=Producer("N15", runtime="deterministic"),
        payload={
            "schema_version": "execution-plan/1.0",
            "actions": [{
                "case_id": "CASE-DETAIL", "action": "run_existing",
                "automation_ref": "tests/test_existing.py",
            }],
        },
    )
    compiled_path = tmp_path / "n25.json"
    execution_path = tmp_path / "n15.json"
    compiled_path.write_text(json.dumps(compiled.to_dict()), encoding="utf-8")
    execution_path.write_text(json.dumps(execution.to_dict()), encoding="utf-8")

    result = prepare_test_data_plan(
        compiled_path, ROOT / "policies/test-data-policy.json", tmp_path / "out",
        environment="112", namespace="qa-run-1-detail",
        execution_plan_path=execution_path,
    )

    assert result["ready_for_execution"] is True
    assert result["a22_artifact"]["status"] == "completed"
    n27 = json.loads((tmp_path / "out/artifacts/n27-test-data-plan-validation.json").read_text())
    assert n27["payload"]["decision"] == "existing_automation_managed"
    assert n27["payload"]["execution_plan_hash"] == execution.artifact_hash


def _planning_level_plan() -> dict:
    """A22 Agent planning-level contract: resources name operations via
    ``setup_operation`` instead of embedding full request/expect objects."""
    return {
        "schema_version": "test-data-plan/1.0",
        "environment": "112",
        "namespace": "qa-a22-planning-level",
        "status": "needs_human",
        "planning_mode": "case_explicit",
        "case_plans": [
            {
                "case_id": "TC-BE-001-BACKEND",
                "requires_data_construction": True,
                "source_refs": ["TC-BE-001-BACKEND"],
                "resources": [
                    {
                        "resource_key": "cd_field",
                        "resource_type": "custom_dimension",
                        "resource_id_variable": "cd_field_id",
                        "setup_operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                        "high_risk_write": True,
                    }
                ],
            },
            {
                "case_id": "TC-BE-002-BACKEND",
                "requires_data_construction": True,
                "source_refs": ["TC-BE-002-BACKEND"],
                "resources": [
                    {
                        "resource_key": "ordinary_field_fixture",
                        "resource_type": "crm_field",
                        "resource_id_variable": "ordinary_field_id",
                        "lifecycle_mode": "existing_read_only",
                        "setup_operation": "fs_bi_stat.stat_schema.get_fields_by_schema_id",
                    }
                ],
            },
        ],
        "paused_cases": [],
        "unresolved_requirements": [
            {"requirement_id": "UR-01", "reason_code": "chart_create_op_unverified"}
        ],
    }


def test_validate_test_data_plan_accepts_planning_level_contract() -> None:
    plan = _planning_level_plan()
    result = validate_test_data_plan(plan, _policy())
    assert result["valid"] is True
    assert result["validated_resource_count"] == 2
    assert result["write_authorized"] is True


def test_validate_test_data_plan_rejects_unknown_setup_operation() -> None:
    plan = _planning_level_plan()
    plan["case_plans"][0]["resources"][0]["setup_operation"] = "not.a.real.operation"
    with pytest.raises(SecurityPolicyError):
        validate_test_data_plan(plan, _policy())


def test_validate_test_data_plan_rejects_delete_without_cleanup_pair() -> None:
    plan = _planning_level_plan()
    plan["case_plans"][0]["resources"][0]["retention_mode"] = "delete"
    # create_custom_dimension has a cleanup pair, so use a setup op without one
    plan["case_plans"][0]["resources"][0]["setup_operation"] = "fs_bi_dev.lwt_manager.save"
    plan["case_plans"][0]["resources"][0]["retention_mode"] = "delete"
    with pytest.raises(SecurityPolicyError):
        validate_test_data_plan(plan, _policy())


def _plan_artifact(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "a22-test-data-plan.json"
    path.write_text(json.dumps({"payload": payload}, ensure_ascii=False), encoding="utf-8")
    return path


def test_record_constructed_test_data_registers_completed_setup_operations(
    tmp_path: Path,
) -> None:
    from qa_agents.test_data import record_constructed_test_data

    plan = _plan_artifact(
        tmp_path,
        {
            "namespace": "qa-pilot-001-source-v1",
            "case_plans": [
                {
                    "case_id": "TC-BE-001-BACKEND",
                    "resources": [
                        {
                            "resource_key": "cd_field",
                            "resource_type": "custom_dimension",
                            "setup_operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                            "resource_id_variable": "cd_field_id",
                        },
                        {
                            "resource_key": "never_created_metric",
                            "resource_type": "aggregate_metric",
                            "setup_operation": "fs_bi_stat.agg_rule.add_new_agg_rule",
                        },
                    ],
                }
            ],
        },
    )
    auto_dir = tmp_path / "auto"
    evidence = auto_dir / "evidence" / "N08-S001" / "lifecycle.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "shard-lifecycle-evidence/1.0",
                "cases": [
                    {
                        "case_id": "TC-BE-001-BACKEND",
                        "phases": {
                            "setup": [
                                {
                                    "name": "create_custom_dimension_variants",
                                    "operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                                    "status": "completed",
                                    "status_code": 200,
                                    "verified": True,
                                    "response_hash": "sha256:abc",
                                }
                            ],
                            "test": [],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    n08 = tmp_path / "n08-automation-execution.json"
    n08.write_text(
        json.dumps(
            {
                "payload": {
                    "shards": [
                        {
                            "case_ids": ["TC-BE-001-BACKEND"],
                            "lifecycle_evidence_path": "evidence/N08-S001/lifecycle.json",
                            "lifecycle_evidence_hash": "sha256:ev",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    observed = tmp_path / "env-observed.json"
    observed.write_text(
        json.dumps(
            {
                "schema_version": "environment-observation/1.0",
                "environment": "112",
                "test_data": [{"key": "existing", "resource_type": "fixture", "status": "constructed"}],
                "test_namespaces": [{"namespace": "qa-pilot-001-source-v1", "cleanup_policy": {"required": True}}],
            }
        ),
        encoding="utf-8",
    )

    result = record_constructed_test_data(plan, n08, auto_dir, observed)

    assert result["registered"][0]["key"] == "cd_field"
    assert result["registered"][0]["namespace"] == "qa-pilot-001-source-v1"
    assert result["registered"][0]["response_hash"] == "sha256:abc"
    assert len(result["registered"]) == 1  # never_created_metric 未构造，不登记
    updated = json.loads(observed.read_text(encoding="utf-8"))
    keys = {(item.get("case_id"), item.get("key")) for item in updated["test_data"]}
    assert ("TC-BE-001-BACKEND", "cd_field") in keys
    assert (None, "existing") in keys  # 无关条目保留


def test_record_constructed_test_data_is_idempotent_and_degradable(
    tmp_path: Path,
) -> None:
    from qa_agents.test_data import record_constructed_test_data

    plan = _plan_artifact(
        tmp_path,
        {
            "namespace": "qa-pilot-001-source-v1",
            "case_plans": [
                {
                    "case_id": "TC-BE-001-BACKEND",
                    "resources": [
                        {
                            "resource_key": "cd_field",
                            "resource_type": "custom_dimension",
                            "setup_operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                        }
                    ],
                }
            ],
        },
    )
    auto_dir = tmp_path / "auto"
    n08 = tmp_path / "n08-automation-execution.json"
    n08.write_text(
        json.dumps({"payload": {"shards": []}}), encoding="utf-8"
    )
    observed = tmp_path / "env-observed.json"
    observed.write_text(
        json.dumps({"schema_version": "environment-observation/1.0", "test_data": []}),
        encoding="utf-8",
    )

    first = record_constructed_test_data(plan, n08, auto_dir, observed)
    second = record_constructed_test_data(plan, n08, auto_dir, observed)

    assert first["registered"] == []
    assert second["registered"] == []
    assert json.loads(observed.read_text(encoding="utf-8"))["test_data"] == []


def test_record_constructed_test_data_demotes_phantom_entries_to_stale(
    tmp_path: Path,
) -> None:
    from qa_agents.test_data import record_constructed_test_data

    plan = _plan_artifact(
        tmp_path,
        {
            "namespace": "qa-pilot-001-source-v1",
            "case_plans": [
                {
                    "case_id": "TC-BE-001-BACKEND",
                    "resources": [
                        {
                            "resource_key": "cd_field",
                            "resource_type": "custom_dimension",
                            "setup_operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                            "resource_id_variable": "cd_field_id",
                        }
                    ],
                }
            ],
        },
    )
    auto_dir = tmp_path / "auto"
    evidence = auto_dir / "evidence" / "N08-S001" / "lifecycle.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "shard-lifecycle-evidence/1.0",
                "cases": [
                    {
                        "case_id": "TC-BE-001-BACKEND",
                        "phases": {
                            "setup": [
                                {
                                    "name": "setup_create_custom_dimension",
                                    "operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                                    "status": "failed",
                                    "error_type": "AssertionError",
                                }
                            ],
                            "test": [],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    n08 = tmp_path / "n08-automation-execution.json"
    n08.write_text(
        json.dumps(
            {
                "payload": {
                    "shards": [
                        {
                            "case_ids": ["TC-BE-001-BACKEND"],
                            "lifecycle_evidence_path": "evidence/N08-S001/lifecycle.json",
                            "lifecycle_evidence_hash": "sha256:ev",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    observed = tmp_path / "env-observed.json"
    observed.write_text(
        json.dumps(
            {
                "schema_version": "environment-observation/1.0",
                "environment": "112",
                "test_data": [
                    {
                        "key": "cd_field",
                        "resource_type": "custom_dimension",
                        "case_id": "TC-BE-001-BACKEND",
                        "operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                        "status": "constructed",
                    }
                ],
                "test_namespaces": [{"namespace": "qa-pilot-001-source-v1", "cleanup_policy": {"required": True}}],
            }
        ),
        encoding="utf-8",
    )

    result = record_constructed_test_data(plan, n08, auto_dir, observed)

    assert result["registered"] == []
    updated = json.loads(observed.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in updated["test_data"]
        if item.get("key") == "cd_field"
    )
    assert entry["status"] == "stale"

def test_bind_plan_injects_chart_config_differentiation_action() -> None:
    """Cloned charts must bind case-owned dimension/measure/filter after rename/move."""
    from qa_agents.data_planning import compile_resource_plan

    catalog = json.loads((ROOT / "knowledge/bi-data-capability-catalog.json").read_text())
    intent = {
        "schema_version": "test-data-intent/1.0",
        "case_intents": [
            {
                "case_id": "CASE-CHART-DIFF",
                "requirement_name": "自定义维度三类位置的专用错误与双语提示",
                "required_scene": "chart_detail",
                "requires_data_construction": True,
                "recipe_id": "custom-dimension-chart-detail",
            }
        ],
        "paused_cases": [],
        "unresolved_requirements": [],
    }
    plan = compile_resource_plan(
        intent, catalog, environment="112", namespace="qa-chart-diff-001"
    )
    case = {"id": "CASE-CHART-DIFF", "title": "自定义维度三类位置的专用错误与双语提示"}
    bound = bind_plan_to_case(case, plan)
    actions = [step.get("action") for step in bound.get("setup", [])]
    assert "bind_stat_chart_config" in actions
    bind_step = next(
        step for step in bound["setup"] if step.get("action") == "bind_stat_chart_config"
    )
    inputs = bind_step["inputs"]
    assert inputs["chart_view_id"] == "{{ chart_view_id }}"
    assert inputs["schema_id"] == "{{ schema_id }}"
    assert inputs["dimension_field_id"] == "{{ custom_dimension_id }}"
    assert inputs["measure_field_id"] == "{{ metric_field_id }}"
    # single aggregate metric => filter falls back to rotated native field (or amount)
    assert inputs["filter_field_id"]
    assert inputs["filter_field_id"] != inputs["measure_field_id"]


def test_case_chart_bind_inputs_splits_filter_and_fallback_dimension() -> None:
    from qa_agents.test_data import _case_chart_bind_inputs

    resources = [
        {"resource_type": "aggregate_metric", "resource_id_variable": "metric_field_id"},
        {"resource_type": "stat_chart", "resource_id_variable": "chart_view_id"},
    ]
    variables = {
        "amount_field_id": "BI_amount",
        "fallback_dimension_field_ids": [
            "BI_dim_a",
            "BI_dim_b",
            "BI_dim_c",
        ],
        "fallback_filter_field_ids": [
            "BI_filt_a",
            "BI_filt_b",
            "BI_filt_c",
        ],
    }
    bound = _case_chart_bind_inputs(
        resources,
        variables=variables,
        case_id="CASE-A",
    )
    assert bound["measure_field_id_var"] == "metric_field_id"
    assert bound["filter_field_id_var"] == ""
    assert bound["filter_field_id"] in {"BI_filt_a", "BI_filt_b", "BI_filt_c"}
    assert bound["dimension_field_id_var"] == ""
    assert bound["dimension_field_id"] in {"BI_dim_a", "BI_dim_b", "BI_dim_c"}
    # dimension and filter should prefer different native fields
    assert bound["filter_field_id"] != bound["dimension_field_id"]

    other = _case_chart_bind_inputs(
        resources,
        variables=variables,
        case_id="CASE-B",
    )
    # different cases should not always collide on the same fallback dim/filter
    assert {bound["dimension_field_id"], other["dimension_field_id"]} <= {"BI_dim_a", "BI_dim_b", "BI_dim_c"}
    assert {bound["filter_field_id"], other["filter_field_id"]} <= {"BI_filt_a", "BI_filt_b", "BI_filt_c"}


def test_case_chart_bind_inputs_prefers_second_metric_for_filter() -> None:
    from qa_agents.test_data import _case_chart_bind_inputs

    bound = _case_chart_bind_inputs(
        [
            {"resource_type": "aggregate_metric", "resource_id_variable": "metric_a"},
            {"resource_type": "aggregate_metric", "resource_id_variable": "metric_b"},
            {"resource_type": "custom_dimension", "resource_id_variable": "custom_dimension_id"},
        ],
        variables={"amount_field_id": "BI_amount"},
        case_id="CASE-MULTI",
    )
    assert bound["dimension_field_id_var"] == "custom_dimension_id"
    assert bound["measure_field_id_var"] == "metric_a"
    assert bound["filter_field_id_var"] == "metric_b"
    assert bound["filter_field_id"] == ""
