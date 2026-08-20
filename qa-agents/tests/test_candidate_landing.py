"""Isolated automation candidate landing tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.agents.automation import BackendAutomationAgent, BackendAutomationReviewAgent
from qa_agents.agents.base import AgentContext
from qa_agents.automation import AutomationPolicy, check_automation_generation
from qa_agents.candidate_landing import land_automation_candidates
from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer, content_hash
from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.security import SecurityPolicy


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "landing-run-001"
SNAPSHOT = "landing-snapshot-001"


def _case() -> dict:
    return {
        "id": "CASE-BE-LAND-001",
        "title": "Landing candidate",
        "layer": "backend",
        "priority": "P1",
        "risk": "medium",
        "automation_candidate": True,
        "execution_policy": {"allowed_modes": ["automated"]},
        "preconditions": [],
        "test_data": {},
        "steps": [
            {
                "name": "call api",
                "request": {"api": "fs_bi_stat.describe_query.detail", "json": {}},
            }
        ],
        "expected": [
            {
                "id": "E1",
                "oracle": {
                    "matcher": "equals",
                    "observation_point": "detail_api.error.code",
                    "expected_value": "s307011534",
                },
            }
        ],
        "cleanup": [],
    }


def _envelope(component: str, artifact_id: str, payload: dict, status: ArtifactStatus) -> dict:
    artifact = ArtifactEnvelope(
        workflow_run_id=RUN_ID,
        workflow_mode="new_requirement",
        artifact_id=artifact_id,
        source_snapshot_id=SNAPSHOT,
        producer=Producer(component),
        payload=payload,
        status=status,
    )
    return artifact.to_dict()


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _inputs(tmp_path: Path) -> dict[str, Path]:
    context = AgentContext(RUN_ID, "new_requirement", SNAPSHOT, ())
    generation = BackendAutomationAgent().run(
        context,
        {
            "cases": [_case()],
            "target": {
                "repository_id": "pytest_for_bi",
                "access_class": "approved_automation_repository",
                "timeout_seconds": 30,
                "network": False,
                "secrets": [],
            },
        },
        SecurityPolicy(),
    )
    review = BackendAutomationReviewAgent().run(
        context, {"cases": [_case()], "generation": generation.payload}, SecurityPolicy()
    )
    policy = AutomationPolicy.from_file(ROOT / "policies/automation-target-policy.json")
    check = check_automation_generation(generation.payload, policy)
    return {
        "generation": _write(
            tmp_path / "generation.json",
            _envelope("A14", "a14-generation", dict(generation.payload), ArtifactStatus.COMPLETED),
        ),
        "review": _write(
            tmp_path / "review.json",
            _envelope("A18-BE", "a18-review", dict(review.payload), ArtifactStatus.COMPLETED),
        ),
        "check": _write(
            tmp_path / "check.json",
            _envelope("N05", "n05-check", check, ArtifactStatus.COMPLETED),
        ),
        "policy": ROOT / "policies/automation-target-policy.json",
    }


def test_land_automation_candidates_writes_isolated_workspace(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    output = tmp_path / "out"
    artifact = land_automation_candidates(
        paths["generation"],
        paths["review"],
        paths["check"],
        paths["policy"],
        output,
    )
    assert artifact["artifact_id"] == "n29-candidate-landing"
    payload = artifact["payload"]
    assert payload["write_mode"] == "isolated_workspace_landing"
    assert payload["mr_disposition"] == "not_requested"
    assert payload["business_repository_write"] is False
    assert payload["file_count"] == 1
    landed = payload["landed_files"][0]
    content = Path(landed["absolute_path"]).read_text(encoding="utf-8")
    assert content_hash(content) == landed["content_hash"]
    assert (output / "automation-workspace").exists()
    assert (output / "artifacts/n29-candidate-landing.json").exists()


def test_land_rejects_unapproved_review(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    review = json.loads(paths["review"].read_text(encoding="utf-8"))
    payload = dict(review["payload"])
    payload["approved"] = False
    paths["review"] = _write(
        paths["review"],
        _envelope("A18-BE", "a18-review", payload, ArtifactStatus.NEEDS_HUMAN),
    )
    with pytest.raises(ContractError, match="approved independent automation review"):
        land_automation_candidates(
            paths["generation"],
            paths["review"],
            paths["check"],
            paths["policy"],
            tmp_path / "out",
        )


def test_land_rejects_external_landing_root(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    with pytest.raises(SecurityPolicyError, match="inside the workflow artifact output"):
        land_automation_candidates(
            paths["generation"],
            paths["review"],
            paths["check"],
            paths["policy"],
            tmp_path / "out",
            landing_root=tmp_path / "outside",
        )
