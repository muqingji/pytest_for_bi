"""Chinese N11 case-result display for Multica task cards.

Implements n11-quality-result-display: the 产出 section must list passed and
failed cases with product scenes and the actual request TraceIds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import json
import re
from typing import Any

from .review_copy import has_cjk

SCHEMA_VERSION = "n11-case-outcomes/1.0"

CASE_SCENE_ZH = {
    "PC-BE-001": "自定义维度三类位置拒绝查看明细",
    "PC-BE-002": "结果集指标筛选拒绝查看明细",
    "PC-BE-003": "多关联关系拒绝查看明细",
    "PC-BE-004": "动态关联关系拒绝查看明细",
    "PC-BE-005": "命中多条限制原因时只返回一条提示",
    "PC-BE-006": "没权限时保持原权限失败",
    "PC-BE-007": "历史配置原地生效且成功明细不丢",
    "PC-CT-001": "错误码透传并绑定中英文模板",
    "PC-E2E-001": "Web 统计图与拼表明细提示一致",
    "PC-E2E-002": "移动端与 Web 明细提示一致",
    "PC-E2E-003": "四个专用场景的中英文模板",
}

CASE_SCENARIO_ZH = {
    "PC-BE-001": (
        "自定义维度字段分别出现在统计图的维度、数据范围、下钻三类位置时，通过已保存资产的查看明细入口触发查看明细，"
        "均被拒绝进入明细视图：返回专用错误码 s307011534，中英文提示精确为批准模板。时分筛选对照路径不得被改写成该专用错误。"
    ),
    "PC-BE-002": (
        "统计图数据范围按结果集筛选普通、聚合、计算、同比/环比指标时，查看明细均被拒绝：返回专用错误码 s307011535，"
        "提示里带上真实指标显示名。多指标时按资产配置顺序带出全部指标名。下游复杂虚拟指标对照路径不得被改写成该专用错误。"
    ),
    "PC-BE-003": (
        "基于多关联关系创建的统计指标，在对象关系校验失败时拒绝查看明细：返回专用错误码 s307011536，中英文提示精确为批准模板。"
        "已经能成功解析关联关系、本来就能看明细的路径必须继续成功，不能被提前禁用。"
        "普通对象关系异常在未命中多关联原因时，不得被改写成 s307011536。"
    ),
    "PC-BE-004": (
        "基于动态关联关系（what/whatlist）创建的统计指标，覆盖业务流程、业务流程任务、服务记录字段且不加工单主题筛选时，"
        "查看明细被拒绝：返回专用错误码 s307011537，中英文提示精确为批准模板。受支持的普通 what/whatlist 对照路径必须继续成功。"
    ),
    "PC-BE-005": (
        "同一张统计图同时命中至少两条「暂不支持查看明细」专用原因时，只返回一条专用错误和一条提示，不得把多条原因拼成一句话。"
        "本条不验证产品固定优先级，也不混入权限失败。"
    ),
    "PC-BE-006": (
        "操作者没有查看明细权限，或看不到某些指标时，即使统计图本身也命中了「暂不支持查看明细」的专用原因，"
        "点击查看明细仍应走原来的权限失败：不能改成四个专用限制错误码，也不能把不该看见的指标名带出来。"
    ),
    "PC-BE-007": (
        "上线前就有的统计图和拼表不用改配置。点查看明细时，运行时按当前逻辑原地判断：本来就不支持的场景走新的专用提示；"
        "本来就能看的图，成功状态、分页和结果结构还在，明细字段展示能力不能丢。"
    ),
    "PC-CT-001": (
        "查看明细接口把四个专用错误码、中英文模板和结果集指标参数原样透传给错误码平台，并按请求当前语言绑定模板。"
        "成功查看明细的契约仍返回成功，且带分页和结果结构，不得返回四个新专用限制错误码。"
    ),
    "PC-E2E-001": (
        "同一不支持查看明细场景下，Web 统计图和 Web 拼表走同一套后端原因：错误码、当前语言提示、指标参数、后端原因都要一致。"
        "拼表可见文案与统计图一致。"
    ),
    "PC-E2E-002": (
        "移动端统计图、移动端拼表与 Web 统计图、Web 拼表在四个专用场景下保持一致：错误码、当前语言提示、后端原因、结果集指标参数相同。"
        "移动端必须走四个专用错误码，不能仍走旧的笼统提示。"
    ),
    "PC-E2E-003": (
        "在真实查看明细入口上，四个专用场景的中英文提示都必须精确等于批准模板。"
        "结果集筛选场景按当前语言代入真实指标显示名。"
    ),
}

ERROR_COPY_ZH = {
    "s307011534": "维度或数据范围中使用了自定义维度字段，暂不支持查看明细",
    "s307011535": "统计图数据范围中设置了「指标名称」按结果集筛选，不支持查看明细",
    "s307011536": "基于多关联关系创建的统计指标，暂不支持查看明细",
    "s307011537": "基于动态关联关系创建的统计指标，不支持查看明细",
    "s307050002": "当前场景暂不支持查看明细",
    "s307051518": "复杂虚拟指标原来的错误",
    "s307051519": "时分筛选原来的错误",
}
GENERIC_ERROR_CODES = {"s307050002"}

_STATUS_ZH = {
    "passed": "通过",
    "failed": "不通过",
    "blocked": "不通过",
    "skipped": "未执行",
    "not_executed": "未执行",
    "pending": "未执行",
}

_STATUS_RANK = {
    "blocked": 4,
    "failed": 3,
    "passed": 2,
    "pending": 1,
    "skipped": 1,
    "not_executed": 1,
}

_EXPECTED_GOT_RE = re.compile(
    r"expected (?P<expected>'[^']*'|\"[^\"]*\"|\S+), got (?P<actual>'[^']*'|\"[^\"]*\"|\S+)",
    re.IGNORECASE,
)
_PATH_MISSING_RE = re.compile(r"Path '([^'{}]+)' does not exist")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _merge_requests(
    left: Sequence[Mapping[str, Any]] | None,
    right: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, str]]:
    merged: dict[tuple[str, str], dict[str, str]] = {}
    order: list[tuple[str, str]] = []
    for source in (left or (), right or ()):
        for item in source:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            phase = str(item.get("phase") or "").strip()
            key = (phase, name)
            row = {
                "name": name,
                "phase": phase,
                "trace_id": str(item.get("trace_id") or "").strip(),
                "operation": str(item.get("operation") or ""),
            }
            existing = merged.get(key)
            if existing is None:
                merged[key] = row
                order.append(key)
            elif row["trace_id"] and not existing["trace_id"]:
                merged[key] = row
    return [merged[key] for key in order]


def _skipped_reason(layer: str) -> str:
    if layer == "e2e":
        return "E2E 尚未接入，已按策略跳过"
    if layer == "contract":
        return "契约用例未绑定接口契约，本轮未执行"
    return "本轮未执行"


def _parent_case_id(case_id: str) -> str:
    text = str(case_id or "").strip()
    for suffix in ("-BACKEND", "-CONTRACT", "-E2E"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _lookup_zh(case_id: str, table: dict[str, str]) -> str:
    cid = str(case_id or "").strip()
    parent = _parent_case_id(cid)
    if cid in table:
        return table[cid]
    if parent in table:
        return table[parent]
    return ""


def case_title_zh(case_id: str, title: str = "") -> str:
    raw_title = str(title or "").strip()
    mapped = _lookup_zh(case_id, CASE_SCENE_ZH)
    if mapped:
        return mapped
    if has_cjk(raw_title) and "。" not in raw_title and len(raw_title) <= 40:
        return raw_title
    cid = str(case_id or "").strip()
    from .asset_scene_naming import scene_display_name

    fallback = scene_display_name(case_id=cid, title=raw_title, allow_type_fallback=False)
    return fallback or raw_title or cid


def _scenario_from_compiled(compiled: Mapping[str, Any] | None) -> str:
    if not isinstance(compiled, Mapping):
        return ""
    for key in ("scenario", "test_scenario", "objective"):
        value = str(compiled.get(key) or "").strip()
        if has_cjk(value) and len(value) >= 12:
            return value
    parts: list[str] = []
    expected = compiled.get("expected")
    if isinstance(expected, list):
        for item in expected:
            if not isinstance(item, Mapping):
                continue
            desc = str(item.get("description") or "").strip()
            if has_cjk(desc) and len(desc) >= 12:
                parts.append(desc.rstrip("。") + "。")
            if len(parts) >= 3:
                break
    return "".join(parts)


def case_scenario_zh(
    case_id: str,
    title: str = "",
    compiled: Mapping[str, Any] | None = None,
) -> str:
    if isinstance(compiled, Mapping):
        for key in ("scenario", "test_scenario", "objective"):
            value = str(compiled.get(key) or "").strip()
            if has_cjk(value) and len(value) >= 12:
                return value
    mapped = _lookup_zh(case_id, CASE_SCENARIO_ZH)
    if mapped:
        return mapped
    from_compiled = _scenario_from_compiled(compiled)
    if from_compiled:
        return from_compiled
    raw_title = str(title or "").strip()
    if has_cjk(raw_title) and (len(raw_title) >= 12 or "。" in raw_title):
        return raw_title
    return case_title_zh(case_id, title)


def case_scene_zh(
    case_id: str,
    title: str = "",
    compiled: Mapping[str, Any] | None = None,
) -> str:
    """Full Chinese test scenario for N11 display."""
    return case_scenario_zh(case_id, title, compiled)


def _quote_zh(value: str) -> str:
    text = str(value or "").strip().strip("'\"")
    copy = ERROR_COPY_ZH.get(text)
    if copy:
        return f"「{copy}」"
    if has_cjk(text):
        return f"「{text}」"
    return f"`{text}`"


def _compiled_expected_messages(compiled: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(compiled, Mapping):
        return []
    messages: list[str] = []
    expected = compiled.get("expected")
    if not isinstance(expected, list):
        return messages
    for item in expected:
        if not isinstance(item, Mapping):
            continue
        oracle = item.get("oracle")
        value = oracle.get("expected_value") if isinstance(oracle, Mapping) else None
        if isinstance(value, str) and has_cjk(value) and len(value.strip()) >= 8:
            messages.append(value.strip())
    return messages


def human_failure_summary(
    raw: str,
    classification: str = "",
    *,
    compiled: Mapping[str, Any] | None = None,
) -> str:
    text = str(raw or "")
    expected_messages = _compiled_expected_messages(compiled)
    for match in _EXPECTED_GOT_RE.finditer(text):
        expected = match.group("expected").strip("'\"")
        actual = match.group("actual").strip("'\"")
        if "{" in expected or "{" in actual:
            continue
        expected_copy = ERROR_COPY_ZH.get(expected) or (
            expected_messages[0] if expected_messages and expected.startswith("s") else ""
        )
        actual_copy = ERROR_COPY_ZH.get(actual)
        expected_zh = _quote_zh(expected_copy or expected)
        actual_zh = _quote_zh(actual_copy or actual)
        if expected.isdigit() and int(expected) <= 5:
            return f"期望只返回一条专用提示，实际返回了{actual_zh}"
        if expected in ERROR_COPY_ZH and actual in GENERIC_ERROR_CODES:
            return f"实际仍返回旧的通用提示{actual_zh}，没有返回专用提示{expected_zh}"
        if expected in ERROR_COPY_ZH or actual in ERROR_COPY_ZH or has_cjk(actual) or has_cjk(expected):
            return f"实际返回了{actual_zh}，没有返回{expected_zh}"
        return f"期望 {expected_zh}，实际 {actual_zh}"
    missing = _PATH_MISSING_RE.search(text)
    if missing:
        path = missing.group(1)
        lowered = path.lower()
        if "params" in lowered:
            return "响应缺少指标名称参数，无法拼出带指标名的结果集筛选提示"
        if lowered.endswith("code") or lowered.endswith(".code"):
            return "响应缺少错误码，无法确认是否返回了专用错误"
        return f"响应缺少字段 `{path}`"
    if classification == "test_data":
        return "造数或绑图失败，用例没有真正跑完"
    if classification == "environment":
        return "环境问题导致执行失败"
    if classification == "automation_defect":
        return "自动化代码问题导致执行失败"
    if "AssertionError" in text:
        return "断言未通过"
    return "执行未通过"


def _trace_from_step(step: Mapping[str, Any]) -> str:
    return str(step.get("trace_id") or step.get("traceId") or "").strip()


def _requests_from_lifecycle(case_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    phases = case_payload.get("phases") if isinstance(case_payload.get("phases"), Mapping) else {}
    rows: list[dict[str, str]] = []
    for phase in ("test", "setup"):
        steps = phases.get(phase) if isinstance(phases.get(phase), list) else []
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            name = str(step.get("name") or "").strip()
            if not name:
                continue
            if str(step.get("status") or "") == "skipped":
                continue
            rows.append(
                {
                    "name": name,
                    "phase": phase,
                    "trace_id": _trace_from_step(step),
                    "operation": str(step.get("operation") or ""),
                }
            )
        if phase == "test" and any(item["trace_id"] for item in rows):
            break
    return rows


def _load_lifecycle_cases(execution_path: Path, payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    root = execution_path.parent.parent
    by_case: dict[str, dict[str, Any]] = {}
    for shard in payload.get("shards") or []:
        if not isinstance(shard, Mapping):
            continue
        relative = str(shard.get("lifecycle_evidence_path") or "").strip()
        if not relative:
            continue
        path = root / relative
        if not path.is_file():
            continue
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cases = body.get("cases") if isinstance(body, Mapping) else None
        if not isinstance(cases, list):
            continue
        for item in cases:
            if not isinstance(item, Mapping):
                continue
            case_id = str(item.get("case_id") or "").strip()
            if case_id:
                by_case[case_id] = dict(item)
    return by_case


def build_case_outcomes(
    *,
    case_results: Sequence[Mapping[str, Any]],
    cases_by_id: Mapping[str, Mapping[str, Any]],
    executions: Sequence[Mapping[str, Any]],
    execution_paths: Sequence[Path] = (),
    skipped_ids: Sequence[str] = (),
    failures: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    lifecycle_by_case: dict[str, dict[str, Any]] = {}
    stdout_by_case: dict[str, str] = {}
    for index, execution in enumerate(executions):
        payload = execution.get("payload") if isinstance(execution.get("payload"), Mapping) else execution
        if not isinstance(payload, Mapping):
            continue
        path = execution_paths[index] if index < len(execution_paths) else None
        if path is not None:
            lifecycle_by_case.update(_load_lifecycle_cases(Path(path), payload))
        for shard in payload.get("shards") or []:
            if not isinstance(shard, Mapping):
                continue
            blob = f"{shard.get('stdout') or ''}\n{shard.get('stderr') or ''}"
            for case_id in shard.get("case_ids") or []:
                stdout_by_case[str(case_id)] = blob
    failure_by_case: dict[str, Mapping[str, Any]] = {}
    for item in failures:
        if not isinstance(item, Mapping):
            continue
        for case_id in item.get("case_ids") or []:
            failure_by_case.setdefault(str(case_id), item)

    outcomes_by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in case_results:
        if not isinstance(item, Mapping):
            continue
        case_id = str(item.get("case_id") or "").strip()
        if not case_id:
            continue
        compiled = cases_by_id.get(case_id) or {}
        status = str(item.get("status") or "failed").strip() or "failed"
        failure = failure_by_case.get(case_id, {})
        reason = ""
        compiled_title = str(compiled.get("title") or "")
        if status in {"failed", "blocked"}:
            reason = human_failure_summary(
                stdout_by_case.get(case_id, "") or str(failure.get("summary") or ""),
                str(failure.get("classification") or ""),
                compiled=compiled,
            )
        elif status in {"skipped", "not_executed", "pending"}:
            reason = _skipped_reason(str(compiled.get("layer") or "").strip().lower())
        lifecycle = lifecycle_by_case.get(case_id) or {}
        candidate = {
            "case_id": case_id,
            "title": case_title_zh(case_id, compiled_title),
            "scene": case_scenario_zh(case_id, compiled_title, compiled),
            "status": status,
            "reason": reason,
            "requests": _requests_from_lifecycle(lifecycle),
        }
        existing = outcomes_by_id.get(case_id)
        if existing is None:
            outcomes_by_id[case_id] = candidate
            order.append(case_id)
            continue
        merged_requests = _merge_requests(existing.get("requests"), candidate.get("requests"))
        existing_rank = _STATUS_RANK.get(str(existing.get("status") or ""), 0)
        new_rank = _STATUS_RANK.get(status, 0)
        if new_rank > existing_rank:
            candidate["requests"] = merged_requests
            outcomes_by_id[case_id] = candidate
        else:
            existing["requests"] = merged_requests
            if not existing.get("reason") and candidate.get("reason"):
                existing["reason"] = candidate["reason"]
    outcomes = [outcomes_by_id[case_id] for case_id in order]
    seen = set(order)
    for case_id in skipped_ids:
        cid = str(case_id or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        compiled = cases_by_id.get(cid) or {}
        layer = str(compiled.get("layer") or "").strip().lower()
        compiled_title = str(compiled.get("title") or "")
        outcomes.append(
            {
                "case_id": cid,
                "title": case_title_zh(cid, compiled_title),
                "scene": case_scenario_zh(cid, compiled_title, compiled),
                "status": "skipped",
                "reason": _skipped_reason(layer),
                "requests": [],
            }
        )
    return outcomes


def render_quality_results_markdown(
    outcomes: Sequence[Mapping[str, Any]] | None,
    *,
    summary: str = "",
) -> str:
    rows = [dict(item) for item in outcomes or [] if isinstance(item, Mapping)]
    if not rows:
        return ""
    groups = (
        ("通过", ("passed",)),
        ("不通过", ("failed", "blocked")),
        ("未执行", ("skipped", "not_executed", "pending")),
    )
    lines = ["## 服务端测试结果", ""]
    if summary:
        lines.extend([f"结论：{summary}", ""])
    for title, statuses in groups:
        items = [item for item in rows if str(item.get("status") or "") in statuses]
        lines.append(f"### {title}")
        lines.append("")
        if not items:
            lines.append("- 无")
            lines.append("")
            continue
        for item in items:
            case_id = str(item.get("case_id") or "").strip() or "未记录用例"
            title = str(item.get("title") or "").strip()
            scene = str(item.get("scene") or "").strip()
            short = title or ("" if ("。" in scene or len(scene) >= 20) else scene)
            head = f"- `{case_id}`"
            if short:
                head += f" {short}"
            lines.append(head)
            if scene and scene != short:
                lines.append(f"  - 测试场景：{scene}")
            assets = item.get("test_assets") if isinstance(item.get("test_assets"), list) else []
            if assets:
                lines.append("  - 实际测试数据：")
                for asset in assets:
                    if not isinstance(asset, Mapping):
                        continue
                    category = str(asset.get("category") or "其他").strip()
                    name = str(asset.get("display_name") or "未记录名称").strip()
                    resource_id = str(asset.get("resource_id") or "未记录 ID").strip()
                    lines.append(f"    - {category}：`{name}`（`{resource_id}`）")
            elif str(item.get("status") or "") in {"skipped", "not_executed", "pending"}:
                lines.append("  - 实际测试数据：本轮未执行，未使用实际测试数据")
            elif "test_assets" in item:
                lines.append("  - 实际测试数据：未记录（需补充实际资产证据）")
            reason = str(item.get("reason") or "").strip()
            if reason:
                lines.append(f"  - 原因：{reason}")
            requests = item.get("requests") if isinstance(item.get("requests"), list) else []
            traces = [
                req
                for req in requests
                if isinstance(req, Mapping) and str(req.get("name") or "").strip()
            ]
            if traces:
                lines.append("  - 请求 TraceId：")
                for req in traces:
                    name = str(req.get("name") or "").strip()
                    trace_id = str(req.get("trace_id") or "").strip() or "未记录"
                    lines.append(f"    - `{name}`：`{trace_id}`")
            elif str(item.get("status") or "") not in {"skipped", "not_executed"}:
                lines.append("  - 请求 TraceId：未记录")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
