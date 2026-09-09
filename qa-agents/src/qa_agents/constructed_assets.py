"""Categorized display of test assets actually constructed in 112.

Implements the constructed-asset-card-display skill: task cards must list
successfully created charts/reports/metrics in Chinese, never as JSON paths.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "constructed-test-assets/1.0"
INVENTORY_FILENAME = "constructed-test-assets.json"
EVIDENCE_FILENAME = "constructed-assets.json"

REQUIRED_CATEGORIES = (
    "统计图",
    "报表",
    "交叉表",
    "驾驶舱",
    "指标",
    "自定义维度",
)
OPTIONAL_CATEGORIES = ("拼表", "其他")

RESOURCE_TYPE_TO_CATEGORY = {
    "stat_chart": "统计图",
    "report": "报表",
    "pivot_table": "交叉表",
    "pivot": "交叉表",
    "dashboard": "驾驶舱",
    "aggregate_metric": "指标",
    "ordinary_metric": "指标",
    "calculated_metric": "指标",
    "comparison_metric": "指标",
    "custom_dimension": "自定义维度",
    "joined_table": "拼表",
    "joined_report": "拼表",
}


def category_for_resource_type(resource_type: str) -> str:
    return RESOURCE_TYPE_TO_CATEGORY.get(str(resource_type or "").strip(), "其他")


def normalize_constructed_asset(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    resource_type = str(
        raw.get("resource_type") or raw.get("type") or ""
    ).strip()
    display_name = str(raw.get("display_name") or raw.get("name") or "").strip()
    resource_id = str(raw.get("resource_id") or raw.get("id") or "").strip()
    if not resource_type and not display_name and not resource_id:
        return None
    asset = {
        "resource_type": resource_type or "unknown",
        "display_name": display_name,
        "resource_id": resource_id,
        "folder_name": str(raw.get("folder_name") or raw.get("directory") or "").strip(),
        "subject": str(raw.get("subject") or "").strip(),
        "case_id": str(raw.get("case_id") or "").strip(),
        "resource_key": str(raw.get("resource_key") or raw.get("key") or "").strip(),
        "title": str(raw.get("title") or "").strip(),
    }
    if isinstance(raw.get("integrity_probes"), list):
        asset["integrity_probes"] = list(raw["integrity_probes"])
    if raw.get("status"):
        asset["status"] = str(raw["status"])
    from .asset_scene_naming import scene_display_name

    scene_name = scene_display_name(
        resource_type=asset["resource_type"],
        resource_key=asset["resource_key"],
        case_id=asset["case_id"],
        title=asset["title"],
        existing_name=asset["display_name"],
        allow_type_fallback=False,
    )
    if scene_name:
        asset["display_name"] = scene_name
    return asset


def _dedupe_assets(assets: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    result: list[dict[str, str]] = []
    for item in assets:
        resource_id = item.get("resource_id") or ""
        if resource_id:
            key = ("id", resource_id)
        else:
            key = (
                "fallback",
                item.get("resource_type") or "",
                item.get("display_name") or "",
                item.get("case_id") or "",
                item.get("resource_key") or "",
            )
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    return result


def _asset_line(asset: Mapping[str, str]) -> str:
    display_name = str(asset.get("display_name") or "").strip()
    resource_id = str(asset.get("resource_id") or "").strip()
    if display_name:
        line = f"- `{display_name}`"
    else:
        line = "- 未记录名称"
    if resource_id:
        line += f"（`{resource_id}`）"
    extras: list[str] = []
    folder_name = str(asset.get("folder_name") or "").strip()
    subject = str(asset.get("subject") or "").strip()
    if folder_name:
        extras.append(f"目录：{folder_name}")
    if subject:
        extras.append(f"主题：{subject}")
    if extras:
        line += " · " + "；".join(extras)
    return line


def render_constructed_assets_markdown(
    assets: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Render the 已构造测试数据 section. Empty inventory yields empty string."""

    from .asset_scene_naming import apply_scene_display_names

    normalized = [
        item
        for item in (_normalize_if_mapping(raw) for raw in assets or [])
        if item is not None
    ]
    normalized = apply_scene_display_names(_dedupe_assets(normalized))
    if not normalized:
        return ""
    grouped: dict[str, list[dict[str, str]]] = {name: [] for name in REQUIRED_CATEGORIES}
    optional: dict[str, list[dict[str, str]]] = {name: [] for name in OPTIONAL_CATEGORIES}
    for asset in normalized:
        category = category_for_resource_type(asset.get("resource_type") or "")
        if category in grouped:
            grouped[category].append(asset)
        else:
            optional.setdefault(category, []).append(asset)
    lines = ["## 已构造测试数据", ""]
    for category in REQUIRED_CATEGORIES:
        lines.append(f"### {category}")
        items = grouped[category]
        if not items:
            lines.append("- 无")
        else:
            lines.extend(_asset_line(item) for item in items)
        lines.append("")
    for category in OPTIONAL_CATEGORIES:
        items = optional.get(category) or []
        if not items:
            continue
        lines.append(f"### {category}")
        lines.extend(_asset_line(item) for item in items)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _normalize_if_mapping(raw: Any) -> dict[str, str] | None:
    return normalize_constructed_asset(raw) if isinstance(raw, Mapping) else None


def load_constructed_assets(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_assets: Any
    if isinstance(value, Mapping):
        raw_assets = value.get("assets", value.get("cases", []))
    elif isinstance(value, list):
        raw_assets = value
    else:
        return []
    if not isinstance(raw_assets, list):
        return []
    assets = [
        item
        for item in (normalize_constructed_asset(raw) for raw in raw_assets)
        if item is not None
    ]
    return _dedupe_assets(assets)


def discover_constructed_assets(*roots: Path | None) -> list[dict[str, str]]:
    """Load the first non-empty inventory found under the given roots."""

    for root in roots:
        if root is None:
            continue
        candidates = [
            root / INVENTORY_FILENAME,
            root / "artifacts" / INVENTORY_FILENAME,
        ]
        if root.name == "artifacts":
            candidates.insert(0, root / INVENTORY_FILENAME)
        for candidate in candidates:
            assets = load_constructed_assets(candidate)
            if assets:
                return assets
    return []


def collect_evidence_assets(auto_dir: Path) -> list[dict[str, str]]:
    evidence_root = auto_dir / "evidence"
    if not evidence_root.is_dir():
        return []
    collected: list[dict[str, str]] = []
    for path in sorted(evidence_root.glob(f"*/{EVIDENCE_FILENAME}")):
        collected.extend(load_constructed_assets(path))
    return _dedupe_assets(collected)



def _copy_unique_resource_keys(
    evidence: list[dict[str, str]],
    registered_assets: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Fill missing evidence resource_key from unique registered case+type."""

    buckets: dict[tuple[str, str], list[str]] = {}
    for item in registered_assets:
        key = (item.get("case_id") or "", item.get("resource_type") or "")
        resource_key = str(item.get("resource_key") or "").strip()
        if not resource_key:
            continue
        buckets.setdefault(key, [])
        if resource_key not in buckets[key]:
            buckets[key].append(resource_key)
    unique = {
        key: values[0] for key, values in buckets.items() if len(values) == 1
    }
    enriched: list[dict[str, str]] = []
    for item in evidence:
        cloned = dict(item)
        if not cloned.get("resource_key"):
            mapped = unique.get(
                (cloned.get("case_id") or "", cloned.get("resource_type") or "")
            )
            if mapped:
                cloned["resource_key"] = mapped
        enriched.append(cloned)
    return enriched


def merge_constructed_inventory(
    registered: Sequence[Mapping[str, Any]] | None = None,
    evidence_assets: Sequence[Mapping[str, Any]] | None = None,
    titles: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    evidence = [
        item
        for item in (normalize_constructed_asset(raw) for raw in evidence_assets or [])
        if item is not None
    ]
    registered_assets: list[dict[str, str]] = []
    for raw in registered or []:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("status") or "constructed") not in {"constructed", ""}:
            continue
        item = normalize_constructed_asset(raw)
        if item is not None:
            registered_assets.append(item)
    from .asset_scene_naming import apply_scene_display_names

    evidence = _copy_unique_resource_keys(evidence, registered_assets)
    evidence = apply_scene_display_names(evidence, titles)
    registered_assets = apply_scene_display_names(registered_assets, titles)
    if not evidence:
        return _dedupe_assets(registered_assets)

    matched_keys: set[tuple[str, str, str]] = set()
    merged = list(evidence)
    for item in evidence:
        matched_keys.add(
            (
                item.get("case_id") or "",
                item.get("resource_type") or "",
                item.get("resource_key") or item.get("resource_id") or "",
            )
        )
    for item in registered_assets:
        key = (
            item.get("case_id") or "",
            item.get("resource_type") or "",
            item.get("resource_key") or item.get("resource_id") or "",
        )
        already = False
        if item.get("resource_id"):
            already = any(
                existing.get("resource_id") == item["resource_id"] for existing in merged
            )
        if not already:
            already = key in matched_keys and bool(key[2])
        if already:
            continue
        if any(
            existing.get("case_id") == item.get("case_id")
            and existing.get("resource_type") == item.get("resource_type")
            and existing.get("resource_id")
            for existing in merged
        ) and not item.get("resource_id"):
            continue
        merged.append(item)
    merged = apply_scene_display_names(_dedupe_assets(merged), titles)
    return merged


def write_constructed_asset_inventory(
    path: Path,
    assets: Sequence[Mapping[str, Any]],
    *,
    namespace: str = "",
    environment: str = "",
) -> Path:
    normalized = [
        item
        for item in (normalize_constructed_asset(raw) for raw in assets)
        if item is not None
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "environment": environment,
        "namespace": namespace,
        "asset_count": len(normalized),
        "assets": normalized,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
