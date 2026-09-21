#!/usr/bin/env python3
"""回查测试用例评审报告自身。

只检查评审报告写得对不对，不评被评审的用例：
  阻塞项：缺章节、结论取值非法、结论与意见级别不一致、意见字段缺失、
          待裁定项没有候选方案、位置指向的文件不存在或行号越界、
          抽样评审却没写漏评风险、结论与计数不符、结论为通过但有未处理意见
  建议项：位置无法解析、修复建议是空话、没记评审对象版本、意见标题为空

退出码 0 表示无阻塞项。仅依赖标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

REQUIRED_SECTIONS = [
    "评审对象与版本",
    "评审范围与抽样说明",
    "结论",
    "独立重推导基线对比",
    "不可测项登记",
    "复审记录",
]

ITEM_SECTIONS = ["阻塞项", "建议项", "待裁定项"]
ITEM_REQUIRED_FIELDS = ["级别", "位置", "证据", "问题", "影响", "修复建议", "状态"]
LEVELS = ["阻塞", "建议", "待裁定"]
STATUSES = ["未处理", "已处理", "不处理"]
CONCLUSIONS = ["通过", "有条件通过", "不通过"]

SECTION_LEVEL = {"阻塞项": "阻塞", "建议项": "建议", "待裁定项": "待裁定"}

VAGUE_PATTERNS = [
    "建议完善", "需要补充", "进一步完善", "优化一下", "待完善",
    "自行补充", "酌情", "视情况", "建议优化", "加强一下",
]

ID_RE = re.compile(r"^(?:SC|TC|AC|FR|MVP|RV|EVAL|SNZ|DSP)-\d+", re.IGNORECASE)
LOC_RE = re.compile(r"^(.+?):(\d+)$")
HEADING2_RE = re.compile(r"^##\s+(.+?)\s*$")
ITEM_RE = re.compile(r"^###\s+(RV-\d+)\s*(.*)$")
FIELD_RE = re.compile(r"^[-*]\s*([^：:]{1,14})[：:]\s*(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
PLACEHOLDER = {"-", "—", "–", "无", "无。", "不适用", "n/a", "N/A"}


def strip_ticks(value):
    return value.strip().strip("`").strip()


def split_locations(value):
    parts = re.split(r"[、,，;；]", value)
    return [p.strip() for p in parts if p.strip()]


def looks_like_path(token):
    return "/" in token or token.endswith(".md") or token.endswith(".yaml") or token.endswith(".json")


class Report:
    def __init__(self, text):
        self.sections = {}
        self.order = []
        self.items = []
        self._parse(text)

    def _parse(self, text):
        current_section = None
        current_item = None
        in_fence = False

        for raw in text.splitlines():
            if FENCE_RE.match(raw):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            m2 = HEADING2_RE.match(raw)
            if m2:
                current_section = m2.group(1).strip()
                current_item = None
                if current_section not in self.sections:
                    self.sections[current_section] = []
                    self.order.append(current_section)
                continue

            m3 = ITEM_RE.match(raw)
            if m3:
                current_item = {
                    "id": m3.group(1),
                    "title": m3.group(2).strip(),
                    "section": current_section,
                    "fields": {},
                }
                self.items.append(current_item)
                continue

            if raw.startswith("#"):
                current_item = None

            mf = FIELD_RE.match(raw)
            if mf:
                key = mf.group(1).strip()
                value = mf.group(2).strip()
                if current_item is not None:
                    current_item["fields"].setdefault(key, value)
                elif current_section:
                    self.sections[current_section].append((key, value))

    def section_fields(self, name):
        return dict(self.sections.get(name, []))

    def items_in(self, section):
        return [i for i in self.items if i["section"] == section]


def build_search_bases(repo_root, report_path):
    """引用路径的候选解析根：仓库根、报告所在目录，以及报告目录向上 3 级。

    报告通常落在 <需求目录>/测试方案/ 下，正文引用多为相对 <需求目录> 的写法。
    """
    bases = [os.path.abspath(repo_root)]
    report_dir = os.path.dirname(os.path.abspath(report_path))
    cur = report_dir
    for _ in range(4):
        if cur not in bases:
            bases.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return bases


def check(report, bases):
    blockers = []
    suggestions = []
    pending = []

    def add(level, message):
        {"blocker": blockers, "suggestion": suggestions, "pending": pending}[level].append(message)

    for name in REQUIRED_SECTIONS:
        if name not in report.sections:
            add("blocker", "缺少章节：## %s" % name)

    ids = [i["id"] for i in report.items]
    for dup in sorted({x for x in ids if ids.count(x) > 1}):
        add("blocker", "意见编号重复：%s" % dup)
    if not report.items and all(s in report.sections for s in ITEM_SECTIONS):
        add("blocker", "阻塞项 / 建议项 / 待裁定项三节均无 RV 编号意见，评审结论没有可复核的依据")

    counts = {"阻塞": 0, "建议": 0, "待裁定": 0}
    for item in report.items:
        f = item["fields"]
        where = "%s(%s)" % (item["id"], item["section"])
        if not item["title"]:
            add("suggestion", "%s 意见标题为空，无法从标题看出问题" % where)

        for field in ITEM_REQUIRED_FIELDS:
            if field not in f or not f[field].strip():
                add("blocker", "%s 缺少必填字段：%s" % (where, field))
                continue
            if field == "级别":
                if f[field] not in LEVELS:
                    add("blocker", "%s 级别取值非法：%s（允许 %s）" % (where, f[field], "/".join(LEVELS)))
            elif field == "状态":
                if f[field] not in STATUSES:
                    add("blocker", "%s 状态取值非法：%s（允许 %s）" % (where, f[field], "/".join(STATUSES)))
            elif field == "修复建议":
                for word in VAGUE_PATTERNS:
                    if word in f[field]:
                        add("suggestion", "%s 修复建议是空话（命中“%s”），作者无法据此改动" % (where, word))
                        break
            elif field == "证据":
                if len(f[field]) < 6:
                    add("suggestion", "%s 证据过短，无法复核" % where)

        level = f.get("级别")
        if level in counts:
            counts[level] += 1
        expected = SECTION_LEVEL.get(item["section"])
        if expected and level and level != expected:
            add("blocker", "%s 所在章节是“%s”，但级别写的是“%s”" % (where, item["section"], level))

        if level == "待裁定":
            for field in ("候选方案", "需要谁定"):
                if field not in f or not f[field].strip():
                    add("blocker", "%s 待裁定项缺少字段：%s（不得替用户直接拍板）" % (where, field))

        loc = f.get("位置", "")
        if loc:
            unparsed = []
            for token in split_locations(loc):
                cleaned = strip_ticks(token)
                m = LOC_RE.match(cleaned)
                if m:
                    rel, lines = m.group(1).strip(), int(m.group(2))
                    resolved = None
                    for base in bases:
                        cand = os.path.join(base, rel)
                        if os.path.isfile(cand):
                            resolved = cand
                            break
                    if resolved is None:
                        add("blocker", "%s 位置指向的文件不存在：%s（按仓库根与报告目录向上回溯均未找到）" % (where, rel))
                    else:
                        with open(resolved, encoding="utf-8", errors="replace") as fh:
                            total = sum(1 for _ in fh)
                        if lines < 1 or lines > total:
                            add("blocker", "%s 位置行号越界：%s 共 %d 行，引用第 %d 行" % (where, rel, total, lines))
                elif ID_RE.match(cleaned) or cleaned in PLACEHOLDER:
                    continue
                else:
                    unparsed.append(cleaned)
            if unparsed:
                hint = "、".join(unparsed[:3])
                if any(looks_like_path(t) for t in unparsed):
                    add("blocker", "%s 位置无法解析为文件:行号：%s" % (where, hint))
                else:
                    add("suggestion", "%s 位置既不是文件:行号也不是编号：%s" % (where, hint))

    scope = report.section_fields("评审范围与抽样说明")
    sampling = " ".join(scope.values())
    if "抽样" in sampling and "漏评风险" not in scope:
        add("blocker", "评审范围声明了抽样，但没有写“漏评风险”字段")

    obj = report.section_fields("评审对象与版本")
    if "对象版本" not in obj:
        add("suggestion", "没有记录评审对象版本，评审结论无法定位到具体版本")

    concl = report.section_fields("结论")
    conclusion = concl.get("结论", "")
    if not conclusion:
        add("blocker", "## 结论 缺少“结论”字段")
    elif conclusion not in CONCLUSIONS:
        add("blocker", "结论取值非法：%s（允许 %s）" % (conclusion, "/".join(CONCLUSIONS)))
    else:
        for label, key in (("阻塞项", "阻塞"), ("建议项", "建议"), ("待裁定项", "待裁定")):
            declared = concl.get(label)
            if declared is None:
                continue
            if not declared.strip().isdigit():
                add("blocker", "结论里的“%s”不是数字：%s" % (label, declared))
            elif int(declared) != counts[key]:
                add("blocker", "结论声明 %s=%s，实际统计为 %d" % (label, declared, counts[key]))

        if conclusion == "通过":
            if counts["阻塞"]:
                add("blocker", "结论为“通过”，但存在 %d 条阻塞项" % counts["阻塞"])
            if counts["待裁定"]:
                add("blocker", "结论为“通过”，但存在 %d 条待裁定项" % counts["待裁定"])
            undecided = [i["id"] for i in report.items if i["fields"].get("状态") == "未处理"]
            if undecided:
                add("blocker", "结论为“通过”，但仍有未处理意见：%s" % "、".join(undecided))
            pre = obj.get("前置确认", "")
            if "阻塞项 0" not in pre and "阻塞项0" not in pre:
                add("blocker", "结论为“通过”，但“前置确认”未记录 check_test_cases.py 阻塞项为 0")
        elif conclusion == "有条件通过":
            if counts["阻塞"]:
                add("blocker", "结论为“有条件通过”，但仍存在 %d 条阻塞项" % counts["阻塞"])
            if counts["待裁定"] == 0 and counts["建议"] == 0:
                add("blocker", "结论为“有条件通过”，但既无待裁定项也无建议项，应判为“通过”或“不通过”")
        elif conclusion == "不通过":
            if counts["阻塞"] == 0:
                add("blocker", "结论为“不通过”，但没有任何阻塞项，结论与意见级别不一致")

    undecided_blockers = [i["id"] for i in report.items
                          if i["fields"].get("状态") == "未处理" and i["fields"].get("级别") == "阻塞"]
    if undecided_blockers:
        add("pending", "阻塞项未处理，不得提交人工评审：%s" % "、".join(undecided_blockers))

    return blockers, suggestions, pending


def main():
    parser = argparse.ArgumentParser(description="回查测试用例评审报告")
    parser.add_argument("--report", required=True, help="评审报告 markdown 路径")
    parser.add_argument("--repo-root", default=".", help="来源路径解析根目录，默认当前目录")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    if not os.path.isfile(args.report):
        print("[阻塞项] 评审报告不存在：%s" % args.report)
        return 2

    with open(args.report, encoding="utf-8") as fh:
        text = fh.read()

    report = Report(text)
    bases = build_search_bases(args.repo_root, args.report)
    blockers, suggestions, pending = check(report, bases)

    if args.json:
        print(json.dumps({
            "report": args.report,
            "blockers": blockers,
            "suggestions": suggestions,
            "pending": pending,
        }, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("评审报告：%s" % args.report)
        print("意见 %d 条（阻塞 %d / 建议 %d / 待裁定 %d）" % (
            len(report.items),
            len(report.items_in("阻塞项")),
            len(report.items_in("建议项")),
            len(report.items_in("待裁定项")),
        ))
        print("=" * 60)
        for label, items in (("阻塞项", blockers), ("建议项", suggestions), ("待确认", pending)):
            print("\n[%s] %d 项" % (label, len(items)))
            for item in items:
                print("  - %s" % item)
        print("\n结论：%s" % ("无阻塞项，评审报告可提交人工评审。" if not blockers
                              else "存在阻塞项，需修订评审报告后重跑。"))

    return 0 if not blockers else 1


if __name__ == "__main__":
    sys.exit(main())
