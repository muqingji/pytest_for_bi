"""Agent work-card contracts used by Multica Issue rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .errors import ContractError


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "policies" / "agent-work-card-registry.json"
REQUIRED_FIELDS = (
    "goal",
    "background",
    "responsibilities",
    "in_scope",
    "out_of_scope",
    "deliverables",
    "acceptance",
)


def load_agent_work_card_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    agents = value.get("agents")
    if value.get("schema_version") != "agent-work-card-registry/1.0" or not isinstance(agents, dict):
        raise ContractError("Agent work-card registry contract is invalid")
    for agent_id, card in agents.items():
        if not isinstance(card, Mapping):
            raise ContractError(f"Agent work card {agent_id} must be an object")
        missing = [field for field in REQUIRED_FIELDS if not card.get(field)]
        if missing:
            raise ContractError(f"Agent work card {agent_id} misses: {', '.join(missing)}")
    return value


def get_agent_work_card(agent_id: str) -> Mapping[str, Any]:
    agents = load_agent_work_card_registry()["agents"]
    try:
        return agents[agent_id]
    except KeyError as error:
        raise ContractError(f"Agent {agent_id} has no work-card definition") from error


def review_items(artifact: Mapping[str, Any], card: Mapping[str, Any]) -> list[str]:
    questions = artifact.get("blocking_questions", [])
    items = [
        str(item.get("question") or item.get("message") or item)
        for item in questions
        if isinstance(item, Mapping)
    ]
    payload = artifact.get("payload", {})
    if artifact.get("status") == "needs_human":
        items.extend(str(item) for item in card.get("review_when_needed", []))
    if isinstance(payload, Mapping) and payload.get("approved") is False:
        items.extend(str(item) for item in card.get("review_when_needed", []))
    return list(dict.fromkeys(item for item in items if item.strip()))
