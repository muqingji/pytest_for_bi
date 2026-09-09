"""N05 deterministic automation checks and N06 repair routing."""

from __future__ import annotations

import ast
from collections.abc import Mapping
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import ValidationIssue, content_hash
from .errors import SecurityPolicyError
from .security import SecurityPolicy

ALLOWED_LIFECYCLE_ACTIONS = frozenset(
    {"bind_stat_chart_config", "prime_stat_chart_data", "validate_chart_integrity"}
)


class AutomationPolicy:
    def __init__(
        self,
        value: Mapping[str, Any],
        *,
        known_operations: set[str] | None = None,
        verified_setup_contracts: Mapping[str, Any] | None = None,
        verified_execution_contracts: Mapping[str, Any] | None = None,
    ) -> None:
        self.value = dict(value)
        self.targets = {
            str(item["repository_id"]): dict(item) for item in value.get("targets", [])
        }
        self.known_operations = known_operations or set()
        self.verified_setup_contracts = dict(verified_setup_contracts or {})
        self.verified_execution_contracts = dict(verified_execution_contracts or {})

    @classmethod
    def from_file(cls, path: Any) -> "AutomationPolicy":
        policy_path = Path(path)
        with policy_path.open(encoding="utf-8") as file:
            value = json.load(file)
        qa_root = policy_path.resolve().parent.parent
        known_operations: set[str] = set()
        catalog_root = qa_root.parent / "idl" / "http"
        if catalog_root.is_dir():
            for document_path in sorted(catalog_root.rglob("*.openapi.json")):
                with document_path.open(encoding="utf-8") as file:
                    document = json.load(file)
                for path_item in document.get("paths", {}).values():
                    if not isinstance(path_item, Mapping):
                        continue
                    for definition in path_item.values():
                        if isinstance(definition, Mapping) and definition.get("operationId"):
                            known_operations.add(str(definition["operationId"]))
        contracts: dict[str, Any] = {}
        execution_contracts: dict[str, Any] = {}
        contracts_path = qa_root / "knowledge" / "verified-setup-contracts.json"
        if contracts_path.exists():
            with contracts_path.open(encoding="utf-8") as file:
                raw_contracts = json.load(file)
            if raw_contracts.get("schema_version") == "verified-setup-contracts/1.0":
                contracts = dict(raw_contracts.get("contracts", {}))
                execution_contracts = dict(raw_contracts.get("execution_contracts", {}))
        return cls(
            value,
            known_operations=known_operations,
            verified_setup_contracts=contracts,
            verified_execution_contracts=execution_contracts,
        )


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


class _CaseSpecFoldError(ValueError):
    """CASE_SPEC cannot be folded into a static dict without executing code."""


def _fold_case_spec_expr(
    node: ast.AST,
    env: dict[str, Any],
    funcs: dict[str, ast.FunctionDef],
) -> Any:
    """Evaluate one expression using only constants, names, and pure helpers."""

    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise _CaseSpecFoldError(f"unbound name {node.id}")
    if isinstance(node, ast.List):
        return [_fold_case_spec_expr(elt, env, funcs) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_fold_case_spec_expr(elt, env, funcs) for elt in node.elts)
    if isinstance(node, ast.Set):
        return {_fold_case_spec_expr(elt, env, funcs) for elt in node.elts}
    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            raise _CaseSpecFoldError("dict unpacking is not static")
        return {
            _fold_case_spec_expr(key, env, funcs): _fold_case_spec_expr(value, env, funcs)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_fold_case_spec_expr(node.operand, env, funcs)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return +_fold_case_spec_expr(node.operand, env, funcs)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _fold_case_spec_expr(node.operand, env, funcs)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _fold_case_spec_expr(node.left, env, funcs)
        right = _fold_case_spec_expr(node.right, env, funcs)
        if not isinstance(left, (str, bytes, list, tuple, int, float)) or type(left) is not type(right):
            raise _CaseSpecFoldError("unsupported addition")
        return left + right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        func = funcs.get(node.func.id)
        if func is None:
            raise _CaseSpecFoldError(f"call {node.func.id} is not a pure helper")
        return _fold_pure_helper_call(func, node, env, funcs)
    raise _CaseSpecFoldError(f"unsupported expression {type(node).__name__}")


def _fold_pure_helper_call(
    func: ast.FunctionDef,
    call: ast.Call,
    env: dict[str, Any],
    funcs: dict[str, ast.FunctionDef],
) -> Any:
    """Inline a single-return helper whose body is itself foldable."""

    if (
        func.args.vararg
        or func.args.kwarg
        or func.args.kwonlyargs
        or func.args.posonlyargs
        or len(func.body) != 1
        or not isinstance(func.body[0], ast.Return)
        or func.body[0].value is None
    ):
        raise _CaseSpecFoldError(f"helper {func.name} is not a pure single-return function")
    names = [arg.arg for arg in func.args.args]
    defaults = func.args.defaults
    required = len(names) - len(defaults)
    if len(call.args) > len(names):
        raise _CaseSpecFoldError(f"helper {func.name} received extra positional arguments")
    bound: dict[str, Any] = {}
    for index, name in enumerate(names):
        if index < len(call.args):
            bound[name] = _fold_case_spec_expr(call.args[index], env, funcs)
        elif index >= required:
            bound[name] = _fold_case_spec_expr(defaults[index - required], env, funcs)
        else:
            raise _CaseSpecFoldError(f"helper {func.name} missing argument {name}")
    for keyword in call.keywords:
        if not keyword.arg:
            raise _CaseSpecFoldError(f"helper {func.name} uses keyword unpacking")
        bound[keyword.arg] = _fold_case_spec_expr(keyword.value, env, funcs)
    return _fold_case_spec_expr(func.body[0].value, {**env, **bound}, funcs)


def _statically_eval_case_spec(tree: ast.Module) -> Any:
    """Fold CASE_SPEC from top-level constants and pure helper functions.

    A14 sometimes compresses a large CASE_SPEC with names like ``NS`` / ``API``
    and a single-return ``q(...)`` builder. Those files are valid pytest source
    and still a static dict; N05 must fold them instead of blocking the run.
    Arbitrary calls, imports, and attribute access stay rejected.
    """

    env: dict[str, Any] = {}
    funcs: dict[str, ast.FunctionDef] = {}
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            name = stmt.targets[0].id
            if name == "CASE_SPEC":
                return _fold_case_spec_expr(stmt.value, env, funcs)
            env[name] = _fold_case_spec_expr(stmt.value, env, funcs)
            continue
        if isinstance(stmt, ast.FunctionDef):
            funcs[stmt.name] = stmt
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
    raise _CaseSpecFoldError("CASE_SPEC assignment is missing")


def _candidate_spec_structure_issues(
    content: str,
    path: str,
    *,
    known_operations: set[str] | None = None,
    verified_setup_contracts: Mapping[str, Any] | None = None,
    verified_execution_contracts: Mapping[str, Any] | None = None,
    route_to: str = "A14",
) -> list["ValidationIssue"]:
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
                        route_to,
                    )
                )
                return issues
            try:
                case_spec = _literal_eval_case_spec(node.value)
            except (ValueError, TypeError):
                try:
                    case_spec = _statically_eval_case_spec(tree)
                except _CaseSpecFoldError:
                    issues.append(
                        ValidationIssue(
                            "case_spec_not_literal",
                            "CASE_SPEC must be a static dict literal",
                            f"code_candidates.{path}.CASE_SPEC",
                            route_to,
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
                route_to,
            )
        )
        return issues
    resource_requirements = case_spec.get("test_data", {}).get("resource_requirements", [])
    required_body_keys_by_api: dict[str, set[str]] = {}
    retained_resource_variables: set[str] = set()
    all_resources_retained = False
    if isinstance(resource_requirements, list):
        typed_resources = [item for item in resource_requirements if isinstance(item, Mapping)]
        all_resources_retained = bool(typed_resources) and all(
            str(item.get("retention_mode", "")) == "retain" for item in typed_resources
        )
        for resource in resource_requirements:
            if not isinstance(resource, Mapping):
                continue
            if str(resource.get("retention_mode", "")) == "retain":
                variable = str(resource.get("resource_id_variable", ""))
                if variable:
                    retained_resource_variables.add(variable)
            operation = str(resource.get("setup_operation", ""))
            keys = resource.get("required_body_keys")
            if not operation or not isinstance(keys, list) or not keys:
                continue
            required_body_keys_by_api.setdefault(operation, set()).update(
                str(key) for key in keys
            )
    chart_resources = {
        str(item.get("resource_id_variable", "")).strip()
        for item in resource_requirements
        if isinstance(item, Mapping)
        and str(item.get("resource_type", "")) in {"stat_chart", "report"}
    }
    chart_resources.discard("")
    serialized_spec = json.dumps(case_spec, ensure_ascii=False)
    if "chart_view_id" in serialized_spec and not chart_resources:
        issues.append(
            ValidationIssue(
                "chart_binding_missing",
                "Case binds chart_view_id but A22 supplies no chart resource",
                "test_data.resource_requirements",
                route_to,
            )
        )
    declared_variables = (
        case_spec.get("variables", {})
        if isinstance(case_spec.get("variables", {}), Mapping)
        else {}
    )
    for variable in chart_resources:
        value = str(declared_variables.get(variable, ""))
        if value.startswith("BI_"):
            issues.append(
                ValidationIssue(
                    "chart_id_forgery",
                    f"{variable} must resolve from its chart resource, not a literal BI ID",
                    f"variables.{variable}",
                    route_to,
                )
            )
    contracts = verified_setup_contracts or {}
    execution_contracts = verified_execution_contracts or {}
    serialized_case = json.dumps(case_spec, ensure_ascii=False)
    applicable_execution_contracts = [
        contract
        for contract in execution_contracts.values()
        if isinstance(contract, Mapping)
        and any(
            marker in serialized_case
            for marker in map(str, contract.get("applies_when_contains", []))
        )
    ]
    for phase in ("setup", "readiness", "steps", "cleanup", "residue_checks"):
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
                        route_to,
                    )
                )
                continue
            if phase == "cleanup":
                cleanup_text = json.dumps(step, ensure_ascii=False)
                targets_retained = all_resources_retained or any(
                    str(step.get("when_variable", "")) == variable
                    or f"{{{{{variable}}}}}" in cleanup_text
                    or f"{{{{ {variable} }}}}" in cleanup_text
                    for variable in retained_resource_variables
                )
                if targets_retained:
                    issues.append(
                        ValidationIssue(
                            "retained_resource_cleanup_forbidden",
                            f"cleanup[{index}] targets a resource whose retention_mode is retain",
                            f"code_candidates.{path}.cleanup[{index}]",
                            route_to,
                        )
                    )
            action = str(step.get("action") or "").strip()
            if action:
                if action not in ALLOWED_LIFECYCLE_ACTIONS:
                    issues.append(
                        ValidationIssue(
                            "unsupported_step_action",
                            f"{phase}[{index}] action {action!r} is not allowed",
                            f"code_candidates.{path}.{phase}[{index}].action",
                            route_to,
                        )
                    )
                    continue
                expect = step.get("expect")
                if phase in {"setup", "readiness"} and not isinstance(expect, Mapping):
                    issues.append(
                        ValidationIssue(
                            "lifecycle_assertion_missing",
                            f"{phase}[{index}] must assert the requested state",
                            f"code_candidates.{path}.{phase}[{index}].expect",
                            route_to,
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
                        route_to,
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
                        route_to,
                    )
                )
            api = str(request.get("api", ""))
            for execution_contract in applicable_execution_contracts:
                constraints = execution_contract.get("operation_constraints", {})
                if (
                    isinstance(constraints, Mapping)
                    and api == str(constraints.get("forbidden_substitute", ""))
                ):
                    issues.append(
                        ValidationIssue(
                            "execution_contract_mismatch",
                            f"{api} is not the verified operation for this execution scenario",
                            f"code_candidates.{path}.{phase}[{index}].request.api",
                            route_to,
                        )
                    )
            if known_operations is not None and api and api not in known_operations:
                issues.append(
                    ValidationIssue(
                        "operation_not_registered",
                        f"{phase}[{index}] operation {api!r} is not defined in idl/http",
                        f"code_candidates.{path}.{phase}[{index}].request.api",
                        route_to,
                    )
                )
            required_keys = required_body_keys_by_api.get(api)
            contract = contracts.get(api)
            execution_contract = execution_contracts.get(api)
            if phase == "setup" and isinstance(contract, Mapping):
                required_keys = set(map(str, contract.get("required_body_keys", [])))
            if phase == "setup" and required_keys:
                body = request.get("json")
                if not isinstance(body, Mapping):
                    issues.append(
                        ValidationIssue(
                            "setup_body_missing_contract_fields",
                            f"setup[{index}] body for {api} must be an object"
                            " carrying the verified contract keys",
                            f"code_candidates.{path}.setup[{index}].request.json",
                            route_to,
                        )
                    )
                else:
                    missing = sorted(required_keys - set(body.keys()))
                    if missing:
                        issues.append(
                            ValidationIssue(
                                "setup_body_missing_contract_fields",
                                f"setup[{index}] {api} body lacks verified contract"
                                f" keys: {', '.join(missing)}",
                                f"code_candidates.{path}.setup[{index}].request.json",
                                route_to,
                            )
                        )
            if phase == "steps" and isinstance(execution_contract, Mapping):
                execution_required = set(
                    map(str, execution_contract.get("required_body_keys", []))
                )
                body = request.get("json")
                missing = sorted(
                    execution_required - set(body)
                    if isinstance(body, Mapping)
                    else execution_required
                )
                if missing:
                    issues.append(
                        ValidationIssue(
                            "execution_body_missing_contract_fields",
                            f"steps[{index}] {api} body lacks verified contract keys: "
                            + ", ".join(missing),
                            f"code_candidates.{path}.steps[{index}].request.json",
                            route_to,
                        )
                    )
                chart_bound = any(
                    isinstance(item, Mapping)
                    and str(item.get("resource_type") or "") in {
                        "stat_chart", "report", "pivot_table", "joined_report"
                    }
                    for item in case_spec.get("data_validity", [])
                )
                if (
                    chart_bound
                    and isinstance(body, Mapping)
                    and str(body.get("id") or "").replace(" ", "")
                    == "{{chart_view_id}}"
                    and body.get("isView") != 1
                ):
                    issues.append(
                        ValidationIssue(
                            "chart_detail_query_mode_mismatch",
                            f"steps[{index}] binds chart_view_id but isView is not 1",
                            f"code_candidates.{path}.steps[{index}].request.json.isView",
                            route_to,
                        )
                    )
            expect = step.get("expect")
            if phase in {"setup", "readiness"} and not isinstance(expect, Mapping):
                issues.append(
                    ValidationIssue(
                        "lifecycle_assertion_missing",
                        f"{phase}[{index}] must assert the requested state",
                        f"code_candidates.{path}.{phase}[{index}].expect",
                        route_to,
                    )
                )
            if isinstance(expect, Mapping):
                from .case_executability import SUPPORTED_RESPONSE_EXPECTATIONS

                unknown = sorted(set(map(str, expect)) - SUPPORTED_RESPONSE_EXPECTATIONS)
                if not expect or unknown:
                    issues.append(
                        ValidationIssue(
                            "response_expectation_unsupported",
                            (
                                "response expectation is empty"
                                if not expect
                                else "unsupported response expectation keys: "
                                + ", ".join(unknown)
                            ),
                            f"code_candidates.{path}.{phase}[{index}].expect",
                            route_to,
                        )
                    )
            if phase == "setup" and isinstance(contract, Mapping):
                allowed_paths = set(map(str, contract.get("response_id_paths", [])))
                extract = step.get("extract")
                actual_paths = (
                    set(map(str, extract.values()))
                    if isinstance(extract, Mapping)
                    else set()
                )
                if allowed_paths and not actual_paths.intersection(allowed_paths):
                    issues.append(
                        ValidationIssue(
                            "setup_extract_contract_mismatch",
                            f"setup[{index}] {api} must extract its resource id from one of "
                            f"{sorted(allowed_paths)}",
                            f"code_candidates.{path}.setup[{index}].extract",
                            route_to,
                        )
                    )
    expected = case_spec.get("expected")
    if isinstance(expected, list):
        from .case_executability import SUPPORTED_ORACLE_MATCHERS

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
                        route_to,
                    )
                )
                continue
            matcher = str(oracle.get("matcher", ""))
            normalized_matcher = "equals" if matcher.startswith("equals:") else matcher
            if normalized_matcher not in SUPPORTED_ORACLE_MATCHERS:
                issues.append(
                    ValidationIssue(
                        "oracle_matcher_not_supported",
                        f"expected[{index}] matcher {matcher!r} is not executable",
                        f"code_candidates.{path}.expected[{index}].oracle.matcher",
                        route_to,
                    )
                )
            if (
                normalized_matcher not in {"exists", "one_of", "not_one_of", "one_of_actually_matched"}
                and "expected_value" not in oracle
                and "expected_values" not in oracle
                and not matcher.startswith("equals:")
            ):
                issues.append(
                    ValidationIssue(
                        "oracle_expected_value_missing",
                        f"expected[{index}] matcher requires expected_value",
                        f"code_candidates.{path}.expected[{index}].oracle.expected_value",
                        route_to,
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
                route_to,
            )
        )
    if not assert_ok:
        issues.append(
            ValidationIssue(
                "assert_oracles_signature_invalid",
                "assert_oracles must be called with (observations, CASE_SPEC[\"expected\"])",
                f"code_candidates.{path}",
                route_to,
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
            enforce_operations = bool(
                policy.value.get("require_registered_operations_for_network", False)
                and manifest.get("permissions", {}).get("network") is True
            )
            issues.extend(
                _candidate_spec_structure_issues(
                    content,
                    path,
                    known_operations=(
                        policy.known_operations if enforce_operations else None
                    ),
                    verified_setup_contracts=policy.verified_setup_contracts,
                    verified_execution_contracts=policy.verified_execution_contracts,
                    route_to=_generator_route(manifest),
                )
            )
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
