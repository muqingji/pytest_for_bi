"""Deterministic executability classification for approved Test Case IR."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable


EXECUTABILITY_CLASSES = {
    "machine_executable",
    "capability_missing",
    "manual_only",
    "invalid_case",
}

SUPPORTED_ORACLE_MATCHERS = {
    "all_equal",
    "all_fields_equal",
    "contains",
    "contains_structure",
    "equals",
    "equals_baseline",
    "equals_baseline_except",
    "equals_one_complete_matched_mapping",
    "exists",
    "not_contains",
    "one_of",
    "one_of_actually_matched",
    "regex",
}

SUPPORTED_RESPONSE_EXPECTATIONS = {
    "body",
    "body_contains_keys",
    "body_contains_values",
    "body_exact",
    "body_not_contains_values",
    "headers",
    "json_path",
    "schema",
    "status_code",
}

_LIFECYCLE_PHASES = ("setup", "readiness", "steps", "cleanup", "residue_checks")


def _reason(code: str, location: str, detail: str) -> dict[str, str]:
    return {"reason_code": code, "location": location, "detail": detail}


def _matcher_name(value: Any) -> str:
    matcher = str(value or "").strip()
    if matcher.startswith("equals:"):
        return "equals"
    return matcher


def _step_issues(
    case: Mapping[str, Any],
    *,
    known_operations: set[str] | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    invalid: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    extracted_variables: set[str] = set()

    for phase in _LIFECYCLE_PHASES:
        raw_steps = case.get(phase, [])
        if not isinstance(raw_steps, list):
            invalid.append(
                _reason("execution_phase_not_list", phase, f"{phase} must be a list")
            )
            continue
        for index, step in enumerate(raw_steps):
            location = f"{phase}[{index}]"
            if not isinstance(step, Mapping):
                invalid.append(
                    _reason(
                        "execution_step_not_structured",
                        location,
                        "automatic execution requires a structured step object",
                    )
                )
                continue
            request = step.get("request")
            if not isinstance(request, Mapping):
                invalid.append(
                    _reason(
                        "execution_request_missing",
                        f"{location}.request",
                        "structured execution step requires request",
                    )
                )
                continue
            operation = str(request.get("api", "")).strip()
            has_direct_http = bool(
                request.get("url")
                or (request.get("method") and request.get("path"))
            )
            if not operation and not has_direct_http:
                invalid.append(
                    _reason(
                        "execution_operation_missing",
                        f"{location}.request",
                        "request requires an api operation or method/path",
                    )
                )
            if operation and known_operations is not None and operation not in known_operations:
                missing.append(
                    _reason(
                        "operation_not_registered",
                        f"{location}.request.api",
                        operation,
                    )
                )
            extract = step.get("extract", {})
            if not isinstance(extract, Mapping):
                invalid.append(
                    _reason(
                        "extract_mapping_invalid",
                        f"{location}.extract",
                        "extract must map variables to response paths",
                    )
                )
            else:
                for variable, path in extract.items():
                    if not str(variable).strip() or not str(path).strip():
                        invalid.append(
                            _reason(
                                "extract_binding_incomplete",
                                f"{location}.extract",
                                "extract variables and response paths must be non-empty",
                            )
                        )
                    else:
                        extracted_variables.add(str(variable))
            if "expect" in step:
                expect = step.get("expect")
                if not isinstance(expect, Mapping) or not expect:
                    invalid.append(
                        _reason(
                            "response_expectation_empty",
                            f"{location}.expect",
                            "expect must contain at least one supported assertion",
                        )
                    )
                elif unknown := sorted(set(map(str, expect)) - SUPPORTED_RESPONSE_EXPECTATIONS):
                    invalid.append(
                        _reason(
                            "response_expectation_unsupported",
                            f"{location}.expect",
                            ", ".join(unknown),
                        )
                    )
            if phase in {"setup", "readiness"} and not step.get("expect"):
                missing.append(
                    _reason(
                        "lifecycle_assertion_missing",
                        f"{location}.expect",
                        f"{phase} must prove the requested state",
                    )
                )

    setup = case.get("setup", [])
    if isinstance(setup, list) and setup:
        readiness = case.get("readiness", [])
        if not isinstance(readiness, list) or not readiness:
            missing.append(
                _reason(
                    "test_data_readiness_missing",
                    "readiness",
                    "created resources require an independent readback",
                )
            )

    for phase in ("cleanup", "residue_checks"):
        raw_steps = case.get(phase, [])
        if not isinstance(raw_steps, list):
            continue
        for index, step in enumerate(raw_steps):
            if not isinstance(step, Mapping):
                continue
            when_variable = str(step.get("when_variable", "")).strip()
            if when_variable and when_variable not in extracted_variables:
                invalid.append(
                    _reason(
                        "lifecycle_guard_variable_unknown",
                        f"{phase}[{index}].when_variable",
                        when_variable,
                    )
                )

    return invalid, missing


def classify_case_executability(
    case: Mapping[str, Any],
    *,
    known_operations: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Classify a Case before code generation, without guessing capabilities."""

    case_id = str(case.get("id", "")).strip()
    allowed_modes = case.get("execution_policy", {}).get("allowed_modes", [])
    automated = isinstance(allowed_modes, list) and "automated" in allowed_modes
    expected = case.get("expected", [])
    deterministic = [
        item
        for item in expected
        if isinstance(item, Mapping)
        and isinstance(item.get("oracle"), Mapping)
        and item["oracle"].get("matcher") != "manual_confirmation"
        and item["oracle"].get("type", "deterministic") != "human_review"
    ] if isinstance(expected, list) else []

    if not case.get("automation_candidate") or not automated or not deterministic:
        return {
            "case_id": case_id,
            "classification": "manual_only",
            "reason_codes": ["case_not_machine_executable"],
            "issues": [],
        }

    invalid: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    if not case_id:
        invalid.append(_reason("case_id_missing", "id", "Case id is required"))
    if not isinstance(expected, list) or not expected:
        invalid.append(_reason("expected_missing", "expected", "expected must be non-empty"))
    for index, item in enumerate(deterministic):
        oracle = item.get("oracle", {})
        location = f"expected[{index}].oracle"
        matcher = _matcher_name(oracle.get("matcher"))
        if matcher not in SUPPORTED_ORACLE_MATCHERS:
            missing.append(
                _reason("oracle_matcher_not_supported", f"{location}.matcher", matcher)
            )
        if not str(oracle.get("observation_point", "")).strip():
            invalid.append(
                _reason(
                    "oracle_observation_missing",
                    f"{location}.observation_point",
                    "deterministic Oracle requires an observation point",
                )
            )
        if matcher not in {"exists", "one_of", "one_of_actually_matched"} and "expected_value" not in oracle:
            encoded_equals = str(oracle.get("matcher", "")).startswith("equals:")
            if not encoded_equals:
                invalid.append(
                    _reason(
                        "oracle_expected_value_missing",
                        f"{location}.expected_value",
                        "matcher requires expected_value",
                    )
                )
        if matcher in ("one_of", "one_of_actually_matched") and not isinstance(oracle.get("expected_values"), list):
            invalid.append(
                _reason(
                    "oracle_expected_values_missing",
                    f"{location}.expected_values",
                    "one_of requires expected_values",
                )
            )

    step_invalid, step_missing = _step_issues(
        case,
        known_operations=set(known_operations) if known_operations is not None else None,
    )
    invalid.extend(step_invalid)
    missing.extend(step_missing)
    if invalid:
        classification = "invalid_case"
        issues = invalid + missing
    elif missing:
        classification = "capability_missing"
        issues = missing
    else:
        classification = "machine_executable"
        issues = []
    return {
        "case_id": case_id,
        "classification": classification,
        "reason_codes": sorted({item["reason_code"] for item in issues}),
        "issues": issues,
    }
