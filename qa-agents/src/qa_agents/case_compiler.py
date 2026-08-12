"""N25 deterministic parent-to-layer Test Case IR compiler."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .errors import ContractError
from .contracts import content_hash


VALID_LAYERS = {"frontend", "backend", "contract", "e2e", "non_functional"}


def project_capability_atoms(
    compiled_cases: list[Mapping[str, Any]],
    capabilities: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Project composite data matrices without changing approved Case semantics.

    An atom is an execution unit, not a new approved Case.  It contributes an
    observation to its parent's Oracle; only the aggregation contract may mark
    that Oracle satisfied after every required variant has completed.
    """

    atoms: list[dict[str, Any]] = []
    aggregations: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for case in sorted(compiled_cases, key=lambda item: str(item.get("id", ""))):
        case_id = str(case.get("id", "")).strip()
        test_data = case.get("test_data", {})
        datasets = test_data.get("datasets") if isinstance(test_data, Mapping) else None
        if not isinstance(datasets, list) or len(datasets) < 2:
            continue
        dataset_variants = [
            str(item.get("type", "")).strip().lower()
            for item in datasets
            if isinstance(item, Mapping)
        ]
        # Only a complete unique typed matrix is an atomic-capability contract.
        # Other ``datasets`` collections retain their approved composite shape.
        if (
            len(dataset_variants) != len(datasets)
            or any(not item for item in dataset_variants)
            or len(set(dataset_variants)) != len(dataset_variants)
        ):
            continue
        variants: list[str] = []
        case_atom_ids: list[str] = []
        for dataset in datasets:
            if not isinstance(dataset, Mapping):
                raise ContractError(f"Case {case_id} has an invalid datasets entry")
            variant = str(dataset.get("type", "")).strip().lower()
            variants.append(variant)
            atom_id = f"{case_id}::{variant}"
            if atom_id in seen_ids:
                raise ContractError(f"Duplicate capability atom id {atom_id}")
            seen_ids.add(atom_id)
            capability = capabilities.get(variant)
            if capability and str(case.get("layer", "")) not in {
                str(item) for item in capability.get("allowed_layers", ["backend"])
            }:
                capability = None
            atom = deepcopy(dict(case))
            atom.update(
                {
                    "id": atom_id,
                    "parent_case_id": case_id,
                    "approved_parent_case_id": str(case.get("parent_case_id", case_id)),
                    "capability_variant": variant,
                    "test_data": deepcopy(dict(dataset)),
                    "parent_oracle_observations": [
                        {
                            "parent_oracle_id": str(item.get("id", "")),
                            "satisfaction_mode": "contribution_only",
                        }
                        for item in case.get("expected", [])
                        if isinstance(item, Mapping)
                        and str(item.get("oracle", {}).get("type", "")) == "deterministic"
                    ],
                    "parent_oracle_satisfied": False,
                }
            )
            if capability:
                atom["capability_status"] = "registered"
                atom["data_intent"] = str(capability.get("data_intent", ""))
                atom["recipe_id"] = str(capability.get("recipe_id", ""))
                atom["test_data"].update(
                    {
                        "dataset": capability.get("dataset"),
                        "data_intent": capability.get("data_intent"),
                        "variants": [capability.get("label", variant)],
                    }
                )
            else:
                atom["capability_status"] = "deferred"
                atom["defer_reason_code"] = (
                    "data_capability_layer_not_registered"
                    if variant in capabilities
                    else "data_capability_variant_not_registered"
                )
            atoms.append(atom)
            case_atom_ids.append(atom_id)
        aggregations.append(
            {
                "parent_case_id": case_id,
                "required_atom_ids": case_atom_ids,
                "required_variants": variants,
                "oracle_rules": [
                    {
                        "parent_oracle_id": str(item.get("id", "")),
                        "required_atom_ids": case_atom_ids,
                        "rule": "all_required_atoms_completed_and_passed",
                    }
                    for item in case.get("expected", [])
                    if isinstance(item, Mapping)
                    and str(item.get("oracle", {}).get("type", "")) == "deterministic"
                ],
                "manual_obligation_ids": [
                    str(item.get("id", ""))
                    for item in case.get("expected", [])
                    if isinstance(item, Mapping)
                    and str(item.get("oracle", {}).get("type", "")) != "deterministic"
                ],
                "parent_completion_rule": (
                    "all_required_atoms_passed_and_all_manual_obligations_completed"
                ),
            }
        )
    return {
        "schema_version": "n25-capability-atom-projection/1.0",
        "atoms": atoms,
        "aggregations": aggregations,
    }


def apply_approved_split_correction(
    parent_cases: list[Mapping[str, Any]], correction: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Apply a content-addressed human-approved responsibility-only correction."""

    if correction.get("schema_version") != "n25-split-correction/1.0":
        raise ContractError("N25 split correction schema_version is invalid")
    unhashed = {key: value for key, value in correction.items() if key != "correction_hash"}
    if correction.get("correction_hash") != content_hash(unhashed):
        raise ContractError("N25 split correction hash is invalid")
    approval = correction.get("approval")
    if not isinstance(approval, Mapping) or approval.get("status") != "done":
        raise ContractError("N25 split correction requires a completed human approval")
    if not str(approval.get("issue_id", "")) or not str(approval.get("issue_identifier", "")):
        raise ContractError("N25 split correction approval binding is incomplete")

    rules = correction.get("case_rules")
    if not isinstance(rules, Mapping):
        raise ContractError("N25 split correction case_rules are invalid")
    result = [deepcopy(dict(item)) for item in parent_cases]
    by_id = {str(item.get("id", "")): item for item in result}
    if set(map(str, rules)) != set(by_id):
        raise ContractError("N25 split correction must cover every parent Case exactly once")
    for case_id, raw_rule in rules.items():
        if not isinstance(raw_rule, Mapping):
            raise ContractError(f"N25 split correction rule is invalid: {case_id}")
        parent = by_id[str(case_id)]
        layers = raw_rule.get("required_layers")
        assignments = raw_rule.get("expected_layers")
        cleanup_oracle = raw_rule.get("cleanup_oracle")
        if (
            not isinstance(layers, list)
            or not layers
            or not set(map(str, layers)) <= VALID_LAYERS
            or not isinstance(assignments, Mapping)
            or not isinstance(cleanup_oracle, Mapping)
        ):
            raise ContractError(f"N25 split correction fields are invalid: {case_id}")
        existing_layers = set(map(str, parent.get("required_layers", [])))
        corrected_layers = set(map(str, layers))
        if not existing_layers <= corrected_layers:
            raise ContractError(f"N25 split correction cannot remove layers: {case_id}")
        expected = parent.get("expected", [])
        expected_ids = {str(item.get("id", "")) for item in expected if isinstance(item, Mapping)}
        if set(map(str, assignments)) != expected_ids:
            raise ContractError(f"N25 split correction must assign every Oracle: {case_id}")
        parent["required_layers"] = sorted(corrected_layers)
        parent["cleanup_oracle"] = deepcopy(dict(cleanup_oracle))
        for item in expected:
            oracle_id = str(item.get("id", ""))
            oracle_layers = assignments[oracle_id]
            if (
                not isinstance(oracle_layers, list)
                or not oracle_layers
                or not set(map(str, oracle_layers)) <= corrected_layers
            ):
                raise ContractError(
                    f"N25 split correction Oracle layers are invalid: {case_id}/{oracle_id}"
                )
            item["layers"] = sorted(set(map(str, oracle_layers)))
    return result


def compile_cases(
    parent_cases: list[Mapping[str, Any]], strategy: Mapping[str, Any]
) -> list[dict[str, Any]]:
    default_layers = list(strategy.get("required_layers", []))
    children: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for parent in sorted(parent_cases, key=lambda item: str(item.get("id", ""))):
        parent_id = str(parent.get("id", "")).strip()
        if not parent_id:
            raise ContractError("Parent case id is required")
        layers = list(parent.get("required_layers", default_layers))
        if not layers:
            raise ContractError(f"Case {parent_id} has no required test layers")
        for layer in sorted(set(layers)):
            if layer not in VALID_LAYERS:
                raise ContractError(f"Case {parent_id} has unsupported layer {layer}")
            child = deepcopy(dict(parent))
            child["expected"] = _narrow_expected_for_layer(
                parent.get("expected", []), layer, parent_id
            )
            child_id = f"{parent_id}-{layer.upper()}"
            if child_id in seen_ids:
                raise ContractError(f"Duplicate compiled case id {child_id}")
            seen_ids.add(child_id)
            child["id"] = child_id
            child["parent_case_id"] = parent_id
            child["layer"] = layer
            if parent.get("expected") and not child["expected"]:
                raise ContractError(
                    f"Case {parent_id} layer {layer} has no expectations after narrowing"
                )
            child.pop("required_layers", None)
            children.append(child)
    return children


def _narrow_expected_for_layer(
    expected: list[Any], layer: str, parent_id: str
) -> list[dict[str, Any]]:
    """Keep only expectations whose explicit layers include the child layer.

    N25 may only copy or narrow execution responsibility. When A08 annotates
    ``expected[].layers``, each layer child keeps exactly those expectations;
    an expectation without a ``layers`` annotation stays in every child
    (backward-compatible default), so no business expectation is silently dropped.
    """

    narrowed: list[dict[str, Any]] = []
    for item in expected:
        if not isinstance(item, Mapping):
            continue
        annotated = item.get("layers")
        if annotated is None:
            narrowed.append(deepcopy(dict(item)))
            continue
        if not isinstance(annotated, list) or not annotated:
            raise ContractError(
                f"Case {parent_id} expected {item.get('id')} has invalid layers annotation"
            )
        if layer in {str(value) for value in annotated}:
            narrowed.append(deepcopy(dict(item)))
    return narrowed
