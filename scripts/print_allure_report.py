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
_TRANSLATION_CASE = re.compile(r"^翻译 case (?P<number>\d+)：(?P<name>.+)$")
_MATCHED_TRANSLATION_TERM = re.compile(r"^采集最终词条：(?P<path>.+)$")
_TRANSLATION_SUBJECT = re.compile(
    r"个人语言为(?P<personal>中文|英文)，翻译成(?P<translation>中文|英文)"
)
_LANGUAGE_FAILURE = re.compile(
    r"(?P<field>.+?)字段应为 (?P<expected>zh-CN|en): "
    r"(?P<value>.*?)（识别为 (?P<actual>zh-CN|en|mixed|unknown)）"
)
_LANGUAGE_LABELS = {
    "zh-CN": "中文",
    "en": "英文",
    "mixed": "中英混合",
    "unknown": "空值或无法识别",
}
_LANGUAGE_CODES = {"中文": "zh-CN", "英文": "en"}
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN = re.compile(r"[A-Za-z]")


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


def _translation_case_info(step: dict[str, Any]) -> tuple[str, str] | None:
    match = _TRANSLATION_CASE.match(str(step.get("name", "")))
    if not match:
        return None
    return match.group("number"), match.group("name").replace("-", " > ")


def _matched_translation_path(step: dict[str, Any]) -> str | None:
    match = _MATCHED_TRANSLATION_TERM.match(str(step.get("name", "")))
    if match:
        path = match.group("path")
        return None if path.startswith("<") else path
    for child in step.get("steps") or []:
        path = _matched_translation_path(child)
        if path:
            return path
    return None


def _translation_case_display(step: dict[str, Any]) -> tuple[str, str] | None:
    info = _translation_case_info(step)
    if not info:
        return None
    number, path = info
    matched_path = _matched_translation_path(step)
    return number, f"{path} > {matched_path}" if matched_path else path


def _translation_subject_languages(result: dict[str, Any]) -> tuple[str, str] | None:
    match = _TRANSLATION_SUBJECT.search(str(result.get("name", "")))
    if not match:
        return None
    return _LANGUAGE_CODES[match.group("personal")], _LANGUAGE_CODES[match.group("translation")]


def _detect_language(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "unknown"
    has_han = _HAN.search(value) is not None
    has_latin = _LATIN.search(value) is not None
    if has_han and has_latin:
        return "mixed"
    if has_han:
        return "zh-CN"
    if has_latin:
        return "en"
    return "unknown"


def _language_matches(actual: str, expected: str) -> bool:
    if expected == "zh-CN":
        return actual in {"zh-CN", "mixed"}
    return actual == expected


def _humanize_failure(message: Any) -> list[str]:
    rendered = _redact_text(str(message or "")).strip()
    rendered = re.sub(r"^AssertionError:\s*", "", rendered)
    if not rendered:
        return ["未提供具体失败原因，请查看详细报告。"]
    failures = []
    for fragment in rendered.replace("\n", " ").split("；"):
        fragment = fragment.strip()
        match = _LANGUAGE_FAILURE.fullmatch(fragment)
        if not match:
            failures.append(fragment)
            continue
        failures.append(
            f"{match.group('field')}：期望{_LANGUAGE_LABELS[match.group('expected')]}，"
            f"实际值={match.group('value')}，"
            f"识别为{_LANGUAGE_LABELS[match.group('actual')]}"
        )
    return failures


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

    def render_summary(self, results: list[dict[str, Any]]) -> str:
        subject_counts = Counter(result.get("status", "unknown") for result in results)
        all_case_steps = [
            step
            for result in results
            for step in result.get("steps") or []
            if _translation_case_info(step)
        ]
        case_counts = Counter(step.get("status", "unknown") for step in all_case_steps)
        starts = [result["start"] for result in results if isinstance(result.get("start"), (int, float))]
        stops = [result["stop"] for result in results if isinstance(result.get("stop"), (int, float))]
        elapsed_ms = max(stops) - min(starts) if starts and stops else 0
        lines = [
            "=" * 88,
            "翻译工作台自动化测试报告",
            "=" * 88,
            f"生成时间: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}",
            f"测试主体: {len(results)} 个  |  通过: {subject_counts['passed']}  |  "
            f"失败: {subject_counts['failed']}  |  异常: {subject_counts['broken']}",
            f"翻译路径 Case: {len(all_case_steps)} 条  |  通过: {case_counts['passed']}  |  "
            f"失败: {case_counts['failed']}  |  异常: {case_counts['broken']}  |  "
            f"总耗时: {elapsed_ms / 1000:.3f}s",
            "",
            "断言规则:",
            "  - 接口返回分组行时，分组名称（needTransName）必须符合当前个人语言。",
            "  - 名称（needTransName）必须符合当前个人语言。",
            "  - 名称翻译（translateValue）必须符合目标翻译语言。",
            "  - 空值、缺失值或语言不匹配均判定为失败。",
            "",
        ]

        for index, result in enumerate(results, start=1):
            subject_languages = _translation_subject_languages(result)
            case_steps = [
                step for step in result.get("steps") or [] if _translation_case_info(step)
            ]
            counts = Counter(step.get("status", "unknown") for step in case_steps)
            lines.extend(
                [
                    "-" * 88,
                    f"场景 {index}: {result.get('name', '<unnamed>')}",
                    f"结果: {STATUS_LABELS.get(result.get('status', 'unknown'), '未知')}  |  "
                    f"Case 通过 {counts['passed']} / 失败 {counts['failed']} / "
                    f"异常 {counts['broken']} / 共 {len(case_steps)} 条",
                    "",
                ]
            )
            failed_steps = [
                step for step in case_steps if step.get("status") in {"failed", "broken"}
            ]
            passed_steps = [step for step in case_steps if step.get("status") == "passed"]

            if failed_steps:
                lines.append(f"失败 Case（{len(failed_steps)} 条）:")
                for step in failed_steps:
                    number, path = _translation_case_display(step) or ("??", str(step.get("name")))
                    lines.append(f"  [{number}] [FAIL] {path}")
                    lines.extend(self._render_translation_field_checks(step, subject_languages))
                    message = (step.get("statusDetails") or {}).get("message")
                    if not self._matched_translation_fields(step):
                        for failure in _humanize_failure(message):
                            lines.append(f"       - {failure}")
                lines.append("")

            if passed_steps:
                lines.append(f"通过 Case（{len(passed_steps)} 条）:")
                for step in passed_steps:
                    number, path = _translation_case_display(step) or ("??", str(step.get("name")))
                    lines.append(f"  [{number}] [PASS] {path}")
                    lines.extend(self._render_translation_field_checks(step, subject_languages))
                lines.append("")

            if not case_steps and result.get("status") in {"failed", "broken"}:
                lines.append("主体在执行翻译 Case 前失败:")
                message = (result.get("statusDetails") or {}).get("message")
                for failure in _humanize_failure(message):
                    lines.append(f"  - {failure}")
                lines.append("")

        failed_subjects = subject_counts["failed"] + subject_counts["broken"]
        failed_cases = case_counts["failed"] + case_counts["broken"]
        if failed_subjects:
            conclusion = (
                f"共有 {failed_subjects} 个测试主体未通过，其中 {failed_cases} 条翻译路径 Case 未通过。"
            )
        elif failed_cases:
            conclusion = (
                f"共有 {failed_cases} 条翻译路径 Case 未通过，请优先处理上方各场景的失败 Case。"
            )
        else:
            conclusion = "全部翻译路径 Case 通过。"

        lines.extend(
            [
                "=" * 88,
                "结论",
                "=" * 88,
                conclusion,
                "原始请求、响应及调用栈请查看 report-details.txt。",
            ]
        )
        return "\n".join(lines) + "\n"

    def _attachment_rows(
        self, step: dict[str, Any], attachment_name: str
    ) -> list[dict[str, Any]]:
        for attachment in step.get("attachments") or []:
            if attachment.get("name") != attachment_name:
                continue
            source = attachment.get("source")
            if not isinstance(source, str):
                return []
            path = (self.results_dir / source).resolve()
            if self.results_dir not in path.parents or not path.is_file():
                return []
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
        for child in step.get("steps") or []:
            fields = self._attachment_rows(child, attachment_name)
            if fields:
                return fields
        return []

    def _matched_translation_fields(self, step: dict[str, Any]) -> list[dict[str, Any]]:
        return self._attachment_rows(step, "命中的名称与名称翻译字段")

    def _matched_folder_fields(self, step: dict[str, Any]) -> list[dict[str, Any]]:
        return self._attachment_rows(step, "命中的文件夹名称字段")

    def _render_translation_field_checks(
        self,
        step: dict[str, Any],
        subject_languages: tuple[str, str] | None,
    ) -> list[str]:
        if not subject_languages:
            return []
        rows = self._matched_translation_fields(step)
        folder_rows = self._matched_folder_fields(step)
        if not rows and not folder_rows:
            return []
        personal_language, translation_language = subject_languages
        lines = []
        for row in folder_rows:
            value = row.get("needTransName")
            actual = _detect_language(value)
            mark = "[PASS]" if _language_matches(actual, personal_language) else "[FAIL]"
            lines.append(
                f"       - {mark} 分组名称（needTransName）："
                f"期望{_LANGUAGE_LABELS[personal_language]}，实际值={value!r}，"
                f"识别为{_LANGUAGE_LABELS[actual]}"
            )
        for row in rows:
            for field_name, field_key, expected in (
                ("名称（needTransName）", "needTransName", personal_language),
                ("名称翻译（translateValue）", "translateValue", translation_language),
            ):
                value = row.get(field_key)
                actual = _detect_language(value)
                mark = "[PASS]" if _language_matches(actual, expected) else "[FAIL]"
                lines.append(
                    f"       - {mark} {field_name}：期望{_LANGUAGE_LABELS[expected]}，"
                    f"实际值={value!r}，识别为{_LANGUAGE_LABELS[actual]}"
                )
        return lines

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
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print the report body; useful when only --output is needed",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Render a readable translation Case summary without raw request/response JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    renderer = LocalReportRenderer(args.results_dir, args.max_attachment_chars)
    results = renderer.load_results()
    if not results:
        print(f"没有找到 Allure 用例结果: {args.results_dir}")
        return 2
    report = renderer.render_summary(results) if args.summary_only else renderer.render(results)
    if not args.quiet:
        print(report, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        if not args.quiet:
            print(f"报告文件: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
