#!/usr/bin/env python3
"""验收标准回查工具：编号、结构、覆盖、可判定性、越界与冗余。

检查项：
1. AC 编号唯一、连续
2. Given / When / Then 结构完整
3. 可判定性：Then 是否含判定依据，是否使用不可判定表述
4. 覆盖矩阵：前置不满足、失效、频控、幂等、失败、设置变更、时间边界
5. 需求覆盖：P0 FR 是否都有 AC，AC 是否可反查需求
6. 越界：实现细节、操作步骤、线上指标
7. 冗余：多条 AC 结论重复

用法：
    python3 check_acceptance_criteria.py --ac 验收标准.md --prd PRD.md
退出码：0 无阻塞项；1 存在阻塞项（可用 --fail-on 调整）。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

BLOCK = "阻塞"
ADVICE = "建议"

AC_HEADING = re.compile(r"^(#{2,6})\s*(AC-(\d{3}))\s*[:：]?\s*(.*)$", re.I)
ANY_HEADING = re.compile(r"^(#{1,6})\s*(\S.*)$")
STEP_KEYWORD = re.compile(r"^(?:-\s*)?(Given|When|Then|And|But)\b", re.I)
FR_RE = re.compile(r"(?<![A-Za-z0-9])(FR)-(\d{2,3})(?![0-9])", re.I)
AC_RE = re.compile(r"(?<![A-Za-z0-9])(AC)-(\d{2,3})(?![0-9])", re.I)
REASON_CODE = re.compile(r"`?[A-Z][A-Z0-9_]{3,}`?")

JUDGEABLE_WORDS = re.compile(
    r"不发送|不生成|不调用|不提醒|不展示|生成|发送|调用|提醒|取消|延后|记录|展示|返回|"
    r"进入|命中|写入|产生|完成|未完成|等于|不超过|最多|至少|大于|小于|落在|保持|复用|"
    r"使用|采用|标记|默认|视为|归入"
)
FUZZY_WORDS = re.compile(r"体验|友好|及时|合理|尽快|适当|大致|视情况|尽量|优雅|顺畅")

IMPLEMENTATION_WORDS = re.compile(
    r"\bSQL\b|\bDB\b|\bQPS\b|表名|字段类型|幂等键|接口路径|/internal/|数据库表|唯一索引名"
)
ONLINE_METRIC_WORDS = re.compile(r"到达率|打开率|留存率|完成率.*(提升|达到)|投诉率|卸载率")
UI_STEP_WORDS = re.compile(r"点击.*→|打开首页|右上角|下拉|进入页面点击|滑动")

COVERAGE_GROUPS = [
    ("前置不满足", r"无任务|没有任务|关闭提醒|未授权|权限关闭|已达上限|达到上限", BLOCK, "缺前置不满足场景，验收会漏掉拒绝分支"),
    ("已完成或已失效", r"已完成|已过期|过期", BLOCK, "缺失效场景，验收会漏掉取消分支"),
    ("频控上限", r"上限|频控|次数限制|最多 1 次|最多一次", BLOCK, "缺频控场景，无法验收重复触发"),
    ("重复与并发", r"重复|幂等|并发", BLOCK, "缺重复或并发场景，验收会漏掉重复执行问题"),
    ("失败与未知", r"失败|重试|未知", BLOCK, "缺失败路径，验收会漏掉异常处理"),
    ("设置变更", r"修改设置|设置|开关|免打扰时间", BLOCK, "缺设置变更场景，无法验收最新配置生效"),
    ("时间边界", r"临界|跨天|截止时间|前后一分钟|窗口边界", ADVICE, "建议补时间边界场景"),
    ("用户主动操作", r"稍后提醒|延后|取消提醒|主动", ADVICE, "建议覆盖用户主动操作"),
    ("数据与隐私", r"敏感|隐私|不展示|不记录", ADVICE, "建议覆盖数据最小化要求"),
]

SIMILARITY_THRESHOLD = 0.9
MAX_AND_LINES = 4


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def parse_acs(lines: list[str]) -> list[dict]:
    acs: list[dict] = []
    for index, line in enumerate(lines):
        match = AC_HEADING.match(line.strip())
        if not match:
            continue
        acs.append(
            {
                "id": match.group(2).upper(),
                "level": len(match.group(1)),
                "title": match.group(4).strip(),
                "line": index + 1,
                "start": index,
            }
        )
    for position, ac in enumerate(acs):
        end = len(lines)
        if position + 1 < len(acs):
            end = acs[position + 1]["start"]
        else:
            for index in range(ac["start"] + 1, len(lines)):
                heading = ANY_HEADING.match(lines[index].strip())
                if heading and not AC_HEADING.match(lines[index].strip()):
                    end = index
                    break
        ac["end"] = end
    return acs


def ac_steps(lines: list[str], ac: dict) -> tuple[list[dict], dict[str, bool]]:
    """解析 Given / When / Then 步骤，跳过代码围栏与章节标题。"""
    steps: list[dict] = []
    in_fence = False
    current: dict | None = None
    for offset, line in enumerate(lines[ac["start"] + 1 : ac["end"]], start=ac["start"] + 2):
        stripped = line.strip()
        if stripped.startswith("~~~") or stripped.startswith("```"):
            in_fence = not in_fence
            current = None
            continue
        if not stripped or stripped.startswith("#"):
            continue
        match = STEP_KEYWORD.match(stripped)
        if match:
            key = match.group(1).capitalize()
            if key == "But":
                key = "And"
            current = {"key": key, "text": stripped, "line": offset}
            steps.append(current)
            continue
        if current and in_fence:
            current["text"] += " " + stripped
    present = {step["key"] for step in steps}
    return steps, {
        "Given": "Given" in present,
        "When": "When" in present,
        "Then": "Then" in present,
    }


def then_content(steps: list[dict]) -> tuple[str, int]:
    """返回 Then 之后的全部内容与并列 And 条数。"""
    texts: list[str] = []
    and_count = 0
    reached_then = False
    for step in steps:
        if step["key"] == "Then":
            reached_then = True
            texts.append(step["text"])
        elif reached_then and step["key"] == "And":
            and_count += 1
            texts.append(step["text"])
    return " ".join(texts), and_count


def collect_ids(text: str, pattern: re.Pattern) -> set[str]:
    return {f"{m.group(1).upper()}-{m.group(2)}" for m in pattern.finditer(text)}


def p0_requirement_ids(prd_lines: list[str]) -> set[str]:
    ids: set[str] = set()
    for line in prd_lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if "P0" not in cells:
            continue
        for cell in cells:
            ids |= collect_ids(cell, FR_RE)
    return ids


def check_numbering(acs: list[dict]) -> list[dict]:
    findings: list[dict] = []
    numbers = [int(ac["id"].split("-")[1]) for ac in acs]
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        findings.append(
            {
                "severity": BLOCK,
                "title": "AC 编号重复",
                "detail": "重复编号：" + "、".join(f"AC-{number:03d}" for number in duplicates),
                "evidence": [],
            }
        )
    if numbers:
        expected = set(range(min(numbers), max(numbers) + 1))
        missing = sorted(expected - set(numbers))
        if missing:
            findings.append(
                {
                    "severity": ADVICE,
                    "title": "AC 编号不连续",
                    "detail": "缺号：" + "、".join(f"AC-{number:03d}" for number in missing),
                    "evidence": [],
                }
            )
    return findings


def check_structure(acs: list[dict], lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    incomplete: list[str] = []
    for ac in acs:
        _, present = ac_steps(lines, ac)
        missing = [key for key in ("Given", "When", "Then") if not present[key]]
        if missing:
            incomplete.append(f"{ac['id']}（缺 {'、'.join(missing)}，L{ac['line']}）")
        elif not ac["title"]:
            incomplete.append(f"{ac['id']} 缺少一句话结论（L{ac['line']}）")
    if incomplete:
        findings.append(
            {
                "severity": BLOCK,
                "title": "AC 结构不完整",
                "detail": "每条 AC 必须有结论标题与 Given / When / Then 三段",
                "evidence": incomplete,
            }
        )
    return findings


def check_judgeable(acs: list[dict], lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    no_evidence: list[str] = []
    fuzzy: list[str] = []
    overloaded: list[str] = []
    for ac in acs:
        steps, _ = ac_steps(lines, ac)
        then_text, and_count = then_content(steps)
        if not then_text:
            continue
        if not (REASON_CODE.search(then_text) or re.search(r"\d", then_text) or JUDGEABLE_WORDS.search(then_text)):
            no_evidence.append(f"{ac['id']}（L{ac['line']}）：{then_text[:50]}")
        if FUZZY_WORDS.search(then_text):
            fuzzy.append(f"{ac['id']}（L{ac['line']}）：{FUZZY_WORDS.search(then_text).group(0)}")
        if and_count > MAX_AND_LINES:
            overloaded.append(f"{ac['id']}（{and_count} 条并列结论，L{ac['line']}）")
    if no_evidence:
        findings.append(
            {
                "severity": BLOCK,
                "title": "Then 缺少判定依据",
                "detail": "结论需要原因码、数量或明确状态词才能判定",
                "evidence": no_evidence[:5],
            }
        )
    if fuzzy:
        findings.append(
            {
                "severity": BLOCK,
                "title": "存在不可判定表述",
                "detail": "模糊表述无法作为验收依据，需改为具体判定条件",
                "evidence": fuzzy[:5],
            }
        )
    if overloaded:
        findings.append(
            {
                "severity": ADVICE,
                "title": "单条 AC 结论过多",
                "detail": f"并列结论超过 {MAX_AND_LINES} 条，建议按判定结果拆分",
                "evidence": overloaded,
            }
        )
    return findings


def check_coverage(text: str) -> list[dict]:
    findings: list[dict] = []
    blocking: list[str] = []
    advice: list[str] = []
    for name, pattern, severity, hint in COVERAGE_GROUPS:
        if re.search(pattern, text):
            continue
        entry = f"{name}：{hint}"
        if severity == BLOCK:
            blocking.append(entry)
        else:
            advice.append(entry)
    if blocking:
        findings.append(
            {
                "severity": BLOCK,
                "title": "关键覆盖维度缺失",
                "detail": "下列维度应有对应 AC，或说明不适用原因",
                "evidence": blocking,
            }
        )
    if advice:
        findings.append(
            {
                "severity": ADVICE,
                "title": "建议补充的覆盖维度",
                "detail": "按需求类型判断是否适用",
                "evidence": advice,
            }
        )
    return findings


def check_requirement_coverage(ac_text: str, prd_lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    if not prd_lines:
        return findings
    prd_text = "\n".join(prd_lines)
    combined = prd_text + "\n" + ac_text
    mapped_fr: set[str] = set()
    for line in combined.splitlines():
        fr_ids = collect_ids(line, FR_RE)
        ac_ids = collect_ids(line, AC_RE)
        if fr_ids and ac_ids:
            mapped_fr |= fr_ids
    p0_fr = p0_requirement_ids(prd_lines)
    missing = sorted(p0_fr - mapped_fr)
    if missing:
        findings.append(
            {
                "severity": BLOCK,
                "title": "P0 需求缺少验收项",
                "detail": "以下 P0 需求在 PRD 与验收标准中都没有 FR→AC 映射：" + "、".join(missing),
                "evidence": [],
            }
        )
    p1_p2 = re.search(r"P1|P2", prd_text) is not None
    if p1_p2:
        non_p0 = sorted(collect_ids(ac_text, FR_RE) - p0_fr)
        if non_p0:
            findings.append(
                {
                    "severity": ADVICE,
                    "title": "验收标准引用了非本期需求",
                    "detail": "确认这些编号属于 P1/P2 且本期不纳入验收：" + "、".join(non_p0),
                    "evidence": [],
                }
            )
    return findings


def check_boundaries(acs: list[dict], lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    impl: list[str] = []
    metrics: list[str] = []
    ui: list[str] = []
    for ac in acs:
        body = " ".join(lines[ac["start"] + 1 : ac["end"]])
        if IMPLEMENTATION_WORDS.search(body):
            impl.append(f"{ac['id']}（L{ac['line']}）：{IMPLEMENTATION_WORDS.search(body).group(0)}")
        if ONLINE_METRIC_WORDS.search(body):
            metrics.append(f"{ac['id']}（L{ac['line']}）：{ONLINE_METRIC_WORDS.search(body).group(0)}")
        if UI_STEP_WORDS.search(body):
            ui.append(f"{ac['id']}（L{ac['line']}）：{UI_STEP_WORDS.search(body).group(0)}")
    if impl or metrics:
        findings.append(
            {
                "severity": BLOCK,
                "title": "验收标准越界",
                "detail": "实现细节与线上统计指标不属于功能验收范围",
                "evidence": (impl + metrics)[:5],
            }
        )
    if ui:
        findings.append(
            {
                "severity": ADVICE,
                "title": "出现页面操作步骤",
                "detail": "操作步骤属于测试用例，验收标准只写判定结果",
                "evidence": ui[:5],
            }
        )
    return findings


def normalize(text: str) -> str:
    return re.sub(r"[\s`*|:：,，。;；]+", "", text)


def check_duplicates(acs: list[dict], lines: list[str]) -> list[dict]:
    bodies = {ac["id"]: normalize(" ".join(lines[ac["start"] + 1 : ac["end"]])) for ac in acs}
    ids = list(bodies)
    similar: list[str] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            left, right = bodies[ids[i]], bodies[ids[j]]
            if not left or not right:
                continue
            ratio = difflib.SequenceMatcher(None, left, right).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                similar.append(f"{ids[i]} 与 {ids[j]} 相似度 {ratio:.0%}")
    if not similar:
        return []
    return [
        {
            "severity": ADVICE,
            "title": f"疑似重复的 AC（{len(similar)} 组）",
            "detail": "同一规则不要写多条 AC，保留一条或明确差异",
            "evidence": similar[:5],
        }
    ]


def render_markdown(ac_path: Path, findings: list[dict]) -> str:
    blocks = [f for f in findings if f["severity"] == BLOCK]
    advices = [f for f in findings if f["severity"] == ADVICE]
    out = [
        "# 验收标准回查报告",
        "",
        f"- 被检查文件：`{ac_path}`",
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
            if finding["evidence"]:
                out.append("- 证据：" + "；".join(finding["evidence"]))
            out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="验收标准回查")
    parser.add_argument("--ac", required=True, help="待检查的验收标准 Markdown")
    parser.add_argument("--prd", action="append", default=[], help="PRD 或产品方案，可多次传入")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--fail-on", choices=["blocking", "any", "none"], default="blocking")
    args = parser.parse_args()

    ac_path = Path(args.ac)
    if not ac_path.is_file():
        print(f"找不到验收标准文件：{ac_path}", file=sys.stderr)
        return 2

    lines = read_lines(ac_path)
    text = "\n".join(lines)
    acs = parse_acs(lines)
    if not acs:
        print("未解析到任何 AC-0NN 章节，请确认编号格式", file=sys.stderr)
        return 2

    prd_lines: list[str] = []
    for prd in args.prd:
        prd_path = Path(prd)
        if not prd_path.is_file():
            print(f"找不到输入文件：{prd_path}", file=sys.stderr)
            return 2
        prd_lines.extend(read_lines(prd_path))

    findings: list[dict] = []
    findings += check_numbering(acs)
    findings += check_structure(acs, lines)
    findings += check_judgeable(acs, lines)
    findings += check_coverage(text)
    findings += check_requirement_coverage(text, prd_lines)
    findings += check_boundaries(acs, lines)
    findings += check_duplicates(acs, lines)

    if args.format == "json":
        print(
            json.dumps(
                {"ac": str(ac_path), "count": len(acs), "findings": findings},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_markdown(ac_path, findings))

    has_block = any(finding["severity"] == BLOCK for finding in findings)
    if args.fail_on == "blocking" and has_block:
        return 1
    if args.fail_on == "any" and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
