"""N05 deterministic automation checks and N06 repair routing."""

from __future__ import annotations

import ast
from collections.abc import Mapping
import json
from pathlib import PurePosixPath
from typing import Any

from .contracts import ValidationIssue, content_hash
from .errors import SecurityPolicyError
from .security import SecurityPolicy


class AutomationPolicy:
    def __init__(self, value: Mapping[str, Any]) -> None:
        self.value = dict(value)
        self.targets = {
            str(item["repository_id"]): dict(item) for item in value.get("targets", [])
        }

    @classmethod
    def from_file(cls, path: Any) -> "AutomationPolicy":
        with open(path, encoding="utf-8") as file:
            return cls(json.load(file))


def _safe_candidate_path(path: str, allowed_roots: list[str]) -> bool:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        return False
    return any(pure == PurePosixPath(root) or PurePosixPath(root) in pure.parents for root in allowed_roots)


def check_automation_generation(
    generation: Mapping[str, Any], policy: AutomationPolicy
) -> dict[str, Any]:
    """Validate but never execute generated code."""

    issues: list[ValidationIssue] = []
    manifest = generation.get("manifest")
    if not isinstance(manifest, Mapping):
        issues.append(
            ValidationIssue("manifest_missing", "Automation Manifest is missing", "manifest", "A14")
        )
        return _result(issues)

    required_manifest_fields = {
        "schema_version",
        "manifest_id",
        "generator_profile",
        "target_repository",
        "framework",
        "language",
        "case_mappings",
        "candidate_files",
        "execution",
        "permissions",
        "expected_artifacts",
    }
    for key in sorted(required_manifest_fields - set(manifest)):
        issues.append(
            ValidationIssue(
                "manifest_required_field",
                f"Automation Manifest is missing {key}",
                f"manifest.{key}",
                "A14",
            )
        )
    if manifest.get("schema_version") != "automation-manifest/1.0":
        issues.append(
            ValidationIssue(
                "manifest_schema_version_unsupported",
                str(manifest.get("schema_version")),
                "manifest.schema_version",
                "A14",
            )
        )

    target_info = manifest.get("target_repository", {})
    repository_id = str(target_info.get("repository_id", ""))
    target = policy.targets.get(repository_id)
    if target is None:
        issues.append(
            ValidationIssue(
                "target_repository_not_approved",
                f"Automation target is not approved: {repository_id}",
                "manifest.target_repository.repository_id",
                "SYSTEM",
            )
        )
    elif target_info.get("access_class") != "approved_automation_repository":
        issues.append(
            ValidationIssue(
                "target_access_class_invalid",
                "Target is not an approved automation repository",
                "manifest.target_repository.access_class",
                "SYSTEM",
            )
        )
    if target_info.get("write_mode") != "artifact_only_candidate":
        issues.append(
            ValidationIssue(
                "candidate_write_mode_invalid",
                "Reference generator may only emit artifact-only candidates",
                "manifest.target_repository.write_mode",
                "SYSTEM",
            )
        )
    if manifest.get("permissions", {}).get("business_repository_write") is not False:
        issues.append(
            ValidationIssue(
                "business_repository_write_requested",
                "Business repository writes are forbidden",
                "manifest.permissions.business_repository_write",
                "SYSTEM",
            )
        )

    framework = str(manifest.get("framework", ""))
    language = str(manifest.get("language", ""))
    if target and framework not in target.get("frameworks", []):
        issues.append(ValidationIssue("framework_not_allowed", framework, "manifest.framework", "A14"))
    if target and language not in target.get("languages", []):
        issues.append(ValidationIssue("language_not_allowed", language, "manifest.language", "A14"))

    command = manifest.get("execution", {}).get("command", [])
    if not command or command[0] not in policy.value.get("command_allowlist", []):
        issues.append(
            ValidationIssue("execution_command_not_allowed", str(command), "manifest.execution.command", "SYSTEM")
        )

    declared = {
        str(item.get("path")): str(item.get("content_hash"))
        for item in manifest.get("candidate_files", [])
    }
    candidates = {
        str(item.get("path")): item for item in generation.get("code_candidates", [])
    }
    expected_command = ["pytest", "-q", *declared]
    if command and command != expected_command:
        issues.append(
            ValidationIssue(
                "execution_command_mismatch",
                "Execution command must be derived exactly from declared candidate paths",
                "manifest.execution.command",
                "SYSTEM",
            )
        )
    if set(declared) != set(candidates):
        issues.append(
            ValidationIssue(
                "candidate_manifest_mismatch",
                "Manifest and candidate file sets differ",
                "manifest.candidate_files",
                "A14",
            )
        )

    forbidden_imports = set(policy.value.get("forbidden_python_imports", []))
    forbidden_calls = set(policy.value.get("forbidden_calls", []))
    security = SecurityPolicy()
    for path, candidate in candidates.items():
        if target and not _safe_candidate_path(path, list(target.get("allowed_candidate_roots", []))):
            issues.append(
                ValidationIssue("candidate_path_not_allowed", path, f"code_candidates.{path}", "SYSTEM")
            )
        content = str(candidate.get("content", ""))
        if content_hash(content) != candidate.get("content_hash") or declared.get(path) != candidate.get("content_hash"):
            issues.append(
                ValidationIssue("candidate_hash_mismatch", path, f"code_candidates.{path}.content_hash", "A14")
            )
        try:
            security.assert_no_secret_values(content)
        except SecurityPolicyError as error:
            issues.append(
                ValidationIssue("credential_in_candidate", str(error), f"code_candidates.{path}.content", "SYSTEM")
            )
        try:
            tree = ast.parse(content, filename=path)
        except SyntaxError as error:
            issues.append(
                ValidationIssue("candidate_syntax_error", str(error), f"code_candidates.{path}.content", "A14")
            )
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split(".")[0] for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module.split(".")[0])
                for name in names:
                    if name in forbidden_imports:
                        issues.append(
                            ValidationIssue("forbidden_import", name, f"code_candidates.{path}", "SYSTEM")
                        )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                issues.append(
                    ValidationIssue("forbidden_call", node.func.id, f"code_candidates.{path}", "SYSTEM")
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
                if call_name in forbidden_calls:
                    issues.append(
                        ValidationIssue("forbidden_call", call_name, f"code_candidates.{path}", "SYSTEM")
                    )
                root = node.func.value
                allowed_case_runner_call = (
                    isinstance(root, ast.Name)
                    and root.id == "case_runner"
                    and call_name in {"execute", "assert_oracles"}
                )
                if not allowed_case_runner_call:
                    issues.append(
                        ValidationIssue(
                            "unapproved_runtime_call",
                            call_name,
                            f"code_candidates.{path}",
                            "SYSTEM",
                        )
                    )

    return _result(issues)


def _result(issues: list[ValidationIssue]) -> dict[str, Any]:
    values = [item.to_dict() for item in issues]
    security_codes = {
        "target_repository_not_approved",
        "target_access_class_invalid",
        "candidate_write_mode_invalid",
        "business_repository_write_requested",
        "execution_command_not_allowed",
        "execution_command_mismatch",
        "candidate_path_not_allowed",
        "credential_in_candidate",
        "forbidden_import",
        "forbidden_call",
        "unapproved_runtime_call",
    }
    fatal = any(item.issue_code in security_codes for item in issues)
    return {
        "schema_version": "automation-code-check/1.0",
        "passed": not issues,
        "fatal_security_violation": fatal,
        "issues": values,
        "repair_routes": sorted({item.route_to for item in issues if item.route_to != "SYSTEM"}),
    }
