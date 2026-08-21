"""Backlog adapter: turn verified BI create contracts into recipe candidates.

Cases that A22/D01 cannot resolve with the frozen capability catalog are
routed to ``capability_adapter_backlog``.  The adapter reads verified 112
create contracts and emits *candidates* (never executable recipes) together
with the evidence each candidate still needs before N27 could accept it as a
published recipe.  This keeps the pipeline honest: no endpoint, body or
evidence is invented.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .errors import ContractError, InputError, SecurityPolicyError


RECIPE_CANDIDATE_CONTRACT = "bi-recipe-candidate/1.0"
_SECRET_KEYS = {"password", "token", "secret", "authorization", "cookie"}
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

ASSET_MATCH_TERMS: dict[str, tuple[str, ...]] = {
    "custom_dimension": ("自定义维度", "枚举维度", "custom dimension"),
    "aggregate_metric": ("聚合指标", "聚合度量", "agg metric", "aggregate metric"),
    "calculated_metric": ("计算指标", "计算度量", "公式指标", "calculated metric"),
    "ordinary_metric": ("普通指标", "普通度量", "一般指标", "ordinary metric"),
    "comparison_metric": ("同环比", "同比", "环比", "comparison metric"),
    "joined_table": ("拼表", "关联表", "joined table", "join table"),
    "stat_chart": ("统计图", "图表", "图形", "chart", "stat view"),
    "pivot_table": ("交叉表", "透视表", "pivot", "cross table"),
    "report": ("报表", "报告", "report", "dashboard"),
    "ordinary_report": ("报表", "报告", "report", "dashboard"),
}

_ID_VARIABLES: dict[str, str] = {
    "aggregate_metric": "metric_field_id",
    "calculated_metric": "calc_field_id",
    "custom_dimension": "dimension_id",
    "joined_table": "joined_table_id",
    "stat_chart": "view_id",
    "pivot_table": "pivot_view_id",
    "report": "report_id",
    "ordinary_report": "report_id",
}


def load_verified_contracts(contracts_dir: Path) -> list[dict[str, Any]]:
    """Normalize ``verified-setup-contracts.json`` and ``bi-*-create-contract.json``."""
    contracts: list[dict[str, Any]] = []
    verified_path = contracts_dir / "verified-setup-contracts.json"
    if verified_path.is_file():
        data = _read_json(verified_path)
        raw_contracts = data.get("contracts", {})
        if not isinstance(raw_contracts, Mapping):
            raise ContractError("verified-setup-contracts.json contracts must be an object")
        for operation_id, spec in raw_contracts.items():
            if not isinstance(spec, Mapping):
                continue
            asset_type = str(spec.get("resource_type", ""))
            if not asset_type:
                continue
            contracts.append(
                {
                    "contract_ref": verified_path.name,
                    "asset_type": asset_type,
                    "operation_id": str(operation_id),
                    "status": str(spec.get("status", "")),
                    "body_template": spec.get("body_template"),
                    "substitutions": spec.get("substitutions", {}),
                    "readback_operation": str(spec.get("readback_operation", "")),
                    "delete_operation": str(spec.get("delete_operation", "")),
                    "retention_mode": str(spec.get("retention_mode", "")),
                    "derivation": spec.get("derivation"),
                    "evidence": str(spec.get("evidence", "")),
                }
            )
    for path in sorted(contracts_dir.glob("bi-*-create-contract.json")):
        data = _read_json(path)
        asset_type = str(data.get("asset_type", ""))
        if not asset_type:
            continue
        contracts.append(
            {
                "contract_ref": path.name,
                "asset_type": asset_type,
                "operation_id": str(data.get("operation_id", "")),
                "status": str(data.get("status", "")),
                "body_template": None,
                "substitutions": data.get("case_derived", []),
                "readback_operation": str(data.get("readback_operation_id", "")),
                    "delete_operation": str(data.get("delete_operation", "") or ""),
                    "retention_mode": str(data.get("retention_mode", "")),
                "derivation": data.get("derivation"),
                "evidence": str(data.get("verification_evidence", "")),
            }
        )
    return contracts


def verification_requirements(
    contract: Mapping[str, Any], operation_pairs: Mapping[str, Any] | None = None
) -> list[dict[str, str]]:
    """Deterministic evidence gaps for a contract before it can be a recipe."""
    requirements: list[dict[str, str]] = []
    asset_type = str(contract.get("asset_type", ""))
    registered_pairs = operation_pairs if isinstance(operation_pairs, Mapping) else {}
    if asset_type == "custom_dimension":
        requirements.append(
            {
                "code": "live_enum_option_bindings",
                "description": "enum_group dimensionConfig values must come from a live get_ui_type option query with response hash",
                "required_evidence": "option_query_operation + option_response_hash + selected_option_codes",
            }
        )
    if asset_type == "joined_table":
        requirements.append(
            {
                "code": "live_discovery_evidence",
                "description": "folder/topology/identity must be derived from live query_arg_detail and hash-bound",
                "required_evidence": "live_discovery_evidence with response hashes",
            }
        )
    if asset_type == "stat_chart":
        requirements.append(
            {
                "code": "folder_binding",
                "description": "chart category must bind a live requirement-name folder with response hash",
                "required_evidence": "folder_query_operation + folder_response_hash + category_id",
            }
        )
        requirements.append(
            {
                "code": "configuration_hash",
                "description": "chart configuration must be hash-bound from live readback",
                "required_evidence": "configuration_hash",
            }
        )
    if str(contract.get("status", "")) != "verified_112":
        requirements.append(
            {
                "code": "contract_verification_112",
                "description": "create operation must be verified against environment 112 with readback evidence",
                "required_evidence": "captured request/response evidence in 112",
            }
        )
    operation_id = str(contract.get("operation_id", ""))
    registered_cleanup = str(registered_pairs.get(operation_id, "")) if operation_id else ""
    retained = str(contract.get("retention_mode", "")) == "retain"
    if not retained and not str(contract.get("delete_operation", "")) and not registered_cleanup:
        requirements.append(
            {
                "code": "cleanup_operation_pair",
                "description": "a verified delete/cleanup operation must exist and be registered in the test-data policy before the resource can be executed",
                "required_evidence": "delete operation verified in 112 and registered operation pair",
            }
        )
    return requirements


def build_candidate(
    contract: Mapping[str, Any], operation_pairs: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Build one recipe candidate from a verified contract."""
    asset_type = str(contract.get("asset_type", ""))
    operation_id = str(contract.get("operation_id", ""))
    terms = ASSET_MATCH_TERMS.get(asset_type, (asset_type,))
    body = deepcopy(contract.get("body_template"))
    if not isinstance(body, Mapping):
        body = {}
    body = _bind_namespace(body)
    requirements = verification_requirements(contract, operation_pairs)
    return {
        "candidate_id": f"{asset_type}-create",
        "asset_type": asset_type,
        "source_contract": str(contract.get("contract_ref", "")),
        "contract_status": str(contract.get("status", "")),
        "operation_id": operation_id,
        "readback_operation": str(contract.get("readback_operation", "")),
        "match": {
            "data_intents": [f"{asset_type}.create"],
            "datasets": [asset_type],
            "all_term_groups": [list(terms)],
        },
        "supported_variants": [asset_type],
        "resource_goals": [
            {"resource_type": asset_type, "desired_state": {"created": True}}
        ],
        "resources": [
            {
                "resource_key": f"{asset_type}_resource",
                "resource_type": asset_type,
                "lifecycle_mode": "create",
                "retention_mode": str(contract.get("retention_mode", "delete")) or "delete",
                "resource_id_variable": _ID_VARIABLES.get(asset_type, f"{asset_type}_id"),
                "depends_on": [],
                "setup": {
                    "name": f"创建{asset_type}隔离资源",
                    "request": {"protocol": "http", "api": operation_id, "json": body},
                },
                "readiness": [],
                "cleanup": {},
                "residue_checks": [],
            }
        ],
        "verification_requirements": requirements,
    }


def build_chart_detail_candidate(
    metric_contract: Mapping[str, Any],
    chart_contract: Mapping[str, Any],
    operation_pairs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Composite candidate: isolated metric + saved chart that can execute 查看明细."""
    metric = build_candidate(metric_contract, operation_pairs)
    chart = build_candidate(chart_contract, operation_pairs)
    metric_resource = deepcopy(metric["resources"][0])
    chart_resource = deepcopy(chart["resources"][0])
    chart_resource["resource_key"] = "detail_chart"
    chart_resource["depends_on"] = [metric_resource["resource_key"]]
    chart_resource["scene_roles"] = [
        "metric_or_dimension",
        "chart_or_pivot",
        "view_readiness",
        "detail_entry_execution",
    ]
    metric_resource["scene_roles"] = ["source_field", "metric_or_dimension"]
    requirements = list(metric["verification_requirements"])
    for item in chart["verification_requirements"]:
        if item not in requirements:
            requirements.append(item)
    requirements.append(
        {
            "code": "requirement_folder",
            "description": "chart folder must exactly match the approved requirement name",
            "required_evidence": "requirement_name + folder readback hash",
        }
    )
    return {
        "candidate_id": "metric-plus-stat-chart-detail",
        "asset_types": [metric["asset_type"], chart["asset_type"]],
        "source_contract": f"{metric['source_contract']}; {chart['source_contract']}",
        "contract_status": "composite_candidate",
        "match": {
            "data_intents": ["chart_detail.metric_with_chart"],
            "datasets": [],
            "all_term_groups": [
                ["查看明细", "统计图"],
                ["查看明细", "图表"],
                ["查看明细", "指标统计图"],
                ["查看明细", "指标图表"],
            ],
        },
        "match_all_terms": True,
        "supported_variants": ["aggregate_metric", "stat_chart"],
        "resource_goals": [
            {"resource_type": "aggregate_metric", "desired_state": {"created": True}},
            {"resource_type": "stat_chart", "desired_state": {"created": True, "saved": True}},
        ],
        "resources": [metric_resource, chart_resource],
        "verification_requirements": requirements,
    }


def build_candidate_catalog(
    contracts: list[Mapping[str, Any]],
    sources: Mapping[str, Any],
    operation_pairs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Full candidate set for all verified contracts (used to seed the catalog)."""
    by_type: dict[str, Mapping[str, Any]] = {}
    for contract in contracts:
        asset_type = str(contract.get("asset_type", ""))
        if asset_type and asset_type not in by_type:
            by_type[asset_type] = contract
    candidates: list[dict[str, Any]] = []
    for contract in by_type.values():
        candidate = build_candidate(contract, operation_pairs)
        if candidate.get("verification_requirements"):
            candidates.append(candidate)
    if "stat_chart" in by_type and "aggregate_metric" in by_type:
        candidates.append(
            build_chart_detail_candidate(
                by_type["aggregate_metric"], by_type["stat_chart"], operation_pairs
            )
        )
    payload = {
        "schema_version": RECIPE_CANDIDATE_CONTRACT,
        "sources_hash": _content_hash(sources),
        "candidates": candidates,
    }
    validate_recipe_candidates(payload)
    return payload


def select_candidates_for_cases(
    cases: list[Mapping[str, Any]], candidate_catalog: Mapping[str, Any]
) -> dict[str, Any]:
    """Match unresolved Cases to candidates by deterministic term scoring.

    When several candidates match, the most specific one (highest matched
    term count) wins; a tie stays unmatched instead of guessing.
    """
    candidates = [
        item for item in candidate_catalog.get("candidates", []) if isinstance(item, Mapping)
    ]
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id", case.get("id", "")))
        text = json.dumps(
            {
                "title": case.get("title", ""),
                "test_data": case.get("test_data", {}),
                "preconditions": case.get("preconditions", []),
                "steps": case.get("steps", []),
            },
            ensure_ascii=False,
        ).lower()
        dataset = str(case.get("dataset", ""))
        scored = [
            (candidate, _candidate_match_score(candidate, text, dataset))
            for candidate in candidates
        ]
        scored = [(candidate, score) for candidate, score in scored if score > 0]
        if not scored:
            unmatched.append(
                {
                    "case_id": case_id,
                    "reason_code": str(case.get("reason_code", "data_capability_not_registered")),
                    "matched_candidate_count": 0,
                }
            )
            continue
        scored.sort(key=lambda item: item[1], reverse=True)
        best_score = scored[0][1]
        winners = [candidate for candidate, score in scored if score == best_score]
        if len(winners) == 1:
            matched.append(
                {
                    "case_id": case_id,
                    "candidate_id": str(winners[0]["candidate_id"]),
                    "reason_code": str(case.get("reason_code", "data_capability_not_registered")),
                    "match_score": best_score,
                }
            )
        else:
            unmatched.append(
                {
                    "case_id": case_id,
                    "reason_code": str(case.get("reason_code", "data_capability_not_registered")),
                    "matched_candidate_count": len(scored),
                }
            )
    return {
        "schema_version": "bi-recipe-candidate-selection/1.0",
        "matched_cases": matched,
        "unmatched_cases": unmatched,
    }


def _candidate_match_score(
    candidate: Mapping[str, Any], text: str, dataset: str
) -> int:
    match = candidate.get("match", {})
    if not isinstance(match, Mapping):
        return 0
    datasets = {str(item) for item in match.get("datasets", [])}
    score = 1000 if dataset and dataset in datasets else 0
    groups = match.get("all_term_groups", [])
    require_all = bool(candidate.get("match_all_terms"))
    for group in groups:
        if not isinstance(group, list) or not group:
            continue
        terms = [str(term).lower() for term in group]
        present = [term for term in terms if term in text]
        if require_all:
            if len(present) == len(terms):
                score += len(present)
        else:
            score += len(present)
    return score


def validate_recipe_candidates(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Reject candidates that would fake autonomous completion."""
    if payload.get("schema_version") != RECIPE_CANDIDATE_CONTRACT:
        raise ContractError("recipe candidate schema_version is invalid")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ContractError("recipe candidates require at least one candidate")
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ContractError(f"candidates[{index}] must be an object")
        candidate_id = str(candidate.get("candidate_id", ""))
        if not candidate_id or candidate_id in seen:
            raise ContractError(f"candidates[{index}].candidate_id must be unique and non-empty")
        seen.add(candidate_id)
        match = candidate.get("match")
        if not isinstance(match, Mapping) or not (
            match.get("data_intents") or match.get("datasets") or match.get("all_term_groups")
        ):
            raise ContractError(f"candidate {candidate_id} requires match rules")
        requirements = candidate.get("verification_requirements")
        if not isinstance(requirements, list) or not requirements:
            raise ContractError(
                f"candidate {candidate_id} must declare verification requirements "
                "(a candidate without evidence gaps would fake completion)"
            )
        for requirement in requirements:
            if not isinstance(requirement, Mapping) or not str(requirement.get("code", "")):
                raise ContractError(f"candidate {candidate_id} has an invalid verification requirement")
        resources = candidate.get("resources")
        if not isinstance(resources, list) or not resources:
            raise ContractError(f"candidate {candidate_id} requires resources")
    lowered = {str(key).lower(): key for key in payload}
    secret_keys = sorted(key for key in _SECRET_KEYS if key in lowered)
    if secret_keys:
        raise SecurityPolicyError(
            "recipe candidates must not contain secret values: " + ", ".join(secret_keys)
        )
    return {
        "schema_version": "bi-recipe-candidate-validation/1.0",
        "valid": True,
        "candidate_count": len(candidates),
    }


def prepare_recipe_candidates(
    compiled_cases_path: Path,
    contracts_dir: Path,
    output_dir: Path,
    *,
    environment: str,
    namespace: str,
    capability_catalog_path: Path | None = None,
    sources_path: Path | None = None,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    """Write hash-bound recipe candidates for unresolved backlog Cases."""
    from .data_planning import extract_test_data_intents
    from .security import SecurityPolicy

    security = SecurityPolicy()
    compiled = _read_envelope(compiled_cases_path, "n25-compiled-test-cases")
    payload = compiled.get("payload", {})
    cases = payload.get("compiled_cases", payload.get("child_cases"))
    if not isinstance(cases, list) or not all(isinstance(item, Mapping) for item in cases):
        raise ContractError("N25 compiled_cases or child_cases must be a list of objects")
    unresolved: list[Mapping[str, Any]] = []
    if capability_catalog_path is not None:
        catalog = _read_json(capability_catalog_path)
        intents = extract_test_data_intents(cases, catalog)
        unresolved = [item for item in intents.get("unresolved_requirements", []) if isinstance(item, Mapping)]
    sources = _read_json(sources_path) if sources_path is not None else {"sources": []}
    security.assert_no_secret_values(sources)
    operation_pairs = None
    if policy_path is not None:
        policy = _read_json(policy_path)
        operation_pairs = policy.get("operation_pairs")
    contracts = load_verified_contracts(contracts_dir)
    candidates = build_candidate_catalog(contracts, sources, operation_pairs)
    selection = select_candidates_for_cases(unresolved, candidates)
    validation = validate_recipe_candidates(candidates)
    output_payload = {
        **candidates,
        "environment": environment,
        "namespace": namespace,
        "selection": selection,
        "unresolved_count": len(unresolved),
    }
    store = _ArtifactStore(output_dir)
    store.write_json("bi-recipe-candidates.json", output_payload)
    store.write_json(
        "bi-recipe-candidate-preparation.json",
        {
            "schema_version": "bi-recipe-candidate-preparation/1.0",
            "environment": environment,
            "namespace": namespace,
            "candidate_count": validation["candidate_count"],
            "matched_case_count": len(selection["matched_cases"]),
            "unmatched_case_count": len(selection["unmatched_cases"]),
        },
    )
    return {
        "schema_version": "bi-recipe-candidate-preparation/1.0",
        "environment": environment,
        "namespace": namespace,
        "candidate_count": validation["candidate_count"],
        "matched_case_count": len(selection["matched_cases"]),
        "unmatched_case_count": len(selection["unmatched_cases"]),
        "validation": validation,
    }


def _bind_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _bind_namespace(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_bind_namespace(item) for item in value]
    if isinstance(value, str) and "{{namespace}}" in value:
        return value.replace("{{namespace}}", "{{ namespace }}")
    return value


def _content_hash(value: Mapping[str, Any]) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InputError(f"not valid JSON: {path}") from error
    if not isinstance(value, Mapping):
        raise ContractError(f"expected an object: {path}")
    return dict(value)


def _read_envelope(path: Path, artifact_id: str) -> dict[str, Any]:
    from .contracts import artifact_hash_from_mapping

    envelope = _read_json(path)
    if envelope.get("schema_version") != "artifact-envelope/1.0":
        raise ContractError(f"{path} is not an Artifact Envelope")
    if envelope.get("artifact_hash") != artifact_hash_from_mapping(envelope):
        raise ContractError(f"{path} Artifact hash is invalid")
    if envelope.get("artifact_id") != artifact_id:
        raise ContractError(f"requires Artifact {artifact_id}")
    return envelope


class _ArtifactStore:
    """Minimal JSON writer (kept local to avoid coupling to storage internals)."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def write_json(self, name: str, value: Mapping[str, Any]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
