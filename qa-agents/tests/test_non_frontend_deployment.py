import importlib.util
import json
from pathlib import Path


def load_deployer():
    path = Path(__file__).parents[1] / "scripts/deploy_non_frontend_agents.py"
    spec = importlib.util.spec_from_file_location("deploy_non_frontend_agents", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_non_frontend_deployment_spec_is_complete_and_unique() -> None:
    module = load_deployer()
    logical_ids = [item[0] for item in module.SPECS]
    assert len(logical_ids) == 23
    assert len(logical_ids) == len(set(logical_ids))
    assert {"K01", "A01", "A07", "A12", "A14", "A15", "A16", "A19", "A20", "A22"} <= set(logical_ids)
    assert not {"A04", "A13", "A17-A11Y", "A18-FE", "A18-A11Y"} & set(logical_ids)


def test_deployed_instructions_are_fail_closed_and_side_effect_free() -> None:
    module = load_deployer()
    value = module.instructions("A22", "test-data-intent/1.0", "test role")
    assert "blocked_input" in value
    assert "不得写业务仓" in value
    assert "不得编造通过" in value
    assert "schema_version=test-data-intent/1.0" in value


def test_k01_uses_dedicated_read_only_knowledge_instruction() -> None:
    module = load_deployer()
    value = module.instructions(
        "K01", "product-test-knowledge-candidates/1.0", "knowledge role"
    )
    assert "只产出候选知识" in value
    assert "禁止修改或提交业务仓" in value
    assert "不得读取、输出或写入知识 Artifact" in value


def test_k01_deployment_receipt_is_active_and_workspace_identity_is_unique() -> None:
    root = Path(__file__).parents[1]
    workspace = json.loads(
        (root / "multica/workspace-manifest.json").read_text(encoding="utf-8")
    )
    receipt = json.loads(
        (root / "multica/non-frontend-agent-deployment.json").read_text(encoding="utf-8")
    )
    workspace_k01 = [item for item in workspace["agents"] if item["logical_id"] == "K01"]
    receipt_k01 = [item for item in receipt["agents"] if item["logical_id"] == "K01"]
    assert len(workspace_k01) == len(receipt_k01) == 1
    assert workspace_k01[0]["runtime_status"] == "active"
    assert workspace_k01[0]["remote_id"] == receipt_k01[0]["remote_id"]
