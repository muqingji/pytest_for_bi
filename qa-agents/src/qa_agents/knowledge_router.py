"""Deterministic routing for BI source-code and product-document knowledge."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import subprocess
from typing import Any

from .errors import ContractError, InputError, SecurityPolicyError
from .skill_registry import SkillRegistry


PURPOSE_AGENTS = {
    "requirement_analysis": "A03",
    "historical_knowledge": "K01",
    "test_case": "A08",
    "test_data": "A22",
}
DOCUMENT_TERMS = ("产品说明", "操作说明", "帮助文档", "白皮书", "乐享", "wps", "kdocs", "历史产品规则")


def load_knowledge_catalog(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Knowledge catalog is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Knowledge catalog is invalid: {path}") from error
    if value.get("schema_version") != "bi-repository-knowledge-catalog/1.0":
        raise ContractError("Knowledge catalog schema_version is invalid")
    return value


def _head(path: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"], check=True, capture_output=True,
            text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def route_knowledge_query(
    query: str, *, purpose: str, catalog: Mapping[str, Any], registry: SkillRegistry,
    check_freshness: bool = True,
) -> dict[str, Any]:
    if purpose not in PURPOSE_AGENTS:
        raise InputError(f"Unsupported knowledge purpose: {purpose}")
    normalized = query.casefold().strip()
    if not normalized:
        raise InputError("Knowledge query must not be empty")

    matches: list[dict[str, Any]] = []
    domains: list[str] = []
    for repository in catalog.get("repositories", []):
        if not isinstance(repository, Mapping):
            continue
        terms = [str(term) for term in repository.get("route_terms", [])]
        hit = [term for term in terms if term.casefold() in normalized]
        if not hit:
            continue
        skill = str(repository.get("skill", ""))
        if not skill or skill not in registry.skills:
            raise SecurityPolicyError(f"Repository source is not published: {repository.get('id')}")
        expected = str(repository.get("verified_commit", ""))
        actual = _head(str(repository.get("local_checkout", ""))) if check_freshness else expected
        freshness = "current" if actual == expected else ("unavailable" if actual is None else "stale")
        domain = str(repository.get("domain", ""))
        if domain not in domains:
            domains.append(domain)
        matches.append({
            "source_id": str(repository.get("id", "")), "skill_id": skill,
            "domain": domain, "matched_terms": hit, "freshness": freshness,
            "verified_commit": expected, "current_commit": actual,
        })

    document_match = any(term.casefold() in normalized for term in DOCUMENT_TERMS)
    skill_ids = ["bi-knowledge-router", *[item["skill_id"] for item in matches]]
    if document_match:
        skill_ids.append("bi-product-docs-router")
        domains.append("product_document")
    if len(skill_ids) == 1:
        raise InputError("Knowledge query did not match a registered source")

    agent_id = PURPOSE_AGENTS[purpose]
    refs = registry.refs(list(dict.fromkeys(skill_ids)), agent_id)
    return {
        "schema_version": "knowledge-routing/1.0", "purpose": purpose,
        "agent_id": agent_id, "query": query, "matched_domains": domains,
        "repositories": matches, "document_router_required": document_match,
        "required_skills": refs, "authority_order": list(catalog.get("authority_order", [])),
        "allowed_tools": sorted({tool for skill in skill_ids for tool in registry.skills[skill].get("tools", [])}),
        "registry_hash": registry.registry_hash,
    }
