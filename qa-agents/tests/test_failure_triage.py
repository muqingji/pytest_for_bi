"""A19 local failure triage tests."""

from qa_agents.failure_triage import run_a19_failure_triage


def test_a19_reclassifies_environment_and_keeps_unknown_for_human() -> None:
    payload = run_a19_failure_triage(
        [
            {
                "cluster_id": "FAIL-001",
                "fingerprint": "sha256:" + "a" * 64,
                "classification": "needs_triage",
                "summary": "Connection refused while calling dependency service",
                "route_to": "A19",
            },
            {
                "cluster_id": "FAIL-002",
                "fingerprint": "sha256:" + "b" * 64,
                "classification": "needs_triage",
                "summary": "mysterious unexplained failure",
                "route_to": "A19",
            },
            {
                "cluster_id": "FAIL-003",
                "fingerprint": "sha256:" + "c" * 64,
                "classification": "product_defect",
                "summary": "already classified",
                "route_to": "N20",
            },
        ]
    )
    assert payload["reclassified_count"] == 1
    assert payload["needs_human_count"] == 1
    updated = {item["cluster_id"]: item for item in payload["updated_clusters"]}
    assert updated["FAIL-001"]["classification"] == "environment"
    assert updated["FAIL-001"]["route_to"] == "N10"
    assert updated["FAIL-002"]["classification"] == "needs_triage"
    assert updated["FAIL-003"]["classification"] == "product_defect"
