"""TAPD story branch and Bug review gate tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from qa_agents.bug_review import apply_bug_review_decision, prepare_bug_review
from qa_agents.contracts import content_hash
from qa_agents.errors import ContractError, InputError
from qa_agents.tapd_submission import extract_tapd_story_id, submit_test_candidates


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _git_repository(root: Path) -> Path:
    repository = root / "target-repository"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=main")
    (repository / "README.md").write_text("test repository\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(
        repository,
        "-c", "user.name=Base",
        "-c", "user.email=base@example.invalid",
        "commit",
        "-m", "init",
    )
    return repository


def _landing(root: Path) -> Path:
    candidate_dir = root / "candidate-workspace" / "generated" / "backend"
    candidate_dir.mkdir(parents=True)
    candidate = candidate_dir / "test_case.py"
    candidate.write_text("def test_case():\n    assert True\n", encoding="utf-8")
    item = {
        "path": "generated/backend/test_case.py",
        "absolute_path": str(candidate),
        "content_hash": content_hash(candidate.read_text(encoding="utf-8")),
    }
    payload = {
        "schema_version": "n29-candidate-landing/1.0",
        "landed_files": [item],
    }
    artifact = {
        "producer": {"component_id": "N29"},
        "status": "completed",
        "payload": payload,
    }
    path = root / "landing.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


def _config(repository: Path) -> Path:
    value = {
        "schema_version": "test-repository-config/1.0",
        "repository_id": "pytest_for_bi",
        "repository_path": str(repository),
        "access_class": "approved_test_repository",
        "base_ref": "main",
        "remote": "origin",
        "push": False,
        "purpose": "temporary_shared_repository",
        "dedicated_results_repository_todo": True,
    }
    path = repository.parent / "repository-config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_extracts_visible_tapd_story_id_from_real_url_and_card_text() -> None:
    value = (
        "【深圳市昊一源】下钻查看明细提示文案优化\n"
        "https://www.tapd.cn/tapd_fe/20097211/story/detail/1120097211001406418\n"
        "ID: 1406418"
    )
    assert extract_tapd_story_id(value) == "1406418"
    assert extract_tapd_story_id(value.splitlines()[1]) == "1406418"


def test_extract_rejects_story_without_visible_id() -> None:
    with pytest.raises(InputError, match="paste the card text"):
        extract_tapd_story_id(
            "https://www.tapd.cn/tapd_fe/20097211/story/detail/999009721100123456"
        )


def test_submission_creates_and_reuses_one_story_branch(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    landing = _landing(tmp_path)
    config = _config(repository)
    story = "https://www.tapd.cn/tapd_fe/20097211/story/detail/1120097211001406418"

    first = submit_test_candidates(story, landing, config, tmp_path / "submission.json")
    second = submit_test_candidates(story, landing, config, tmp_path / "submission.json")

    assert first["branch"] == second["branch"] == "qa/tapd-story-1406418"
    assert first["branch_existed"] is False
    assert second["branch_existed"] is True
    assert second["commit_hash"] == first["commit_hash"]
    assert second["pushed"] is False
    assert second["storage_repository_disposition"]["dedicated_results_repository_required"] is True
    assert repository.joinpath(".qa-worktrees").exists() is False
    show = subprocess.run(
        [
            "git", "show", f"{first['branch']}:{first['submitted_files'][0]['path']}",
        ],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert "def test_case" in show.stdout


def test_prepare_bug_review_renders_required_human_table(tmp_path: Path) -> None:
    review_input = {
        "schema_version": "tapd-bug-review-input/1.0",
        "workflow_run_id": "run-1",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
        "tapd_story_id": "1406418",
        "tapd_story_url": "https://www.tapd.cn/story/1406418",
        "bug_candidates": [
            {
                "id": "BUG-001",
                "case_id": "CASE-001",
                "business_scenario": "查看统计图明细",
                "expected_behavior": "提示支持查看明细",
                "actual_problem": "提示不支持查看明细",
                "bug_explanation": "实际文案与冻结需求不一致",
                "test_data": [{"real_name": "收入", "id": "metric-001"}],
                "fingerprint": "sha256:1",
            }
        ],
    }
    input_path = tmp_path / "review-input.json"
    input_path.write_text(json.dumps(review_input, ensure_ascii=False), encoding="utf-8")
    artifact = prepare_bug_review(input_path, tmp_path / "out")
    card = (tmp_path / "out/tapd-bug-review-card.md").read_text(encoding="utf-8")

    assert artifact["status"] == "needs_human"
    for column in (
        "Case", "业务场景", "期望行为", "实际问题", "Bug 解释", "测试数据（真实的现实名称）", "ID"
    ):
        assert column in card
    assert "收入(ID:metric-001)" in card
    assert "blocked_until_human_approval" in json.dumps(artifact, ensure_ascii=False)


def test_rejected_bug_review_creates_round_two_retest_plan(tmp_path: Path) -> None:
    review_input = {
        "schema_version": "tapd-bug-review-input/1.0",
        "workflow_run_id": "run-1",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
        "tapd_story_id": "1406418",
        "bug_candidates": [
            {
                "id": "BUG-001",
                "case_id": "CASE-001",
                "business_scenario": "查看统计图明细",
                "expected_behavior": "提示支持查看明细",
                "actual_problem": "提示不支持查看明细",
                "bug_explanation": "实际文案与冻结需求不一致",
                "test_data": [{"real_name": "收入", "id": "metric-001"}],
            }
        ],
    }
    input_path = tmp_path / "review-input.json"
    input_path.write_text(json.dumps(review_input, ensure_ascii=False), encoding="utf-8")
    review = prepare_bug_review(input_path, tmp_path / "out")
    decision = {
        "schema_version": "bug-review-decision/1.0",
        "review_artifact_hash": review["artifact_hash"],
        "review_hash": review["payload"]["review_hash"],
        "decision": "rejected",
        "approver": "Alice",
        "bug_ids": ["BUG-001"],
        "comments": [
            {
                "bug_id": "BUG-001",
                "case_id": "CASE-001",
                "comment": "请先确认数据和 Case 是否正确",
            }
        ],
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(decision, ensure_ascii=False), encoding="utf-8")

    result = apply_bug_review_decision(
        decision_path,
        tmp_path / "out/artifacts/tapd-bug-review-request.json",
        tmp_path / "out",
    )

    assert result["payload"]["outcome"] == "retest_required"
    assert result["payload"]["tapd_registration_disposition"] == "not_registered"
    plan = json.loads(
        (tmp_path / "out/artifacts/tapd-bug-retest-plan.json").read_text(encoding="utf-8")
    )
    assert plan["payload"]["review_round"] == 2
    assert plan["payload"]["case_ids"] == ["CASE-001"]
    assert "verify_test_data_recipe" in plan["payload"]["required_checks"]


def test_approved_bug_review_defers_missing_tapd_adapter(tmp_path: Path) -> None:
    review_input = {
        "schema_version": "tapd-bug-review-input/1.0",
        "workflow_run_id": "run-1",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "snapshot-1",
        "tapd_story_id": "1406418",
        "bug_candidates": [
            {
                "id": "BUG-001",
                "case_id": "CASE-001",
                "business_scenario": "查看统计图明细",
                "expected_behavior": "提示支持查看明细",
                "actual_problem": "提示不支持查看明细",
                "bug_explanation": "实际文案与冻结需求不一致",
                "test_data": [{"real_name": "收入", "id": "metric-001"}],
            }
        ],
    }
    input_path = tmp_path / "review-input.json"
    input_path.write_text(json.dumps(review_input, ensure_ascii=False), encoding="utf-8")
    review = prepare_bug_review(input_path, tmp_path / "out")
    decision = {
        "schema_version": "bug-review-decision/1.0",
        "review_artifact_hash": review["artifact_hash"],
        "decision": "approved",
        "approver": "Alice",
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(decision, ensure_ascii=False), encoding="utf-8")

    result = apply_bug_review_decision(
        decision_path,
        tmp_path / "out/artifacts/tapd-bug-review-request.json",
        tmp_path / "out",
    )

    assert result["payload"]["next_node"] == "TAPD_BUG_ADAPTER"
    assert result["payload"]["tapd_registration_disposition"] == "pending_external_bug_adapter"
    assert result["reason_code"] == "tapd_bug_adapter_not_implemented"


def test_bug_review_requires_complete_human_columns(tmp_path: Path) -> None:
    value = {
        "schema_version": "tapd-bug-review-input/1.0",
        "workflow_run_id": "run-1",
        "source_snapshot_id": "snapshot-1",
        "tapd_story_id": "1406418",
        "bug_candidates": [
            {"case_id": "CASE-001", "test_data": [{"real_name": "收入"}]}
        ],
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ContractError, match="business_scenario"):
        prepare_bug_review(path, tmp_path / "out")
