from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.chart_builder import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
SOURCE_VIEW_ID = "BI_6a7c6421280b910007abfe94"
OUTPUT = ROOT / "generated/112-stat-chart-update-snapshot.json"


def test_capture_complete_update_sources_in_112(environment, case_runner):
    if environment.name != "112":
        pytest.skip("112 only")
    calls = {
        "crm": ("fs_bi_crm.stat_edit.get_stat_view", {"id": SOURCE_VIEW_ID}),
        "chart": ("fs_bi_stat.stat_edit.get_chart_config", {
            "id": SOURCE_VIEW_ID, "isView": 1, "type": "edit",
            "querySource": "UNKNOWN", "cacheTime": 0, "refresh": 1,
        }),
        "filters": ("fs_bi_stat.stat_edit.get_filters_result", {
            "id": SOURCE_VIEW_ID, "isView": 1,
        }),
    }
    responses = {}
    for key, (operation, body) in calls.items():
        response = case_runner.http_api.call(operation, body=body)
        assert response.status_code == 200
        assert response.body.get("Result", {}).get("FailureCode") in (None, 0), response.body
        responses[key] = response.body
    chart = responses["chart"].get("Value") or {}
    crm_text = json.dumps(responses["crm"], ensure_ascii=False)
    assert chart.get("schemaId") and chart.get("measureFields")
    assert SOURCE_VIEW_ID in crm_text
    payload = {
        "resource_id": SOURCE_VIEW_ID,
        "crm_hash": canonical_hash(responses["crm"]),
        "chart_hash": canonical_hash(responses["chart"]),
        "filters_hash": canonical_hash(responses["filters"]),
        "chart_keys": sorted(chart),
        "crm_value_keys": sorted((responses["crm"].get("Value") or {}).keys()),
        "filter_value_keys": sorted((responses["filters"].get("Value") or {}).keys()),
        "chart_summary": {
            "view_name": chart.get("viewName"),
            "schema_id": chart.get("schemaId"),
            "chart_type": chart.get("chartType"),
            "dimension_count": len(chart.get("dimensionFields") or []),
            "measure_count": len(chart.get("measureFields") or []),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
