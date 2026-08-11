from pathlib import Path

import pytest

from qa_agents.case_provider import CaseProviderAdapter, CaseProviderCapabilityProbe
from qa_agents.contracts import ArtifactEnvelope, EvidenceRef, Producer
from qa_agents.errors import SecurityPolicyError
from qa_agents.security import SecurityPolicy
from qa_agents.storage import ArtifactStore


def test_artifact_hash_is_stable_across_creation_times() -> None:
    values = []
    for created_at in ("2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"):
        artifact = ArtifactEnvelope(
            workflow_run_id="run-1",
            workflow_mode="new_requirement",
            artifact_id="a02-requirement-analysis",
            source_snapshot_id="snapshot-1",
            producer=Producer("A02"),
            payload={"requirements": []},
            created_at=created_at,
            evidence_refs=(EvidenceRef("requirement", "REQ", "section-1"),),
        )
        values.append(artifact.artifact_hash)
    assert values[0] == values[1]


def test_artifact_store_rejects_path_escape(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    with pytest.raises(SecurityPolicyError):
        store.write_json("../outside.json", {})


def test_agent_cannot_receive_oracle_path() -> None:
    with pytest.raises(SecurityPolicyError):
        SecurityPolicy().assert_agent_paths(["fixture/oracle/expected-analysis.json"])


def test_input_rejects_embedded_credentials() -> None:
    with pytest.raises(SecurityPolicyError, match="Credential-like"):
        SecurityPolicy().assert_no_secret_values(
            {"request": "Authorization: Bearer this-is-a-real-looking-token"}
        )


def test_empty_secret_declaration_is_allowed_but_values_are_rejected() -> None:
    SecurityPolicy().assert_no_secret_values({"secrets": []})
    with pytest.raises(SecurityPolicyError, match="Credential-like"):
        SecurityPolicy().assert_no_secret_values({"secrets": ["secret-reference"]})


def test_redaction_preserves_empty_secret_declaration_shape() -> None:
    policy = SecurityPolicy()
    assert policy.redact_secrets({"secrets": [], "network": False}) == {
        "secrets": [],
        "network": False,
    }
    assert policy.redact_secrets({"password": "not-empty-value"}) == {
        "password": "[REDACTED]"
    }


def test_case_provider_requires_artifact_only_and_fixed_commit() -> None:
    adapter = CaseProviderAdapter()
    commit = "a" * 40
    result = adapter.adapt(
        {
            "metadata": {
                "mode": "artifact_only",
                "provider_commit": commit,
                "output_contract": "case-provider-output/1.0",
                "side_effects": [],
            },
            "candidates": [
                {
                    "id": "FS-20260807-001",
                    "feature": "查看明细",
                    "title": "验证提示文案",
                    "priority": "P1",
                    "case_type": "功能测试",
                    "preconditions": ["准备数据"],
                    "steps": ["查看明细"],
                    "expected": ["展示专用提示"],
                    "source_refs": ["REQ-1"],
                }
            ],
        },
        expected_commit=commit,
    )
    assert result["candidate_count"] == 1
    assert result["external_side_effects"] is False

    with pytest.raises(SecurityPolicyError):
        adapter.adapt(
            {
                "metadata": {
                    "mode": "upload2fs",
                    "provider_commit": commit,
                    "output_contract": "case-provider-output/1.0",
                    "side_effects": ["upload"],
                },
                "candidates": [],
            }
        )


def test_case_provider_capability_rejects_current_mandatory_upload_contract() -> None:
    result = CaseProviderCapabilityProbe().probe(
        "1ca888b645bd1c346b6d708a9a583af58d299fc8",
        {
            "skills/testcase-generate/SKILL.md": (
                "### Step 10.1：强制检查点——FS 对象上传（禁止跳过）"
            )
        },
    )
    assert result["status"] == "incompatible"
    assert result["mutable_worktree_used"] is False
    assert {item["code"] for item in result["blockers"]} == {
        "provider_manifest_missing",
        "mandatory_external_side_effect_workflow",
    }


def test_case_provider_parses_merged_markdown_table() -> None:
    commit = "b" * 40
    markdown = """# 测试用例集

| 用例ID | 功能点 | 用例标题 | 优先级 | 用例类型 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FS-20260807-001 | 查看明细 | 验证异常场景展示专用文案 | P1 | 功能测试 | 1. 准备数据 | 1. 点击查看明细<br>2. 等待响应 | 1. 返回专用错误码<br>2. 文案正确 |
"""
    result = CaseProviderAdapter().from_markdown_bundle(
        markdown,
        {
            "mode": "artifact_only",
            "provider_commit": commit,
            "output_contract": "case-provider-output/1.0",
            "side_effects": [],
            "source_refs": ["REQ-1:section-1"],
        },
        expected_commit=commit,
    )
    assert result["candidate_count"] == 1
    assert result["source_format"] == "markdown_table"
    assert result["candidates"][0]["steps"] == ["1. 点击查看明细", "2. 等待响应"]
