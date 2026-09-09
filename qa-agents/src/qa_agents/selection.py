"""N26 deterministic Case selection, A12 advice validation and N15 plan compilation.

N26 merges policy-forced cases, affected stored automation and impact evidence
into a deterministic selection.  Only impact relationships that the rules
cannot resolve (missing call graph, cross-repo conflict, uncertain asset
mapping) are delegated to A12 as ``unresolved_items``; A12 returns advice-only
``test-selection-advice`` payloads that N26 validates before folding.  A12 can
expand or escalate scope but can never shrink, skip or downgrade a
policy-forced Case, and the final collection is always computed by N26.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import ContractError, SecurityPolicyError


SELECTION_VALUES = {"must_run", "recommended", "skip", "needs_human"}
ADVISORY_TOPICS = {
    "missing_call_graph",
    "cross_repo_impact_conflict",
    "uncertain_asset_mapping",
    "invalid_asset_mapping",
}
ADVICE_RECOMMENDATIONS = {"expand_selection", "keep_must_run", "request_human"}
EXPANDED_SCOPE_RULE_ID = "A12-ADVICE-VALIDATED"


def _asset_for_case(
    assets: Mapping[str, Any], case_id: str
) -> tuple[Any | None, bool]:
    """Resolve an asset by canonical Case id or an explicit audited alias."""
    if case_id in assets:
        return assets[case_id], False
    matches = [
        asset
        for asset in assets.values()
        if isinstance(asset, Mapping)
        and case_id in {str(alias) for alias in asset.get("case_aliases", [])}
    ]
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


def _rule_matches(rule: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    case_id = str(case.get("id", ""))
    layer = str(case.get("layer", ""))
    case_ids = rule.get("case_ids")
    layers = rule.get("layers")
    if isinstance(case_ids, list) and case_id in {str(item) for item in case_ids}:
        return True
    if isinstance(layers, list) and layer in {str(item) for item in layers}:
        return True
    return rule.get("scope") == "all"


def _first_matching(
    rules: list[Mapping[str, Any]], case: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    for rule in rules:
        if isinstance(rule, Mapping) and _rule_matches(rule, case):
            return rule
    return None


def _forced_must_run(
    case: Mapping[str, Any], policy: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    for rule in policy.get("forced_selection", []):
        if (
            isinstance(rule, Mapping)
            and rule.get("selection") == "must_run"
            and _rule_matches(rule, case)
        ):
            return rule
    return None


def select_cases(
    cases: list[Mapping[str, Any]],
    asset_catalog: Mapping[str, Any] | None = None,
    *,
    selection_policy: Mapping[str, Any] | None = None,
    change_set: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select the final test set with deterministic rules and bounded A12 scope.

    Rules are evaluated in order: policy-forced ``must_run``, approved
    ``skip``, then automation-asset state with impact-confidence resolution.
    Unresolvable impact relationships are kept in ``unresolved_items`` with an
    ``advisory_topic``; the Case itself stays ``must_run`` so the scope never
    silently shrinks.
    """

    assets = (asset_catalog or {}).get("automation_assets", {})
    impact_evidence = (asset_catalog or {}).get("impact_evidence", {})
    policy = selection_policy or {}
    skip_rules = [rule for rule in policy.get("skip_selection", []) if isinstance(rule, Mapping)]
    selected: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for case in sorted(cases, key=lambda item: str(item.get("id", ""))):
        case_id = str(case["id"])
        evidence = [f"test-case:{case_id}"]
        forced = _forced_must_run(case, policy)
        if forced is not None:
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "must_run",
                    "reason_code": "policy_forced",
                    "rule_id": str(forced.get("rule_id", "")),
                    "evidence": evidence,
                }
            )
            continue
        skip_rule = _first_matching(skip_rules, case)
        if skip_rule is not None and skip_rule.get("approved") is True:
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "skip",
                    "reason_code": "policy_skip_approved",
                    "rule_id": str(skip_rule.get("rule_id", "")),
                    "evidence": evidence,
                }
            )
            continue

        linked, ambiguous = _asset_for_case(assets, case_id)
        if ambiguous:
            unresolved.append(
                {
                    "id": f"N26-U{len(unresolved) + 1:03d}",
                    "case_id": case_id,
                    "advisory_topic": "uncertain_asset_mapping",
                    "reason_code": "uncertain_asset_mapping",
                    "evidence": evidence,
                    "uncertainty": "多个存量自动化资产声明了同一 Case 别名。",
                }
            )
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "needs_human",
                    "reason_code": "uncertain_asset_mapping",
                    "evidence": evidence,
                }
            )
            continue
        if linked is None:
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "must_run",
                    "reason_code": "new_case_without_automation",
                    "evidence": evidence,
                }
            )
            continue
        if not isinstance(linked, Mapping):
            unresolved.append(
                {
                    "id": f"N26-U{len(unresolved) + 1:03d}",
                    "case_id": case_id,
                    "advisory_topic": "invalid_asset_mapping",
                    "reason_code": "invalid_asset_mapping",
                    "evidence": evidence,
                    "uncertainty": "存量资产映射不是结构化对象，无法确定自动化状态。",
                }
            )
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "needs_human",
                    "reason_code": "invalid_asset_mapping",
                    "evidence": evidence,
                }
            )
            continue
        if linked.get("status") == "active" and not linked.get("impacted", False):
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "must_run",
                    "reason_code": "active_existing_automation",
                    "evidence": evidence,
                }
            )
            continue

        impact = impact_evidence.get(case_id)
        if isinstance(impact, Mapping) and impact.get("cross_repo_conflict") is True:
            unresolved.append(
                {
                    "id": f"N26-U{len(unresolved) + 1:03d}",
                    "case_id": case_id,
                    "advisory_topic": "cross_repo_impact_conflict",
                    "reason_code": "cross_repo_impact_conflict",
                    "evidence": evidence + list(impact.get("evidence", [])),
                    "uncertainty": "跨仓库影响冲突，规则无法判定受影响范围。",
                }
            )
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "must_run",
                    "reason_code": "cross_repo_impact_conflict",
                    "evidence": evidence,
                }
            )
            continue
        if isinstance(impact, Mapping) and impact.get("confidence") == "medium":
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "recommended",
                    "reason_code": "impact_evidence_medium_confidence",
                    "rule_id": "impact-evidence-medium-confidence",
                    "evidence": evidence + list(impact.get("evidence", [])),
                }
            )
            continue
        if not isinstance(impact, Mapping) or impact.get("confidence") == "low":
            unresolved.append(
                {
                    "id": f"N26-U{len(unresolved) + 1:03d}",
                    "case_id": case_id,
                    "advisory_topic": "missing_call_graph",
                    "reason_code": "missing_call_graph",
                    "evidence": evidence,
                    "uncertainty": "缺少代码调用关系证据，受影响范围不确定。",
                }
            )
            selected.append(
                {
                    "case_id": case_id,
                    "selection": "must_run",
                    "reason_code": "missing_call_graph",
                    "evidence": evidence,
                }
            )
            continue
        selected.append(
            {
                "case_id": case_id,
                "selection": "must_run",
                "reason_code": "automation_requires_update",
                "rule_id": "impact-evidence-high-confidence",
                "evidence": evidence + list(impact.get("evidence", [])),
            }
        )
    return {
        "schema_version": "test-selection/1.0",
        "selected_cases": selected,
        "unresolved_items": unresolved,
    }


def _unresolved_index(
    unresolved: list[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[tuple[str, str], Mapping[str, Any]]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in unresolved:
        item_id = str(item.get("id", ""))
        if item_id:
            by_id[item_id] = item
        key = (str(item.get("case_id", "")), str(item.get("advisory_topic", "")))
        by_key[key] = item
    return by_id, by_key


def apply_selection_advice(
    selection: Mapping[str, Any],
    advice: Mapping[str, Any],
    cases: list[Mapping[str, Any]],
    *,
    selection_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fold validated A12 advice into the N26 selection.

    A12 can only expand scope or escalate to a human; it cannot skip, remove or
    downgrade a policy-forced Case.  Unresolved items without advice remain
    unresolved so the scope never silently shrinks.
    """

    if not isinstance(advice, Mapping):
        raise ContractError("A12 advice must be an object")
    if advice.get("schema_version") != "test-selection-advice/1.0":
        raise ContractError("A12 advice schema_version is invalid")
    unresolved = selection.get("unresolved_items", [])
    if not isinstance(unresolved, list):
        raise ContractError("N26 selection unresolved_items are invalid")
    if not unresolved:
        return {
            "schema_version": "test-selection/1.0",
            "selected_cases": list(selection.get("selected_cases", [])),
            "unresolved_items": [],
            "advice": {
                "advice_item_count": 0,
                "applied_count": 0,
                "unresolved_after_advice": 0,
            },
        }
    policy = selection_policy or {}
    known_case_ids = {str(item.get("id", "")) for item in cases}
    by_id, by_key = _unresolved_index(unresolved)
    selected_by_case = {
        str(item.get("case_id", "")): dict(item)
        for item in selection.get("selected_cases", [])
        if isinstance(item, Mapping)
    }
    advice_items = advice.get("advice_items")
    if not isinstance(advice_items, list):
        raise ContractError("A12 advice_items must be a list")
    advised: set[str] = set()
    for index, item in enumerate(advice_items):
        if not isinstance(item, Mapping):
            raise ContractError(f"A12 advice_items[{index}] must be an object")
        recommendation = item.get("recommendation")
        if recommendation not in ADVICE_RECOMMENDATIONS:
            raise ContractError(f"A12 advice_items[{index}] has an invalid recommendation")
        if item.get("unresolved_item_id"):
            target = by_id.get(str(item.get("unresolved_item_id", "")))
        else:
            target = by_key.get(
                (str(item.get("case_id", "")), str(item.get("advisory_topic", "")))
            )
        if target is None:
            raise ContractError(
                f"A12 advice_items[{index}] references an unknown unresolved item"
            )
        target_case_id = str(target.get("case_id", ""))
        if item.get("case_id") and str(item["case_id"]) != target_case_id:
            raise ContractError(
                f"A12 advice_items[{index}] case_id does not match its unresolved item"
            )
        suggested = set(map(str, item.get("suggested_case_ids", [])))
        if not suggested <= known_case_ids:
            raise ContractError(
                f"A12 advice_items[{index}] suggests an unknown Case"
            )
        if recommendation == "expand_selection":
            for suggested_id in suggested:
                current = selected_by_case.get(suggested_id)
                if current is None or current["selection"] == "recommended":
                    selected_by_case[suggested_id] = {
                        "case_id": suggested_id,
                        "selection": "must_run",
                        "reason_code": "a12_expanded_scope",
                        "rule_id": EXPANDED_SCOPE_RULE_ID,
                        "evidence": [
                            *list(item.get("evidence", [])),
                            f"unresolved:{target.get('id', '')}",
                        ],
                    }
        elif recommendation == "request_human":
            target_case = next(
                (case for case in cases if str(case.get("id", "")) == target_case_id),
                {},
            )
            if _forced_must_run(target_case, policy) is not None:
                raise SecurityPolicyError(
                    "A12 cannot downgrade a policy-forced Case to human"
                )
            current = selected_by_case.get(target_case_id)
            if current is not None and current["selection"] != "skip":
                current["selection"] = "needs_human"
                current["reason_code"] = "a12_advice_request_human"
        advised.add(str(target.get("id", "")) or target_case_id)
    remaining = [
        item for item in unresolved if str(item.get("id", "")) not in advised
    ]
    selected = sorted(selected_by_case.values(), key=lambda item: str(item["case_id"]))
    return {
        "schema_version": "test-selection/1.0",
        "selected_cases": selected,
        "unresolved_items": remaining,
        "advice": {
            "advice_item_count": len(advice_items),
            "applied_count": len(advised),
            "unresolved_after_advice": len(remaining),
        },
    }


def compile_execution_plan(
    selection: Mapping[str, Any],
    cases: list[Mapping[str, Any]],
    asset_catalog: Mapping[str, Any] | None = None,
    *,
    deferred_layers: set[str] | None = None,
    skip_layers: set[str] | None = None,
) -> dict[str, Any]:
    assets = (asset_catalog or {}).get("automation_assets", {})
    cases_by_id = {str(case["id"]): case for case in cases}
    actions: list[dict[str, Any]] = []
    deferred = set(deferred_layers or ())
    skipped = set(skip_layers or ())
    for item in selection.get("selected_cases", []):
        case_id = str(item["case_id"])
        case = cases_by_id[case_id]
        asset, ambiguous = _asset_for_case(assets, case_id)
        if ambiguous:
            asset = None
        test_level = str(case.get("test_level", "") or "").strip().lower()
        layer = str(case.get("layer", "")).strip().lower()
        if layer in skipped:
            action = "skip"
            reason_code = f"{layer}_capability_not_ready"
        elif layer in deferred:
            action = "deferred_frontend" if layer in {"frontend", "e2e"} else "deferred_by_policy"
            reason_code = f"{layer}_scope_deferred_by_policy"
        elif test_level in {"unit", "unit_test", "单元", "单元测试"}:
            action = "skip"
            reason_code = "paused_existing_developer_unit_coverage"
        elif item["selection"] == "skip":
            action = "skip"
            reason_code = item["reason_code"]
        elif item["selection"] == "needs_human":
            action = "manual_run"
            reason_code = item["reason_code"]
        elif asset is None:
            action = "generate_new" if case.get("automation_candidate") else "manual_run"
            reason_code = item["reason_code"]
        elif asset.get("status") == "active" and not asset.get("impacted", False):
            action = "run_existing"
            reason_code = item["reason_code"]
        else:
            action = "update_existing"
            reason_code = item["reason_code"]
        actions.append(
            {
                "case_id": case_id,
                "action": action,
                "reason_code": reason_code,
                "automation_ref": asset.get("commit") if isinstance(asset, Mapping) else None,
            }
        )
    return {"schema_version": "execution-plan/1.0", "actions": actions}
