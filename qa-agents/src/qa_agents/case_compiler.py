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
            child_id = f"{parent_id}-{layer.upper()}"
            if child_id in seen_ids:
                raise ContractError(f"Duplicate compiled case id {child_id}")
            seen_ids.add(child_id)
            child["id"] = child_id
            child["parent_case_id"] = parent_id
            child["layer"] = layer
            child.pop("required_layers", None)
            children.append(child)
    return children
