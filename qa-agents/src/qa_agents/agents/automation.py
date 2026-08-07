"""Phase 2 automation generation and independent review Profiles."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from .base import AgentOutput, BaseAgent
from ..contracts import ArtifactStatus, content_hash


def _python_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return normalized or "unnamed_case"


class BackendAutomationAgent(BaseAgent):
    """Build pytest candidates in an Artifact without writing either Git repository."""

    agent_id = "A14"
    output_name = "backend-automation-generation"
    runtime = "automation-generation-runtime"
    output_contract = "automation-generation/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        cases = list(inputs.get("cases", []))
        target = dict(inputs.get("target", {}))
        candidates: list[dict[str, Any]] = []
        mappings: list[dict[str, Any]] = []
        rejected: list[dict[str, str]] = []

        for case in cases:
            case_id = str(case.get("id", ""))
            allowed_modes = set(case.get("execution_policy", {}).get("allowed_modes", []))
            expected_ids = [str(item.get("id", "")) for item in case.get("expected", [])]
            manual_oracle = any(
                item.get("oracle", {}).get("matcher") == "manual_confirmation"
                for item in case.get("expected", [])
            )
            if (
                case.get("layer") != "backend"
                or not case.get("automation_candidate")
                or "automated" not in allowed_modes
                or not expected_ids
                or manual_oracle
            ):
                rejected.append(
                    {"case_id": case_id, "reason_code": "case_not_machine_executable"}
                )
                continue

            case_spec = {
                "case_id": case_id,
                "title": str(case.get("title", "")),
                "preconditions": list(case.get("preconditions", [])),
                "test_data": dict(case.get("test_data", {})),
                "steps": list(case.get("steps", [])),
                "expected": list(case.get("expected", [])),
                "cleanup": list(case.get("cleanup", [])),
            }
            path = f"generated/backend/test_{_python_name(case_id)}.py"
            literal = repr(case_spec)
            function_name = f"test_{_python_name(case_id)}"
            content = (
                '"""Artifact-only candidate generated from approved Test Case IR."""\n\n'
                f"CASE_SPEC = {literal}\n\n\n"
                f"def {function_name}(case_runner):\n"
                "    observations = case_runner.execute(CASE_SPEC)\n"
                "    case_runner.assert_oracles(observations, CASE_SPEC[\"expected\"])\n"
            )
            candidates.append(
                {"path": path, "content": content, "content_hash": content_hash(content)}
            )
            mappings.append(
                {"case_id": case_id, "expected_ids": expected_ids, "candidate_path": path}
            )

        if not candidates:
            return AgentOutput(
                payload={
                    "schema_version": "automation-generation/1.0",
                    "manifest": None,
                    "code_candidates": [],
                    "rejected_cases": rejected,
                },
                status=ArtifactStatus.NOT_APPLICABLE,
                reason_code="no_machine_executable_backend_case",
            )

        candidate_files = [
            {"path": item["path"], "content_hash": item["content_hash"]}
            for item in candidates
        ]
        paths = [item["path"] for item in candidates]
        manifest = {
            "schema_version": "automation-manifest/1.0",
            "manifest_id": "manifest-a14-backend",
            "generator_profile": "A14/1.0.0",
            "target_repository": {
                "repository_id": str(target.get("repository_id", "")),
                "access_class": str(target.get("access_class", "")),
                "write_mode": "artifact_only_candidate",
            },
            "framework": "pytest",
            "language": "python",
            "case_mappings": mappings,
            "candidate_files": candidate_files,
            "execution": {
                "command": ["pytest", "-q", *paths],
                "timeout_seconds": int(target.get("timeout_seconds", 600)),
            },
            "permissions": {
                "business_repository_write": False,
                "network": bool(target.get("network", False)),
                "secrets": list(target.get("secrets", [])),
            },
            "expected_artifacts": ["junit_xml", "stdout", "stderr"],
        }
        return AgentOutput(
            payload={
                "schema_version": "automation-generation/1.0",
                "manifest": manifest,
                "code_candidates": candidates,
                "rejected_cases": rejected,
            }
        )


class BackendAutomationReviewAgent(BaseAgent):
    """Review generated behavior without sharing the generator call context."""

    agent_id = "A18-BE"
    output_name = "backend-automation-review"
    runtime = "automation-review-runtime"
    output_contract = "automation-review/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        cases = {str(item.get("id")): item for item in inputs.get("cases", [])}
        generation = inputs.get("generation", {})
        manifest = generation.get("manifest") or {}
        candidates = {
            str(item.get("path")): item for item in generation.get("code_candidates", [])
        }
        issues: list[dict[str, Any]] = []

        for mapping in manifest.get("case_mappings", []):
            case_id = str(mapping.get("case_id", ""))
            case = cases.get(case_id)
            path = str(mapping.get("candidate_path", ""))
            candidate = candidates.get(path)
            if case is None:
                issues.append(
                    {"issue_code": "review_case_missing", "case_id": case_id, "route_to": "N25"}
                )
                continue
            if candidate is None:
                issues.append(
                    {"issue_code": "candidate_file_missing", "case_id": case_id, "route_to": "A14"}
                )
                continue
            expected_ids = {str(item.get("id")) for item in case.get("expected", [])}
            mapped_ids = set(mapping.get("expected_ids", []))
            if expected_ids != mapped_ids:
                issues.append(
                    {"issue_code": "oracle_mapping_incomplete", "case_id": case_id, "route_to": "A14"}
                )
            content = str(candidate.get("content", ""))
            if "case_runner.execute(CASE_SPEC)" not in content:
                issues.append(
                    {"issue_code": "execution_binding_missing", "case_id": case_id, "route_to": "A14"}
                )
            if "case_runner.assert_oracles" not in content:
                issues.append(
                    {"issue_code": "oracle_assertion_missing", "case_id": case_id, "route_to": "A14"}
                )
            for expected_id in expected_ids:
                if expected_id not in content:
                    issues.append(
                        {
                            "issue_code": "expected_id_not_bound",
                            "case_id": case_id,
                            "expected_id": expected_id,
                            "route_to": "A14",
                        }
                    )

        mapped_case_ids = {
            str(item.get("case_id")) for item in manifest.get("case_mappings", [])
        }
        missing_cases = set(cases) - mapped_case_ids
        for case_id in sorted(missing_cases):
            issues.append(
                {"issue_code": "automation_case_not_mapped", "case_id": case_id, "route_to": "A14"}
            )

        return AgentOutput(
            payload={
                "schema_version": "automation-review/1.0",
                "review_profile": "A18-BE/1.0.0",
                "approved": not issues,
                "issues": issues,
                "generator_hidden_reasoning_accessed": False,
                "evaluation_oracle_accessed": False,
            },
            status=ArtifactStatus.COMPLETED if not issues else ArtifactStatus.NEEDS_HUMAN,
            reason_code=None if not issues else "automation_review_failed",
        )
