from qa_agents.agents.phase_one import TestDesignerAgent
from qa_agents.case_provider import (
    CaseProviderCapabilityProbe,
    apply_reviewed_provider_commit_gate,
    compare_provider_shadow,
    complete_provider_parent_case,
    load_case_provider_inspection,
    reviewed_provider_commits,
)


REVIEWED_COMMIT = "64cf10c3d2e030285f7f634a4cc5c61539546713"
HISTORICAL_COMMIT = "1ca888b645bd1c346b6d708a9a583af58d299fc8"


def test_inspection_pins_reviewed_incompatible_commit() -> None:
    inspection = load_case_provider_inspection()
    assert inspection["reviewed_commit"] == REVIEWED_COMMIT
    assert inspection["status"] == "incompatible"
    assert inspection["production_enabled"] is False
    assert reviewed_provider_commits() == {REVIEWED_COMMIT, HISTORICAL_COMMIT}


def test_reviewed_commit_gate_rejects_unpinned_fs_qa_knowledge() -> None:
    result = apply_reviewed_provider_commit_gate(
        {
            "provider_commit": "a" * 40,
            "status": "compatible",
            "supported_mode": "artifact_only",
            "blockers": [],
        },
        repository_id="fs-qa-knowledge",
    )
    assert result["status"] == "incompatible"
    assert result["reviewed_commit_pinned"] is False
    assert {item["code"] for item in result["blockers"]} == {"unreviewed_provider_commit"}


def test_reviewed_commit_gate_accepts_pinned_commit_without_enabling() -> None:
    probed = CaseProviderCapabilityProbe().probe(
        REVIEWED_COMMIT,
        {
            "skills/testcase-generate/SKILL.md": (
                "### Step 10.1：强制检查点——FS 对象上传（禁止跳过）"
            )
        },
    )
    result = apply_reviewed_provider_commit_gate(
        probed, repository_id="fs-qa-knowledge"
    )
    assert result["reviewed_commit_pinned"] is True
    assert result["status"] == "incompatible"
    assert {item["code"] for item in result["blockers"]} == {
        "provider_manifest_missing",
        "mandatory_external_side_effect_workflow",
    }


def test_provider_ir_completion_models_layer_oracle_and_test_data() -> None:
    completed = complete_provider_parent_case(
        {
            "id": "FS-001",
            "feature": "查看明细",
            "title": "接口返回专用错误码 s307011534",
            "case_type": "接口测试",
            "preconditions": ["准备统计图"],
            "steps": ["调用查看明细接口"],
            "expected": ["返回错误码 s307011534"],
            "source_refs": ["REQ-001"],
        },
        index=1,
        risk="critical",
        priority="P0",
        required_layers=["backend", "contract"],
    )
    assert completed is not None
    intent, case, mapping = completed
    assert mapping == {"provider_case_id": "FS-001", "test_case_ir_id": "PROVIDER-CASE-001"}
    assert intent["required_layers"] == ["backend", "contract"]
    assert case["layer"] == "backend"
    assert case["risk"] == "critical"
    assert case["test_data"]["provider_case_id"] == "FS-001"
    assert case["test_data"]["preconditions"] == ["准备统计图"]
    assert case["expected"][0]["oracle"]["type"] == "deterministic"
    assert case["automation_candidate"] is True
    assert case["execution_policy"]["allowed_modes"] == ["automated"]


def test_a08_adds_non_provider_cases_for_uncovered_obligations() -> None:
    output = TestDesignerAgent().analyze(
        {
            "requirement_analysis": {
                "requirements": [
                    {
                        "id": "REQ-001",
                        "summary": "自定义维度不支持查看明细",
                        "source_refs": [{"id": "prd", "location": "1-2"}],
                    },
                    {
                        "id": "REQ-002",
                        "summary": "结果集筛选提示指标名",
                        "source_refs": [{"id": "prd", "location": "3-4"}],
                    },
                ]
            },
            "test_strategy": {
                "risk_level": "high",
                "required_layers": ["backend", "contract"],
            },
            "case_provider_draft": {
                "candidate_count": 1,
                "candidates": [
                    {
                        "id": "FS-001",
                        "feature": "自定义维度",
                        "title": "自定义维度拒绝查看明细",
                        "case_type": "功能测试",
                        "preconditions": ["准备自定义维度图"],
                        "steps": ["点击查看明细"],
                        "expected": ["展示专用提示"],
                        "source_refs": ["REQ-001"],
                    }
                ],
            },
        }
    )
    payload = output.payload
    assert [item["id"] for item in payload["parent_cases"]] == [
        "PROVIDER-CASE-001",
        "CASE-001",
    ]
    assert payload["provider_case_mappings"] == [
        {"provider_case_id": "FS-001", "test_case_ir_id": "PROVIDER-CASE-001"}
    ]
    provider_case = payload["parent_cases"][0]
    assert provider_case["test_data"]["feature"] == "自定义维度"
    assert provider_case["layer"] == "scenario"
    assert provider_case["expected"][0]["oracle"]["type"] == "human_review"
    supplemental = payload["parent_cases"][1]
    assert supplemental["test_data"]["obligation"] == "g01_n24_uncovered"
    assert supplemental["test_data"]["requirement_id"] == "REQ-002"
    coverage = {item["requirement_id"]: item["case_ids"] for item in payload["coverage_matrix"]}
    assert coverage["REQ-001"] == ["PROVIDER-CASE-001"]
    assert coverage["REQ-002"] == ["CASE-001"]


def test_shadow_comparison_stays_disabled_until_all_gates_pass() -> None:
    design = {
        "parent_cases": [
            {"id": "PROVIDER-CASE-001"},
            {"id": "CASE-001"},
        ],
        "provider_case_mappings": [
            {"provider_case_id": "FS-001", "test_case_ir_id": "PROVIDER-CASE-001"}
        ],
        "coverage_matrix": [
            {"requirement_id": "REQ-001", "case_ids": ["PROVIDER-CASE-001"]},
            {"requirement_id": "REQ-002", "case_ids": ["CASE-001"]},
        ],
    }
    shadow = compare_provider_shadow(
        {"candidates": [{"id": "FS-001"}]},
        design,
        requirements=[{"id": "REQ-001"}, {"id": "REQ-002"}],
        provider_status="incompatible",
        a09_approved=True,
        n04_valid=True,
        g02_mapping_complete=True,
    )
    assert shadow["mapping_complete"] is True
    assert shadow["supplemental_case_ids"] == ["CASE-001"]
    assert shadow["production_enabled"] is False
    assert shadow["mode"] == "shadow_only"

    enabled = compare_provider_shadow(
        {"candidates": [{"id": "FS-001"}]},
        design,
        requirements=[{"id": "REQ-001"}, {"id": "REQ-002"}],
        provider_status="compatible",
        a09_approved=True,
        n04_valid=True,
        g02_mapping_complete=True,
    )
    assert enabled["production_enabled"] is True
    assert enabled["mode"] == "enabled"
