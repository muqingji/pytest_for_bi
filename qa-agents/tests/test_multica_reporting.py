from qa_agents.errors import ContractError
from qa_agents.reporting import render_multica_alignment_markdown


def test_render_multica_alignment_markdown() -> None:
    bundle = {
        "workflow_run_id": "run-1",
        "bundle_hash": "sha256:bundle",
        "allowed_inputs": {
            "requirement_analysis": {
                "requirements": [{"id": "REQ-001", "summary": "展示专用提示"}]
            }
        },
    }
    artifact = {
        "artifact_id": "a06-alignment-result",
        "workflow_run_id": "run-1",
        "source_snapshot_id": "snapshot-1",
        "status": "needs_human",
        "payload": {
            "input_bundle_hash": "sha256:bundle",
            "mappings": [
                {
                    "requirement_id": "REQ-001",
                    "status": "partially_aligned",
                    "technical_fact_ids": ["TF-001"],
                    "change_fact_ids": ["BE-001"],
                }
            ],
            "findings": [
                {
                    "id": "FND-001",
                    "severity": "high",
                    "type": "conflict",
                    "summary": "实现与方案不一致",
                    "requirement_ids": ["REQ-001"],
                    "technical_fact_ids": ["TF-001"],
                    "implementation_ids": ["BE-001"],
                    "source_refs": ["REQ-001", "TF-001", "BE-001"],
                }
            ],
        },
    }

    report = render_multica_alignment_markdown(artifact, bundle)

    assert "REQ-001 展示专用提示" in report
    assert "[HIGH] FND-001 conflict" in report
    assert "G01" in report


def test_render_multica_alignment_rejects_wrong_bundle() -> None:
    artifact = {
        "artifact_id": "a06-alignment-result",
        "workflow_run_id": "run-1",
        "payload": {"input_bundle_hash": "sha256:one"},
    }
    bundle = {"workflow_run_id": "run-1", "bundle_hash": "sha256:two"}

    try:
        render_multica_alignment_markdown(artifact, bundle)
    except ContractError as error:
        assert "bundle does not match" in str(error)
    else:
        raise AssertionError("Expected report binding validation to fail")
