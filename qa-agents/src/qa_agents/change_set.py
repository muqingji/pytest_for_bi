"""N01 ChangeSet normalization with deterministic diff baselines."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import content_hash
from .errors import InputError


def normalize_change_set(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    source = snapshot.get("implementation_source")
    if not isinstance(source, Mapping):
        raise InputError("source_snapshot.implementation_source is required")

    repository_id = str(source.get("repository_id", "")).strip()
    head = str(source.get("commit", "")).strip()
    kind = str(source.get("commit_kind", "single")).strip()
    parents = [str(item) for item in source.get("parents", [])]
    comparison = source.get("comparison", {})
    if not isinstance(comparison, Mapping):
        raise InputError("implementation_source.comparison must be an object")

    mode = str(comparison.get("mode", "")).strip()
    base = str(comparison.get("base", "")).strip()
    comparison_head = str(comparison.get("head", head)).strip()
    if not repository_id or not head or not base:
        raise InputError("repository_id, commit and comparison.base are required")
    if comparison_head != head:
        raise InputError("comparison.head must equal implementation commit")

    if kind == "merge":
        if len(parents) < 2:
            raise InputError("merge commit must declare at least two parents")
        if mode != "first_parent" or base != parents[0]:
            raise InputError("merge commit must use first-parent baseline")
        change_kind = "merge_commit"
    else:
        if parents and base != parents[0]:
            raise InputError("single commit baseline must be its first parent")
        if mode not in {"first_parent", "explicit_range", "merge_base"}:
            raise InputError(f"unsupported diff mode: {mode}")
        change_kind = "single_commit"

    summary = source.get("change_summary", {})
    changed_files = list(summary.get("changed_paths", [])) if isinstance(summary, Mapping) else []
    diff_identity = {
        "repository_id": repository_id,
        "base_commit": base,
        "head_commit": head,
        "diff_mode": mode,
        "changed_files": changed_files,
    }
    return {
        "schema_version": "change-set/1.0",
        "change_set_id": f"changeset-{repository_id}-{head[:12]}",
        "repository_id": repository_id,
        "repository": source.get("repository"),
        "access_class": source.get("access_class"),
        "change_kind": change_kind,
        "source_ref": head,
        "base_commit": base,
        "head_commit": head,
        "parents": parents,
        "diff_mode": mode,
        "changed_files": changed_files,
        "summary": dict(summary) if isinstance(summary, Mapping) else {},
        "diff_hash": content_hash(diff_identity),
    }
