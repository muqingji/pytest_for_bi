"""Deterministic N12-style local reports for workflow development."""

from __future__ import annotations

from html import escape
from typing import Any, Mapping

from .errors import ContractError


def render_text(summary: Mapping[str, Any]) -> str:
    lines = [
        "QA Multi-Agent Workflow Report",
        "=" * 80,
        f"Run: {summary['workflow_run_id']}",
        f"Mode: {summary['workflow_mode']}",
        f"Status: {summary['status']}",
        f"Stopped at: {summary['stopped_at']}",
        "",
        "Nodes:",
    ]
    for node in summary.get("nodes", []):
        reason = f" ({node['reason_code']})" if node.get("reason_code") else ""
        lines.append(f"  [{node['status'].upper()}] {node['id']}{reason}")
    issues = summary.get("validation_issues", [])
    lines.extend(["", f"Validation issues: {len(issues)}"])
    for issue in issues:
        lines.append(
            f"  [{issue.get('severity', 'error').upper()}] "
            f"{issue.get('issue_code')}: {issue.get('message')} @ {issue.get('path')}"
        )
    lines.extend(
        [
            "",
            "Safety:",
            "  Business repositories: read-only",
            "  Oracle exposed to agents: no",
            "  Quality conclusion: not calculated before N11",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(summary: Mapping[str, Any]) -> str:
    node_rows = "".join(
        "<tr>"
        f"<td>{escape(str(node['id']))}</td>"
        f"<td><span class='status {escape(str(node['status']))}'>{escape(str(node['status']))}</span></td>"
        f"<td>{escape(str(node.get('reason_code') or ''))}</td>"
        "</tr>"
        for node in summary.get("nodes", [])
    )
    issue_rows = "".join(
        "<tr>"
        f"<td>{escape(str(issue.get('issue_code', '')))}</td>"
        f"<td>{escape(str(issue.get('message', '')))}</td>"
        f"<td>{escape(str(issue.get('path', '')))}</td>"
        f"<td>{escape(str(issue.get('route_to', '')))}</td>"
        "</tr>"
        for issue in summary.get("validation_issues", [])
    ) or "<tr><td colspan='4'>No contract validation issues</td></tr>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QA Multi-Agent Report</title>
  <style>
    body {{ font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #202124; margin: 32px; }}
    main {{ max-width: 1080px; margin: 0 auto; }}
    h1 {{ font-size: 24px; }} h2 {{ font-size: 17px; margin-top: 28px; }}
    .meta {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 24px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border: 1px solid #dfe1e5; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f8f9fa; }}
    .status {{ font-weight: 600; }} .completed {{ color: #137333; }}
    .completed_with_gaps, .needs_human {{ color: #b06000; }}
    .failed_fatal, .blocked_input {{ color: #b3261e; }}
    .safety {{ border-left: 4px solid #137333; padding: 8px 12px; background: #f1f8f4; }}
  </style>
</head>
<body><main>
  <h1>QA Multi-Agent Workflow Report</h1>
  <div class="meta">
    <div><b>Run</b>: {escape(str(summary['workflow_run_id']))}</div>
    <div><b>Status</b>: {escape(str(summary['status']))}</div>
    <div><b>Mode</b>: {escape(str(summary['workflow_mode']))}</div>
    <div><b>Stopped at</b>: {escape(str(summary['stopped_at']))}</div>
  </div>
  <h2>Node Results</h2>
  <table><thead><tr><th>Node</th><th>Status</th><th>Reason</th></tr></thead><tbody>{node_rows}</tbody></table>
  <h2>Contract Validation</h2>
  <table><thead><tr><th>Code</th><th>Message</th><th>Path</th><th>Route</th></tr></thead><tbody>{issue_rows}</tbody></table>
  <h2>Safety Boundary</h2>
  <div class="safety">Business sources stayed read-only. Agent inputs did not include the Oracle Registry. This reference chain does not calculate a release decision before N11.</div>
</main></body></html>
"""


def render_multica_alignment_markdown(
    artifact: Mapping[str, Any], bundle: Mapping[str, Any]
) -> str:
    """Render the accepted A06 Artifact without changing its quality conclusion."""

    if artifact.get("artifact_id") != "a06-alignment-result":
        raise ContractError("Expected an A06 alignment Artifact")
    payload = artifact.get("payload")
    if not isinstance(payload, Mapping):
        raise ContractError("A06 Artifact payload is invalid")
    if payload.get("input_bundle_hash") != bundle.get("bundle_hash"):
        raise ContractError("A06 report bundle does not match the Artifact")
    if artifact.get("workflow_run_id") != bundle.get("workflow_run_id"):
        raise ContractError("A06 report inputs belong to different workflow runs")
    requirement_items = (
        bundle.get("allowed_inputs", {})
        .get("requirement_analysis", {})
        .get("requirements", [])
    )
    requirement_titles = {
        str(item.get("id")): str(item.get("summary", "")) for item in requirement_items
    }
    mappings = payload.get("mappings", [])
    findings = payload.get("findings", [])
    severity_counts: dict[str, int] = {}
    for finding in findings:
        severity = str(finding.get("severity", "unknown"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    lines = [
        "# A06 需求与变更对齐报告",
        "",
        f"- Workflow Run: `{artifact.get('workflow_run_id', '')}`",
        f"- Source Snapshot: `{artifact.get('source_snapshot_id', '')}`",
        f"- 结果状态: `{artifact.get('status', '')}`",
        f"- 需求映射: {len(mappings)} 条",
        f"- 对齐问题: {len(findings)} 条",
        f"- 严重度统计: {', '.join(f'{key}={value}' for key, value in sorted(severity_counts.items())) or '无'}",
        "",
        "## 需求对齐",
        "",
        "| 需求 | 对齐状态 | 技术事实 | 实现事实 |",
        "| --- | --- | --- | --- |",
    ]
    for mapping in mappings:
        requirement_id = str(mapping.get("requirement_id", ""))
        title = requirement_titles.get(requirement_id, "")
        requirement_label = f"{requirement_id} {title}".strip().replace("|", "\\|")
        technical_ids = ", ".join(map(str, mapping.get("technical_fact_ids", []))) or "无"
        change_ids = ", ".join(map(str, mapping.get("change_fact_ids", []))) or "无"
        lines.append(
            f"| {requirement_label} | {mapping.get('status', '')} | {technical_ids} | {change_ids} |"
        )

    lines.extend(["", "## 对齐问题", ""])
    for index, finding in enumerate(findings, 1):
        lines.extend(
            [
                f"### {index}. [{str(finding.get('severity', '')).upper()}] {finding.get('id', '')} {finding.get('type', '')}",
                "",
                str(finding.get("summary", "")),
                "",
                f"- 关联需求: {', '.join(map(str, finding.get('requirement_ids', []))) or '无'}",
                f"- 技术事实: {', '.join(map(str, finding.get('technical_fact_ids', []))) or '无'}",
                f"- 实现事实: {', '.join(map(str, finding.get('implementation_ids', []))) or '无'}",
                f"- 证据引用: {', '.join(map(str, finding.get('source_refs', []))) or '无'}",
                "",
            ]
        )
    lines.extend(
        [
            "## 下一步",
            "",
            "当前结论必须进入 `G01` 人工范围与口径审核。未完成审批前，不得把 A08 Test Case IR 标记为最终批准。",
            "",
            "安全边界：业务仓库只读；Agent 未读取评估 Oracle；本报告由已验收 Artifact 确定性生成。",
            "",
        ]
    )
    return "\n".join(lines)


def render_scope_review_markdown(request: Mapping[str, Any]) -> str:
    if request.get("gate_id") != "G01" or request.get("schema_version") != "scope-review-request/1.1":
        raise ContractError("Expected a G01 scope review request")
    lines = [
        "## 目标",
        "",
        "确认需求口径和测试范围是否可以进入测试设计；有未确认项时，明确回流节点和责任人。",
        "",
        "## 背景",
        "",
        f"需求、技术方案和实际变更对齐后，仍有 {request.get('issue_count', 0)} 项需要处置。Agent 不能代替人工确认业务口径。",
        "",
        "## 范围",
        "",
        "包含：",
        "- 提示优先级、指标名称展示、what/whatList 范围、拼表文案、多语口径。",
        "- 需求与实现不一致或缺少证据的回流决定。",
        "",
        "不包含：",
        "- 不审批生产发布，不修改业务仓库，不代替研发补实现证据。",
        "",
        "## 输入材料",
        "",
        "- A02 需求分析",
        "- A03 技术可测性分析",
        "- A06 需求与实现对齐结果",
        "- 本 Issue 的审核请求和决策模板附件",
        "",
        "## 你需要审核什么",
        "",
        "1. 多个限制同时命中时，是否按“自定义维度 -> 结果集筛选 -> 动态关联 -> 多关联 -> 原关系异常”只展示第一个提示。",
        "2. 数据范围有多个结果集统计指标时，提示一个还是全部指标名，顺序如何。",
        "3. 特殊 what/whatList 的准确对象和字段范围。",
        "4. 拼表命中结果集筛选时，是否使用不含“统计图”的通用文案。",
        "5. 自定义维度提示是否同时覆盖下钻字段，并冻结中英文文案。",
        "6. Web/移动端是否只要沿用同一后端错误码和文案，无需额外规定提示组件样式。",
        "",
        "研发需要补证，不由审核人代替确认：",
        "- 动态关联判定是否过宽或漏判。",
        "- 统计图与拼表是否复用同一后端判定和异常透传。",
        "- 错误码平台中英文模板及指标名参数渲染是否已完成联调。",
        "",
        "## 你需要怎么做",
        "",
        "- 同意：评论“批准，按卡片中 6 项口径执行；研发补齐 3 项证据”。",
        "- 有不同意项：按编号写明口径，例如“2：只提示第一个指标名”。",
        "- 不继续：评论“拒绝”并说明原因。",
        "",
        "## 验收",
        "",
        "- 6 项业务口径都有明确结论。",
        "- 3 项研发补证有责任人，不被当作人工已确认。",
        "- 未批准前 N24/A08 不启动；批准后只进入测试设计。",
        "",
        "## 待处置明细与追溯信息",
        "",
        f"- Workflow Run: `{request.get('workflow_run_id', '')}`",
        f"- Source Snapshot: `{request.get('source_snapshot_id', '')}`",
        f"- Gate 状态: `{request.get('status', '')}`",
        f"- 当前决策: `{request.get('decision', '')}`",
        f"- 待处理问题: {request.get('issue_count', 0)} 条",
        f"- Request Hash: `{request.get('request_hash', '')}`",
        f"- 审批模式: `{request.get('review_policy', {}).get('approval_mode', '')}`",
        f"- 策略范围: `{request.get('review_policy', {}).get('policy_scope', '')}`",
        f"- 生产发布权限: `{request.get('review_policy', {}).get('production_release_authority', False)}`",
        f"- Policy Hash: `{request.get('review_policy', {}).get('policy_hash', '')}`",
        "",
        "审批不能只选择同意或拒绝。每个问题都必须记录处置、理由和责任人；上游 Artifact 哈希变化后，本审批自动失效。",
        "请阅读问题详情后，在本 Issue 新增一条评论，完整填写文末的审核表。只有当前绑定人员提交、请求哈希匹配且所有必填项通过校验，系统才会形成正式决策。单独修改卡片状态无效。",
        "",
    ]
    def review_suggestion(issue: Mapping[str, Any]) -> tuple[str, str, str]:
        detail = issue.get("detail", {})
        if not isinstance(detail, Mapping):
            detail = {}
        source = str(issue.get("source", ""))
        route = str(issue.get("route_to") or source).lower()
        disposition = f"return_to_{route}"
        owner = str(detail.get("owner") or {
            "A02": "产品负责人",
            "A03": "技术方案负责人",
            "A05": "研发负责人",
            "A06": "后端研发负责人",
        }.get(source, "对应负责人"))
        summary = str(detail.get("summary") or detail.get("message") or issue.get("issue_code", ""))
        rationale = str(detail.get("recommendation") or f"需确认并冻结：{summary}")
        return disposition, rationale.replace("|", "/"), owner.replace("|", "/")

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for issue in request.get("issues", []):
        grouped.setdefault(str(issue.get("source", "unknown")), []).append(issue)
    source_names = {"A02": "需求问题", "A03": "技术与可测性问题", "A06": "需求实现对齐问题"}
    for source in ("A02", "A03", "A06"):
        issues = grouped.get(source, [])
        if not issues:
            continue
        lines.extend([f"## {source_names[source]}（{len(issues)} 条）", ""])
        for index, issue in enumerate(issues, 1):
            detail = issue.get("detail", {})
            summary = detail.get("summary") or detail.get("message") or issue.get("issue_code", "")
            disposition, rationale, owner = review_suggestion(issue)
            lines.extend(
                [
                    f"### {source}-{index:02d} `{issue.get('issue_id', '')}`",
                    "",
                    str(summary),
                    "",
                    f"- 问题类型: `{issue.get('issue_code', '')}`",
                    f"- 严重度: `{issue.get('severity', '')}`",
                    f"- 建议回流: `{issue.get('route_to', '')}`",
                    f"- 建议处置: `{disposition}`",
                    f"- 建议责任人: {owner}",
                    f"- 建议方案: {rationale}",
                    f"- 原始 ID: `{detail.get('id', '')}`",
                ]
            )
            if detail.get("start_condition"):
                lines.append(f"- 恢复条件: {detail['start_condition']}")
            lines.append("")
    lines.extend(
        [
            "## 允许的决策",
            "",
            "- `approved`: 所有问题都必须为 `confirmed` 或 `resolved_upstream`。",
            "- `request_changes`: 指定问题回流 A02/A03/A05/A06，并填写理由和责任人。",
            "- `rejected`: 当前范围不进入后续测试设计。",
            "",
            "## 审核评论模板",
            "",
            "下面已按当前证据预填非绑定的 `request_changes` 建议。请逐项核对并修改，再将整段作为一条新评论提交；只有你的评论才是正式输入。若改为 `approved`，必须把全部处置改为 `confirmed` 或 `resolved_upstream`。",
            "",
            "G01 Decision Protocol | 1.0",
            f"Request Hash | {request.get('request_hash', '')}",
            "Decision |",
            "Overall Reason |",
            "Test Rules |",
            "Issue ID | Disposition | Rationale | Owner",
            "--- | --- | --- | ---",
            *[
                f"{item.get('issue_id', '')} | "
                + " | ".join(review_suggestion(item))
                for item in request.get("issues", [])
            ],
            "",
            "允许的 `Disposition`：`confirmed`、`resolved_upstream`、`return_to_a02`、`return_to_a03`、`return_to_a05`、`return_to_a06`。",
            "",
            "Agent 不能审批 G01。审批完成前，N24 和 A08 必须保持阻塞。",
            "",
        ]
    )
    return "\n".join(lines)


def render_evaluation_text(evaluation: Mapping[str, Any]) -> str:
    lines = [
        "QA Multi-Agent Offline Evaluation",
        "=" * 80,
        f"Run: {evaluation['workflow_run_id']}",
        f"Result: {'PASS' if evaluation['passed'] else 'FAIL'}",
        f"Checks: {evaluation['passed_checks']} passed / {evaluation['failed_checks']} failed",
        "",
        "Category recall:",
    ]
    for category, values in evaluation.get("categories", {}).items():
        lines.append(
            f"  {category}: {values['passed']} passed / {values['failed']} failed / "
            f"{values['total']} total"
        )
    failed = [item for item in evaluation.get("checks", []) if not item.get("passed")]
    lines.extend(["", f"Missing or mismatched checks ({len(failed)}):"])
    for index, item in enumerate(failed, start=1):
        lines.append(f"  [{index:02d}] {item['check']}")
        lines.append(f"       Expected: {item.get('expected')}")
        lines.append(f"       Actual: {item.get('actual')}")
    lines.extend(
        [
            "",
            "Evaluation safety:",
            "  Oracle was loaded only after workflow artifacts were frozen.",
            "  A broad parent Case is counted at most once across independent obligations.",
            "",
        ]
    )
    return "\n".join(lines)


def render_evaluation_html(evaluation: Mapping[str, Any]) -> str:
    category_rows = "".join(
        "<tr>"
        f"<td>{escape(str(category))}</td>"
        f"<td>{values['passed']}</td><td>{values['failed']}</td><td>{values['total']}</td>"
        "</tr>"
        for category, values in evaluation.get("categories", {}).items()
    )
    failed_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item['check']))}</td>"
        f"<td>{escape(str(item.get('expected', '')))}</td>"
        f"<td>{escape(str(item.get('actual', '')))}</td>"
        "</tr>"
        for item in evaluation.get("checks", [])
        if not item.get("passed")
    ) or "<tr><td colspan='3'>No failed checks</td></tr>"
    result_class = "passed" if evaluation["passed"] else "failed"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QA Multi-Agent Offline Evaluation</title>
  <style>
    body {{ font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #202124; margin: 32px; }}
    main {{ max-width: 1180px; margin: 0 auto; }}
    h1 {{ font-size: 24px; }} h2 {{ font-size: 17px; margin-top: 28px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border: 1px solid #dfe1e5; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f8f9fa; }} .passed {{ color: #137333; }} .failed {{ color: #b3261e; }}
    .safety {{ border-left: 4px solid #137333; padding: 8px 12px; background: #f1f8f4; }}
  </style>
</head>
<body><main>
  <h1>QA Multi-Agent Offline Evaluation</h1>
  <p>Run: {escape(str(evaluation['workflow_run_id']))} | <strong class="{result_class}">{'PASS' if evaluation['passed'] else 'FAIL'}</strong> | {evaluation['passed_checks']} passed / {evaluation['failed_checks']} failed</p>
  <h2>Category Recall</h2>
  <table><thead><tr><th>Category</th><th>Passed</th><th>Failed</th><th>Total</th></tr></thead><tbody>{category_rows}</tbody></table>
  <h2>Missing Or Mismatched Checks</h2>
  <table><thead><tr><th>Check</th><th>Expected</th><th>Actual</th></tr></thead><tbody>{failed_rows}</tbody></table>
  <h2>Evaluation Safety</h2>
  <div class="safety">Oracle data was loaded only after workflow artifacts were frozen. One broad parent Case is counted at most once across independent obligations.</div>
</main></body></html>
"""
