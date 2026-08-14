from __future__ import annotations

import json

from scripts.reconcile_multica_issue_states import (
    expected_issue_state,
    run_failure_kind,
    run_result_status,
)


def test_run_result_status_reads_completed_business_result() -> None:
    run = {"result": {"output": json.dumps({"status": "needs_human"})}}
    assert run_result_status(run) == "needs_human"


def test_run_result_status_fails_closed_for_invalid_output() -> None:
    assert run_result_status({"result": {"output": "not-json"}}) == ""
    assert run_result_status(None) == ""


def test_completed_agent_result_closes_stale_in_progress_issue() -> None:
    issue = {"status": "in_progress"}
    run = {"status": "completed", "result": {"output": json.dumps({"status": "completed_with_gaps"})}}

    assert expected_issue_state(issue, run, accepted=False) == (
        "done",
        "agent_result_completed_with_gaps",
    )


def test_completed_needs_human_result_blocks_stale_in_progress_issue() -> None:
    issue = {"status": "in_progress"}
    run = {"status": "completed", "result": {"output": json.dumps({"status": "needs_human"})}}

    assert expected_issue_state(issue, run, accepted=False) == (
        "blocked",
        "agent_result_needs_human",
    )


def test_unknown_completed_result_preserves_current_issue_state() -> None:
    issue = {"status": "in_progress"}
    run = {"status": "completed", "result": {"output": "not-json"}}

    assert expected_issue_state(issue, run, accepted=False) == ("in_progress", None)


def test_completed_result_does_not_override_a_contract_blocked_issue() -> None:
    issue = {"status": "blocked"}
    run = {"status": "completed", "result": {"output": json.dumps({"status": "completed_with_gaps"})}}

    assert expected_issue_state(issue, run, accepted=False) == ("blocked", None)


def test_active_run_restores_planning_or_blocked_issue() -> None:
    run = {"status": "running"}

    assert expected_issue_state({"status": "todo"}, run, accepted=False) == (
        "in_progress",
        "active_agent_run",
    )
    assert expected_issue_state({"status": "blocked"}, run, accepted=False) == (
        "in_progress",
        "active_agent_run",
    )


def test_deferred_retry_is_still_in_progress() -> None:
    assert expected_issue_state(
        {"status": "todo"}, {"status": "deferred"}, accepted=False
    ) == ("in_progress", "active_agent_run")


def test_failed_run_never_remains_in_planning() -> None:
    assert expected_issue_state(
        {"status": "todo"}, {"status": "failed"}, accepted=False
    ) == ("blocked", "agent_run_failed")


def test_provider_failures_are_classified_for_circuit_breaking() -> None:
    assert run_failure_kind(
        {"status": "failed", "error": "403 Forbidden: subscription quota insufficient"}
    ) == "provider_subscription_quota"
    assert run_failure_kind(
        {"status": "failed", "failure_reason": "agent_error.provider_network"}
    ) == "provider_network"
