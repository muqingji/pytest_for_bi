import json
from pathlib import Path

import pytest

from qa_agents.cli import _load_json_input, _run, main
from qa_agents.errors import ContractError, InputError


def test_prepare_human_correction_cli_forwards_parent_issue(monkeypatch, tmp_path, capsys) -> None:
    captured = {}

    def prepare(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "needs_human",
            "request_hash": "sha256:test",
            "directives": [],
            "policy": {"allowed_actor_ids": ["owner"]},
        }

    monkeypatch.setattr("qa_agents.cli.prepare_human_correction_request", prepare)
    args = []
    for flag in ("test-design-artifact", "oracle-review-artifact", "n04-artifact", "policy", "output"):
        args.extend([f"--{flag}", str(tmp_path / flag)])
    args.extend(["--multica-parent-issue-id", "run-issue-1"])

    assert _run(["prepare-human-correction", *args]) == 0
    assert captured["multica_parent_issue_id"] == "run-issue-1"


def test_cli_returns_structured_domain_error(monkeypatch, capsys) -> None:
    def fail(_argv=None) -> int:
        raise ContractError("G01 approval is missing")

    monkeypatch.setattr("qa_agents.cli._run", fail)

    assert main([]) == 2
    output = json.loads(capsys.readouterr().err)
    assert output == {
        "status": "blocked",
        "reason_code": "contract_validation_failed",
        "retryable": False,
        "message": "G01 approval is missing",
    }


def test_json_input_loader_classifies_missing_and_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="Required g01_decision input is missing"):
        _load_json_input(tmp_path / "missing.json", "g01_decision")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(ContractError, match="is not valid JSON"):
        _load_json_input(invalid, "g01_decision")


def test_assess_automation_knowledge_cli_writes_readiness(tmp_path: Path) -> None:
    packet = {
        "schema_version": "test-knowledge-packet/1.0",
        "knowledge_snapshot_id": "ptkb-1",
        "cases": [{
            "case_id": "CASE-1",
            "source_refs": [{"source_id": "openapi:x", "authority": "frozen_openapi", "contract_authority": True}],
            "execution_chain": {"operations": [{"operation_id": "x", "method": "POST", "path": "/x", "parameter_bindings": []}]},
            "data_recipe": {"resources": [{"id": "r", "depends_on": [], "create_capability": "create", "readiness": {"capability": "get"}, "cleanup": {"capability": "delete"}}]},
            "oracles": [
                {"type": "field", "path": "$.data.id", "expected": "${r.id}", "source_ref": "openapi:x", "polarity": "positive"},
                {"type": "field", "path": "$.data.id", "expected": "not:${other.id}", "source_ref": "openapi:x", "polarity": "negative"},
            ],
        }],
    }
    compiled = {"compiled_cases": [{"id": "CASE-1"}]}
    packet_path = tmp_path / "packet.json"
    compiled_path = tmp_path / "compiled.json"
    output = tmp_path / "readiness.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    compiled_path.write_text(json.dumps(compiled), encoding="utf-8")
    assert _run(["assess-automation-knowledge", "--packet", str(packet_path), "--compiled-cases", str(compiled_path), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["status"] == "ready"


def test_assess_automation_knowledge_cli_can_exclude_frontend_scope(tmp_path: Path) -> None:
    packet = {"schema_version": "test-knowledge-packet/1.0", "knowledge_snapshot_id": "ptkb-1", "cases": []}
    # Empty packets are invalid, so retain one backend Case as a deliberate deferred entry.
    packet["cases"] = [{"case_id": "BE", "source_refs": [{"source_id": "x", "authority": "current_code", "contract_authority": True}]}]
    compiled = {"compiled_cases": [{"id": "BE", "layer": "backend"}, {"id": "FE", "layer": "e2e"}]}
    packet_path, compiled_path, output = tmp_path / "p.json", tmp_path / "c.json", tmp_path / "o.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    compiled_path.write_text(json.dumps(compiled), encoding="utf-8")
    assert _run(["assess-automation-knowledge", "--packet", str(packet_path), "--compiled-cases", str(compiled_path), "--exclude-layer", "e2e", "--output", str(output)]) == 0
    assert {item["case_id"] for item in json.loads(output.read_text())["cases"]} == {"BE"}


def test_human_correction_sync_cli_forwards_manifest_projection_paths(
    monkeypatch, tmp_path: Path
) -> None:
    captured = {}

    def sync(request, n04, policy, output, **kwargs):
        captured.update(
            {
                "request": request,
                "n04": n04,
                "policy": policy,
                "output": output,
                **kwargs,
            }
        )
        return {"status": "completed"}

    monkeypatch.setattr("qa_agents.cli.sync_multica_human_correction", sync)
    paths = {
        name: tmp_path / name
        for name in ("request", "n04", "policy", "output", "run", "workspace")
    }

    assert (
        _run(
            [
                "sync-human-correction-multica",
                "--request",
                str(paths["request"]),
                "--n04-artifact",
                str(paths["n04"]),
                "--policy",
                str(paths["policy"]),
                "--output",
                str(paths["output"]),
                "--run-manifest",
                str(paths["run"]),
                "--workspace-manifest",
                str(paths["workspace"]),
            ]
        )
        == 0
    )
    assert captured["run_manifest_path"] == paths["run"]
    assert captured["workspace_manifest_path"] == paths["workspace"]
