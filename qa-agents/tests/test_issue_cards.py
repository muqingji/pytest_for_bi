import json
from pathlib import Path

import pytest

from qa_agents import cli
from qa_agents.errors import ContractError
from qa_agents.issue_cards import (
    render_multica_issue_result_markdown,
    sync_multica_issue_card,
)


ISSUE_ID = "issue-a06"


def inputs(tmp_path: Path) -> tuple[Path, Path, dict, dict]:
    bundle = {
        "profile_id": "A06",
        "workflow_run_id": "run-1",
        "output_contract": "alignment-result/1.0",
        "bundle_hash": "sha256:bundle",
    }
    artifact = {
        "artifact_id": "a06-alignment-result",
        "artifact_hash": "sha256:artifact",
        "workflow_run_id": "run-1",
        "status": "needs_human",
        "producer": {"component_id": "A06", "runtime": "multica"},
        "payload": {
            "input_bundle_hash": "sha256:bundle",
            "findings": [
                {
                    "id": "FIND-001",
                    "summary": "四个错误码已实现，但平台模板仍缺少联调证据。",
                }
            ],
        },
        "facts": [
            {
                "type": "multica_tool_trace_audit",
                "result": "passed",
                "task_id": "task-a06",
                "issue_id": ISSUE_ID,
                "attachment_id": "attachment-a06",
                "commands": ["cat a06-input.json"],
            }
        ],
    }
    bundle_path = tmp_path / "a06-input.json"
    artifact_path = tmp_path / "a06-artifact.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    return bundle_path, artifact_path, bundle, artifact


def test_render_multica_issue_result_is_readable_and_bound(tmp_path: Path) -> None:
    _, _, bundle, artifact = inputs(tmp_path)
    markdown = render_multica_issue_result_markdown(bundle, artifact)

    assert "A06 运行结果" in markdown
    assert "`findings` (1)" in markdown
    assert "四个错误码已实现" in markdown
    assert "task-a06" in markdown
    assert "sha256:artifact" in markdown
    assert "Result binding hash" in markdown


def test_sync_multica_issue_card_uses_stdin_and_marks_bound_issue_done(
    tmp_path: Path,
) -> None:
    bundle_path, artifact_path, _, _ = inputs(tmp_path)
    captured: dict = {}

    def runner(command: list[str], description: str) -> dict:
        captured["command"] = command
        captured["description"] = description
        return {"id": ISSUE_ID, "status": "done"}

    result = sync_multica_issue_card(
        bundle_path,
        artifact_path,
        ISSUE_ID,
        runner=runner,
    )

    assert captured["command"] == [
        "multica",
        "issue",
        "update",
        ISSUE_ID,
        "--description-stdin",
        "--status",
        "done",
        "--output",
        "json",
    ]
    assert "四个错误码已实现" in captured["description"]
    assert result["artifact_hash"].startswith("sha256:")


def test_sync_multica_issue_card_rejects_another_issue(tmp_path: Path) -> None:
    bundle_path, artifact_path, _, _ = inputs(tmp_path)
    with pytest.raises(ContractError, match="target does not match"):
        sync_multica_issue_card(
            bundle_path, artifact_path, "another-issue", runner=lambda *_: {}
        )


def test_ingest_sync_flag_publishes_only_after_artifact_is_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_path = tmp_path / "bundle.json"
    response_path = tmp_path / "response.json"
    output = tmp_path / "accepted"
    bundle_path.write_text("{}", encoding="utf-8")
    response_path.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    def fake_ingest(*args: object, **kwargs: object) -> dict:
        calls.append("ingest")
        artifact = {"artifact_id": "a06-alignment-result"}
        artifact_dir = output / "artifacts"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "a06-alignment-result.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )
        return artifact

    def fake_sync(bundle: Path, artifact: Path, issue_id: str) -> dict:
        calls.append("sync")
        assert bundle == bundle_path
        assert artifact.exists()
        assert issue_id == ISSUE_ID
        return {"issue_id": issue_id, "status": "done"}

    monkeypatch.setattr(cli, "ingest_multica_output", fake_ingest)
    monkeypatch.setattr(cli, "sync_multica_issue_card", fake_sync)

    result = cli._run(
        [
            "ingest-multica",
            "--bundle",
            str(bundle_path),
            "--response",
            str(response_path),
            "--output",
            str(output),
            "--task-id",
            "task-a06",
            "--issue-id",
            ISSUE_ID,
            "--attachment-id",
            "attachment-a06",
            "--model-provider",
            "codex",
            "--model",
            "gpt-5.6-sol",
            "--prompt-version",
            "1.0.0",
            "--sync-issue-card",
        ]
    )

    assert result == 0
    assert calls == ["ingest", "sync"]
