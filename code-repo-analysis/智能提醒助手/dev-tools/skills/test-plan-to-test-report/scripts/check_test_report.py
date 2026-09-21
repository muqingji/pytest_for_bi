#!/usr/bin/env python3
"""测试报告回查工具：结构完整性、AC 覆盖、命令证据、未覆盖声明、边界表述。

检查项：
1. 必要章节：测试环境 / 测试命令 / 结果 / 已知限制是否齐全
2. 命令证据：每个命令块附近是否有结果或输出说明
3. AC 覆盖：验收标准里的 AC 是否在报告或用例文件中被追踪，或显式声明为未覆盖
4. 未勾选项：未演示的演示项是否写明原因
5. 状态一致性：声称全部通过时是否仍存在失败或未执行标记
6. 边界表述：Mock / 本地环境结论是否被表述为真实渠道或线上指标
7. 未执行表述：是否有把未执行检查写成通过的表述

用法：
    python3 check_test_report.py --report docs/test-report.md \
        --ac 需求拆解/验收标准/验收标准.md \
        --cases docs/test-cases.md
退出码：0 无阻塞项；1 存在阻塞项（可用 --fail-on 调整）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BLOCK = "阻塞"
ADVICE = "建议"

AC_RE = re.compile(r"(?<![A-Za-z0-9])(AC)-(\d{2,3})(?![0-9])", re.I)
AC_RANGE_RE = re.compile(
    r"(?<![A-Za-z0-9])AC-(\d{2,3})\s*(?:~|-|—|至|到|,|、|，|和|及)+\s*(?:AC-)?(\d{2,3})(?![0-9])",
    re.I,
)
CODE_FENCE_RE = re.compile(r"^\s*```+\s*([A-Za-z0-9_+-]*)")
UNCHECKED_RE = re.compile(r"^\s*[-*]\s*\[ \]\s*(.+)$")
UNCOVERED_WORDS = re.compile(
    r"未覆盖|未进入本轮|不在本轮|后续切片|后续功能|待实现|未实现|未执行|未联调|未验证|属于后续"
)
MOCK_WORDS = re.compile(r"Mock|mock|Fake|fake|Fixture|fixture|SQLite|sqlite|本地内存|进程内|桩")
REAL_CLAIM_WORDS = re.compile(r"真实|生产|线上|已联调|真实渠道|真实 Push|端到端验证通过")
REAL_CLAIM_HEDGE_WORDS = re.compile(r"不代表|不验证|不能证明|未联调|未接入真实|未验证|未实测")
METRIC_CLAIM_WORDS = re.compile(
    r"打开率|到达率|完成率|留存率|转化率|投诉率|卸载率"
)
METRIC_HEDGE_WORDS = re.compile(r"不代表|不验证|不能证明|未验证|未实测|仅本地|Mock|Fixture")
PASS_CLAIM_WORDS = re.compile(r"全部通过|全部已执行包通过|0\s*个?失败|失败数?\s*[:：]?\s*0|无失败")
FAIL_MARK_WORDS = re.compile(r"\bFAIL\b|失败项|失败数?\s*[:：]?\s*[1-9]|未执行|跳过")
UNEXECUTED_AS_PASS = re.compile(r"未执行[^\n]{0,20}(通过|已通过)|跳过[^\n]{0,10}视为通过")

REQUIRED_SECTIONS = [
    ("测试环境", r"测试环境"),
    ("测试命令", r"测试命令|执行命令"),
    ("测试结果", r"测试结果|自动化测试结果|结果"),
    ("已知限制", r"已知限制|限制与风险|未覆盖范围"),
]


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def expand_ac_ids(text: str) -> set[str]:
    ids = {f"AC-{m.group(2).zfill(3)}" for m in AC_RE.finditer(text)}
    for match in AC_RANGE_RE.finditer(text):
        start, end = int(match.group(1)), int(match.group(2))
        if start <= end:
            ids.update(f"AC-{n:03d}" for n in range(start, end + 1))
    return ids


def parse_acs(lines: list[str]) -> list[dict]:
    acs: list[dict] = []
    heading = re.compile(r"^(#{2,6})\s*(AC-(\d{2,3}))\s*[:：]?\s*(.*)$", re.I)
    for index, line in enumerate(lines):
        match = heading.match(line.strip())
        if not match:
            continue
        acs.append({"id": f"AC-{match.group(3).zfill(3)}", "title": match.group(4).strip(), "line": index + 1})
    return acs


def check_sections(report_lines: list[str]) -> list[dict]:
    text = "\n".join(report_lines)
    findings: list[dict] = []
    missing = [name for name, pattern in REQUIRED_SECTIONS if not re.search(pattern, text)]
    if missing:
        findings.append(
            {
                "severity": BLOCK,
                "title": "报告缺少必要章节",
                "detail": "缺少以下内容时结论无法复核：" + "、".join(missing) + "。",
                "evidence": missing,
            }
        )
    return findings


def check_command_evidence(report_lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    fence_indexes = [i for i, line in enumerate(report_lines) if CODE_FENCE_RE.match(line)]
    for start in range(0, len(fence_indexes) - 1, 2):
        block_start, block_end = fence_indexes[start], fence_indexes[start + 1]
        commands = [line.strip() for line in report_lines[block_start + 1 : block_end] if line.strip()]
        if not commands:
            continue
        window = "\n".join(report_lines[block_end + 1 : block_end + 12])
        if not re.search(r"通过|失败|输出|结果|ok\b|FAIL|错误", window):
            findings.append(
                {
                    "severity": ADVICE,
                    "title": "命令缺少结果说明",
                    "detail": "命令块后未看到结果或输出说明，无法确认是否执行过。",
                    "evidence": commands[:2],
                }
            )
    return findings


def check_ac_coverage(report_lines: list[str], acs: list[dict], case_lines: list[str]) -> list[dict]:
    if not acs:
        return []
    report_text = "\n".join(report_lines)
    tracked = expand_ac_ids(report_text) | expand_ac_ids("\n".join(case_lines))
    missing = [ac["id"] for ac in acs if ac["id"] not in tracked]
    findings: list[dict] = []
    if missing:
        findings.append(
            {
                "severity": BLOCK,
                "title": "AC 未建立追踪关系",
                "detail": "以下 AC 既没有出现在测试报告的覆盖矩阵，也没有被显式声明为未覆盖，结论无法对应验收标准。"
                "请补充用例与结果，或用“未覆盖 + 原因 + 后续切片”登记。",
                "evidence": missing,
            }
        )
    return findings


def check_unchecked_items(report_lines: list[str]) -> list[dict]:
    evidences: list[str] = []
    for index, line in enumerate(report_lines):
        match = UNCHECKED_RE.match(line)
        if not match:
            continue
        if UNCOVERED_WORDS.search(line):
            continue
        evidences.append(f"{index + 1}: {line.strip()}")
    if not evidences:
        return []
    return [
        {
            "severity": ADVICE,
            "title": "未勾选项缺少原因",
            "detail": "未演示或未执行的项必须写明原因和承接的后续切片。",
            "evidence": evidences,
        }
    ]


def check_status_consistency(report_lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    text = "\n".join(report_lines)
    for index, line in enumerate(report_lines):
        if not PASS_CLAIM_WORDS.search(line):
            continue
        window_start = max(index - 12, 0)
        nearby = "\n".join(report_lines[window_start : index + 12])
        undocumented = [
            item
            for item in report_lines[window_start : index + 12]
            if UNCHECKED_RE.match(item) and not UNCOVERED_WORDS.search(item)
        ]
        if FAIL_MARK_WORDS.search(nearby) or undocumented:
            findings.append(
                {
                    "severity": ADVICE,
                    "title": "通过结论与未完成项并存",
                    "detail": "同一区域既声称全部通过，又存在失败、跳过或未勾选项，需要分别写清状态。",
                    "evidence": [f"{index + 1}: {line.strip()}"],
                }
            )
            break
    for index, line in enumerate(report_lines):
        if UNEXECUTED_AS_PASS.search(line):
            findings.append(
                {
                    "severity": BLOCK,
                    "title": "未执行检查被表述为通过",
                    "detail": "未执行或跳过的检查不得写成通过，必须标注未执行。",
                    "evidence": [f"{index + 1}: {line.strip()}"],
                }
            )
    return findings


def check_boundaries(report_lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    for index, line in enumerate(report_lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        if MOCK_WORDS.search(stripped) and REAL_CLAIM_WORDS.search(stripped) and not REAL_CLAIM_HEDGE_WORDS.search(stripped):
            findings.append(
                {
                    "severity": BLOCK,
                    "title": "Mock 环境被表述为真实联调",
                    "detail": "使用 Mock、Fixture 或本地数据库时，不能表述为真实渠道或线上已联调。",
                    "evidence": [f"{index + 1}: {stripped}"],
                }
            )
        if METRIC_CLAIM_WORDS.search(stripped) and re.search(r"提升|达到|上升|高于|降至", stripped):
            if not METRIC_HEDGE_WORDS.search(stripped):
                findings.append(
                    {
                        "severity": BLOCK,
                        "title": "缺少依据的线上指标结论",
                        "detail": "本地 Demo 与 Mock 结果不能作为线上指标结论；如需保留，请标注不代表线上效果。",
                        "evidence": [f"{index + 1}: {stripped}"],
                    }
                )
    return findings


def render_markdown(report_path: Path, ac_path: Path | None, findings: list[dict]) -> str:
    blocks = [f for f in findings if f["severity"] == BLOCK]
    advices = [f for f in findings if f["severity"] == ADVICE]
    out = [
        "# 测试报告回查报告",
        "",
        f"- 被检查报告：`{report_path}`",
        f"- 验收标准：`{ac_path}`" if ac_path else "- 验收标准：未提供（跳过 AC 覆盖检查）",
        f"- 阻塞项：{len(blocks)}",
        f"- 建议项：{len(advices)}",
        "",
    ]
    for title, group in (("## 阻塞项", blocks), ("## 建议项", advices)):
        out.append(title if group else f"{title}（无）")
        out.append("")
        for finding in group:
            out.append(f"### {finding['title']}")
            out.append(f"- 说明：{finding['detail']}")
            if finding.get("evidence"):
                out.append("- 证据：" + "；".join(str(item) for item in finding["evidence"]))
            out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="测试报告回查")
    parser.add_argument("--report", required=True, help="待检查的测试报告 Markdown")
    parser.add_argument("--ac", action="append", default=[], help="验收标准 Markdown，可多次传入")
    parser.add_argument("--cases", action="append", default=[], help="用例矩阵 Markdown，可多次传入")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--fail-on", choices=["blocking", "any", "none"], default="blocking")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"找不到测试报告文件：{report_path}", file=sys.stderr)
        return 2

    report_lines = read_lines(report_path)

    acs: list[dict] = []
    ac_path: Path | None = None
    for ac_arg in args.ac:
        path = Path(ac_arg)
        if not path.is_file():
            print(f"找不到验收标准文件：{path}", file=sys.stderr)
            return 2
        ac_path = path
        acs.extend(parse_acs(read_lines(path)))

    case_lines: list[str] = []
    for case_arg in args.cases:
        path = Path(case_arg)
        if not path.is_file():
            print(f"找不到用例文件：{path}", file=sys.stderr)
            return 2
        case_lines.extend(read_lines(path))

    findings: list[dict] = []
    findings += check_sections(report_lines)
    findings += check_ac_coverage(report_lines, acs, case_lines)
    findings += check_command_evidence(report_lines)
    findings += check_unchecked_items(report_lines)
    findings += check_status_consistency(report_lines)
    findings += check_boundaries(report_lines)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "report": str(report_path),
                    "ac": str(ac_path) if ac_path else None,
                    "ac_count": len(acs),
                    "findings": findings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_markdown(report_path, ac_path, findings))

    has_block = any(finding["severity"] == BLOCK for finding in findings)
    if args.fail_on == "blocking" and has_block:
        return 1
    if args.fail_on == "any" and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
