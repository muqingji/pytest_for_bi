"""N03/N04 deterministic contract validators."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import ArtifactStatus, ValidationIssue


ARTIFACT_REQUIRED = {
    "workflow_run_id",
    "workflow_mode",
    "schema_version",
    "artifact_id",
    "artifact_hash",
    "source_snapshot_id",
    "producer",
    "created_at",
    "status",
    "evidence_refs",
    "payload",
}

CASE_REQUIRED = {
    "id",
    "title",
    "intent_ids",
    "layer",
    "risk",
    "priority",
    "source_refs",
    "preconditions",
    "test_data",
    "steps",
    "expected",
    "cleanup",
    "execution_policy",
    "automation_candidate",
}


def validate_artifact(value: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for key in sorted(ARTIFACT_REQUIRED - set(value)):
        issues.append(
            ValidationIssue("artifact_required_field", f"Missing {key}", key, "producer")
        )
    status = value.get("status")
    if status is not None and status not in {item.value for item in ArtifactStatus}:
        issues.append(
            ValidationIssue("artifact_invalid_status", f"Unknown status {status}", "status", "producer")
        )
    return issues


def validate_test_case_ir(cases: list[Mapping[str, Any]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_case_ids: set[str] = set()
    seen_expected_ids: set[tuple[str, str]] = set()

    for index, case in enumerate(cases):
        path = f"cases[{index}]"
        case_id = str(case.get("id", "")) or None
        for key in sorted(CASE_REQUIRED - set(case)):
            issues.append(
                ValidationIssue(
                    "case_required_field",
                    f"Missing {key}",
                    f"{path}.{key}",
                    "A08",
                    case_id=case_id,
                )
            )
        if case_id:
            if case_id in seen_case_ids:
                issues.append(
                    ValidationIssue(
                        "duplicate_case_id", case_id, f"{path}.id", "A08", case_id=case_id
                    )
                )
            seen_case_ids.add(case_id)

        if not case.get("source_refs"):
            issues.append(
                ValidationIssue(
                    "missing_source_ref",
                    "Case has no source evidence",
                    f"{path}.source_refs",
                    "A08",
                    case_id=case_id,
                )
            )
        if not case.get("steps"):
            issues.append(
                ValidationIssue(
                    "missing_steps", "Case has no steps", f"{path}.steps", "A08", case_id=case_id
                )
            )

        if not isinstance(case.get("test_data"), Mapping):
            issues.append(
                ValidationIssue(
                    "invalid_test_data_type",
                    "Case test_data must be an object",
                    f"{path}.test_data",
                    "A08",
                    case_id=case_id,
                )
            )

        execution_policy = case.get("execution_policy")
        if not isinstance(execution_policy, Mapping):
            issues.append(
                ValidationIssue(
                    "invalid_execution_policy_type",
                    "Case execution_policy must be an object",
                    f"{path}.execution_policy",
                    "A08",
                    case_id=case_id,
                )
            )
            allowed_modes: set[str] = set()
        else:
            raw_modes = execution_policy.get("allowed_modes")
            allowed_modes = set(raw_modes) if isinstance(raw_modes, list) else set()
            if not allowed_modes:
                issues.append(
                    ValidationIssue(
                        "missing_execution_modes",
                        "Case execution_policy.allowed_modes must be a non-empty list",
                        f"{path}.execution_policy.allowed_modes",
                        "A08",
                        case_id=case_id,
                    )
                )

        for expected_index, expected in enumerate(case.get("expected", [])):
            expected_path = f"{path}.expected[{expected_index}]"
            expected_id = str(expected.get("id", "")) or None
            key = (case_id or "", expected_id or "")
            if expected_id and key in seen_expected_ids:
                issues.append(
                    ValidationIssue(
                        "duplicate_expected_id",
                        expected_id,
                        f"{expected_path}.id",
                        "A08",
                        case_id=case_id,
                        expected_id=expected_id,
                    )
                )
            seen_expected_ids.add(key)
            oracle = expected.get("oracle")
            if not isinstance(oracle, Mapping):
                issues.append(
                    ValidationIssue(
                        "missing_oracle",
                        "Expected result has no Oracle",
                        f"{expected_path}.oracle",
                        "A08",
                        case_id=case_id,
                        expected_id=expected_id,
                    )
                )
                continue
            required_oracle = {"type", "observation_point", "matcher", "source_ref"}
            for key_name in sorted(required_oracle - set(oracle)):
                issues.append(
                    ValidationIssue(
                        "oracle_required_field",
                        f"Oracle missing {key_name}",
                        f"{expected_path}.oracle.{key_name}",
                        "A08",
                        case_id=case_id,
                        expected_id=expected_id,
                    )
                )
            if "type" in oracle and oracle.get("type") not in {
                "deterministic",
                "human_review",
            }:
                issues.append(
                    ValidationIssue(
                        "oracle_invalid_type",
                        "Oracle type must be deterministic or human_review",
                        f"{expected_path}.oracle.type",
                        "A08",
                        case_id=case_id,
                        expected_id=expected_id,
                    )
                )
            if "observation_point" in oracle and not str(
                oracle.get("observation_point", "")
            ).strip():
                issues.append(
                    ValidationIssue(
                        "oracle_empty_observation_point",
                        "Oracle observation_point must be non-empty",
                        f"{expected_path}.oracle.observation_point",
                        "A08",
                        case_id=case_id,
                        expected_id=expected_id,
                    )
                )
            if "matcher" in oracle and not str(oracle.get("matcher", "")).strip():
                issues.append(
                    ValidationIssue(
                        "oracle_empty_matcher",
                        "Oracle matcher must be non-empty",
                        f"{expected_path}.oracle.matcher",
                        "A08",
                        case_id=case_id,
                        expected_id=expected_id,
                    )
                )
            if "source_ref" in oracle and not str(oracle.get("source_ref", "")).strip():
                issues.append(
                    ValidationIssue(
                        "oracle_empty_source_ref",
                        "Oracle source_ref must be non-empty",
                        f"{expected_path}.oracle.source_ref",
                        "A08",
                        case_id=case_id,
                        expected_id=expected_id,
                    )
                )
            if oracle.get("matcher") == "manual_confirmation" and "manual" not in allowed_modes:
                issues.append(
                    ValidationIssue(
                        "manual_oracle_not_routed",
                        "Manual Oracle requires manual execution mode",
                        f"{expected_path}.oracle.matcher",
                        "A08",
                        case_id=case_id,
                        expected_id=expected_id,
                    )
                )
    return issues
