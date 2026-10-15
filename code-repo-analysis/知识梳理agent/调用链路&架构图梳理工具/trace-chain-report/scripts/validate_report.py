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
SECRET_RE = re.compile(r"password|passwd|userId|userName\s*=|uid\s*[:=]", re.IGNORECASE)
WALK_STEP_RE = re.compile(
    r"(?m)^### 步骤 \d+\n"
    r"1、这一步是干什么的：(?P<purpose>\S.*)\n"
    r"2、文件绝对路径：`?(?P<path>未取证|/[^\s`]+)`?\n"
    r"3、（方法：(?P<method>[^，）]+)，接口：(?P<iface>[^）]+)）[ \t]*$"
)


def _line_present(text: str, line: object) -> bool:
    try:
        number = int(line)
    except (TypeError, ValueError):
        return False
    return f":{number}" in text or f"第 {number} 行" in text or f"第{number}行" in text


def walk_step_errors(node_id: str, source: dict[str, object], code_section: str) -> list[str]:
    """Each mapped method must be one Java walk step: purpose, absolute path, method and interface."""
    steps = list(WALK_STEP_RE.finditer(code_section))
    if not steps:
        return [f"node {node_id} code section missing Java walk step"]
    body = str(source["file"])
    filename = body.rsplit("/", 1)[-1]
    method = str(source["symbol"]).rsplit(".", 1)[-1].strip()
    declaration = str(source.get("declaration_file") or "")
    impl_steps = [
        step
        for step in steps
        if filename in step.group("path") and step.group("method").strip() == method
    ]
    if not impl_steps:
        return [f"node {node_id} code section missing walk step for {method} in {filename}"]
    step = impl_steps[0]
    errors: list[str] = []
    if not CJK_RE.search(step.group("purpose")):
        errors.append(f"node {node_id} walk step missing Chinese purpose")
    iface = step.group("iface").strip()
    if not declaration or declaration == body:
        if iface != "无":
            errors.append(f"node {node_id} walk step interface must be 无")
    else:
        expected = declaration.rsplit("/", 1)[-1].removesuffix(".java")
        if iface != expected:
            errors.append(f"node {node_id} walk step interface must be {expected}")
        decl_name = declaration.rsplit("/", 1)[-1]
        if not any(decl_name in item.group("path") for item in steps):
            errors.append(f"node {node_id} code section missing interface file walk step")
    if not step.group("path").startswith("/"):
        errors.append(f"node {node_id} walk step file is not absolute")
    return errors


def code_mapping_errors(node_id: str, source: object, detail: str, code_section: str, html: str) -> list[str]:
    """Reject mappings that name a call without its implementation file and line."""
    if not isinstance(source, dict) or not all(source.get(key) for key in ("repo", "file", "symbol", "declaration_file")):
        return [f"node {node_id} code mapping missing declaration or implementation source"]
    errors: list[str] = []
    body = str(source["file"])
    declaration = str(source["declaration_file"])
    for text, name in ((detail, "detail"), (html, "html")):
        if body not in text:
            errors.append(f"node {node_id} {name} missing implementation file")
    if declaration != body:
        if declaration not in detail or declaration not in html:
            errors.append(f"node {node_id} missing declaration file in reader text")
        if "没有" not in detail:
            errors.append(f"node {node_id} must say the declaration file has no call")
        if not _line_present(detail, source.get("declaration_line")) and not _line_present(html, source.get("declaration_line")):
            errors.append(f"node {node_id} missing declaration line")
    calls = source.get("calls", [])
    if calls is None:
        calls = []
    if not isinstance(calls, list):
        return [*errors, f"node {node_id} source.calls must be a list"]
    if "调用" in detail and not calls:
        errors.append(f"node {node_id} describes a call without source.calls")
    if not calls and "行号未取证" not in detail and not _line_present(detail, source.get("line")):
        errors.append(f"node {node_id} missing method line or 行号未取证")
    for call in calls:
        if not isinstance(call, dict) or not all(call.get(key) for key in ("symbol", "file", "line")):
            errors.append(f"node {node_id} call missing symbol, file, or line")
            continue
        call_file = str(call["file"])
        call_symbol = str(call["symbol"])
        if call_file != body:
            errors.append(f"node {node_id} call {call_symbol} is not pinned to the implementation file")
        if declaration != body and call_file == declaration:
            errors.append(f"node {node_id} call {call_symbol} is pinned to the declaration file")
        for text, name in ((detail, "detail"), (html, "html")):
            if call_file not in text or call_symbol not in text or not _line_present(text, call["line"]):
                errors.append(f"node {node_id} {name} missing call site for {call_symbol}")
    if isinstance(source, dict):
        errors.extend(walk_step_errors(node_id, source, code_section))
    return errors



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
        layer = str(node["layer"])
        title = str(node["title_zh"])
        detail = str(node["detail"])
        if label == "代码映射":
            mapped = True
            errors.extend(code_mapping_errors(str(node.get("id")), node.get("source"), detail, code_section, html))
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

    if SECRET_RE.search(visible):
        errors.append("report contains a secret or user identifier")

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
