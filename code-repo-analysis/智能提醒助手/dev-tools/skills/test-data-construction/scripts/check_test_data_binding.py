#!/usr/bin/env python3
"""回查 pytest case、test_data 与服务端 Fixture 的强绑定关系。"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DATA_REF = re.compile(r"\{data\.([A-Za-z0-9_.\-]+)\}")
EXACT_DATA_REF = re.compile(r"^\{data\.([A-Za-z0-9_.\-]+)\}$")


@dataclass
class Findings:
    blocking: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def block(self, where: str, message: str) -> None:
        self.blocking.append(f"{where}: {message}")

    def suggest(self, where: str, message: str) -> None:
        self.suggestions.append(f"{where}: {message}")


def locate_project_root(raw: str | None) -> Path | None:
    candidates = [Path(raw).resolve()] if raw else [Path.cwd().resolve(), *Path.cwd().resolve().parents]
    for candidate in candidates:
        if (candidate / "tests" / "cases").is_dir() and (candidate / "testenv" / "fixtures").is_dir():
            return candidate
        nested = candidate / "code-repo-analysis" / "智能提醒助手"
        if (nested / "tests" / "cases").is_dir():
            return nested
    return None


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: JSON 读取失败：{error}") from error


def resolve_data(data: dict[str, Any], key_path: str) -> Any:
    current: Any = data
    for part in key_path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(part)
        current = current[part]
    return current


def collect_refs(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(DATA_REF.findall(value))
    if isinstance(value, dict):
        refs: set[str] = set()
        for item in value.values():
            refs |= collect_refs(item)
        return refs
    if isinstance(value, list):
        refs = set()
        for item in value:
            refs |= collect_refs(item)
        return refs
    return set()


def materialize(value: Any, data: dict[str, Any]) -> Any:
    if isinstance(value, str):
        exact = EXACT_DATA_REF.fullmatch(value)
        if exact:
            return copy.deepcopy(resolve_data(data, exact.group(1)))
        return DATA_REF.sub(lambda match: str(resolve_data(data, match.group(1))), value)
    if isinstance(value, dict):
        return {key: materialize(item, data) for key, item in value.items()}
    if isinstance(value, list):
        return [materialize(item, data) for item in value]
    return value


def case_units(case: dict[str, Any]) -> list[dict[str, Any]]:
    steps = case.get("steps")
    return steps if isinstance(steps, list) else [case]


def load_cases(cases_dir: Path, findings: Findings) -> tuple[dict[str, tuple[str, dict[str, Any]]], dict[str, int]]:
    cases: dict[str, tuple[str, dict[str, Any]]] = {}
    counts = {"files": 0, "cases": 0}
    for path in sorted(cases_dir.glob("*.json")):
        counts["files"] += 1
        try:
            payload = load_json(path)
        except ValueError as error:
            findings.block(path.as_posix(), str(error))
            continue
        raw_cases = payload.get("cases") if isinstance(payload, dict) else None
        if not isinstance(raw_cases, list):
            findings.block(path.as_posix(), "缺少 cases 数组")
            continue
        for index, case in enumerate(raw_cases):
            where = f"tests/cases/{path.name}#cases[{index}]"
            if not isinstance(case, dict) or not str(case.get("id", "")).strip():
                findings.block(where, "case 必须是对象且包含 id")
                continue
            case_id = str(case["id"])
            counts["cases"] += 1
            if case_id in cases:
                findings.block(where, f"case id 与 {cases[case_id][0]} 重复：{case_id}")
                continue
            cases[case_id] = (f"tests/cases/{path.name}#{case_id}", case)
    return cases, counts


def load_fixtures(path: Path, findings: Findings) -> dict[str, dict[str, Any]]:
    try:
        payload = load_json(path)
    except ValueError as error:
        findings.block(path.as_posix(), str(error))
        return {}
    users = payload.get("users") if isinstance(payload, dict) else None
    if not isinstance(users, list):
        findings.block("testenv/fixtures/users.json", "缺少 users 数组")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, user in enumerate(users):
        where = f"testenv/fixtures/users.json#users[{index}]"
        if not isinstance(user, dict) or not str(user.get("user_id", "")).strip():
            findings.block(where, "Fixture 必须是对象且包含 user_id")
            continue
        user_id = str(user["user_id"])
        if user_id in result:
            findings.block(where, f"user_id 重复：{user_id}")
            continue
        result[user_id] = user
    return result


def check_bound_case(
    case_id: str,
    where: str,
    case: dict[str, Any],
    fixtures: dict[str, dict[str, Any]],
    fixture_owners: dict[str, str],
    findings: Findings,
) -> None:
    data = case.get("test_data")
    if not isinstance(data, dict) or not data:
        findings.block(where, "目标 case 缺少非空 test_data 对象")
        return

    fixture_id = data.get("fixture")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        findings.block(where, "test_data.fixture 必须是非空字符串")
        return

    scenario = case.get("scenario")
    scenario_fixture = scenario.get("fixture") if isinstance(scenario, dict) else None
    if scenario_fixture != fixture_id:
        findings.block(where, f"scenario.fixture={scenario_fixture!r} 与 test_data.fixture={fixture_id!r} 不一致")

    fixture = fixtures.get(fixture_id)
    if fixture is None:
        findings.block(where, f"test_data.fixture 引用不存在的用户：{fixture_id}")
    else:
        covers = fixture.get("covers")
        if not isinstance(covers, list) or case_id not in covers:
            findings.block(where, f"Fixture {fixture_id} 的 covers 未包含 {case_id}")
        elif set(str(item) for item in covers) != {case_id}:
            findings.block(where, f"Fixture {fixture_id} 不是一 case 一状态，covers={covers!r}")

    previous_owner = fixture_owners.get(fixture_id)
    if previous_owner and previous_owner != case_id:
        findings.block(where, f"Fixture {fixture_id} 已绑定 {previous_owner}，不能再绑定 {case_id}")
    else:
        fixture_owners[fixture_id] = case_id

    request_refs: set[str] = set()
    for step_index, unit in enumerate(case_units(case), start=1):
        unit_where = where if len(case_units(case)) == 1 else f"{where}#step{step_index}"
        request = unit.get("request")
        if not isinstance(request, dict):
            findings.block(unit_where, "缺少 request 对象")
            continue
        candidate = {
            "method": unit.get("method"),
            "path": unit.get("path"),
            "request": request,
        }
        refs = collect_refs(candidate)
        request_refs |= refs
        for ref in sorted(refs):
            try:
                resolve_data(data, ref)
            except KeyError as error:
                findings.block(unit_where, f"{{data.{ref}}} 无法解析，缺少路径段 {error.args[0]!r}")

        try:
            body = materialize(request.get("body"), data)
        except KeyError:
            continue
        if isinstance(body, dict) and "user_id" in body and body["user_id"] != fixture_id:
            findings.block(
                unit_where,
                f"装配后的 request.body.user_id={body['user_id']!r} 与绑定 Fixture {fixture_id!r} 不一致",
            )

    if not request_refs:
        findings.block(where, "请求没有使用任何 {data.xxx}，pytest 仍在使用手写请求数据")


def render(findings: Findings, counts: dict[str, int], checked: int) -> str:
    lines = [
        "# 测试数据绑定回查报告",
        "",
        f"- 用例文件：{counts['files']}",
        f"- 发现 case：{counts['cases']}",
        f"- 检查绑定 case：{checked}",
        f"- 阻塞项：{len(findings.blocking)}",
        f"- 建议项：{len(findings.suggestions)}",
        "",
        "## 阻塞项" if findings.blocking else "## 阻塞项（无）",
        "",
    ]
    lines.extend(f"- {item}" for item in findings.blocking)
    lines.extend(["", "## 建议项" if findings.suggestions else "## 建议项（无）", ""])
    lines.extend(f"- {item}" for item in findings.suggestions)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 pytest case 与 Fixture 的测试数据强绑定")
    parser.add_argument("--project-root", help="智能提醒助手项目根目录；默认自动定位")
    parser.add_argument("--case-id", action="append", default=[], help="本轮必须完成绑定的 case id，可重复")
    parser.add_argument("--require-all", action="store_true", help="要求全部业务 case 都完成 test_data 绑定")
    args = parser.parse_args()

    project_root = locate_project_root(args.project_root)
    if project_root is None:
        print("未找到项目根目录，请用 --project-root 指定", file=sys.stderr)
        return 2

    findings = Findings()
    cases, counts = load_cases(project_root / "tests" / "cases", findings)
    fixtures = load_fixtures(project_root / "testenv" / "fixtures" / "users.json", findings)
    targets = set(args.case_id)
    missing_targets = sorted(targets - set(cases))
    for case_id in missing_targets:
        findings.block("--case-id", f"找不到目标 case：{case_id}")

    selected: list[tuple[str, str, dict[str, Any]]] = []
    for case_id, (where, case) in cases.items():
        if case_id in targets or args.require_all or "test_data" in case:
            selected.append((case_id, where, case))
        elif not targets:
            findings.suggest(where, "尚未建立 test_data 强绑定（遗留 case）")

    fixture_owners: dict[str, str] = {}
    for case_id, where, case in selected:
        check_bound_case(case_id, where, case, fixtures, fixture_owners, findings)

    print(render(findings, counts, len(selected)))
    return 1 if findings.blocking else 0


if __name__ == "__main__":
    sys.exit(main())
