import pytest

from qa_agents.agents import RequirementAnalyzerAgent
from qa_agents.agents.base import AgentContext
from qa_agents.errors import SecurityPolicyError
from qa_agents.model_runtime import StructuredModelRuntime
from qa_agents.security import SecurityPolicy


def policy(**binding_overrides) -> dict:
    binding = {
        "provider": "multica-model-gateway",
        "model_snapshot": "model-2026-08-07",
        "prompt_version": "prompt-a02-001",
        "output_contract": "requirement-analysis/1.0",
        "inference_config": {"temperature": 0},
        "tool_bundle_version": "no-tools/1.0",
        "tools": [],
    }
    binding.update(binding_overrides)
    return {
        "schema_version": "model-runtime-policy/1.0",
        "enabled": True,
        "data_retention_allowed": False,
        "allowed_deployments": [
            {
                "provider": "multica-model-gateway",
                "model_snapshot": "model-2026-08-07",
            }
        ],
        "profile_bindings": {"A02": binding},
    }


def model_response(request: dict) -> dict:
    assert request["profile_id"] == "A02"
    assert request["source_snapshot_id"] == "snapshot-1"
    return {
        "status": "completed",
        "payload": {
            "schema_version": "requirement-analysis/1.0",
            "requirements": [
                {
                    "id": "REQ-001",
                    "summary": "返回专用错误码",
                    "acceptance_criteria": ["返回专用错误码"],
                    "source_refs": [
                        {"type": "requirement", "id": "prd.md", "location": "section-1"}
                    ],
                }
            ],
            "ambiguities": [],
        },
        "evidence_refs": [
            {"source_type": "requirement", "source_id": "prd.md", "location": "section-1"}
        ],
    }


def test_model_runtime_is_injected_with_frozen_producer_metadata() -> None:
    runtime = StructuredModelRuntime(policy(), model_response)
    artifact = RequirementAnalyzerAgent().run(
        AgentContext("run-1", "new_requirement", "snapshot-1", ("input/prd.json",)),
        {"requirement": {"content": "需求内容"}},
        SecurityPolicy(),
        runtime,
    )
    assert artifact.payload["requirements"][0]["id"] == "REQ-001"
    assert artifact.producer.model_provider == "multica-model-gateway"
    assert artifact.producer.model_snapshot == "model-2026-08-07"
    assert artifact.producer.prompt_version == "prompt-a02-001"
    assert artifact.producer.inference_config_hash.startswith("sha256:")


def test_model_runtime_rejects_mutable_or_tool_enabled_binding() -> None:
    mutable_policy = policy(model_snapshot="model-latest")
    mutable_policy["allowed_deployments"][0]["model_snapshot"] = "model-latest"
    with pytest.raises(SecurityPolicyError, match="immutable"):
        StructuredModelRuntime(mutable_policy, model_response).invoke(
            profile_id="A02",
            profile_version="1.0.0",
            output_contract="requirement-analysis/1.0",
            workflow_run_id="run-1",
            source_snapshot_id="snapshot-1",
            inputs={"requirement": {"content": "需求内容"}},
        )

    with pytest.raises(SecurityPolicyError, match="direct tools"):
        StructuredModelRuntime(policy(tools=["shell"]), model_response).invoke(
            profile_id="A02",
            profile_version="1.0.0",
            output_contract="requirement-analysis/1.0",
            workflow_run_id="run-1",
            source_snapshot_id="snapshot-1",
            inputs={"requirement": {"content": "需求内容"}},
        )
