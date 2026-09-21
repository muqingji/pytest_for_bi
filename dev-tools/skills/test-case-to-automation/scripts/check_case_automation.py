#!/usr/bin/env python3
"""测试用例转自动化的确定性回查。

机械检查四类事实：

1. 覆盖：测试用例文档里的每条 TC 都且只在「映射表」「条件可自动化清单」「不可自动化清单」里出现一次；
2. 用例数据：tests/cases/*.json 的结构、id 唯一性、预期字段与枚举是否能在 IDL 里找到、fixture 是否存在；
3. 追踪：ac/fr 标签能否在验收标准与需求文档里找到，用例文档的「自动化映射」是否已回填；
4. 对应：每个用例数据文件都有对应主体文件，且主体文件加载的是同名主体。

只做机械检查，不判断业务对错，也不替代门禁 A / 门禁 B 的人工确认。

用法：
    python3 check_case_automation.py --project-root code-repo-analysis/智能提醒助手
    python3 check_case_automation.py --stage mapping      # 门禁 A 前：只查映射报告与 TC 覆盖
    python3 check_case_automation.py --json

退出码：0 无阻塞项，1 有阻塞项，2 输入缺失。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

STAGES = ("mapping", "delivered")
REPORT_SECTIONS = ("映射表", "条件可自动化清单", "不可自动化清单", "数据缺口清单", "契约核对表", "回查结论")
MAPPING_COVERAGE_SECTIONS = ("映射表", "条件可自动化清单", "不可自动化清单")

TC_RE = re.compile(r"^###\s+TC-(\d+)\s*(.*)$")
FIELD_RE = re.compile(r"^-\s*([^：:]+)[：:]\s*(.*)$")
SOURCE_RE = re.compile(r"([^\s、,，|]+?\.md):(\d+)")
FR_RE = re.compile(r"FR-\d{3}")
AC_RE = re.compile(r"AC-\d{3}")
CASE_ID_RE = re.compile(r"[A-Z]{2,6}-\d{3}")
IGNORED_SUBJECT_PREFIXES = ("test_harness", "test_pipeline")


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


# --------------------------------------------------------------------------------------
# 极简 YAML 解析：只覆盖本仓库 IDL 用到的写法（映射、序列、块标量、行内序列、引号标量）。
# 目的是取字段名与枚举，不追求通用性。
# --------------------------------------------------------------------------------------


def _scalar(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(item) for item in inner.split(",")] if inner else []
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _parse_list(items: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(items):
        line_indent, content = items[index]
        if line_indent != indent or not content.startswith("-"):
            break
        body = content[1:].lstrip()
        if body == "":
            child, index = _parse_block(items, index + 1, items[index + 1][0])
            result.append(child)
            continue
        if ":" not in body:
            result.append(_scalar(body))
            index += 1
            continue
        key, _, value = body.partition(":")
        item: dict[str, Any] = {key.strip().strip("'\""): _scalar(value.strip())}
        index += 1
        while index < len(items) and items[index][0] > indent:
            sub_key, _, sub_value = items[index][1].partition(":")
            if sub_key.strip():
                item[sub_key.strip().strip("'\"")] = _scalar(sub_value.strip())
            index += 1
        result.append(item)
    return result, index


def _parse_mapping(items: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    node: dict[str, Any] = {}
    while index < len(items):
        line_indent, content = items[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ValueError(f"无法解析的缩进（第 {index} 项）：{content!r}")
        key, sep, value = content.partition(":")
        if not sep:
            index += 1
            continue
        key = key.strip().strip("'\"")
        value = value.strip()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            lines: list[str] = []
            index += 1
            while index < len(items) and items[index][0] > indent:
                lines.append(items[index][1])
                index += 1
            node[key] = "\n".join(lines)
        elif value == "":
            child, index = _parse_block(items, index + 1, items[index + 1][0])
            node[key] = child
        else:
            node[key] = _scalar(value)
            index += 1
    return node, index


def _parse_block(items: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if items[index][1].startswith("-"):
        return _parse_list(items, index, indent)
    return _parse_mapping(items, index, indent)


def parse_yaml(text: str) -> dict[str, Any]:
    items: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        items.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    if not items:
        return {}
    node, _ = _parse_block(items, 0, items[0][0])
    return node if isinstance(node, dict) else {}


class IdlIndex:
    """从 IDL 取：状态码对应的响应 schema、schema 字段、schema 枚举。"""

    def __init__(self, document: dict[str, Any]) -> None:
        self.schemas: dict[str, Any] = (document.get("components") or {}).get("schemas") or {}
        self.responses: dict[str, Any] = (document.get("components") or {}).get("responses") or {}
        self.paths: dict[str, Any] = document.get("paths") or {}

    def _ref_name(self, node: Any) -> str | None:
        if isinstance(node, dict) and isinstance(node.get("$ref"), str):
            ref = node["$ref"]
            return ref.rsplit("/", 1)[-1] if ref.startswith("#/") else None
        return None

    def resolve(self, node: Any, hops: int = 4) -> dict[str, Any]:
        while hops > 0:
            name = self._ref_name(node)
            if not name:
                return node if isinstance(node, dict) else {}
            node = self.schemas.get(name) or {}
            hops -= 1
        return node if isinstance(node, dict) else {}

    def response_schema(self, path: str, method: str, status_code: str) -> dict[str, Any] | None:
        operation = self.paths.get(path)
        if not isinstance(operation, dict):
            return None
        method_node = operation.get(method.lower())
        if not isinstance(method_node, dict):
            return None
        response = (method_node.get("responses") or {}).get(status_code)
        if response is None:
            return None
        reference = self._ref_name(response)
        if reference:
            response = self.responses.get(reference)
            if response is None:
                return None
        media = ((response or {}).get("content") or {}).get("application/json") or {}
        schema = media.get("schema")
        return self.resolve(schema) if schema is not None else None

    def enum_of(self, node: Any) -> list[Any] | None:
        enum = self.resolve(node).get("enum")
        return enum if isinstance(enum, list) else None


# --------------------------------------------------------------------------------------
# 文档解析
# --------------------------------------------------------------------------------------


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_entries(text: str, prefix: str) -> list[dict[str, Any]]:
    """把 markdown 解析成 `### XX-0NN` 条目：条目号、标题、行号与顶层字段。"""
    entry_re = re.compile(rf"^###\s+{prefix}-(\d+)\s*(.*)$")
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        match = entry_re.match(stripped)
        if match:
            current = {"id": f"{prefix}-{match.group(1)}", "title": match.group(2).strip(), "line": lineno, "fields": {}}
            entries.append(current)
            continue
        if current is None:
            continue
        if stripped.startswith("### "):
            current = None
            continue
        if not stripped:
            continue
        if len(raw) - len(raw.lstrip(" ")) != 0:
            continue
        field = FIELD_RE.match(stripped)
        if field:
            current["fields"][field.group(1).strip()] = field.group(2).strip()
    return entries


def parse_tables(text: str) -> dict[str, list[dict[str, str]]]:
    """按小节切分，把每个小节里的 markdown 表格解析成 header -> cell 的列表。"""
    sections: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    header: list[str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        heading = re.match(r"^#{2,3}\s*(.*)$", line)
        if heading:
            title = heading.group(1).strip()
            current = next((name for name in REPORT_SECTIONS if name in title), None)
            header = None
            if current:
                sections.setdefault(current, [])
            continue
        if current is None or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if header is None:
            header = cells
            continue
        sections[current].append({header[i]: (cells[i] if i < len(cells) else "") for i in range(len(header))})
    return sections


def cell(row: dict[str, str], *names: str) -> str:
    for key, value in row.items():
        if any(name.lower() in key.lower() for name in names):
            return value
    return ""


def first_case_id(value: str) -> str:
    match = CASE_ID_RE.search(value)
    return match.group(0) if match else ""


def resolve_source(reference: str, project_root: Path, repo_root: Path) -> Path | None:
    match = SOURCE_RE.search(reference)
    if not match:
        return None
    relative = match.group(1)
    for base in (project_root, repo_root):
        candidate = base / relative
        if candidate.is_file():
            return candidate
    for candidate in repo_root.rglob(Path(relative).name):
        if candidate.is_file():
            return candidate
    return None


# --------------------------------------------------------------------------------------
# 各项检查
# --------------------------------------------------------------------------------------


def check_report_shape(report_path: Path, findings: Findings) -> dict[str, list[dict[str, str]]]:
    text = read_text(report_path)
    label = "测试方案/自动化映射报告.md"
    if not text.strip():
        findings.block(label, "报告为空")
        return {}
    for section in REPORT_SECTIONS:
        if section not in text:
            findings.block(label, f"缺少必需小节：{section}")
    if "状态：" not in text:
        findings.block(label, "缺少 `> 状态：` 行，无法判断门禁状态")
    elif "门禁 B" not in text:
        findings.suggest(label, "尚未记录门禁 B 复核结论")
    return parse_tables(text)


def check_tc_coverage(
    tc_entries: list[dict[str, Any]],
    tables: dict[str, list[dict[str, str]]],
    findings: Findings,
    project_root: Path,
    repo_root: Path,
) -> dict[str, list[dict[str, str]]]:
    """每条 TC 必须出现在映射、条件可自动化、不可自动化三张清单之一，且互斥。"""
    label = "测试方案/自动化映射报告.md"
    covered: dict[str, str] = {}
    for section in MAPPING_COVERAGE_SECTIONS:
        for row in tables.get(section, []):
            raw_tc = cell(row, "TC")
            tc_id = raw_tc.split()[0].strip() if raw_tc.split() else ""
            if not re.fullmatch(r"TC-\d{3}", tc_id):
                findings.block(label, f"「{section}」有一行的 TC 列不是合法编号：{raw_tc!r}")
                continue
            if tc_id in covered:
                findings.block(label, f"{tc_id} 同时出现在「{covered[tc_id]}」与「{section}」，三张清单必须互斥")
                continue
            covered[tc_id] = section

    known = {entry["id"] for entry in tc_entries}
    for entry in tc_entries:
        if entry["id"] not in covered:
            findings.block(
                "测试方案/测试用例.md",
                f"{entry['id']}（第 {entry['line']} 行）未出现在「映射表」「条件可自动化清单」「不可自动化清单」任何一处",
            )
    for tc_id, section in covered.items():
        if tc_id not in known:
            findings.block(label, f"「{section}」引用了测试用例文档里不存在的 {tc_id}")

    for section in ("条件可自动化清单", "不可自动化清单"):
        for row in tables.get(section, []):
            if not cell(row, "原因", "依赖", "解锁条件"):
                findings.block(label, f"「{section}」的 {cell(row, 'TC')} 没写原因或依赖")

    mapping: dict[str, list[dict[str, str]]] = {}
    for row in tables.get("映射表", []):
        tc_id = cell(row, "TC").split()[0].strip() if cell(row, "TC").split() else ""
        reference = cell(row, "依据", "来源")
        if not resolve_source(reference, project_root, repo_root):
            findings.block(label, f"「映射表」{tc_id or '某行'} 的依据无法解析成 `文件:行号`：{reference!r}")
        if not first_case_id(cell(row, "case", "用例")):
            findings.block(label, f"「映射表」{tc_id or '某行'} 没有可识别的 case id")
        mapping.setdefault(tc_id, []).append(row)
    return mapping


def check_case_files(cases_dir: Path, findings: Findings, seen_ids: dict[str, str]) -> dict[str, dict[str, Any]]:
    subjects: dict[str, dict[str, Any]] = {}
    files = sorted(path for path in cases_dir.glob("*.json") if not path.name.startswith("_"))
    if not files:
        findings.block("tests/cases", "没有找到任何用例数据文件")
        return subjects

    for path in files:
        label = f"tests/cases/{path.name}"
        try:
            raw = json.loads(read_text(path))
        except json.JSONDecodeError as error:
            findings.block(label, f"不是合法 JSON：{error}")
            continue
        if not isinstance(raw, dict):
            findings.block(label, "顶层必须是对象")
            continue
        subject = raw.get("subject")
        if subject != path.stem:
            findings.block(label, f"`subject` 为 {subject!r}，与文件名 {path.stem!r} 不一致")
            continue
        endpoint = raw.get("endpoint")
        if not isinstance(endpoint, dict) or not endpoint.get("method") or not endpoint.get("path"):
            findings.block(label, "`endpoint` 必须含 method 与 path")
            continue
        cases = raw.get("cases")
        if not isinstance(cases, list) or not cases:
            findings.block(label, "`cases` 必须是非空数组")
            continue

        for index, case in enumerate(cases):
            where = f"{label}#cases[{index}]"
            for key in ("id", "name"):
                if not case.get(key):
                    findings.block(where, f"缺少必填字段 {key}")
            case_id = str(case.get("id", ""))
            if not case_id:
                continue
            if not re.fullmatch(r"[A-Z]{2,6}-\d{3}", case_id):
                findings.suggest(label, f"用例 id {case_id!r} 不符合「主体前缀-三位序号」约定")
            if case_id in seen_ids:
                findings.block(where, f"用例 id {case_id} 与 {seen_ids[case_id]} 重复")
            else:
                seen_ids[case_id] = where
            if str(case.get("match", "subset")) not in ("subset", "exact"):
                findings.block(where, f"`match` 只支持 subset 或 exact，当前为 {case.get('match')!r}")
            if case.get("pending") and not str(case.get("pending_reason", "")).strip():
                findings.block(where, "标记了 `pending` 但没有写 `pending_reason`")
            if "steps" in case:
                steps = case.get("steps")
                if not isinstance(steps, list) or not steps:
                    findings.block(where, "`steps` 必须是非空数组")
                    continue
                units = [(f"{where}.steps[{i}]", step) for i, step in enumerate(steps)]
            else:
                units = [(where, case)]
            for unit_where, unit in units:
                for key in ("request", "expected"):
                    if key not in unit:
                        findings.block(unit_where, f"缺少必填字段 {key}")
                if isinstance(unit.get("request"), dict) and "body" not in unit["request"]:
                    findings.block(unit_where, "`request` 必须含 body（可显式写 null）")
                expected = unit.get("expected")
                if isinstance(expected, dict):
                    for key in ("status_code", "body"):
                        if key not in expected:
                            findings.block(unit_where, f"`expected` 缺少必填字段 {key}")
                elif "expected" in unit:
                    findings.block(unit_where, "`expected` 必须是对象")

        subjects[path.stem] = {"path": path, "raw": raw}
    return subjects


def check_idl_fields(subjects: dict[str, dict[str, Any]], idl: IdlIndex, findings: Findings) -> None:
    """预期字段名必须能在 IDL 响应 schema 里找到；字符串枚举值必须在 IDL 枚举内。"""
    for subject, payload in subjects.items():
        raw = payload["raw"]
        default_method = raw["endpoint"]["method"]
        default_path = raw["endpoint"]["path"]
        for index, case in enumerate(raw["cases"]):
            label = f"tests/cases/{subject}.json#{case.get('id', f'cases[{index}]')}"
            steps = case.get("steps") or [{"request": case.get("request") or {}, "expected": case.get("expected") or {}}]
            for step_index, step in enumerate(steps, start=1):
                request = step.get("request") or {}
                expected = step.get("expected") or {}
                method = str(request.get("method") or default_method)
                path = str(request.get("path") or default_path)
                if re.search(r"\{step\d+\.", path):
                    continue
                status_code = str(expected.get("status_code"))
                schema = idl.response_schema(path, method, status_code)
                where = label if len(steps) == 1 else f"{label} 步骤 {step_index}"
                if schema is None:
                    findings.suggest(where, f"IDL 里找不到 {method} {path} 的 {status_code} 响应 schema，字段未校验")
                    continue
                body = expected.get("body")
                if not isinstance(body, dict):
                    continue
                properties = schema.get("properties") or {}
                for field, value in body.items():
                    if field not in properties:
                        findings.block(where, f"IDL 的 {status_code} 响应 schema 里没有字段 {field!r}")
                        continue
                    if not isinstance(value, str) or value == "$any":
                        continue
                    allowed = idl.enum_of(properties[field])
                    if allowed is not None and value not in allowed:
                        findings.block(where, f"字段 {field} 的取值 {value!r} 不在 IDL 枚举 {allowed} 内")


def check_fixtures(subjects: dict[str, dict[str, Any]], fixtures: dict[str, Any], findings: Findings) -> None:
    label = "testenv/fixtures/users.json"
    users = fixtures.get("users")
    if not isinstance(users, list):
        findings.block(label, "`users` 必须是数组")
        return
    known = {str(user.get("user_id")) for user in users if isinstance(user, dict)}
    if len(known) != len(users):
        findings.block(label, "存在重复的 user_id；每个 user_id 只允许一种确定状态")
    for subject, payload in subjects.items():
        for index, case in enumerate(payload["raw"]["cases"]):
            fixture = (case.get("scenario") or {}).get("fixture")
            if fixture and fixture not in known:
                findings.block(
                    f"tests/cases/{subject}.json#{case.get('id', f'cases[{index}]')}",
                    f"`scenario.fixture` 指向的 {fixture!r} 不在 {label} 里",
                )


def check_traceability(
    subjects: dict[str, dict[str, Any]],
    ac_ids: set[str],
    requirement_fr_ids: set[str],
    findings: Findings,
) -> None:
    for subject, payload in subjects.items():
        for index, case in enumerate(payload["raw"]["cases"]):
            where = f"tests/cases/{subject}.json#{case.get('id', f'cases[{index}]')}"
            for ac in case.get("ac") or []:
                if ac_ids and ac not in ac_ids:
                    findings.block(where, f"标签 ac={ac!r} 在验收标准里找不到")
            for fr in case.get("fr") or []:
                if not FR_RE.fullmatch(str(fr)):
                    findings.block(where, f"标签 fr={fr!r} 不是 FR-0NN 形式")
                elif requirement_fr_ids and fr not in requirement_fr_ids:
                    findings.block(where, f"标签 fr={fr!r} 在 PRD / 测试方案里找不到")


def check_subject_files(subjects_dir: Path, subjects: dict[str, dict[str, Any]], findings: Findings) -> None:
    for subject in subjects:
        name = f"tests/subjects/test_{subject}.py"
        path = subjects_dir / f"test_{subject}.py"
        if not path.is_file():
            findings.block(name, f"用例数据 {subject}.json 没有对应的主体文件")
            continue
        text = read_text(path)
        if f'load_subject("{subject}")' not in text:
            findings.block(name, f"没有加载同名主体 {subject!r}")
        if "@pytest.mark.subject" not in text:
            findings.block(name, "缺少 `@pytest.mark.subject` 标记")
    for path in sorted(subjects_dir.glob("test_*.py")):
        if path.stem.startswith(IGNORED_SUBJECT_PREFIXES) or path.stem[len("test_"):] in subjects:
            continue
        findings.suggest(
            f"tests/subjects/{path.name}",
            "没有同名用例数据文件；若它属于自检或环境主体可忽略，否则可能是文件名写错",
        )


def check_backfill(
    tc_entries: list[dict[str, Any]],
    mapping: dict[str, list[dict[str, str]]],
    case_ids: set[str],
    findings: Findings,
) -> None:
    label = "测试方案/测试用例.md"
    for entry in tc_entries:
        value = entry["fields"].get("自动化映射", "")
        if not value:
            findings.block(label, f"{entry['id']}（第 {entry['line']} 行）缺少「自动化映射」字段")
            continue
        if value.strip() in ("待实现", "待补", "-", "无"):
            findings.block(label, f"{entry['id']} 的「自动化映射」仍是 {value.strip()!r}，没有回填")
            continue
        for referenced in CASE_ID_RE.findall(value):
            if referenced not in case_ids:
                findings.block(label, f"{entry['id']} 的「自动化映射」引用了不存在的 case id {referenced}")
        if entry["id"] not in mapping:
            findings.suggest(label, f"{entry['id']} 已回填自动化映射，但「映射表」里没有对应行")


def check_mapping_references(
    subjects: dict[str, dict[str, Any]],
    mapping: dict[str, list[dict[str, str]]],
    case_ids: set[str],
    findings: Findings,
) -> None:
    """映射表引用的 case id 必须存在；带 tc 字段的用例必须被映射表引用。"""
    referenced: set[str] = set()
    for rows in mapping.values():
        for row in rows:
            referenced.update(CASE_ID_RE.findall(cell(row, "case", "用例")))
    for case_id in sorted(referenced - case_ids):
        findings.block("测试方案/自动化映射报告.md", f"「映射表」引用的 case id {case_id} 在 tests/cases 里不存在")
    for subject, payload in subjects.items():
        for case in payload["raw"]["cases"]:
            case_id = str(case.get("id", ""))
            tc_field = case.get("tc")
            if not tc_field:
                continue
            if str(tc_field) not in mapping:
                findings.block(
                    f"tests/cases/{subject}.json#{case_id}",
                    f"用例声明的 tc={tc_field} 不在「映射表」的 TC 列内",
                )
            elif case_id not in referenced:
                findings.block(
                    f"tests/cases/{subject}.json#{case_id}",
                    f"用例声明了 tc={tc_field}，但「映射表」的 case 列没有引用 {case_id}",
                )


# --------------------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------------------


def locate_project_root(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).resolve()
        return path if path.is_dir() else None
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        target = candidate / "code-repo-analysis" / "智能提醒助手"
        if (target / "tests" / "cases").is_dir():
            return target
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="测试用例转自动化回查")
    parser.add_argument("--project-root", default=None, help="智能提醒助手目录，默认自动定位")
    parser.add_argument("--stage", choices=STAGES, default="delivered", help="mapping 只查映射报告，delivered 全量检查")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = parser.parse_args()

    project_root = locate_project_root(args.project_root)
    if project_root is None:
        print("未找到智能提醒助手目录，请用 --project-root 指定", file=sys.stderr)
        return 2
    repo_root = project_root.parents[1]

    report_path = project_root / "测试方案" / "自动化映射报告.md"
    tc_path = project_root / "测试方案" / "测试用例.md"
    if not report_path.is_file():
        print(f"映射报告不存在：{report_path}", file=sys.stderr)
        return 2
    if not tc_path.is_file():
        print(f"测试用例文档不存在：{tc_path}；本 skill 不从不存在的输入推导用例。", file=sys.stderr)
        return 2

    findings = Findings()
    tables = check_report_shape(report_path, findings)
    tc_entries = parse_entries(read_text(tc_path), "TC")
    if not tc_entries:
        findings.block("测试方案/测试用例.md", "没有解析到任何 `### TC-0NN` 用例条目")
    mapping = check_tc_coverage(tc_entries, tables, findings, project_root, repo_root)

    if args.stage == "mapping":
        return report(summarize(args, tc_entries, findings), findings, args)

    cases_dir = project_root / "tests" / "cases"
    subjects_dir = project_root / "tests" / "subjects"
    if not cases_dir.is_dir() or not subjects_dir.is_dir():
        print(f"用例目录不存在：{cases_dir} 或 {subjects_dir}", file=sys.stderr)
        return 2

    seen_ids: dict[str, str] = {}
    subjects = check_case_files(cases_dir, findings, seen_ids)

    idl_path = project_root / "docs" / "api" / "reminder-service.openapi.yaml"
    if idl_path.is_file():
        try:
            check_idl_fields(subjects, IdlIndex(parse_yaml(read_text(idl_path))), findings)
        except ValueError as error:
            findings.block("docs/api/reminder-service.openapi.yaml", f"IDL 解析失败：{error}")
    else:
        findings.block("docs/api/reminder-service.openapi.yaml", "找不到 IDL，无法校验字段与枚举")

    fixtures_path = project_root / "testenv" / "fixtures" / "users.json"
    if fixtures_path.is_file():
        check_fixtures(subjects, json.loads(read_text(fixtures_path)), findings)
    else:
        findings.block("testenv/fixtures/users.json", "找不到 fixture 种子文件")

    ac_path = project_root / "需求拆解" / "验收标准" / "验收标准.md"
    ac_ids = set(AC_RE.findall(read_text(ac_path))) if ac_path.is_file() else set()
    requirement_text = ""
    for pattern in ("智能提醒助手PRD*.md", "测试方案/测试方案.md", "测试方案/测试场景清单.md"):
        for path in sorted(project_root.glob(pattern)):
            requirement_text += read_text(path)
    requirement_fr_ids = set(FR_RE.findall(requirement_text))

    check_traceability(subjects, ac_ids, requirement_fr_ids, findings)
    check_subject_files(subjects_dir, subjects, findings)
    check_backfill(tc_entries, mapping, set(seen_ids), findings)
    check_mapping_references(subjects, mapping, set(seen_ids), findings)

    return report(summarize(args, tc_entries, findings, subjects), findings, args)


def summarize(args, tc_entries: list[dict[str, Any]], findings: Findings, subjects: dict[str, Any] | None = None) -> dict[str, Any]:
    subjects = subjects or {}
    return {
        "stage": args.stage,
        "tc_count": len(tc_entries),
        "subject_count": len(subjects),
        "case_count": sum(len(payload["raw"]["cases"]) for payload in subjects.values()),
        "blocking": findings.blocking,
        "suggestion": findings.suggestion,
        "pending": findings.pending,
    }


def report(summary: dict[str, Any], findings: Findings, args) -> int:
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if findings.blocking else 0
    print("=" * 60)
    print(
        f"阶段：{summary['stage']}；测试用例 {summary['tc_count']} 条；"
        f"主体 {summary['subject_count']} 个；用例数据 {summary['case_count']} 条"
    )
    print("=" * 60)
    for label, items in (("阻塞项", findings.blocking), ("建议项", findings.suggestion), ("待确认", findings.pending)):
        print(f"\n[{label}] {len(items)} 项")
        for item in items:
            print(f"  - {item}")
    print()
    if findings.blocking:
        print(f"结论：不可交付，阻塞项 {len(findings.blocking)} 项需先修完。")
        return 1
    print("结论：无阻塞项，可进入人工门禁复核。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
