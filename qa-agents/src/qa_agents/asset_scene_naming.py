"""Visible Chinese names for case-constructed BI test assets.

Implements retained-test-asset-naming: the card/112 visible name must match
the case semantics from the A22 capability catalog (for example
``自定义维度查看明细验证统计图``). Short tags, namespaces, English titles,
``resource_key`` values, and ``_副本N`` copy suffixes are not the visible name.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re

_CJK = re.compile(r"[\u4e00-\u9fff]")
_COPY_SUFFIX = re.compile(r"_副本\d+$")
_PLACEHOLDER = re.compile(r"\{\{.*\}\}")
_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "knowledge" / "bi-data-capability-catalog.json"
)
_SCENE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("calculated", "dynamic_name", "calc_field", "计算指标"), "动态名称"),
    (("combo", "multiple matched", "组合"), "组合限制"),
    (("custom_dimension", "custom dimension", "s307011534", "自定义维度"), "自定义维度"),
    (
        (
            "result_filter",
            "result-set",
            "result_set",
            "s307011535",
            "resolution_set",
            "结果集",
        ),
        "结果集筛选",
    ),
    (("multi_relation", "multi-relation", "s307011536", "多关联"), "多关联"),
    (("dynamic_relation", "dynamic-relation", "s307011537", "动态关联"), "动态关联"),
    (("sensitive", "permission", "权限"), "权限优先"),
    (("restricted_chart", "restricted_metric"), "权限优先"),
    (("contract", "契约"), "契约透传"),
    (("e2e", "joined_table", "端到端"), "端到端"),
    (("historical", "compat", "历史"), "历史兼容"),
)
_TYPE_FALLBACK = {
    "stat_chart": "统计图",
    "report": "报表",
    "pivot_table": "交叉表",
    "dashboard": "驾驶舱",
    "aggregate_metric": "聚合指标",
    "ordinary_metric": "普通指标",
    "calculated_metric": "计算指标",
    "comparison_metric": "同环比指标",
    "custom_dimension": "自定义维度",
    "joined_table": "拼表",
}
_SHORT_SCENE_LABELS = {label for _, label in _SCENE_RULES} | set(_TYPE_FALLBACK.values())
_catalog_display_names: dict[str, str] | None = None


def is_short_scene_label(name: str | None) -> bool:
    return str(name or "").strip() in _SHORT_SCENE_LABELS


def is_usable_visible_name(name: str | None) -> bool:
    text = str(name or "").strip()
    if not text or _CJK.search(text) is None:
        return False
    lowered = text.lower()
    if lowered.startswith("qa-") or lowered.startswith("a08_"):
        return False
    if _COPY_SUFFIX.search(text):
        return False
    if is_short_scene_label(text):
        return False
    return True


def load_catalog_display_names(path: Path | None = None) -> dict[str, str]:
    """Map catalog ``resource_key`` to semantic ``display_name``."""

    global _catalog_display_names
    catalog_path = path or _CATALOG_PATH
    if path is None and _catalog_display_names is not None:
        return _catalog_display_names
    names: dict[str, str] = {}
    if not catalog_path.exists() or not catalog_path.is_file():
        if path is None:
            _catalog_display_names = names
        return names
    try:
        value = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        if path is None:
            _catalog_display_names = names
        return names
    recipes = value.get("recipes") if isinstance(value, Mapping) else None
    if not isinstance(recipes, list):
        if path is None:
            _catalog_display_names = names
        return names
    for recipe in recipes:
        if not isinstance(recipe, Mapping):
            continue
        resources = recipe.get("resources")
        if not isinstance(resources, list):
            continue
        for resource in resources:
            if not isinstance(resource, Mapping):
                continue
            resource_key = str(resource.get("resource_key") or "").strip()
            display_name = str(resource.get("display_name") or "").strip()
            if not resource_key or not display_name:
                continue
            if _PLACEHOLDER.search(display_name):
                continue
            names.setdefault(resource_key, display_name)
    if path is None:
        _catalog_display_names = names
    return names


def catalog_display_name(resource_key: str, path: Path | None = None) -> str:
    key = str(resource_key or "").strip()
    if not key:
        return ""
    return load_catalog_display_names(path).get(key, "")


def scene_display_name(
    *,
    resource_type: str = "",
    resource_key: str = "",
    case_id: str = "",
    title: str = "",
    existing_name: str = "",
    allow_type_fallback: bool = True,
) -> str:
    """Return the case-semantic visible name for a constructed asset."""

    if is_usable_visible_name(existing_name):
        return str(existing_name).strip()
    catalog_name = catalog_display_name(resource_key)
    if catalog_name:
        return catalog_name
    blob = " ".join(
        part for part in (resource_key, case_id, title, resource_type) if part
    ).lower()
    for terms, label in _SCENE_RULES:
        if any(term in blob for term in terms):
            return label
    if not allow_type_fallback:
        return ""
    fallback = _TYPE_FALLBACK.get(str(resource_type or "").strip())
    return fallback or ""


def load_case_titles(*paths: Path) -> dict[str, str]:
    titles: dict[str, str] = {}
    for path in paths:
        if path is None or not path.exists() or not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload = value.get("payload", value) if isinstance(value, Mapping) else {}
        if not isinstance(payload, Mapping):
            continue
        for key in ("compiled_cases", "parent_cases", "cases"):
            items = payload.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                case_id = str(item.get("id") or item.get("case_id") or "").strip()
                title = str(item.get("title") or item.get("name") or "").strip()
                if case_id and title:
                    titles.setdefault(case_id, title)
    return titles


def apply_scene_display_names(
    assets: list[dict[str, str]],
    titles: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    title_map = dict(titles or {})
    enriched: list[dict[str, str]] = []
    for asset in assets:
        item = dict(asset)
        case_id = str(item.get("case_id") or "")
        name = scene_display_name(
            resource_type=str(item.get("resource_type") or ""),
            resource_key=str(item.get("resource_key") or ""),
            case_id=case_id,
            title=title_map.get(case_id, ""),
            existing_name=str(item.get("display_name") or ""),
            allow_type_fallback=True,
        )
        if name:
            item["display_name"] = name
        enriched.append(item)
    return enriched
