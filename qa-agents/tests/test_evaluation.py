import json
from pathlib import Path

from qa_agents.evaluation import evaluate_run


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_run_after_scope_decision_accepts_completed_with_gaps(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    oracle_dir = tmp_path / "oracle"
    write_json(
        run_dir / "run-summary.json",
        {
            "workflow_run_id": "run-1",
            "nodes": [{"id": "A08", "status": "completed_with_gaps"}],
        },
    )
    write_json(
        oracle_dir / "expected-routing.json",
        {"nodes": [{"id": "A08", "expected": "run_after_scope_decision"}]},
    )
    result = evaluate_run(run_dir, oracle_dir)
    assert result["passed"] is True
    assert result["passed_checks"] == 1
    assert result["failed_checks"] == 0


def test_pause_if_unresolved_requires_recorded_gate_reason(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    oracle_dir = tmp_path / "oracle"
    write_json(
        run_dir / "run-summary.json",
        {
            "workflow_run_id": "run-1",
            "nodes": [
                {
                    "id": "G01",
                    "status": "needs_human",
                    "reason_code": "product_acceptance_open_questions",
                }
            ],
        },
    )
    write_json(
        oracle_dir / "expected-routing.json",
        {
            "nodes": [
                {
                    "id": "G01",
                    "expected": "pause_if_unresolved",
                    "reason_code": "product_acceptance_open_questions",
                }
            ]
        },
    )
    assert evaluate_run(run_dir, oracle_dir)["passed"] is True


def test_approved_gate_preserves_needs_human_audit_decision(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    oracle_dir = tmp_path / "oracle"
    write_json(
        run_dir / "run-summary.json",
        {
            "workflow_run_id": "run-1",
            "nodes": [
                {
                    "id": "G01",
                    "status": "completed",
                    "reason_code": "product_acceptance_open_questions",
                }
            ],
        },
    )
    write_json(oracle_dir / "expected-routing.json", {"nodes": []})
    write_json(
        oracle_dir / "expected-analysis.json",
        {
            "atomic_requirements": [],
            "implementation_facts": [],
            "alignment_findings": [],
            "open_questions": [],
            "minimum_expected_decision": {"gate": "G01", "status": "needs_human"},
        },
    )
    write_json(
        run_dir / "artifacts" / "g01-scope-review.json",
        {
            "payload": {
                "decision": "approved",
                "issues": [{"issue_code": "product_acceptance_open_question"}],
            }
        },
    )
    for name, key in (
        ("a02-requirement-analysis.json", "requirements"),
        ("a05-backend-change-analysis.json", "facts"),
        ("a06-alignment-result.json", "findings"),
        ("a03-technical-testability-analysis.json", "blocking_items"),
    ):
        write_json(run_dir / "artifacts" / name, {"payload": {key: []}})

    assert evaluate_run(run_dir, oracle_dir)["passed"] is True


def test_semantic_evaluation_uses_explicit_rules_and_one_to_one_matching(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    oracle_dir = tmp_path / "oracle"
    write_json(run_dir / "run-summary.json", {"workflow_run_id": "run-1", "nodes": []})
    write_json(oracle_dir / "expected-routing.json", {"nodes": []})
    write_json(
        oracle_dir / "expected-test-obligations.json",
        {
            "obligations": [
                {
                    "id": "TEST-1",
                    "summary": "普通指标结果集筛选",
                    "match": {"all_terms": ["普通指标", "结果集"]},
                },
                {
                    "id": "TEST-2",
                    "summary": "聚合指标结果集筛选",
                    "match": {"all_terms": ["聚合指标", "结果集"]},
                },
            ]
        },
    )
    write_json(
        run_dir / "artifacts" / "a08-test-design-ir.json",
        {
            "payload": {
                "parent_cases": [
                    {
                        "id": "CASE-1",
                        "title": "普通指标和聚合指标按结果集筛选",
                    }
                ]
            }
        },
    )

    result = evaluate_run(run_dir, oracle_dir)

    assert result["passed"] is False
    assert result["categories"]["test_obligations"] == {"passed": 1, "failed": 1, "total": 2}


def test_semantic_evaluation_does_not_use_undeclared_fuzzy_matching(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    oracle_dir = tmp_path / "oracle"
    write_json(run_dir / "run-summary.json", {"workflow_run_id": "run-1", "nodes": []})
    write_json(oracle_dir / "expected-routing.json", {"nodes": []})
    write_json(
        oracle_dir / "expected-analysis.json",
        {
            "atomic_requirements": [{"id": "REQ-ORACLE", "summary": "中文提示"}],
            "implementation_facts": [],
            "alignment_findings": [],
            "open_questions": [],
        },
    )
    write_json(
        run_dir / "artifacts" / "a02-requirement-analysis.json",
        {"payload": {"requirements": [{"id": "REQ-ACTUAL", "summary": "中文提示"}]}},
    )
    for name, key in (
        ("a05-backend-change-analysis.json", "facts"),
        ("a06-alignment-result.json", "findings"),
        ("a03-technical-testability-analysis.json", "blocking_items"),
    ):
        write_json(run_dir / "artifacts" / name, {"payload": {key: []}})

    result = evaluate_run(run_dir, oracle_dir)

    assert result["passed"] is False
    assert result["categories"]["atomic_requirements"]["failed"] == 1


def test_partial_run_reports_missing_semantic_artifacts_instead_of_crashing(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    oracle_dir = tmp_path / "oracle"
    write_json(run_dir / "run-summary.json", {"workflow_run_id": "run-1", "nodes": []})
    write_json(oracle_dir / "expected-routing.json", {"nodes": []})
    write_json(
        oracle_dir / "expected-analysis.json",
        {
            "atomic_requirements": [
                {
                    "id": "REQ-1",
                    "summary": "必须存在",
                    "match": {"all_terms": ["必须存在"]},
                }
            ],
            "implementation_facts": [],
            "alignment_findings": [],
            "open_questions": [],
        },
    )

    result = evaluate_run(run_dir, oracle_dir)

    assert result["passed"] is False
    assert result["categories"]["atomic_requirements"]["failed"] == 1
