#!/usr/bin/env python3
"""Render Allure result files as a detailed, readable local text report."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


STATUS_LABELS = {
    "passed": "通过",
    "failed": "失败",
    "broken": "异常",
    "skipped": "跳过",
    "unknown": "未知",
}
STATUS_MARKS = {
    "passed": "[PASS]",
    "failed": "[FAIL]",
    "broken": "[ERROR]",
    "skipped": "[SKIP]",
    "unknown": "[????]",
}
SENSITIVE_FRAGMENTS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "session",
    "token",
)
_SENSITIVE_KEY_PATTERN = "|".join(re.escape(item) for item in SENSITIVE_FRAGMENTS)
_QUOTED_SECRET = re.compile(
    rf"(?i)([\"']?(?:{_SENSITIVE_KEY_PATTERN})[\w-]*[\"']?\s*[:=]\s*)([\"'])(.*?)(\2)"
)
_UNQUOTED_SECRET = re.compile(
    rf"(?i)([\"']?(?:{_SENSITIVE_KEY_PATTERN})[\w-]*[\"']?\s*[:=]\s*)([^\s,;}}\]&]+)"
)


def _duration_ms(item: dict[str, Any]) -> int:
    start = item.get("start")
    stop = item.get("stop")
    if isinstance(start, (int, float)) and isinstance(stop, (int, float)):
        return max(0, round(stop - start))
    return 0


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***"
            if any(fragment in str(key).lower() for fragment in SENSITIVE_FRAGMENTS)
            else _redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact(child) for child in value]
    return value


def _redact_text(value: str) -> str:
    value = _QUOTED_SECRET.sub(lambda match: f"{match.group(1)}{match.group(2)}***REDACTED***{match.group(2)}", value)
    return _UNQUOTED_SECRET.sub(lambda match: f"{match.group(1)}***REDACTED***", value)


def _truncate(value: str, limit: int) -> str:
    if limit <= 0 or len(value) <= limit:
        return value
    omitted = len(value) - limit
    return f"{value[:limit]}\n... 已省略 {omitted} 个字符（可通过 --max-attachment-chars 调整）"


def _indent(value: str, width: int) -> list[str]:
    prefix = " " * width
    return [prefix + line for line in value.splitlines()]


def _case_metadata(result: dict[str, Any]) -> dict[str, Any]:
    for parameter in result.get("parameters") or []:
        if parameter.get("name") != "api_case":
            continue
        raw_value = parameter.get("value")
        if not isinstance(raw_value, str):
            continue
        try:
            value = ast.literal_eval(raw_value)
        except (SyntaxError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return {}


class LocalReportRenderer:
    def __init__(self, results_dir: Path, max_attachment_chars: int = 6000) -> None:
        self.results_dir = results_dir.resolve()
        self.max_attachment_chars = max_attachment_chars
        self._seen_attachments: set[str] = set()
        self._seen_attachment_content: set[str] = set()
        self._seen_failure_traces: dict[str, str] = {}

    def load_results(self) -> list[dict[str, Any]]:
        results = []
        for path in self.results_dir.glob("*-result.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                results.append(
                    {
                        "name": path.name,
                        "status": "broken",
                        "statusDetails": {"message": f"无法读取结果文件: {error}"},
                    }
                )
                continue
            if isinstance(value, dict):
                results.append(value)
        return sorted(results, key=lambda item: (item.get("start", 0), item.get("name", "")))

    def render(self, results: list[dict[str, Any]]) -> str:
        self._seen_attachments.clear()
        self._seen_attachment_content.clear()
        self._seen_failure_traces.clear()
        counts = Counter(result.get("status", "unknown") for result in results)
        starts = [result["start"] for result in results if isinstance(result.get("start"), (int, float))]
        stops = [result["stop"] for result in results if isinstance(result.get("stop"), (int, float))]
        elapsed_ms = max(stops) - min(starts) if starts and stops else sum(_duration_ms(item) for item in results)

        lines = [
            "=" * 88,
            "BI 接口自动化本地详细报告",
            "=" * 88,
            f"生成时间: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}",
            f"结果目录: {self.results_dir}",
            f"用例总数: {len(results)}  |  通过: {counts['passed']}  |  失败: {counts['failed']}  |  "
            f"异常: {counts['broken']}  |  跳过: {counts['skipped']}  |  总耗时: {elapsed_ms / 1000:.3f}s",
            "",
        ]

        for index, result in enumerate(results, start=1):
            lines.extend(self._render_case(index, result))

        lines.extend(
            [
                "=" * 88,
                "执行汇总",
                "=" * 88,
                f"通过 {counts['passed']} / 失败 {counts['failed']} / 异常 {counts['broken']} / "
                f"跳过 {counts['skipped']} / 共 {len(results)} 条",
            ]
        )
        unsuccessful = [item for item in results if item.get("status") in {"failed", "broken"}]
        if unsuccessful:
            lines.append("未通过用例:")
            for item in unsuccessful:
                metadata = _case_metadata(item)
                lines.append(f"  - {metadata.get('name') or item.get('name', '<unnamed>')}")
        else:
            lines.append("结论: 全部已执行用例通过。")
        return "\n".join(lines) + "\n"

    def _render_case(self, index: int, result: dict[str, Any]) -> list[str]:
        metadata = _case_metadata(result)
        status = result.get("status", "unknown")
        display_name = metadata.get("name") or result.get("name", "<unnamed>")
        lines = [
            "-" * 88,
            f"{index:02d}. {STATUS_MARKS.get(status, STATUS_MARKS['unknown'])} {display_name}",
        ]
        details = []
        if metadata.get("id"):
            details.append(f"ID: {metadata['id']}")
        if metadata.get("priority"):
            details.append(f"优先级: {metadata['priority']}")
        details.extend(
            [
                f"状态: {STATUS_LABELS.get(status, status)}",
                f"耗时: {_duration_ms(result) / 1000:.3f}s",
            ]
        )
        lines.append("  " + "  |  ".join(details))
        lines.append(f"  测试节点: {result.get('name', '<unnamed>')}")

        for step in result.get("steps") or []:
            lines.extend(self._render_step(step, depth=1))
        for attachment in result.get("attachments") or []:
            lines.extend(self._render_attachment(attachment, depth=1))

        status_details = result.get("statusDetails") or {}
        message = status_details.get("message")
        trace = status_details.get("trace")
        if message:
            lines.append("  失败原因:")
            lines.extend(_indent(_redact_text(str(message)), 4))
        if trace:
            redacted_trace = _redact_text(str(trace))
            trace_digest = hashlib.sha256(redacted_trace.encode("utf-8")).hexdigest()
            duplicate_of = self._seen_failure_traces.get(trace_digest)
            if duplicate_of:
                lines.append(f"  调用栈: 与用例「{duplicate_of}」相同，已省略重复内容")
            else:
                self._seen_failure_traces[trace_digest] = str(display_name)
                lines.append("  调用栈:")
                lines.extend(_indent(_truncate(redacted_trace, self.max_attachment_chars), 4))
        lines.append("")
        return lines

    def _render_step(self, step: dict[str, Any], depth: int) -> list[str]:
        status = step.get("status", "unknown")
        prefix = "  " * depth
        lines = [
            f"{prefix}{STATUS_MARKS.get(status, STATUS_MARKS['unknown'])} 步骤: "
            f"{step.get('name', '<unnamed>')} ({_duration_ms(step)}ms)"
        ]
        for attachment in step.get("attachments") or []:
            lines.extend(self._render_attachment(attachment, depth + 1))
        for child in step.get("steps") or []:
            lines.extend(self._render_step(child, depth + 1))
        return lines

    def _render_attachment(self, attachment: dict[str, Any], depth: int) -> list[str]:
        source = attachment.get("source")
        prefix = "  " * depth
        if not isinstance(source, str) or source in self._seen_attachments:
            return []
        self._seen_attachments.add(source)
        path = (self.results_dir / source).resolve()
        if self.results_dir not in path.parents or not path.is_file():
            return [f"{prefix}附件 {attachment.get('name', source)}: 无法读取 {source}"]
        try:
            raw_value = path.read_text(encoding="utf-8")
        except OSError as error:
            return [f"{prefix}附件 {attachment.get('name', source)}: 读取失败: {error}"]
        content_digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
        if content_digest in self._seen_attachment_content:
            return []
        self._seen_attachment_content.add(content_digest)

        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            rendered = _redact_text(raw_value)
        else:
            rendered = json.dumps(_redact(value), ensure_ascii=False, indent=2, default=str)
        rendered = _truncate(rendered, self.max_attachment_chars)
        lines = [f"{prefix}附件 {attachment.get('name', source)}:"]
        lines.extend(_indent(rendered, len(prefix) + 2))
        return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path, help="Directory containing Allure *-result.json files")
    parser.add_argument("--output", type=Path, help="Also save the rendered report to this file")
    parser.add_argument(
        "--max-attachment-chars",
        type=int,
        default=6000,
        help="Maximum characters printed for one attachment; 0 means unlimited",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    renderer = LocalReportRenderer(args.results_dir, args.max_attachment_chars)
    results = renderer.load_results()
    if not results:
        print(f"没有找到 Allure 用例结果: {args.results_dir}")
        return 2
    report = renderer.render(results)
    print(report, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"报告文件: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
