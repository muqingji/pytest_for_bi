#!/usr/bin/env python3
"""缺陷修复记录的确定性回查。

机械检查六类事实：

1. 结构：修复记录是否包含归属、复现、根因、改动清单、回归用例、验证范围、未验证、剩余风险、回滚；
2. 证据：验证范围表的每一行是否都写了结果，命令与结果是否成对；
3. 覆盖率：能否解析「修前 x% → 修后 y%」，且修后不得低于修前；
4. 回归用例：记录里的用例凭据能否在仓库里真实找到（Go 测试函数或 tests/cases 里的 case id）；
5. CR 处置：P0 / P1 的 finding 是否都已修复或关闭，不能留「未修 / 不修 / 遗留」；
6. 不静默：业务接口用例整体 skip 时，必须写明「未获得业务结论」，不能算通过。

只做机械检查，不判断根因对不对，也不替代人工复核。

用法：
    python3 check_fix_record.py --record code-repo-analysis/智能提醒助手/docs/fixes/BUG-001-xxx.md
    python3 check_fix_record.py --record <记录.md> --project-root code-repo-analysis/智能提醒助手 --json

退出码：0 无阻塞项，1 有阻塞项，2 输入缺失。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = ("缺陷归属", "复现", "根因", "改动清单", "回归用例", "验证范围", "未验证", "剩余风险", "回滚")
COVERAGE_BEFORE_RE = re.compile(r"(?:修前|修复前|修改前)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%")
COVERAGE_AFTER_RE = re.compile(r"(?:修后|修复后|修改后)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%")
GO_TEST_FILE_RE = re.compile(r"([A-Za-z0-9_./\-]+_test\.go)")
GO_TEST_FUNC_RE = re.compile(r"\b(Test[A-Za-z0-9_]+)\b")
CASE_REF_RE = re.compile(r"tests/cases/([^/\s#|]+)\.json#([A-Z]{2,6}-\d{3})")
SKIP_MARKERS = ("skip", "跳过", "skipped")
NO_BUSINESS_CONCLUSION = ("未获得业务结论", "没有业务结论", "不出业务结论")
UNFIXED_MARKERS = ("未修", "不修", "待修", "遗留", "未处置", "推迟")


class Findings:
    def __init__(self) -> None:
        self.blocking: list[str] = []
        self.suggestion: list[str] = []
        self.pending: list[str] = []

    def block(self, where: str, message: str) -> None:
        self.blocking.append(f"{where} {message}")

    def suggest(self, where: str, message: str) -> None:
        self.suggestion.append(f"{where} {message}")

    def note(self, where: str, message: str) -> None:
        self.pending.append(f"{where} {message}")


def split_sections(text: str) -> dict[str, str]:
    """按 `## ` 切分，小节名做包含匹配，返回小节名 -> 正文。"""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.*)$", line.strip())
        if heading:
            title = heading.group(1).strip()
            current = next((name for name in REQUIRED_SECTIONS if name in title), None)
            if current is None and re.search(r"\bCR\b|code-review", title, re.I):
                current = "CR"
            if current:
                sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def parse_tables(text: str) -> list[dict[str, str]]:
    """把一段 markdown 里的所有表格行合并返回（按表头映射单元格）。"""
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if header is None:
            header = cells
            continue
        rows.append({header[i]: (cells[i] if i < len(cells) else "") for i in range(len(header))})
    return rows


def cell(row: dict[str, str], *names: str) -> str:
    for key, value in row.items():
        if any(name.lower() in key.lower() for name in names):
            return value
    return ""


def check_structure(text: str, sections: dict[str, str], findings: Findings, label: str) -> None:
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            findings.block(label, f"缺少必需小节：{name}")
        elif not sections[name]:
            findings.block(label, f"小节为空：{name}")
    if "CR" not in sections:
        findings.block(label, "缺少 CR 小节，无法确认已按流程调用 code-review")
    if "复现" in sections and not re.search(r"```|命令|Command|make |go test|pytest", sections["复现"]):
        findings.block(label, "「复现」小节没有给出可执行命令")
    if "改动清单" in sections:
        body = sections["改动清单"]
        if not re.search(r"没有改|未改动|不改|未修改|排除", body):
            findings.suggest(label, "「改动清单」没有声明未改动的范围，无法确认没有影响其他功能")


def check_verification_table(sections: dict[str, str], findings: Findings, label: str) -> list[dict[str, str]]:
    body = sections.get("验证范围", "")
    if not body:
        return []
    rows = parse_tables(body)
    if not rows:
        findings.block(label, "「验证范围」没有可解析的表格")
        return []
    for index, row in enumerate(rows, start=1):
        result = cell(row, "结果", "实际")
        item = cell(row, "层级", "项目", "检查项")
        if not result:
            findings.block(label, f"「验证范围」第 {index} 行（{item or '未命名'}）没有写结果")
        if not cell(row, "命令"):
            findings.suggest(label, f"「验证范围」第 {index} 行（{item or '未命名'}）没有写命令")
    return rows


def check_coverage(rows: list[dict[str, str]], findings: Findings, label: str) -> None:
    target = next((row for row in rows if "覆盖率" in cell(row, "层级", "项目", "检查项")), None)
    if target is None:
        findings.block(label, "「验证范围」缺少覆盖率行，无法确认覆盖率没有下降")
        return
    value = cell(target, "结果", "实际") + " " + cell(target, "命令")
    before = COVERAGE_BEFORE_RE.search(value)
    after = COVERAGE_AFTER_RE.search(value)
    if not before or not after:
        findings.block(label, f"覆盖率行必须写成「修前 x% → 修后 y%」，当前为 {value.strip()!r}")
        return
    before_value, after_value = float(before.group(1)), float(after.group(1))
    if after_value < before_value:
        findings.block(label, f"覆盖率下降：修前 {before_value}% → 修后 {after_value}%")
    else:
        findings.note(label, f"覆盖率未下降：修前 {before_value}% → 修后 {after_value}%")


def check_regression_case(sections: dict[str, str], project_root: Path | None, findings: Findings, label: str) -> None:
    body = sections.get("回归用例", "")
    if not body:
        return
    go_files = GO_TEST_FILE_RE.findall(body)
    go_funcs = GO_TEST_FUNC_RE.findall(body)
    case_refs = CASE_REF_RE.findall(body)
    if not go_files and not case_refs:
        findings.block(label, "「回归用例」没有可定位的凭据：需要 `<文件>_test.go:TestXxx` 或 `tests/cases/<主体>.json#<case id>`")
        return
    if go_files and not go_funcs:
        findings.suggest(label, "「回归用例」给了测试文件但没给测试函数名，无法确认用例真实存在")
    if project_root is None:
        findings.suggest(label, "未提供 --project-root，跳过回归用例存在性校验")
    else:
        for relative in go_files:
            path = resolve_file(relative, project_root)
            if path is None:
                findings.block(label, f"「回归用例」引用的测试文件不存在：{relative}")
                continue
            content = path.read_text(encoding="utf-8")
            for func in go_funcs:
                if f"func {func}(" not in content:
                    findings.block(label, f"「回归用例」引用的 {func} 在 {path.name} 里找不到")
        for subject, case_id in case_refs:
            path = resolve_file(f"tests/cases/{subject}.json", project_root)
            if path is None:
                findings.block(label, f"「回归用例」引用的用例文件不存在：tests/cases/{subject}.json")
                continue
            if f'"{case_id}"' not in path.read_text(encoding="utf-8"):
                findings.block(label, f"「回归用例」引用的 {case_id} 不在 tests/cases/{subject}.json 里")
    if not re.search(r"红|失败|FAIL", body):
        findings.suggest(label, "「回归用例」没有写明修复前是失败的（先红后绿）")
    if not re.search(r"绿|通过|PASS", body):
        findings.suggest(label, "「回归用例」没有写明修复后是通过的")


def check_cr(rows: list[dict[str, str]], sections: dict[str, str], findings: Findings, label: str) -> None:
    body = sections.get("CR", "")
    if not body:
        return
    cr_rows = parse_tables(body)
    if not cr_rows:
        findings.block(label, "「CR」小节没有 finding 表格")
        return
    for index, row in enumerate(cr_rows, start=1):
        severity = cell(row, "级别", "严重级别", "等级").upper()
        disposition = cell(row, "处置", "处理", "状态", "结论")
        finding = cell(row, "finding", "问题", "标题") or f"第 {index} 行"
        if not disposition:
            findings.block(label, f"CR finding「{finding}」没有写处置结论")
            continue
        if "P0" in severity or "P1" in severity:
            if any(marker in disposition for marker in UNFIXED_MARKERS):
                findings.block(label, f"CR 的 {severity} finding「{finding}」处置为 {disposition!r}，P0/P1 必须修完再交付")
            elif not re.search(r"已修|已关闭|已修复|已复验", disposition):
                findings.block(label, f"CR 的 {severity} finding「{finding}」处置不明确：{disposition!r}")


def check_skip_disclosure(
    rows: list[dict[str, str]], sections: dict[str, str], findings: Findings, label: str
) -> None:
    """业务接口用例有 skip 时必须在「未验证」里交代，不能静默算通过。"""
    skipped = False
    for row in rows:
        command = cell(row, "命令")
        result = cell(row, "结果", "实际")
        if "test-api" not in command and "pytest" not in command and "用例" not in command:
            continue
        if any(marker in result.lower() for marker in SKIP_MARKERS):
            skipped = True
    if not skipped:
        return
    unverified = sections.get("未验证", "")
    disclosed = any(phrase in unverified for phrase in NO_BUSINESS_CONCLUSION) or any(
        marker in unverified for marker in ("跳过", "skip", "以及", "pending", "未执行")
    )
    if not disclosed:
        findings.block(
            label,
            "业务接口用例存在 skip，但「未验证」里没有交代这些用例没有执行，不能算通过",
        )


def resolve_file(relative: str, project_root: Path) -> Path | None:
    candidate = project_root / relative
    if candidate.is_file():
        return candidate
    repo_root = project_root.parents[1]
    candidate = repo_root / relative
    if candidate.is_file():
        return candidate
    for found in repo_root.rglob(Path(relative).name):
        if found.is_file():
            return found
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="缺陷修复记录回查")
    parser.add_argument("--record", required=True, help="修复记录 markdown 路径")
    parser.add_argument("--project-root", default=None, help="智能提醒助手目录，用于校验回归用例是否真实存在")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = parser.parse_args()

    record = Path(args.record)
    if not record.is_file():
        print(f"修复记录不存在：{record}", file=sys.stderr)
        return 2
    project_root = Path(args.project_root).resolve() if args.project_root else None
    if project_root is not None and not project_root.is_dir():
        print(f"项目目录不存在：{project_root}", file=sys.stderr)
        return 2

    text = record.read_text(encoding="utf-8")
    label = record.name
    findings = Findings()
    sections = split_sections(text)
    check_structure(text, sections, findings, label)
    rows = check_verification_table(sections, findings, label)
    check_coverage(rows, findings, label)
    check_regression_case(sections, project_root, findings, label)
    check_cr(rows, sections, findings, label)
    check_skip_disclosure(rows, sections, findings, label)

    summary: dict[str, Any] = {
        "record": str(record),
        "section_count": len(sections),
        "verification_rows": len(rows),
        "blocking": findings.blocking,
        "suggestion": findings.suggestion,
        "pending": findings.pending,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if findings.blocking else 0

    print("=" * 60)
    print(f"修复记录：{record}；小节 {len(sections)} 个；验证范围 {len(rows)} 项")
    print("=" * 60)
    for name, items in (("阻塞项", findings.blocking), ("建议项", findings.suggestion), ("待确认", findings.pending)):
        print(f"\n[{name}] {len(items)} 项")
        for item in items:
            print(f"  - {item}")
    print()
    if findings.blocking:
        print(f"结论：记录不可交付，阻塞项 {len(findings.blocking)} 项需先补完。")
        return 1
    print("结论：无阻塞项，可进入人工复核。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
