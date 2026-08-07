"""N26 deterministic Case selection and N15 execution-plan compilation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def select_cases(
    cases: list[Mapping[str, Any]],
    asset_catalog: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assets = asset_catalog or {}
    automation_assets = assets.get("automation_assets", {})
    selected: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for case in sorted(cases, key=lambda item: str(item.get("id", ""))):
        case_id = str(case["id"])
        linked = automation_assets.get(case_id)
        if linked is None:
            selection = "must_run"
            reason_code = "new_case_without_automation"
        elif not isinstance(linked, Mapping):
            selection = "needs_human"
            reason_code = "invalid_asset_mapping"
            unresolved.append({"case_id": case_id, "reason_code": reason_code})
        elif linked.get("status") == "active" and not linked.get("impacted", False):
            selection = "must_run"
            reason_code = "active_existing_automation"
        else:
            selection = "must_run"
            reason_code = "automation_requires_update"
        selected.append(
            {
                "case_id": case_id,
                "selection": selection,
                "reason_code": reason_code,
                "evidence": [f"test-case:{case_id}"],
            }
        )
    return {
        "schema_version": "test-selection/1.0",
        "selected_cases": selected,
        "unresolved_items": unresolved,
    }


def compile_execution_plan(
    selection: Mapping[str, Any],
    cases: list[Mapping[str, Any]],
    asset_catalog: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assets = (asset_catalog or {}).get("automation_assets", {})
    cases_by_id = {str(case["id"]): case for case in cases}
    actions: list[dict[str, Any]] = []
    for item in selection.get("selected_cases", []):
        case_id = str(item["case_id"])
        case = cases_by_id[case_id]
        asset = assets.get(case_id)
        if item["selection"] == "needs_human":
            action = "manual_run"
        elif asset is None:
            action = "generate_new" if case.get("automation_candidate") else "manual_run"
        elif asset.get("status") == "active" and not asset.get("impacted", False):
            action = "run_existing"
        else:
            action = "update_existing"
        actions.append(
            {
                "case_id": case_id,
                "action": action,
                "reason_code": item["reason_code"],
                "automation_ref": asset.get("commit") if isinstance(asset, Mapping) else None,
            }
        )
    return {"schema_version": "execution-plan/1.0", "actions": actions}
