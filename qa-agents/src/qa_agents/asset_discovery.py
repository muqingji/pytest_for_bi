"""Recursive BI report catalog discovery without assuming root-level assets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def walk_values(value: object):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_values(child)


def discover_catalog(
    query: Callable[[str, int, int], Mapping[str, Any]], *, page_size: int = 500
) -> list[dict[str, Any]]:
    """Traverse every category and return unique category/report entries."""
    pending = ["0"]
    visited_categories: set[str] = set()
    found: dict[str, dict[str, Any]] = {}
    while pending:
        category_id = pending.pop(0)
        if category_id in visited_categories:
            continue
        visited_categories.add(category_id)
        page = 1
        while True:
            response = query(category_id, page, page_size)
            entries = [dict(item) for item in walk_values(response)
                       if item.get("itemID") and "isCategory" in item]
            new_ids = 0
            for entry in entries:
                item_id = str(entry["itemID"])
                if item_id not in found:
                    found[item_id] = entry
                    new_ids += 1
                if int(entry.get("isCategory", -1)) == 1 and item_id not in visited_categories:
                    pending.append(item_id)
            if len(entries) < page_size or new_ids == 0:
                break
            page += 1
    return list(found.values())
