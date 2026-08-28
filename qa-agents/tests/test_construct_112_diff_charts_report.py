"""Validate latest 112 differentiated chart construction report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "runs/pilot-001/test-data/112-demo-construction-latest.json"


@pytest.mark.skipif(not REPORT.exists(), reason="no construction report yet")
def test_latest_diff_chart_report_has_split_bindings() -> None:
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    diff = payload.get("differentiation") or {}
    sigs = payload.get("chart_signatures") or []
    assert payload.get("totals", {}).get("failed_cases", 1) == 0
    assert diff.get("unique_chart_signature_count", 0) >= 1
    assert diff.get("unique_measure_count", 0) >= 1
    # Prefer full split when report was produced by the new constructor.
    if "in_chart_measure_filter_split_count" in diff:
        assert diff["in_chart_measure_filter_split_count"] == len(sigs)
        assert diff.get("unique_dimension_count", 0) >= 1
        assert diff.get("unique_filter_count", 0) >= 2
    for row in sigs:
        measures = [item[0] for item in (row.get("measures") or []) if item]
        filters = [item[0] for item in (row.get("filters") or []) if item]
        assert measures, row
        if "in_chart_measure_filter_split_count" in diff:
            assert filters and set(measures).isdisjoint(set(filters)), row
