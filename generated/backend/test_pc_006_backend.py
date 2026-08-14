from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.chart_builder import canonical_hash as chart_hash
from qa_agents.joined_table import canonical_hash as joined_hash


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "generated/pc006-historical-assets-evidence.json"


@pytest.mark.parametrize("resource_type", ["stat_chart", "joined_table"])
def test_pc_006_historical_assets_live_readback(environment, case_runner, resource_type):
    if environment.name != "112":
        pytest.skip("PC-006 runs only with --env=112")
    evidence = json.loads(EVIDENCE.read_text())
    asset = next(item for item in evidence["assets"]
                 if item["resource_type"] == resource_type)
    if resource_type == "stat_chart":
        response = case_runner.http_api.call(
            "fs_bi_stat.stat_edit.get_chart_config",
            body={"id": asset["resource_id"], "isView": 1, "type": "edit",
                  "querySource": "UNKNOWN", "cacheTime": 0, "refresh": 1},
        )
        value = response.body.get("Value") or {}
        actual_hash = chart_hash(value)
        assert value.get("viewName") == asset["display_name"]
    else:
        response = case_runner.http_api.call(
            "fs_bi_dev.lwt_manager.query_arg_detail",
            body={"id": asset["resource_id"], "updateViewTime": 0},
        )
        value = response.body.get("Value", response.body)
        actual_hash = joined_hash(value)
        assert value.get("viewName") == asset["display_name"]
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") in (None, 0), response.body
    assert actual_hash.startswith("sha256:")
