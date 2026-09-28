#!/usr/bin/env python3
"""Parse a call-log markdown file into one task per trace and route.

This script only extracts identifiers. It does not query logs or write reports.
Duplicate traceIds stay separate when the description ends with a different route.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TRACE_RE = re.compile(r"FSW-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*")
TRAILING_BACKTICK_RE = re.compile(r"`([^`]+)`\s*$")
TRAILING_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_/])((?:FHH/)?(?:EM\d+[A-Z0-9]+/)?[A-Za-z][\w.-]*(?:/[\w.-]+)+)\s*$"
)
METHOD_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,80}$")
SKIP_LABELS = {"描述", "trace", "traceid", "项目", "已完成", "---"}
SERVICE_CODE_RE = re.compile(r"EM\d+H([A-Z][A-Z0-9]+)")


def _looks_like_route(token: str) -> bool:
    value = token.strip().strip("/")
    if not value or any(ch.isspace() for ch in value):
        return False
    if any("\u4e00" <= ch <= "\u9fff" for ch in value):
        return False
    if any(ch in value for ch in "=${}()"):
        return False
    if "/" in value:
        return True
    return bool(METHOD_TOKEN_RE.match(value))


def _route_key(route: str) -> str:
    value = route.strip().strip("`").strip("/")
    if value.startswith("FHH/"):
        value = value[4:]
    return value


def _split_route(label: str) -> tuple[str, str]:
    raw = label.strip()
    route = ""
    match = TRAILING_BACKTICK_RE.search(raw)
    if match and _looks_like_route(match.group(1)):
        route = match.group(1).strip()
        raw = raw[: match.start()]
    else:
        match = TRAILING_PATH_RE.search(raw)
        if match and _looks_like_route(match.group(1)):
            route = match.group(1).strip()
            raw = raw[: match.start()]
    description = raw.strip().strip("`").strip(" ，,。；; ")
    return description or _route_key(route) or "未命名链路", route


def _label_for_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("|"):
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            return ""
        label = cells[0].strip()
        if not label or label.lower() in SKIP_LABELS or "trace" in label.lower():
            return ""
        return label
    if "：" not in stripped and ":" not in stripped:
        return ""
    head = re.split(r"[：:]", stripped, maxsplit=1)[0]
    head = re.sub(r"^\s*[-*]\s*", "", head).strip()
    if not head or head.lower() in SKIP_LABELS or "trace" in head.lower() or len(head) > 400:
        return ""
    return head


def _short_title(description: str) -> str:
    text = re.sub(r"`[^`]*`", "", description)
    text = re.sub(r"\s+", "", text).strip(" ，,。；;")
    for sep in ("。", "；", ";"):
        if sep in text:
            text = text.split(sep, 1)[0].strip(" ，,。；;")
            break
    if len(text) > 24:
        text = text[:24].rstrip(" ，,")
    return text or "未命名链路"


def _route_slug(route: str) -> str:
    parts = [part for part in _route_key(route).split("/") if part and part != "FHH"]
    parts = [part for part in parts if not re.match(r"EM\d+", part)]
    tail = parts[-3:] if len(parts) >= 3 else parts
    slug = "-".join(tail)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", slug).strip("-")
    return slug[:48]


def _trace_slug(trace_id: str) -> str:
    tail = trace_id.split("-")[-1]
    return tail[:9]


def _service_code(route: str) -> str:
    match = SERVICE_CODE_RE.search(route)
    return match.group(1) if match else ""


def _assign_output_dirs(tasks: list[dict[str, object]]) -> None:
    for task in tasks:
        route = str(task.get("route") or "")
        trace_id = str(task["trace_id"])
        task["title"] = _short_title(str(task["description"]))
        task["slug"] = _route_slug(route) if route else _trace_slug(trace_id)
    seen: dict[str, int] = {}
    for task in tasks:
        slug = str(task["slug"])
        seen[slug] = seen.get(slug, 0) + 1
    used: set[str] = set()
    for task in tasks:
        slug = str(task["slug"])
        if seen[slug] > 1:
            slug = f"{slug}-{_trace_slug(str(task['trace_id']))}"
        if slug in used:
            slug = f"{slug}-{task['line']}"
        used.add(slug)
        task["slug"] = slug
        task["output_dir"] = f"统计图/{task['title']}-{slug}/"


def parse_call_log(text: str) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    seen: dict[tuple[str, str], dict[str, object]] = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        label = _label_for_line(line)
        if not label:
            continue
        description, route = _split_route(label)
        route_key = _route_key(route)
        for trace_id in TRACE_RE.findall(line):
            # 没有末尾路由时无法区分同一次抓包里的重复 traceId，只保留先出现的描述。
            identity = (trace_id, route_key) if route_key else (trace_id, "")
            if identity in seen:
                if not route_key and description != seen[identity]["description"]:
                    merged = seen[identity].setdefault("merged_without_route", [])
                    merged.append({"description": description, "line": line_no})
                continue
            task = {
                "description": description,
                "trace_id": trace_id,
                "route": route,
                "route_key": route_key,
                "service_code": _service_code(route),
                "line": line_no,
            }
            seen[identity] = task
            tasks.append(task)
    _assign_output_dirs(tasks)
    return tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract trace tasks from a call log.")
    parser.add_argument("call_log", type=Path)
    parser.add_argument("--output", type=Path, help="Write JSON here. Defaults to stdout.")
    args = parser.parse_args(argv)
    tasks = parse_call_log(args.call_log.read_text(encoding="utf-8"))
    payload = json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
