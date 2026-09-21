#!/usr/bin/env python3
"""测试场景清单与用例清单的确定性回查。

只做机械检查：结构、必备字段、来源可解析、场景与用例双向追踪、优先级单调、预期结果非空话。
不判断业务对错，也不替代人工评审。

用法：
    python3 check_test_cases.py --scenarios <场景清单.md> --cases <用例清单.md> [--repo-root .]
    python3 check_test_cases.py --cases <用例清单.md>            # 只查用例
    python3 check_test_cases.py --cases <用例清单.md> --json     # 机器可读输出

退出码：0 表示无阻塞项，1 表示有阻塞项。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
COVERAGE_DIMENSIONS = {
    "正常路径",
    "前置不满足",
    "终止或取消",
    "幂等与并发",
    "频控上限",
    "失败与异常",
    "时间边界",
    "数据边界",
    "设置变更",
}
SCENE_REQUIRED = ["优先级", "来源", "关联需求", "覆盖维度", "判定点"]
CASE_REQUIRED = ["场景", "优先级", "前置条件", "测试步骤", "预期结果", "来源"]
VAGUE_EXACT = {"正常", "符合预期", "无异常", "功能可用", "正确", "一切正常", "符合要求", "符合需求", "没有问题"}

ENTRY_RE = re.compile(r"^###\s+(SC|TC)-(\d+)\s*(.*)$")
FIELD_RE = re.compile(r"^-\s*([^：:]+)[：:]\s*(.*)$")
SOURCE_RE = re.compile(r"([^\s、,，()（）]+\.md):(\d+)")


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


def parse_entries(path: Path, kind: str) -> list[dict]:
    """把 markdown 解析成条目：标题行 + 顶层字段 + 缩进子项。"""
    entries: list[dict] = []
    current: dict | None = None
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = ENTRY_RE.match(raw.strip())
        if match:
            if match.group(1) != kind:
                current = None
                continue
            current = {
                "id": f"{match.group(1)}-{match.group(2)}",
                "number": int(match.group(2)),
                "title": match.group(3).strip(),
                "line": lineno,
                "fields": {},
                "sub": {},
                "raw": [],
            }
            entries.append(current)
            continue
        if current is not None and raw.startswith("## "):
            current = None
            continue
        if current is None:
            continue
        current["raw"].append(raw)
        field = FIELD_RE.match(raw.strip()) if not raw.startswith("  ") else None
        if field:
            name = field.group(1).strip()
            current["fields"][name] = field.group(2).strip()
            current["sub"].setdefault(name, [])
            continue
        stripped = raw.strip()
        if stripped and current["fields"]:
            last = list(current["fields"])[-1]
            item = re.sub(r"^(\d+[.)]|[-*])\s*", "", stripped)
            if item:
                current["sub"].setdefault(last, []).append(item)
    return entries


def check_sources(sources: str, repo_root: Path, where: str, findings: Findings) -> int:
    found = SOURCE_RE.findall(sources)
    if not found:
        findings.block(where, "来源里没有解析到任何 `文件:行号` 引用")
        return 0
    for relative, line_text in found:
        target = (repo_root / relative).resolve()
        if not target.is_file():
            findings.block(where, f"来源文件不存在：{relative}")
            continue
        line = int(line_text)
        total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        if line < 1 or line > total:
            findings.block(where, f"来源行号越界：{relative}:{line}（该文件共 {total} 行）")
    return len(found)


def check_scenes(entries: list[dict], repo_root: Path, findings: Findings) -> dict[str, dict]:
    scenes: dict[str, dict] = {}
    seen_numbers: set[int] = set()
    for scene in entries:
        where = f"{scene['id']}（第 {scene['line']} 行）"
        if scene["number"] in seen_numbers:
            findings.block(where, f"场景编号重复：SC-{scene['number']:03d}")
        seen_numbers.add(scene["number"])
        scenes[scene["id"]] = scene
        if not scene["title"]:
            findings.block(where, "场景标题为空")
        for name in SCENE_REQUIRED:
            if not scene["fields"].get(name):
                findings.block(where, f"缺少必填字段：{name}")
        priority = scene["fields"].get("优先级", "")
        if priority and priority not in PRIORITY_ORDER:
            findings.block(where, f"优先级取值非法：{priority!r}（只允许 P0/P1/P2）")
        dimension = scene["fields"].get("覆盖维度", "")
        if dimension and dimension not in COVERAGE_DIMENSIONS:
            findings.suggest(where, f"覆盖维度 {dimension!r} 不在清单内，确认是否为新维度")
        if scene["fields"].get("来源"):
            check_sources(scene["fields"]["来源"], repo_root, where, findings)
        if not scene["fields"].get("优先理由"):
            findings.suggest(where, "建议补 `优先理由`，避免优先级凭感觉")
    return scenes


def check_cases(entries: list[dict], scenes: dict[str, dict], repo_root: Path, findings: Findings) -> dict[str, list[str]]:
    by_scene: dict[str, list[str]] = {scene_id: [] for scene_id in scenes}
    seen_numbers: set[int] = set()
    for case in entries:
        where = f"{case['id']}（第 {case['line']} 行）"
        if case["number"] in seen_numbers:
            findings.block(where, f"用例编号重复：TC-{case['number']:03d}")
        seen_numbers.add(case["number"])
        if not case["title"]:
            findings.block(where, "用例标题为空")
        for name in CASE_REQUIRED:
            if name in ("前置条件", "测试步骤", "预期结果"):
                if not case["sub"].get(name):
                    findings.block(where, f"缺少必填字段：{name}（需要至少一条内容）")
            elif not case["fields"].get(name):
                findings.block(where, f"缺少必填字段：{name}")

        scene_ref = case["fields"].get("场景", "")
        scene_id = scene_ref.split()[0] if scene_ref else ""
        if scene_id:
            if scene_id in scenes:
                by_scene[scene_id].append(case["id"])
                case_priority = case["fields"].get("优先级", "")
                scene_priority = scenes[scene_id]["fields"].get("优先级", "")
                if case_priority in PRIORITY_ORDER and scene_priority in PRIORITY_ORDER:
                    if PRIORITY_ORDER[case_priority] < PRIORITY_ORDER[scene_priority]:
                        findings.block(
                            where,
                            f"优先级 {case_priority} 高于其场景 {scene_id} 的 {scene_priority}；降级需在用例里写明理由",
                        )
            elif scenes:
                findings.block(where, f"引用了不存在的场景：{scene_id}")

        priority = case["fields"].get("优先级", "")
        if priority and priority not in PRIORITY_ORDER:
            findings.block(where, f"优先级取值非法：{priority!r}（只允许 P0/P1/P2）")

        for name in ("测试步骤", "预期结果"):
            for item in case["sub"].get(name, []):
                if name == "预期结果" and item.strip(" 。.；;") in VAGUE_EXACT:
                    findings.block(where, f"预期结果是空话，无判定依据：{item!r}")
        for item in case["sub"].get("预期结果", []):
            if "符合预期" in item:
                findings.block(where, f"预期结果含“符合预期”，需改为可观察值：{item!r}")
        for item in case["sub"].get("测试步骤", []):
            if re.search(r"(SELECT|INSERT|UPDATE|DELETE)\s", item, re.IGNORECASE):
                findings.suggest(where, f"测试步骤疑似写了 SQL：{item!r}")

        if case["fields"].get("来源"):
            check_sources(case["fields"]["来源"], repo_root, where, findings)
        else:
            findings.suggest(where, "建议补 `来源`，便于门禁 C 前追溯")

    if scenes:
        for scene_id, case_ids in by_scene.items():
            if not case_ids:
                findings.block(
                    f"{scene_id}（第 {scenes[scene_id]['line']} 行）",
                    "没有任何用例挂靠；确不覆盖时须在清单里写明原因",
                )
    return by_scene


def check_pending(entries: list[dict], findings: Findings) -> None:
    """待确认条目不得占用 SC-/TC- 编号。"""
    for entry in entries:
        if not entry["fields"].get("判定点") and not entry["fields"].get("场景"):
            continue
        if entry["fields"].get("状态", "").startswith("待确认"):
            findings.note(
                f"{entry['id']}（第 {entry['line']} 行）",
                "标注为待确认但仍占用正式编号；待用户裁定后再编号入册",
            )


def load_json_report(findings: Findings, scenes: list[dict], cases: list[dict]) -> dict:
    return {
        "blocking": findings.blocking,
        "suggestion": findings.suggestion,
        "pending": findings.pending,
        "scene_count": len(scenes),
        "case_count": len(cases),
        "scene_priority": _count(scenes, "优先级"),
        "case_priority": _count(cases, "优先级"),
    }


def _count(entries: list[dict], field: str) -> dict[str, int]:
    counter: dict[str, int] = {}
    for entry in entries:
        value = entry["fields"].get(field, "")
        if value:
            counter[value] = counter.get(value, 0) + 1
    return dict(sorted(counter.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="回查测试场景清单与用例清单")
    parser.add_argument("--scenarios", help="测试场景清单 markdown 路径")
    parser.add_argument("--cases", help="测试用例清单 markdown 路径")
    parser.add_argument("--repo-root", default=".", help="来源路径解析根目录，默认当前目录")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)

    if not args.scenarios and not args.cases:
        parser.error("至少提供 --scenarios 或 --cases 之一")

    repo_root = Path(args.repo_root).resolve()
    findings = Findings()
    scenes_entries: list[dict] = []
    cases_entries: list[dict] = []

    scenes: dict[str, dict] = {}
    if args.scenarios:
        path = Path(args.scenarios)
        if not path.is_file():
            print(f"场景清单不存在：{path}", file=sys.stderr)
            return 2
        scenes_entries = parse_entries(path, "SC")
        if not scenes_entries:
            findings.block(str(path), "没有解析到任何 `### SC-0NN` 场景条目")
        scenes = check_scenes(scenes_entries, repo_root, findings)

    by_scene: dict[str, list[str]] = {}
    if args.cases:
        path = Path(args.cases)
        if not path.is_file():
            print(f"用例清单不存在：{path}", file=sys.stderr)
            return 2
        cases_entries = parse_entries(path, "TC")
        if not cases_entries:
            findings.block(str(path), "没有解析到任何 `### TC-0NN` 用例条目")
        by_scene = check_cases(cases_entries, scenes, repo_root, findings)

    check_pending(scenes_entries + cases_entries, findings)

    if args.json:
        print(json.dumps(load_json_report(findings, scenes_entries, cases_entries), ensure_ascii=False, indent=2))
        return 1 if findings.blocking else 0

    print("=" * 60)
    print(f"场景 {len(scenes_entries)} 条，用例 {len(cases_entries)} 条")
    if scenes_entries:
        print(f"场景优先级分布：{_count(scenes_entries, '优先级')}")
    if cases_entries:
        print(f"用例优先级分布：{_count(cases_entries, '优先级')}")
    if by_scene:
        print("\n场景 → 用例：")
        for scene_id, case_ids in by_scene.items():
            print(f"  {scene_id} -> {'、'.join(case_ids) if case_ids else '（无用例）'}")
    print("=" * 60)
    for label, items in (("阻塞项", findings.blocking), ("建议项", findings.suggestion), ("待确认", findings.pending)):
        print(f"\n[{label}] {len(items)} 项")
        for item in items:
            print(f"  - {item}")
    print()
    if findings.blocking:
        print(f"结论：不可进入下一阶段，阻塞项 {len(findings.blocking)} 项需先修完。")
        return 1
    print("结论：无阻塞项，可进入下一阶段（仍需人工评审）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
