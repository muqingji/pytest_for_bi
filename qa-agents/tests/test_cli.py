import json
from pathlib import Path

import pytest

from qa_agents.cli import _load_json_input, _run, main
from qa_agents.errors import ContractError, InputError


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
