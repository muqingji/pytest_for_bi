"""Deterministic inputs for human Gate decisions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from .contracts import artifact_hash_from_mapping, content_hash
from .errors import ContractError, SecurityPolicyError
from .security import SecurityPolicy
from .storage import ArtifactStore


RETURN_DISPOSITION_TARGETS = {
    "return_to_a02": "A02",
    "return_to_a03": "A03",
    "return_to_a05": "A05",
    "return_to_a06": "A06",
}

# 审批条目分类与通俗表达：面向 QA Owner 的审核表直接展示中文，
# 不要求先看懂内部术语才能判断要确认什么。
CATEGORY_BY_SOURCE = {
    "A02": "待确认需求",
    "A03": "待确认技术方案",
    "A06": "待确认测试范围",
}

_TOPIC_MARKERS = (
    ("multiple_limit_priority", ("多个受限", "多个限制", "同时命中", "提示优先级")),
    ("multiple_metric_names", ("多个按结果集", "全部指标", "展示数量", "指标名称的展示")),
    ("what_whatlist", ("whatlist", "动态关联")),
    ("custom_dimension_copy", ("自定义维度", "最终中英文文案")),
    ("result_filter_copy", ("结果集筛选", "固定写", "端无关文案")),
    ("i18n_copy", ("多语言", "目标语言", "英文译文", "语言回退")),
    ("cross_client_consistency", ("移动端", "web", "拼表入口", "端最终提示")),
    ("error_code_evidence", ("错误码", "模板", "配置并发布")),
    ("test_evidence", ("测试证据", "端到端验证", "可执行测试")),
)

FINDING_TYPE_LABELS = {
    "conflict": "实现与需求/技术方案冲突",
    "omission": "缺少实现证据",
    "partial_implementation": "只实现了一部分",
    "needs_human": "需要人工确认",
    "out_of_scope_change": "存在超出需求范围的变更",
    "design_not_evidenced": "技术方案没有落地证据",
    "implementation_not_evidenced": "没有实现证据",
    "scope_drift": "范围漂移",
    "implementation_evidence_gap": "实现证据不足",
}

# 常见内部术语的确定性通俗化（长词优先，避免部分替换）。
_PLAIN_TERMS = (
    ("METRIC_OBJECT_RELATION_DETAIL_UNSUPPORTED", "「对象关系明细暂不支持」错误码"),
    ("I18NErrorCodeEnum", "国际化错误码枚举"),
    ("MultiRelationMetricDetailUnsupported", "「多关联明细暂不支持」错误码"),
    ("filter.fieldName", "筛选字段名称"),
    ("filterLists", "筛选条件"),
    ("businessObjects", "业务对象数量"),
    ("fieldId", "字段 ID"),
    ("WhatList", "WhatList 动态关联"),
    ("what-list", "WhatList 动态关联"),
    ("What", "What 动态关联"),
    ("zh_CN", "中文"),
    ("en_US", "英文"),
    ("UDF", "自定义函数"),
    ("PRD", "需求文档"),
    ("StatDetailQueryService", "明细查询服务"),
    ("OperateMenuElement", "操作菜单组件"),
    ("BusinessObjectTransConverter", "业务对象转换组件"),
    ("ObjectRelationTransConverter", "对象关系转换组件"),
    ("StatDetailRptDwService", "明细报表服务"),
    ("GrayManager", "灰度开关"),
    ("AggRuleCovertService", "聚合规则转换服务"),
)
_PLAIN_TERM_MAP = dict(_PLAIN_TERMS)
_PLAIN_TERM_PATTERN = re.compile(
    "|".join(re.escape(source) for source, _target in _PLAIN_TERMS)
)


def plain_text(value: Any) -> str:
    """把内部术语替换为通俗中文，方便 QA Owner 直接阅读。"""

    text = str(value or "").strip()
    return _PLAIN_TERM_PATTERN.sub(lambda match: _PLAIN_TERM_MAP[match.group(0)], text)


def _plain_summary(source: str, item: Mapping[str, Any]) -> str:
    if source == "A02":
        message = plain_text(item.get("message") or item.get("summary") or "")
        return f"需求文档里没有写清楚：{message}" if message else "需求文档里存在未明确的规则，需要补充确认。"
    if source == "A03":
        summary = plain_text(item.get("summary") or item.get("message") or "")
        recommendation = plain_text(item.get("recommendation") or "")
        text = f"技术方案里有待确认项：{summary}" if summary else "技术方案里存在待确认项。"
        if recommendation:
            text = f"{text} 建议：{recommendation}"
        return text
    finding_type = str(item.get("type") or "")
    label = FINDING_TYPE_LABELS.get(finding_type, "实现与需求/技术方案存在差异")
    summary = plain_text(item.get("summary") or "")
    return f"{label}：{summary}" if summary else f"{label}，需要确认口径。"


def _confirm_action(source: str, item: Mapping[str, Any]) -> str:
    if source == "A02":
        return "请确认或补充需求口径；确认后 A02 会重新分析并更新需求事实。"
    if source == "A03":
        recommendation = plain_text(item.get("recommendation") or "")
        return f"请确认技术方案的处理方式：{recommendation}" if recommendation else (
            "请确认技术方案如何处理该待确认项；确认后 A03 会更新技术事实。"
        )
    return "请确认是接受当前实现口径、补齐实现证据，还是调整需求/技术方案；确认后会回流 A06 重新对齐。"


def _requirement_ids(item: Mapping[str, Any]) -> list[str]:
    raw = item.get("requirement_ids")
    if not isinstance(raw, list):
        return []
    return [str(value) for value in raw if str(value).strip()]


def _dedupe_topic(issue: Mapping[str, Any]) -> str | None:
    explicit = str(issue.get("dedupe_key", ""))
    if explicit and explicit != str(issue.get("issue_id", "")):
        return explicit
    detail = issue.get("detail", {})
    text = " ".join(
        str(value).lower()
        for value in (
            issue.get("plain_summary", ""),
            detail.get("message", "") if isinstance(detail, Mapping) else "",
            detail.get("summary", "") if isinstance(detail, Mapping) else "",
            detail.get("recommendation", "") if isinstance(detail, Mapping) else "",
        )
    )
    for topic, markers in _TOPIC_MARKERS:
        if any(marker in text for marker in markers):
            return topic
    return None


def _merge_duplicate_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse known cross-agent topics while retaining complete provenance."""

    merged: list[dict[str, Any]] = []
    by_topic: dict[str, dict[str, Any]] = {}
    for issue in issues:
        issue_id = str(issue["issue_id"])
        source = str(issue["source"])
        issue["related_issue_ids"] = [issue_id]
        issue["sources"] = [source]
        topic = _dedupe_topic(issue)
        issue["dedupe_key"] = topic or issue_id
        if not topic or topic not in by_topic:
            merged.append(issue)
            if topic:
                by_topic[topic] = issue
            continue
        primary = by_topic[topic]
        primary["related_issue_ids"].append(issue_id)
        if source not in primary["sources"]:
            primary["sources"].append(source)
        primary["requirement_ids"] = list(
            dict.fromkeys([*primary["requirement_ids"], *issue["requirement_ids"]])
        )
        primary.setdefault("related_details", []).append(
            {"issue_id": issue_id, "source": source, "detail": issue["detail"]}
        )
    return merged


def scope_followup_issues(
    issues: list[dict[str, Any]],
    previous_request: Mapping[str, Any],
    previous_decision: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Keep only returned topics and present their newest A06 explanation."""

    returned_ids = {
        str(item.get("issue_id", ""))
        for item in previous_decision.get("resolutions", [])
        if isinstance(item, Mapping)
        and str(item.get("disposition", "")) in RETURN_DISPOSITION_TARGETS
    }
    previous_by_id = {
        str(item.get("issue_id", "")): item
        for item in previous_request.get("issues", [])
        if isinstance(item, Mapping)
    }
    returned_topics = {
        topic
        for item in previous_decision.get("resolutions", [])
        if isinstance(item, Mapping)
        and str(item.get("issue_id", "")) in returned_ids
        if (topic := str(item.get("topic_key", "")) or _dedupe_topic(previous_by_id.get(str(item.get("issue_id", "")), {})))
    }
    returned_topic_by_id = {
        issue_id: _dedupe_topic(previous_by_id.get(issue_id, {}))
        for issue_id in returned_ids
    }
    matched_topics: set[str] = set()
    followups: list[dict[str, Any]] = []
    for issue in issues:
        topic = _dedupe_topic(issue)
        related_ids = set(issue.get("related_issue_ids", []))
        exact_topic_match = any(
            returned_topic_by_id.get(issue_id) in {None, topic}
            for issue_id in related_ids & returned_ids
        )
        if not (exact_topic_match or (topic and topic in returned_topics)):
            continue
        related = next(
            (
                item for item in issue.get("related_details", [])
                if isinstance(item, Mapping) and item.get("source") == "A06"
            ),
            None,
        )
        if related and isinstance(related.get("detail"), Mapping):
            detail = dict(related["detail"])
            followup = {
                **issue,
                "issue_id": str(related["issue_id"]),
                "issue_code": detail.get("type", "alignment_conflict"),
                "source": "A06",
                "route_to": "A06",
                "severity": detail.get("severity", issue.get("severity", "high")),
                "category": CATEGORY_BY_SOURCE["A06"],
                "plain_summary": _plain_summary("A06", detail),
                "confirm_action": _confirm_action("A06", detail),
                "requirement_ids": _requirement_ids(detail),
                "detail": detail,
            }
        else:
            followup = dict(issue)
        followup["followup_of"] = sorted(returned_ids & related_ids) or sorted(
            issue_id
            for issue_id, returned_topic in returned_topic_by_id.items()
            if topic and returned_topic == topic
        )
        followup["review_reason"] = "上一轮回复为没看明白，A06 已重新解释；仅需复核本项。"
        followups.append(followup)
        if topic:
            matched_topics.add(topic)
    for issue_id in returned_ids:
        previous = previous_by_id.get(issue_id)
        if not previous:
            continue
        topic = _dedupe_topic(previous)
        if topic and topic in matched_topics:
            continue
        followups.append(
            {
                **dict(previous),
                "issue_id": f"A06:FOLLOWUP-{issue_id.replace(':', '-')}",
                "source": "A06",
                "route_to": "A06",
                "category": CATEGORY_BY_SOURCE["A06"],
                "dedupe_key": topic or issue_id,
                "followup_of": [issue_id],
                "review_reason": "上一轮回复为没看明白；仅需复核本项的新解释。",
            }
        )
    return followups


def scope_carry_forward(
    issues: list[dict[str, Any]],
    prior_decisions: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only G01 issues whose scope was never resolved in a prior decision.

    Confirmed scope must not be re-asked when the review request is rebuilt:
    items whose id, dedupe topic or related ids were already decided are dropped
    so the next review round only surfaces genuinely new findings. Returned
    items are re-asked by ``scope_followup_issues`` and are intentionally
    excluded here because they are already part of the decided scope.
    """

    seen_ids: set[str] = set()
    seen_topics: set[str] = set()
    for decision in prior_decisions:
        for resolution in decision.get("resolutions", []):
            if not isinstance(resolution, Mapping):
                continue
            issue_id = str(resolution.get("issue_id", "")).strip()
            if issue_id:
                seen_ids.add(issue_id)
            topic = str(resolution.get("topic_key", "")).strip()
            if topic and topic != issue_id:
                seen_topics.add(topic)
    kept: list[dict[str, Any]] = []
    for issue in issues:
        issue_id = str(issue.get("issue_id", "")).strip()
        topic = _dedupe_topic(issue)
        related = {
            str(value)
            for value in issue.get("related_issue_ids", [])
            if isinstance(value, str) and value.strip()
        }
        if topic and topic in seen_topics:
            continue
        if issue_id and issue_id in seen_ids:
            continue
        if related & seen_ids:
            continue
        kept.append(issue)
    return kept


def scope_gate_issues(
    requirement_analysis: Mapping[str, Any],
    technical_analysis: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for ambiguity in requirement_analysis.get("ambiguities", []):
        issues.append(
            {
                "issue_id": f"A02:{ambiguity.get('id', len(issues) + 1)}",
                "issue_code": ambiguity.get("issue_code", "requirement_ambiguity"),
                "source": "A02",
                "route_to": "A02",
                "severity": ambiguity.get("severity", "high"),
                "category": CATEGORY_BY_SOURCE["A02"],
                "plain_summary": _plain_summary("A02", ambiguity),
                "confirm_action": _confirm_action("A02", ambiguity),
                "requirement_ids": _requirement_ids(ambiguity),
                "detail": dict(ambiguity),
            }
        )
    for item in technical_analysis.get("blocking_items", []):
        issues.append(
            {
                "issue_id": f"A03:{item.get('id', len(issues) + 1)}",
                "issue_code": item.get("issue_code", "testability_blocked"),
                "source": "A03",
                "route_to": "A03",
                "severity": item.get("severity", "high"),
                "category": CATEGORY_BY_SOURCE["A03"],
                "plain_summary": _plain_summary("A03", item),
                "confirm_action": _confirm_action("A03", item),
                "requirement_ids": _requirement_ids(item),
                "detail": dict(item),
            }
        )
    for finding in alignment.get("findings", []):
        issues.append(
            {
                "issue_id": f"A06:{finding.get('id', len(issues) + 1)}",
                "issue_code": finding.get("type", "alignment_conflict"),
                "source": "A06",
                "route_to": "A06",
                "severity": finding.get("severity", "high"),
                "category": CATEGORY_BY_SOURCE["A06"],
                "plain_summary": _plain_summary("A06", finding),
                "confirm_action": _confirm_action("A06", finding),
                "requirement_ids": _requirement_ids(finding),
                "detail": dict(finding),
            }
        )
    return _merge_duplicate_issues(issues)


def _read_artifact(path: Path, expected_id: str, security: SecurityPolicy) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        artifact = json.load(file)
    if not isinstance(artifact, dict) or artifact.get("artifact_id") != expected_id:
        raise ContractError(f"Expected Artifact {expected_id}: {path}")
    security.assert_no_secret_values(artifact)
    if artifact.get("artifact_hash") != artifact_hash_from_mapping(artifact):
        raise ContractError(f"Artifact hash mismatch: {expected_id}")
    return artifact


def prepare_scope_review_request(
    requirement_artifact_path: Path,
    technical_artifact_path: Path,
    alignment_artifact_path: Path,
    output_dir: Path,
    *,
    policy: Mapping[str, Any],
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Build a content-addressed G01 request from accepted A02/A03/A06 Artifacts."""

    security = security or SecurityPolicy()
    if not isinstance(policy, Mapping):
        raise ContractError("G01 review policy must be an object")
    if policy.get("temporary_policy") is True and policy.get(
        "production_release_authority"
    ) is not False:
        raise SecurityPolicyError(
            "Temporary G01 review policy cannot grant production release authority"
        )
    artifacts = [
        _read_artifact(requirement_artifact_path, "a02-requirement-analysis", security),
        _read_artifact(technical_artifact_path, "a03-technical-testability-analysis", security),
        _read_artifact(alignment_artifact_path, "a06-alignment-result", security),
    ]
    identities = {
        (
            str(item.get("workflow_run_id", "")),
            str(item.get("workflow_mode", "")),
            str(item.get("source_snapshot_id", "")),
        )
        for item in artifacts
    }
    if len(identities) != 1 or not all(next(iter(identities))):
        raise ContractError("G01 upstream Artifacts belong to different workflow runs")
    workflow_run_id, workflow_mode, source_snapshot_id = identities.pop()
    security.assert_no_secret_values(policy)
    issues = scope_gate_issues(
        artifacts[0]["payload"], artifacts[1]["payload"], artifacts[2]["payload"]
    )
    request = {
        "schema_version": "scope-review-request/1.1",
        "gate_id": "G01",
        "workflow_run_id": workflow_run_id,
        "workflow_mode": workflow_mode,
        "source_snapshot_id": source_snapshot_id,
        "status": "needs_human" if issues else "completed",
        "decision": "pending" if issues else "not_required",
        "issues": issues,
        "issue_count": len(issues),
        "upstream_artifacts": [
            {"artifact_id": item["artifact_id"], "artifact_hash": item["artifact_hash"]}
            for item in artifacts
        ],
        "review_policy": {
            "schema_version": policy.get("schema_version"),
            "policy_hash": content_hash(policy),
            "approval_mode": policy.get("approval_mode"),
            "policy_scope": policy.get("policy_scope"),
            "temporary_policy": policy.get("temporary_policy", False),
            "production_release_authority": policy.get(
                "production_release_authority", False
            ),
        },
        "decision_contract": "scope-review-decision/1.0",
    }
    security.assert_no_secret_values(request)
    request["request_hash"] = content_hash(request)
    store = ArtifactStore(output_dir)
    store.write_json("g01-review-request.json", request)
    return request


def validate_scope_review_decision(
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Validate a human G01 decision; this function never creates an approval."""

    security = security or SecurityPolicy()
    security.assert_no_secret_values(decision)
    unhashed_request = {key: value for key, value in request.items() if key != "request_hash"}
    if request.get("request_hash") != content_hash(unhashed_request):
        raise ContractError("G01 review request hash is invalid")
    policy_binding = request.get("review_policy")
    if not isinstance(policy_binding, Mapping) or policy_binding.get(
        "policy_hash"
    ) != content_hash(policy):
        raise ContractError("G01 review policy does not match the bound request policy")
    for field in ("gate_id", "workflow_run_id", "source_snapshot_id", "request_hash"):
        if decision.get(field) != request.get(field):
            raise ContractError(f"G01 decision {field} does not match its request")
    if decision.get("schema_version") != "scope-review-decision/1.0":
        raise ContractError("G01 decision schema_version is invalid")
    actor = decision.get("actor")
    if not isinstance(actor, Mapping) or actor.get("type") != "human":
        raise SecurityPolicyError("G01 decision must be made by a human actor")
    if not str(actor.get("id", "")):
        raise ContractError("G01 decision actor.id is required")
    if actor.get("role") not in set(policy.get("allowed_roles", [])):
        raise SecurityPolicyError("G01 decision actor role is not authorized")
    try:
        decided_at = datetime.fromisoformat(str(decision.get("decided_at", "")))
    except ValueError as error:
        raise ContractError("G01 decision decided_at is invalid") from error
    if decided_at.tzinfo is None:
        raise ContractError("G01 decision decided_at must include a timezone")
    decision_value = decision.get("decision")
    if decision_value not in {"approved", "request_changes", "rejected"}:
        raise ContractError("G01 decision value is invalid")
    resolutions = decision.get("resolutions")
    if not isinstance(resolutions, list):
        raise ContractError("G01 decision resolutions must be a list")
    resolution_ids = [str(item.get("issue_id", "")) for item in resolutions if isinstance(item, Mapping)]
    if len(resolution_ids) != len(resolutions) or len(resolution_ids) != len(set(resolution_ids)):
        raise ContractError("G01 decision contains invalid or duplicate resolution IDs")
    request_issue_ids = {str(item.get("issue_id", "")) for item in request.get("issues", [])}
    if not set(resolution_ids) <= request_issue_ids:
        raise ContractError("G01 decision references an unknown issue")
    allowed_dispositions = set(policy.get("allowed_dispositions", []))
    allowed_roles = set(policy.get("allowed_roles", []))
    request_issues = {
        str(item.get("issue_id", "")): item for item in request.get("issues", [])
    }
    required_roles_by_source = policy.get("required_roles_by_source", {})
    for index, resolution in enumerate(resolutions):
        if resolution.get("disposition") not in allowed_dispositions:
            raise ContractError(f"G01 resolution {index} has an invalid disposition")
        if not str(resolution.get("rationale", "")).strip() or not str(
            resolution.get("owner", "")
        ).strip():
            raise ContractError(f"G01 resolution {index} requires rationale and owner")
        approvals = resolution.get("approvals", [])
        if not isinstance(approvals, list):
            raise ContractError(f"G01 resolution {index} approvals must be a list")
        approval_roles: set[str] = set()
        approval_identities: set[tuple[str, str]] = set()
        for approval in approvals:
            if not isinstance(approval, Mapping) or approval.get("type") != "human":
                raise SecurityPolicyError(f"G01 resolution {index} has a non-human approval")
            identity = (str(approval.get("id", "")), str(approval.get("role", "")))
            if not all(identity) or identity in approval_identities:
                raise ContractError(f"G01 resolution {index} has an invalid approval identity")
            if identity[1] not in allowed_roles:
                raise SecurityPolicyError(f"G01 resolution {index} has an unauthorized role")
            approval_identities.add(identity)
            approval_roles.add(identity[1])
        if decision_value == "approved":
            issue_source = str(request_issues[resolution["issue_id"]].get("source", ""))
            required_roles = set(required_roles_by_source.get(issue_source, []))
            if not required_roles <= approval_roles:
                missing_roles = ", ".join(sorted(required_roles - approval_roles))
                raise SecurityPolicyError(
                    f"G01 resolution {index} is missing required role approvals: {missing_roles}"
                )
    if decision_value == "approved":
        for field in policy.get("required_approval_fields", []):
            value = decision.get(field)
            if value is None or value == "" or value == [] or value == {}:
                raise ContractError(f"G01 approval requires decision field: {field}")
        if set(resolution_ids) != request_issue_ids:
            raise ContractError("G01 approval must resolve every review issue")
        if any(item.get("disposition") not in {"confirmed", "resolved_upstream"} for item in resolutions):
            raise ContractError("G01 approval contains an unresolved disposition")
    else:
        if not str(decision.get("reason", "")).strip():
            raise ContractError("Non-approved G01 decisions require a reason")
        if decision_value == "request_changes" and not any(
            item.get("disposition") in RETURN_DISPOSITION_TARGETS for item in resolutions
        ):
            raise ContractError("G01 request_changes requires at least one upstream return route")

    normalized = dict(decision)
    normalized["decision_hash"] = content_hash(decision)
    return normalized


def validate_recorded_scope_review_decision(
    request: Mapping[str, Any],
    recorded_decision: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    raw_decision = {
        key: value for key, value in recorded_decision.items() if key != "decision_hash"
    }
    if recorded_decision.get("decision_hash") != content_hash(raw_decision):
        raise ContractError("Recorded G01 decision hash is invalid")
    return validate_scope_review_decision(request, raw_decision, policy)


def scope_review_decision_template(request: Mapping[str, Any]) -> dict[str, Any]:
    """Create an intentionally invalid blank form; it cannot be mistaken for approval."""

    return {
        "schema_version": "scope-review-decision/1.0",
        "gate_id": "G01",
        "workflow_run_id": request.get("workflow_run_id"),
        "source_snapshot_id": request.get("source_snapshot_id"),
        "request_hash": request.get("request_hash"),
        "decision": "",
        "decided_at": "",
        "actor": {"type": "human", "id": "", "role": ""},
        "reason": "",
        "resolutions": [
            {
                "issue_id": item.get("issue_id"),
                "disposition": "",
                "rationale": "",
                "owner": "",
                "approvals": [],
            }
            for item in request.get("issues", [])
        ],
    }


def build_scope_review_outcome(
    request: Mapping[str, Any],
    recorded_decision: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    security: SecurityPolicy | None = None,
) -> dict[str, Any]:
    """Compile a validated G01 decision into an explicit orchestration action."""

    security = security or SecurityPolicy()
    decision = validate_recorded_scope_review_decision(request, recorded_decision, policy)
    decision_value = str(decision["decision"])
    issues = {
        str(item.get("issue_id", "")): item
        for item in request.get("issues", [])
        if isinstance(item, Mapping)
    }
    return_routes = []
    for resolution in decision.get("resolutions", []):
        target = RETURN_DISPOSITION_TARGETS.get(str(resolution.get("disposition", "")))
        if not target:
            continue
        issue = issues[str(resolution["issue_id"])]
        return_routes.append(
            {
                "issue_id": resolution["issue_id"],
                "issue_code": issue.get("issue_code"),
                "source": issue.get("source"),
                "target_node": target,
                "owner": resolution["owner"],
                "rationale": resolution["rationale"],
            }
        )

    if decision_value == "approved":
        action = "continue"
        status = "completed"
        next_node = "N24"
        invalidation = {"roots": [], "include_all_descendants": False}
        resume_at = None
    elif decision_value == "request_changes":
        action = "return_upstream"
        status = "blocked_input"
        next_node = None
        invalidation = {"roots": ["A06"], "include_all_descendants": True}
        resume_at = "A06"
    else:
        action = "terminate"
        status = "cancelled"
        next_node = None
        return_routes = []
        invalidation = {"roots": ["A06"], "include_all_descendants": True}
        resume_at = None

    outcome = {
        "schema_version": "scope-review-outcome/1.0",
        "gate_id": "G01",
        "workflow_run_id": request["workflow_run_id"],
        "source_snapshot_id": request["source_snapshot_id"],
        "request_hash": request["request_hash"],
        "decision_hash": decision["decision_hash"],
        "decision": decision_value,
        "review_policy": dict(request["review_policy"]),
        "status": status,
        "action": action,
        "next_node": next_node,
        "return_routes": return_routes,
        "resume_at": resume_at,
        "invalidation": invalidation,
    }
    security.assert_no_secret_values(outcome)
    outcome["outcome_hash"] = content_hash(outcome)
    return outcome


def record_scope_review_decision(
    request_path: Path,
    decision_path: Path,
    policy_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    with request_path.open(encoding="utf-8") as file:
        request = json.load(file)
    with decision_path.open(encoding="utf-8") as file:
        decision = json.load(file)
    with policy_path.open(encoding="utf-8") as file:
        policy = json.load(file)
    normalized = validate_scope_review_decision(request, decision, policy)
    store = ArtifactStore(output_dir)
    store.write_json("g01-review-decision.json", normalized)
    store.write_json(
        "g01-review-outcome.json",
        build_scope_review_outcome(request, normalized, policy),
    )
    return normalized
