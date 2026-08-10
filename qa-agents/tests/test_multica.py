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
from qa_agents.case_compiler import compile_cases
from qa_agents.multica import (
    fetch_multica_run_messages,
    ingest_multica_output,
    prepare_multica_alignment_input,
    prepare_multica_inputs,
    prepare_multica_oracle_review_input,
    prepare_multica_split_review_input,
    prepare_multica_test_design_correction_input,
    prepare_multica_test_design_input,
)
from qa_agents.storage import ArtifactStore


ROOT = Path(__file__).resolve().parents[1]
PILOT_INPUT = ROOT / "eval" / "workflows" / "pilot-001-detail-drill-message-i18n" / "input"
PILOT_RUN = ROOT / "runs" / "pilot-001"


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


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


def test_ingest_multica_output_rejects_markdown_and_missing_evidence(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    prepare_multica_inputs(PILOT_INPUT, input_dir, workflow_run_id="multica-pilot-001")
    bundle = read_json(input_dir / "a02-input.json")
    output = valid_a02_output(bundle)
    with pytest.raises(ContractError, match="response file"):
        ingest_multica_output(
            input_dir / "a02-input.json",
            f"```json\n{json.dumps(output, ensure_ascii=False)}\n```",
            tmp_path / "run",
            task_id="task-001",
            issue_id="issue-001",
            attachment_id="attachment-001",
            model_provider="codex",
            model_snapshot="gpt-test",
            prompt_version="1.1.0",
        )

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
    return {
        "schema_version": bundle["output_contract"],
        "workflow_run_id": bundle["workflow_run_id"],
        "source_snapshot_id": bundle["source_snapshot_id"],
        "input_bundle_hash": bundle["bundle_hash"],
        "status": "completed",
        "approved": True,
        "issues": [],
        "parent_case_coverage": [
            {
                "parent_case_id": parent["id"],
                "status": "covered",
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
                "status": "covered",
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


def test_prepare_and_ingest_multica_a11_input(tmp_path: Path) -> None:
    bundle, _, _ = build_a11_prepare_inputs(tmp_path)
    artifact = ingest_a11(bundle, valid_a11_output(bundle), tmp_path)

    assert artifact["artifact_id"] == "a11-split-coverage-review"
    assert artifact["status"] == "completed"
    assert artifact["payload"]["approved"] is True
    assert artifact["payload"]["input_bundle_hash"] == bundle["bundle_hash"]
    assert artifact["producer"]["component_id"] == "A11"
    assert artifact["producer"]["prompt_version"] == "1.0.0"


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
    output["issues"] = [
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
        }
    ]

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

    with pytest.raises(ContractError, match="changed the Oracle set"):
        ingest_a11(bundle, output, tmp_path)
