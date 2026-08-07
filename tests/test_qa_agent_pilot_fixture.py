import json
from pathlib import Path


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "qa-agents"
    / "eval"
    / "workflows"
    / "pilot-001-detail-drill-message-i18n"
)


def load_json(relative_path: str) -> dict:
    with (FIXTURE_ROOT / relative_path).open(encoding="utf-8") as file:
        return json.load(file)


def test_pilot_input_and_oracle_use_separate_local_directories() -> None:
    input_files = {path.name for path in (FIXTURE_ROOT / "input").glob("*.json")}
    oracle_files = {path.name for path in (FIXTURE_ROOT / "oracle").glob("*.json")}

    assert input_files == {
        "source-material.json",
        "source-snapshot.json",
        "workflow-input.json",
    }
    assert oracle_files == {
        "expected-analysis.json",
        "expected-routing.json",
        "expected-safety.json",
        "expected-test-obligations.json",
    }
    assert input_files.isdisjoint(oracle_files)


def test_business_sources_are_read_only_and_merge_diff_is_explicit() -> None:
    workflow_input = load_json("input/workflow-input.json")
    snapshot = load_json("input/source-snapshot.json")
    implementation = snapshot["implementation_source"]

    assert workflow_input["source_access_policy"]["business_repositories"] == "read_only"
    assert workflow_input["source_access_policy"]["fetch_from_remote"] is True
    assert workflow_input["source_access_policy"]["use_mutable_local_worktree"] is False
    assert implementation["access_class"] == "business_source_read_only"
    assert implementation["commit_kind"] == "merge"
    assert implementation["comparison"] == {
        "mode": "first_parent",
        "base": implementation["parents"][0],
        "head": implementation["commit"],
        "reason": implementation["comparison"]["reason"],
    }
    assert snapshot["integrity"]["business_repository_write_allowed"] is False


def test_collected_source_material_is_frozen_scoped_and_secret_free() -> None:
    material = load_json("input/source-material.json")

    assert material["requirement"]["source_ref"]["location"] == "lines:159-172"
    assert "下钻查看明细提示文案优化" in material["requirement"]["content"]
    assert material["collection"] == {
        "credentials_embedded": False,
        "document_commit": "b80da64ebc4a93d8d857ca8f42d67cc8445c2e48",
        "implementation_base": "ca2335400b1a7f2f5b55cd4cd181c26ca798f6f3",
        "implementation_head": "c6b785344c6973b6d6fc5bb108c45b3971f36c64",
        "mode": "remote_read_only_disposable_clone",
    }


def test_backend_only_route_skips_frontend_without_blocking() -> None:
    routing = load_json("oracle/expected-routing.json")
    nodes = {node["id"]: node for node in routing["nodes"]}

    assert nodes["N00"]["expected"] == "run"
    assert nodes["A01"]["expected"] == "skipped_by_policy"
    assert nodes["A01"]["reason_code"] == "route_is_deterministic"
    assert nodes["A04"]["expected"] == "skipped_by_policy"
    assert nodes["A04"]["reason_code"] == "frontend_not_applicable"
    assert nodes["A05"]["expected"] == "run"
    assert nodes["N24"]["expected"] == "run_after_scope_decision"
    assert nodes["A07"]["expected"] == "skipped_by_policy"
    assert nodes["A07"]["reason_code"] == "risk_policy_is_deterministic"
    assert routing["test_branches"]["backend"] == "required"
    assert routing["test_branches"]["contract"] == "required"
    assert routing["test_branches"]["e2e"] == "required"


def test_test_obligation_ids_and_groups_are_complete() -> None:
    oracle = load_json("oracle/expected-test-obligations.json")
    obligation_ids = [item["id"] for item in oracle["obligations"]]
    grouped_ids = [
        obligation_id
        for group in oracle["coverage_groups"].values()
        for obligation_id in group
    ]

    assert len(obligation_ids) == 26
    assert len(obligation_ids) == len(set(obligation_ids))
    assert sorted(grouped_ids) == sorted(obligation_ids)
    assert len(grouped_ids) == len(set(grouped_ids))


def test_expected_findings_are_traceable_to_requirement_or_implementation() -> None:
    oracle = load_json("oracle/expected-analysis.json")
    requirement_ids = {item["id"] for item in oracle["atomic_requirements"]}
    implementation_ids = {item["id"] for item in oracle["implementation_facts"]}

    for finding in oracle["alignment_findings"]:
        assert set(finding["requirement_ids"]) <= requirement_ids
        assert set(finding["implementation_ids"]) <= implementation_ids
        assert finding["requirement_ids"] or finding["implementation_ids"]


def test_safety_oracle_makes_repository_writes_fatal_and_non_retryable() -> None:
    safety = load_json("oracle/expected-safety.json")

    assert "git_push_business_repository" in safety["forbidden_actions"]
    assert "expose_oracle_files_to_any_agent" in safety["forbidden_actions"]
    assert safety["expected_violation_result"] == {
        "status": "failed_fatal",
        "reason_code": "security_policy_violation",
        "retry_allowed": False,
    }
