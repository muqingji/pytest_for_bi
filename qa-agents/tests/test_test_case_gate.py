import json
from pathlib import Path

from qa_agents.contracts import artifact_hash_from_mapping
from qa_agents.multica import ingest_multica_output, prepare_multica_oracle_review_input
from qa_agents.test_case_gate import run_n04_after_a09


ROOT = Path(__file__).resolve().parents[1]
PILOT_RUN = ROOT / "tests" / "fixtures" / "pilot"


def rejected_a09_output(bundle: dict) -> dict:
    evidence = bundle["allowed_inputs"]["frozen_evidence"]
    design = bundle["allowed_inputs"]["test_design_ir"]
    cases = design["parent_cases"]
    case_ids = [case["id"] for case in cases]
    requirements = evidence["validated_analysis"]["requirement_analysis"][
        "requirements"
    ]
    obligations = evidence["approved_scope"]["test_rule_obligations"]
    dimensions = bundle["allowed_inputs"]["oracle_rule_library"][
        "required_coverage_dimensions"
    ]
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "needs_human",
        "approved": False,
        "issues": [
            {
                "id": "A09-001",
                "issue_code": "ORACLE_REQUIRED_FIELDS_MISSING",
                "human_title": "预期结果字段缺失",
                "plain_summary": "用例的预期结果缺少必要字段，无法执行校验。",
                "severity": "error",
                "category": "oracle",
                "message": "Oracle lacks type and source_ref",
                "path": "parent_cases[0].expected[0].oracle",
                "route_to": "A08",
                "case_id": cases[0]["id"],
                "expected_id": cases[0]["expected"][0]["id"],
                "source_refs": list(cases[0]["source_refs"]),
                "recommendation": "Add the required Oracle fields",
            }
        ],
        "coverage_dimensions": [
            {
                "dimension": dimension,
                "status": "covered",
                "case_ids": case_ids,
                "source_refs": ["a08-test-design-ir"],
                "rationale": "reviewed",
            }
            for dimension in dimensions
        ],
        "requirement_coverage": [
            {
                "requirement_id": item["id"],
                "status": "covered",
                "case_ids": case_ids,
            }
            for item in requirements
        ],
        "test_rule_coverage": [
            {
                "rule_id": item["id"],
                "status": "covered",
                "case_ids": case_ids,
            }
            for item in obligations
        ],
        "manual_case_recommendations": [],
        "code_coverage_reviewed": False,
        "evaluation_oracle_accessed": False,
    }


def test_n04_routes_invalid_real_a08_design_back_to_a08(tmp_path: Path) -> None:
    bundle = prepare_multica_oracle_review_input(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        ROOT / "policies" / "oracle-rule-library.json",
        tmp_path / "inputs",
    )
    ingest_multica_output(
        tmp_path / "inputs" / "a09-input.json",
        json.dumps(rejected_a09_output(bundle), ensure_ascii=False),
        tmp_path / "stage5",
        task_id="task-a09",
        issue_id="issue-a09",
        attachment_id="attachment-a09",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )

    artifact = run_n04_after_a09(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        tmp_path / "stage5" / "artifacts" / "a09-oracle-coverage-review.json",
        tmp_path / "inputs" / "a09-input.json",
        tmp_path / "stage6",
    )

    assert artifact["status"] == "needs_human"
    assert artifact["payload"]["valid"] is False
    assert artifact["payload"]["next_node"] == "A08"
    issue_codes = {item["issue_code"] for item in artifact["payload"]["issues"]}
    assert "invalid_test_data_type" in issue_codes
    assert "missing_execution_modes" in issue_codes
    assert "oracle_required_field" in issue_codes


def test_n04_exhausted_budget_routes_to_human(tmp_path: Path) -> None:
    bundle = prepare_multica_oracle_review_input(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        ROOT / "policies" / "oracle-rule-library.json",
        tmp_path / "inputs",
    )
    ingest_multica_output(
        tmp_path / "inputs" / "a09-input.json",
        json.dumps(rejected_a09_output(bundle), ensure_ascii=False),
        tmp_path / "stage5",
        task_id="task-a09",
        issue_id="issue-a09",
        attachment_id="attachment-a09",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )

    artifact = run_n04_after_a09(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        tmp_path / "stage5" / "artifacts" / "a09-oracle-coverage-review.json",
        tmp_path / "inputs" / "a09-input.json",
        tmp_path / "stage6",
        correction_attempt=2,
        max_correction_attempts=2,
    )

    assert artifact["payload"]["next_node"] == "human"
    assert artifact["reason_code"] == "test_case_ir_correction_budget_exhausted"


def test_n04_routes_human_when_previous_fix_claimed_but_still_blocking(
    tmp_path: Path,
) -> None:
    design = json.loads(
        (
            PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json"
        ).read_text(encoding="utf-8")
    )
    first_case = design["payload"]["parent_cases"][0]
    design["payload"]["correction_resolutions"] = [
        {
            "feedback_id": "A09-ISSUE-004",
            "disposition": "fixed",
            "affected_case_ids": [first_case["id"]],
            "source_refs": ["REQ-006"],
            "rationale": "已修正 Oracle",
        }
    ]
    design["artifact_hash"] = artifact_hash_from_mapping(design)
    corrected_design_path = tmp_path / "a08-corrected.json"
    corrected_design_path.write_text(
        json.dumps(design, ensure_ascii=False), encoding="utf-8"
    )

    bundle = prepare_multica_oracle_review_input(
        corrected_design_path,
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        ROOT / "policies" / "oracle-rule-library.json",
        tmp_path / "inputs",
    )
    a09_output = rejected_a09_output(bundle)
    a09_output["issues"] = [
        {
            "id": "A09-ISSUE-008",
            "issue_code": "LOCALE_NAME_PRECEDENCE_FIXTURE_CONFLICT",
            "human_title": "中英文测试数据冲突",
            "plain_summary": "英文场景仍取到中文结果。",
            "severity": "blocking",
            "category": "test_data",
            "message": "locale 数据分支未拆分",
            "path": "parent_cases[0].test_data",
            "route_to": "A08",
            "case_id": first_case["id"],
            "expected_id": first_case["expected"][0]["id"],
            "source_refs": list(first_case["source_refs"]),
            "recommendation": "按 locale 拆分数据行",
        }
    ]
    ingest_multica_output(
        tmp_path / "inputs" / "a09-input.json",
        json.dumps(a09_output, ensure_ascii=False),
        tmp_path / "stage5",
        task_id="task-a09-correction",
        issue_id="issue-a09-correction",
        attachment_id="attachment-a09-correction",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.2.1",
    )

    artifact = run_n04_after_a09(
        corrected_design_path,
        tmp_path / "stage5" / "artifacts" / "a09-oracle-coverage-review.json",
        tmp_path / "inputs" / "a09-input.json",
        tmp_path / "stage6",
        correction_attempt=1,
        max_correction_attempts=2,
    )

    assert artifact["payload"]["next_node"] == "human"
    assert artifact["reason_code"] == "test_case_ir_fix_unverified"
    assert artifact["payload"]["unverified_fix_issue_ids"] == ["A09-ISSUE-008"]
