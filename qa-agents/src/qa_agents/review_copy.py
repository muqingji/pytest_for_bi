"""Deterministic Chinese copy for G02 review items shown on Multica cards."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ERROR_CODE_RE = re.compile(r"s\d{6,}")

LAYER_ZH = {
    "backend": "服务端",
    "contract": "契约",
    "e2e": "端到端",
    "frontend": "前端",
    "scenario": "场景",
    "non_functional": "非功能",
}

RULE_THEME_ZH = {
    "RULE-CUSTOM-DIMENSION": "自定义维度不支持查看明细",
    "RULE-SINGLE-METRIC": "结果集指标筛选不支持查看明细",
    "RULE-MULTI-RELATION": "多关联关系不支持查看明细",
    "RULE-DYNAMIC-RELATION": "动态关联关系不支持查看明细",
    "RULE-MULTIPLE-REASONS": "多原因只返回一条提示",
    "RULE-PERMISSION-PRIORITY": "权限错误优先于明细提示",
    "RULE-HISTORICAL-COMPATIBILITY": "历史配置原地生效",
    "RULE-ENTRY-CONSISTENCY": "各入口明细提示一致",
}

RULE_TITLE_ZH = {
    "RULE-CUSTOM-DIMENSION": "自定义维度拒绝明细",
    "RULE-SINGLE-METRIC": "结果集筛选拒绝明细",
    "RULE-MULTI-RELATION": "多关联关系拒绝明细",
    "RULE-DYNAMIC-RELATION": "动态关联拒绝明细",
    "RULE-MULTIPLE-REASONS": "多原因只回一条",
    "RULE-PERMISSION-PRIORITY": "权限错误优先",
    "RULE-HISTORICAL-COMPATIBILITY": "历史配置原地生效",
    "RULE-ENTRY-CONSISTENCY": "入口提示一致",
}

ERROR_THEME_ZH = {
    "s307011534": "自定义维度不支持查看明细",
    "s307011535": "结果集指标筛选不支持查看明细",
    "s307011536": "多关联关系不支持查看明细",
    "s307011537": "动态关联关系不支持查看明细",
}

ERROR_TITLE_ZH = {
    "s307011534": "自定义维度拒绝明细",
    "s307011535": "结果集筛选拒绝明细",
    "s307011536": "多关联关系拒绝明细",
    "s307011537": "动态关联拒绝明细",
}

DEDICATED_CODES = ("s307011534", "s307011535", "s307011536", "s307011537")

TITLE_HINTS = (
    ("permission", "权限错误优先于明细提示", "权限错误优先"),
    ("historical", "历史配置原地生效", "历史配置原地生效"),
    ("concatenat", "多原因只返回一条提示", "多原因只回一条"),
    ("multiple matched", "多原因只返回一条提示", "多原因只回一条"),
    ("passthrough", "错误码透传并绑定中英文模板", "契约错误码双语透传"),
    ("locale template", "四个专用场景的中英文模板", "四场景中英文模板"),
    ("joined-table", "Web 统计图与拼表明细提示一致", "Web与拼表一致"),
    ("joined table", "Web 统计图与拼表明细提示一致", "Web与拼表一致"),
    ("mobile", "移动端与 Web 明细提示一致", "移动端与Web一致"),
    ("custom dimension", "自定义维度不支持查看明细", "自定义维度拒绝明细"),
    ("result-set", "结果集指标筛选不支持查看明细", "结果集筛选拒绝明细"),
    ("result set", "结果集指标筛选不支持查看明细", "结果集筛选拒绝明细"),
    ("multi-relation", "多关联关系不支持查看明细", "多关联关系拒绝明细"),
    ("dynamic relation", "动态关联关系不支持查看明细", "动态关联拒绝明细"),
)


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text or ""))


def humanize_review_item(item: Mapping[str, Any]) -> dict[str, str]:
    """Return Chinese human_title / plain_summary for a G02 review item.

    Already-Chinese author fields are kept. English IR is rewritten from layer,
    rule ids, error codes and a small title lexicon so the details page never
    shows a raw English scenario as the thing to approve.
    """

    existing_title = str(item.get("human_title") or "").strip()
    existing_summary = str(item.get("plain_summary") or "").strip()
    title = str(item.get("title") or "").strip()
    scenario = str(item.get("scenario") or "").strip()
    composed_title, composed_summary = _compose_zh(item)
    human_title = (
        existing_title
        if has_cjk(existing_title)
        else title if has_cjk(title) else composed_title
    )
    plain_summary = (
        existing_summary
        if has_cjk(existing_summary)
        else scenario if has_cjk(scenario) else composed_summary
    )
    if has_cjk(scenario) and "条预期" not in scenario:
        expected = item.get("expected")
        count = len(expected) if isinstance(expected, list) and expected else 0
        if count:
            plain_summary = f"{scenario.rstrip('。')}，共 {count} 条预期。"
    return {"human_title": human_title, "plain_summary": plain_summary}


def _compose_zh(item: Mapping[str, Any]) -> tuple[str, str]:
    layer = str(item.get("layer") or "").strip()
    layer_zh = LAYER_ZH.get(layer, "")
    theme, short_title = _theme(item)
    if layer == "contract" and short_title in {
        "自定义维度拒绝明细",
        "结果集筛选拒绝明细",
        "多关联关系拒绝明细",
        "动态关联拒绝明细",
        "查看明细用例",
    }:
        theme, short_title = "错误码透传并绑定中英文模板", "契约错误码双语透传"
    if layer == "e2e" and short_title in {
        "自定义维度拒绝明细",
        "结果集筛选拒绝明细",
        "多关联关系拒绝明细",
        "动态关联拒绝明细",
        "查看明细用例",
        "入口提示一致",
        "历史配置原地生效",
    }:
        theme, short_title = _e2e_theme(item)
    paths = _path_labels(item)
    codes = [code for code in _error_codes(item) if code in DEDICATED_CODES]
    expected = item.get("expected")
    count = len(expected) if isinstance(expected, list) else 0
    parts = [f"{layer_zh or '用例'}校验「{theme}」"]
    if paths:
        parts.append("覆盖" + "、".join(paths))
    if codes:
        parts.append("错误码 " + "、".join(codes))
    if count:
        parts.append(f"共 {count} 条预期")
    summary = "，".join(parts) + "。"
    return short_title, summary


def _theme(item: Mapping[str, Any]) -> tuple[str, str]:
    rules = [
        str(ref)
        for ref in item.get("source_refs", [])
        if isinstance(ref, str) and str(ref).startswith("RULE-")
    ]
    if "RULE-PERMISSION-PRIORITY" in rules:
        return RULE_THEME_ZH["RULE-PERMISSION-PRIORITY"], RULE_TITLE_ZH["RULE-PERMISSION-PRIORITY"]
    if "RULE-MULTIPLE-REASONS" in rules:
        return RULE_THEME_ZH["RULE-MULTIPLE-REASONS"], RULE_TITLE_ZH["RULE-MULTIPLE-REASONS"]
    primary = [rule for rule in rules if not rule.startswith("RULE-I18N-")]
    for rule in primary:
        if rule in RULE_THEME_ZH:
            return RULE_THEME_ZH[rule], RULE_TITLE_ZH[rule]
    codes = _error_codes(item)
    for code in DEDICATED_CODES:
        if code in codes:
            return ERROR_THEME_ZH[code], ERROR_TITLE_ZH[code]
    blob = _blob(item).lower()
    for needle, theme, title in TITLE_HINTS:
        if needle in blob:
            return theme, title
    return "查看明细用例", "查看明细用例"


def _e2e_theme(item: Mapping[str, Any]) -> tuple[str, str]:
    blob = _blob(item).lower()
    if "mobile" in blob:
        return "移动端与 Web 明细提示一致", "移动端与Web一致"
    if "joined" in blob or "RULE-ENTRY-CONSISTENCY" in [
        str(ref) for ref in item.get("source_refs", []) if isinstance(ref, str)
    ]:
        return "Web 统计图与拼表明细提示一致", "Web与拼表一致"
    return "四个专用场景的中英文模板", "四场景中英文模板"


def _path_labels(item: Mapping[str, Any]) -> list[str]:
    blob = _blob(item).lower()
    has_data_range = "data_range" in blob or "data range" in blob
    has_drill = "drill_field" in blob or "drill field" in blob
    if "three-path" in blob or (has_data_range and has_drill):
        return ["维度", "数据范围", "下钻"]
    labels: list[str] = []
    if has_data_range:
        labels.append("数据范围")
    if has_drill:
        labels.append("下钻")
    return labels


def _error_codes(item: Mapping[str, Any]) -> list[str]:
    seen: set[str] = set()
    codes: list[str] = []
    for match in ERROR_CODE_RE.findall(_blob(item)):
        if match not in seen:
            seen.add(match)
            codes.append(match)
    return codes


def _blob(item: Mapping[str, Any]) -> str:
    parts = [
        str(item.get("title") or ""),
        str(item.get("scenario") or ""),
    ]
    for field in ("steps", "preconditions"):
        value = item.get(field)
        if isinstance(value, list):
            parts.extend(str(entry) for entry in value if isinstance(entry, str))
    expected = item.get("expected")
    if isinstance(expected, list):
        for entry in expected:
            if isinstance(entry, Mapping):
                parts.append(str(entry.get("description") or ""))
                parts.append(str(entry.get("expected_value") or ""))
    refs = item.get("source_refs")
    if isinstance(refs, list):
        parts.extend(str(ref) for ref in refs if isinstance(ref, str))
    return "\n".join(parts)


def _expected_is_human_review(item: Mapping[str, Any]) -> bool:
    oracle = item.get("oracle") if isinstance(item.get("oracle"), Mapping) else item
    return (
        str(oracle.get("type") or item.get("oracle_type") or "") == "human_review"
        or str(oracle.get("matcher") or item.get("matcher") or "") == "manual_confirmation"
    )


def _human_review_expected(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected = case.get("expected")
    if not isinstance(expected, list):
        return []
    return [item for item in expected if isinstance(item, Mapping) and _expected_is_human_review(item)]


def build_g02_decision_items(
    review_items: list[Mapping[str, Any]] | None = None,
    *,
    skipped_scenarios: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Approval items for G02: only case-design uncertainties, not every parent case."""

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in seen:
            return
        seen.add(item_id)
        items.append(item)

    for case in review_items or []:
        if not isinstance(case, Mapping):
            continue
        humans = _human_review_expected(case)
        if not humans:
            continue
        add(_decision_from_human_review(case, humans))
    for skipped in skipped_scenarios or []:
        if not isinstance(skipped, Mapping):
            continue
        add(_decision_from_skipped(skipped))
    return items


def g02_decision_items_from_request(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    decisions = request.get("decision_items")
    if isinstance(decisions, list):
        return [dict(item) for item in decisions if isinstance(item, Mapping)]
    review_items = [
        item for item in request.get("review_items") or [] if isinstance(item, Mapping)
    ]
    skipped = [
        item for item in request.get("skipped_scenarios") or [] if isinstance(item, Mapping)
    ]
    return build_g02_decision_items(review_items, skipped_scenarios=skipped)


def g02_approval_items(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Never-empty G02 approval list: uncertainties, or one delivery confirmation."""

    items = g02_decision_items_from_request(request)
    if items:
        return items
    summary = request.get("review_summary")
    count = 0
    if isinstance(summary, Mapping):
        raw = summary.get("parent_case_count")
        if isinstance(raw, int):
            count = raw
    if not count:
        review_items = request.get("review_items")
        if isinstance(review_items, list):
            count = len(review_items)
    return [g02_delivery_confirmation(count)]


def g02_delivery_confirmation(parent_case_count: int) -> dict[str, Any]:
    count = parent_case_count if parent_case_count > 0 else 0
    count_text = f"{count} 条" if count else "这批"
    return {
        "id": "g02-delivery-confirmation",
        "category": "用例设计待确认",
        "human_title": "没有未冻结的产品口径",
        "product_scene": (
            "查看明细在自定义维度、结果集筛选、多关联、动态关联下给出专用提示；"
            "多原因只回一条；没权限仍走原权限失败；Web / 拼表 / 移动端提示一致。"
        ),
        "plain_summary": (
            f"{count_text}父用例的错误码、文案和覆盖已经按冻结规则写完，"
            "没有需要你补口径的产品场景。"
        ),
        "confirm_action": (
            "没有缺场景或口径问题则放行进入编译；"
            "若有缺项请在评论写明后置 blocked。"
        ),
        "case_id": "",
        "requirement_ids": [],
        "source_refs": [],
    }


def _decision_from_human_review(
    case: Mapping[str, Any], humans: list[Mapping[str, Any]]
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or case.get("id") or "").strip()
    refs = [
        str(ref)
        for ref in case.get("source_refs", [])
        if isinstance(ref, str)
    ]
    expected_ids = [str(item.get("id") or "").strip() for item in humans if item.get("id")]
    blob = _blob(case).lower() + " " + " ".join(
        str(item.get("description") or "").lower() for item in humans
    )
    if "RULE-PERMISSION-PRIORITY" in refs or "permission" in blob:
        return {
            "id": f"{case_id}:human_review" if case_id else "permission-baseline",
            "category": "用例设计待确认",
            "human_title": "没权限时不要改提示",
            "product_scene": (
                "操作者没有查看明细权限，或看不到某些指标时，点「查看明细」"
                "应该继续走原来的权限失败，不能改成「暂不支持查看明细」，"
                "也不能把不该看见的指标名带出来。"
            ),
            "plain_summary": (
                "权限失败具体用哪条错误码、会不会新泄露指标名，需求里没有写死。"
                f"所以 {case_id or '该用例'} 写不了自动断言，"
                f"{'、'.join(f'`{item}`' for item in expected_ids) or '相关预期'} "
                "只能对照改前同一账号、同一张图。"
                "能写死的只有：不会改成四个明细专用码。"
            ),
            "confirm_action": (
                "接受「维持原权限失败，对照改前基线人工核对」即可交付。"
                "若必须写成固定权限码，请在评论写明码值后置 blocked。"
            ),
            "case_id": case_id,
            "expected_id": "、".join(expected_ids),
            "source_refs": refs,
            "requirement_ids": [ref for ref in refs if ref.startswith("REQ-")],
        }
    if "sql_shape" in blob or "RULE-HISTORICAL-COMPATIBILITY" in refs:
        return {
            "id": f"{case_id}:human_review" if case_id else "historical-sql-baseline",
            "category": "用例设计待确认",
            "human_title": "老图能看的明细不能丢",
            "product_scene": (
                "上线前就有的统计图不用改配置。点查看明细时："
                "本来就不支持的场景走新的专用提示；本来就能看的图，数据和分页还得在。"
            ),
            "plain_summary": (
                "不支持场景的新错误码已经写成确定断言；"
                "但成功查看明细时结果长什么样没有冻结样本，"
                f"{'、'.join(f'`{item}`' for item in expected_ids) or '相关预期'} "
                "只能对照历史成功查询。"
            ),
            "confirm_action": (
                "接受「成功明细对照历史查询人工确认」即可交付。"
                "若必须先补冻结样本再编译，请评论后置 blocked。"
            ),
            "case_id": case_id,
            "expected_id": "、".join(expected_ids),
            "source_refs": refs,
            "requirement_ids": [ref for ref in refs if ref.startswith("REQ-")],
        }
    theme = humanize_review_item(case)
    return {
        "id": f"{case_id}:human_review" if case_id else "human-review",
        "category": "用例设计待确认",
        "human_title": theme["human_title"] or "期望值未冻结",
        "product_scene": theme["plain_summary"],
        "plain_summary": (
            f"{case_id or '该用例'} 有 {len(humans)} 条预期没有冻结期望值，"
            f"只能人工确认（{'、'.join(f'`{item}`' for item in expected_ids) or '相关预期'}）。"
        ),
        "confirm_action": (
            "接受「这些预期对照现网/基线人工确认」即可交付。"
            "若必须写成可自动执行的确定值，请评论补口径后置 blocked。"
        ),
        "case_id": case_id,
        "expected_id": "、".join(expected_ids),
        "source_refs": refs,
        "requirement_ids": [ref for ref in refs if ref.startswith("REQ-")],
    }


def _decision_from_skipped(skipped: Mapping[str, Any]) -> dict[str, Any]:
    skip_id = str(skipped.get("id") or "").strip()
    details = str(skipped.get("details") or skipped.get("reason") or "").strip()
    rule_ref = str(skipped.get("rule_ref") or "").strip()
    blob = f"{skip_id} {details} {rule_ref}".lower()
    if "empty" in blob and "metric" in blob:
        return {
            "id": skip_id or "SKIP-EMPTY-METRIC-NAME",
            "category": "用例设计待确认",
            "human_title": "空指标名这轮不测",
            "product_scene": (
                "统计图数据范围按结果集筛选时，如果指标显示名是空的，"
                "界面要不要提示「不支持查看明细」。"
            ),
            "plain_summary": (
                "当前口径是空指标名不生成专用提示用例，所以这轮没有这条，"
                "不会验证空名称时怎么提示。"
            ),
            "confirm_action": (
                "接受「这轮不覆盖空指标名」即可交付。"
                "若空名称也要专用提示，请评论补口径后置 blocked。"
            ),
            "case_id": "",
            "source_refs": [rule_ref] if rule_ref else [],
            "requirement_ids": [],
        }
    return {
        "id": skip_id or "skipped-scenario",
        "category": "用例设计待确认",
        "human_title": "这轮跳过一条场景",
        "product_scene": details or "有一条产品场景没有落成用例。",
        "plain_summary": (
            f"用例设计将 `{skip_id or '该场景'}` 标记为不覆盖"
            f"（{skipped.get('reason') or 'skipped'}）。"
        ),
        "confirm_action": (
            "接受「这轮可以不测这条场景」即可交付。"
            "若必须覆盖，请评论说明后置 blocked。"
        ),
        "case_id": "",
        "source_refs": [rule_ref] if rule_ref else [],
        "requirement_ids": [],
    }
