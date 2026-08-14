from __future__ import annotations

import json
from pathlib import Path


def test_pc_006_frozen_historical_manifest_contract() -> None:
    path = Path(__file__).resolve().parents[2] / "generated/pc006-historical-assets-evidence.json"
    evidence = json.loads(path.read_text())
    assert evidence["evidence_level"] == "historical_candidate_verified_by_id_timestamp_and_live_readback"
    assert {item["resource_type"] for item in evidence["assets"]} == {"stat_chart", "joined_table"}
    assert all(item["readback_status"] == "succeeded" for item in evidence["assets"])
    assert all(item["normalized_configuration_hash"].startswith("sha256:")
               for item in evidence["assets"])
