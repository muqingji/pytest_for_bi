"""N08 controlled execution, provenance binding and retry routing tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.agents import BackendAutomationAgent, BackendAutomationReviewAgent
from qa_agents.agents.base import AgentContext
from qa_agents.automation import AutomationPolicy, check_automation_generation
from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer
from qa_agents.errors import ContractError, SecurityPolicyError
from qa_agents.execution import ProcessResult, run_n08_automation
from qa_agents.security import SecurityPolicy


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "run-n08"
SNAPSHOT = "snapshot-n08"


def _case(case_id: str = "CASE-001-BACKEND") -> dict:
    return {
        "id": case_id,
        "parent_case_id": "CASE-001",
        "intent_ids": ["INTENT-001"],
        "title": "无权限请求返回 403",
        "layer": "backend",
        "risk": "high",
        "priority": "P1",
        "source_refs": [{"type": "requirement", "id": "REQ-1", "location": "s1"}],
        "preconditions": ["无权限账号"],
        "test_data": {"request": {"method": "GET", "path": "/api/report"}},
        "steps": ["请求接口"],
        "expected": [{
            "id": "EXP-01",
            "description": "返回 403",
            "oracle": {
                "type": "deterministic",
                "observation_point": "response.status",
                "matcher": "equals:403",
                "source_ref": "REQ-1:s1",
            },
        }],
        "cleanup": [],
        "execution_policy": {
            "allowed_modes": ["automated"],
            "required_evidence": ["request_response"],
        },
        "automation_candidate": True,
    }


def _context() -> AgentContext:
    return AgentContext(RUN_ID, "new_requirement", SNAPSHOT, ("cases.json",))


def _write_artifact(path: Path, artifact: ArtifactEnvelope) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact.to_dict(), ensure_ascii=False), encoding="utf-8")
    return path


def _envelope(component: str, artifact_id: str, payload: dict, status: ArtifactStatus) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        workflow_run_id=RUN_ID,
        workflow_mode="new_requirement",
        artifact_id=artifact_id,
        source_snapshot_id=SNAPSHOT,
        producer=Producer(component),
        payload=payload,
        status=status,
    )


def _inputs(
    tmp_path: Path, *, network: bool = False, secrets: list[str] | None = None
) -> dict[str, Path]:
    target = {
        "repository_id": "pytest_for_bi",
        "access_class": "approved_automation_repository",
        "timeout_seconds": 30,
        "network": network,
        "secrets": list(secrets or []),
    }
    generation = BackendAutomationAgent().run(
        _context(), {"cases": [_case()], "target": target}, SecurityPolicy()
    )
    review = BackendAutomationReviewAgent().run(
        _context(), {"cases": [_case()], "generation": generation.payload}, SecurityPolicy()
    )
    policy = AutomationPolicy.from_file(ROOT / "policies/automation-target-policy.json")
    check = check_automation_generation(generation.payload, policy)
    precheck = {
        "schema_version": "n07-environment-precheck/1.0",
        "workflow_run_id": RUN_ID,
        "source_snapshot_id": SNAPSHOT,
        "environment_fingerprint": "sha256:" + "1" * 64,
        "decision": "passed",
        "next_node": "N08",
    }
    return {
        "generation": _write_artifact(
            tmp_path / "generation.json",
            _envelope("A14", "a14-generation", dict(generation.payload), ArtifactStatus.COMPLETED),
        ),
        "review": _write_artifact(
            tmp_path / "review.json",
            _envelope("A18-BE", "a18-review", dict(review.payload), ArtifactStatus.COMPLETED),
        ),
        "check": _write_artifact(
            tmp_path / "check.json",
            _envelope("N05", "n05-check", check, ArtifactStatus.COMPLETED),
        ),
        "precheck": _write_artifact(
            tmp_path / "precheck.json",
            _envelope("N07", "n07-precheck", precheck, ArtifactStatus.COMPLETED),
        ),
    }


class FakeRunner:
    backend = "local_process_reference"
    production_isolated = False

    def __init__(self, result: ProcessResult | None = None) -> None:
        self.result = result or ProcessResult(0, "1 passed", "", False, 12)
        self.commands: list[list[str]] = []

    def run(self, command: list[str], **_: object) -> ProcessResult:
        self.commands.append(command)
        if not self.result.timed_out and self.result.returncode in {0, 1}:
            cwd = Path(str(_["cwd"]))
            junit_arg = next(item for item in command if item.startswith("--junitxml="))
            junit_path = cwd / junit_arg.split("=", 1)[1]
            junit_path.parent.mkdir(parents=True, exist_ok=True)
            failures = 0 if self.result.returncode == 0 else 1
            junit_path.write_text(
                f'<testsuites><testsuite tests="1" failures="{failures}" errors="0" skipped="0"/></testsuites>',
                encoding="utf-8",
            )
        return self.result


def _run(tmp_path: Path, paths: dict[str, Path], runner: FakeRunner | None = None) -> dict:
    return run_n08_automation(
        paths["generation"],
        paths["review"],
        paths["check"],
        paths["precheck"],
        ROOT / "policies/automation-target-policy.json",
        ROOT / "policies/execution-policy.json",
        tmp_path / "out",
        runner=runner,
    )


def test_n08_executes_bound_candidates_without_shell(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    runner = FakeRunner()
    artifact = _run(tmp_path, paths, runner)

    assert artifact["status"] == "completed"
    assert artifact["payload"]["decision"] == "passed"
    assert artifact["payload"]["next_node"] == "N09"
    assert artifact["payload"]["summary"] == {
        "total": 1, "passed": 1, "failed": 0, "timed_out": 0, "infrastructure_error": 0
    }
    assert artifact["payload"]["runner"]["shell"] is False
    assert runner.commands[0][1:3] == ["-m", "pytest"]
    assert (tmp_path / "out/artifacts/n08-automation-execution.json").exists()


def test_n08_business_assertion_failure_is_not_retried(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    runner = FakeRunner(ProcessResult(1, "failed", "assertion", False, 15))
    artifact = _run(tmp_path, paths, runner)

    assert artifact["status"] == "completed_with_gaps"
    assert artifact["payload"]["decision"] == "test_failures"
    assert artifact["payload"]["next_node"] == "N09"


def test_n08_local_process_runner_captures_real_pytest_evidence(tmp_path: Path) -> None:
    artifact = _run(tmp_path, _inputs(tmp_path))
    shard = artifact["payload"]["shards"][0]

    assert artifact["payload"]["decision"] == "test_failures"
    assert shard["return_code"] == 1
    assert shard["junit_xml_present"] is True
    assert shard["junit_xml_hash"].startswith("sha256:")
    assert (tmp_path / "out" / shard["junit_xml_path"]).exists()
    assert "case_runner" in shard["stdout"]


@pytest.mark.parametrize("result", [
    ProcessResult(None, "", "timeout", True, 30000),
    ProcessResult(2, "", "runner error", False, 10),
])
def test_n08_infrastructure_failures_route_to_n10(
    tmp_path: Path, result: ProcessResult
) -> None:
    artifact = _run(tmp_path, _inputs(tmp_path), FakeRunner(result))
    assert artifact["status"] == "failed_retryable"
    assert artifact["payload"]["decision"] == "retryable_infrastructure_failure"
    assert artifact["payload"]["next_node"] == "N10"


def test_n08_rejects_review_not_bound_to_generation(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    review = json.loads(paths["review"].read_text(encoding="utf-8"))
    payload = dict(review["payload"])
    payload["generation_hash"] = "sha256:" + "9" * 64
    paths["review"] = _write_artifact(
        paths["review"], _envelope("A18-BE", "a18-review", payload, ArtifactStatus.COMPLETED)
    )
    with pytest.raises(ContractError, match="not bound"):
        _run(tmp_path, paths, FakeRunner())


def test_n08_rejects_blocked_environment(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    precheck = {
        "schema_version": "n07-environment-precheck/1.0",
        "workflow_run_id": RUN_ID,
        "source_snapshot_id": SNAPSHOT,
        "environment_fingerprint": "sha256:" + "1" * 64,
        "decision": "blocked",
        "next_node": "N16",
    }
    paths["precheck"] = _write_artifact(
        paths["precheck"],
        _envelope("N07", "n07-precheck", precheck, ArtifactStatus.BLOCKED),
    )
    with pytest.raises(ContractError, match="passed N07"):
        _run(tmp_path, paths, FakeRunner())


def test_n08_local_runner_rejects_network_permission(tmp_path: Path) -> None:
    # Default FakeRunner backend cannot satisfy controlled_env_reference when
    # the manifest requests network, even if the policy knows about staging.
    with pytest.raises(SecurityPolicyError, match="Runner backend does not match|denies network|environment class"):
        _run(tmp_path, _inputs(tmp_path, network=True), FakeRunner())


def test_n08_controlled_runner_allows_registered_env_class(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from qa_agents.execution import ControlledEnvironmentRunner, ProcessResult

    monkeypatch.setenv("QA_ENV_TOKEN", "test-token-value-not-for-prod")
    paths = _inputs(tmp_path, network=True, secrets=["QA_ENV_TOKEN"])
    precheck = json.loads(paths["precheck"].read_text(encoding="utf-8"))
    payload = dict(precheck["payload"])
    payload["environment_class"] = "staging_112"
    payload["production_isolation"] = False
    paths["precheck"] = _write_artifact(
        paths["precheck"],
        _envelope("N07", "n07-precheck", payload, ArtifactStatus.COMPLETED),
    )

    class ControlledFake(ControlledEnvironmentRunner):
        def __init__(self) -> None:
            self.commands: list[list[str]] = []

        def run(self, command: list[str], **kwargs: object) -> ProcessResult:
            self.commands.append(command)
            env = kwargs.get("env") or {}
            assert env.get("QA_ENV_TOKEN") == "test-token-value-not-for-prod"
            assert env.get("QA_ENV_CLASS") == "staging_112"
            junit = None
            for item in command:
                if item.startswith("--junitxml="):
                    junit = Path(str(kwargs["cwd"])) / item.split("=", 1)[1]
            assert junit is not None
            junit.parent.mkdir(parents=True, exist_ok=True)
            junit.write_text(
                '<testsuite tests="1" failures="0" errors="0" skipped="0"></testsuite>',
                encoding="utf-8",
            )
            return ProcessResult(0, "1 passed", "", False, 15)

    artifact = _run(tmp_path, paths, ControlledFake())
    runner = artifact["payload"]["runner"]
    assert runner["backend"] == "controlled_env_reference"
    assert runner["network"] is True
    assert runner["secrets"] == ["QA_ENV_TOKEN"]
    assert runner["environment_class"] == "staging_112"
    assert runner["production_isolated"] is False


def test_n08_controlled_runner_rejects_production_class(tmp_path: Path) -> None:
    from qa_agents.execution import ControlledEnvironmentRunner

    paths = _inputs(tmp_path, network=True)
    precheck = json.loads(paths["precheck"].read_text(encoding="utf-8"))
    payload = dict(precheck["payload"])
    payload["environment_class"] = "production"
    payload["production_isolation"] = True
    paths["precheck"] = _write_artifact(
        paths["precheck"],
        _envelope("N07", "n07-precheck", payload, ArtifactStatus.COMPLETED),
    )
    with pytest.raises(SecurityPolicyError, match="production"):
        _run(tmp_path, paths, ControlledEnvironmentRunner())


def test_n08_rejects_tampered_candidate_even_with_stale_upstream_artifacts(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    generation = json.loads(paths["generation"].read_text(encoding="utf-8"))
    payload = dict(generation["payload"])
    payload["code_candidates"] = [dict(payload["code_candidates"][0])]
    payload["code_candidates"][0]["content"] += "\n# post-review drift\n"
    paths["generation"] = _write_artifact(
        paths["generation"],
        _envelope("A14", "a14-generation", payload, ArtifactStatus.COMPLETED),
    )
    with pytest.raises(ContractError, match="not bound"):
        _run(tmp_path, paths, FakeRunner())


@pytest.mark.parametrize(
    ("key", "forged_component"),
    [
        ("generation", "N05"),
        ("review", "A14"),
        ("check", "A18-BE"),
        ("precheck", "A14"),
    ],
)
def test_n08_rejects_forged_upstream_producer(
    tmp_path: Path, key: str, forged_component: str
) -> None:
    paths = _inputs(tmp_path)
    value = json.loads(paths[key].read_text(encoding="utf-8"))
    paths[key] = _write_artifact(
        paths[key],
        _envelope(
            forged_component,
            str(value["artifact_id"]),
            dict(value["payload"]),
            ArtifactStatus(str(value["status"])),
        ),
    )

    with pytest.raises(ContractError, match="producer"):
        _run(tmp_path, paths, FakeRunner())


def test_n08_rejects_upstream_payload_contract_drift(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    value = json.loads(paths["check"].read_text(encoding="utf-8"))
    payload = dict(value["payload"])
    payload["schema_version"] = "automation-code-check/2.0"
    paths["check"] = _write_artifact(
        paths["check"],
        _envelope("N05", str(value["artifact_id"]), payload, ArtifactStatus.COMPLETED),
    )

    with pytest.raises(ContractError, match="payload contract"):
        _run(tmp_path, paths, FakeRunner())
