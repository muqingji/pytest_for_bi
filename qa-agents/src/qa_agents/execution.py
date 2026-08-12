"""N08 hash-bound, no-shell automation execution and evidence capture."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
import xml.etree.ElementTree as ET

from .automation import AutomationPolicy, check_automation_generation
from .contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    Producer,
    artifact_hash_from_mapping,
    content_hash,
)
from .errors import ContractError, InputError, SecurityPolicyError
from .security import SecurityPolicy
from .storage import ArtifactStore


@dataclass(frozen=True)
class ProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int


class LocalProcessRunner:
    """Reference runner. Production policy must replace it with an isolated runner."""

    backend = "local_process_reference"
    production_isolated = False
    network_enabled = False
    secrets_enabled = False

    def run(
        self, command: list[str], *, cwd: Path, env: Mapping[str, str], timeout: int
    ) -> ProcessResult:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=dict(env),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
                check=False,
            )
            return ProcessResult(
                completed.returncode,
                completed.stdout,
                completed.stderr,
                False,
                int((time.monotonic() - started) * 1000),
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
            stderr = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
            return ProcessResult(
                None, stdout, stderr, True, int((time.monotonic() - started) * 1000)
            )


class ControlledEnvironmentRunner(LocalProcessRunner):
    """Non-production controlled runner for registered staging/112 environments.

    Still no shell and not production-isolated. Network and host secret env names
    are only available when the versioned execution policy and N07 environment
    class both authorize them.
    """

    backend = "controlled_env_reference"
    production_isolated = False
    network_enabled = True
    secrets_enabled = True


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be a JSON object")
    return value


def _validate_artifact(artifact: Mapping[str, Any], label: str) -> None:
    if artifact.get("schema_version") != "artifact-envelope/1.0":
        raise ContractError(f"{label} is not an Artifact Envelope")
    if artifact_hash_from_mapping(artifact) != artifact.get("artifact_hash"):
        raise ContractError(f"{label} artifact hash is invalid")
    if not isinstance(artifact.get("producer"), Mapping):
        raise ContractError(f"{label} producer is missing")
    if not isinstance(artifact.get("payload"), Mapping):
        raise ContractError(f"{label} payload is not an object")


def _require_source(
    artifact: Mapping[str, Any], label: str, component_id: str, payload_schema: str
) -> None:
    producer = artifact["producer"]
    payload = artifact["payload"]
    if producer.get("component_id") != component_id:
        raise ContractError(f"{label} producer must be {component_id}")
    if payload.get("schema_version") != payload_schema:
        raise ContractError(f"{label} payload contract must be {payload_schema}")


def _binding(payload: Mapping[str, Any], generation_hash: str) -> Mapping[str, Any] | None:
    if payload.get("generation_hash") == generation_hash:
        return payload
    for item in payload.get("input_bindings", []):
        if isinstance(item, Mapping) and item.get("generation_hash") == generation_hash:
            return item
    return None


def _safe_relative(path: str) -> PurePosixPath:
    pure = PurePosixPath(path)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise SecurityPolicyError(f"Candidate path is not confined: {path}")
    return pure


def _log(value: str, limit: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8", "replace")
    truncated = len(encoded) > limit
    text = encoded[:limit].decode("utf-8", "replace")
    redacted = SecurityPolicy().redact_secrets(text)
    return str(redacted), truncated


def run_n08_automation(
    generation_path: Path,
    review_path: Path,
    code_check_path: Path,
    environment_precheck_path: Path,
    automation_policy_path: Path,
    execution_policy_path: Path,
    output_dir: Path,
    *,
    runner: LocalProcessRunner | None = None,
) -> dict[str, Any]:
    generation_artifact = _load(generation_path, "automation generation Artifact")
    review_artifact = _load(review_path, "automation review Artifact")
    code_check_artifact = _load(code_check_path, "N05 code-check Artifact")
    precheck_artifact = _load(environment_precheck_path, "N07 precheck Artifact")
    execution_policy = _load(execution_policy_path, "execution policy")
    framework_root = Path.cwd().parent if Path.cwd().name == "qa-agents" else Path.cwd()
    runner_sources = [
        framework_root / "src/framework/core/runner.py",
        framework_root / "src/framework/core/assertions.py",
        framework_root / "src/framework/pytest_plugin.py",
    ]
    if not all(path.is_file() for path in runner_sources):
        raise InputError("N08 framework runner bundle is incomplete")
    runner_bundle_hash = content_hash(
        {str(path.relative_to(framework_root)): path.read_text(encoding="utf-8")
         for path in runner_sources}
    )
    for label, artifact in (
        ("generation", generation_artifact),
        ("review", review_artifact),
        ("code check", code_check_artifact),
        ("environment precheck", precheck_artifact),
    ):
        _validate_artifact(artifact, label)

    run_ids = {str(item.get("workflow_run_id", "")) for item in (
        generation_artifact, review_artifact, code_check_artifact, precheck_artifact
    )}
    snapshots = {str(item.get("source_snapshot_id", "")) for item in (
        generation_artifact, review_artifact, code_check_artifact, precheck_artifact
    )}
    workflow_modes = {str(item.get("workflow_mode", "")) for item in (
        generation_artifact, review_artifact, code_check_artifact, precheck_artifact
    )}
    if (
        len(run_ids) != 1
        or "" in run_ids
        or len(snapshots) != 1
        or "" in snapshots
        or len(workflow_modes) != 1
        or "" in workflow_modes
    ):
        raise ContractError("N08 upstream workflow/source/mode bindings do not match")

    precheck = precheck_artifact.get("payload", {})
    _require_source(
        precheck_artifact, "environment precheck", "N07", "n07-environment-precheck/1.0"
    )
    if (
        precheck.get("workflow_run_id") != next(iter(run_ids))
        or precheck.get("source_snapshot_id") != next(iter(snapshots))
    ):
        raise ContractError("N07 payload workflow/source bindings do not match its Envelope")
    if (
        precheck_artifact.get("status") not in {"completed", "completed_with_gaps"}
        or precheck.get("decision") not in {"passed", "passed_with_warnings"}
        or precheck.get("next_node") != "N08"
    ):
        raise ContractError("N08 requires a passed N07 precheck routed to N08")

    generation = generation_artifact.get("payload", {})
    manifest = generation.get("manifest")
    if generation_artifact.get("status") != "completed" or not isinstance(manifest, Mapping):
        raise ContractError("N08 requires a completed automation generation")
    generator_id = str(manifest.get("generator_profile", "")).split("/", 1)[0]
    if not generator_id:
        raise ContractError("Automation generation has no generator profile")
    _require_source(
        generation_artifact, "automation generation", generator_id, "automation-generation/1.0"
    )
    generation_hash = content_hash(generation)
    manifest_hash = content_hash(manifest)
    candidate_hashes = {
        str(item.get("path")): str(item.get("content_hash", ""))
        for item in generation.get("code_candidates", []) if isinstance(item, Mapping)
    }

    review = review_artifact.get("payload", {})
    review_id = str(review.get("review_profile", "")).split("/", 1)[0]
    if not review_id.startswith("A18-"):
        raise ContractError("Automation review has no independent A18 profile")
    _require_source(review_artifact, "automation review", review_id, "automation-review/1.0")
    review_binding = _binding(review, generation_hash)
    if review_artifact.get("status") != "completed" or review.get("approved") is not True:
        raise ContractError("N08 requires an approved independent automation review")
    if not review_binding or review_binding.get("manifest_hash") != manifest_hash:
        raise ContractError("Automation review is not bound to this generation manifest")
    if dict(review_binding.get("candidate_hashes", {})) != candidate_hashes:
        raise ContractError("Automation review candidate bindings do not match generation")

    code_check = code_check_artifact.get("payload", {})
    _require_source(code_check_artifact, "code check", "N05", "automation-code-check/1.0")
    check_binding = _binding(code_check, generation_hash)
    if code_check_artifact.get("status") != "completed" or code_check.get("passed") is not True:
        raise ContractError("N08 requires a passed N05 code check")
    if not check_binding or check_binding.get("manifest_hash") != manifest_hash:
        raise ContractError("N05 is not bound to this generation manifest")
    if dict(check_binding.get("candidate_hashes", {})) != candidate_hashes:
        raise ContractError("N05 candidate bindings do not match generation")

    automation_policy = AutomationPolicy.from_file(automation_policy_path)
    recheck = check_automation_generation(generation, automation_policy)
    if not recheck["passed"]:
        raise SecurityPolicyError("Generation no longer passes the current automation policy")

    if execution_policy.get("schema_version") != "execution-policy/1.0":
        raise ContractError("Unsupported execution policy schema_version")
    permissions = manifest.get("permissions", {})
    if not isinstance(permissions, Mapping):
        raise ContractError("Manifest permissions must be an object")
    if permissions.get("business_repository_write") is not False:
        raise SecurityPolicyError("N08 cannot write a business repository")
    command = list(manifest.get("execution", {}).get("command", []))
    if not command or command[0] not in execution_policy.get("allowed_executables", []):
        raise SecurityPolicyError("Manifest executable is not allowed by execution policy")

    controlled = execution_policy.get("controlled_environment") or {}
    if controlled and not isinstance(controlled, Mapping):
        raise ContractError("execution policy controlled_environment must be an object")
    needs_network = bool(permissions.get("network"))
    raw_secrets = permissions.get("secrets", [])
    if raw_secrets is None:
        raw_secrets = []
    if isinstance(raw_secrets, str):
        raise SecurityPolicyError(
            "Manifest permissions.secrets must be a list of environment names, not a string"
        )
    if not isinstance(raw_secrets, list):
        raise ContractError("Manifest permissions.secrets must be a list")
    requested_secrets = [str(item) for item in raw_secrets if str(item)]
    needs_secrets = bool(requested_secrets)
    env_class = str(precheck.get("environment_class", "unspecified"))
    production_isolation = bool(precheck.get("production_isolation", False))

    if needs_network or needs_secrets:
        if not controlled.get("enabled"):
            raise SecurityPolicyError(
                "Local N08 reference runner denies network and secrets"
            )
        if env_class not in set(controlled.get("allowed_environment_classes", [])):
            raise SecurityPolicyError(
                f"Controlled runner does not allow environment class {env_class!r}"
            )
        if production_isolation or env_class == "production":
            raise SecurityPolicyError(
                "Controlled runner cannot execute production or production-isolated targets"
            )
        if needs_network and not controlled.get("allow_network", False):
            raise SecurityPolicyError("Execution policy denies network for controlled runner")
        if needs_secrets and not controlled.get("allow_secrets", False):
            raise SecurityPolicyError("Execution policy denies secrets for controlled runner")
        allowed_secret_names = {
            str(item) for item in controlled.get("allowed_secret_env_names", [])
        }
        unknown_secrets = sorted(set(requested_secrets) - allowed_secret_names)
        if unknown_secrets:
            raise SecurityPolicyError(
                f"Secret env names are not allowlisted: {', '.join(unknown_secrets)}"
            )
        expected_backend = str(
            controlled.get("runner_backend", "controlled_env_reference")
        )
        active_runner = runner or ControlledEnvironmentRunner()
    else:
        if permissions.get("network") or permissions.get("secrets"):
            raise SecurityPolicyError(
                "Local N08 reference runner denies network and secrets"
            )
        expected_backend = str(execution_policy.get("runner_backend", "local_process_reference"))
        active_runner = runner or LocalProcessRunner()

    if active_runner.backend != expected_backend:
        raise SecurityPolicyError("Runner backend does not match execution policy")
    if execution_policy.get("require_production_isolation") and not active_runner.production_isolated:
        raise SecurityPolicyError("Execution policy requires a production-isolated runner")
    if command[0] == "pytest":
        executable_prefix = [sys.executable, "-m", "pytest"]
    else:
        executable = shutil.which(command[0])
        if not executable:
            raise InputError(f"Approved executable is unavailable: {command[0]}")
        executable_prefix = [executable]
    max_timeout = int(execution_policy.get("max_timeout_seconds", 900))
    timeout = min(int(manifest.get("execution", {}).get("timeout_seconds", max_timeout)), max_timeout)
    max_log_bytes = int(execution_policy.get("max_log_bytes", 1_048_576))
    max_junit_bytes = int(execution_policy.get("max_junit_bytes", 10_485_760))
    max_workers = max(1, int(execution_policy.get("max_parallel_shards", 1)))

    candidates = {
        str(item["path"]): item for item in generation.get("code_candidates", [])
    }
    declared_paths = command[2:]
    if not declared_paths:
        raise ContractError("Manifest command has no candidate paths")
    if set(declared_paths) != set(candidates):
        raise ContractError("Manifest command and candidate set do not match")
    mappings_by_path: dict[str, list[str]] = {}
    for item in manifest.get("case_mappings", []):
        mappings_by_path.setdefault(str(item.get("candidate_path", "")), []).append(
            str(item.get("case_id", ""))
        )
    manifest_bindings = manifest.get("input_bindings", {})
    if manifest_bindings and not isinstance(manifest_bindings, Mapping):
        raise ContractError("Manifest input_bindings must be an object")
    lifecycle_evidence_required = bool(
        isinstance(manifest_bindings, Mapping)
        and manifest_bindings.get("test_data_resource_plan_hash")
    )

    store = ArtifactStore(output_dir)
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory(prefix="qa-n08-") as temporary:
        workdir = Path(temporary)
        for path, candidate in candidates.items():
            pure = _safe_relative(path)
            target = workdir.joinpath(*pure.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            content = str(candidate.get("content", ""))
            if content_hash(content) != candidate.get("content_hash"):
                raise ContractError(f"Candidate content hash drifted before execution: {path}")
            target.write_text(content, encoding="utf-8")
        evidence_dir = workdir / ".qa-evidence"
        evidence_dir.mkdir()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "QA_ENV_CLASS": env_class,
        }
        if needs_network or needs_secrets:
            # Controlled path: allow optional host passthrough names and secret env names.
            for name in controlled.get("allowed_env_passthrough", []):
                key = str(name)
                if key and key in os.environ and key not in env:
                    env[key] = os.environ[key]
            for name in requested_secrets:
                if name in os.environ and os.environ[name]:
                    env[name] = os.environ[name]
                    continue
                providers = controlled.get("secret_providers", {})
                provider = providers.get(env_class, {}) if isinstance(providers, Mapping) else {}
                provider_names = {
                    str(item) for item in provider.get("secret_names", [])
                } if isinstance(provider, Mapping) else set()
                provider_path = Path.cwd() / str(provider.get("path", ""))
                repository_root = Path.cwd().parent.resolve()
                if (
                    provider.get("type") != "environment_local_config"
                    or name not in provider_names
                    or not provider_path.is_file()
                    or repository_root not in provider_path.resolve().parents
                ):
                    raise InputError(
                        f"Required secret is unavailable from an approved provider: {name}"
                    )
            pythonpath_entries = [
                str((Path.cwd() / item).resolve())
                for item in controlled.get("framework_pythonpath_entries", [])
            ]
            existing = env.get("PYTHONPATH", "")
            merged = os.pathsep.join(
                [item for item in pythonpath_entries + ([existing] if existing else []) if item]
            )
            if merged:
                env["PYTHONPATH"] = merged
            # Network-capable runs need plugins (framework fixtures); keep offline
            # reference runs plugin-free for hermetic evidence.
            env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
        collect_coverage = bool(
            (controlled.get("collect_coverage") if (needs_network or needs_secrets) else False)
            or execution_policy.get("collect_coverage")
        )
        coverage_available = False
        if collect_coverage:
            try:
                import coverage as _coverage  # noqa: F401
            except ImportError:
                coverage_available = False
            else:
                coverage_available = True

        def execute(index_path: tuple[int, str]) -> dict[str, Any]:
            index, path = index_path
            shard_lifecycle_dir = evidence_dir / f"lifecycle-{index:03d}"
            shard_lifecycle_dir.mkdir()
            shard_env = {**env, "QA_LIFECYCLE_EVIDENCE_DIR": str(shard_lifecycle_dir)}
            junit = evidence_dir / f"shard-{index:03d}.xml"
            coverage_json = evidence_dir / f"coverage-{index:03d}.json"
            pytest_policy_args: list[str] = []
            if needs_network or needs_secrets:
                for plugin in controlled.get("pytest_plugins", []):
                    pytest_policy_args.extend(["-p", str(plugin)])
                by_environment = controlled.get("pytest_arguments_by_environment_class", {})
                if isinstance(by_environment, Mapping):
                    pytest_policy_args.extend(
                        str(item) for item in by_environment.get(env_class, [])
                    )
            effective = [
                *executable_prefix, *pytest_policy_args, "-q", path,
                f"--junitxml={junit.relative_to(workdir)}",
            ]
            if collect_coverage and coverage_available:
                effective.extend(
                    [
                        "--cov",
                        "--cov-branch",
                        "--cov-report",
                        f"json:{coverage_json.relative_to(workdir)}",
                    ]
                )
            result = active_runner.run(effective, cwd=workdir, env=shard_env, timeout=timeout)
            stdout, stdout_truncated = _log(result.stdout, max_log_bytes)
            stderr, stderr_truncated = _log(result.stderr, max_log_bytes)
            junit_content = ""
            junit_valid = False
            junit_summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
            if junit.exists() and junit.stat().st_size <= max_junit_bytes:
                junit_content = junit.read_text(encoding="utf-8")
                try:
                    root = ET.fromstring(junit_content)
                except ET.ParseError:
                    pass
                else:
                    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
                    for suite in suites:
                        for key in junit_summary:
                            junit_summary[key] += int(suite.attrib.get(key, 0))
                    junit_valid = bool(suites)
            if result.timed_out:
                outcome = "timed_out"
            elif not junit_valid:
                outcome = "infrastructure_error"
            elif junit_summary["tests"] < len(mappings_by_path.get(path, [])):
                outcome = "infrastructure_error"
            elif junit_summary["tests"] == junit_summary["skipped"]:
                outcome = "infrastructure_error"
            elif result.returncode == 0:
                outcome = "passed"
            elif result.returncode == 1:
                outcome = "failed"
            else:
                outcome = "infrastructure_error"
            coverage_summary = None
            coverage_content = ""
            if coverage_json.exists() and coverage_json.stat().st_size <= max_junit_bytes:
                coverage_content = coverage_json.read_text(encoding="utf-8")
                try:
                    coverage_obj = json.loads(coverage_content)
                except json.JSONDecodeError:
                    coverage_obj = None
                if isinstance(coverage_obj, dict):
                    totals = coverage_obj.get("totals")
                    if isinstance(totals, Mapping):
                        coverage_summary = {
                            "statement_coverage_percent": totals.get("percent_covered"),
                            "covered_lines": totals.get("covered_lines"),
                            "num_statements": totals.get("num_statements"),
                            "missing_lines": totals.get("missing_lines"),
                        }
            lifecycle_evidence = [
                json.loads(item.read_text(encoding="utf-8"))
                for item in sorted(shard_lifecycle_dir.glob("*.json"))
                if any(
                    case_id == item.stem for case_id in mappings_by_path.get(path, [])
                )
            ]
            if lifecycle_evidence_required and len(lifecycle_evidence) < len(
                mappings_by_path.get(path, [])
            ):
                outcome = "infrastructure_error"
            return {
                "shard_id": f"N08-S{index:03d}",
                "candidate_path": path,
                "case_ids": sorted(mappings_by_path.get(path, [])),
                "manifest_command_hash": content_hash(command),
                "effective_command": [command[0], "-q", path, "--junitxml=<evidence>"],
                "return_code": result.returncode,
                "timed_out": result.timed_out,
                "duration_ms": result.duration_ms,
                "outcome": outcome,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "junit_xml_present": junit.exists(),
                "junit_xml_valid": junit_valid,
                "junit_xml_hash": content_hash(junit_content) if junit_valid else None,
                "junit_summary": junit_summary,
                "collection_complete": (
                    junit_summary["tests"] >= len(mappings_by_path.get(path, []))
                    and junit_summary["tests"] > junit_summary["skipped"]
                ),
                "lifecycle_evidence_required": lifecycle_evidence_required,
                "lifecycle_evidence_present": len(lifecycle_evidence) >= len(
                    mappings_by_path.get(path, [])
                ),
                "coverage_summary": coverage_summary,
                "_junit_xml_content": junit_content,
                "_coverage_json_content": coverage_content if coverage_summary else "",
                "_lifecycle_evidence": lifecycle_evidence,
            }

        with ThreadPoolExecutor(max_workers=min(max_workers, len(declared_paths))) as pool:
            shards = list(pool.map(execute, enumerate(declared_paths, start=1)))
        for shard in shards:
            junit_content = shard.pop("_junit_xml_content")
            coverage_content = shard.pop("_coverage_json_content", "")
            lifecycle_evidence = shard.pop("_lifecycle_evidence", [])
            if shard["junit_xml_valid"]:
                evidence_path = f"evidence/{shard['shard_id']}/junit.xml"
                store.write_text(evidence_path, junit_content)
                shard["junit_xml_path"] = evidence_path
            else:
                shard["junit_xml_path"] = None
            if coverage_content:
                coverage_path = f"evidence/{shard['shard_id']}/coverage.json"
                store.write_text(coverage_path, coverage_content)
                shard["coverage_json_path"] = coverage_path
            else:
                shard["coverage_json_path"] = None
            if lifecycle_evidence:
                lifecycle_path = f"evidence/{shard['shard_id']}/lifecycle.json"
                store.write_json(lifecycle_path, {
                    "schema_version": "shard-lifecycle-evidence/1.0",
                    "cases": lifecycle_evidence,
                })
                shard["lifecycle_evidence_path"] = lifecycle_path
                shard["lifecycle_evidence_hash"] = content_hash(lifecycle_evidence)
            else:
                shard["lifecycle_evidence_path"] = None
                shard["lifecycle_evidence_hash"] = None

    counts = {name: sum(item["outcome"] == name for item in shards) for name in (
        "passed", "failed", "timed_out", "infrastructure_error"
    )}
    if counts["timed_out"] or counts["infrastructure_error"]:
        decision, next_node = "retryable_infrastructure_failure", "N10"
        status, reason = ArtifactStatus.FAILED_RETRYABLE, "automation_infrastructure_failure"
    elif counts["failed"]:
        decision, next_node = "test_failures", "N09"
        status, reason = ArtifactStatus.COMPLETED_WITH_GAPS, "automation_test_failures"
    else:
        decision, next_node = "passed", "N09"
        status, reason = ArtifactStatus.COMPLETED, None
    payload = {
        "schema_version": "n08-automation-execution/1.0",
        "workflow_run_id": next(iter(run_ids)),
        "source_snapshot_id": next(iter(snapshots)),
        "environment_fingerprint": precheck["environment_fingerprint"],
        "input_bindings": {
            "environment_precheck_hash": precheck_artifact["artifact_hash"],
            "generation_hash": generation_artifact["artifact_hash"],
            "review_hash": review_artifact["artifact_hash"],
            "code_check_hash": code_check_artifact["artifact_hash"],
            "manifest_hash": manifest_hash,
            "runner_bundle_hash": runner_bundle_hash,
        },
        "execution_policy_hash": content_hash(execution_policy),
        "automation_policy_hash": content_hash(automation_policy.value),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runner": {
            "backend": active_runner.backend,
            "production_isolated": active_runner.production_isolated,
            "shell": False,
            "network": bool(needs_network),
            "secrets": list(requested_secrets),
            "environment_class": env_class,
        },
        "shards": shards,
        "summary": {"total": len(shards), **counts},
        "decision": decision,
        "next_node": next_node,
    }
    artifact = ArtifactEnvelope(
        workflow_run_id=next(iter(run_ids)),
        workflow_mode=next(iter(workflow_modes)),
        artifact_id="n08-automation-execution",
        source_snapshot_id=next(iter(snapshots)),
        producer=Producer("N08", profile_version="1.0.0"),
        payload=payload,
        status=status,
        reason_code=reason,
    )
    store.write_artifact(artifact)
    return artifact.to_dict()
