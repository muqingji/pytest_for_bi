#!/usr/bin/env python3
"""检查最终测试准出报告的结构、证据和结论一致性。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = [
    "需求信息",
    "单元测试与覆盖率",
    "集成测试",
    "CR 结论",
    "测试 Case",
    "自动化执行报告",
    "Bug 信息",
    "最终测试结论",
    "准出决定",
]
REQUIRED_GATES = ["需求范围", "单元测试", "集成测试", "CR", "测试 Case", "自动化执行", "Bug"]
DECISION_RE = re.compile(r"准出结论\s*[|:：]\s*\*{0,2}(准出|有条件准出|不准出)\*{0,2}")
MARKDOWN_PATH_RE = re.compile(r"`([^`\n]+\.(?:md|json|xml|html|out|log|cover|txt))(?::\d+)?`")
FAILURE_RE = re.compile(r"失败\s*(?:[|:：]\s*)?[1-9]\d*|\bFAIL(?:ED)?\b", re.I)
OPEN_HIGH_BUG_RE = re.compile(r"\|\s*(?:P0|P1)\s*\|[^\n]*(?:未修复|未关闭|处理中|待确认|Open|OPEN)")
BLOCKING_RE = re.compile(r"阻塞项\s*[|:：]\s*(?!无(?:\s|[；;。]|$)|0(?:\s|[；;。]|$))\S+")
BAD_GATE_RE = re.compile(
    r"\|\s*(需求范围|单元测试|集成测试|CR|测试 Case|自动化执行|Bug)\s*\|\s*(不通过|未执行|待确认|缺失)\s*\|",
    re.I,
)


def add(findings: list[str], message: str) -> None:
    if message not in findings:
        findings.append(message)


def check_report(report: Path, project_root: Path) -> list[str]:
    text = report.read_text(encoding="utf-8")
    findings: list[str] = []

    for section in REQUIRED_SECTIONS:
        if not re.search(rf"^##\s+\d+\.\s+{re.escape(section)}\s*$", text, re.M | re.I):
            add(findings, f"缺少必要章节：{section}")

    for gate in REQUIRED_GATES:
        if not re.search(rf"\|\s*{re.escape(gate)}\s*\|", text, re.I):
            add(findings, f"最终测试结论缺少门禁：{gate}")

    decision_match = DECISION_RE.search(text)
    if not decision_match:
        add(findings, "准出结论缺失或不是：准出 / 有条件准出 / 不准出")
        decision = None
    else:
        decision = decision_match.group(1)

    if "通过" not in text or "失败" not in text or "跳过" not in text or "未执行" not in text:
        add(findings, "报告未完整区分通过、失败、跳过、未执行四种状态")

    if not re.search(r"覆盖率[^\n]*\d+(?:\.\d+)?%", text):
        add(findings, "单元测试章节缺少覆盖率百分比")
    if not re.search(r"覆盖率[^\n]*(?:门槛|阈值)", text):
        add(findings, "单元测试章节缺少覆盖率门槛或阈值说明")

    if decision == "准出":
        if FAILURE_RE.search(text):
            add(findings, "报告存在失败项，但准出结论为“准出”")
        if OPEN_HIGH_BUG_RE.search(text):
            add(findings, "报告存在未关闭的 P0/P1 Bug 或 CR，但准出结论为“准出”")
        if BAD_GATE_RE.search(text):
            add(findings, "报告存在未通过门禁，但准出结论为“准出”")
        if BLOCKING_RE.search(text):
            add(findings, "报告存在阻塞项，但准出结论为“准出”")

    if decision == "有条件准出":
        exception_line = re.search(r"例外审批\s*[|:：]\s*([^\n]+)", text)
        detail = exception_line.group(1) if exception_line else ""
        for field in ("审批人", "批准记录", "到期时间", "补验", "回退"):
            if field not in detail:
                add(findings, f"有条件准出缺少例外审批信息：{field}")

    for raw_path in MARKDOWN_PATH_RE.findall(text):
        if any(char in raw_path for char in "*<>"):
            continue
        candidate = Path(raw_path)
        if candidate.is_absolute():
            exists = candidate.is_file()
        else:
            exists = (project_root / candidate).is_file()
        if not exists:
            add(findings, f"证据文件不存在：{raw_path}")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="最终测试准出报告回查")
    parser.add_argument("--report", required=True, help="待检查的最终测试准出报告")
    parser.add_argument("--project-root", default=".", help="项目根目录，默认当前目录")
    args = parser.parse_args()

    report = Path(args.report).resolve()
    project_root = Path(args.project_root).resolve()
    if not report.is_file():
        print(f"找不到报告：{report}", file=sys.stderr)
        return 2
    if not project_root.is_dir():
        print(f"找不到项目根目录：{project_root}", file=sys.stderr)
        return 2

    findings = check_report(report, project_root)
    print("# 最终测试准出报告回查")
    print()
    print(f"- 报告：`{report}`")
    print(f"- 阻塞项：{len(findings)}")
    print()
    if findings:
        print("## 阻塞项")
        print()
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("## 结论")
    print()
    print("结构、证据路径和准出结论一致性检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
