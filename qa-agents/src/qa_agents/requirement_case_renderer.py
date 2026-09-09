"""Deterministic renderer for compact requirement cards -> standard cases.

A compact requirement card is the approved authoring format for a requirement
whose expectations are expressed as oracle specs:

    ### `TC-BE-001` 自定义维度三类位置的专用错误与双语提示 · backend / critical / P0

    ## 测试场景
    ...

    ## 变体
    - dimension：...

    ## 前置条件
    - ...

    ## 测试步骤
    1. ...

    ## 预期结果
    - `EXP-BE-001-01`：三个变体均拒绝查看明细并返回错误码 s307011534。
       - deterministic · equals @ `detail_api.error.code` → `s307011534`

The renderer is deterministic and lossless:

- `parse_requirement_cards` normalizes the card into the
  `requirement-case/1.0` contract (see contracts/requirement-case.schema.json).
- `render_review_card` renders 测试场景 / 测试步骤 / 预期结果 for G02 review;
  section labels are emitted as bold body text (`**测试场景**`) so the font stays
  smaller than the card `##` headings while keeping bold emphasis. The 预期结果
  section is human-readable only: approved descriptions are kept verbatim and
  approved messages/error codes are spelled out in plain language; the machine
  oracle spec (type · matcher @ point → value) is kept only in the JSON review
  request / case IR, never on the card.
- `render_g02_review_items` emits the exact `review_items` shape consumed by
  g02_review.py so the card can enter the G02 review request directly.
- `render_case_ir` emits a test-case-ir/1.0 compatible parent case.

Oracle expected values are preserved verbatim: the renderer never rewrites,
translates, or normalizes approved messages or error codes.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
import re
from typing import Any

from .errors import ContractError
from .review_copy import has_cjk, humanize_review_item

SCHEMA_VERSION = "requirement-case/1.0"
RISK_VALUES = ("low", "medium", "high", "critical")
PRIORITY_VALUES = ("P0", "P1", "P2", "P3")
ALLOWED_SECTIONS = ("变体", "测试场景", "前置条件", "测试步骤", "预期结果")
CASE_CARDS_FILENAME = "case-cards.md"
CASE_CARDS_HEADER = (
    "# 中文用例\n"
    "\n"
    "请打开本文件阅读本次生成的全部父用例。"
    "每条格式为测试场景 / 前置条件 / 测试步骤 / 预期结果。\n"
    "未冻结的产品口径仍在 G02 任务卡「你需要拍板」里确认；"
    "不要打开 JSON 或自动化代码来审批用例。\n"
)

HEADER_RE = re.compile(
    r"^#{3}\s*`(?P<case_id>[^`]+)`\s+(?P<title>.+?)\s*·\s*(?P<attrs>.+?)\s*$"
)
SECTION_RE = re.compile(r"^#{2,3}\s+(?P<name>.+?)\s*$")
EXP_RE = re.compile(r"^\s*-\s*`(?P<exp_id>[^`]+)`\s*[：:]\s*(?P<description>.+?)\s*$")
ORACLE_RE = re.compile(
    r"^\s*-\s*(?P<oracle_type>[A-Za-z_][A-Za-z0-9_]*)\s*·\s*"
    r"(?P<matcher>[A-Za-z_][A-Za-z0-9_]*)\s*@\s*`(?P<point>[^`]+)`\s*→\s*"
    r"(?P<value>.+?)\s*$"
)
VARIANT_RE = re.compile(r"^\s*-\s*(?P<variant_id>\S+)\s*[：:]\s*(?P<name>.+?)\s*$")
STEP_RE = re.compile(r"^\s*(?:\d+[.、]|\-)\s*(?P<step>.+?)\s*$")
BULLET_RE = re.compile(r"^\s*-\s*(?P<body>.+?)\s*$")


def _parse_header(line: str) -> dict[str, str]:
    match = HEADER_RE.match(line)
    if not match:
        raise ContractError(
            "Requirement card header must be "
            "`### `ID` Title · layer / risk / priority`"
        )
    attrs = [part.strip() for part in match.group("attrs").split("/")]
    if len(attrs) != 3 or not all(attrs):
        raise ContractError("Requirement card header attributes must be `layer / risk / priority`")
    layer, risk, priority = attrs
    if risk not in RISK_VALUES:
        raise ContractError(f"Requirement risk must be one of {RISK_VALUES}: {risk}")
    if priority not in PRIORITY_VALUES:
        raise ContractError(f"Requirement priority must be one of {PRIORITY_VALUES}: {priority}")
    return {
        "id": match.group("case_id").strip(),
        "title": match.group("title").strip(),
        "layer": layer,
        "risk": risk,
        "priority": priority,
    }


def _parse_sections(lines: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Split card body into sections and position-bound expectation entries.

    Each expectation entry carries the oracle lines that immediately follow it,
    so every EXP-* bullet binds exactly to its own oracle line(s).
    """
    sections: dict[str, list[str]] = {}
    expectations: list[dict[str, Any]] = []
    current: str | None = None
    current_exp_id: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        section = SECTION_RE.match(line)
        if section:
            name = section.group("name").strip()
            if name not in ALLOWED_SECTIONS:
                raise ContractError(f"Unknown requirement card section: {name}")
            current = name
            current_exp_id = None
            sections.setdefault(name, [])
            continue
        exp = EXP_RE.match(line)
        if exp:
            exp_id = exp.group("exp_id")
            if any(entry["id"] == exp_id for entry in expectations):
                raise ContractError(f"Duplicate expectation id: {exp_id}")
            expectations.append(
                {
                    "id": exp_id,
                    "description": exp.group("description"),
                    "oracle_lines": [],
                }
            )
            current_exp_id = exp_id
            continue
        if ORACLE_RE.match(line):
            if current_exp_id is None:
                raise ContractError("Oracle line found without a preceding expectation")
            expectations[-1]["oracle_lines"].append(line)
            continue
        if current is None:
            raise ContractError(
                "Expectation bullets must appear after the card header; "
                f"unexpected line: {stripped}"
            )
        sections[current].append(stripped)
    return sections, expectations


def _oracle_from_lines(lines: list[str], exp_id: str) -> dict[str, str]:
    oracles = []
    for line in lines:
        match = ORACLE_RE.match(line)
        if not match:
            continue
        value = match.group("value")
        if value.startswith("`") and value.endswith("`"):
            value = value[1:-1]
        oracles.append(
            {
                "type": match.group("oracle_type"),
                "matcher": match.group("matcher"),
                "observation_point": match.group("point"),
                "expected_value": value,
            }
        )
    if not oracles:
        raise ContractError(f"Expectation {exp_id} must declare an oracle line: "
                            "`- deterministic · equals @ `point` → `value``")
    if len(oracles) > 1:
        raise ContractError(f"Expectation {exp_id} must declare exactly one oracle line")
    return oracles[0]


def _parse_variants(lines: list[str]) -> list[dict[str, str]]:
    variants: list[dict[str, str]] = []
    for line in lines:
        match = VARIANT_RE.match(line)
        if not match:
            raise ContractError(f"Invalid 变体 line: {line}")
        variants.append(
            {"id": match.group("variant_id").strip(), "name": match.group("name").strip()}
        )
    return variants


def _parse_steps(lines: list[str]) -> list[str]:
    steps: list[str] = []
    for line in lines:
        match = STEP_RE.match(line)
        if not match:
            raise ContractError(f"Invalid 测试步骤 line: {line}")
        steps.append(match.group("step"))
    return steps


def _parse_preconditions(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        match = BULLET_RE.match(line)
        if not match:
            raise ContractError(f"Invalid 前置条件 line: {line}")
        items.append(match.group("body"))
    return items


def _observation_points(expected: Iterable[Mapping[str, Any]]) -> list[str]:
    points: list[str] = []
    for item in expected:
        point = str(item.get("oracle", {}).get("observation_point", ""))
        if point and point not in points:
            points.append(point)
    return points


def _synthesize_steps(
    scenario: str, variants: list[dict[str, str]], expected: list[dict[str, Any]]
) -> list[str]:
    points = _observation_points(expected)
    if variants:
        steps = [
            f"构造并保存 {variant['name']} 变体资产，配置回查确认需求指定字段精确出现在该位置"
            for variant in variants
        ]
        steps.append("通过各变体资产的查看明细入口实际触发查看明细，记录 detail_api 响应")
    else:
        steps = [
            "按需求定义构造并保存资产，配置回查确认需求指定字段精确出现在指定位置",
            "通过保存资产的查看明细入口实际触发查看明细，记录 detail_api 响应",
        ]
    if points:
        steps.append(f"比对 {', '.join(points)} 实际值与预期结果")
    return steps


def parse_requirement_cards(text: str) -> list[dict[str, Any]]:
    """Parse one or more compact requirement cards into requirement-case/1.0."""
    raw_lines = text.splitlines()
    cards: list[dict[str, Any]] = []
    current_header: dict[str, str] | None = None
    body_lines: list[str] = []
    seen_ids: set[str] = set()

    def flush() -> None:
        nonlocal current_header, body_lines
        if current_header is None:
            return
        sections, expectation_entries = _parse_sections(body_lines)
        expected: list[dict[str, Any]] = []
        for entry in expectation_entries:
            expected.append(
                {
                    "id": entry["id"],
                    "description": entry["description"],
                    "oracle": _oracle_from_lines(entry["oracle_lines"], entry["id"]),
                }
            )

        variants = _parse_variants(sections.get("变体", []))
        preconditions = _parse_preconditions(sections.get("前置条件", []))
        authored_steps = sections.get("测试步骤", [])
        steps = _parse_steps(authored_steps) if authored_steps else None
        scenario_lines = sections.get("测试场景", [])
        scenario = " ".join(scenario_lines).strip() if scenario_lines else None

        if not expected:
            raise ContractError(f"Requirement {current_header['id']} has no 预期结果")
        if scenario is None:
            scenario = f"{current_header['title']}：{expected[0]['description']}"
        if steps is None:
            steps = _synthesize_steps(scenario, variants, expected)
        if not steps:
            raise ContractError(f"Requirement {current_header['id']} has no 测试步骤")

        card = {
            "schema_version": SCHEMA_VERSION,
            "requirement": dict(current_header),
            "scenario": scenario,
            "steps": steps,
            "expected": expected,
        }
        if variants:
            card["variants"] = variants
        if preconditions:
            card["preconditions"] = preconditions
        validate_requirement_case(card)
        if card["requirement"]["id"] in seen_ids:
            raise ContractError(f"Duplicate requirement card id: {card['requirement']['id']}")
        seen_ids.add(card["requirement"]["id"])
        cards.append(card)
        current_header = None
        body_lines = []

    for line in raw_lines:
        header = HEADER_RE.match(line)
        if header:
            flush()
            current_header = _parse_header(line)
            body_lines = []
            continue
        if current_header is not None:
            body_lines.append(line)
    flush()
    if not cards:
        raise ContractError("No requirement card found in input")
    return cards


def validate_requirement_case(case: Mapping[str, Any]) -> None:
    """Manual validation mirroring contracts/requirement-case.schema.json."""
    if case.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"Requirement case schema_version must be {SCHEMA_VERSION}")
    requirement = case.get("requirement")
    if not isinstance(requirement, Mapping):
        raise ContractError("Requirement case requires a requirement object")
    for field in ("id", "title", "layer", "risk", "priority"):
        if not str(requirement.get(field, "")).strip():
            raise ContractError(f"Requirement case requires requirement.{field}")
    if requirement.get("risk") not in RISK_VALUES:
        raise ContractError("Requirement case risk is invalid")
    if requirement.get("priority") not in PRIORITY_VALUES:
        raise ContractError("Requirement case priority is invalid")
    if not str(case.get("scenario", "")).strip():
        raise ContractError("Requirement case requires scenario")
    steps = case.get("steps")
    if not isinstance(steps, list) or not steps or not all(str(s).strip() for s in steps):
        raise ContractError("Requirement case requires non-empty steps")
    expected = case.get("expected")
    if not isinstance(expected, list) or not expected:
        raise ContractError("Requirement case requires non-empty expected")
    ids: set[str] = set()
    for item in expected:
        if not isinstance(item, Mapping):
            raise ContractError("Requirement case expected items must be objects")
        exp_id = str(item.get("id", ""))
        if not exp_id or exp_id in ids:
            raise ContractError("Requirement case expected ids must be unique and non-empty")
        ids.add(exp_id)
        if not str(item.get("description", "")).strip():
            raise ContractError(f"Requirement case expected {exp_id} requires description")
        oracle = item.get("oracle")
        if not isinstance(oracle, Mapping):
            raise ContractError(f"Requirement case expected {exp_id} requires oracle")
        for field in ("type", "matcher", "observation_point"):
            if not str(oracle.get(field, "")).strip():
                raise ContractError(f"Requirement case expected {exp_id} requires oracle.{field}")
        if "expected_value" not in oracle:
            raise ContractError(f"Requirement case expected {exp_id} requires oracle.expected_value")


def normalize_ir_parent_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt a test-case-ir/1.0 parent case into requirement-case/1.0 shape.

    The A08 test-design IR parent cases already carry real steps, preconditions,
    test_data and approved EXP oracles; this adapter preserves them and
    synthesizes a scenario from the title and the first expectation when absent.
    """
    expected: list[dict[str, Any]] = []
    for item in case.get("expected", []):
        if not isinstance(item, Mapping):
            continue
        oracle = item.get("oracle")
        if isinstance(oracle, Mapping):
            oracle = {
                "type": str(oracle.get("type", "")),
                "matcher": str(oracle.get("matcher", "")),
                "observation_point": str(oracle.get("observation_point", "")),
                "expected_value": str(oracle.get("expected_value", "")),
            }
        else:
            oracle = {
                "type": str(item.get("oracle_type", "")),
                "matcher": str(item.get("matcher", "")),
                "observation_point": str(item.get("observation_point", "")),
                "expected_value": str(item.get("expected_value", "")),
            }
        expected.append(
            {
                "id": str(item.get("id", "")),
                "description": str(item.get("description", "")),
                "oracle": oracle,
            }
        )
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "requirement": {
            "id": str(case.get("id", "")),
            "title": str(case.get("title", "")),
            "layer": str(case.get("layer", "")),
            "risk": str(case.get("risk", "")),
            "priority": str(case.get("priority", "")),
        },
        "scenario": str(case.get("scenario", "")),
        "steps": [
            str(step) for step in case.get("steps", []) if isinstance(step, str)
        ],
        "expected": expected,
    }
    preconditions = [
        str(item) for item in case.get("preconditions", []) if isinstance(item, str)
    ]
    if preconditions:
        normalized["preconditions"] = preconditions
    variants = case.get("test_data")
    if isinstance(variants, Mapping) and variants.get("variants"):
        normalized["variants"] = variants["variants"]
    if not normalized["scenario"] and expected:
        normalized["scenario"] = (
            f"{normalized['requirement']['title']}：{expected[0]['description']}"
        )
    if not normalized["steps"]:
        normalized["steps"] = _synthesize_steps(
            normalized["scenario"], normalized.get("variants", []), expected
        )
    return normalized


def _case_parts(case: Mapping[str, Any]) -> tuple[dict[str, str], str, list[str], list[str], list[dict[str, Any]]]:
    """Extract (requirement meta, scenario, preconditions, steps, expected) from
    either a requirement-case/1.0 card or a test-case-ir parent case."""
    requirement_mapping = case.get("requirement")
    if isinstance(requirement_mapping, Mapping):
        requirement = {
            field: str(requirement_mapping.get(field, ""))
            for field in ("id", "title", "layer", "risk", "priority")
        }
        scenario = str(case.get("scenario", ""))
        preconditions = [
            str(item) for item in case.get("preconditions", []) if isinstance(item, str)
        ]
        steps = [str(item) for item in case.get("steps", []) if isinstance(item, str)]
        expected = case.get("expected", [])
    else:
        requirement = {
            "id": str(case.get("id") or case.get("case_id") or ""),
            "title": str(case.get("title", "")),
            "layer": str(case.get("layer", "")),
            "risk": str(case.get("risk", "")),
            "priority": str(case.get("priority", "")),
        }
        scenario = str(case.get("scenario", ""))
        preconditions = [
            str(item) for item in case.get("preconditions", []) if isinstance(item, str)
        ]
        steps = [str(item) for item in case.get("steps", []) if isinstance(item, str)]
        expected = case.get("expected", [])
    if not scenario and expected and isinstance(expected[0], Mapping):
        scenario = f"{requirement['title']}：{expected[0].get('description', '')}"
    if not steps:
        steps = _synthesize_steps(scenario, [], expected)
    return requirement, scenario, preconditions, steps, expected


def _oracle_parts(item: Mapping[str, Any]) -> dict[str, str]:
    oracle = item.get("oracle")
    if isinstance(oracle, Mapping):
        return {
            "type": str(oracle.get("type", "")),
            "matcher": str(oracle.get("matcher", "")),
            "observation_point": str(oracle.get("observation_point", "")),
            "expected_value": str(oracle.get("expected_value", "")),
        }
    return {
        "type": str(item.get("oracle_type", "")),
        "matcher": str(item.get("matcher", "")),
        "observation_point": str(item.get("observation_point", "")),
        "expected_value": str(item.get("expected_value", "")),
    }


def _human_expected_value(item: Mapping[str, Any]) -> str:
    """Human-readable enrichment for an expected result.

    The review card is for people: it keeps the approved EXP description and
    spells out approved messages/error codes when the description only refers
    to them indirectly (e.g. "消息精确为批准模板"). The machine oracle spec
    (type · matcher @ point → value) stays in the JSON review request and is
    never shown on the card.
    """
    oracle = _oracle_parts(item)
    matcher = oracle["matcher"]
    oracle_type = oracle["type"]
    point = oracle["observation_point"]
    value = oracle["expected_value"]
    description = str(item.get("description", ""))
    if matcher == "manual_confirmation" or oracle_type == "human_review":
        return ""
    if matcher == "not_contains":
        return f"（不得包含：`{value}`）"
    if matcher == "one_of":
        allowed = _parse_code_list(value)
        if not allowed:
            return ""
        if "message.zh_CN" in point:
            return "（允许文案：" + "、".join(f"「{entry}」" for entry in allowed) + "）"
        if "message.en" in point:
            return "（允许文案：" + "、".join(f"`{entry}`" for entry in allowed) + "）"
        if point.endswith("code") or ".code" in point or "_code" in point:
            return f"（允许错误码：{'、'.join(allowed)}）"
        return ""
    if "message.zh_CN" in point:
        return f"：「{value}」"
    if "message.en" in point:
        return f"：`{value}`"
    if point.endswith("code") or ".code" in point or "_code" in point:
        if matcher == "equals" and value not in description:
            return f"（错误码 `{value}`）"
    return ""


def _parse_code_list(value: str) -> list[str] | None:
    """Parse a Python-list literal like "['s307011535', 's307011537']" for display."""
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(parsed, list):
        return None
    codes = [str(item) for item in parsed if str(item)]
    return codes or None


def render_review_card(case: Mapping[str, Any], *, index: int | None = None) -> str:
    """Render a case as a 测试场景 / 测试步骤 / 预期结果 review card.

    Accepts both requirement-case/1.0 cards and test-case-ir parent cases /
    G02 review items; sections fall back deterministically when the input only
    carries expectations.
    """
    requirement, scenario, preconditions, steps, expected = _case_parts(case)
    copy = humanize_review_item(
        {
            "case_id": requirement["id"],
            "title": requirement["title"],
            "layer": requirement["layer"],
            "risk": requirement["risk"],
            "priority": requirement["priority"],
            "scenario": scenario,
            "preconditions": preconditions,
            "steps": steps,
            "expected": expected,
            "source_refs": case.get("source_refs", []),
            "human_title": case.get("human_title", ""),
            "plain_summary": case.get("plain_summary", ""),
        }
    )
    display_title = requirement["title"] if has_cjk(requirement["title"]) else copy["human_title"]
    display_scenario = scenario if has_cjk(scenario) else copy["plain_summary"]
    header_index = f"{index}. " if index is not None else ""
    lines = [
        f"### {header_index}`{requirement['id']}` {display_title}"
        f" · {requirement['layer']} / {requirement['risk']} / {requirement['priority']}",
        "",
        "**测试场景**",
        "",
        display_scenario,
        "",
    ]
    if preconditions:
        lines.extend(["**前置条件**", ""])
        lines.extend(f"- {item}" for item in preconditions)
        lines.append("")
    lines.extend(["**测试步骤**", ""])
    lines.extend(f"{i}. {step}" for i, step in enumerate(steps, start=1))
    lines.extend(["", "**预期结果**", ""])
    for item in expected:
        if not isinstance(item, Mapping):
            continue
        description = str(item.get("description", "")).strip()
        enrichment = _human_expected_value(item)
        if enrichment:
            description = description.rstrip("。.") + enrichment
        lines.append(f"- `{item.get('id', '')}`：{description}")
    return "\n".join(lines)


def render_review_cards(cases: Iterable[Mapping[str, Any]]) -> str:
    """Render multiple requirement cases as a numbered G02 review card bundle."""
    blocks = [
        render_review_card(case, index=index)
        for index, case in enumerate(cases, start=1)
    ]
    return "\n\n".join(blocks)


def render_case_cards_document(cases: Iterable[Mapping[str, Any]]) -> str:
    """Render the human-approval case file written next to the G02 task card."""
    cards = render_review_cards(cases).strip()
    if not cards:
        return CASE_CARDS_HEADER + "\n（本轮没有可渲染的父用例。）\n"
    return CASE_CARDS_HEADER + "\n" + cards + "\n"


def render_g02_review_items(cases: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Render requirement cases into the exact review_items shape of g02_review.py."""
    items: list[dict[str, Any]] = []
    for case in cases:
        requirement = case["requirement"]
        expected = [
            {
                "id": item["id"],
                "description": item["description"],
                "oracle_type": item["oracle"]["type"],
                "matcher": item["oracle"]["matcher"],
                "observation_point": item["oracle"]["observation_point"],
                "expected_value": item["oracle"]["expected_value"],
            }
            for item in case["expected"]
        ]
        item = {
            "case_id": requirement["id"],
            "title": requirement["title"],
            "layer": requirement["layer"],
            "risk": requirement["risk"],
            "priority": requirement["priority"],
            "source_refs": [
                f"requirement-case/{requirement['id']}"
            ],
            "scenario": str(case.get("scenario", "")),
            "preconditions": [
                str(entry) for entry in case.get("preconditions", [])
                if isinstance(entry, str)
            ],
            "steps": [
                str(entry) for entry in case.get("steps", []) if isinstance(entry, str)
            ],
            "expected": expected,
        }
        item.update(humanize_review_item(item))
        items.append(item)
    return items


def render_case_ir(case: Mapping[str, Any]) -> dict[str, Any]:
    """Render a requirement case into a test-case-ir/1.0 compatible parent case."""
    requirement = case["requirement"]
    test_data: dict[str, Any] = {}
    if case.get("variants"):
        test_data["variants"] = case["variants"]
    return {
        "id": requirement["id"],
        "title": requirement["title"],
        "intent_ids": [requirement["id"]],
        "layer": requirement["layer"],
        "risk": requirement["risk"],
        "priority": requirement["priority"],
        "source_refs": [{"id": requirement["id"], "location": "requirement-case", "type": "requirement"}],
        "preconditions": list(case.get("preconditions", [])),
        "test_data": test_data,
        "steps": list(case["steps"]),
        "expected": [
            {
                "id": item["id"],
                "description": item["description"],
                "oracle": {
                    "type": item["oracle"]["type"],
                    "matcher": item["oracle"]["matcher"],
                    "observation_point": item["oracle"]["observation_point"],
                    "expected_value": item["oracle"]["expected_value"],
                },
            }
            for item in case["expected"]
        ],
        "cleanup": [],
        "execution_policy": {
            "allowed_modes": ["manual"],
            "required_evidence": ["structured_manual_result"],
        },
        "automation_candidate": False,
    }


def render_requirement_case_bundle(input_path, output_dir) -> dict[str, Any]:
    """CLI entry: parse a compact requirement card file and render all outputs."""
    from pathlib import Path

    from .storage import ArtifactStore

    input_path = Path(input_path)
    output_dir = Path(output_dir)
    if not input_path.is_file():
        raise ContractError(f"Requirement card input is missing: {input_path}")
    text = input_path.read_text(encoding="utf-8")
    cases = parse_requirement_cards(text)
    store = ArtifactStore(output_dir)
    if len(cases) == 1:
        store.write_json("requirement-case.json", cases[0])
        store.write_text("case-card.md", render_review_card(cases[0]))
    else:
        store.write_json("requirement-cases.json", {"schema_version": SCHEMA_VERSION, "cases": cases})
        store.write_text(CASE_CARDS_FILENAME, render_case_cards_document(cases))
    store.write_json("g02-review-items.json", {"schema_version": "g02-review-items/1.0", "items": render_g02_review_items(cases)})
    irs = [render_case_ir(case) for case in cases]
    store.write_json("case-ir.json" if len(irs) == 1 else "case-irs.json", irs[0] if len(irs) == 1 else irs)
    return {
        "output_dir": str(output_dir),
        "requirement_count": len(cases),
        "requirement_ids": [case["requirement"]["id"] for case in cases],
        "expected_count": sum(len(case["expected"]) for case in cases),
        "artifacts": sorted(item.name for item in output_dir.iterdir() if item.is_file()),
    }
