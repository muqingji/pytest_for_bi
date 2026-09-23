#!/usr/bin/env python3
"""Validate one trace report directory against the fact card.

The script checks structure, isolation, and redaction. It does not write or score prose.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ALLOWED_LABELS = {"已观测", "代码映射", "推断", "未取证"}
NODE_KEYS = (
    "id",
    "service",
    "entry",
    "method",
    "flow",
    "downstream",
    "timing",
    "evidence",
    "label",
    "row",
    "title_zh",
    "detail",
    "layer",
)
LAYERS = {"display", "gateway", "service", "data", "offpath"}
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
HEADINGS = (
    "## 1. 分析对象",
    "## 2. 一句话结论",
    "## 3. 调用链路图",
    "## 4. 请求序列",
    "## 5. 节点逐条说明",
    "## 6. 代码走读链路",
    "## 7. 性能分解与瓶颈",
    "## 8. Pod 与资源配置",
    "## 9. 证据边界",
    "## 10. 证据索引",
)
SECRET_RE = re.compile(r"password|passwd|jdbc:|userId|userName\s*=|uid\s*[:=]", re.IGNORECASE)
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

def _load_card(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fact card must be an object")
    return payload


def _section(markdown: str, heading: str, following: str | None) -> str:
    start = markdown.find(heading)
    if start < 0:
        return ""
    end = markdown.find(following, start + len(heading)) if following else -1
    return markdown[start:] if end < 0 else markdown[start:end]


def validate_report(directory: Path, peer: Path | None = None, check_evidence: bool = False) -> list[str]:
    errors: list[str] = []
    card_path = directory / "fact-card.json"
    markdown_path = directory / "调用链路分析.md"
    html_path = directory / "调用链路线性图.html"
    index_path = directory / "证据索引.md"
    for path in (card_path, markdown_path, html_path, index_path):
        if not path.is_file():
            errors.append(f"missing {path.name}")
    if errors:
        return errors

    try:
        card = _load_card(card_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"fact card unreadable: {exc}"]

    for key in ("schema_version", "mode", "trace_id", "title", "nodes", "gaps", "evidence"):
        if key not in card:
            errors.append(f"fact card missing {key}")
    if card.get("schema_version") != "trace-fact-card-v1":
        errors.append("schema_version must be trace-fact-card-v1")
    if card.get("mode") not in {"knowledge", "live"}:
        errors.append("mode must be knowledge or live")
    trace_id = str(card.get("trace_id") or "")
    nodes = card.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return [*errors, "nodes must be a non-empty list"]

    markdown = markdown_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    index = index_path.read_text(encoding="utf-8")
    visible = "\n".join((markdown, html, index, json.dumps(card, ensure_ascii=False)))
    if trace_id and trace_id not in markdown:
        errors.append("markdown missing trace_id")
    if trace_id and trace_id not in html:
        errors.append("html missing trace_id")
    if trace_id and trace_id not in index:
        errors.append("evidence index missing trace_id")

    for heading in HEADINGS:
        if heading not in markdown:
            errors.append(f"markdown missing {heading}")
    code_section = _section(markdown, HEADINGS[5], HEADINGS[6])
    perf_section = _section(markdown, HEADINGS[6], HEADINGS[7])
    boundary = _section(markdown, HEADINGS[8], HEADINGS[9])
    if "未细分" not in perf_section:
        errors.append("performance section missing 未细分")
    if "未取证" not in boundary:
        errors.append("boundary section missing 未取证")

    mapped = False
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("node must be an object")
            continue
        missing = [key for key in NODE_KEYS if key not in node]
        if missing:
            errors.append(f"node {node.get('id')} missing {', '.join(missing)}")
            continue
        label = str(node["label"])
        if label not in ALLOWED_LABELS:
            errors.append(f"node {node['id']} has unknown label {label}")
        if label == "代码映射":
            mapped = True
            source = node.get("source")
            if not isinstance(source, dict) or not all(source.get(key) for key in ("repo", "file", "symbol")):
                errors.append(f"node {node['id']} code mapping missing source")
        layer = str(node["layer"])
        title = str(node["title_zh"])
        detail = str(node["detail"])
        if layer not in LAYERS:
            errors.append(f"node {node['id']} has unknown layer {layer}")
        if not CJK_RE.search(title) or not CJK_RE.search(detail):
            errors.append(f"node {node['id']} title or detail is not Chinese")
        if str(node["method"]) not in detail:
            errors.append(f"node {node['id']} detail missing method")
        if title not in html or detail not in html:
            errors.append(f"html missing card text for {node['id']}")
        if str(node["method"]) not in markdown:
            errors.append(f"markdown missing method {node['method']}")
    if mapped and "代码映射" not in code_section:
        errors.append("code section missing 代码映射")
    if not mapped and "未取得精确源码" not in code_section:
        errors.append("code section must say 未取得精确源码 when no code mapping exists")

    if re.search(r"https?://|cdn", html, re.IGNORECASE):
        errors.append("html must not load external resources")
    for marker in ("class=\"page\"", "class=\"stack\"", "class=\"layer", "class=\"card\"", "class=\"arrow\""):
        if marker not in html:
            errors.append(f"html missing {marker}")
    if html.count('class="card"') < len(nodes):
        errors.append("html has fewer cards than fact-card nodes")
    if "<svg" in html:
        errors.append("html must use layered cards, not svg")

    if SECRET_RE.search(visible) or IPV4_RE.search(visible):
        errors.append("report contains a secret or IP address")

    evidence = card.get("evidence")
    if check_evidence:
        if not isinstance(evidence, list):
            errors.append("evidence must be a list")
        else:
            for item in evidence:
                if not isinstance(item, dict) or not item.get("path"):
                    errors.append("evidence item missing path")
                    continue
                if not Path(str(item["path"])).is_file():
                    errors.append(f"evidence file missing: {item['path']}")

    if peer:
        try:
            other = _load_card(peer / "fact-card.json")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"peer fact card unreadable: {exc}")
        else:
            other_trace = str(other.get("trace_id") or "")
            if other_trace and other_trace != trace_id and other_trace in visible:
                errors.append("report contains the peer trace_id")
            own_pod = str((card.get("runtime") or {}).get("pod") or "") if isinstance(card.get("runtime"), dict) else ""
            other_runtime = other.get("runtime")
            other_pod = str(other_runtime.get("pod") or "") if isinstance(other_runtime, dict) else ""
            if own_pod and other_pod and own_pod != other_pod and other_pod in visible:
                errors.append("report contains the peer pod")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a trace-chain report directory.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--peer", type=Path, help="Another trace directory that must stay isolated.")
    parser.add_argument("--check-evidence", action="store_true")
    args = parser.parse_args(argv)
    errors = validate_report(args.directory, args.peer, args.check_evidence)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
