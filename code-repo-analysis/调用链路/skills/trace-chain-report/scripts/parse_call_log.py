#!/usr/bin/env python3
"""Parse a call-log markdown file into one task per traceId.

This script only extracts identifiers. It does not query logs or write reports.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TRACE_RE = re.compile(r"FSW-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*")
LABEL_RE = re.compile(r"^\s*(?:[-*]\s*)?([^|：:\n`]{1,40})[：:]\s*\S")
SKIP_LABELS = {"描述", "trace", "traceid", "项目", "已完成"}


def _clean_label(value: str) -> str:
    return value.strip().strip("`").strip()


def _label_for_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("|"):
        cells = [_clean_label(cell) for cell in stripped.strip("|").split("|")]
        if cells and cells[0] and cells[0] not in SKIP_LABELS and "trace" not in cells[0].lower():
            return cells[0]
        return ""
    match = LABEL_RE.match(stripped)
    if not match:
        return ""
    label = _clean_label(match.group(1))
    if label.lower() in SKIP_LABELS:
        return ""
    return label


def parse_call_log(text: str) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    seen: set[str] = set()
    for line_no, line in enumerate(text.splitlines(), start=1):
        label = _label_for_line(line)
        for trace_id in TRACE_RE.findall(line):
            if trace_id in seen:
                continue
            seen.add(trace_id)
            tasks.append({"description": label or "未命名链路", "trace_id": trace_id, "line": line_no})
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
