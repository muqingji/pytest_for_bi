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


def _generator_route(manifest: Mapping[str, Any]) -> str:
    profile = str(manifest.get("generator_profile", ""))
    return profile.split("/")[0] if profile else "A14"


def _declared_candidate_root(policy: "AutomationPolicy", manifest: Mapping[str, Any]) -> str | None:
    agent_id = _generator_route(manifest)
    for config in policy.value.get("layer_profiles", {}).values():
        if config.get("agent_id") == agent_id:
            return config.get("candidate_root")
        for kind_config in config.get("kinds", {}).values():
            if kind_config.get("agent_id") == agent_id:
                return kind_config.get("candidate_root") or config.get("candidate_root")
    return None


_JSON_SPEC_LITERALS = {"true": True, "false": False, "null": None}


def _literal_eval_case_spec(value_node: ast.AST) -> Any:
    """``ast.literal_eval`` with a JSON-literal safety net for evaluation.

    Generation Agents sometimes mirror the input JSON verbatim, which spells
    booleans as ``true``/``false`` instead of Python ``True``/``False``. N05
    rejects such candidates before this helper runs (the gate must match pytest
    runtime semantics, where ``false`` raises NameError), but keeping the swap
    here makes the static evaluation itself never crash on the same shape.
    """

    for sub in ast.walk(value_node):
        if isinstance(sub, ast.Name) and sub.id in _JSON_SPEC_LITERALS:
            sub.__class__ = ast.Constant
            sub.value = _JSON_SPEC_LITERALS[sub.id]
    return ast.literal_eval(value_node)


def _candidate_spec_structure_issues(content: str, path: str) -> list["ValidationIssue"]:
    """Deterministic N05 guard: generated CASE_SPEC must be executable.

    Rejects text-only skeletons (string steps/cleanup, missing oracle values) so
    a non-executable candidate cannot reach N08: the controlled runner would only
    fail at runtime, keeping the quality gate blocked for the wrong reason.

    The gate mirrors pytest runtime semantics: the candidate file is imported by
    pytest as plain Python, so JSON-style ``true``/``false``/``null`` (bare
    names) are rejected even though ``ast.literal_eval`` could parse them after
    a swap.
    """

    issues: list[ValidationIssue] = []
    tree = ast.parse(content, filename=path)
    case_spec: Any = None
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "CASE_SPEC"
        ):
            json_literals = sorted({
                sub.id for sub in ast.walk(node.value)
                if isinstance(sub, ast.Name) and sub.id in _JSON_SPEC_LITERALS
            })
            if json_literals:
                issues.append(
                    ValidationIssue(
                        "case_spec_json_literals_not_python",
                        "CASE_SPEC 必须是合法 Python 字面量：布尔用 True/False、"
                        f"空值用 None；JSON 风格 {json_literals} 在 pytest 导入时"
                        "会抛 NameError",
                        f"code_candidates.{path}.CASE_SPEC",
                        "A14",
                    )
                )
                return issues
            try:
                case_spec = _literal_eval_case_spec(node.value)
            except (ValueError, TypeError):
                issues.append(
                    ValidationIssue(
                        "case_spec_not_literal",
                        "CASE_SPEC must be a static dict literal",
                        f"code_candidates.{path}.CASE_SPEC",
                        "A14",
                    )
                )
                return issues
            break
    if not isinstance(case_spec, dict):
        issues.append(
            ValidationIssue(
                "case_spec_missing",
                "Candidate must declare a CASE_SPEC dict",
                f"code_candidates.{path}.CASE_SPEC",
                "A14",
            )
        )
        return issues
    # cleanup/residue 是尽力而为的拆除动作：runner 对非结构化条目会优雅跳过，
    # 因此只对测试步骤（setup/readiness/steps）做严格结构校验。
    resource_requirements = case_spec.get("test_data", {}).get("resource_requirements", [])
    required_body_keys_by_api: dict[str, set[str]] = {}
    if isinstance(resource_requirements, list):
        for resource in resource_requirements:
            if not isinstance(resource, Mapping):
                continue
            operation = str(resource.get("setup_operation", ""))
            keys = resource.get("required_body_keys")
            if not operation or not isinstance(keys, list) or not keys:
                continue
            required_body_keys_by_api.setdefault(operation, set()).update(
                str(key) for key in keys
            )
    for phase in ("setup", "readiness", "steps"):
        steps = case_spec.get(phase)
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                issues.append(
                    ValidationIssue(
                        "execution_step_not_structured",
                        f"{phase}[{index}] must be a structured step object",
                        f"code_candidates.{path}.{phase}[{index}]",
                        "A14",
                    )
                )
                continue
            request = step.get("request")
            if not isinstance(request, Mapping):
                issues.append(
                    ValidationIssue(
                        "execution_request_missing",
                        f"{phase}[{index}] has no request",
                        f"code_candidates.{path}.{phase}[{index}].request",
                        "A14",
                    )
                )
                continue
            if not (
                request.get("api")
                or (request.get("method") and request.get("path"))
                or request.get("url")
            ):
                issues.append(
                    ValidationIssue(
                        "execution_operation_missing",
                        f"{phase}[{index}] request has no api/method+path/url",
                        f"code_candidates.{path}.{phase}[{index}].request",
                        "A14",
                    )
                )
            api = str(request.get("api", ""))
            required_keys = required_body_keys_by_api.get(api)
            if phase == "setup" and required_keys:
                body = request.get("json")
                if not isinstance(body, Mapping):
                    issues.append(
                        ValidationIssue(
                            "setup_body_missing_contract_fields",
                            f"setup[{index}] body for {api} must be an object"
                            " carrying the verified contract keys",
                            f"code_candidates.{path}.setup[{index}].request.json",
                            "A14",
                        )
                    )
                    continue
                missing = sorted(required_keys - set(body.keys()))
                if missing:
                    issues.append(
                        ValidationIssue(
                            "setup_body_missing_contract_fields",
                            f"setup[{index}] {api} body lacks verified contract"
                            f" keys: {', '.join(missing)}",
                            f"code_candidates.{path}.setup[{index}].request.json",
                            "A14",
                        )
                    )
    expected = case_spec.get("expected")
    if isinstance(expected, list):
        for index, item in enumerate(expected):
            oracle = item.get("oracle") if isinstance(item, Mapping) else None
            if not isinstance(oracle, Mapping):
                oracle = (
                    {key: item.get(key) for key in ("matcher", "observation_point", "expected_value", "expected_values") if key in item}
                    if isinstance(item, Mapping) else {}
                )
            if not isinstance(oracle, Mapping) or not oracle.get("observation_point") or not oracle.get("matcher"):
                issues.append(
                    ValidationIssue(
                        "executable_oracle_missing",
                        f"expected[{index}] must carry an oracle with observation_point/matcher",
                        f"code_candidates.{path}.expected[{index}].oracle",
                        "A14",
                    )
                )
    execute_seen = False
    assert_ok = False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        root = node.func.value
        if not (isinstance(root, ast.Name) and root.id == "case_runner"):
            continue
        if node.func.attr == "execute":
            execute_seen = True
        elif node.func.attr == "assert_oracles":
            first = node.args[0] if node.args else None
            assert_ok = len(node.args) == 2 and not (
                isinstance(first, ast.Name) and first.id == "CASE_SPEC"
            )
    if not execute_seen:
        issues.append(
            ValidationIssue(
                "case_runner_execute_missing",
                "Candidate must call case_runner.execute(CASE_SPEC)",
                f"code_candidates.{path}",
                "A14",
            )
        )
    if not assert_ok:
        issues.append(
            ValidationIssue(
                "assert_oracles_signature_invalid",
                "assert_oracles must be called with (observations, CASE_SPEC[\"expected\"])",
                f"code_candidates.{path}",
                "A14",
            )
        )
    return issues


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
        return _result(issues, generation)

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
                _generator_route(manifest),
            )
        )
    if manifest.get("schema_version") != "automation-manifest/1.0":
        issues.append(
            ValidationIssue(
                "manifest_schema_version_unsupported",
                str(manifest.get("schema_version")),
                "manifest.schema_version",
                _generator_route(manifest),
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
    skill_bound = manifest.get("aggregate_agent_id") == "B01"
    if skill_bound and manifest.get("allowed_tools") != ["case_runner"]:
        issues.append(
            ValidationIssue("unauthorized_tool", str(manifest.get("allowed_tools")),
                            "manifest.allowed_tools", "SYSTEM")
        )
    authorizations = generation.get("skill_router_bindings")
    authorized = {
        str(ref) for value in authorizations.values() if isinstance(value, Mapping)
        for ref in value.get("required_skills", [])
    } if isinstance(authorizations, Mapping) else set()
    if skill_bound and set(manifest.get("authorized_skills", [])) != authorized:
        issues.append(
            ValidationIssue("unauthorized_skill", "Manifest Skills differ from Router authorization",
                            "manifest.authorized_skills", "SYSTEM")
        )
    registry_hashes = {
        str(value.get("registry_hash", "")) for value in authorizations.values()
        if isinstance(value, Mapping)
    } if isinstance(authorizations, Mapping) else set()
    if skill_bound and registry_hashes != {str(manifest.get("skill_registry_hash", ""))}:
        issues.append(
            ValidationIssue("skill_registry_hash_mismatch", "Skill Registry binding differs",
                            "manifest.skill_registry_hash", "SYSTEM")
        )

    framework = str(manifest.get("framework", ""))
    language = str(manifest.get("language", ""))
    if target and framework not in target.get("frameworks", []):
        issues.append(
            ValidationIssue(
                "framework_not_allowed", framework, "manifest.framework", _generator_route(manifest)
            )
        )
    if target and language not in target.get("languages", []):
        issues.append(
            ValidationIssue(
                "language_not_allowed", language, "manifest.language", _generator_route(manifest)
            )
        )

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
        declared_root = _declared_candidate_root(policy, manifest)
        if declared_root and not _safe_candidate_path(path, [declared_root]):
            issues.append(
                ValidationIssue(
                    "candidate_path_not_allowed",
                    f"{path} is outside the {declared_root} candidate root",
                    f"code_candidates.{path}",
                    _generator_route(manifest),
                )
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
        if _generator_route(manifest) in {"A14", "A15"}:
            issues.extend(_candidate_spec_structure_issues(content, path))
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

    return _result(issues, generation)


def _result(
    issues: list[ValidationIssue], generation: Mapping[str, Any]
) -> dict[str, Any]:
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
        "unauthorized_tool",
        "unauthorized_skill",
        "skill_registry_hash_mismatch",
    }
    fatal = any(item.issue_code in security_codes for item in issues)
    manifest = generation.get("manifest")
    candidates = generation.get("code_candidates", [])
    return {
        "schema_version": "automation-code-check/1.0",
        "generation_hash": content_hash(generation),
        "manifest_hash": content_hash(manifest),
        "candidate_hashes": {
            str(candidate.get("path")): str(candidate.get("content_hash", ""))
            for candidate in sorted(
                (item for item in candidates if isinstance(item, Mapping)),
                key=lambda item: str(item.get("path", "")),
            )
        },
        "passed": not issues,
        "fatal_security_violation": fatal,
        "issues": values,
        "repair_routes": sorted({item.route_to for item in issues if item.route_to != "SYSTEM"}),
    }
