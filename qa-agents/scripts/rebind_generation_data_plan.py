#!/usr/bin/env python3
"""Rebind reviewed executable candidates to the current A22 lifecycle plan."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from qa_agents.contracts import artifact_hash_from_mapping, content_hash
from qa_agents.test_data import bind_plan_to_case


def _case_spec(content: str) -> tuple[dict, int, int, dict[str, object]]:
    marker = "CASE_SPEC=" if "CASE_SPEC=" in content else "CASE_SPEC = "
    start = content.index(marker) + len(marker)
    end = content.index("\ndef test_", start)
    namespace: dict[str, object] = {}
    exec(content[:end], {"__builtins__": {}}, namespace)
    spec = namespace.get("CASE_SPEC")
    if not isinstance(spec, dict):
        raise TypeError("candidate CASE_SPEC must be a mapping")
    return spec, start, end, namespace


def _preserve_candidate_asset_bindings(
    spec: dict, module_values: dict[str, object]
) -> dict:
    """Carry generator-owned retained fixture constants into CASE_SPEC."""

    variables = dict(spec.get("variables") or {})
    if re.fullmatch(r"BI_[^\"']+", str(variables.get("chart_view_id", ""))):
        variables.pop("chart_view_id", None)
    aliases = {
        "schema_id": "SID",
        "metric_field_id": "FID",
        "field_id": "FID",
    }
    content = json.dumps(spec, ensure_ascii=False)
    for variable, alias in aliases.items():
        marker = "{{" + variable + "}}"
        spaced_marker = "{{ " + variable + " }}"
        value = module_values.get(alias)
        if (marker in content or spaced_marker in content) and variable not in variables:
            if isinstance(value, (str, int, float, bool)) and str(value).strip():
                variables[variable] = value
    if variables:
        spec["variables"] = variables
    return spec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--a22-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact = json.loads(args.generation.read_text(encoding="utf-8"))
    plan_artifact = json.loads(args.a22_plan.read_text(encoding="utf-8"))
    plan = plan_artifact["payload"]
    hashes: dict[str, str] = {}
    for candidate in artifact["payload"]["code_candidates"]:
        content = str(candidate["content"])
        spec, start, end, module_values = _case_spec(content)
        spec = _preserve_candidate_asset_bindings(spec, module_values)
        bound = bind_plan_to_case(spec, plan)
        candidate["content"] = content[:start] + repr(bound) + content[end:]
        candidate["content_hash"] = content_hash(candidate["content"])
        hashes[str(candidate["path"])] = candidate["content_hash"]
    for item in artifact["payload"]["manifest"]["candidate_files"]:
        item["content_hash"] = hashes[str(item["path"])]
    bindings = artifact["payload"]["manifest"].setdefault("input_bindings", {})
    bindings["test_data_resource_plan_hash"] = plan_artifact["artifact_hash"]
    artifact["artifact_hash"] = artifact_hash_from_mapping(artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
