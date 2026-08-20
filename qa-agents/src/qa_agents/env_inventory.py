"""Deterministic environment-inventory resolution for test-data plans.

The static capability catalog cannot know every live 112 field id, enum
option code or folder id.  An environment inventory snapshot captured by a
112 probe supplies those values so N28 can render a plan before N27
validation.  Values that the snapshot cannot prove stay unresolved and are
reported as ``runtime_required`` instead of being guessed.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .errors import ContractError, InputError, SecurityPolicyError


INVENTORY_CONTRACT = "bi-environment-inventory/1.0"
_SECRET_KEYS = {"password", "token", "secret", "authorization", "cookie"}
_VARIABLE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def validate_inventory_snapshot(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an environment inventory snapshot and reject secret values."""
    if inventory.get("schema_version") != INVENTORY_CONTRACT:
        raise ContractError("environment inventory schema_version is invalid")
    environment = str(inventory.get("environment", ""))
    if not environment:
        raise ContractError("environment inventory requires an environment")
    variables = inventory.get("variables")
    if not isinstance(variables, Mapping):
        raise ContractError("environment inventory requires a variables object")
    lowered = {str(key).lower(): key for key in variables}
    secret_keys = sorted(key for key in _SECRET_KEYS if key in lowered)
    if secret_keys:
        raise SecurityPolicyError(
            "environment inventory must not contain secret values: " + ", ".join(secret_keys)
        )
    provenance = inventory.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ContractError("environment inventory requires provenance")
    if not str(provenance.get("captured_at", "")) or not str(
        provenance.get("probe_refs", "")
    ):
        raise ContractError("environment inventory provenance is incomplete")
    schemas = inventory.get("schemas", [])
    if not isinstance(schemas, list):
        raise ContractError("environment inventory schemas must be a list")
    for index, schema in enumerate(schemas):
        if not isinstance(schema, Mapping):
            raise ContractError(f"environment inventory schemas[{index}] must be an object")
        schema_id = str(schema.get("schema_id", ""))
        if not schema_id:
            raise ContractError(f"environment inventory schemas[{index}] requires schema_id")
        if not str(schema.get("schema_object", "")):
            raise ContractError(f"environment inventory schema {schema_id} requires schema_object")
        fields = schema.get("fields", [])
        if not isinstance(fields, list):
            raise ContractError(f"environment inventory schema {schema_id} fields must be a list")
        for field_index, field in enumerate(fields):
            if not isinstance(field, Mapping):
                raise ContractError(
                    f"environment inventory schema {schema_id} fields[{field_index}] must be an object"
                )
            if not str(field.get("field_id", "")) or not str(field.get("field_name", "")):
                raise ContractError(
                    f"environment inventory schema {schema_id} field {field_index} "
                    "requires field_id and field_name"
                )
    return {
        "schema_version": "bi-environment-inventory-validation/1.0",
        "valid": True,
        "environment": environment,
        "variable_count": len(variables),
        "schema_count": len(schemas),
    }


def load_inventory_snapshot(path: Path) -> dict[str, Any]:
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InputError(f"environment inventory is not valid JSON: {path}") from error
    if not isinstance(inventory, Mapping):
        raise ContractError("environment inventory must be an object")
    return dict(inventory)


def _schema_lookup(inventory: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for schema in inventory.get("schemas", []):
        if not isinstance(schema, Mapping):
            continue
        for key in ("schema_id", "schema_object", "describe_api_name", "schema_name"):
            value = str(schema.get(key, ""))
            if value and value not in lookup:
                lookup[value] = dict(schema)
    return lookup


def _field_lookup(schema: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for field in schema.get("fields", []):
        if not isinstance(field, Mapping):
            continue
        for key in ("field_id", "field_name", "db_field_name"):
            value = str(field.get(key, ""))
            if value and value not in lookup:
                lookup[value] = dict(field)
    return lookup


def resolve_variables_from_inventory(
    variables: Mapping[str, Any], inventory: Mapping[str, Any]
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve ``{{ ... }}`` variables from a snapshot.

    Resolution order is deterministic:
      1. inventory.variables for exact logical variable names;
      2. schema lookup by ``schema_id`` / ``schema_object`` / ``schema_name``;
      3. field lookup inside the resolved schema for ``*_field_id`` /
         ``*_db_field`` / ``*_field_type`` keys.
    Unresolvable keys are reported with mode ``runtime_required``.
    """
    resolved = {str(key): str(value) for key, value in variables.items()}
    modes: dict[str, str] = {}
    explicit = {
        str(key): str(value)
        for key, value in inventory.get("variables", {}).items()
        if isinstance(value, (str, int, float))
    }
    schema_lookup = _schema_lookup(inventory)
    selected_schema: dict[str, Any] | None = None
    for key, value in list(resolved.items()):
        if not isinstance(value, str) or not _VARIABLE.search(value):
            modes[key] = "static"
            continue
        if key in explicit and not _VARIABLE.search(explicit[key]):
            resolved[key] = explicit[key]
            modes[key] = "inventory"
            continue
        if key in {"schema_id", "schema_object", "schema_name", "describe_api_name"}:
            if key == "schema_id":
                candidate = schema_lookup.get(value) or (
                    next(iter(schema_lookup.values())) if schema_lookup else None
                )
            else:
                base = str(resolved.get("schema_id") or resolved.get("schema_object") or "")
                candidate = schema_lookup.get(base) if base else None
            if candidate is not None:
                resolved[key] = str(candidate.get(key, ""))
                modes[key] = "inventory"
                selected_schema = candidate
            else:
                modes[key] = "runtime_required"
            continue
        if selected_schema is None and str(resolved.get("schema_id", "")):
            selected_schema = schema_lookup.get(str(resolved["schema_id"]))
        match = re.fullmatch(r"(.+)_(field_id|db_field|field_type)$", key)
        if match and selected_schema is not None:
            prefix = match.group(1)
            field = next(
                (
                    item
                    for item in _field_lookup(selected_schema).values()
                    if prefix in str(item.get("field_name", ""))
                    or prefix in str(item.get("db_field_name", "")).lower()
                ),
                None,
            )
            if field is not None:
                attribute = {
                    "field_id": "field_id",
                    "db_field": "db_field_name",
                    "field_type": "field_type",
                }[match.group(2)]
                candidate_value = str(field.get(attribute, ""))
                if candidate_value:
                    resolved[key] = candidate_value
                    modes[key] = "inventory"
                    continue
        modes[key] = "runtime_required"
    return resolved, modes


def render_plan_variables(
    plan: Mapping[str, Any], resolved: Mapping[str, str]
) -> dict[str, Any]:
    """Render ``{{ variable }}`` placeholders inside a deep-copied plan."""
    rendered = deepcopy(dict(plan))
    context = {str(key): str(value) for key, value in resolved.items()}

    def replace(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        return str(context.get(name, match.group(0)))

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str):
            return _VARIABLE.sub(replace, value)
        return value

    return walk(rendered)


def enrich_plan_with_inventory(
    plan: Mapping[str, Any], inventory: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve case-plan variables from the inventory and render the plan."""
    validate_inventory_snapshot(inventory)
    enriched = deepcopy(dict(plan))
    case_resolutions: list[dict[str, Any]] = []
    for case_plan in enriched.get("case_plans", []):
        if not isinstance(case_plan, Mapping):
            continue
        variables = case_plan.get("variables", {})
        if not isinstance(variables, Mapping):
            continue
        resolved, modes = resolve_variables_from_inventory(variables, inventory)
        case_plan["variables"] = resolved
        for resource in case_plan.get("resources", []):
            if not isinstance(resource, Mapping):
                continue
            for phase in ("setup", "readiness", "cleanup"):
                step = resource.get(phase)
                if isinstance(step, Mapping):
                    resource[phase] = render_plan_variables(step, resolved)
            residue = resource.get("residue_checks", [])
            if isinstance(residue, list):
                resource["residue_checks"] = [
                    render_plan_variables(item, resolved) if isinstance(item, Mapping) else item
                    for item in residue
                ]
        case_resolutions.append(
            {
                "case_id": str(case_plan.get("case_id", "")),
                "variables": resolved,
                "modes": modes,
            }
        )
    enriched["inventory_resolution"] = {
        "schema_version": "test-data-inventory-resolution/1.0",
        "environment": str(inventory.get("environment", "")),
        "case_resolutions": case_resolutions,
        "runtime_required": sorted(
            {
                key
                for case in case_resolutions
                for key, mode in case["modes"].items()
                if mode == "runtime_required"
            }
        ),
    }
    return enriched

