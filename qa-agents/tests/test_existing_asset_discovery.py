from qa_agents.existing_asset_discovery import discover_existing_assets
from qa_agents.contracts import content_hash


def _integrity_evidence(*, missing: str = "") -> dict:
    checks = [
        {"check": name, "status": "failed" if name == missing else "passed"}
        for name in ("source_data", "warehouse_dimension", "warehouse_aggregation", "chart_topology")
    ]
    packet = {
        "schema_version": "test-data-integrity-evidence/1.0",
        "provider": "bug-finder/fxops_query",
        "required_checks": sorted(item["check"] for item in checks),
        "checks": checks,
        "valid": not missing,
    }
    packet["evidence_hash"] = content_hash(packet)
    return packet


def test_discovery_only_reuses_exact_lineage_with_live_evidence() -> None:
    cases = [{"id": "CASE-1", "test_data": {"resource_requirements": [{"resource_key": "chart", "resource_type": "stat_chart"}]}}]
    inventory = [
        {"case_id": "CASE-1", "resource_key": "chart", "resource_type": "stat_chart", "resource_id": "BI-1", "display_name": "目标图"},
        {"case_id": "OTHER", "resource_key": "chart", "resource_type": "stat_chart", "resource_id": "BI-2", "display_name": "名字很像的图"},
    ]

    def verify(candidate):
        assert candidate["resource_id"] == "BI-1"
        return {
            "live_readback_status": "succeeded",
            "baseline_status": "passed",
            "configuration": {"id": "BI-1", "dimensions": ["customer"]},
            "baseline": {"FailureCode": 0},
            "readback_operation": "fs_bi_stat.stat_edit.get_chart_config",
            "baseline_operation": "fs_bi_stat.stat_base.data_query_da655ba1",
            "trace_ids": ["FSW-1.2-live"],
            "readback_request": {"id": "BI-1"},
            "baseline_request": {"id": "BI-1", "pageSize": 1},
            "integrity_evidence": _integrity_evidence(),
        }

    packet = discover_existing_assets(cases, inventory, verifier=verify)
    assert len(packet["candidates"]) == 1
    candidate = packet["candidates"][0]
    assert candidate["decision"] == "reusable"
    assert candidate["resource_id"] == "BI-1"
    assert candidate["existing_asset_evidence"]["configuration_hash"].startswith("sha256:")
    assert candidate["discovery"]["request"]["json"]["id"] == "BI-1"
    assert candidate["readiness"][0]["request"]["json"]["pageSize"] == 1


def test_discovery_rejects_candidate_when_baseline_is_not_proven() -> None:
    cases = [{"id": "CASE-1", "resource_requirements": [{"resource_key": "chart", "resource_type": "stat_chart"}]}]
    inventory = [{"case_id": "CASE-1", "resource_key": "chart", "resource_type": "stat_chart", "resource_id": "BI-1"}]
    packet = discover_existing_assets(
        cases,
        inventory,
        verifier=lambda _: {"live_readback_status": "succeeded", "configuration": {"id": "BI-1"}, "baseline_status": "failed", "baseline": {"FailureCode": 1}},
    )
    assert packet["candidates"][0]["decision"] == "rejected"


def test_discovery_offers_exact_case_lineage_before_a22_plans_resources() -> None:
    packet = discover_existing_assets(
        [{"id": "CASE-1", "test_data": {"dataset": "existing-chart"}}],
        [
            {"case_id": "CASE-1", "resource_key": "chart", "resource_type": "stat_chart", "resource_id": "BI-1"},
            {"case_id": "OTHER", "resource_key": "chart", "resource_type": "stat_chart", "resource_id": "BI-2"},
        ],
        verifier=lambda _: {
            "live_readback_status": "succeeded",
            "baseline_status": "passed",
            "configuration": {"id": "BI-1"},
            "baseline": {"Result": {"FailureCode": 0}},
            "readback_operation": "read",
            "baseline_operation": "query",
            "integrity_evidence": _integrity_evidence(),
        },
    )
    assert [item["resource_id"] for item in packet["candidates"]] == ["BI-1"]


def test_discovery_rejects_chart_when_warehouse_integrity_is_not_proven() -> None:
    packet = discover_existing_assets(
        [{"id": "CASE-1", "resource_requirements": [{"resource_key": "chart", "resource_type": "stat_chart"}]}],
        [{"case_id": "CASE-1", "resource_key": "chart", "resource_type": "stat_chart", "resource_id": "BI-1"}],
        verifier=lambda _: {
            "live_readback_status": "succeeded", "baseline_status": "passed",
            "configuration": {"id": "BI-1"}, "baseline": {"Result": {"FailureCode": 0}},
            "readback_operation": "read", "baseline_operation": "query",
            "integrity_evidence": _integrity_evidence(missing="warehouse_aggregation"),
        },
    )
    assert packet["candidates"][0]["decision"] == "rejected"
    assert packet["candidates"][0]["reason_code"] == "integrity_not_proven"
