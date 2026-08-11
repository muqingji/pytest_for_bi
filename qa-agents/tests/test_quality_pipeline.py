import json
from pathlib import Path

import pytest

from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer
from qa_agents.errors import ContractError
from qa_agents.quality_pipeline import run_server_quality_tail


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "server-run-1"
SNAPSHOT_ID = "snapshot-server-1"


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _artifact(
    path: Path,
    component_id: str,
    artifact_id: str,
    payload: dict,
    *,
    status: ArtifactStatus = ArtifactStatus.COMPLETED,
    run_id: str = RUN_ID,
) -> Path:
    envelope = ArtifactEnvelope(
        workflow_run_id=run_id,
        workflow_mode="new_requirement",
        artifact_id=artifact_id,
        source_snapshot_id=SNAPSHOT_ID,
        producer=Producer(component_id, runtime="deterministic"),
        payload=payload,
        status=status,
    )
    return _write(path, envelope.to_dict())


def _inputs(
    tmp_path: Path, *, manual: bool = True, production_isolation: bool = True
) -> dict[str, object]:
    cases = [
        {
            "id": "CASE-AUTO",
            "title": "后端自动化",
            "priority": "P0",
            "risk": "critical",
            "steps": ["调用服务端接口"],
            "expected": [{"description": "返回成功"}],
        }
    ]
    actions = [
        {"case_id": "CASE-AUTO", "action": "generate_new", "reason_code": "new"}
    ]
    if manual:
        cases.append(
            {
                "id": "CASE-MANUAL",
                "title": "人工核对服务端数据",
                "priority": "P0",
                "risk": "critical",
                "steps": ["查询真实结果"],
                "expected": [{"description": "结果一致"}],
            }
        )
        actions.append(
            {"case_id": "CASE-MANUAL", "action": "manual_run", "reason_code": "manual"}
        )
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
    precheck = _artifact(
        tmp_path / "n07.json",
        "N07",
        "n07-environment-precheck",
        {
            "schema_version": "n07-environment-precheck/1.0",
            "environment_fingerprint": "sha256:" + "1" * 64,
            "environment_class": "production_isolated_test",
            "production_isolation": production_isolation,
            "decision": "passed",
            "next_node": "N08",
        },
    )
    execution = _artifact(
        tmp_path / "n08.json",
        "N08",
        "n08-automation-execution",
        {
            "schema_version": "n08-automation-execution/1.0",
            "environment_fingerprint": "sha256:" + "1" * 64,
            "next_node": "N09",
            "shards": [
                {
                    "shard_id": "N08-S001",
                    "case_ids": ["CASE-AUTO"],
                    "outcome": "passed",
                    "stdout": "1 passed",
                    "stderr": "",
                    "duration_ms": 10,
                    "junit_summary": {
                        "tests": 1,
                        "failures": 0,
                        "errors": 0,
                        "skipped": 0,
                    },
                }
            ],
        },
    )
    return {"plan": plan, "compiled": compiled, "precheck": precheck, "execution": execution}


def _manual_results(tmp_path: Path, *, status: str = "passed", classification: str | None = None) -> Path:
    result = {
        "case_id": "CASE-MANUAL",
        "status": status,
        "actual_result": "服务端数据与冻结期望一致" if status == "passed" else "返回值不一致",
        "executor": {"id": "qa-owner", "role": "qa_owner"},
        "evidence": [{"type": "log", "id": "evidence-1"}],
    }
    if classification:
        result["classification"] = classification
    return _write(
        tmp_path / "manual.json",
        {
            "schema_version": "manual-test-results/1.0",
            "workflow_run_id": RUN_ID,
            "source_snapshot_id": SNAPSHOT_ID,
            "results": [result],
        },
    )


def _run(tmp_path: Path, inputs: dict[str, object], **kwargs: object) -> dict:
    return run_server_quality_tail(
        inputs["plan"],
        inputs["compiled"],
        inputs["precheck"],
        tmp_path / "out",
        automation_execution_paths=[inputs["execution"]],
        quality_policy_path=ROOT / "policies/quality-policy.json",
        **kwargs,
    )


def test_server_quality_tail_reaches_report_with_all_results(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    result = _run(tmp_path, inputs, manual_results_path=_manual_results(tmp_path))

    assert result["decision"] == "passed_with_warning"
    assert result["metrics"] == {
        "planned": 2,
        "executed": 2,
        "passed": 2,
        "failed": 0,
        "pending": 0,
        "skipped": 0,
        "deferred": 0,
        "quarantined": 0,
    }
    assert (tmp_path / "out/artifacts/a19-failure-triage.json").exists()
    report = json.loads((tmp_path / "out/server-quality-report.json").read_text())
    assert report["decision"] == "passed_with_warning"
    assert (tmp_path / "out/server-quality-report.html").exists()
    assert (tmp_path / "out/artifacts/n09-evidence.json").exists()
    assert (tmp_path / "out/artifacts/n11-quality-decision.json").exists()
    assert (tmp_path / "out/artifacts/n12-quality-report.json").exists()


def test_missing_manual_results_is_inconclusive_not_passed(tmp_path: Path) -> None:
    result = _run(tmp_path, _inputs(tmp_path))

    assert result["decision"] == "inconclusive"
    assert result["metrics"]["pending"] == 1
    n17 = json.loads((tmp_path / "out/artifacts/n17-manual-execution.json").read_text())
    assert n17["status"] == "needs_human"
    assert n17["payload"]["tasks"][0]["status"] == "pending"


def test_server_quality_updates_run_manifest_after_artifacts_complete(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    manifest_path = _write(
        tmp_path / "run-manifest.json",
        {
            "schema_version": "test-run/1.0",
            "workflow_run_id": RUN_ID,
            "source_snapshot_id": SNAPSHOT_ID,
            "current_node": "N15",
        },
    )

    result = _run(tmp_path, inputs, run_manifest_path=manifest_path)

    manifest = json.loads(manifest_path.read_text())
    assert result["current_node"] == "N17"
    assert manifest["current_node"] == "N17"
    assert manifest["server_quality"]["status"] == "inconclusive"
    assert manifest["server_quality"]["metrics"]["pending"] == 1
    assert manifest["server_quality"]["n12_artifact_hash"].startswith("sha256:")
    assert manifest["server_quality"]["n23_artifact_hash"].startswith("sha256:")


def test_reference_environment_cannot_be_release_eligible(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        _inputs(tmp_path, manual=False, production_isolation=False),
    )

    assert result["decision"] == "inconclusive"
    assert result["release_disposition"] == "pending"
    n11 = json.loads((tmp_path / "out/artifacts/n11-quality-decision.json").read_text())
    assert "environment_not_production_isolated" in n11["payload"]["warnings"]


def test_product_failure_is_blocked_and_deduplicated(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    history = _write(
        tmp_path / "bugs.json",
        {"schema_version": "bug-history/1.0", "bugs": []},
    )
    result = _run(
        tmp_path,
        inputs,
        manual_results_path=_manual_results(
            tmp_path, status="failed", classification="product_defect"
        ),
        bug_history_path=history,
    )

    assert result["decision"] == "blocked"
    dedup = json.loads((tmp_path / "out/artifacts/n20-defect-dedup.json").read_text())
    assert dedup["payload"]["decisions"][0]["disposition"] == "create_new"
    drafts = json.loads((tmp_path / "out/bug-drafts.json").read_text())
    assert len(drafts["drafts"]) == 1


def test_retryable_execution_uses_n10_budget(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, manual=False)
    inputs["execution"] = _artifact(
        tmp_path / "n08-retry.json",
        "N08",
        "n08-automation-execution",
        {
            "schema_version": "n08-automation-execution/1.0",
            "environment_fingerprint": "sha256:" + "1" * 64,
            "next_node": "N10",
            "shards": [
                {
                    "shard_id": "N08-S001",
                    "case_ids": ["CASE-AUTO"],
                    "outcome": "timed_out",
                    "stdout": "",
                    "stderr": "timeout",
                    "duration_ms": 30000,
                    "junit_summary": {"tests": 0},
                }
            ],
        },
        status=ArtifactStatus.FAILED_RETRYABLE,
    )
    result = _run(tmp_path, inputs)

    assert result["decision"] == "blocked"
    n10 = json.loads((tmp_path / "out/artifacts/n10-retry-budget.json").read_text())
    assert n10["payload"]["decision"] == "retry_allowed"
    assert n10["payload"]["next_node"] == "N07"


def test_server_quality_tail_rejects_cross_run_execution(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, manual=False)
    original = json.loads(Path(inputs["execution"]).read_text())
    inputs["execution"] = _artifact(
        tmp_path / "n08-other.json",
        "N08",
        "n08-automation-execution",
        original["payload"],
        run_id="other-run",
    )

    with pytest.raises(ContractError, match="different workflow runs"):
        _run(tmp_path, inputs)


def test_failed_manual_result_requires_classification(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="requires classification"):
        _run(
            tmp_path,
            _inputs(tmp_path),
            manual_results_path=_manual_results(tmp_path, status="failed"),
        )


def test_a19_reclassifies_needs_triage_before_quality_decision(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, manual=False)
    original = json.loads(Path(inputs["execution"]).read_text())
    payload = dict(original["payload"])
    payload["shards"] = [
        {
            "shard_id": "N08-S001",
            "case_ids": ["CASE-AUTO"],
            "outcome": "failed",
            "stdout": "mystery failure without markers",
            "stderr": "",
            "duration_ms": 12,
            "junit_summary": {"tests": 1, "failures": 1, "errors": 0, "skipped": 0},
        }
    ]
    inputs["execution"] = _artifact(
        tmp_path / "n08-triage.json",
        "N08",
        "n08-automation-execution",
        payload,
        status=ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    # Force needs_triage by using unclassified text that _auto_classification maps to needs_triage
    result = _run(tmp_path, inputs)
    a19 = json.loads((tmp_path / "out/artifacts/a19-failure-triage.json").read_text())
    assert a19["payload"]["input_cluster_count"] >= 1
    assert result["decision"] in {"blocked", "inconclusive"}


def test_flaky_quarantine_blocks_required_case(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, manual=False)
    quarantine = _write(
        tmp_path / "flaky.json",
        {
            "schema_version": "flaky-quarantine/1.0",
            "cases": [
                {
                    "case_id": "CASE-AUTO",
                    "status": "quarantined",
                    "owner": "qa-owner",
                    "reason": "intermittent environment flake",
                    "expires_at": "2099-01-01T00:00:00+00:00",
                    "fingerprint": "sha256:" + "f" * 64,
                }
            ],
        },
    )
    result = _run(tmp_path, inputs, flaky_quarantine_path=quarantine)
    assert result["decision"] == "blocked"
    assert result["metrics"]["quarantined"] == 1
    n11 = json.loads((tmp_path / "out/artifacts/n11-quality-decision.json").read_text())
    assert "CASE-AUTO" in n11["payload"]["flaky_quarantine"]["critical_case_ids"]


def test_n18_reads_coverage_summary_from_n08_shards(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, manual=False)
    original = json.loads(Path(inputs["execution"]).read_text())
    payload = dict(original["payload"])
    payload["shards"] = [
        {
            "shard_id": "N08-S001",
            "case_ids": ["CASE-AUTO"],
            "outcome": "passed",
            "stdout": "1 passed",
            "stderr": "",
            "duration_ms": 10,
            "junit_summary": {"tests": 1, "failures": 0, "errors": 0, "skipped": 0},
            "coverage_summary": {
                "statement_coverage_percent": 88.5,
                "covered_lines": 88,
                "num_statements": 100,
            },
        }
    ]
    inputs["execution"] = _artifact(
        tmp_path / "n08-cov.json",
        "N08",
        "n08-automation-execution",
        payload,
    )
    result = _run(tmp_path, inputs)
    n18 = json.loads((tmp_path / "out/artifacts/n18-quality-signals.json").read_text())
    assert n18["payload"]["signals"]["statement_coverage_percent"] == 88.5
    assert n18["payload"]["gaps"] == []
    assert n18["status"] == "completed"
    assert result["decision"] in {"passed", "passed_with_warning", "inconclusive"}
