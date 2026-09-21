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
SCENE_TYPES = {"正常场景", "异常场景", "边界场景", "性能场景", "回归场景"}
SKELETON_TYPES = ("正常场景", "异常场景", "边界场景")
COVERAGE_DIMENSIONS = {
    "正常主路径",
    "性能容量",
    "历史回归",
    "前置不满足",
    "终止或取消",
    "幂等与并发",
    "频控上限",
    "失败与异常",
    "时间边界",
    "数据边界",
    "设置变更",
}
SCENE_REQUIRED = ["优先级", "来源", "关联需求", "场景类型", "等价类", "覆盖维度", "判定点"]
CASE_REQUIRED = ["场景", "优先级", "场景类型", "等价类", "前置条件", "测试步骤", "预期结果", "来源"]
VAGUE_EXACT = {"正常", "符合预期", "无异常", "功能可用", "正确", "一切正常", "符合要求", "符合需求", "没有问题"}

ENTRY_RE = re.compile(r"^###\s+(SC|TC)-(\d+)\s*(.*)$")
FIELD_RE = re.compile(r"^-\s*([^：:]+)[：:]\s*(.*)$")
SOURCE_RE = re.compile(r"([^\s、,，]+?\.(?:md|ya?ml|json)):(\d+)")


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


def field_text(entry: dict, name: str) -> str:
    """字段值 + 其缩进子项，便于校验多行字段。"""
    parts = [entry["fields"].get(name, "")]
    parts.extend(entry["sub"].get(name, []))
    return " ".join(part for part in parts if part).strip()


def check_equivalence_classes(entry: dict, scene_type: str, where: str, findings: Findings) -> None:
    """等价类划分：骨架三类必做，性能与回归允许简化或跳过但要显式登记。"""
    content = field_text(entry, "等价类")
    if not content:
        return
    if scene_type in ("正常场景", "异常场景"):
        missing = [mark for mark in ("有效", "无效") if mark not in content]
        if missing:
            findings.block(where, f"{scene_type}的等价类划分缺少：{'、'.join(missing)}等价类")
    elif scene_type == "边界场景":
        if "边界值" not in content and "边界" not in content:
            findings.block(where, "边界场景的等价类里没有列出边界值")
    elif scene_type in ("性能场景", "回归场景"):
        if not any(mark in content for mark in ("简化", "跳过", "不适用")):
            findings.suggest(where, f"{scene_type}建议标注是本轮简化还是跳过，避免被当成已覆盖")


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
        content = target.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(content)
        if line < 1 or line > total:
            findings.block(where, f"来源行号越界：{relative}:{line}（该文件共 {total} 行）")
            continue
        if not content[line - 1].strip():
            findings.block(
                where,
                f"来源行号指向空行：{relative}:{line}（引用已漂移；章节级引用请按章节名重新定位）",
            )
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
            if not field_text(scene, name):
                findings.block(where, f"缺少必填字段：{name}")
        scene_type = scene["fields"].get("场景类型", "")
        if scene_type and scene_type not in SCENE_TYPES:
            findings.block(where, f"场景类型取值非法：{scene_type!r}（只允许 {'、'.join(sorted(SCENE_TYPES))}）")
        if scene_type in SCENE_TYPES:
            check_equivalence_classes(scene, scene_type, where, findings)
        priority = scene["fields"].get("优先级", "")
        if priority and priority not in PRIORITY_ORDER:
            findings.block(where, f"优先级取值非法：{priority!r}（只允许 P0/P1/P2）")
        dimension = scene["fields"].get("覆盖维度", "")
        if dimension:
            unknown = [part for part in re.split(r"[、,，/]", dimension) if part and part not in COVERAGE_DIMENSIONS]
            if unknown:
                findings.suggest(where, f"覆盖维度 {unknown} 不在清单内，确认是否为新维度")
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
            if not field_text(case, name):
                suffix = "（需要至少一条内容）" if name in ("前置条件", "测试步骤", "预期结果") else ""
                findings.block(where, f"缺少必填字段：{name}{suffix}")

        case_type = case["fields"].get("场景类型", "")
        if case_type and case_type not in SCENE_TYPES:
            findings.block(where, f"场景类型取值非法：{case_type!r}")

        scene_ref = case["fields"].get("场景", "")
        scene_id = scene_ref.split()[0] if scene_ref else ""
        if scene_id:
            if scene_id in scenes:
                by_scene[scene_id].append(case["id"])
                scene_type = scenes[scene_id]["fields"].get("场景类型", "")
                if case_type and scene_type and case_type != scene_type:
                    findings.block(
                        where,
                        f"场景类型 {case_type!r} 与其场景 {scene_id} 的 {scene_type!r} 不一致",
                    )
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

        for item in case["sub"].get("预期结果", []):
            stripped = item.strip(" 。.；;")
            if stripped in VAGUE_EXACT:
                findings.block(where, f"预期结果是空话，无判定依据：{item!r}")
            elif "符合预期" in item:
                findings.block(where, f"预期结果含“符合预期”，需改为可观察值：{item!r}")
        for item in case["sub"].get("测试步骤", []):
            if re.search(r"(SELECT|INSERT|UPDATE|DELETE)\s", item, re.IGNORECASE):
                findings.suggest(where, f"测试步骤疑似写了 SQL：{item!r}")

        if case["fields"].get("来源"):
            check_sources(case["fields"]["来源"], repo_root, where, findings)
        else:
            findings.suggest(where, "建议补 `来源`，便于门禁 C 前追溯")

    if scenes:
        present = {scene["fields"].get("场景类型", "") for scene in scenes.values()}
        missing_types = [name for name in SKELETON_TYPES if name not in present]
        if missing_types:
            findings.suggest(
                "场景清单",
                f"骨架三类缺少：{'、'.join(missing_types)}；确无此类场景时在清单里写明原因",
            )
        for scene_id, case_ids in by_scene.items():
            if not case_ids:
                findings.block(
                    f"{scene_id}（第 {scenes[scene_id]['line']} 行）",
                    "没有任何用例挂靠；确不覆盖时须在清单里写明原因",
                )
    return by_scene


def check_pending(entries: list[dict], findings: Findings) -> None:
    """标为待确认的条目不得占用 SC-/TC- 正式编号，避免被误当成已审批内容。"""
    for entry in entries:
        text = " ".join([entry["title"]] + list(entry["fields"].values()))
        if "待确认" in text:
            findings.note(
                f"{entry['id']}（第 {entry['line']} 行）",
                "条目含“待确认”却已占用正式编号；待裁定后再编号入册",
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
