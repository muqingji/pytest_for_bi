"""Validated historical-behavior evidence for test design and review."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import content_hash
from .errors import ContractError


def validate_historical_behavior_packet(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != "historical-behavior-packet/1.0":
        raise ContractError("Historical behavior packet schema_version is invalid")
    behaviors, sources = value.get("behaviors"), value.get("sources")
    if not isinstance(behaviors, list) or not behaviors:
        raise ContractError("Historical behavior packet has no behaviors")
    if not isinstance(sources, list) or not sources:
        raise ContractError("Historical behavior packet has no sources")
    source_ids = {str(item.get("id", "")) for item in sources if isinstance(item, Mapping)}
    for index, behavior in enumerate(behaviors):
        if not isinstance(behavior, Mapping):
            raise ContractError(f"Historical behavior[{index}] must be an object")
        for field in ("id", "module", "scenario", "expected_behavior"):
            if not str(behavior.get(field, "")).strip():
                raise ContractError(f"Historical behavior[{index}] requires {field}")
        refs = set(map(str, behavior.get("source_refs", [])))
        if not refs or not refs <= source_ids:
            raise ContractError(f"Historical behavior[{index}] has invalid source_refs")
    unhashed = {key: item for key, item in value.items() if key != "packet_hash"}
    if value.get("packet_hash") != content_hash(unhashed):
        raise ContractError("Historical behavior packet_hash is invalid")
    return dict(value)


def assert_historical_regression_coverage(
    payload: Mapping[str, Any], packet: Mapping[str, Any]
) -> None:
    required = {str(item["id"]) for item in packet["behaviors"]}
    covered: set[str] = set()
    for case in payload.get("parent_cases", []):
        if isinstance(case, Mapping):
            covered.update(map(str, case.get("historical_behavior_refs", [])))
    missing = sorted(required - covered)
    if missing:
        raise ContractError(
            "A08 does not cover historical normal behaviors: " + ", ".join(missing)
        )
