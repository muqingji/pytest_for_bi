#!/usr/bin/env python3
"""技术方案回查工具：结构合规、需求覆盖、关键要素与冗余。

检查项：
1. 章节完整性：对照《后端技术方案》模板 1~9 章，区分必填与（选）
2. 空壳章节：只有标题没有实质内容
3. 需求覆盖：PRD 的 P0 需求与验收标准是否都有落点
4. 关键要素：幂等、唯一约束、错误码、未知状态、回滚、监控、成本等
5. 异常链路占比：第 4 章异常、失败、降级内容占比
6. 冗余：与 PRD 重复的长句、文档内重复行
7. 待确认项是否集中，而非散落正文

用法：
    python3 check_tech_design.py --design 技术方案.md --prd PRD.md [--prd 验收标准.md]
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

NUM_HEADING = re.compile(r"^(#{1,6})\s*(\d+(?:\.\d+)*)[.、]?\s+(\S.*)$")
CN_HEADING = re.compile(r"^(#{1,6})\s*([一二三四五六七八九十]+)[、.]\s*(\S.*)$")
TPL_CHAPTER = re.compile(r"^(\d+(?:\.\d+)*)[.、]?\s+(\S.*)$")
SEP_ROW = re.compile(r"^\|[\s:\-|]+\|$")
FR_RE = re.compile(r"(?<![A-Za-z0-9])(FR)-(\d{2,3})(?![0-9])", re.I)
AC_RE = re.compile(r"(?<![A-Za-z0-9])(AC)-(\d{2,3})(?![0-9])", re.I)
ANOMALY_RE = re.compile(
    r"异常|失败|超时|降级|兜底|取消|重试|回滚|未知|不可用|失败关闭|容错|补偿|容灾"
)

KEYWORDS = [
    ("幂等设计", r"幂等", BLOCK, "发奖、任务进度、补偿、重试等场景必须有幂等设计"),
    ("唯一约束", r"唯一(约束|索引|键)", BLOCK, "频控与排程幂等依赖持久化层唯一约束"),
    ("错误码", r"错误码", BLOCK, "需给出错误码分类与上下游处理"),
    ("未知状态", r"未知", BLOCK, "渠道或下游返回未知状态时必须有处理策略"),
    ("回滚方案", r"回滚", BLOCK, "上线方案必须包含回滚"),
    ("监控告警", r"监控|告警", BLOCK, "关键链路需要可观测指标"),
    ("成本评估", r"成本", BLOCK, "第 7 章成本评估为必填"),
    ("状态机", r"状态机|状态图|状态流转", ADVICE, "状态类需求建议给出状态图与迁移条件"),
    ("止损方案", r"止损|应急", ADVICE, "建议给出止损与应急手段"),
    ("补偿逻辑", r"补偿", ADVICE, "涉及资源流动时需说明补偿边界"),
    ("限流评估", r"限流", ADVICE, "新增接口需评估是否配置限流"),
    ("鉴权与安全", r"鉴权|验签|mTLS|权限|敏感", ADVICE, "接口需说明鉴权与敏感信息保护"),
    ("容量估算", r"容量|数据量|QPS", ADVICE, "建议给出容量或数据量估算"),
    ("灰度方案", r"灰度", ADVICE, "建议给出灰度放量步骤"),
]

MIN_SECTION_CHARS = 30
SHORT_SECTION_CHARS = 80
MAX_TOP_LEVEL_CHAPTER = 9
MAX_TEMPLATE_TITLE_CHARS = 25
MIN_PRD_DUPLICATE_HITS = 3


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def top_level(number: str) -> str:
    return number.split(".")[0]


def sort_key(number: str) -> list[int]:
    return [int(part) for part in number.split(".")]


def parse_sections(lines: list[str]) -> tuple[list[dict], list[int]]:
    """返回编号章节列表与使用中文序号标题的行号。"""
    sections: list[dict] = []
    cn_heading_lines: list[int] = []
    for index, line in enumerate(lines):
        match = NUM_HEADING.match(line.strip())
        if match:
            sections.append(
                {
                    "num": match.group(2),
                    "title": match.group(3).strip(),
                    "level": len(match.group(1)),
                    "start": index,
                }
            )
            continue
        if CN_HEADING.match(line.strip()):
            cn_heading_lines.append(index + 1)
    for position, section in enumerate(sections):
        section["end"] = (
            sections[position + 1]["start"] if position + 1 < len(sections) else len(lines)
        )
    return sections, cn_heading_lines


def section_body(lines: list[str], section: dict) -> list[str]:
    return [line for line in lines[section["start"] + 1 : section["end"]] if line.strip()]


def content_chars(section: dict, lines: list[str]) -> int:
    total = 0
    for line in section_body(lines, section):
        if NUM_HEADING.match(line.strip()):
            continue
        total += len(line.strip())
    return total


def has_child(section: dict, sections: list[dict]) -> bool:
    prefix = section["num"] + "."
    return any(other["num"].startswith(prefix) for other in sections)


def subtree_chars(section: dict, sections: list[dict], lines: list[str]) -> int:
    """父章节自身内容为空但子节有内容时不算空壳，因此按子树统计。"""
    total = content_chars(section, lines)
    prefix = section["num"] + "."
    for other in sections:
        if other["num"] != section["num"] and other["num"].startswith(prefix):
            total += content_chars(other, lines)
    return total


def load_template_chapters(template_path: Path | None) -> dict[str, dict]:
    if not template_path or not template_path.is_file():
        return {}
    chapters: dict[str, dict] = {}
    for line in read_lines(template_path):
        match = TPL_CHAPTER.match(line.strip())
        if not match:
            continue
        number, title = match.group(1), match.group(2).strip()
        if re.match(r"^[AB]XXX", title):
            continue
        # 排除模板正文里的编号列表，只保留章节标题
        if len(title) > MAX_TEMPLATE_TITLE_CHARS or re.search(r"[，。：]", title):
            continue
        if "." not in number and not number.isdigit():
            continue
        if "." not in number and not 1 <= int(number) <= MAX_TOP_LEVEL_CHAPTER:
            continue
        chapters[number] = {"title": title, "required": "（选）" not in title}
    return chapters


def collect_ids(text: str, pattern: re.Pattern) -> set[str]:
    return {f"{m.group(1).upper()}-{m.group(2)}" for m in pattern.finditer(text)}


def p0_requirement_ids(prd_lines: list[str]) -> set[str]:
    """仅从表格行中读取优先级，避免把正文里的“P0 提醒闭环”误判为优先级。"""
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


def check_structure(
    sections: list[dict], cn_heading_lines: list[int], chapters: dict[str, dict]
) -> list[dict]:
    findings: list[dict] = []
    present = {section["num"] for section in sections}

    if not chapters:
        return [
            {
                "severity": ADVICE,
                "title": "未找到模板文件，跳过章节完整性比对",
                "detail": "请用 --template 指定《后端技术方案》模板路径",
                "evidence": [],
            }
        ]

    missing_top = sorted(
        {
            top_level(number)
            for number, meta in chapters.items()
            if meta["required"] and top_level(number) not in present
        },
        key=int,
    )
    if missing_top:
        findings.append(
            {
                "severity": BLOCK,
                "title": "缺少模板必填章节",
                "detail": "模板要求 1~9 章完整，缺失："
                + "、".join(
                    f"{number}（{chapters[number]['title']}）"
                    for number in sorted(chapters, key=sort_key)
                    if number in missing_top
                ),
                "evidence": [],
            }
        )

    missing_sub = [
        number
        for number, meta in chapters.items()
        if meta["required"] and "." in number and number not in present
    ]
    if missing_sub:
        findings.append(
            {
                "severity": ADVICE,
                "title": "缺少模板必填子节",
                "detail": "缺失："
                + "、".join(f"{n}（{chapters[n]['title']}）" for n in sorted(missing_sub, key=sort_key)),
                "evidence": [],
            }
        )

    extra = [
        f"{section['num']}（{section['title']}）"
        for section in sections
        if "." not in section["num"] and section["num"] not in chapters
    ]
    if extra:
        findings.append(
            {
                "severity": ADVICE,
                "title": "存在模板之外的顶级章节",
                "detail": f"模板顶级章节为 1~{MAX_TOP_LEVEL_CHAPTER}，确认是否有意扩展："
                + "、".join(extra),
                "evidence": [],
            }
        )

    if cn_heading_lines:
        findings.append(
            {
                "severity": ADVICE,
                "title": "存在中文序号标题",
                "detail": "模板使用数字编号章节，中文序号会降低模板比对与检索效率",
                "evidence": [f"L{line}" for line in cn_heading_lines[:5]],
            }
        )
    return findings


def check_empty_sections(sections: list[dict], lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    empty_block: list[str] = []
    short_block: list[str] = []
    for section in sections:
        size = subtree_chars(section, sections, lines)
        label = f"{section['num']} {section['title']}（{size} 字）"
        is_leaf = not has_child(section, sections)
        if size < MIN_SECTION_CHARS:
            empty_block.append(label)
        elif is_leaf and size < SHORT_SECTION_CHARS:
            short_block.append(label)
    if empty_block:
        findings.append(
            {
                "severity": BLOCK,
                "title": "存在空壳章节",
                "detail": "只有标题或内容过少，需要补齐或写明“不涉及 + 原因”",
                "evidence": empty_block,
            }
        )
    if short_block:
        findings.append(
            {
                "severity": ADVICE,
                "title": "章节内容偏薄",
                "detail": "内容明显不足，确认是否遗漏关键设计",
                "evidence": short_block,
            }
        )
    return findings


def check_requirement_coverage(design_text: str, prd_lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    prd_text = "\n".join(prd_lines)
    design_fr = collect_ids(design_text, FR_RE)
    design_ac = collect_ids(design_text, AC_RE)
    prd_fr = collect_ids(prd_text, FR_RE)
    prd_ac = collect_ids(prd_text, AC_RE)
    if not prd_fr and not prd_ac:
        return findings

    missing_p0 = sorted(p0_requirement_ids(prd_lines) - design_fr)
    if missing_p0:
        findings.append(
            {
                "severity": BLOCK,
                "title": "P0 需求缺少实现落点",
                "detail": "以下 P0 需求未在技术方案中出现：" + "、".join(missing_p0),
                "evidence": [],
            }
        )
    missing_other = sorted(prd_fr - design_fr - set(missing_p0))
    if missing_other:
        findings.append(
            {
                "severity": ADVICE,
                "title": "部分 P1/P2 需求未在方案中标注",
                "detail": "非 P0 需求也应说明是延后实现还是不实现：" + "、".join(missing_other),
                "evidence": [],
            }
        )
    missing_ac = sorted(prd_ac - design_ac)
    if missing_ac:
        findings.append(
            {
                "severity": ADVICE,
                "title": "验收标准未映射到测试或评审记录",
                "detail": "缺少：" + "、".join(missing_ac),
                "evidence": [],
            }
        )
    extra_ids = sorted((design_fr | design_ac) - (prd_fr | prd_ac))
    if extra_ids:
        findings.append(
            {
                "severity": ADVICE,
                "title": "方案中出现 PRD 未定义的编号",
                "detail": "确认是否改名或自行新增：" + "、".join(extra_ids),
                "evidence": [],
            }
        )
    return findings


def check_keywords(design_text: str) -> list[dict]:
    findings: list[dict] = []
    for name, pattern, severity, hint in KEYWORDS:
        if re.search(pattern, design_text):
            continue
        findings.append(
            {
                "severity": severity,
                "title": f"缺少关键要素：{name}",
                "detail": hint,
                "evidence": [],
            }
        )
    return findings


def check_anomaly_ratio(sections: list[dict], lines: list[str]) -> list[dict]:
    chapter_lines: list[str] = []
    for section in sections:
        if top_level(section["num"]) != "4":
            continue
        chapter_lines.extend(
            line.strip() for line in section_body(lines, section) if not NUM_HEADING.match(line.strip())
        )
    chapter_lines = [line for line in chapter_lines if line]
    if not chapter_lines:
        return []
    anomaly = [line for line in chapter_lines if ANOMALY_RE.search(line)]
    ratio = len(anomaly) / len(chapter_lines)
    if ratio >= 0.25:
        return []
    return [
        {
            "severity": ADVICE,
            "title": f"第 4 章异常链路占比偏低（{ratio:.0%}）",
            "detail": "模板要求异常链路占详细方案正文 40% 以上，此处按含异常关键词的行统计",
            "evidence": [],
        }
    ]


def normalize(line: str) -> str:
    return re.sub(r"\s+", "", line.strip())


def check_redundancy(design_lines: list[str], prd_lines: list[str]) -> list[dict]:
    findings: list[dict] = []
    prd_normalized = {normalize(line) for line in prd_lines if len(normalize(line)) >= 20}
    repeated_with_prd: list[str] = []
    internal: list[str] = []
    seen: dict[str, int] = {}
    for index, line in enumerate(design_lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or SEP_ROW.match(stripped):
            continue
        if stripped.startswith("|"):
            # 表格行在不同表中重复出现属正常情况，不参与重复行判定
            continue
        normalized = normalize(stripped)
        if len(normalized) < 20:
            continue
        if normalized in prd_normalized:
            repeated_with_prd.append(f"L{index}: {stripped[:60]}")
        if len(normalized) >= 25:
            seen[normalized] = seen.get(normalized, 0) + 1
            if seen[normalized] == 2:
                internal.append(f"L{index}: {stripped[:60]}")
    if len(repeated_with_prd) >= MIN_PRD_DUPLICATE_HITS:
        findings.append(
            {
                "severity": ADVICE,
                "title": f"与 PRD 重复的长句较多（{len(repeated_with_prd)} 处）",
                "detail": "技术方案应只写实现落点，不建议复述 PRD 表述",
                "evidence": repeated_with_prd[:5],
            }
        )
    if internal:
        findings.append(
            {
                "severity": ADVICE,
                "title": f"文档内存在重复行（{len(internal)} 处）",
                "detail": "同一结论建议只在一个权威位置定义，其他地方引用小节号",
                "evidence": internal[:5],
            }
        )
    return findings


def check_pending_items(design_lines: list[str]) -> list[dict]:
    hits = [
        f"L{index}: {line.strip()[:60]}"
        for index, line in enumerate(design_lines, start=1)
        if re.search(r"待确认|待定|待补|TODO", line)
    ]
    if len(hits) <= 8:
        return []
    return [
        {
            "severity": ADVICE,
            "title": f"待确认项分散（共 {len(hits)} 处）",
            "detail": "建议集中到第 9 章评审记录，逐条给出影响面与责任人",
            "evidence": hits[:5],
        }
    ]


def render_markdown(design: Path, findings: list[dict]) -> str:
    blocks = [f for f in findings if f["severity"] == BLOCK]
    advices = [f for f in findings if f["severity"] == ADVICE]
    out = [
        "# 技术方案回查报告",
        "",
        f"- 被检查文件：`{design}`",
        f"- 阻塞项：{len(blocks)}",
        f"- 建议项：{len(advices)}",
        "",
    ]
    out.append("## 阻塞项" if blocks else "## 阻塞项（无）")
    out.append("")
    for finding in blocks:
        out.append(f"### {finding['title']}")
        out.append(f"- 说明：{finding['detail']}")
        if finding["evidence"]:
            out.append("- 证据：" + "；".join(finding["evidence"]))
        out.append("")
    out.append("## 建议项" if advices else "## 建议项（无）")
    out.append("")
    for finding in advices:
        out.append(f"### {finding['title']}")
        out.append(f"- 说明：{finding['detail']}")
        if finding["evidence"]:
            out.append("- 证据：" + "；".join(finding["evidence"]))
        out.append("")
    return "\n".join(out)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description="技术方案结构回查")
    parser.add_argument("--design", required=True, help="待检查的技术方案 Markdown")
    parser.add_argument("--prd", action="append", default=[], help="PRD 或验收标准，可多次传入")
    parser.add_argument(
        "--template",
        default=str(repo_root / "code-repo-analysis/模版/技术方案/后端技术方案.md"),
        help="《后端技术方案》模板路径",
    )
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--fail-on", choices=["blocking", "any", "none"], default="blocking")
    args = parser.parse_args()

    design_path = Path(args.design)
    if not design_path.is_file():
        print(f"找不到技术方案文件：{design_path}", file=sys.stderr)
        return 2

    lines = read_lines(design_path)
    text = "\n".join(lines)
    sections, cn_lines = parse_sections(lines)

    prd_lines: list[str] = []
    for prd in args.prd:
        prd_path = Path(prd)
        if not prd_path.is_file():
            print(f"找不到输入文件：{prd_path}", file=sys.stderr)
            return 2
        prd_lines.extend(read_lines(prd_path))

    chapters = load_template_chapters(Path(args.template))
    findings: list[dict] = []
    findings += check_structure(sections, cn_lines, chapters)
    findings += check_empty_sections(sections, lines)
    findings += check_requirement_coverage(text, prd_lines)
    findings += check_keywords(text)
    findings += check_anomaly_ratio(sections, lines)
    findings += check_redundancy(lines, prd_lines)
    findings += check_pending_items(lines)

    if args.format == "json":
        print(
            json.dumps(
                {"design": str(design_path), "findings": findings},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_markdown(design_path, findings))

    has_block = any(finding["severity"] == BLOCK for finding in findings)
    if args.fail_on == "blocking" and has_block:
        return 1
    if args.fail_on == "any" and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
