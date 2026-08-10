"""N25 deterministic parent-to-layer Test Case IR compiler."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .errors import ContractError


VALID_LAYERS = {"frontend", "backend", "contract", "e2e", "non_functional"}


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
