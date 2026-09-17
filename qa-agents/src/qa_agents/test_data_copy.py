"""Deterministic Chinese copy for A22 test-data-plan review items.

A22 writes free-form ``reason_code`` identifiers plus English
``required_resolution`` text into ``unresolved_requirements``. Display surfaces
always split items into two sections: owner-only materials under
``## 你需要处理``, and auto-created data under
``## 系统要去造的数据（不用你审）``. Each item answers 要测什么 / 要造什么 /
卡在哪. Owner items also show 请提供 / 请拍板. Known reason codes always use
this table; unknown codes fail closed as owner review.

The same helper is used by three layers so a plan can never reach a human
reviewer as English-only or jargon-only content:

- ingest backfill (``qa_agents.multica``) so accepted Artifacts carry Chinese
  ``human_title`` / ``product_scene`` / ``plain_summary`` / ``needed_from_you``
  / ``confirm_action`` / ``recommendation``;
- the workflow-center projection (``qa_agents.autopilot``);
- the A22 task card (``scripts.sync_eight_card_progress``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .review_copy import has_cjk

__all__ = [
    "A22_OWNER_HEADING",
    "A22_SYSTEM_HEADING",
    "DEFAULT_UNRESOLVED_TITLE",
    "OWNER_REVIEW",
    "SYSTEM_GAP",
    "GENERIC_UNRESOLVED_CONFIRM",
    "GENERIC_UNRESOLVED_NEEDED",
    "GENERIC_UNRESOLVED_PROBLEM",
    "GENERIC_UNRESOLVED_RESOLUTION",
    "GENERIC_UNRESOLVED_SCENE",
    "UNRESOLVED_REASON_ZH",
    "case_themes",
    "case_titles_from_cases",
    "has_cjk",
    "humanize_unresolved_requirement",
    "is_disposition_comment",
    "is_owner_review",
    "is_test_data_approval_item",
    "render_a22_approval_sections",
    "render_a22_issue_lines",
    "unresolved_reason_code",
    "unresolved_requirement_id",
]

DEFAULT_UNRESOLVED_TITLE = "未决数据需求"

GENERIC_UNRESOLVED_SCENE = "这轮要在 112 新建隔离测试数据，还有事项要你确认。"
GENERIC_UNRESOLVED_PROBLEM = "测试数据计划还没确认完，系统不能擅自决定怎么造数。"
GENERIC_UNRESOLVED_NEEDED = "默认新建隔离数据。确认要新建，或确认这些用例这轮不测。"
GENERIC_UNRESOLVED_CONFIRM = "要新建就 confirmed。这些用例不测才 skip。计划写错了就 return。"
GENERIC_UNRESOLVED_RESOLUTION = (
    "确认新建后放行。这些用例不测就 skip。"
    "不要把「112 没有现成数据」当成不造数的理由。"
)

# title ≤12 字 / 要测什么 / 要造什么 / 卡在哪 / 请提供(可空) / 请拍板。
# 默认路径是新建隔离数据。skip 只表示这些用例这轮不测，不是「没有现成数据就不造」。
# review=system 的项不进人审，系统默认 confirmed 去新建。
UNRESOLVED_REASON_ZH: dict[str, dict[str, str]] = {
    "stat_chart_integrity_probes_missing": {
        "title": "确认新建统计图",
        "scene": "查看明细要在真实统计图上测。",
        "problem": "112 没有现成测试图，本应新建。系统还缺图表验真步骤，所以停在这里。",
        "needed": "不用找现成图，也不用写查询。确认这轮新建隔离统计图。",
        "provide": "",
        "data": "自定义维度统计图；结果集筛选统计图；多关联统计图；动态关联统计图；一张同时命中多个不支持原因的统计图。",
        "review": "system",
        "confirm": "要新建就 confirmed。这些用例不测才 skip。",
        "resolution": "默认新建隔离统计图。不要因为没有现成图就放弃造数。",
    },
    "integrity_probes_not_in_verified_recipe": {
        "title": "确认新建并验真",
        "scene": "查看明细要在真实统计图上测。",
        "problem": "新建统计图后还要验真。验真步骤还没登记，系统不敢自己编。",
        "needed": "不用找现成图。确认这轮新建统计图，验真交给后续系统步骤。",
        "provide": "",
        "data": "隔离统计图，覆盖自定义维度、结果集筛选、多关联、动态关联。",
        "review": "system",
        "confirm": "要新建就 confirmed。这些用例不测才 skip。",
        "resolution": "默认新建。不要让模型编造验真查询。",
    },
    "historical_pre_change_assets_missing": {
        "title": "历史场景缺老图",
        "scene": "要证明改前就能看的图，改后还能看。",
        "problem": "这只能用改前就存在的图。新造的图证明不了改前行为。",
        "needed": "没有改前老图，就只能这轮不测历史兼容。",
        "provide": "若 112 有改前就存在的图，写下名称或 ID。",
        "data": "变更前就存在、没有改过配置的统计图；变更前就存在的拼表。必须是老对象，不能新造。",
        "review": "owner",
        "confirm": "有老图就 confirmed。没有就 skip。",
        "resolution": "历史用例不能用新图代替。没有老图就 skip。",
    },
    "pre_change_response_baselines_missing": {
        "title": "缺改前提示样例",
        "scene": "成功、没权限、其他失败、回退的提示，改后不能变差。",
        "problem": "新造数据带不出改前的提示原文，对不上旧返回和英文。",
        "needed": "没有改前样例时，确认对照现网人工看，或这些核对这轮不做。",
        "provide": "若有改前截图或接口返回，贴在评论里。",
        "data": "不是新建业务数据。缺的是改前「查看明细成功 / 权限失败 / 其它失败」的接口返回样例。",
        "review": "system",
        "confirm": "接受人工对照就 confirmed。不做改前核对就 skip。",
        "resolution": "不要编造改前英文。没有样例就人工对照或 skip。",
    },
    "joined_table_policy_gap": {
        "title": "请批准新建拼表",
        "scene": "Web 统计图和拼表入口的查看明细提示要一致。",
        "problem": "拼表入口也要测，但这轮还没允许自动创建拼表。",
        "needed": "不用找现成拼表。确认是否允许这轮新建拼表。",
        "provide": "",
        "data": "拼表数据：自定义维度、结果集筛选、多关联、动态关联各一套，Web 和移动端都要用。",
        "review": "system",
        "confirm": "允许新建就 confirmed。拼表入口不测才 skip。",
        "resolution": "默认批准新建拼表。不要因为没有现成拼表就放弃。",
    },
    "frozen_dynamic_relation_metadata_missing": {
        "title": "动态关联名单未定",
        "scene": "动态关联不支持查看明细，要返回专用提示。",
        "problem": "系统只知道三种对象，不能当成全部名单去造数。",
        "needed": "确认这轮按完整名单造，还是只按已知三种造。",
        "provide": "若有完整对象名单，写在评论里。",
        "data": "动态关联统计图。关联对象至少：业务流程、业务流程任务、服务记录。",
        "review": "system",
        "confirm": "给名单或同意只测三种就 confirmed。动态关联不测才 skip。",
        "resolution": "默认仍要造动态关联测试数据。名单不全就按已知三种。",
    },
    "permission_test_fixtures_missing": {
        "title": "缺无权限测试账号",
        "scene": "没权限时要维持原来的权限失败，不能改成明细专用提示。",
        "problem": "要用看不到图、看不到数据、看不到指标名的账号。这不能靠造图解决。",
        "needed": "没有这三类账号，就只能这轮不测权限场景。",
        "provide": "三类 112 账号的用户名。",
        "data": "三个 112 账号：不能看统计图；不能看指标数据；不能看指标名称。中英文都要测。",
        "review": "owner",
        "confirm": "有账号就 confirmed。没有就 skip。",
        "resolution": "权限账号需要你提供。系统不能造用户。",
    },
    "result_set_metric_type_fixtures_missing": {
        "title": "确认新建更多指标",
        "scene": "结果集按指标筛选时，不支持查看明细。",
        "problem": "还要覆盖普通指标和同环比指标。系统目前只会造聚合指标和计算指标。",
        "needed": "不用找现成指标。确认这轮要新建普通指标和同环比指标。",
        "provide": "",
        "data": "普通指标、聚合指标、计算指标、同环比指标，并做成数据范围=结果集筛选的统计图。用例例子：销售金额、毛利额、客单价、回款环比。",
        "review": "system",
        "confirm": "要新建就 confirmed。这两种这轮不测才 skip。",
        "resolution": "默认新建。不要因为 112 没有现成指标就放弃造数。",
    },
    "manual_boundary_confirmation_required": {
        "title": "数据边界未拍板",
        "scene": "造数前要知道取值边界。",
        "problem": "边界还没定，系统不能自己假定。",
        "needed": "确认边界取值，系统再按这个去造数。",
        "provide": "对象类型或字段取值范围。",
        "data": "按你确认的取值边界去新建对应测试数据。",
        "review": "owner",
        "confirm": "写下取值后 confirmed。这些用例不测才 skip。",
        "resolution": "先定边界，再新建数据。",
    },
    "manual_identifier_set_confirmation_required": {
        "title": "对象名单未拍板",
        "scene": "造数前要知道用哪些对象。",
        "problem": "对象名单还没定，系统不能自己编。",
        "needed": "确认对象名单，系统再按这个去造数。",
        "provide": "对象名称或 ID。",
        "data": "按你确认的对象名单去新建对应测试数据。",
        "review": "owner",
        "confirm": "写下名单后 confirmed。这些用例不测才 skip。",
        "resolution": "先定名单，再新建数据。",
    },
    "reusable_asset_discovery_absent": {
        "title": "确认改为新建",
        "scene": "这轮可以复用现成数据，也可以新建。",
        "problem": "没有可复用的现成数据。",
        "needed": "112 没有现成测试数据时，确认改为新建隔离数据。",
        "provide": "",
        "data": "本轮用例需要的隔离统计图、指标或拼表。",
        "review": "system",
        "confirm": "改为新建就 confirmed。这些用例不测才 skip。",
        "resolution": "没有可复用数据就新建，不要停住。",
    },
    "data_recipe_semantics_not_proven": {
        "title": "造数口径还没定",
        "scene": "新建的数据必须对上用例口径。",
        "problem": "表、字段、关联还没定，系统不能只凭名称去造。",
        "needed": "确认按哪套口径新建。口径不明就 return，不要改成不造数。",
        "provide": "表名、字段和关联关系。",
        "data": "对上用例口径的隔离测试数据：表、字段、关联关系要明确。",
        "review": "system",
        "confirm": "给出口径就 confirmed。这些用例不测才 skip。",
        "resolution": "口径定了再新建。不要用名称凑数。",
    },
    "data_capability_not_registered": {
        "title": "这种数据还不会造",
        "scene": "系统只能按已登记的能力造数。",
        "problem": "这种类型还不会造。",
        "needed": "仍要这种数据就 confirmed，后续按系统能力去造。这些用例不测才 skip。",
        "provide": "",
        "data": "用例需要、但系统还不会造的那类 112 数据。",
        "review": "system",
        "confirm": "仍要就 confirmed。不测才 skip。",
        "resolution": "默认仍要造。不要因为没有现成数据就放弃。",
    },
    "data_capability_variant_not_registered": {
        "title": "这种变体还不会造",
        "scene": "同一类数据还有不同变体。",
        "problem": "这个变体还不会造。",
        "needed": "仍要这个变体就 confirmed，后续按系统能力去造。这些用例不测才 skip。",
        "provide": "",
        "data": "用例需要的那种数据变体。",
        "review": "system",
        "confirm": "仍要就 confirmed。不测才 skip。",
        "resolution": "默认仍要造这个变体。",
    },
    "ambiguous_data_capability": {
        "title": "该造哪种还没定",
        "scene": "用例提到的数据能对应多种造法。",
        "problem": "系统不能擅自选择造哪一种。",
        "needed": "确认造哪一种，选定后系统去新建。",
        "provide": "你选的那一种，例如普通指标或聚合指标。",
        "data": "你选定的那一种数据，选定后系统去新建。",
        "review": "owner",
        "confirm": "写下选择后 confirmed。这些用例不测才 skip。",
        "resolution": "先选定再新建。",
    },
    "paused_existing_developer_unit_coverage": {
        "title": "研发数据还是新建",
        "scene": "研发单里可能已经有数据。",
        "problem": "还没决定复用研发数据，还是新建隔离数据。",
        "needed": "没有可核对的研发数据时，确认改为新建。",
        "provide": "若要复用，写研发数据名称或 ID。",
        "data": "本轮隔离测试数据；若复用研发数据则不用新造。",
        "review": "owner",
        "confirm": "改为新建或写下复用对象后 confirmed。这些用例不测才 skip。",
        "resolution": "没有可复用研发数据就新建。",
    },
    "chart_create_op_unverified": {
        "title": "确认系统去建图",
        "scene": "查看明细要在统计图上测。",
        "problem": "建图方法还没验证，系统不敢新建。",
        "needed": "不用找现成图。确认由系统新建隔离统计图。",
        "provide": "",
        "data": "隔离统计图，用来测查看明细提示。",
        "review": "system",
        "confirm": "要新建就 confirmed。这些用例不测才 skip。",
        "resolution": "默认新建隔离统计图。",
    },
    "relation_topology_params_unconfirmed": {
        "title": "关联口径未拍板",
        "scene": "多关联、动态关联不支持查看明细。",
        "problem": "表怎么关联、用哪些字段还没定，没法按口径去建图。",
        "needed": "确认关联怎么拼，系统再按这个新建图。",
        "provide": "关联对象和关联字段。",
        "data": "多关联或动态关联统计图，关联对象和字段要明确。",
        "review": "owner",
        "confirm": "写下口径后 confirmed。这些用例不测才 skip。",
        "resolution": "先定关联口径，再新建图。",
    },
    "permission_fixture_unverified": {
        "title": "权限账号未核实",
        "scene": "没权限时要维持原来的权限失败。",
        "problem": "权限测试账号还没核实。这不能靠造图解决。",
        "needed": "没有无权限账号，就只能这轮不测权限场景。",
        "provide": "看不到图、看不到数据、看不到指标名的 112 账号。",
        "data": "三个无权限 112 账号：不能看图、不能看数据、不能看指标名。",
        "review": "owner",
        "confirm": "有账号就 confirmed。没有就 skip。",
        "resolution": "权限账号需要你提供。",
    },
    "historical_fixture_seed_unverified": {
        "title": "改前老数据未核实",
        "scene": "上线前就有的配置，查看明细不能变差。",
        "problem": "所谓改前数据还没核实。新造的数据不能冒充改前数据。",
        "needed": "没有核实过的改前数据，就只能这轮不测历史配置。",
        "provide": "已核实的改前统计图或配置名称、ID。",
        "data": "变更前就存在的统计图或配置。不能新造。",
        "review": "owner",
        "confirm": "有核实过的老数据就 confirmed。没有就 skip。",
        "resolution": "历史配置不能用新数据代替。",
    },
    "fault_injection_capability_unconfirmed": {
        "title": "异常路径还不会测",
        "scene": "元数据服务异常、超时时，查看明细要有对应表现。",
        "problem": "异常注入不是造数能解决的。",
        "needed": "确认这些异常用例这轮不测，或使用已批准的注入方式。",
        "provide": "若有已批准的故障注入方式，写在评论里。",
        "data": "不是业务测试数据。缺的是元数据异常、超时的注入方式。",
        "review": "system",
        "confirm": "不测异常路径就 skip。有注入方式就 confirmed。",
        "resolution": "异常路径不能靠新建业务数据解决。",
    },
}

_ENTRY_FIELDS = ("title", "scene", "problem", "needed", "provide", "data", "review", "confirm", "resolution")
_PROBLEM_FIELDS = ("plain_summary", "requirement", "detail", "summary", "message")
_RESOLUTION_FIELDS = (
    "recommendation",
    "required_resolution",
    "resolution",
    "suggested_resolution",
)
_DISPOSITION_RE = re.compile(
    r"UR-\d{2}\s*:\s*confirmed/skip/return/need_evidence",
    re.IGNORECASE,
)
_UR_REVIEW_ID = re.compile(r"UR-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")


def unresolved_reason_code(item: Mapping[str, Any]) -> str:
    """Return the free-form A22 reason code of one unresolved requirement."""

    return str(
        item.get("reason_code")
        or item.get("reason")
        or item.get("id")
        or item.get("issue_code")
        or ""
    ).strip()


def unresolved_requirement_id(item: Mapping[str, Any], index: int = 0) -> str:
    """Return the review id used by the A22 disposition comments.

    Plans normally declare ``UR-01``, but A22 re-runs are free-form and emit
    ids such as ``UR-DISC-01``. Renumbering those to ``UR-01`` silently made
    the same id mean a different requirement after every plan revision, so the
    owner's earlier disposition comment could be applied to the wrong
    requirement. Any ``UR-...`` id the agent declared is therefore kept as is;
    only plans without any id-like field fall back to the 1-based ``UR-NN``.
    """

    raw = str(
        item.get("requirement_id")
        or item.get("id")
        or ""
    ).strip()
    declared = raw.upper()
    if _UR_REVIEW_ID.fullmatch(declared):
        return declared
    return f"UR-{index + 1:02d}"


def is_disposition_comment(text: str) -> bool:
    """Return True when the text is the A22 comment template, not a decision."""

    return bool(_DISPOSITION_RE.search(str(text or "").strip()))


def _first_chinese(values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and has_cjk(text) and not is_disposition_comment(text):
            return text
    return ""


CASE_THEME_ZH: tuple[tuple[str, str], ...] = (
    ("CUSTOM-DIMENSION", "自定义维度不支持查看明细"),
    ("RESULT-SET", "结果集筛选不支持查看明细"),
    ("MULTI-RELATION", "多关联不支持查看明细"),
    ("DYNAMIC-RELATION", "动态关联不支持查看明细"),
    ("CROSS-ENTRY-HISTORY", "统计图/拼表在 Web、移动端提示一致，以及改前老图还能看明细"),
    ("MULTILINGUAL", "Web 和移动端的中英文提示一致"),
    ("PRIORITY-MULTI-REASON", "没权限时走原来的权限失败；多个不支持原因只回一条提示"),
)

OWNER_REVIEW = "owner"
SYSTEM_GAP = "system"

A22_OWNER_HEADING = "## 你需要处理"
A22_SYSTEM_HEADING = "## 系统要去造的数据（不用你审）"
A22_DISPOSITION_TEMPLATE = "confirmed/skip/return/need_evidence"


def _affected_case_ids(item: Mapping[str, Any]) -> list[str]:
    for key in ("affected_case_ids", "affected_cases"):
        raw = item.get(key)
        if isinstance(raw, list):
            return [str(value).strip() for value in raw if str(value).strip()]
    return []


def case_titles_from_cases(cases: Any) -> dict[str, str]:
    """Collect Chinese case titles from compiled case objects."""

    titles: dict[str, str] = {}
    if not isinstance(cases, list):
        return titles
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        case_id = str(case.get("id") or case.get("case_id") or "").strip()
        title = _first_chinese(
            (
                case.get("title"),
                case.get("human_title"),
                case.get("name"),
                case.get("scene"),
            )
        )
        if case_id and title:
            titles[case_id] = title
    return titles


def _case_title_catalog(
    item: Mapping[str, Any],
    case_titles: Mapping[str, str] | None,
) -> dict[str, str]:
    catalog: dict[str, str] = {}
    if case_titles:
        for key, value in case_titles.items():
            text = str(value or "").strip()
            if str(key).strip() and text:
                catalog[str(key).strip()] = text
    raw = item.get("affected_case_titles")
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            text = str(value or "").strip()
            if str(key).strip() and text:
                catalog[str(key).strip()] = text
    return catalog


def case_themes(
    case_ids: list[str],
    case_titles: Mapping[str, str] | None = None,
) -> list[str]:
    """Map compiled cases to product scenes, de-duplicated in order.

    Prefer the case title, then a known id token, so a later requirement is
    not stuck with this run's hardcoded scene table.
    """

    catalog = case_titles or {}
    themes: list[str] = []
    seen: set[str] = set()
    for case_id in case_ids:
        title = str(catalog.get(case_id) or "").strip()
        theme = ""
        if title and has_cjk(title):
            theme = title.rstrip("。；; ")
        else:
            blob = case_id.upper()
            for token, mapped in CASE_THEME_ZH:
                if token in blob:
                    theme = mapped
                    break
        if theme and theme not in seen:
            seen.add(theme)
            themes.append(theme)
    return themes


def is_owner_review(item: Mapping[str, Any] | str) -> bool:
    """Return True when only the QA owner can supply the missing material."""

    if isinstance(item, str):
        code = item
        review = str(UNRESOLVED_REASON_ZH.get(code, {}).get("review") or "").strip()
    else:
        code = unresolved_reason_code(item)
        review = str(item.get("review_kind") or item.get("review") or "").strip()
        if not review:
            review = str(UNRESOLVED_REASON_ZH.get(code, {}).get("review") or "").strip()
    return review != SYSTEM_GAP


def is_test_data_approval_item(item: Mapping[str, Any], node_id: str = "") -> bool:
    """Identify A22 unresolved-data items that use the two-section card."""

    if node_id == "A22":
        return True
    if str(item.get("category") or "") == "test_data_pending_human":
        return True
    return bool(str(item.get("reason_code") or "").strip())


def humanize_unresolved_requirement(
    item: Mapping[str, Any],
    index: int = 0,
    *,
    case_titles: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return one unresolved requirement with Chinese human-facing fields.

    Known reason codes always use the product-language table so the reviewer
    never has to decode Agent jargon or English ``required_resolution``.
    Unknown codes keep author Chinese when present, otherwise the generic copy.
    Unknown codes fail closed as owner review.
    """

    code = unresolved_reason_code(item)
    entry = UNRESOLVED_REASON_ZH.get(code, {})
    requirement_id = unresolved_requirement_id(item, index)
    affected = _affected_case_ids(item)
    catalog = _case_title_catalog(item, case_titles)
    themes = case_themes(affected, case_titles=catalog)
    persisted_titles = {
        case_id: catalog[case_id] for case_id in affected if case_id in catalog
    }
    if entry:
        title = entry["title"]
        scene = entry["scene"]
        problem = entry["problem"]
        needed = entry["needed"]
        provide = str(entry.get("provide") or "").strip()
        confirm = entry["confirm"]
        resolution = entry["resolution"]
        data = str(entry.get("data") or "").strip()
        review = str(entry.get("review") or SYSTEM_GAP)
    else:
        title = _first_chinese((item.get("human_title"),)) or DEFAULT_UNRESOLVED_TITLE
        scene = _first_chinese((item.get("product_scene"),)) or GENERIC_UNRESOLVED_SCENE
        problem = _first_chinese(item.get(field) for field in _PROBLEM_FIELDS)
        if not problem:
            problem = GENERIC_UNRESOLVED_PROBLEM
            if code:
                problem = f"{problem}（内部原因代码：{code}）"
        needed = (
            _first_chinese((item.get("needed_from_you"),)) or GENERIC_UNRESOLVED_NEEDED
        )
        provide = _first_chinese((item.get("provide_from_you"), item.get("provide")))
        confirm = (
            _first_chinese((item.get("confirm_action"),)) or GENERIC_UNRESOLVED_CONFIRM
        )
        resolution = _first_chinese(item.get(field) for field in _RESOLUTION_FIELDS)
        if not resolution:
            resolution = GENERIC_UNRESOLVED_RESOLUTION
        data = _first_chinese((item.get("data_to_build"), item.get("data")))
        review = OWNER_REVIEW
    if themes:
        scene = "；".join(themes) + "。"
    if review == SYSTEM_GAP:
        needed = "不需要你审。这是系统自己该去造的数据，不是产品口径。"
        provide = ""
        confirm = "不用回评论。系统默认按新建继续。"
        why = "系统缺造数能力或验真步骤，不该问你要不要建。"
    else:
        why = "系统造不出来，只有你知道 112 里有没有这些材料。"
    humanized = dict(item)
    humanized.update(
        {
            "requirement_id": requirement_id,
            "reason_code": code,
            "human_title": title,
            "product_scene": scene,
            "plain_summary": problem,
            "data_to_build": data,
            "review_kind": review,
            "why_human": why,
            "needed_from_you": needed,
            "provide_from_you": provide,
            "confirm_action": confirm,
            "recommendation": resolution,
            "affected_case_ids": affected,
            "affected_case_titles": persisted_titles,
        }
    )
    return humanized


def render_a22_issue_lines(
    issue: Mapping[str, Any],
    index: int,
    *,
    decision: bool,
) -> list[str]:
    """Render one A22 item with the locked field labels."""

    issue_id = str(
        issue.get("requirement_id") or unresolved_requirement_id(issue, index - 1)
    )
    title = str(issue.get("human_title") or "未决数据需求")
    severity = str(issue.get("severity") or "")
    header = f"{index}. **{title}**（`{issue_id}`"
    if severity:
        header += f" · {severity}"
    header += "）"
    lines = [header]
    scene = str(issue.get("product_scene") or "").strip()
    data = str(issue.get("data_to_build") or "").strip()
    summary = str(issue.get("plain_summary") or issue.get("summary") or "").strip()
    why = str(issue.get("why_human") or "").strip()
    needed = str(issue.get("needed_from_you") or "").strip()
    provide = str(issue.get("provide_from_you") or "").strip()
    confirm = str(issue.get("confirm_action") or "").strip()
    if is_disposition_comment(confirm):
        confirm = ""
    if scene:
        lines.append(f"   - 要测什么：{scene}")
    if data:
        lines.append(f"   - 要造什么：{data}")
    if summary:
        lines.append(f"   - 卡在哪：{summary}")
    if why:
        lines.append(f"   - 为什么出现在这张卡：{why}")
    affected_case_ids = issue.get("affected_case_ids")
    if not isinstance(affected_case_ids, list) or not affected_case_ids:
        affected_case_ids = (
            issue.get("affected_cases")
            if isinstance(issue.get("affected_cases"), list)
            else []
        )
    if affected_case_ids:
        lines.append(
            "   - 涉及用例：" + "、".join(f"`{item}`" for item in affected_case_ids)
        )
    if decision:
        if needed:
            lines.append(f"   - 你要确认：{needed}")
        if provide:
            lines.append(f"   - 请提供：{provide}")
        if confirm:
            lines.append(f"   - 请拍板：{confirm}")
        lines.append(
            f"   - 处置评论：`{issue_id}: {A22_DISPOSITION_TEMPLATE}`"
        )
    lines.append("")
    return lines


def render_a22_approval_sections(
    issues: Sequence[Mapping[str, Any]],
    *,
    include_operations: bool = True,
    node_id: str = "",
    case_titles: Mapping[str, str] | None = None,
) -> list[str]:
    """Render the locked two-section A22 review card."""

    humanized = [
        humanize_unresolved_requirement(item, index, case_titles=case_titles)
        for index, item in enumerate(issues)
    ]
    owner_issues = [issue for issue in humanized if is_owner_review(issue)]
    system_issues = [issue for issue in humanized if not is_owner_review(issue)]
    lines = [A22_OWNER_HEADING, ""]
    if owner_issues:
        lines.append("只列出系统造不出来、必须你拍板的材料。")
        lines.append("")
        lines.append(f"待审批：`{len(owner_issues)}` 项")
        lines.append("")
        for index, issue in enumerate(owner_issues, 1):
            lines.extend(render_a22_issue_lines(issue, index, decision=True))
    else:
        lines.append("没有必须你拍板的材料。")
        lines.append("")
    if system_issues:
        lines.extend(
            [
                A22_SYSTEM_HEADING,
                "",
                "这些是 A22 自己还不会造或还没授权的数据，不是产品口径。",
                "不用回评论。系统默认按新建继续。",
                "",
            ]
        )
        for index, issue in enumerate(system_issues, 1):
            lines.extend(render_a22_issue_lines(issue, index, decision=False))
    if include_operations:
        lines.extend(
            [
                "操作选项：",
                "- 只给上面「你需要处理」里出现「请提供」的项回评论。",
                "- 先在评论区逐项写出处置，再置 **done**；仅改状态不会形成确认。",
                "- `confirmed`：你补了材料，按评论继续。",
                "- `skip`：这些用例这轮不测。",
                "- `return`：计划理解错了，退回 A22。",
                "- 置 **cancelled**：终止当前流程。",
                "",
            ]
        )
    return lines
