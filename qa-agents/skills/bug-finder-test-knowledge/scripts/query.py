#!/usr/bin/env python3
"""Produce a bounded, provenance-bound view of bug-finder knowledge."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


DEFAULT_REPOSITORY = Path("/Users/liushanshan/code/QA/bug-finder")
EXCLUDED_PARTS = {"output", "tmp", ".git", "node_modules", "scripts", "assets"}


def _revision(repository: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _allowed(relative: Path) -> bool:
    value = relative.as_posix()
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if value.startswith("docs/knowledge/"):
        return True
    return value.startswith(".agents/skills/") and "/references/" in value


def _classify(relative: Path) -> tuple[str, str]:
    value = relative.as_posix().lower()
    if "bug" in value or "failure" in value or value.startswith("docs/knowledge/"):
        return "historical_risk", "expand_risk_scenarios"
    return "diagnostic_pattern", "inform_domain_workflow_analysis"


def query(
    repository: Path, keywords: list[str], domains: list[str], limit: int
) -> dict[str, object]:
    if not (repository / ".git").exists():
        raise ValueError("bug-finder repository is unavailable")
    normalized_keywords = [term.casefold() for term in keywords if term.strip()]
    normalized_domains = [term.casefold() for term in domains if term.strip()]
    if not normalized_keywords:
        raise ValueError("at least one keyword is required")

    matches: list[dict[str, object]] = []
    for path in sorted(repository.rglob("*.md")):
        relative = path.relative_to(repository)
        if not _allowed(relative):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_number, line in enumerate(lines, 1):
            folded = line.casefold()
            if not any(term in folded for term in normalized_keywords):
                continue
            domain_match = not normalized_domains or any(
                term in folded or term in relative.as_posix().casefold()
                for term in normalized_domains
            )
            knowledge_class, allowed_use = _classify(relative)
            excerpt = line.strip()[:500]
            matches.append(
                {
                    "knowledge_class": knowledge_class,
                    "allowed_test_use": allowed_use,
                    "path": relative.as_posix(),
                    "line": line_number,
                    "excerpt": excerpt,
                    "content_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                    "authority": "historical_context_only",
                    "domain_match": domain_match,
                }
            )
    matches.sort(
        key=lambda item: (
            not item["domain_match"],
            item["knowledge_class"] != "historical_risk",
            item["path"],
            item["line"],
        )
    )
    matches = matches[:limit]

    return {
        "schema_version": "bug-finder-test-knowledge-evidence/1.0",
        "provider_id": "bug-finder",
        "repository": str(repository.resolve()),
        "revision": _revision(repository),
        "query": {"keywords": keywords, "domains": domains, "limit": limit},
        "matches": matches,
        "contract_authority": False,
        "required_corroboration": [
            "current_product_documentation",
            "current_code_or_openapi",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", action="append", required=True)
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 200:
        parser.error("--limit must be between 1 and 200")
    artifact = query(args.repository.resolve(), args.keyword, args.domain, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
