"""A19 local failure triage for clusters N09 could not classify."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .contracts import ArtifactStatus, content_hash


_ENV_MARKERS = re.compile(
    r"(connection refused|timed out|timeout|dns|temporary failure|"
    r"service unavailable|bad gateway|dependency|environment)",
    re.IGNORECASE,
)
_AUTO_MARKERS = re.compile(
    r"(importerror|modulenotfounderror|syntaxerror|fixture|locator|"
    r"selector|no such file|attributeerror|nameerror|typeerror)",
    re.IGNORECASE,
)
_PRODUCT_MARKERS = re.compile(
    r"(assertionerror|assert |expected|did not match|status code|"
    r"oracle|business rule)",
    re.IGNORECASE,
)
_DATA_MARKERS = re.compile(
    r"(test data|fixture data|namespace|not found id|stale id|missing metric)",
    re.IGNORECASE,
)
_AMBIGUITY_MARKERS = re.compile(
    r"(ambiguous|undefined expected|requirement does not|not specified)",
    re.IGNORECASE,
)


def _classify_summary(summary: str) -> tuple[str, str, float]:
    text = summary or ""
    if _AMBIGUITY_MARKERS.search(text):
        return "requirement_ambiguity", "summary_matches_requirement_ambiguity", 0.72
    if _ENV_MARKERS.search(text):
        return "environment", "summary_matches_environment_marker", 0.8
    if _DATA_MARKERS.search(text):
        return "test_data", "summary_matches_test_data_marker", 0.75
    if _AUTO_MARKERS.search(text):
        return "automation_defect", "summary_matches_automation_marker", 0.78
    if _PRODUCT_MARKERS.search(text):
        return "product_defect", "summary_matches_product_marker", 0.7
    return "needs_triage", "insufficient_evidence_for_local_triage", 0.0


def run_a19_failure_triage(
    clusters: Sequence[Mapping[str, Any]],
    *,
    min_confidence: float = 0.7,
) -> dict[str, Any]:
    """Deterministic local A19 profile for needs_triage clusters.

    Only rewrites a cluster when a single rule-based classification clears the
    confidence floor. Everything else stays needs_human.
    """

    decisions: list[dict[str, Any]] = []
    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            continue
        if cluster.get("classification") != "needs_triage":
            continue
        summary = str(cluster.get("summary", ""))
        classification, rule, confidence = _classify_summary(summary)
        disposition = (
            "reclassified"
            if classification != "needs_triage" and confidence >= min_confidence
            else "needs_human"
        )
        decisions.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "fingerprint": cluster.get("fingerprint"),
                "input_classification": "needs_triage",
                "output_classification": (
                    classification if disposition == "reclassified" else "needs_triage"
                ),
                "disposition": disposition,
                "confidence": confidence,
                "rule": rule,
                "route_to": {
                    "product_defect": "N20",
                    "automation_defect": "G04",
                    "test_data": "N16",
                    "environment": "N10",
                    "requirement_ambiguity": "G01",
                    "needs_triage": "human",
                }[classification if disposition == "reclassified" else "needs_triage"],
            }
        )

    reclassified = {
        item["cluster_id"]: item
        for item in decisions
        if item["disposition"] == "reclassified"
    }
    updated_clusters: list[dict[str, Any]] = []
    for cluster in clusters:
        item = dict(cluster)
        decision = reclassified.get(item.get("cluster_id"))
        if decision is not None:
            item["classification"] = decision["output_classification"]
            item["route_to"] = decision["route_to"]
            item["triage"] = {
                "agent": "A19",
                "profile": "local-conservative/1.0.0",
                "confidence": decision["confidence"],
                "rule": decision["rule"],
            }
        updated_clusters.append(item)

    payload = {
        "schema_version": "a19-failure-triage/1.0",
        "profile": "local-conservative/1.0.0",
        "min_confidence": min_confidence,
        "input_cluster_count": sum(
            1 for item in clusters if item.get("classification") == "needs_triage"
        ),
        "decisions": decisions,
        "reclassified_count": sum(item["disposition"] == "reclassified" for item in decisions),
        "needs_human_count": sum(item["disposition"] == "needs_human" for item in decisions),
        "updated_clusters": updated_clusters,
        "status": (
            ArtifactStatus.COMPLETED.value
            if decisions and all(item["disposition"] == "reclassified" for item in decisions)
            else (
                ArtifactStatus.COMPLETED_WITH_GAPS.value
                if decisions
                else ArtifactStatus.NOT_APPLICABLE.value
            )
        ),
    }
    payload["triage_hash"] = content_hash(
        {
            "decisions": decisions,
            "updated_clusters": [
                {
                    "cluster_id": item.get("cluster_id"),
                    "classification": item.get("classification"),
                    "route_to": item.get("route_to"),
                }
                for item in updated_clusters
            ],
        }
    )
    return payload
