from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = ROOT / "generated" / "pc006-historical-assets-evidence.json"


def test_pc006_historical_candidates_are_read_back_before_requirement_baseline() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    baseline = datetime.fromisoformat(evidence["requirement_baseline_time"])

    assert evidence["evidence_level"] == (
        "historical_candidate_verified_by_id_timestamp_and_live_readback"
    )
    assert evidence["database_created_at_verified"] is False
    assert {asset["resource_type"] for asset in evidence["assets"]} == {
        "stat_chart",
        "joined_table",
    }
    for asset in evidence["assets"]:
        timestamp = datetime.fromisoformat(
            asset["timestamp_evidence"]["value"].replace("Z", "+00:00")
        )
        assert timestamp < baseline
        assert asset["readback_status"] == "succeeded"
        assert re.fullmatch(
            r"sha256:[0-9a-f]{64}", asset["normalized_configuration_hash"]
        )


def test_pc006_evidence_does_not_persist_session_material() -> None:
    text = EVIDENCE_PATH.read_text(encoding="utf-8")
    lowered = text.lower()
    forbidden = (
        "cookie",
        "fs_token",
        "fsauthx",
        "jsessionid",
        "authorization",
        "__bodykey",
        "x-fs-token",
    )
    assert not any(key in lowered for key in forbidden)
