from qa_agents.knowledge_packet_builder import build_test_knowledge_packet
from qa_agents.test_knowledge import assess_automation_readiness


def test_builder_excludes_e2e_and_does_not_promote_partial_variant_coverage():
    compiled = {"artifact_hash": "sha256:compiled", "payload": {"compiled_cases": [
        {"id": "PC-002-BACKEND", "layer": "backend", "test_data": {"datasets": [
            {"type": "ordinary"}, {"type": "aggregate"}, {"type": "calculated"}, {"type": "comparison"}
        ]}, "expected": [{"id": "E1", "oracle": {"type": "deterministic", "observation_point": "detail.error", "expected_value": {"code": "x"}, "matcher": "equal", "source_ref": "RULE"}}]},
        {"id": "PC-002-E2E", "layer": "e2e"},
    ]}}
    openapi = {"paths": {"/detail": {"post": {"operationId": "fs_bi_stat.stat_base.data_query_da655ba1"}}}}
    catalog = {"recipes": [
        {"id": "agg", "supported_variants": ["aggregate_metric"], "resources": [{"resource_key": "agg", "depends_on": [], "setup": {"api": "create"}, "readiness": [{"api": "get"}], "cleanup": {"api": "delete"}}]},
        {"id": "calc", "supported_variants": ["calculated_metric"], "resources": [{"resource_key": "calc", "depends_on": [], "setup": {"api": "create"}, "readiness": [{"api": "get"}], "cleanup": {"api": "delete"}}]},
    ]}
    packet = build_test_knowledge_packet(compiled, openapi, catalog, knowledge_snapshot_id="ptkb-1")
    assert [item["case_id"] for item in packet["cases"]] == ["PC-002-BACKEND"]
    case = packet["cases"][0]
    assert case["data_recipe"]["resources"] == []
    assert [item["status"] for item in case["coverage_obligations"]] == ["deferred", "ready", "ready", "deferred"]
    readiness = assess_automation_readiness(packet, {"PC-002-BACKEND"})
    assert readiness["status"] == "deferred"
