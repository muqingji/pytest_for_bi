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


def test_ingest_a09_rejects_blocking_issue_without_plain_summary(
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
    with pytest.raises(ContractError, match="plain_summary"):
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
    with pytest.raises(ContractError):
        ingest_multica_output(
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
