"""Deterministic Multica Issue-card rendering and accepted-result synchronization."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from .contracts import content_hash
from .agent_work_cards import get_agent_work_card, review_items
from .errors import ContractError, InputError, RetryableAgentError
from .security import SecurityPolicy


CommandRunner = Callable[[list[str], str], Mapping[str, Any]]


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except OSError as error:
        raise InputError(f"Required {label} cannot be read: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be a JSON object")
    return value


def _audit_fact(artifact: Mapping[str, Any]) -> Mapping[str, Any]:
    for fact in artifact.get("facts", []):
        if isinstance(fact, Mapping) and fact.get("type") == "multica_tool_trace_audit":
            return fact
    raise ContractError("Accepted Multica Artifact has no tool-trace audit fact")


def _item_text(item: Mapping[str, Any]) -> str:
    for field in ("summary", "message", "title", "capability", "description"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", " ")
    item_id = item.get("id") or item.get("requirement_id") or item.get("parent_case_id")
    return str(item_id or "Structured item")


def _compact_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return "; ".join(f"{key}={_compact_value(item)}" for key, item in value.items())
    if isinstance(value, list):
        return "；".join(_compact_value(item) for item in value)
    return str(value).strip().replace("\n", " ")


def _render_structured_item(item: Mapping[str, Any]) -> list[str]:
    """Render useful Agent output fields instead of hiding them in an attachment."""

    item_id = item.get("id") or item.get("requirement_id") or item.get("parent_case_id")
    title = item.get("title") or item.get("summary") or item.get("objective") or _item_text(item)
    heading = " ".join(part for part in (str(item_id or "").strip(), str(title).strip()) if part)
    lines = [f"#### {heading or '结构化结果'}", ""]
    labels = (
        ("layer", "层级"),
        ("risk", "风险"),
        ("priority", "优先级"),
        ("status", "状态"),
        ("objective", "目标"),
        ("description", "说明"),
        ("preconditions", "前置条件"),
        ("test_data", "测试数据"),
        ("steps", "步骤"),
        ("expected", "预期结果"),
        ("cleanup", "清理"),
        ("execution_policy", "执行方式"),
        ("case_ids", "覆盖 Case"),
        ("source_refs", "来源"),
    )
    rendered = False
    for field, label in labels:
        value = item.get(field)
        if value in (None, "", [], {}):
            continue
        lines.append(f"- {label}：{_compact_value(value)}")
        rendered = True
    if not rendered:
        lines.append(f"- 结果：{_item_text(item)}")
    lines.append("")
    return lines


def _render_a08_cases(payload: Mapping[str, Any]) -> list[str]:
    cases = payload.get("parent_cases", [])
    lines = ["## 测试 Case", ""]
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        lines.extend([f"### {case.get('id', '')} {case.get('title', '')}".strip(), ""])
        layer = case.get("layer")
        if layer:
            lines.append(f"- 类型：{layer}")
        datasets = case.get("test_data", {}).get("datasets", [])
        lines.append(f"- 测试场景：{_compact_value(datasets)}")
        lines.append(f"- 执行步骤：{_compact_value(case.get('steps', []))}")
        expected = [
            item.get("description", "")
            for item in case.get("expected", [])
            if isinstance(item, Mapping) and item.get("description")
        ]
        lines.append(f"- 预期结果：{_compact_value(expected)}")
        lines.append("")
    gaps = payload.get("blocking_gaps", [])
    if gaps:
        lines.extend(["## 暂不可直接执行的项", ""])
        lines.extend(f"- {item}" for item in gaps)
        lines.append("")
    return lines


def render_multica_issue_result_markdown(
    bundle: Mapping[str, Any], artifact: Mapping[str, Any]
) -> str:
    """Render an accepted Artifact into a readable, bounded Issue description."""

    payload = artifact.get("payload")
    producer = artifact.get("producer")
    if not isinstance(payload, Mapping) or not isinstance(producer, Mapping):
        raise ContractError("Multica Issue card requires a valid Artifact Envelope")
    if producer.get("runtime") != "multica":
        raise ContractError("Multica Issue card only accepts Multica-produced Artifacts")
    if producer.get("component_id") != bundle.get("profile_id"):
        raise ContractError("Multica Issue card profile does not match its input bundle")
    if artifact.get("workflow_run_id") != bundle.get("workflow_run_id"):
        raise ContractError("Multica Issue card inputs belong to different workflow runs")
    if payload.get("input_bundle_hash") != bundle.get("bundle_hash"):
        raise ContractError("Multica Issue card Artifact does not bind its input bundle")

    audit = _audit_fact(artifact)
    task_id = str(audit.get("task_id", ""))
    issue_id = str(audit.get("issue_id", ""))
    if not task_id or not issue_id or audit.get("result") != "passed":
        raise ContractError("Multica Issue card requires a passed, bound tool-trace audit")

    card = get_agent_work_card(str(bundle.get("profile_id")))
    inputs = bundle.get("inputs") or bundle.get("input_materials") or []
    if isinstance(inputs, Mapping):
        input_lines = [f"- `{key}`: {value}" for key, value in inputs.items()]
    elif isinstance(inputs, list):
        input_lines = [f"- {item}" for item in inputs]
    else:
        input_lines = [f"- {inputs}"] if inputs else []
    if not input_lines:
        input_lines = [f"- 输入 Bundle: `{bundle.get('bundle_hash')}`"]
    reviews = review_items(artifact, card)

    if bundle.get("profile_id") == "A08":
        return "\n".join(_render_a08_cases(payload))

    lines = [
        "## 目标",
        "",
        str(card["goal"]),
        "",
        "## 背景",
        "",
        str(card["background"]),
        "",
        "## 范围",
        "",
        "包含：",
        *[f"- {item}" for item in card["in_scope"]],
        "",
        "不包含：",
        *[f"- {item}" for item in card["out_of_scope"]],
        "",
        "## 输入材料",
        "",
        *input_lines,
        "",
        "## 产出",
        "",
        *[f"- {item}" for item in card["deliverables"]],
        "",
        "## 验收",
        "",
        *[f"- {item}" for item in card["acceptance"]],
        "- 现有业务仓库只读边界和既有通过现象不能被破坏。",
        "",
        "## 需要你做什么",
        "",
        *([f"- {item}" for item in reviews] if reviews else ["- 无需人工审核；当前结果可按既定 Gate 自动流转。"]),
        "",
        "## 产出摘要",
        "",
    ]
    collections = 0
    for field, value in payload.items():
        if not isinstance(value, list):
            continue
        collections += 1
        lines.append(f"### `{field}` ({len(value)})")
        lines.append("")
        for item in value[:20]:
            if isinstance(item, Mapping):
                lines.extend(_render_structured_item(item))
            else:
                lines.append(f"- {_compact_value(item)}")
        if len(value) > 20:
            lines.append(f"- 其余 {len(value) - 20} 项保留在内容寻址 Artifact 中。")
        lines.append("")
    if not collections:
        lines.append("该输出没有列表型结果；完整结构保留在内容寻址 Artifact 中。")
        lines.append("")
    lines.extend(
        [
            "## 追溯信息",
            "",
            f"- Issue: `{issue_id}`",
            f"- Workflow: `{artifact.get('workflow_run_id')}`",
            f"- 输出契约: `{bundle.get('output_contract')}`",
            f"- 最终状态: `{artifact.get('status')}`",
            f"- 接受 Task: `{task_id}`",
            f"- Artifact: `{artifact.get('artifact_hash')}`",
            f"- Input bundle: `{bundle.get('bundle_hash')}`",
            f"- Result binding hash: `{content_hash({'artifact_hash': artifact.get('artifact_hash'), 'issue_id': issue_id})}`",
        ]
    )
    return "\n".join(lines)


def _run_multica(command: list[str], description: str) -> Mapping[str, Any]:
    completed = subprocess.run(
        command,
        input=description,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "Multica issue update failed"
        raise RetryableAgentError(detail)
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ContractError("Multica issue update returned invalid JSON") from error
    if not isinstance(value, Mapping):
        raise ContractError("Multica issue update must return a JSON object")
    return value


def sync_multica_issue_card(
    bundle_path: Path,
    artifact_path: Path,
    issue_id: str,
    *,
    runner: CommandRunner | None = None,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Publish one accepted result and mark only its bound Multica Issue done."""

    security = security or SecurityPolicy()
    bundle = _read_object(bundle_path, "Multica input bundle")
    artifact = _read_object(artifact_path, "accepted Multica Artifact")
    security.assert_no_secret_values(bundle)
    security.assert_no_secret_values(artifact)
    audit = _audit_fact(artifact)
    if audit.get("issue_id") != issue_id:
        raise ContractError("Multica Issue card target does not match the accepted Artifact")
    description = render_multica_issue_result_markdown(bundle, artifact)
    active_runner = runner or _run_multica
    command = [
        "multica",
        "issue",
        "update",
        issue_id,
        "--description-stdin",
        "--status",
        "done",
        "--output",
        "json",
    ]
    response = active_runner(command, description)
    if response.get("id") != issue_id or response.get("status") != "done":
        raise ContractError("Multica Issue card update did not confirm the bound done state")
    return {
        "issue_id": issue_id,
        "status": "done",
        "artifact_id": artifact.get("artifact_id"),
        "artifact_hash": artifact.get("artifact_hash"),
        "task_id": audit.get("task_id"),
        "description_hash": content_hash(description),
    }
