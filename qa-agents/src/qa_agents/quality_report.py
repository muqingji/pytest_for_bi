"""Human-readable N12 quality report rendered on Multica record cards."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .quality_results import render_quality_results_markdown
from .constructed_assets import category_for_resource_type


_DECISION_ZH = {
    "passed": "测试通过，可以准出",
    "passed_with_warning": "测试通过，但需关注告警",
    "completed_with_defects": "测试完成，存在缺陷，暂不建议准出",
    "blocked": "测试未通过，不准出",
    "inconclusive": "证据不足，暂不能给出准出结论",
}

_RELEASE_ZH = {
    "approved": "建议发布",
    "pending": "暂缓发布，待缺陷修复并复测",
    "blocked": "禁止发布",
}


def render_standard_quality_report(
    report_artifact: Mapping[str, Any],
    *,
    case_outcomes: Sequence[Mapping[str, Any]] | None = None,
    quality_summary: str = "",
    constructed_assets: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Render the standard report shown inside the N12 ``产出`` section."""

    payload = report_artifact.get("payload")
    if not isinstance(payload, Mapping):
        payload = {}
    assets_by_case: dict[str, list[dict[str, str]]] = {}
    for asset in constructed_assets or []:
        if not isinstance(asset, Mapping):
            continue
        case_id = str(asset.get("case_id") or "").strip()
        if not case_id:
            continue
        assets_by_case.setdefault(case_id, []).append(
            {
                "category": category_for_resource_type(str(asset.get("resource_type") or "")),
                "display_name": str(asset.get("display_name") or "").strip(),
                "resource_id": str(asset.get("resource_id") or "").strip(),
            }
        )
    outcomes = []
    for raw in case_outcomes or []:
        if not isinstance(raw, Mapping):
            continue
        outcome = dict(raw)
        outcome["test_assets"] = assets_by_case.get(str(raw.get("case_id") or "").strip(), [])
        outcomes.append(outcome)
    counts = Counter(str(item.get("status") or "skipped") for item in outcomes)
    executed = counts["passed"] + counts["failed"]
    decision = str(payload.get("decision") or "inconclusive")
    release = str(payload.get("release_disposition") or "pending")
    bug_count = int(payload.get("bug_draft_count") or 0)
    workflow_run_id = str(report_artifact.get("workflow_run_id") or "未记录")

    lines = [
        "## 标准测试报告",
        "",
        "### 1. 报告结论",
        "",
        f"- 测试结论：**{_DECISION_ZH.get(decision, decision)}**",
        f"- 发布建议：**{_RELEASE_ZH.get(release, release)}**",
        f"- 结论摘要：{quality_summary or '未提供'}",
        "",
        "### 2. 测试概况",
        "",
        f"- 工作流运行：`{workflow_run_id}`",
        f"- 纳入报告：`{len(outcomes)}` 条用例",
        f"- 实际执行：`{executed}` 条；通过 `{counts['passed']}` 条，不通过 `{counts['failed']}` 条",
        f"- 未执行：`{counts['skipped']}` 条",
        f"- 待跟进缺陷：`{bug_count}` 个",
        "",
        "### 3. 准出依据",
        "",
    ]
    if counts["failed"]:
        lines.append(f"- 有 `{counts['failed']}` 条实际执行用例不通过，缺陷修复并复测通过前不建议发布。")
    elif counts["skipped"]:
        lines.append(f"- 已执行用例全部通过；仍有 `{counts['skipped']}` 条未执行，需结合风险确认是否发布。")
    else:
        lines.append("- 纳入范围的用例均已执行通过，当前证据支持准出。")
    if bug_count:
        lines.append(f"- 已形成 `{bug_count}` 个缺陷草稿，需完成提单、修复和回归闭环。")

    result_section = render_quality_results_markdown(outcomes)
    if result_section:
        detail = result_section.replace("## 服务端测试结果\n\n", "", 1)
        detail = detail.replace("### 通过", "#### 通过")
        detail = detail.replace("### 不通过", "#### 不通过")
        detail = detail.replace("### 未执行", "#### 未执行")
        lines.extend(["", "### 4. 用例执行明细", "", detail.rstrip()])

    lines.extend(
        [
            "",
            "### 5. 风险与后续动作",
            "",
            "- 不通过用例：研发修复后按原场景和 TraceId 关联链路复测。" if counts["failed"] else "- 当前无不通过用例。",
            "- 未执行用例：补齐对应测试能力后执行，不能按通过计入准出证据。" if counts["skipped"] else "- 当前无未执行用例。",
            "- 报告反馈请在“报告反馈入口”子任务中登记，保证结论可追溯。",
        ]
    )
    return "\n".join(lines)
