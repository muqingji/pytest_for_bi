"""Offline evaluation. This is the only runtime allowed to read Oracle fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _read_payload(run_dir: Path, artifact_name: str) -> dict[str, Any]:
    path = run_dir / "artifacts" / artifact_name
    if not path.exists():
        return {}
    artifact = _read(path)
    payload = artifact.get("payload")
    return payload if isinstance(payload, dict) else {}


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _searchable_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(_searchable_text(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return " ".join(_searchable_text(item) for item in value)
    return str(value) if value is not None else ""


def _matches_rule(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Apply an auditable Oracle predicate without calling a model.

    Exact IDs are accepted when producers share the Oracle's stable taxonomy. Otherwise
    the Oracle must declare explicit all_terms/any_term_groups. This avoids silently
    treating fuzzy text similarity as a quality pass.
    """

    expected_level = expected.get("level")
    actual_levels = set(actual.get("required_layers", []))
    if actual.get("layer"):
        actual_levels.add(actual["layer"])
    if expected_level and expected_level not in actual_levels:
        return False
    if actual.get("id") == expected.get("id"):
        return True
    rule = expected.get("match")
    if not isinstance(rule, Mapping):
        return False
    text = _normalize(_searchable_text(actual))
    all_terms = rule.get("all_terms", [])
    if not isinstance(all_terms, list) or not all(
        isinstance(term, str) and _normalize(term) in text for term in all_terms
    ):
        return False
    groups = rule.get("any_term_groups", [])
    if not isinstance(groups, list):
        return False
    for group in groups:
        if not isinstance(group, list) or not any(
            isinstance(term, str) and _normalize(term) in text for term in group
        ):
            return False
    return True


def _maximum_matching(
    expected_items: Sequence[Mapping[str, Any]],
    actual_items: Sequence[Mapping[str, Any]],
) -> dict[int, int]:
    """Return a maximum one-to-one expected-to-actual matching.

    One broad Case cannot satisfy many independent obligations unless it is represented
    as independently reviewable parameterized children in the Test Case IR.
    """

    candidates = [
        [index for index, actual in enumerate(actual_items) if _matches_rule(actual, expected)]
        for expected in expected_items
    ]
    actual_to_expected: dict[int, int] = {}

    def assign(expected_index: int, visited: set[int]) -> bool:
        for actual_index in candidates[expected_index]:
            if actual_index in visited:
                continue
            visited.add(actual_index)
            previous = actual_to_expected.get(actual_index)
            if previous is None or assign(previous, visited):
                actual_to_expected[actual_index] = expected_index
                return True
        return False

    for expected_index in range(len(expected_items)):
        assign(expected_index, set())
    return {expected: actual for actual, expected in actual_to_expected.items()}


def _semantic_checks(
    category: str,
    expected_items: Sequence[Mapping[str, Any]],
    actual_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    matches = _maximum_matching(expected_items, actual_items)
    checks: list[dict[str, Any]] = []
    for expected_index, expected in enumerate(expected_items):
        actual_index = matches.get(expected_index)
        actual = actual_items[actual_index] if actual_index is not None else None
        checks.append(
            {
                "check": f"{category}:{expected.get('id', expected_index)}",
                "category": category,
                "passed": actual is not None,
                "expected": expected.get("summary", expected.get("id")),
                "actual": actual.get("id", "matched") if actual else "missing",
                "actual_summary": actual.get("summary", actual.get("title")) if actual else None,
            }
        )
    return checks


def _routing_checks(summary: Mapping[str, Any], routing: Mapping[str, Any]) -> list[dict[str, Any]]:
    actual_nodes = {item["id"]: item for item in summary["nodes"]}
    checks = []
    run_expectations = {"run", "run_after_scope_decision"}
    running_statuses = {"completed", "completed_with_gaps", "needs_human", "inconclusive"}
    for expected in routing.get("nodes", []):
        node_id = expected["id"]
        actual = actual_nodes.get(node_id)
        if expected["expected"] in run_expectations:
            passed = actual is not None and actual["status"] in running_statuses
        elif expected["expected"] == "pause_if_unresolved":
            passed = (
                actual is not None
                and actual["status"] in {"needs_human", "completed"}
                and actual.get("reason_code") == expected.get("reason_code")
            )
        else:
            passed = actual is not None and actual["status"] == expected["expected"]
        checks.append(
            {
                "check": f"routing:{node_id}",
                "category": "routing",
                "passed": passed,
                "expected": expected["expected"],
                "actual": actual["status"] if actual else "missing",
            }
        )
    return checks


def _decision_checks(
    run_dir: Path, summary: Mapping[str, Any], analysis_oracle: Mapping[str, Any]
) -> list[dict[str, Any]]:
    expected = analysis_oracle.get("minimum_expected_decision")
    if not isinstance(expected, Mapping):
        return []
    actual = next(
        (node for node in summary.get("nodes", []) if node.get("id") == expected.get("gate")),
        None,
    )
    passed = actual is not None and actual.get("status") == expected.get("status")
    gate_payload: Mapping[str, Any] = {}
    gate_name = str(expected.get("gate", "")).casefold()
    gate_artifact = run_dir / "artifacts" / f"{gate_name}-scope-review.json"
    if not passed and expected.get("status") == "needs_human" and gate_artifact.exists():
        envelope = _read(gate_artifact)
        payload = envelope.get("payload", {})
        gate_payload = payload if isinstance(payload, Mapping) else {}
        # An explicitly approved Gate is a valid continuation of an earlier needs_human
        # decision only when the unresolved issues and reason remain in the audit record.
        passed = (
            actual is not None
            and actual.get("status") == "completed"
            and gate_payload.get("decision") == "approved"
            and bool(gate_payload.get("issues"))
            and bool(actual.get("reason_code"))
        )
    return [
        {
            "check": "analysis:minimum_expected_decision",
            "category": "minimum_expected_decision",
            "passed": passed,
            "expected": {"gate": expected.get("gate"), "status": expected.get("status")},
            "actual": (
                {
                    "gate": actual.get("id"),
                    "status": actual.get("status"),
                    "decision": gate_payload.get("decision"),
                }
                if actual
                else "missing"
            ),
        }
    ]


def _category_summary(checks: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for check in checks:
        category = str(check["category"])
        values = result.setdefault(category, {"passed": 0, "failed": 0, "total": 0})
        values["total"] += 1
        values["passed" if check["passed"] else "failed"] += 1
    return result


def evaluate_run(run_dir: Path, oracle_dir: Path) -> dict[str, Any]:
    """Evaluate frozen outputs after the Agent workflow has finished.

    Oracle files are optional by category so small unit fixtures can evaluate routing only.
    A production evaluation set should provide routing, analysis and test obligations.
    """

    summary = _read(run_dir / "run-summary.json")
    routing = _read(oracle_dir / "expected-routing.json")
    checks = _routing_checks(summary, routing)

    analysis_path = oracle_dir / "expected-analysis.json"
    if analysis_path.exists():
        analysis = _read(analysis_path)
        analysis_sources = (
            ("atomic_requirements", "a02-requirement-analysis.json", "requirements"),
            ("implementation_facts", "a05-backend-change-analysis.json", "facts"),
            ("alignment_findings", "a06-alignment-result.json", "findings"),
            ("open_questions", "a03-technical-testability-analysis.json", "blocking_items"),
        )
        for category, artifact_name, payload_key in analysis_sources:
            expected_items = analysis.get(category, [])
            actual_items = _read_payload(run_dir, artifact_name).get(payload_key, [])
            checks.extend(_semantic_checks(category, expected_items, actual_items))
        checks.extend(_decision_checks(run_dir, summary, analysis))

    obligations_path = oracle_dir / "expected-test-obligations.json"
    if obligations_path.exists():
        obligations = _read(obligations_path).get("obligations", [])
        parent_cases = _read_payload(run_dir, "a08-test-design-ir.json").get("parent_cases", [])
        checks.extend(_semantic_checks("test_obligations", obligations, parent_cases))

    passed_count = sum(1 for item in checks if item["passed"])
    return {
        "schema_version": "workflow-evaluation/2.0",
        "workflow_run_id": summary["workflow_run_id"],
        "passed": all(item["passed"] for item in checks),
        "passed_checks": passed_count,
        "failed_checks": len(checks) - passed_count,
        "categories": _category_summary(checks),
        "oracle_coverage": {
            "routing": "evaluated",
            "analysis": "evaluated" if analysis_path.exists() else "not_provided",
            "test_obligations": "evaluated" if obligations_path.exists() else "not_provided",
            "safety": (
                "separate_negative_test_suite_required"
                if (oracle_dir / "expected-safety.json").exists()
                else "not_provided"
            ),
        },
        "checks": checks,
        "note": "Oracle was read only by the offline evaluator after Agent output was frozen.",
    }
