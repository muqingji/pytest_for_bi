"""Human Bug gate for TAPD registration and rejection-driven retest planning."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Any

from .contracts import ArtifactEnvelope, ArtifactStatus, EvidenceRef, Producer, content_hash
from .errors import ContractError, InputError
from .storage import ArtifactStore


REQUIRED_COLUMNS = (
    "case_id",
    "business_scenario",
    "expected_behavior",
    "actual_problem",
    "bug_explanation",
    "test_data",
    "id",
)


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"Required {label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ContractError(f"Required {label} must be a JSON object")
    return value


def _md(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        value = "; ".join(
            f"{key}={item}" for key, item in value.items() if str(item).strip()
        )
    return str(value).replace("|", "\\|").replace("\n", "<br>") or "-"


def _identity(value: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(value.get("workflow_run_id", "")),
        str(value.get("workflow_mode", "")),
        str(value.get("source_snapshot_id", "")),
    )


def _normalize_candidates(value: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    if value.get("schema_version") != "tapd-bug-review-input/1.0":
        raise ContractError("Bug review input must use tapd-bug-review-input/1.0")
    story_id = str(value.get("tapd_story_id", "")).strip()
    if not story_id:
        raise ContractError("Bug review input requires tapd_story_id")
    candidates = value.get("bug_candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ContractError("Bug review input requires at least one bug candidate")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(candidates, start=1):
        if not isinstance(item, dict):
            raise ContractError(f"Bug candidate {index} must be an object")
        case_id = str(item.get("case_id", "")).strip()
        if not case_id:
            raise ContractError(f"Bug candidate {index} has no case_id")
        if case_id in seen:
            raise ContractError(f"Duplicate bug candidate case_id: {case_id}")
        seen.add(case_id)
        for field in (
            "business_scenario",
            "expected_behavior",
            "actual_problem",
            "bug_explanation",
        ):
            if not str(item.get(field, "")).strip():
                raise ContractError(f"Bug candidate {case_id} has no {field}")
        test_data = item.get("test_data", [])
        if not isinstance(test_data, list) or not test_data:
            raise ContractError(f"Bug candidate {case_id} has no real test data")
        normalized_data = []
        for data in test_data:
            if not isinstance(data, dict) or not str(data.get("real_name", "")).strip():
                raise ContractError(f"Bug candidate {case_id} test data requires real_name")
            normalized_data.append(
                {
                    "real_name": str(data["real_name"]),
                    "id": str(data.get("id", "")),
                    "kind": str(data.get("kind", "business_object")),
                }
            )
        bug_id = str(item.get("id", "")).strip() or f"BUG-{case_id}"
        normalized.append(
            {
                "id": bug_id,
                "case_id": case_id,
                "business_scenario": str(item.get("business_scenario", "")),
                "expected_behavior": str(item.get("expected_behavior", "")),
                "actual_problem": str(item.get("actual_problem", "")),
                "bug_explanation": str(item.get("bug_explanation", "")),
                "test_data": normalized_data,
                "fingerprint": str(item.get("fingerprint", "")),
                "evidence": item.get("evidence", []) if isinstance(item.get("evidence"), list) else [],
                "trace_ids": item.get("trace_ids", item.get("trace_id", [])),
                "reproduction_steps": item.get("reproduction_steps", []),
                "reproduction": item.get("reproduction", "可复现"),
                "accounts": item.get("accounts", item.get("test_accounts", "未记录")),
                "bug_introduction": item.get("bug_introduction", "未评估"),
                "version": item.get("version", item.get("version_report", "未记录")),
                "platform": item.get("platform", "未记录"),
                "test_phase": item.get("test_phase", "业务测试"),
                "iteration_id": item.get("iteration_id", "未记录"),
                "tapd_bug_id": item.get("tapd_bug_id", "待创建"),
                "tapd_bug_url": item.get("tapd_bug_url", "待创建"),
            }
        )
    return story_id, str(value.get("tapd_story_url", "")), normalized


def render_bug_review_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# TAPD Bug 准出审批",
        "",
        f"- 需求 ID：`{payload['tapd_story_id']}`",
        f"- 工作流：`{payload['workflow_run_id']}`",
        f"- 评审轮次：`{payload['review_round']}`",
        "",
        "> 审批通过后才会进入 Bug Adapter；驳回时请在评论区指定 Bug/Case ID 和原因。",
        "",
        "| Case | 业务场景 | 期望行为 | 实际问题 | Bug 解释 | 测试数据（真实的现实名称） | ID |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in payload["bug_candidates"]:
        lines.append(
            "| {case} | {scenario} | {expected} | {actual} | {explanation} | {data} | {bug_id} |".format(
                case=_md(item["case_id"]),
                scenario=_md(item["business_scenario"]),
                expected=_md(item["expected_behavior"]),
                actual=_md(item["actual_problem"]),
                explanation=_md(item["bug_explanation"]),
                data=_md(
                    [
                        f"{entry['real_name']}(ID:{entry['id'] or '-'})"
                        for entry in item["test_data"]
                    ]
                ),
                bug_id=_md(item["id"]),
            )
        )
        lines.extend([
            "",
            f"### {item['case_id']} 评审明细",
            "",
            f"- 实际 TraceID：{_md(item.get('trace_ids'))}",
            f"- 测试账号（租户/账号/密码）：{_md(item.get('accounts'))}",
            f"- 复现步骤：{_md(item.get('reproduction_steps'))}",
            f"- 重现规律：{_md(item.get('reproduction'))}",
            f"- Bug 引入时机：{_md(item.get('bug_introduction'))}",
            f"- 发现版本：{_md(item.get('version'))}",
            f"- 软件平台：{_md(item.get('platform'))}",
            f"- 测试阶段：{_md(item.get('test_phase'))}",
            f"- 需求迭代：{_md(item.get('iteration_id'))}",
            f"- 需求关联：需求 `{payload['tapd_story_id']}`（创建后必须回读确认）",
            f"- TAPD Bug：{_md(item.get('tapd_bug_id'))}；{_md(item.get('tapd_bug_url'))}",
        ])
    lines.extend(
        [
            "",
            "## 审批决定",
            "",
            "```yaml",
            "schema_version: bug-review-decision/1.0",
            f"review_artifact_hash: {payload['review_hash']}",
            "decision: approved | rejected",
            "approver: <human>",
            "bug_ids: []",
            "comments:",
            "  - bug_id: <id>",
            "    case_id: <case id>",
            "    comment: <rejection reason>",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def prepare_bug_review(input_path: Path, output_dir: Path) -> dict[str, Any]:
    value = _load(input_path, "Bug review input")
    run_id, workflow_mode, snapshot_id = _identity(value)
    if not run_id or not snapshot_id:
        raise ContractError("Bug review input requires workflow identity")
    story_id, story_url, candidates = _normalize_candidates(value)
    payload = {
        "schema_version": "tapd-bug-review-request/1.0",
        "workflow_run_id": run_id,
        "source_snapshot_id": snapshot_id,
        "tapd_story_id": story_id,
        "tapd_story_url": story_url,
        "review_round": int(value.get("review_round", 1)),
        "bug_candidates": candidates,
        "candidate_hash": content_hash(candidates),
        "review_hash": content_hash(
            {"tapd_story_id": story_id, "round": int(value.get("review_round", 1)), "candidates": candidates}
        ),
        "decision": "waiting_human",
        "tapd_registration_disposition": "blocked_until_human_approval",
    }
    artifact = ArtifactEnvelope(
        workflow_run_id=run_id,
        workflow_mode=workflow_mode or "new_requirement",
        artifact_id="tapd-bug-review-request",
        source_snapshot_id=snapshot_id,
        producer=Producer("N20", profile_version="tapd-review-gate/1.0.0"),
        payload=payload,
        status=ArtifactStatus.NEEDS_HUMAN,
        reason_code="bug_registration_approval_required",
        blocking_questions=(
            {"question": "是否将这些候选登记为 TAPD Bug？", "owner": "QA approver"},
        ),
    )
    store = ArtifactStore(output_dir)
    store.write_artifact(artifact)
    store.write_text("tapd-bug-review-card.md", render_bug_review_markdown(payload))
    return artifact.to_dict()


def _validate_review_binding(decision: dict[str, Any], review: dict[str, Any]) -> None:
    expected = review.get("payload", {}).get("review_hash")
    if decision.get("schema_version") != "bug-review-decision/1.0":
        raise ContractError("Decision must use bug-review-decision/1.0")
    if decision.get("review_artifact_hash") != review.get("artifact_hash"):
        raise ContractError("Decision is not bound to this Bug review Artifact")
    if expected and decision.get("review_hash") not in {None, expected}:
        raise ContractError("Decision review_hash does not match the Bug review Artifact")


def apply_bug_review_decision(
    decision_path: Path,
    review_artifact_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    decision = _load(decision_path, "Bug review decision")
    review = _load(review_artifact_path, "Bug review Artifact")
    if review.get("artifact_id") != "tapd-bug-review-request":
        raise ContractError("Decision requires a tapd-bug-review-request Artifact")
    _validate_review_binding(decision, review)
    payload = review["payload"]
    result = str(decision.get("decision", "")).strip()
    approver = str(decision.get("approver", "")).strip()
    if not approver or approver == "QA Agent":
        raise ContractError("Bug review requires a named human approver")
    requested_ids = {str(item) for item in decision.get("bug_ids", []) if str(item)}
    all_ids = {str(item["id"]) for item in payload["bug_candidates"]}
    if result == "approved":
        selected = requested_ids or all_ids
        unknown = selected - all_ids
        if unknown:
            raise ContractError(f"Decision references unknown Bug IDs: {sorted(unknown)}")
        outcome = "approved_for_bug_adapter"
        status = ArtifactStatus.COMPLETED_WITH_GAPS
        reason = "tapd_bug_adapter_not_implemented"
        next_node = "TAPD_BUG_ADAPTER"
        notes = ["审批已通过；正式 TAPD 写入 Adapter 将在下一步接入。"]
    elif result == "rejected":
        comments = decision.get("comments", [])
        if not isinstance(comments, list) or not comments:
            raise ContractError("Rejected Bug review requires comments")
        rejected_ids = set()
        for comment in comments:
            if not isinstance(comment, dict) or not str(comment.get("comment", "")).strip():
                raise ContractError("Each rejection comment requires text")
            bug_id = str(comment.get("bug_id", "")).strip()
            case_id = str(comment.get("case_id", "")).strip()
            if not bug_id and not case_id:
                raise ContractError("Rejection comment must target bug_id or case_id")
            matches = [
                item for item in payload["bug_candidates"]
                if (bug_id and item["id"] == bug_id) or (case_id and item["case_id"] == case_id)
            ]
            if not matches:
                raise ContractError(f"Rejection target does not exist: {bug_id or case_id}")
            rejected_ids.update(item["id"] for item in matches)
        selected = rejected_ids
        outcome = "retest_required"
        status = ArtifactStatus.COMPLETED_WITH_GAPS
        reason = "rejected_bug_candidates_require_retest"
        next_node = "N07"
        notes = [
            "驳回候选必须先复核数据构造与 Case 定义，再重新执行并生成新评审轮次。",
            "本节点不直接判定“不是 Bug”；复核/重测证据进入下一轮审批。",
        ]
    else:
        raise ContractError("Bug review decision must be approved or rejected")

    affected = [item for item in payload["bug_candidates"] if item["id"] in selected]
    result_payload = {
        "schema_version": "tapd-bug-review-result/1.0",
        "workflow_run_id": payload["workflow_run_id"],
        "source_snapshot_id": payload["source_snapshot_id"],
        "tapd_story_id": payload["tapd_story_id"],
        "review_round": payload["review_round"],
        "decision": result,
        "outcome": outcome,
        "approver": approver,
        "affected_bug_ids": sorted(selected),
        "affected_cases": sorted({item["case_id"] for item in affected}),
        "comments": decision.get("comments", []),
        "next_node": next_node,
        "tapd_registration_disposition": (
            "pending_external_bug_adapter" if result == "approved" else "not_registered"
        ),
        "notes": notes,
        "decision_hash": content_hash(decision),
    }
    artifact = ArtifactEnvelope(
        workflow_run_id=payload["workflow_run_id"],
        workflow_mode=review.get("workflow_mode", "new_requirement"),
        artifact_id="tapd-bug-review-result",
        source_snapshot_id=payload["source_snapshot_id"],
        producer=Producer("N20", profile_version="tapd-review-gate/1.0.0"),
        payload=result_payload,
        status=status,
        reason_code=reason,
        evidence_refs=(
            EvidenceRef("artifact", "tapd-bug-review-request", review_artifact_path.name, review.get("artifact_hash")),
        ),
    )
    store = ArtifactStore(output_dir)
    store.write_artifact(artifact)
    if result == "rejected":
        retest_payload = {
            "schema_version": "tapd-bug-retest-plan/1.0",
            "workflow_run_id": payload["workflow_run_id"],
            "source_snapshot_id": payload["source_snapshot_id"],
            "tapd_story_id": payload["tapd_story_id"],
            "review_round": payload["review_round"] + 1,
            "case_ids": sorted({item["case_id"] for item in affected}),
            "required_checks": [
                "verify_test_data_recipe",
                "verify_created_data_visible",
                "verify_case_request_matches_oracle",
                "verify_expected_result_is_frozen",
                "rerun_selected_cases",
            ],
            "next_review": "prepare_bug_review",
        }
        retest = ArtifactEnvelope(
            workflow_run_id=payload["workflow_run_id"],
            workflow_mode=review.get("workflow_mode", "new_requirement"),
            artifact_id="tapd-bug-retest-plan",
            source_snapshot_id=payload["source_snapshot_id"],
            producer=Producer("N20", profile_version="tapd-review-gate/1.0.0"),
            payload=retest_payload,
            status=ArtifactStatus.COMPLETED,
            reason_code="rejected_bug_retest_required",
        )
        store.write_artifact(retest)
    return artifact.to_dict()
