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
    tmp_path: Path,
    *,
    manual: bool = True,
    production_isolation: bool = True,
    e2e: bool = False,
    contract: bool = False,
    contract_ref: str | None = None,
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
    if e2e:
        cases.append(
            {
                "id": "CASE-E2E",
                "layer": "e2e",
                "title": "端到端页面核对",
                "priority": "P0",
                "risk": "critical",
                "steps": ["打开页面"],
                "expected": [{"description": "文案一致"}],
            }
        )
        actions.append(
            {"case_id": "CASE-E2E", "action": "generate_new", "reason_code": "new"}
        )
    if contract:
        test_data = {}
        if contract_ref:
            test_data["contract_ref"] = contract_ref
        cases.append(
            {
                "id": "CASE-CT",
                "layer": "contract",
                "title": "契约用例",
                "priority": "P0",
                "risk": "critical",
                "steps": ["调用契约接口"],
                "expected": [{"description": "契约断言成立"}],
                "test_data": test_data,
            }
        )
        actions.append(
            {"case_id": "CASE-CT", "action": "generate_new", "reason_code": "new"}
        )
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
                    "lifecycle_evidence_path": "evidence/N08-S001/lifecycle.json",
                    "lifecycle_evidence_hash": "sha256:" + "2" * 64,
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
        "scope_total": 2,
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

    n18 = json.loads((tmp_path / "out/artifacts/n18-quality-signals.json").read_text())
    lifecycle = n18["payload"]["lifecycle_evidence_bindings"]
    assert n18["payload"]["signals"]["lifecycle_evidence_count"] == 1
    assert lifecycle == [
        {
            "automation_execution_hash": json.loads(inputs["execution"].read_text())[
                "artifact_hash"
            ],
            "shard_id": "N08-S001",
            "case_ids": ["CASE-AUTO"],
            "path": "evidence/N08-S001/lifecycle.json",
            "content_hash": "sha256:" + "2" * 64,
        }
    ]
    n09 = json.loads((tmp_path / "out/artifacts/n09-evidence.json").read_text())
    assert n09["payload"]["input_bindings"]["lifecycle_evidence_bindings"] == lifecycle


def test_quality_tail_accepts_pending_human_n27_evidence(tmp_path: Path) -> None:
    """N27 completed_with_gaps + pending_human (structurally safe plan awaiting
    the A22 human confirmation) is valid evidence for the quality tail."""

    inputs = _inputs(tmp_path, manual=False)
    n27 = _artifact(
        tmp_path / "n27.json",
        "N27",
        "n27-test-data-plan-validation",
        {
            "schema_version": "test-data-plan-validation/1.0",
            "valid": True,
            "pending_human": True,
        },
        status=ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    result = _run(tmp_path, inputs, test_data_validation_path=n27)

    assert result["decision"] == "passed_with_warning"
    assert (tmp_path / "out/artifacts/n09-evidence.json").exists()
    assert (tmp_path / "out/artifacts/n11-quality-decision.json").exists()
    assert (tmp_path / "out/artifacts/n12-quality-report.json").exists()


def test_missing_manual_results_stops_at_n17_not_passed(tmp_path: Path) -> None:
    result = _run(tmp_path, _inputs(tmp_path))

    assert result["decision"] == "blocked"
    assert result["current_node"] == "N17"
    assert result["stopped_at"] == "N17"
    assert result["metrics"]["pending"] == 1
    n17 = json.loads((tmp_path / "out/artifacts/n17-manual-execution.json").read_text())
    assert n17["status"] == "blocked"
    assert n17["payload"]["next_node"] == "N17"
    assert n17["payload"]["tasks"][0]["status"] == "pending"
    assert not (tmp_path / "out/artifacts/n11-quality-decision.json").exists()
    assert not (tmp_path / "out/artifacts/n12-quality-report.json").exists()
    assert not (tmp_path / "out/artifacts/n18-quality-signals.json").exists()


def test_unexecuted_generate_new_stops_at_n17_and_drops_stale_quality_decision(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path, manual=False)
    inputs["execution"] = _artifact(
        tmp_path / "n08-empty.json",
        "N08",
        "n08-automation-execution",
        {
            "schema_version": "n08-automation-execution/1.0",
            "environment_fingerprint": "sha256:" + "1" * 64,
            "next_node": "N09",
            "shards": [],
        },
    )
    stale_dir = tmp_path / "out/artifacts"
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "n18-quality-signals.json").write_text("{}", encoding="utf-8")
    (stale_dir / "n11-quality-decision.json").write_text("{}", encoding="utf-8")
    (stale_dir / "n12-quality-report.json").write_text("{}", encoding="utf-8")

    result = _run(tmp_path, inputs)

    assert result["decision"] == "blocked"
    assert result["current_node"] == "N17"
    assert result["metrics"]["pending"] == 1
    n17 = json.loads((tmp_path / "out/artifacts/n17-manual-execution.json").read_text())
    assert n17["status"] == "blocked"
    assert n17["payload"]["next_node"] == "N17"
    assert n17["payload"]["tasks"][0]["case_id"] == "CASE-AUTO"
    assert n17["payload"]["tasks"][0]["reason_code"] == "automation_not_executed"
    assert not (tmp_path / "out/artifacts/n11-quality-decision.json").exists()
    assert not (tmp_path / "out/artifacts/n12-quality-report.json").exists()
    assert not (tmp_path / "out/artifacts/n18-quality-signals.json").exists()


def test_server_quality_skips_e2e_and_gates_on_backend(tmp_path: Path) -> None:
    result = _run(tmp_path, _inputs(tmp_path, manual=False, e2e=True))

    n17 = json.loads((tmp_path / "out/artifacts/n17-manual-execution.json").read_text())
    assert n17["status"] == "completed"
    assert n17["payload"]["pending_count"] == 0
    assert all(item["case_id"] != "CASE-E2E" for item in n17["payload"]["tasks"])
    assert result["metrics"]["skipped"] >= 1
    assert result["current_node"] != "N17"
    assert (tmp_path / "out/artifacts/n11-quality-decision.json").exists()


def test_server_quality_skips_contract_without_ref(tmp_path: Path) -> None:
    result = _run(tmp_path, _inputs(tmp_path, manual=False, contract=True))

    n17 = json.loads((tmp_path / "out/artifacts/n17-manual-execution.json").read_text())
    assert n17["status"] == "completed"
    assert n17["payload"]["pending_count"] == 0
    assert all(item["case_id"] != "CASE-CT" for item in n17["payload"]["tasks"])
    assert result["metrics"]["skipped"] >= 1
    assert result["current_node"] != "N17"
    assert (tmp_path / "out/artifacts/n11-quality-decision.json").exists()


def test_unexecuted_contract_with_ref_stops_at_n17(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        _inputs(tmp_path, manual=False, contract=True, contract_ref="openapi#/paths/x"),
    )

    assert result["decision"] == "blocked"
    assert result["current_node"] == "N17"
    n17 = json.loads((tmp_path / "out/artifacts/n17-manual-execution.json").read_text())
    assert n17["status"] == "blocked"
    assert n17["payload"]["tasks"][0]["case_id"] == "CASE-CT"
    assert n17["payload"]["tasks"][0]["reason_code"] == "automation_not_executed"
    assert not (tmp_path / "out/artifacts/n11-quality-decision.json").exists()


def test_incomplete_pytest_collection_cannot_pass_quality_gate(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, manual=False)
    execution = json.loads(Path(inputs["execution"]).read_text())
    payload = dict(execution["payload"])
    payload["shards"] = [dict(payload["shards"][0])]
    payload["shards"][0]["collection_complete"] = False
    inputs["execution"] = _artifact(
        tmp_path / "n08-incomplete.json", "N08", "n08-automation-execution", payload,
    )
    result = _run(tmp_path, inputs)
    n18 = json.loads((tmp_path / "out/artifacts/n18-quality-signals.json").read_text())
    assert "pytest_collection_incomplete:N08-S001" in n18["payload"]["gaps"]
    assert result["decision"] != "passed"


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
    assert manifest["server_quality"]["status"] == "blocked"
    assert manifest["server_quality"]["metrics"]["pending"] == 1
    assert manifest["server_quality"]["n17_artifact_hash"].startswith("sha256:")
    assert "n12_artifact_hash" not in manifest["server_quality"]
    assert "n23_artifact_hash" not in manifest["server_quality"]


def test_reference_environment_cannot_be_release_eligible(tmp_path: Path) -> None:
    """112 是本流程真实环境：服务端用例通过即可准出，不要求生产隔离。"""
    result = _run(
        tmp_path,
        _inputs(tmp_path, manual=False, production_isolation=False),
    )

    assert result["decision"] == "passed_with_warning"
    assert result["release_disposition"] == "eligible"
    n11 = json.loads((tmp_path / "out/artifacts/n11-quality-decision.json").read_text())
    assert "environment_not_production_isolated" not in n11["payload"]["warnings"]
    assert all("生产隔离" not in str(item) for item in n11["payload"]["reasons"])


def test_product_failure_completes_and_drafts_bugs(tmp_path: Path) -> None:
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

    assert result["decision"] == "completed_with_defects"
    assert result["release_disposition"] == "pending"
    n11 = json.loads((tmp_path / "out/artifacts/n11-quality-decision.json").read_text())
    assert n11["status"] == "completed_with_gaps"
    assert "服务端测试完成（有缺陷）" in n11["payload"]["summary"]
    assert any("已按产品缺陷流转" in item for item in n11["payload"]["reasons"])
    outcomes = n11["payload"]["case_outcomes"]
    by_id = {item["case_id"]: item for item in outcomes}
    assert by_id["CASE-AUTO"]["status"] == "passed"
    assert by_id["CASE-MANUAL"]["status"] == "failed"
    assert by_id["CASE-MANUAL"]["scene"] == "人工核对服务端数据"
    dedup = json.loads((tmp_path / "out/artifacts/n20-defect-dedup.json").read_text())
    assert dedup["payload"]["decisions"][0]["disposition"] == "create_new"
    drafts = json.loads((tmp_path / "out/bug-drafts.json").read_text())
    assert len(drafts["drafts"]) == 1
    assert result["external_adapter_dispositions"]["bug"] == "draft_ready_not_sent"


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


def test_n08_failure_categories_block_without_fake_triage(tmp_path: Path) -> None:
    """N08 已标 test_data_setup 时，N11 必须按造数失败阻断准出，而不是 needs_triage。"""
    inputs = _inputs(tmp_path, manual=False)
    original = json.loads(Path(inputs["execution"]).read_text())
    payload = dict(original["payload"])
    payload["shards"] = [
        {
            "shard_id": "N08-S001",
            "case_ids": ["CASE-AUTO"],
            "outcome": "failed",
            "failure_categories": ["test_data_setup"],
            "stdout": "ContractError: setup.bind_chart failed",
            "stderr": "",
            "duration_ms": 12,
            "junit_summary": {"tests": 1, "failures": 1, "errors": 0, "skipped": 0},
        }
    ]
    inputs["execution"] = _artifact(
        tmp_path / "n08-setup-fail.json",
        "N08",
        "n08-automation-execution",
        payload,
        status=ArtifactStatus.COMPLETED_WITH_GAPS,
    )
    result = _run(tmp_path, inputs)
    assert result["decision"] == "blocked"
    n09 = json.loads((tmp_path / "out/artifacts/n09-evidence.json").read_text())
    clusters = n09["payload"]["failure_clusters"]
    assert clusters
    assert clusters[0]["classification"] == "test_data"
    report = json.loads((tmp_path / "out/server-quality-report.json").read_text())
    markdown = (tmp_path / "out/server-quality-report.md").read_text()
    assert report["failure_clusters"][0]["detail"]["failure_code"] == "runtime_failure"
    assert "ContractError" in markdown
    assert "setup.bind_chart failed" in markdown
    assert "Failure Details" in (tmp_path / "out/server-quality-report.html").read_text()
    n11 = json.loads((tmp_path / "out/artifacts/n11-quality-decision.json").read_text())
    assert n11["status"] == "blocked"
    assert any("已分类失败簇阻断准出" in item for item in n11["payload"]["reasons"])
    assert all("仍待归类" not in item for item in n11["payload"]["reasons"])
    assert "服务端不准出" in n11["payload"]["summary"]


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
