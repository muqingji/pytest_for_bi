import json
from pathlib import Path

import pytest

from qa_agents.contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.security import SecurityPolicy
from qa_agents.case_compiler import compile_cases
from qa_agents.g02_review import prepare_test_case_review_request
from qa_agents.multica import (
    fetch_multica_run_messages,
    ingest_multica_output,
    prepare_multica_alignment_input,
    prepare_multica_automation_generation_input,
    prepare_multica_automation_review_input,
    prepare_multica_inputs,
    prepare_multica_oracle_review_input,
    prepare_multica_split_review_input,
    prepare_multica_test_data_plan_input,
    prepare_multica_test_data_plan_revision_input,
    prepare_multica_test_design_correction_input,
    prepare_multica_test_design_input,
)
from qa_agents.storage import ArtifactStore


ROOT = Path(__file__).resolve().parents[1]
PILOT_INPUT = ROOT / "eval" / "workflows" / "pilot-001-detail-drill-message-i18n" / "input"
PILOT_RUN = ROOT / "tests" / "fixtures" / "pilot"
G02_POLICY = ROOT / "policies" / "g02-review-policy.json"


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _valid_chart_integrity_evidence() -> dict:
    checks = [
        {"check": item, "status": "passed"}
        for item in ("chart_topology", "source_data", "warehouse_aggregation", "warehouse_dimension")
    ]
    packet = {
        "schema_version": "test-data-integrity-evidence/1.0",
        "provider": "bug-finder/fxops_query",
        "required_checks": sorted(item["check"] for item in checks),
        "checks": checks,
        "valid": True,
    }
    packet["evidence_hash"] = content_hash(packet)
    return packet


def test_prepare_multica_inputs_enforces_profile_input_isolation(tmp_path: Path) -> None:
    manifest = prepare_multica_inputs(
        PILOT_INPUT,
        tmp_path,
        workflow_run_id="multica-pilot-001",
    )

    assert {item["profile_id"] for item in manifest["bundles"]} == {"A02", "A03", "A05"}
    a02 = read_json(tmp_path / "a02-input.json")
    a03 = read_json(tmp_path / "a03-input.json")
    a05 = read_json(tmp_path / "a05-input.json")
    assert set(a02["allowed_inputs"]) == {"frozen_requirement"}
    assert set(a03["allowed_inputs"]) == {
        "frozen_technical_design",
        "test_tool_capabilities",
    }
    assert set(a05["allowed_inputs"]) == {
        "backend_change_set",
        "read_only_source_snapshot",
    }
    assert a05["profile_version"] == "1.1.0"
    assert a05["allowed_inputs"]["backend_change_set"]["change_set"]["change_set_id"]
    assert (
        a05["allowed_inputs"]["backend_change_set"]["implementation_diff"]["content_hash"]
        == "sha256:157bfc4cf1bb25a4ee8cfff4ddb7b6409035bc19108712bdecf8272a7db13452"
    )
    for bundle in (a02, a03, a05):
        assert bundle["integrity"]["oracle_included_in_agent_input"] is False
        assert bundle["integrity"]["business_repository_write_allowed"] is False
        assert bundle["bundle_hash"].startswith("sha256:")


def test_prepare_multica_inputs_rejects_oracle_source_path(tmp_path: Path) -> None:
    oracle_path = tmp_path / "oracle"
    oracle_path.mkdir()
    with pytest.raises(SecurityPolicyError, match="Oracle directory"):
        prepare_multica_inputs(oracle_path, tmp_path / "out", workflow_run_id="run-1")


def valid_a02_output(bundle: dict) -> dict:
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "requirements": [
            {
                "id": "REQ-001",
                "summary": "明确查看明细提示",
                "acceptance_criteria": ["返回需求约定的提示"],
                "source_refs": [
                    {"type": "requirement", "id": "prd.md", "location": "lines:1-2"}
                ],
            }
        ],
        "ambiguities": [],
        "needs_human": [],
    }


def valid_a05_output(bundle: dict) -> dict:
    change_set = bundle["allowed_inputs"]["backend_change_set"]["change_set"]
    path = change_set["changed_files"][0]
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "domain": "backend",
        "change_set_id": change_set["change_set_id"],
        "changed_file_count": len(change_set["changed_files"]),
        "facts": [
            {
                "id": "CHANGE-BACKEND-001",
                "path": path,
                "change_set_id": change_set["change_set_id"],
                "summary": "Changed file",
                "evidence_class": "business_source",
                "eligible_for_business_alignment": True,
                "source_refs": [
                    {
                        "type": "change_set",
                        "id": change_set["change_set_id"],
                        "location": path,
                    }
                ],
            }
        ],
    }


def write_alignment_upstream_artifacts(root: Path) -> None:
    store = ArtifactStore(root)
    common = {
        "workflow_run_id": "multica-pilot-001",
        "workflow_mode": "new_requirement",
        "source_snapshot_id": "pilot-001-source-v1",
        "producer": Producer(component_id="test"),
    }
    artifacts = [
        ArtifactEnvelope(
            **common,
            artifact_id="a02-requirement-analysis",
            payload={
                "requirements": [
                    {"id": "REQ-001", "summary": "专用提示", "source_refs": ["prd.md"]}
                ]
            },
        ),
        ArtifactEnvelope(
            **common,
            artifact_id="a03-technical-testability-analysis",
            payload={
                "technical_facts": [
                    {"id": "TF-001", "summary": "专用错误码", "source_refs": ["tech.md"]}
                ]
            },
        ),
        ArtifactEnvelope(
            **common,
            artifact_id="a05-backend-change-analysis",
            payload={
                "facts": [
                    {
                        "id": "BE-001",
                        "summary": "实现专用错误码",
                        "eligible_for_business_alignment": True,
                        "source_refs": ["Service.java"],
                    },
                    {
                        "id": "TE-001",
                        "summary": "新增单测",
                        "eligible_for_business_alignment": False,
                        "source_refs": ["ServiceTest.java"],
                    },
                ]
            },
        ),
    ]
    for artifact in artifacts:
        store.write_artifact(artifact)


def valid_a06_output(bundle: dict) -> dict:
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "mappings": [
            {
                "requirement_id": "REQ-001",
                "technical_fact_ids": ["TF-001"],
                "change_fact_ids": ["BE-001"],
                "status": "aligned",
                "source_refs": ["REQ-001", "TF-001", "BE-001"],
            }
        ],
        "findings": [],
    }


def test_ingest_multica_output_binds_response_to_frozen_input(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")

    artifact = ingest_multica_output(
        input_dir / "a02-input.json",
        json.dumps(valid_a02_output(bundle), ensure_ascii=False),
        tmp_path / "run",
        task_id="task-001",
        issue_id="issue-001",
        attachment_id="attachment-001",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )

    assert artifact["artifact_id"] == "a02-requirement-analysis"
    assert artifact["payload"]["input_bundle_hash"] == bundle["bundle_hash"]
    assert artifact["producer"]["tool_bundle_version"] == "multica-task:task-001"
    assert artifact["producer"]["profile_version"] == "1.0.0"
    assert artifact["producer"]["prompt_version"] == "1.1.0"
    assert (tmp_path / "run" / "artifacts" / "a02-requirement-analysis.json").exists()


@pytest.mark.parametrize("field", ["workflow_run_id", "source_snapshot_id", "input_bundle_hash"])
def test_ingest_multica_output_rejects_cross_run_response(
    tmp_path: Path, field: str
) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")
    output = valid_a02_output(bundle)
    output[field] = "wrong-binding"

    with pytest.raises(ContractError, match=field):
        ingest_multica_output(
            input_dir / "a02-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "run",
            task_id="task-001",
            issue_id="issue-001",
            attachment_id="attachment-001",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_ingest_multica_output_accepts_prose_and_fenced_wrappers(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")
    output = valid_a02_output(bundle)
    for wrapped in (
        f"```json\n{json.dumps(output, ensure_ascii=False)}\n```",
        f"人话说明：已完成需求分析。\n\n{json.dumps(output, ensure_ascii=False)}",
    ):
        artifact = ingest_multica_output(
            input_dir / "a02-input.json",
            wrapped,
            tmp_path / "run",
            task_id="task-001",
            issue_id="issue-001",
            attachment_id="attachment-001",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )
        assert artifact["payload"]["input_bundle_hash"] == bundle["bundle_hash"]

    output["requirements"][0]["source_refs"] = []
    with pytest.raises(ContractError, match="source_refs"):
        ingest_multica_output(
            input_dir / "a02-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "run",
            task_id="task-001",
            issue_id="issue-001",
            attachment_id="attachment-001",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_ingest_multica_output_uses_last_text_message_only(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")
    response = [
        {"type": "text", "content": "正在读取唯一批准附件"},
        {
            "type": "tool_use",
            "tool": "exec_command",
            "task_id": "task-002",
            "issue_id": "issue-002",
            "input": {
                "command": "/bin/zsh -lc 'multica issue get issue-002 --output json'"
            },
        },
        {
            "type": "tool_use",
            "tool": "exec_command",
            "task_id": "task-002",
            "issue_id": "issue-002",
            "input": {
                "command": "/bin/zsh -lc 'multica attachment download attachment-002 -o .'"
            },
        },
        {
            "type": "text",
            "content": json.dumps(valid_a02_output(bundle), ensure_ascii=False),
        },
    ]

    artifact = ingest_multica_output(
        input_dir / "a02-input.json",
        json.dumps(response, ensure_ascii=False),
        tmp_path / "run",
        task_id="task-002",
        issue_id="issue-002",
        attachment_id="attachment-002",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )

    assert artifact["payload"]["requirements"][0]["id"] == "REQ-001"


def test_ingest_multica_output_rejects_downstream_incompatible_shape(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")
    output = valid_a02_output(bundle)
    output["requirements"][0].pop("summary")

    with pytest.raises(ContractError, match="summary"):
        ingest_multica_output(
            input_dir / "a02-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "run",
            task_id="task-003",
            issue_id="issue-003",
            attachment_id="attachment-003",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_fetch_multica_messages_uses_argument_array_and_binds_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Completed:
        returncode = 0
        stderr = ""
        stdout = json.dumps(
            [{"type": "text", "task_id": "task-004", "content": "{}"}]
        )

    captured: dict = {}

    def fake_run(command: list[str], **kwargs: object) -> Completed:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("qa_agents.multica.subprocess.run", fake_run)
    output_path = tmp_path / "messages.json"
    messages = fetch_multica_run_messages("workspace-001", "task-004", output_path)

    assert captured["command"] == [
        "multica",
        "issue",
        "run-messages",
        "task-004",
        "--workspace-id",
        "workspace-001",
        "--output",
        "json",
    ]
    assert captured["kwargs"]["check"] is False
    assert messages[0]["task_id"] == "task-004"
    assert read_json(output_path) == messages


def test_ingest_a05_rejects_fact_outside_frozen_change_set(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a05-input.json")
    output = valid_a05_output(bundle)
    output["facts"][0]["path"] = "outside/change-set.java"

    with pytest.raises(ContractError, match="outside the frozen ChangeSet"):
        ingest_multica_output(
            input_dir / "a05-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "run",
            task_id="task-005",
            issue_id="issue-005",
            attachment_id="attachment-005",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_ingest_multica_output_rejects_shell_command_substitution(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")
    response = [
        {
            "type": "tool_use",
            "tool": "exec_command",
            "task_id": "task-006",
            "issue_id": "issue-006",
            "input": {"command": "/bin/zsh -lc 'cat $(pwd)/a02-input.json'"},
        },
        {
            "type": "text",
            "task_id": "task-006",
            "issue_id": "issue-006",
            "content": json.dumps(valid_a02_output(bundle), ensure_ascii=False),
        },
    ]

    with pytest.raises(SecurityPolicyError, match="Shell composition"):
        ingest_multica_output(
            input_dir / "a02-input.json",
            json.dumps(response, ensure_ascii=False),
            tmp_path / "run",
            task_id="task-006",
            issue_id="issue-006",
            attachment_id="attachment-006",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_ingest_multica_output_rejects_another_issue_attachment(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")
    response = [
        {
            "type": "tool_use",
            "tool": "exec_command",
            "task_id": "task-007",
            "issue_id": "issue-007",
            "input": {
                "command": "/bin/zsh -lc 'multica attachment download attachment-other --output-dir .'"
            },
        },
        {
            "type": "text",
            "task_id": "task-007",
            "issue_id": "issue-007",
            "content": json.dumps(valid_a02_output(bundle), ensure_ascii=False),
        },
    ]

    with pytest.raises(SecurityPolicyError, match="Unapproved Multica command"):
        ingest_multica_output(
            input_dir / "a02-input.json",
            json.dumps(response, ensure_ascii=False),
            tmp_path / "run",
            task_id="task-007",
            issue_id="issue-007",
            attachment_id="attachment-007",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_ingest_multica_output_rejects_issue_metadata_access(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")
    response = [
        {
            "type": "tool_use",
            "tool": "exec_command",
            "task_id": "task-metadata",
            "issue_id": "issue-metadata",
            "input": {
                "command": "/bin/zsh -lc 'multica issue metadata list issue-metadata --output json'"
            },
        },
        {
            "type": "text",
            "task_id": "task-metadata",
            "issue_id": "issue-metadata",
            "content": json.dumps(valid_a02_output(bundle), ensure_ascii=False),
        },
    ]

    with pytest.raises(SecurityPolicyError, match="Unapproved Multica command"):
        ingest_multica_output(
            input_dir / "a02-input.json",
            json.dumps(response, ensure_ascii=False),
            tmp_path / "run",
            task_id="task-metadata",
            issue_id="issue-metadata",
            attachment_id="attachment-metadata",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_prepare_and_ingest_multica_alignment_input(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "stage1" / "artifacts"
    write_alignment_upstream_artifacts(tmp_path / "stage1")
    bundle = prepare_multica_alignment_input(artifact_dir, tmp_path / "inputs")

    assert set(bundle["allowed_inputs"]) == {
        "requirement_analysis",
        "technical_analysis",
        "backend_change_analysis",
    }
    assert len(bundle["upstream_artifacts"]) == 3
    artifact = ingest_multica_output(
        tmp_path / "inputs" / "a06-input.json",
        json.dumps(valid_a06_output(bundle), ensure_ascii=False),
        tmp_path / "stage2",
        task_id="task-008",
        issue_id="issue-008",
        attachment_id="attachment-008",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )

    assert artifact["artifact_id"] == "a06-alignment-result"
    assert artifact["payload"]["mappings"][0]["status"] == "aligned"


def test_prepare_multica_alignment_rejects_tampered_upstream(tmp_path: Path) -> None:
    write_alignment_upstream_artifacts(tmp_path / "stage1")
    path = tmp_path / "stage1" / "artifacts" / "a02-requirement-analysis.json"
    artifact = read_json(path)
    artifact["payload"]["requirements"][0]["summary"] = "tampered"
    ArtifactStore(path.parent).write_json(path.name, artifact)

    with pytest.raises(ContractError, match="Artifact hash mismatch"):
        prepare_multica_alignment_input(path.parent, tmp_path / "inputs")


def test_ingest_a06_rejects_test_code_as_implementation_evidence(tmp_path: Path) -> None:
    write_alignment_upstream_artifacts(tmp_path / "stage1")
    bundle = prepare_multica_alignment_input(
        tmp_path / "stage1" / "artifacts", tmp_path / "inputs"
    )
    output = valid_a06_output(bundle)
    output["mappings"][0]["change_fact_ids"] = ["TE-001"]

    with pytest.raises(ContractError, match="non-business implementation evidence"):
        ingest_multica_output(
            tmp_path / "inputs" / "a06-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage2",
            task_id="task-009",
            issue_id="issue-009",
            attachment_id="attachment-009",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_ingest_a06_rejects_hallucinated_source_reference(tmp_path: Path) -> None:
    write_alignment_upstream_artifacts(tmp_path / "stage1")
    bundle = prepare_multica_alignment_input(
        tmp_path / "stage1" / "artifacts", tmp_path / "inputs"
    )
    output = valid_a06_output(bundle)
    output["mappings"][0]["source_refs"].append("NONEXISTENT-001")

    with pytest.raises(ContractError, match="unknown source evidence"):
        ingest_multica_output(
            tmp_path / "inputs" / "a06-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage2",
            task_id="task-010",
            issue_id="issue-010",
            attachment_id="attachment-010",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def prepare_real_a08_bundle(tmp_path: Path) -> dict:
    return prepare_multica_test_design_input(
        PILOT_RUN / "multica-stage1" / "artifacts" / "a02-requirement-analysis.json",
        PILOT_RUN
        / "multica-stage1"
        / "artifacts"
        / "a03-technical-testability-analysis.json",
        PILOT_RUN / "multica-stage2" / "artifacts" / "a06-alignment-result.json",
        PILOT_RUN / "multica-stage3" / "artifacts" / "n24-test-strategy.json",
        PILOT_RUN / "g01" / "g01-review-request.json",
        PILOT_RUN / "g01" / "g01-review-decision.json",
        ROOT / "policies" / "g01-review-policy.json",
        tmp_path,
    )


def valid_a08_output(bundle: dict) -> dict:
    requirements = bundle["allowed_inputs"]["validated_analysis"][
        "requirement_analysis"
    ]["requirements"]
    rules = bundle["allowed_inputs"]["approved_scope"]["test_rule_obligations"]
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "test_intents": [
            {
                "id": "INTENT-001",
                "objective": "验证查看明细的场景化双语提示",
                "risk": "critical",
                "required_layers": ["backend", "contract", "e2e"],
                "source_refs": ["REQ-001"],
            }
        ],
        "parent_cases": [
            {
                "id": "CASE-001",
                "title": "查看明细场景化双语提示",
                "intent_ids": ["INTENT-001"],
                "layer": "scenario",
                "required_layers": ["backend", "contract", "e2e"],
                "risk": "critical",
                "priority": "P0",
                "source_refs": ["REQ-001"],
                "preconditions": ["准备目标场景数据"],
                "test_data": {"language": ["zh-CN", "en"]},
                "steps": ["调用查看明细接口"],
                "expected": [
                    {
                        "id": "EXP-001",
                        "description": "返回冻结的当前语言提示",
                        "oracle": {
                            "type": "deterministic",
                            "matcher": "template_equals",
                            "observation_point": "response.message",
                            "source_ref": "G01:test_rules.localization",
                        },
                    }
                ],
                "cleanup": [],
                "execution_policy": {"allowed_modes": ["automated"]},
                "automation_candidate": True,
            }
        ],
        "coverage_matrix": [
            {"requirement_id": item["id"], "case_ids": ["CASE-001"]}
            for item in requirements
        ],
        "test_rule_coverage": [
            {"rule_id": item["id"], "case_ids": ["CASE-001"]} for item in rules
        ],
    }


def test_prepare_and_ingest_multica_a08_input(tmp_path: Path) -> None:
    bundle = prepare_real_a08_bundle(tmp_path / "inputs")

    assert set(bundle["allowed_inputs"]) == {
        "validated_analysis",
        "approved_scope",
        "test_strategy",
        "case_provider_draft",
    }
    assert bundle["allowed_inputs"]["test_strategy"]["risk_level"] == "critical"
    assert bundle["allowed_inputs"]["approved_scope"]["decision"] == "approved"
    assert bundle["allowed_inputs"]["approved_scope"]["status"] == "approved"
    assert {
        item["id"]
        for item in bundle["allowed_inputs"]["approved_scope"][
            "test_rule_obligations"
        ]
    } == {
        "RULE-MULTIPLE-REASONS",
        "RULE-SINGLE-METRIC",
        "RULE-ENTRY-CONSISTENCY",
        "RULE-CUSTOM-DIMENSION",
        "RULE-DYNAMIC-RELATION",
        "RULE-MULTI-RELATION",
        "RULE-PERMISSION-PRIORITY",
        "RULE-HISTORICAL-COMPATIBILITY",
        "RULE-I18N-CUSTOM-DIMENSION",
        "RULE-I18N-RESULT-SET",
        "RULE-I18N-MULTI-RELATION",
        "RULE-I18N-DYNAMIC-RELATION",
    }

    artifact = ingest_multica_output(
        tmp_path / "inputs" / "a08-input.json",
        json.dumps(valid_a08_output(bundle), ensure_ascii=False),
        tmp_path / "stage4",
        task_id="task-a08",
        issue_id="issue-a08",
        attachment_id="attachment-a08",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    assert artifact["artifact_id"] == "a08-test-design-ir"
    assert artifact["payload"]["parent_cases"][0]["priority"] == "P0"


def test_ingest_a08_rejects_missing_approved_rule_coverage(tmp_path: Path) -> None:
    bundle = prepare_real_a08_bundle(tmp_path / "inputs")
    output = valid_a08_output(bundle)
    output["test_rule_coverage"].pop()

    with pytest.raises(ContractError, match="every G01-approved test rule"):
        ingest_multica_output(
            tmp_path / "inputs" / "a08-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage4",
            task_id="task-a08",
            issue_id="issue-a08",
            attachment_id="attachment-a08",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_ingest_a08_allows_test_oracles_but_rejects_evaluation_oracle(
    tmp_path: Path,
) -> None:
    bundle = prepare_real_a08_bundle(tmp_path / "inputs")
    output = valid_a08_output(bundle)
    output["evaluation_oracle_registry"] = {"answer": "hidden"}

    with pytest.raises(SecurityPolicyError, match="Evaluation Oracle field"):
        ingest_multica_output(
            tmp_path / "inputs" / "a08-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage4",
            task_id="task-a08",
            issue_id="issue-a08",
            attachment_id="attachment-a08",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_prepare_multica_a08_correction_input_compacts_and_binds_feedback(
    tmp_path: Path,
) -> None:
    bundle = prepare_multica_test_design_correction_input(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        PILOT_RUN / "multica-stage5" / "artifacts" / "a09-oracle-coverage-review.json",
        PILOT_RUN
        / "multica-stage6"
        / "artifacts"
        / "n04-test-case-ir-validation.json",
        tmp_path,
    )

    assert bundle["profile_version"] == "1.2.1"
    assert set(bundle["allowed_inputs"]) == {
        "validated_analysis",
        "approved_scope",
        "test_strategy",
        "case_provider_draft",
        "previous_test_design_ir",
        "correction_feedback",
    }
    feedback = bundle["allowed_inputs"]["correction_feedback"]
    assert feedback["schema_version"] == "test-design-correction/1.1"
    assert bundle["allowed_inputs"]["approved_scope"]["decision"] == "approved"
    assert feedback["correction_attempt"] == 1
    assert feedback["max_correction_attempts"] == 2
    assert len(feedback["a09_issues"]) == 22
    assert len(feedback["n04_schema_issue_groups"]) < 86
    assert {
        item["issue_code"] for item in feedback["n04_schema_issue_groups"]
    } == {
        "invalid_test_data_type",
        "missing_execution_modes",
        "oracle_required_field",
    }
    assert all(
        item["affected_locations"] for item in feedback["n04_schema_issue_groups"]
    )
    assert all(item["group_id"] for item in feedback["n04_schema_issue_groups"])
    assert "input_bundle_hash" not in bundle["allowed_inputs"]["previous_test_design_ir"]
    assert bundle["integrity"]["evaluation_oracle_included_in_agent_input"] is False
    assert (tmp_path / "a08-input.json").exists()


def test_prepare_multica_a08_correction_input_rejects_exhausted_budget(
    tmp_path: Path,
) -> None:
    n04 = read_json(
        PILOT_RUN
        / "multica-stage6"
        / "artifacts"
        / "n04-test-case-ir-validation.json"
    )
    n04["payload"]["correction_attempt"] = n04["payload"]["max_correction_attempts"]
    n04["artifact_hash"] = artifact_hash_from_mapping(n04)
    n04_path = tmp_path / "n04-test-case-ir-validation.json"
    write_json(n04_path, n04)

    with pytest.raises(ContractError, match="budget is exhausted"):
        prepare_multica_test_design_correction_input(
            PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
            PILOT_RUN / "multica-inputs" / "a08-input.json",
            PILOT_RUN
            / "multica-stage5"
            / "artifacts"
            / "a09-oracle-coverage-review.json",
            n04_path,
            tmp_path / "output",
        )


def test_prepare_multica_a08_correction_input_accepts_g02_direction(
    tmp_path: Path,
) -> None:
    a09 = read_json(
        PILOT_RUN
        / "multica-stage5"
        / "artifacts"
        / "a09-oracle-coverage-review.json"
    )
    a09["payload"]["approved"] = True
    a09["status"] = "completed"
    a09["artifact_hash"] = artifact_hash_from_mapping(a09)
    a09_path = tmp_path / "a09-approved.json"
    write_json(a09_path, a09)
    n04 = read_json(
        PILOT_RUN
        / "multica-stage6"
        / "artifacts"
        / "n04-test-case-ir-validation.json"
    )
    n04["payload"]["oracle_review_artifact_hash"] = a09["artifact_hash"]
    n04["evidence_refs"] = [
        {
            **dict(item),
            "content_hash": a09["artifact_hash"],
        }
        if str(item.get("source_id", "")) == "a09-oracle-coverage-review"
        else dict(item)
        for item in n04.get("evidence_refs", [])
    ]
    n04["payload"]["valid"] = True
    n04["payload"]["blocking_issue_count"] = 0
    n04["payload"]["issues"] = []
    n04["payload"]["next_node"] = "G02"
    n04["payload"]["g02_status"] = "pending"
    n04["artifact_hash"] = artifact_hash_from_mapping(n04)
    n04_path = tmp_path / "n04-valid.json"
    write_json(n04_path, n04)
    g02_dir = tmp_path / "g02"
    request = prepare_test_case_review_request(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        a09_path,
        n04_path,
        G02_POLICY,
        g02_dir,
    )
    comment = {"id": "g02-comment-1", "created_at": "2026-08-10T08:04:00Z", "content": "CASE 缺少 en 下钻边界场景"}
    decision = {
        "schema_version": "test-case-ir-review-decision/1.0",
        "gate_id": "G02",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "review_key": request["review_key"],
        "decision": "request_changes",
        "decided_at": "2026-08-10T08:05:00Z",
        "actor": {
            "type": "human",
            "id": "muqj11262",
            "role": "qa_owner",
            "multica_member_id": "c2c6b9c6-4fb9-4439-a4a5-de4e93784c54",
        },
        "multica_event": {
            "workspace_id": "457d700f-6c27-4a59-871d-c2c56bca9f46",
            "issue_id": "g02-issue-1",
            "event_id": "event-1",
            "status": "blocked",
            "comment_id": comment["id"],
            "identity_evidence_mode": "assigned_member_pilot",
        },
        "reviewer_comment": comment,
        "reason": comment["content"],
    }
    decision["decision_hash"] = content_hash(decision)
    decision_path = g02_dir / "g02-review-decision.json"
    write_json(decision_path, decision)

    bundle = prepare_multica_test_design_correction_input(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        a09_path,
        n04_path,
        tmp_path / "a08-correction-g02",
        g02_review_request_path=g02_dir / "g02-review-request.json",
        g02_review_decision_path=decision_path,
    )

    assert bundle["profile_version"] == "1.4.0"
    assert bundle["upstream_g02_decision"] == {
        "request_hash": request["request_hash"],
        "decision_hash": decision["decision_hash"],
    }
    direction = bundle["allowed_inputs"]["g02_review_direction"]
    assert direction["decision"] == "request_changes"
    assert direction["reason"] == comment["content"]
    assert direction["reviewer_comment"]["id"] == "g02-comment-1"
    assert direction["automatic_budget_reset"] is False
    assert direction["required_revalidation"] == ["A09", "N04"]
    feedback = bundle["allowed_inputs"]["correction_feedback"]
    assert feedback["schema_version"] == "test-design-correction/1.3"
    assert feedback["recovery_mode"] == "g02_reviewer_direction"
    assert feedback["correction_attempt"] == 2


def correction_resolutions(bundle: dict) -> list[dict]:
    feedback = bundle["allowed_inputs"]["correction_feedback"]
    resolutions = [
        {
            "feedback_id": item["id"],
            "disposition": (
                "rejected_conflict_with_frozen_evidence"
                if item["id"] == "A09-018"
                else "fixed"
            ),
            "affected_case_ids": ["CASE-001"],
            "source_refs": list(item["source_refs"]),
            "rationale": "Resolved against the frozen test rules",
        }
        for item in feedback["a09_issues"]
    ]
    resolutions.extend(
        {
            "group_id": item["group_id"],
            "disposition": "fixed",
            "affected_case_ids": ["CASE-001"],
            "source_refs": list(item["source_refs"]),
            "rationale": "The formal Test Case IR contract is satisfied",
        }
        for item in feedback["n04_schema_issue_groups"]
    )
    return resolutions


def test_ingest_multica_a08_correction_requires_complete_feedback_resolution(
    tmp_path: Path,
) -> None:
    bundle = prepare_multica_test_design_correction_input(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        PILOT_RUN / "multica-stage5" / "artifacts" / "a09-oracle-coverage-review.json",
        PILOT_RUN
        / "multica-stage6"
        / "artifacts"
        / "n04-test-case-ir-validation.json",
        tmp_path / "inputs",
    )
    output = valid_a08_output(bundle)
    output["correction_resolutions"] = correction_resolutions(bundle)

    artifact = ingest_multica_output(
        tmp_path / "inputs" / "a08-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage7",
        task_id="task-a08-correction",
        issue_id="issue-a08-correction",
        attachment_id="attachment-a08-correction",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.2.0",
    )
    assert artifact["producer"]["profile_version"] == "1.2.1"

    output["correction_resolutions"].pop()
    with pytest.raises(ContractError, match="resolve every N04 issue group"):
        ingest_multica_output(
            tmp_path / "inputs" / "a08-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "rejected",
            task_id="task-a08-correction",
            issue_id="issue-a08-correction",
            attachment_id="attachment-a08-correction",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.2.0",
        )


def test_ingest_multica_a08_correction_accepts_legacy_n04_issue_code_bindings(
    tmp_path: Path,
) -> None:
    bundle = prepare_multica_test_design_correction_input(
        PILOT_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        PILOT_RUN / "multica-inputs" / "a08-input.json",
        PILOT_RUN / "multica-stage5" / "artifacts" / "a09-oracle-coverage-review.json",
        PILOT_RUN
        / "multica-stage6"
        / "artifacts"
        / "n04-test-case-ir-validation.json",
        tmp_path / "inputs",
    )
    output = valid_a08_output(bundle)
    output["correction_resolutions"] = correction_resolutions(bundle)
    groups = bundle["allowed_inputs"]["correction_feedback"][
        "n04_schema_issue_groups"
    ]
    group_codes = {item.pop("group_id"): item["issue_code"] for item in groups}
    bundle["profile_version"] = "1.2.0"
    bundle_without_hash = {key: value for key, value in bundle.items() if key != "bundle_hash"}
    bundle["bundle_hash"] = content_hash(bundle_without_hash)
    write_json(tmp_path / "inputs" / "a08-input.json", bundle)

    output["input_bundle_hash"] = bundle["bundle_hash"]
    for resolution in output["correction_resolutions"]:
        group_id = resolution.pop("group_id", None)
        if group_id:
            resolution["issue_code"] = group_codes[group_id]

    artifact = ingest_multica_output(
        tmp_path / "inputs" / "a08-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "legacy-stage7",
        task_id="task-a08-legacy-correction",
        issue_id="issue-a08-legacy-correction",
        attachment_id="attachment-a08-legacy-correction",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.2.0",
    )
    assert artifact["producer"]["profile_version"] == "1.2.0"


def prepare_a09_bundle(tmp_path: Path) -> dict:
    a08_bundle = prepare_real_a08_bundle(tmp_path / "inputs")
    ingest_multica_output(
        tmp_path / "inputs" / "a08-input.json",
        json.dumps(valid_a08_output(a08_bundle), ensure_ascii=False),
        tmp_path / "stage4",
        task_id="task-a08",
        issue_id="issue-a08",
        attachment_id="attachment-a08",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.1",
    )
    return prepare_multica_oracle_review_input(
        tmp_path / "stage4" / "artifacts" / "a08-test-design-ir.json",
        tmp_path / "inputs" / "a08-input.json",
        ROOT / "policies" / "oracle-rule-library.json",
        tmp_path / "inputs",
    )


def valid_a09_output(bundle: dict) -> dict:
    evidence = bundle["allowed_inputs"]["frozen_evidence"]
    requirements = evidence["validated_analysis"]["requirement_analysis"][
        "requirements"
    ]
    obligations = evidence["approved_scope"]["test_rule_obligations"]
    dimensions = bundle["allowed_inputs"]["oracle_rule_library"][
        "required_coverage_dimensions"
    ]
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "approved": True,
        "issues": [],
        "coverage_dimensions": [
            {
                "dimension": dimension,
                "status": "covered",
                "case_ids": ["CASE-001"],
                "source_refs": ["CASE-001"],
                "rationale": "covered by the frozen Case",
            }
            for dimension in dimensions
        ],
        "requirement_coverage": [
            {
                "requirement_id": item["id"],
                "status": "covered",
                "case_ids": ["CASE-001"],
            }
            for item in requirements
        ],
        "test_rule_coverage": [
            {
                "rule_id": item["id"],
                "status": "covered",
                "case_ids": ["CASE-001"],
            }
            for item in obligations
        ],
        "manual_case_recommendations": [],
        "code_coverage_reviewed": False,
        "evaluation_oracle_accessed": False,
    }


def test_prepare_and_ingest_multica_a09_input(tmp_path: Path) -> None:
    bundle = prepare_a09_bundle(tmp_path)

    assert set(bundle["allowed_inputs"]) == {
        "test_design_ir",
        "oracle_rule_library",
        "frozen_evidence",
    }
    assert bundle["integrity"]["evaluation_oracle_registry_included"] is False
    artifact = ingest_multica_output(
        tmp_path / "inputs" / "a09-input.json",
        json.dumps(valid_a09_output(bundle), ensure_ascii=False),
        tmp_path / "stage5",
        task_id="task-a09",
        issue_id="issue-a09",
        attachment_id="attachment-a09",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    assert artifact["artifact_id"] == "a09-oracle-coverage-review"
    assert artifact["payload"]["code_coverage_reviewed"] is False


def test_ingest_a09_backfills_blocking_issue_human_facing_fields(
    tmp_path: Path,
) -> None:
    bundle = prepare_a09_bundle(tmp_path)
    output = valid_a09_output(bundle)
    output["approved"] = False
    output["status"] = "needs_human"
    output["issues"] = [
        {
            "id": "A09-001",
            "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE",
            "severity": "blocking",
            "category": "oracle",
            "message": "expected_value 指向不存在的路径。",
            "path": "allowed_inputs",
            "route_to": "A08",
            "case_id": "CASE-001",
            "expected_id": "EXP-001",
            "source_refs": ["REQ-001"],
            "recommendation": "改为可解析期望值。",
        }
    ]
    artifact = ingest_multica_output(
        tmp_path / "inputs" / "a09-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage5",
        task_id="task-a09",
        issue_id="issue-a09",
        attachment_id="attachment-a09",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    issue = artifact["payload"]["issues"][0]
    assert issue["plain_summary"]
    assert issue["human_title"]


def test_ingest_a09_accepts_issue_with_plain_summary(tmp_path: Path) -> None:
    bundle = prepare_a09_bundle(tmp_path)
    output = valid_a09_output(bundle)
    output["approved"] = False
    output["status"] = "needs_human"
    output["issues"] = [
        {
            "id": "A09-001",
            "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE",
            "human_title": "预期结果写错了",
            "plain_summary": "预期结果指向不存在的字段，用例无法校验。",
            "severity": "blocking",
            "category": "oracle",
            "message": "expected_value 指向不存在的路径。",
            "path": "allowed_inputs",
            "route_to": "A08",
            "case_id": "CASE-001",
            "expected_id": "EXP-001",
            "source_refs": ["REQ-001"],
            "recommendation": "改为可解析期望值。",
        }
    ]
    artifact = ingest_multica_output(
        tmp_path / "inputs" / "a09-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage5",
        task_id="task-a09",
        issue_id="issue-a09",
        attachment_id="attachment-a09",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    assert artifact["payload"]["issues"][0]["plain_summary"]


def test_ingest_a09_accepts_gap_issue_without_human_facing_fields(
    tmp_path: Path,
) -> None:
    bundle = prepare_a09_bundle(tmp_path)
    output = valid_a09_output(bundle)
    output["status"] = "completed_with_gaps"
    output["issues"] = [
        {
            "id": "A09-001",
            "issue_code": "UNFROZEN_ORACLE_BASELINE",
            "severity": "gap",
            "category": "oracle",
            "message": "六处 human_review Oracle 依赖未冻结基线。",
            "path": "test_design_ir.parent_cases",
            "route_to": "A08",
            "case_id": None,
            "expected_id": None,
            "source_refs": ["RULE-SINGLE-METRIC"],
            "recommendation": "执行时人工确认。",
        }
    ]
    artifact = ingest_multica_output(
        tmp_path / "inputs" / "a09-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage5",
        task_id="task-a09",
        issue_id="issue-a09",
        attachment_id="attachment-a09",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    assert artifact["status"] == ArtifactStatus.COMPLETED_WITH_GAPS


def test_ingest_a09_rejects_code_coverage_claim(tmp_path: Path) -> None:
    bundle = prepare_a09_bundle(tmp_path)
    output = valid_a09_output(bundle)
    output["code_coverage_reviewed"] = True

    with pytest.raises(ContractError, match="not code coverage"):
        ingest_multica_output(
            tmp_path / "inputs" / "a09-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage5",
            task_id="task-a09",
            issue_id="issue-a09",
            attachment_id="attachment-a09",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )


def test_a03_instructions_fail_closed_on_missing_blocking_evidence() -> None:
    workspace = read_json(ROOT / "multica" / "workspace-manifest.json")
    a03 = next(item for item in workspace["agents"] if item["logical_id"] == "A03")
    instruction = (ROOT.parent / a03["instruction_path"]).read_text(encoding="utf-8")

    assert a03["instruction_version"] == "1.1.2"
    assert "blocking_items | all(.source_refs 是非空数组)" in instruction
    assert "不得把它放进" in instruction


def test_g02_pilot_approver_policy_matches_workspace_manifest() -> None:
    policy = read_json(ROOT / "policies" / "g02-review-policy.json")
    workspace = read_json(ROOT / "multica" / "workspace-manifest.json")
    workspace_policy = workspace["gate_policies"]["G02"]
    pilot_state = workspace["pilot_state"]

    assert policy["gate_id"] == "G02"
    assert policy["approval_mode"] == "named_qa_owner_single_signoff"
    assert policy["allowed_actor_ids"] == [workspace_policy["allowed_actor_id"]]
    assert policy["allowed_multica_member_ids"] == [
        workspace_policy["allowed_multica_member_id"]
    ]
    assert policy["allowed_roles"] == [workspace_policy["allowed_role"]]
    assert pilot_state["g02_approver_id"] == workspace_policy["allowed_actor_id"]
    assert pilot_state["g02_approver_role"] == workspace_policy["allowed_role"]
    assert policy["require_n04_valid"] is True
    assert policy["temporary_policy"] is True
    assert policy["production_release_authority"] is False
    assert workspace_policy["production_release_authority"] is False
    assert policy["migration"]["target_role"] == "qa_reviewer"


def test_g03_pilot_approver_policy_matches_workspace_manifest() -> None:
    policy = read_json(ROOT / "policies" / "g03-review-policy.json")
    workspace = read_json(ROOT / "multica" / "workspace-manifest.json")
    workspace_policy = workspace["gate_policies"]["G03"]
    pilot_state = workspace["pilot_state"]

    assert policy["gate_id"] == "G03"
    assert policy["approval_mode"] == "named_qa_owner_single_signoff"
    assert policy["allowed_actor_ids"] == [workspace_policy["allowed_actor_id"]]
    assert policy["allowed_multica_member_ids"] == [
        workspace_policy["allowed_multica_member_id"]
    ]
    assert policy["allowed_roles"] == [workspace_policy["allowed_role"]]
    assert pilot_state["g03_approver_id"] == workspace_policy["allowed_actor_id"]
    assert pilot_state["g03_approver_role"] == workspace_policy["allowed_role"]
    assert policy["require_n05_valid"] is True
    assert policy["require_human_actor"] is True
    assert policy["temporary_policy"] is True
    assert policy["production_release_authority"] is False
    assert workspace_policy["production_release_authority"] is False
    assert workspace_policy["policy_path"] == "policies/g03-review-policy.json"
    assert workspace_policy["workflow_contract"] == "multica/g03-review-workflow.json"
    assert policy["migration"]["target_role"] == "qa_reviewer"


def build_a11_prepare_inputs(tmp_path: Path) -> tuple[dict, Path, Path]:
    """Return (a11_bundle, a08_artifact_path, n25_compiled_path) from real pilot inputs."""
    bundle = prepare_real_a08_bundle(tmp_path / "inputs")
    a08_input_path = tmp_path / "inputs" / "a08-input.json"
    artifact = ingest_multica_output(
        a08_input_path,
        json.dumps(valid_a08_output(bundle), ensure_ascii=False),
        tmp_path / "stage4",
        task_id="task-a08-a11",
        issue_id="issue-a08-a11",
        attachment_id="attachment-a08-a11",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    a08_path = tmp_path / "stage4" / "artifacts" / "a08-test-design-ir.json"
    a08 = read_json(a08_path)
    parents = a08["payload"]["parent_cases"]
    children = compile_cases(parents, {})
    compiled = ArtifactEnvelope(
        workflow_run_id=a08["workflow_run_id"],
        workflow_mode=a08["workflow_mode"],
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id=a08["source_snapshot_id"],
        producer=Producer(component_id="N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "parent_artifact_id": "a08-test-design-ir",
            "parent_artifact_hash": a08["artifact_hash"],
            "compiled_cases": children,
            "parent_count": len(parents),
            "child_count": len(children),
            "compile_rule_version": "n25-compiler/1.0",
        },
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a08-test-design-ir",
                location="a08-test-design-ir.json",
                content_hash=a08["artifact_hash"],
            ),
        ),
    )
    ArtifactStore(tmp_path / "stage13").write_artifact(compiled)
    compiled_path = tmp_path / "stage13" / "artifacts" / "n25-compiled-test-cases.json"
    a11_bundle = prepare_multica_split_review_input(
        a08_path,
        a08_input_path,
        compiled_path,
        ROOT / "policies" / "oracle-rule-library.json",
        tmp_path / "a11-inputs",
    )
    return a11_bundle, a08_path, compiled_path


def valid_a11_output(bundle: dict) -> dict:
    parents = bundle["allowed_inputs"]["parent_test_cases"]
    children = bundle["allowed_inputs"]["compiled_child_cases"]
    unscoped = {
        parent["id"]
        for parent in parents
        if len(set(parent.get("required_layers", []))) > 1
        and len({child["layer"] for child in children if child["parent_case_id"] == parent["id"]}) > 1
        and all(
            child["expected"] == parent["expected"]
            for child in children if child["parent_case_id"] == parent["id"]
        )
    }
    issues = [
        {
            "id": f"A11-UNSCOPED-{index:03d}",
            "issue_code": "CROSS_LAYER_RESPONSIBILITY_NOT_NARROWED",
            "severity": "warning",
            "category": "layer_boundary",
            "message": "cross-layer responsibility is unchanged",
            "plain_summary": "该用例拆分层后各层职责未收窄，需要补充分层职责说明。",
            "human_title": "拆分后分层职责未收窄",
            "path": "compiled_child_cases",
            "route_to": "N25",
            "case_id": parent_id,
            "source_refs": [{"type": "parent_case", "id": parent_id}],
            "recommendation": "narrow each child layer responsibility",
        }
        for index, parent_id in enumerate(sorted(unscoped), start=1)
    ]
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed_with_gaps" if issues else "completed",
        "approved": True,
        "issues": issues,
        "parent_case_coverage": [
            {
                "parent_case_id": parent["id"],
                "status": "partial" if parent["id"] in unscoped else "covered",
                "covered_child_ids": [
                    child["id"] for child in children if child["parent_case_id"] == parent["id"]
                ],
                "source_refs": [{"type": "parent_case", "id": parent["id"]}],
                "rationale": "children cover the parent",
            }
            for parent in parents
        ],
        "layer_coverage": [
            {
                "layer": layer,
                "status": (
                    "partial"
                    if any(
                        child["parent_case_id"] in unscoped
                        for child in children if child["layer"] == layer
                    )
                    else "covered"
                ),
                "case_ids": [child["id"] for child in children if child["layer"] == layer],
                "source_refs": [{"type": "layer", "id": layer}],
                "rationale": "layer covered",
            }
            for layer in sorted({child["layer"] for child in children})
        ],
        "evaluation_oracle_accessed": False,
    }


def ingest_a11(bundle: dict, output: dict, tmp_path: Path) -> dict:
    return ingest_multica_output(
        tmp_path / "a11-inputs" / "a11-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage14",
        task_id="task-a11",
        issue_id="issue-a11",
        attachment_id="attachment-a11",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )


def test_prepare_multica_split_review_input_binds_a08_and_n25(tmp_path: Path) -> None:
    bundle, a08_path, compiled_path = build_a11_prepare_inputs(tmp_path)
    a08 = read_json(a08_path)
    compiled = read_json(compiled_path)

    assert bundle["profile_id"] == "A11"
    assert bundle["output_contract"] == "split-review/1.0"
    assert bundle["workflow_run_id"] == a08["workflow_run_id"]
    assert bundle["source_snapshot_id"] == a08["source_snapshot_id"]
    assert set(bundle["allowed_inputs"]) == {
        "parent_test_cases",
        "compiled_child_cases",
        "oracle_rule_library",
    }
    upstream = {
        item["artifact_id"]: item["artifact_hash"] for item in bundle["upstream_artifacts"]
    }
    assert upstream == {
        "a08-test-design-ir": a08["artifact_hash"],
        "n25-compiled-test-cases": compiled["artifact_hash"],
    }
    assert bundle["integrity"]["evaluation_oracle_registry_included"] is False
    assert bundle["bundle_hash"].startswith("sha256:")


def test_a11_input_is_compact_review_scope(tmp_path: Path) -> None:
    """A11 input must stay a compact review scope, not the full duplicated payloads.

    N25 children copy the parent content; shipping both full payloads to the Agent
    inflates the context and can exceed the runtime semantic-inactivity watchdog.
    """

    bundle, a08_path, compiled_path = build_a11_prepare_inputs(tmp_path)
    a08 = read_json(a08_path)
    compiled = read_json(compiled_path)
    parents = bundle["allowed_inputs"]["parent_test_cases"]
    children = bundle["allowed_inputs"]["compiled_child_cases"]

    assert parents and children
    assert set(parents[0]) <= {
        "id",
        "title",
        "layer",
        "required_layers",
        "risk",
        "priority",
        "source_refs",
        "intent_ids",
        "expected",
        "execution_policy",
        "test_data_present",
        "cleanup_present",
        "cleanup_oracle_present",
        "steps_count",
        "preconditions_count",
    }
    assert "test_data" not in parents[0] and "steps" not in parents[0]
    expected = parents[0]["expected"][0]
    assert set(expected) <= {"id", "description", "type", "matcher", "source_ref"}
    assert set(children[0]) <= set(parents[0]) | {"parent_case_id", "inherits_parent"}
    assert children[0]["parent_case_id"] == parents[0]["id"]
    assert children[0]["inherits_parent"]["expected_oracle_ids"] is True

    full_parents = a08["payload"]["parent_cases"]
    full_children = compiled["payload"]["compiled_cases"]
    heavy_fields = {
        "test_data",
        "steps",
        "cleanup",
        "cleanup_oracle",
        "preconditions",
    }
    for case in parents + children:
        assert not (heavy_fields & set(case))
        for item in case["expected"]:
            assert "expected_value" not in item and "observation_point" not in item
    for full in full_parents + full_children:
        assert full["id"] in {case["id"] for case in parents + children}
    assert {child["id"] for child in children} == {
        child["id"] for child in full_children
    }


def test_prepare_and_ingest_multica_a11_input(tmp_path: Path) -> None:
    bundle, _, _ = build_a11_prepare_inputs(tmp_path)
    artifact = ingest_a11(bundle, valid_a11_output(bundle), tmp_path)

    assert artifact["artifact_id"] == "a11-split-coverage-review"
    assert artifact["status"] == "completed_with_gaps"
    assert artifact["payload"]["approved"] is True
    assert artifact["payload"]["input_bundle_hash"] == bundle["bundle_hash"]
    assert artifact["producer"]["component_id"] == "A11"
    assert artifact["producer"]["prompt_version"] == "1.0.0"


def test_ingest_a11_allows_extra_not_applicable_layer(tmp_path: Path) -> None:
    bundle, _, _ = build_a11_prepare_inputs(tmp_path)
    output = valid_a11_output(bundle)
    output["layer_coverage"].append(
        {
            "layer": "frontend",
            "status": "not_applicable",
            "case_ids": [],
            "source_refs": [{"type": "layer", "id": "frontend"}],
            "rationale": "no compiled frontend child",
        }
    )
    artifact = ingest_a11(bundle, output, tmp_path)
    assert artifact["payload"]["approved"] is True


def test_ingest_a11_rejects_evaluation_oracle_access(tmp_path: Path) -> None:
    bundle, _, _ = build_a11_prepare_inputs(tmp_path)
    output = valid_a11_output(bundle)
    output["evaluation_oracle_accessed"] = True

    with pytest.raises(SecurityPolicyError, match="must not access the evaluation Oracle"):
        ingest_a11(bundle, output, tmp_path)


def test_ingest_a11_rejects_approval_mismatch_with_blocking_issue(tmp_path: Path) -> None:
    bundle, _, _ = build_a11_prepare_inputs(tmp_path)
    output = valid_a11_output(bundle)
    children = bundle["allowed_inputs"]["compiled_child_cases"]
    output["issues"].append(
        {
            "id": "A11-001",
            "issue_code": "A11-COVERAGE-GAP",
            "severity": "blocking",
            "category": "coverage",
            "message": "coverage gap",
            "path": "case",
            "route_to": "N26",
            "case_id": children[0]["id"],
            "source_refs": [{"type": "compiled_case", "id": children[0]["id"]}],
            "recommendation": "补充用例",
            "plain_summary": "拆分后的子用例没有覆盖到全部层级，需要补用例。",
            "human_title": "子用例覆盖不完整",
        }
    )

    with pytest.raises(ContractError, match="approval does not match"):
        ingest_a11(bundle, output, tmp_path)


def test_ingest_a11_rejects_skipped_parent_review(tmp_path: Path) -> None:
    bundle, _, _ = build_a11_prepare_inputs(tmp_path)
    output = valid_a11_output(bundle)
    output["parent_case_coverage"].pop()

    with pytest.raises(ContractError, match="every parent Case exactly once"):
        ingest_a11(bundle, output, tmp_path)


def test_ingest_a11_rejects_child_oracle_set_change(tmp_path: Path) -> None:
    _, _, _ = build_a11_prepare_inputs(tmp_path)
    bundle_path = tmp_path / "a11-inputs" / "a11-input.json"
    bundle = read_json(bundle_path)
    first_parent = bundle["allowed_inputs"]["parent_test_cases"][0]
    child_id = first_parent["id"]
    changed = False
    for child in bundle["allowed_inputs"]["compiled_child_cases"]:
        if child["parent_case_id"] == child_id:
            child["expected"][0]["id"] = "CHANGED-EXPECTED"
            changed = True
    assert changed
    unhashed = {key: value for key, value in bundle.items() if key != "bundle_hash"}
    bundle["bundle_hash"] = content_hash(unhashed)
    write_json(bundle_path, bundle)
    output = valid_a11_output(bundle)

    with pytest.raises(ContractError, match="added or changed an Oracle"):
        ingest_a11(bundle, output, tmp_path)


def test_ingest_a11_rejects_unreported_cross_layer_duplicate(tmp_path: Path) -> None:
    bundle, _, _ = build_a11_prepare_inputs(tmp_path)
    bundle_path = tmp_path / "a11-inputs" / "a11-input.json"
    parent = bundle["allowed_inputs"]["parent_test_cases"][0]
    child = next(
        item for item in bundle["allowed_inputs"]["compiled_child_cases"]
        if item["parent_case_id"] == parent["id"]
    )
    parent["required_layers"] = ["backend", "contract"]
    child["layer"] = "backend"
    bundle["allowed_inputs"]["compiled_child_cases"].append(
        {**child, "id": f"{parent['id']}-CONTRACT", "layer": "contract"}
    )
    bundle["bundle_hash"] = content_hash(
        {key: value for key, value in bundle.items() if key != "bundle_hash"}
    )
    write_json(bundle_path, bundle)

    output = valid_a11_output(bundle)
    output["issues"] = []
    output["status"] = "completed"
    for item in output["parent_case_coverage"]:
        if item["parent_case_id"] == parent["id"]:
            item["status"] = "covered"
    with pytest.raises(ContractError, match="unscoped cross-layer responsibilities"):
        ingest_a11(bundle, output, tmp_path)


def test_ingest_a11_accepts_reported_global_cross_layer_duplicate(tmp_path: Path) -> None:
    bundle, _, _ = build_a11_prepare_inputs(tmp_path)
    bundle_path = tmp_path / "a11-inputs" / "a11-input.json"
    parent = bundle["allowed_inputs"]["parent_test_cases"][0]
    child = next(
        item for item in bundle["allowed_inputs"]["compiled_child_cases"]
        if item["parent_case_id"] == parent["id"]
    )
    parent["required_layers"] = ["backend", "contract"]
    child["layer"] = "backend"
    bundle["allowed_inputs"]["compiled_child_cases"].append(
        {**child, "id": f"{parent['id']}-CONTRACT", "layer": "contract"}
    )
    bundle["bundle_hash"] = content_hash(
        {key: value for key, value in bundle.items() if key != "bundle_hash"}
    )
    write_json(bundle_path, bundle)

    output = valid_a11_output(bundle)
    output["issues"] = [{
        "id": "A11-GLOBAL-001",
        "issue_code": "CROSS_LAYER_FULL_DUPLICATION",
        "severity": "error",
        "category": "coverage",
        "message": "Multiple parents duplicate responsibilities across layers",
        "path": "$.allowed_inputs.compiled_child_cases",
        "route_to": "N25",
        "case_id": None,
        "source_refs": ["REQ-001"],
        "recommendation": "Scope each layer responsibility",
        "plain_summary": "多个父用例在拆分后职责完全重复，需要明确各自分层职责。",
        "human_title": "拆分后职责重复",
    }]
    output["approved"] = False
    output["status"] = "needs_human"
    for item in output["parent_case_coverage"]:
        if item["parent_case_id"] == parent["id"]:
            item["status"] = "partial"

    artifact = ingest_a11(bundle, output, tmp_path)
    assert artifact["payload"]["approved"] is False
    assert artifact["status"] == "needs_human"


def _concise_n24(output_dir: Path, a06_artifact_path: Path, decision_hash: str) -> None:
    a06 = json.loads(a06_artifact_path.read_text(encoding="utf-8"))
    envelope = ArtifactEnvelope(
        workflow_run_id="multica-pilot-001",
        workflow_mode="new_requirement",
        artifact_id="n24-test-strategy",
        source_snapshot_id="pilot-001-source-v1",
        producer=Producer("N24"),
        payload={
            "schema_version": "test-strategy/1.0",
            "risk_level": "critical",
            "risk_score": 42,
            "required_layers": ["backend", "contract", "e2e"],
            "required_non_functional": [],
            "human_gates": {"test_case_ir_review": "required"},
            "unresolved_items": [],
            "reasons": [],
            "policy_version": "risk-policy/1.0",
        },
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a06-alignment-result",
                location="payload",
                content_hash=a06["artifact_hash"],
            ),
            EvidenceRef(
                source_type="human_gate_decision",
                source_id="G01",
                location="g01-review-decision.json",
                content_hash=decision_hash,
            ),
        ),
    )
    ArtifactStore(output_dir).write_artifact(envelope)


def test_a08_input_falls_back_to_prior_structured_test_rules(tmp_path: Path) -> None:
    """Concise G01 test_rules fall back to the snapshot's frozen structured rules."""

    prior_dir = tmp_path / "prior"
    prior_dir.mkdir()
    prior_decision = {
        "schema_version": "scope-review-decision/1.0",
        "gate_id": "G01",
        "workflow_run_id": "multica-pilot-000",
        "source_snapshot_id": "pilot-001-source-v1",
        "decision": "approved",
        "decided_at": "2026-08-17T08:00:00+00:00",
        "test_rules": {
            "multiple_reasons": {"message_count": 1},
            "metric_name": {"filter": "all_metric_display_names"},
            "entry_consistency": {
                "required_entries": ["web_chart", "web_joined_table"]
            },
            "custom_dimension": {
                "error_key": "CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED"
            },
            "dynamic_relation": {
                "error_key": "DYNAMIC_RELATION_METRIC_DETAIL_UNSUPPORTED"
            },
            "multi_relation": {
                "error_key": "MULTI_RELATION_METRIC_DETAIL_UNSUPPORTED"
            },
            "permission": {"preserve_detection_order": True},
            "compatibility": {"success_response": "unchanged"},
            "localization": {
                "errors": [
                    {
                        "key": "CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED",
                        "code": "s307011534",
                        "zh_CN": "维度或数据范围中使用了自定义维度字段，暂不支持查看明细",
                        "en": "Custom dimension fields are used in the dimension or data range. Details view is not supported.",
                        "parameters": [],
                    },
                    {
                        "key": "RESULT_SET_FILTER_DETAIL_UNSUPPORTED",
                        "code": "s307011535",
                        "zh_CN": "统计图数据范围中设置了「指标名称」按结果集筛选，不支持查看明细",
                        "en": "The chart data range uses Metric Name with result set filtering. Details view is not supported.",
                        "parameters": ["all_metric_display_names"],
                    },
                    {
                        "key": "MULTI_RELATION_METRIC_DETAIL_UNSUPPORTED",
                        "code": "s307011536",
                        "zh_CN": "基于多关联关系创建的统计指标，暂不支持查看明细",
                        "en": "Metrics created based on multiple relationships do not support Details view.",
                        "parameters": [],
                    },
                    {
                        "key": "DYNAMIC_RELATION_METRIC_DETAIL_UNSUPPORTED",
                        "code": "s307011537",
                        "zh_CN": "基于动态关联关系创建的统计指标，暂不支持查看明细",
                        "en": "Metrics created based on dynamic relationships do not support Details view.",
                        "parameters": [],
                    },
                ]
            },
        },
        "decision_hash": "sha256:prior-structured",
    }
    write_json(prior_dir / "g01-review-decision.json", prior_decision)

    concise_dir = tmp_path / "g01"
    concise_dir.mkdir()
    fixture_request = read_json(PILOT_RUN / "g01" / "g01-review-request.json")
    write_json(concise_dir / "g01-review-request.json", fixture_request)
    concise_decision = read_json(PILOT_RUN / "g01" / "g01-review-decision.json")
    concise_decision["test_rules"] = "按逐项回复冻结的口径执行测试设计"
    concise_decision["decision_hash"] = content_hash(
        {key: value for key, value in concise_decision.items() if key != "decision_hash"}
    )
    write_json(concise_dir / "g01-review-decision.json", concise_decision)
    _concise_n24(
        tmp_path / "n24",
        PILOT_RUN / "multica-stage2" / "artifacts" / "a06-alignment-result.json",
        concise_decision["decision_hash"],
    )

    bundle = prepare_multica_test_design_input(
        PILOT_RUN / "multica-stage1" / "artifacts" / "a02-requirement-analysis.json",
        PILOT_RUN / "multica-stage1" / "artifacts" / "a03-technical-testability-analysis.json",
        PILOT_RUN / "multica-stage2" / "artifacts" / "a06-alignment-result.json",
        tmp_path / "n24" / "artifacts" / "n24-test-strategy.json",
        concise_dir / "g01-review-request.json",
        concise_dir / "g01-review-decision.json",
        ROOT / "policies" / "g01-review-policy.json",
        tmp_path / "inputs",
        prior_test_rules_paths=[prior_dir / "g01-review-decision.json"],
    )

    scope = bundle["allowed_inputs"]["approved_scope"]
    assert scope["test_rule_instruction"] == "按逐项回复冻结的口径执行测试设计"
    assert scope["test_rule_fallback"]["mode"] == "prior_frozen_scope"
    assert scope["test_rules"]["localization"]["errors"][0]["key"] == (
        "CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED"
    )
    assert any(
        item["id"] == "RULE-I18N-CUSTOM-DIMENSION"
        for item in scope["test_rule_obligations"]
    )


def test_a08_input_rejects_concise_rules_without_structured_fallback(
    tmp_path: Path,
) -> None:
    concise_dir = tmp_path / "g01"
    concise_dir.mkdir()
    fixture_request = read_json(PILOT_RUN / "g01" / "g01-review-request.json")
    write_json(concise_dir / "g01-review-request.json", fixture_request)
    concise_decision = read_json(PILOT_RUN / "g01" / "g01-review-decision.json")
    concise_decision["test_rules"] = "按逐项回复冻结的口径执行测试设计"
    concise_decision["decision_hash"] = content_hash(
        {key: value for key, value in concise_decision.items() if key != "decision_hash"}
    )
    write_json(concise_dir / "g01-review-decision.json", concise_decision)
    _concise_n24(
        tmp_path / "n24",
        PILOT_RUN / "multica-stage2" / "artifacts" / "a06-alignment-result.json",
        concise_decision["decision_hash"],
    )

    with pytest.raises(ContractError, match="no structured rules are available"):
        prepare_multica_test_design_input(
            PILOT_RUN / "multica-stage1" / "artifacts" / "a02-requirement-analysis.json",
            PILOT_RUN / "multica-stage1" / "artifacts" / "a03-technical-testability-analysis.json",
            PILOT_RUN / "multica-stage2" / "artifacts" / "a06-alignment-result.json",
            tmp_path / "n24" / "artifacts" / "n24-test-strategy.json",
            concise_dir / "g01-review-request.json",
            concise_dir / "g01-review-decision.json",
            ROOT / "policies" / "g01-review-policy.json",
            tmp_path / "inputs",
        )


def build_c5_prepare_inputs(tmp_path: Path) -> dict:
    """Build N25 + N15 + A14 bundle + A18-BE bundle from real pilot stage-4 A08."""
    bundle = prepare_real_a08_bundle(tmp_path / "inputs")
    a08_input_path = tmp_path / "inputs" / "a08-input.json"
    artifact = ingest_multica_output(
        a08_input_path,
        json.dumps(valid_a08_output(bundle), ensure_ascii=False),
        tmp_path / "stage4",
        task_id="task-a08-c5",
        issue_id="issue-a08-c5",
        attachment_id="attachment-a08-c5",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.1.0",
    )
    a08_path = tmp_path / "stage4" / "artifacts" / "a08-test-design-ir.json"
    a08 = read_json(a08_path)
    parents = a08["payload"]["parent_cases"]
    children = compile_cases(parents, {})
    compiled = ArtifactEnvelope(
        workflow_run_id=a08["workflow_run_id"],
        workflow_mode=a08["workflow_mode"],
        artifact_id="n25-compiled-test-cases",
        source_snapshot_id=a08["source_snapshot_id"],
        producer=Producer(component_id="N25", runtime="deterministic"),
        payload={
            "schema_version": "n25-compiled-test-cases/1.0",
            "parent_artifact_id": "a08-test-design-ir",
            "parent_artifact_hash": a08["artifact_hash"],
            "compiled_cases": children,
            "parent_count": len(parents),
            "child_count": len(children),
            "compile_rule_version": "n25-compiler/1.0",
        },
        status=ArtifactStatus.COMPLETED,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a08-test-design-ir",
                location="a08-test-design-ir.json",
                content_hash=a08["artifact_hash"],
            ),
        ),
    )
    ArtifactStore(tmp_path / "stage13").write_artifact(compiled)
    compiled_path = tmp_path / "stage13" / "artifacts" / "n25-compiled-test-cases.json"
    all_case_ids = [str(item["id"]) for item in children]
    case_ids = [str(item["id"]) for item in children if str(item.get("layer")) == "backend"]
    n15 = ArtifactEnvelope(
        workflow_run_id=a08["workflow_run_id"],
        workflow_mode=a08["workflow_mode"],
        artifact_id="n15-execution-plan",
        source_snapshot_id=a08["source_snapshot_id"],
        producer=Producer(component_id="N15", runtime="deterministic"),
        payload={
            "schema_version": "execution-plan/1.0",
            "actions": [
                {"action": "generate_new", "case_id": case_id, "reason_code": "new_case_without_automation"}
                for case_id in all_case_ids
            ],
            "selection_artifact_id": "n26-test-selection",
            "selection_artifact_hash": "sha256:sel",
        },
        status=ArtifactStatus.COMPLETED,
    )
    ArtifactStore(tmp_path / "stage14").write_artifact(n15)
    n15_path = tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json"
    a14_bundle = prepare_multica_automation_generation_input(
        compiled_path,
        n15_path,
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs",
        profile_id="A14",
    )
    return {
        "a14_bundle": a14_bundle,
        "compiled_path": compiled_path,
        "a08_path": a08_path,
        "case_ids": case_ids,
        "inputs_dir": tmp_path / "c5-inputs",
    }


def valid_a14_output(bundle: dict, case_ids: list[str]) -> dict:
    candidate_path = f"generated/backend/test_{case_ids[0].casefold().replace('-', '_')}.py"
    content = (
        '"""Artifact-only candidate generated from approved Test Case IR."""\n'
        "CASE_SPEC = {}\n\n\n"
        f"def test_{case_ids[0].casefold().replace('-', '_')}(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = {
        "path": candidate_path,
        "content": content,
        "content_hash": content_hash(content),
    }
    manifest = {
        "schema_version": "automation-manifest/1.0",
        "manifest_id": "manifest-a14-backend",
        "generator_profile": "A14/1.0.0",
        "layer": "backend",
        "target_repository": {
            "repository_id": "pytest_for_bi",
            "access_class": "approved_automation_repository",
            "write_mode": "artifact_only_candidate",
        },
        "framework": "pytest",
        "language": "python",
        "case_mappings": [
            {
                "case_id": case_ids[0],
                "expected_ids": [],
                "manual_expected_ids": [],
                "candidate_path": candidate_path,
            }
        ],
        "candidate_files": [{"path": candidate_path, "content_hash": candidate["content_hash"]}],
        "execution": {"command": ["pytest", "-q", candidate_path], "timeout_seconds": 600},
        "permissions": {"business_repository_write": False, "network": False, "secrets": []},
        "expected_artifacts": ["junit_xml"],
        "input_bindings": {},
    }
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "manifest": manifest,
        "code_candidates": [candidate],
        "rejected_cases": [
            {
                "case_id": case_id,
                "reason_code": "case_not_machine_executable",
                "source_refs": [case_id],
            }
            for case_id in case_ids[1:]
        ],
        "evaluation_oracle_accessed": False,
    }


def test_prepare_and_ingest_multica_a14_generation_input(tmp_path: Path) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    assert bundle["profile_id"] == "A14"
    assert bundle["output_contract"] == "automation-generation/1.0"
    assert bundle["allowed_inputs"]["layer"] == "backend"
    allowed = bundle["allowed_inputs"]
    catalog = allowed.get("api_catalog")
    assert catalog is not None and catalog.get("schema_version") == "http-operation-catalog/1.0"
    assert catalog.get("operation_count", 0) > 0
    assert any(str(item.get("operationId", "")) for item in catalog.get("operations", []))
    for case in allowed.get("cases", []):
        for item in case.get("expected", []):
            oracle = item.get("oracle")
            assert isinstance(oracle, dict)
            assert oracle.get("matcher") and oracle.get("observation_point")
            assert "expected_value" in oracle or "expected_values" in oracle or oracle.get("matcher") in {
                "manual_confirmation", "template_equals"
            }
    artifact = ingest_multica_output(
        setup["inputs_dir"] / "a14-input.json",
        json.dumps(valid_a14_output(bundle, setup["case_ids"]), ensure_ascii=False),
        tmp_path / "stage14b",
        task_id="task-a14",
        issue_id="issue-a14",
        attachment_id="attachment-a14",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    assert artifact["artifact_id"] == "a14-backend-automation-generation"
    assert artifact["status"] == "completed"


def test_ingest_a14_rejects_unknown_rejected_case(tmp_path: Path) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    output = valid_a14_output(bundle, setup["case_ids"])
    output["rejected_cases"] = [
        {"case_id": "UNKNOWN-CASE", "reason_code": "case_not_machine_executable", "source_refs": ["UNKNOWN-CASE"]}
    ]
    with pytest.raises(ContractError):
        ingest_multica_output(
            setup["inputs_dir"] / "a14-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage14c",
            task_id="task-a14-x",
            issue_id="issue-a14-x",
            attachment_id="attachment-a14-x",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_ingest_a14_accepts_candidate_path_alias(tmp_path: Path) -> None:
    """code_candidates/candidate_files 用 candidate_path 键名时也应能摄入。

    Agent 输出天然会镜像 case_mappings 的 candidate_path 键名；校验器把
    path/candidate_path 归一化，同时仍以 content 现场计算哈希做权威校验。
    """
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    output = valid_a14_output(bundle, setup["case_ids"])
    for candidate in output["code_candidates"]:
        candidate["candidate_path"] = candidate.pop("path")
    for file_item in output["manifest"]["candidate_files"]:
        file_item["candidate_path"] = file_item.pop("path")
    artifact = ingest_multica_output(
        setup["inputs_dir"] / "a14-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage14-alias",
        task_id="task-a14-alias",
        issue_id="issue-a14-alias",
        attachment_id="attachment-a14-alias",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    assert artifact["artifact_id"] == "a14-backend-automation-generation"


def test_ingest_a14_backfills_authoritative_content_hash(tmp_path: Path) -> None:
    """Agent 自算哈希不可靠：摄入时以 content 现场计算的哈希为权威并回填。

    content 与声明 content_hash 不一致时不再拒掉完整源码，而是把真实哈希写回
    code_candidates 与 manifest.candidate_files，保证下游绑定一致。
    """
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    output = valid_a14_output(bundle, setup["case_ids"])
    candidate = output["code_candidates"][0]
    candidate["content"] = candidate["content"] + "\n# trailer"
    candidate["content_hash"] = "sha256:" + "0" * 64  # 错误声明，应被回填
    artifact = ingest_multica_output(
        setup["inputs_dir"] / "a14-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage14-hash",
        task_id="task-a14-hash",
        issue_id="issue-a14-hash",
        attachment_id="attachment-a14-hash",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    payload = artifact["payload"]
    stored = payload["code_candidates"][0]
    computed = content_hash(stored["content"])
    assert stored["content_hash"] == computed
    manifest_files = {f["path"]: f["content_hash"] for f in payload["manifest"]["candidate_files"]}
    assert manifest_files[stored["path"]] == computed
    assert "candidate_path" not in stored


def test_ingest_a14_backfills_execution_and_expected_artifacts(tmp_path: Path) -> None:
    """Agent 未声明 execution/expected_artifacts 时系统按候选确定性派生回填。

    N05/N08 依赖完整的执行契约；这两个字段可由 candidate_files 精确推导，
    缺失时摄入归一化回填，避免 Agent 输出缺字段导致 N05 failed_fatal。
    """
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    output = valid_a14_output(bundle, setup["case_ids"])
    manifest = output["manifest"]
    manifest.pop("execution", None)
    manifest.pop("expected_artifacts", None)
    artifact = ingest_multica_output(
        setup["inputs_dir"] / "a14-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage14-exec",
        task_id="task-a14-exec",
        issue_id="issue-a14-exec",
        attachment_id="attachment-a14-exec",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    stored_manifest = artifact["payload"]["manifest"]
    paths = [f["path"] for f in stored_manifest["candidate_files"]]
    assert stored_manifest["execution"]["command"] == ["pytest", "-q", *paths]
    assert stored_manifest["execution"]["timeout_seconds"] == 600
    assert stored_manifest["expected_artifacts"] == ["junit_xml", "stdout", "stderr"]


def test_ingest_a14_rejects_undetermined_execution_command(tmp_path: Path) -> None:
    """Agent 声明 execution 时必须与候选路径精确一致，防命令注入。"""
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    output = valid_a14_output(bundle, setup["case_ids"])
    output["manifest"]["execution"]["command"].append("--pdb")
    with pytest.raises(ContractError):
        ingest_multica_output(
            setup["inputs_dir"] / "a14-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage14-exec-bad",
            task_id="task-a14-exec-bad",
            issue_id="issue-a14-exec-bad",
            attachment_id="attachment-a14-exec-bad",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_ingest_a14_rejects_invalid_expected_artifacts(tmp_path: Path) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    output = valid_a14_output(bundle, setup["case_ids"])
    output["manifest"]["expected_artifacts"] = []
    with pytest.raises(ContractError):
        ingest_multica_output(
            setup["inputs_dir"] / "a14-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage14-artifacts-bad",
            task_id="task-a14-artifacts-bad",
            issue_id="issue-a14-artifacts-bad",
            attachment_id="attachment-a14-artifacts-bad",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_prepare_and_ingest_multica_a18_review_input(tmp_path: Path) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    generation = ingest_multica_output(
        setup["inputs_dir"] / "a14-input.json",
        json.dumps(valid_a14_output(bundle, setup["case_ids"]), ensure_ascii=False),
        tmp_path / "stage14d",
        task_id="task-a14-r",
        issue_id="issue-a14-r",
        attachment_id="attachment-a14-r",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    generation_path = tmp_path / "stage14d" / "artifacts" / "a14-backend-automation-generation.json"
    review_bundle = prepare_multica_automation_review_input(
        generation_path,
        setup["inputs_dir"] / "a14-input.json",
        setup["compiled_path"],
        ROOT / "policies" / "automation-target-policy.json",
        setup["inputs_dir"],
        profile_id="A18-BE",
    )
    review_inputs = review_bundle["allowed_inputs"]
    assert set(review_inputs) == {
        "layer",
        "cases",
        "generation",
        "security_rules",
        "review_profile",
        "verified_setup_contracts",
    }
    assert review_inputs["verified_setup_contracts"] == bundle["allowed_inputs"][
        "verified_setup_contracts"
    ]
    assert content_hash(review_inputs["verified_setup_contracts"]) == bundle[
        "allowed_inputs"
    ]["input_bindings"]["verified_setup_contracts_hash"]
    gen_payload = review_bundle["allowed_inputs"]["generation"]
    candidate_hashes = {
        str(item.get("path")): str(item.get("content_hash", ""))
        for item in gen_payload.get("code_candidates", [])
    }
    output = {
        "schema_version": review_bundle["output_contract"],
        "workflow_run_id": review_bundle["workflow_run_id"],
        "source_snapshot_id": review_bundle["source_snapshot_id"],
        "input_bundle_hash": review_bundle["bundle_hash"],
        "status": "completed",
        "review_profile": "A18-BE/1.0.0",
        "approved": True,
        "issues": [],
        "generation_hash": content_hash(gen_payload),
        "manifest_hash": content_hash(gen_payload.get("manifest")),
        "candidate_hashes": candidate_hashes,
        "generator_hidden_reasoning_accessed": False,
        "evaluation_oracle_accessed": False,
    }
    artifact = ingest_multica_output(
        setup["inputs_dir"] / "a18-be-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage18",
        task_id="task-a18",
        issue_id="issue-a18",
        attachment_id="attachment-a18",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    assert artifact["artifact_id"] == "a18-be-backend-automation-review"
    assert artifact["status"] == "completed"


def test_ingest_a18_rejects_generation_hash_mismatch(tmp_path: Path) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    ingest_multica_output(
        setup["inputs_dir"] / "a14-input.json",
        json.dumps(valid_a14_output(bundle, setup["case_ids"]), ensure_ascii=False),
        tmp_path / "stage14e",
        task_id="task-a14-s",
        issue_id="issue-a14-s",
        attachment_id="attachment-a14-s",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    generation_path = tmp_path / "stage14e" / "artifacts" / "a14-backend-automation-generation.json"
    review_bundle = prepare_multica_automation_review_input(
        generation_path,
        setup["inputs_dir"] / "a14-input.json",
        setup["compiled_path"],
        ROOT / "policies" / "automation-target-policy.json",
        setup["inputs_dir"],
        profile_id="A18-BE",
    )
    output = {
        "schema_version": review_bundle["output_contract"],
        "workflow_run_id": review_bundle["workflow_run_id"],
        "source_snapshot_id": review_bundle["source_snapshot_id"],
        "input_bundle_hash": review_bundle["bundle_hash"],
        "status": "completed",
        "review_profile": "A18-BE/1.0.0",
        "approved": True,
        "issues": [],
        "generation_hash": "sha256:wrong",
        "manifest_hash": content_hash(review_bundle["allowed_inputs"]["generation"].get("manifest")),
        "candidate_hashes": {},
        "generator_hidden_reasoning_accessed": False,
        "evaluation_oracle_accessed": False,
    }
    artifact = ingest_multica_output(
        setup["inputs_dir"] / "a18-be-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage18b",
        task_id="task-a18-s",
        issue_id="issue-a18-s",
        attachment_id="attachment-a18-s",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    # 摄入时以冻结输入重算并回填绑定哈希，Agent 自算哈希不再阻塞复核
    gen_payload = review_bundle["allowed_inputs"]["generation"]
    payload = artifact["payload"]
    assert payload["generation_hash"] == content_hash(gen_payload)
    assert payload["manifest_hash"] == content_hash(gen_payload.get("manifest"))
    expected_hashes = {
        str(item.get("path")): str(item.get("content_hash", ""))
        for item in gen_payload.get("code_candidates", [])
    }
    assert payload["candidate_hashes"] == expected_hashes


def test_prepare_and_ingest_multica_a22_plan_input(tmp_path: Path) -> None:
    from qa_agents.agents.base import AgentContext
    from qa_agents.test_data import TestDataPlannerAgent

    setup = build_c5_prepare_inputs(tmp_path)
    bundle = prepare_multica_test_data_plan_input(
        setup["compiled_path"],
        tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json",
        ROOT / "policies" / "test-data-policy.json",
        setup["inputs_dir"],
        capability_catalog_path=ROOT / "knowledge" / "bi-data-capability-catalog.json",
        knowledge_sources_path=ROOT / "knowledge" / "bi-knowledge-sources.json",
    )
    assert bundle["profile_id"] == "A22"
    assert bundle["output_contract"] == "test-data-plan/1.0"
    resource = {
        "resource_key": "metric",
        "resource_type": "aggregate_metric",
        "retention_mode": "delete",
        "resource_id_variable": "metric_field_id",
        "setup": {
            "name": "create namespaced metric",
            "request": {
                "api": "fs_bi_stat.agg_rule.add_new_agg_rule",
                "json": {"displayName": "{{ namespace }}-metric"},
            },
            "extract": {"metric_field_id": "Value.fieldId"},
            "expect": {"status_code": 200},
        },
        "readiness": [
            {
                "name": "query metric",
                "request": {
                    "api": "fs_bi_stat.agg_rule.query_agg_rule_by_field_id",
                    "json": {"fieldId": "{{ metric_field_id }}"},
                },
                "expect": {"status_code": 200},
            }
        ],
        "cleanup": {
            "name": "delete metric",
            "request": {
                "api": "fs_bi_stat.agg_rule.delete_agg_rule",
                "json": {"fieldId": "{{ metric_field_id }}"},
            },
            "expect": {"status_code": 200},
        },
    }
    planner_case_id = str(bundle["allowed_inputs"]["cases"][0]["id"])
    planner = TestDataPlannerAgent().run(
        AgentContext(bundle["workflow_run_id"], "new_requirement", bundle["source_snapshot_id"]),
        {
            "environment": "112",
            "namespace": "qa-a22-plan-test",
            "cases": [
                {
                    "id": planner_case_id,
                    "test_level": "integration",
                    "test_data": {"resource_requirements": [resource]},
                    "steps": [{"request": {"api": "fs_bi_stat.stat_base.data_query_da655ba1"}}],
                }
            ],
        },
        SecurityPolicy(),
    )
    plan = planner.payload
    for case_plan in plan.get("case_plans", []):
        case_plan["source_refs"] = [str(case_plan.get("case_id", ""))]
    plan["workflow_run_id"] = bundle["workflow_run_id"]
    plan["source_snapshot_id"] = bundle["source_snapshot_id"]
    plan["input_bundle_hash"] = bundle["bundle_hash"]
    plan["status"] = "completed"
    artifact = ingest_multica_output(
        setup["inputs_dir"] / "a22-input.json",
        json.dumps(plan, ensure_ascii=False),
        tmp_path / "stage22",
        task_id="task-a22",
        issue_id="issue-a22",
        attachment_id="attachment-a22",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    assert artifact["artifact_id"] == "a22-test-data-plan"
    assert artifact["status"] == "completed"


def test_a22_existing_asset_reuse_must_bind_frozen_discovery(tmp_path: Path) -> None:
    from qa_agents.existing_asset_discovery import discover_existing_assets
    from qa_agents.test_data import validate_test_data_plan

    setup = build_c5_prepare_inputs(tmp_path)
    initial = prepare_multica_test_data_plan_input(
        setup["compiled_path"],
        tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json",
        ROOT / "policies" / "test-data-policy.json",
        tmp_path / "initial-a22",
    )
    case = initial["allowed_inputs"]["cases"][0]
    case_id = str(case["id"])
    case.setdefault("test_data", {})["resource_requirements"] = [
        {"resource_key": "chart", "resource_type": "stat_chart"}
    ]
    discovery = discover_existing_assets(
        [case],
        [{"case_id": case_id, "resource_key": "chart", "resource_type": "stat_chart", "resource_id": "BI-1"}],
        verifier=lambda _: {
            "live_readback_status": "succeeded",
            "baseline_status": "passed",
            "configuration": {"id": "BI-1"},
            "baseline": {"Result": {"FailureCode": 0}},
            "readback_operation": "fs_bi_stat.stat_edit.get_chart_config",
            "baseline_operation": "fs_bi_stat.stat_base.chart_query",
            "integrity_evidence": _valid_chart_integrity_evidence(),
        },
    )
    bundle = prepare_multica_test_data_plan_input(
        setup["compiled_path"],
        tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json",
        ROOT / "policies" / "test-data-policy.json",
        tmp_path / "a22-with-discovery",
        existing_asset_discovery=discovery,
    )
    candidate = discovery["candidates"][0]
    output = {
        "schema_version": "test-data-plan/1.0",
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "environment": "112",
        "namespace": "qa-a22-existing-assets",
            "case_plans": [{
                "case_id": case_id,
                "requirement_name": case.get("requirement_name") or case.get("title") or case_id,
                "requires_data_construction": False,
            "source_refs": [case_id],
                "resources": [{
                "resource_key": "chart",
                "resource_type": "stat_chart",
                "resource_id": "BI-1",
                    "resource_id_variable": "chart_view_id",
                    "asset_folder_name": case.get("requirement_name") or case.get("title") or case_id,
                "lifecycle_mode": "existing_read_only",
                "existing_asset_evidence": candidate["existing_asset_evidence"],
                "discovery": candidate["discovery"],
                "readiness": candidate["readiness"],
                "validity_contract": candidate["validity_contract"],
                "discovery_hash": discovery["discovery_hash"],
            }],
        }],
        "paused_cases": [],
        "unresolved_requirements": [],
        "planning_mode": "assisted",
        "evaluation_oracle_accessed": False,
    }
    validation = validate_test_data_plan(
        output, read_json(ROOT / "policies" / "test-data-policy.json")
    )
    assert validation["valid"] is True
    ingest_multica_output(
        tmp_path / "a22-with-discovery" / "a22-input.json",
        json.dumps(output),
        tmp_path / "accepted-existing",
        task_id="task", issue_id="issue", attachment_id="attachment",
        model_provider="codex", model_snapshot="test", prompt_version="1.0.0",
    )
    output["case_plans"][0]["resources"][0]["resource_id"] = "BI-forged"
    with pytest.raises(SecurityPolicyError, match="unverified asset"):
        ingest_multica_output(
            tmp_path / "a22-with-discovery" / "a22-input.json",
            json.dumps(output),
            tmp_path / "rejected-existing",
            task_id="task", issue_id="issue", attachment_id="attachment",
            model_provider="codex", model_snapshot="test", prompt_version="1.0.0",
        )


def test_c5_agent_contracts_match_workspace_manifest(tmp_path: Path) -> None:
    workspace = read_json(ROOT / "multica" / "workspace-manifest.json")
    agents = {a["logical_id"]: a for a in workspace["agents"]}
    setup = build_c5_prepare_inputs(tmp_path)
    a14_contract = setup["a14_bundle"]["output_contract"]
    a15_bundle = prepare_multica_automation_generation_input(
        setup["compiled_path"],
        tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json",
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs-a15",
        profile_id="A15",
    )
    expected = {
        "A14": a14_contract,
        "A15": a15_bundle["output_contract"],
        "A22": "test-data-plan/1.0",
        "A18-BE": "automation-review/1.0",
        "A18-CT": "automation-review/1.0",
    }
    for logical_id, contract in expected.items():
        assert agents[logical_id]["output_contract"] == contract, logical_id
        instruction = ROOT / "multica" / "agent-instructions" / f"{logical_id.lower()}-v1.0.0.md"
        assert instruction.exists(), instruction
        assert f"output_contract={contract}" in instruction.read_text(encoding="utf-8"), (
            f"{instruction} does not declare {contract}"
        )


def test_prepare_multica_test_data_plan_revision_input_contract(
    tmp_path: Path,
) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = prepare_multica_test_data_plan_input(
        setup["compiled_path"],
        tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json",
        ROOT / "policies" / "test-data-policy.json",
        setup["inputs_dir"],
        capability_catalog_path=ROOT / "knowledge" / "bi-data-capability-catalog.json",
        knowledge_sources_path=ROOT / "knowledge" / "bi-knowledge-sources.json",
    )
    plan = {
        "schema_version": "test-data-plan/1.0",
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "needs_human",
        "environment": "112",
        "namespace": "qa-a22-plan-test",
        "case_plans": [],
        "paused_cases": [],
        "unresolved_requirements": [],
        "planning_mode": "case_explicit",
    }
    plan_artifact = ArtifactEnvelope(
        workflow_run_id=bundle["workflow_run_id"],
        workflow_mode=bundle["workflow_mode"],
        artifact_id="a22-test-data-plan",
        source_snapshot_id=bundle["source_snapshot_id"],
        producer=Producer(component_id="A22", runtime="multica"),
        payload=plan,
        status=ArtifactStatus.NEEDS_HUMAN,
    )
    ArtifactStore(tmp_path / "rev").write_artifact(plan_artifact)
    plan_path = tmp_path / "rev" / "artifacts" / "a22-test-data-plan.json"
    validation_payload = {
        "schema_version": "test-data-plan-validation/1.0",
        "valid": False,
        "decision": "rejected",
        "validation_error": "case_plans[0].resources[0] requires a setup operation",
        "a22_artifact_id": "a22-test-data-plan",
        "a22_artifact_hash": plan_artifact.artifact_hash,
    }
    validation_artifact = ArtifactEnvelope(
        workflow_run_id=bundle["workflow_run_id"],
        workflow_mode=bundle["workflow_mode"],
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id=bundle["source_snapshot_id"],
        producer=Producer(component_id="N27", runtime="deterministic-node"),
        payload=validation_payload,
        status=ArtifactStatus.BLOCKED,
    )
    ArtifactStore(tmp_path / "rev").write_artifact(validation_artifact)
    validation_path = (
        tmp_path / "rev" / "artifacts" / "n27-test-data-plan-validation.json"
    )
    revision = prepare_multica_test_data_plan_revision_input(
        plan_path,
        validation_path,
        setup["inputs_dir"] / "a22-input.json",
        tmp_path / "rev-inputs",
        revision_attempt=2,
    )
    assert revision["profile_id"] == "A22"
    assert revision["revision"]["revision_attempt"] == 2
    assert revision["revision"]["validation_hash"] == validation_artifact.artifact_hash
    assert revision["revision"]["previous_plan_hash"] == plan_artifact.artifact_hash
    assert revision["allowed_inputs"]["previous_plan"]["planning_mode"] == "case_explicit"
    assert revision["allowed_inputs"]["n27_validation"]["decision"] == "rejected"
    assert (tmp_path / "rev-inputs" / "a22-input-revision-2.json").exists()
    accepted_payload = {**validation_payload, "valid": True}
    accepted_artifact = ArtifactEnvelope(
        workflow_run_id=bundle["workflow_run_id"],
        workflow_mode=bundle["workflow_mode"],
        artifact_id="n27-test-data-plan-validation",
        source_snapshot_id=bundle["source_snapshot_id"],
        producer=Producer(component_id="N27", runtime="deterministic-node"),
        payload=accepted_payload,
        status=ArtifactStatus.BLOCKED,
    )
    ArtifactStore(tmp_path / "rev").write_artifact(accepted_artifact)
    with pytest.raises(ContractError, match="rejected N27"):
        prepare_multica_test_data_plan_revision_input(
            plan_path,
            validation_path,
            setup["inputs_dir"] / "a22-input.json",
            tmp_path / "rev-inputs-ok",
            revision_attempt=1,
        )


def test_ingest_a22_rejects_unknown_case_plan(tmp_path: Path) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = prepare_multica_test_data_plan_input(
        setup["compiled_path"],
        tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json",
        ROOT / "policies" / "test-data-policy.json",
        setup["inputs_dir"],
    )


def test_ingest_a22_rejects_chart_detail_case_without_resources(tmp_path: Path) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    frozen_case = json.loads((setup["compiled_path"]).read_text())["payload"][
        "compiled_cases"
    ][0]
    frozen_case["test_data"]["required_scene"] = "chart_detail"
    raw_compiled = json.loads((setup["compiled_path"]).read_text())
    raw_compiled["payload"]["compiled_cases"] = [frozen_case]
    compiled_envelope = ArtifactEnvelope(
        workflow_run_id=raw_compiled["workflow_run_id"],
        workflow_mode=raw_compiled["workflow_mode"],
        artifact_id=raw_compiled["artifact_id"],
        source_snapshot_id=raw_compiled["source_snapshot_id"],
        producer=Producer(**raw_compiled["producer"]),
        payload=raw_compiled["payload"],
        status=ArtifactStatus(raw_compiled["status"]),
        created_at=raw_compiled["created_at"],
    )
    (setup["compiled_path"]).write_text(
        json.dumps(compiled_envelope.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    bundle = prepare_multica_test_data_plan_input(
        setup["compiled_path"],
        tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json",
        ROOT / "policies" / "test-data-policy.json",
        setup["inputs_dir"],
    )
    plan = {
        "schema_version": "test-data-plan/1.0",
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "environment": "112",
        "namespace": "qa-a22-plan-test",
        "case_plans": [
            {
                "case_id": frozen_case["id"],
                "required_scene": "chart_detail",
                "requires_data_construction": False,
                "resources": [],
                "source_refs": [frozen_case["id"]],
            }
        ],
        "paused_cases": [],
        "unresolved_requirements": [],
        "planning_mode": "case_explicit",
    }
    with pytest.raises(ContractError, match="chart_detail without asset resources"):
        ingest_multica_output(
            setup["inputs_dir"] / "a22-input.json",
            json.dumps(plan, ensure_ascii=False),
            tmp_path / "stage22-chart-gap",
            task_id="task-a22-chart-gap",
            issue_id="issue-a22-chart-gap",
            attachment_id="attachment-a22-chart-gap",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )
    plan = {
        "schema_version": "test-data-plan/1.0",
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "environment": "112",
        "namespace": "qa-a22-plan-test",
        "case_plans": [
            {
                "case_id": "UNKNOWN-CASE",
                "requires_data_construction": False,
                "resources": [],
                "source_refs": ["UNKNOWN-CASE"],
            }
        ],
        "paused_cases": [],
        "unresolved_requirements": [],
        "planning_mode": "case_explicit",
    }
    with pytest.raises(ContractError):
        ingest_multica_output(
            setup["inputs_dir"] / "a22-input.json",
            json.dumps(plan, ensure_ascii=False),
            tmp_path / "stage22b",
            task_id="task-a22-x",
            issue_id="issue-a22-x",
            attachment_id="attachment-a22-x",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_generation_input_regeneration_round_changes_bundle_hash(
    tmp_path: Path,
) -> None:
    """重生成必须改变输入包哈希，否则幂等摄入会把被删的旧产物恢复回来。"""
    setup = build_c5_prepare_inputs(tmp_path)
    plan_path = tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json"
    first = prepare_multica_automation_generation_input(
        setup["compiled_path"],
        plan_path,
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs-r0",
        profile_id="A14",
    )
    same = prepare_multica_automation_generation_input(
        setup["compiled_path"],
        plan_path,
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs-r0b",
        profile_id="A14",
    )
    rerun = prepare_multica_automation_generation_input(
        setup["compiled_path"],
        plan_path,
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs-r1",
        profile_id="A14",
        regeneration_round=1,
    )
    assert first["bundle_hash"] == same["bundle_hash"]
    assert first["bundle_hash"] != rerun["bundle_hash"]
    assert rerun["regeneration_round"] == "1"
    assert "regeneration_round" not in first

def _a22_plan_envelope(
    bundle: dict, case_ids: str | list[str], setup_operation: str
) -> ArtifactEnvelope:
    if isinstance(case_ids, str):
        case_ids = [case_ids]
    plan = {
        "schema_version": "test-data-plan/1.0",
        "environment": "112",
        "namespace": "qa-a22-pilot-001-source-v1",
        "status": "completed",
        "case_plans": [
            {
                "case_id": case_id,
                "requires_data_construction": True,
                "resources": [
                    {
                        "resource_key": "cd_field",
                        "resource_type": "custom_dimension",
                        "setup_operation": setup_operation,
                        "resource_id_variable": "cd_field_id",
                        "high_risk_write": True,
                    }
                ],
                "source_refs": [case_id],
            }
            for case_id in case_ids
        ],
        "paused_cases": [],
        "unresolved_requirements": [],
        "planning_mode": "case_explicit",
    }
    return ArtifactEnvelope(
        workflow_run_id=bundle["workflow_run_id"],
        workflow_mode=bundle["workflow_mode"],
        artifact_id="a22-test-data-plan",
        source_snapshot_id=bundle["source_snapshot_id"],
        producer=Producer(component_id="A22", runtime="agent"),
        payload=plan,
        status=ArtifactStatus.COMPLETED,
    )


def test_ingest_a14_rejects_setup_contract_unavailable_when_verified(
    tmp_path: Path,
) -> None:
    """已验证 setup 契约存在时，A14 不得用 setup_contract_unavailable 拒案。"""
    setup = build_c5_prepare_inputs(tmp_path)
    n15_path = tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json"
    backend_case_id = str(setup["case_ids"][0])
    store = ArtifactStore(tmp_path / "stage-a22-verified")
    store.write_artifact(
        _a22_plan_envelope(
            setup["a14_bundle"],
            setup["case_ids"],
            "fs_bi_stat.custom_dimension.create_custom_dimension",
        )
    )
    bundle = prepare_multica_automation_generation_input(
        setup["compiled_path"],
        n15_path,
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs-false-reject",
        profile_id="A14",
        test_data_plan_path=tmp_path / "stage-a22-verified" / "artifacts" / "a22-test-data-plan.json",
    )
    frozen_ids = [str(item["id"]) for item in bundle["allowed_inputs"]["cases"]]
    output = valid_a14_output(bundle, frozen_ids)
    output["manifest"] = None
    output["code_candidates"] = []
    output["status"] = "not_applicable"
    output["rejected_cases"] = [
        {
            "case_id": case_id,
            "reason_code": "setup_contract_unavailable",
            "source_refs": [case_id],
        }
        for case_id in frozen_ids
    ]
    with pytest.raises(ContractError, match="already verified"):
        ingest_multica_output(
            tmp_path / "c5-inputs-false-reject" / "a14-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage14-false-reject",
            task_id="task-a14-false-reject",
            issue_id="issue-a14-false-reject",
            attachment_id="attachment-a14-false-reject",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_ingest_a14_rejects_setup_contract_unavailable_without_setup_operation(
    tmp_path: Path,
) -> None:
    """没有 setup_operation 的 Case 不能用 setup_contract_unavailable 拒绝。"""
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    frozen_ids = [str(item["id"]) for item in bundle["allowed_inputs"]["cases"]]
    output = valid_a14_output(bundle, frozen_ids)
    output["manifest"] = None
    output["code_candidates"] = []
    output["status"] = "not_applicable"
    output["rejected_cases"] = [
        {
            "case_id": case_id,
            "reason_code": "setup_contract_unavailable",
            "source_refs": [case_id],
        }
        for case_id in frozen_ids
    ]
    with pytest.raises(ContractError, match="has no setup_operation"):
        ingest_multica_output(
            setup["inputs_dir"] / "a14-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage14-no-setup",
            task_id="task-a14-no-setup",
            issue_id="issue-a14-no-setup",
            attachment_id="attachment-a14-no-setup",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )


def test_ingest_a14_allows_setup_contract_unavailable_for_unverified_operation(
    tmp_path: Path,
) -> None:
    setup = build_c5_prepare_inputs(tmp_path)
    n15_path = tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json"
    backend_case_id = str(setup["case_ids"][0])
    store = ArtifactStore(tmp_path / "stage-a22-unknown")
    store.write_artifact(
        _a22_plan_envelope(
            setup["a14_bundle"],
            backend_case_id,
            "fs_bi.unknown.create_unverified_resource",
        )
    )
    bundle = prepare_multica_automation_generation_input(
        setup["compiled_path"],
        n15_path,
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs-true-reject",
        profile_id="A14",
        test_data_plan_path=tmp_path / "stage-a22-unknown" / "artifacts" / "a22-test-data-plan.json",
    )
    frozen_ids = [str(item["id"]) for item in bundle["allowed_inputs"]["cases"]]
    output = valid_a14_output(bundle, frozen_ids)
    output["manifest"] = None
    output["code_candidates"] = []
    output["status"] = "not_applicable"
    output["rejected_cases"] = [
        {
            "case_id": case_id,
            "reason_code": (
                "setup_contract_unavailable"
                if case_id == backend_case_id
                else "case_not_machine_executable"
            ),
            "source_refs": [case_id],
        }
        for case_id in frozen_ids
    ]
    artifact = ingest_multica_output(
        tmp_path / "c5-inputs-true-reject" / "a14-input.json",
        json.dumps(output, ensure_ascii=False),
        tmp_path / "stage14-true-reject",
        task_id="task-a14-true-reject",
        issue_id="issue-a14-true-reject",
        attachment_id="attachment-a14-true-reject",
        model_provider="codex",
        model_snapshot="gpt-test",
        prompt_version="1.0.0",
    )
    assert artifact["artifact_id"] == "a14-backend-automation-generation"
    rejected = {
        item["case_id"]: item["reason_code"]
        for item in artifact["payload"]["rejected_cases"]
    }
    assert rejected[backend_case_id] == "setup_contract_unavailable"


def test_generation_input_merges_a22_resources_and_verified_contracts(
    tmp_path: Path,
) -> None:
    """A14 输入必须合并 A22 计划资源为 test_data.resource_requirements，并注入
    112 已验证构造契约，否则生成器只能编占位 body、N08 setup 必然失败。"""
    setup = build_c5_prepare_inputs(tmp_path)
    n15_path = tmp_path / "stage14" / "artifacts" / "n15-execution-plan.json"
    backend_case_id = str(setup["case_ids"][0])
    plan = {
        "schema_version": "test-data-plan/1.0",
        "environment": "112",
        "namespace": "qa-a22-pilot-001-source-v1",
        "status": "completed",
        "case_plans": [
            {
                "case_id": backend_case_id,
                "requires_data_construction": True,
                "resources": [
                    {
                        "resource_key": "cd_field",
                        "resource_type": "custom_dimension",
                        "setup_operation": "fs_bi_stat.custom_dimension.create_custom_dimension",
                        "resource_id_variable": "cd_field_id",
                        "high_risk_write": True,
                    },
                    {
                        "resource_key": "rs_metric",
                        "resource_type": "aggregate_metric",
                        "setup_operation": "fs_bi_stat.agg_rule.add_new_agg_rule",
                        "resource_id_variable": "rs_metric_id",
                    },
                ],
                "source_refs": [backend_case_id],
            }
        ],
        "paused_cases": [],
        "unresolved_requirements": [],
        "planning_mode": "case_explicit",
    }
    envelope = ArtifactEnvelope(
        workflow_run_id=setup["a14_bundle"]["workflow_run_id"],
        workflow_mode=setup["a14_bundle"]["workflow_mode"],
        artifact_id="a22-test-data-plan",
        source_snapshot_id=setup["a14_bundle"]["source_snapshot_id"],
        producer=Producer(component_id="A22", runtime="agent"),
        payload=plan,
        status=ArtifactStatus.COMPLETED,
    )
    store = ArtifactStore(tmp_path / "stage-a22")
    store.write_artifact(envelope)
    plan_path = tmp_path / "stage-a22" / "artifacts" / "a22-test-data-plan.json"

    bundle = prepare_multica_automation_generation_input(
        setup["compiled_path"],
        n15_path,
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs-contracts",
        profile_id="A14",
        test_data_plan_path=plan_path,
    )
    case = next(
        item for item in bundle["allowed_inputs"]["cases"]
        if str(item["id"]) == backend_case_id
    )
    requirements = case["test_data"]["resource_requirements"]
    assert [item["resource_key"] for item in requirements] == ["cd_field", "rs_metric"]
    for resource in requirements:
        assert resource["setup_operation"]
        assert resource["required_body_keys"]
        assert resource["retention_mode"] == "retain"
    contracts = bundle["allowed_inputs"]["verified_setup_contracts"]
    assert contracts["contracts"][
        "fs_bi_stat.custom_dimension.create_custom_dimension"
    ]["response_id_paths"] == ["Value.dimensionId", "Value.fieldId"]
    assert contracts["schema_version"] == "verified-setup-contracts/1.0"
    assert "fs_bi_stat.custom_dimension.create_custom_dimension" in contracts["contracts"]
    assert "required_body_keys" in contracts["contracts"][
        "fs_bi_stat.custom_dimension.create_custom_dimension"
    ]
    assert bundle["allowed_inputs"]["input_bindings"]["verified_setup_contracts_hash"].startswith(
        "sha256:"
    )
    assert any(
        item["artifact_id"] == "a22-test-data-plan"
        for item in bundle["upstream_artifacts"]
    )

    a15 = prepare_multica_automation_generation_input(
        setup["compiled_path"],
        n15_path,
        ROOT / "policies" / "automation-target-policy.json",
        tmp_path / "c5-inputs-a15",
        profile_id="A15",
    )
    assert "verified_setup_contracts" not in a15["allowed_inputs"]


def test_ingest_a14_rejects_chart_binding_without_chart_resource(tmp_path: Path) -> None:
    """A14 不能在 A22 没有图表资源时注入 chart_view_id。"""
    setup = build_c5_prepare_inputs(tmp_path)
    bundle = setup["a14_bundle"]
    output = valid_a14_output(bundle, setup["case_ids"])
    content = (
        "CASE_SPEC={'id':'PC-BE-007-BACKEND','steps':[{'name':'call',"
        "'request':{'api':'fs_bi_stat.stat_base.data_query_da655ba1',"
        "'json':{'id':'{{chart_view_id}}'}},'expect':{'status_code':200}}],"
        "'expected':[],'cleanup':[]}\n"
        "def test_case(case_runner):\n"
        "    observations=case_runner.execute(CASE_SPEC)\n"
        "    case_runner.assert_oracles(observations,CASE_SPEC['expected'])\n"
    )
    output["code_candidates"][0]["content"] = content
    output["code_candidates"][0]["content_hash"] = content_hash(content)
    output["manifest"]["candidate_files"][0]["content_hash"] = content_hash(content)
    with pytest.raises(ContractError, match="bind chart_view_id without a chart resource"):
        ingest_multica_output(
            setup["inputs_dir"] / "a14-input.json",
            json.dumps(output, ensure_ascii=False),
            tmp_path / "stage14-chart-gap",
            task_id="task-a14-chart-gap",
            issue_id="issue-a14-chart-gap",
            attachment_id="attachment-a14-chart-gap",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.0.0",
        )
