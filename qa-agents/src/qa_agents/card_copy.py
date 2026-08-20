"""Deterministic card copy for the Multica workflow surface (card-copy skill).

Single source of truth for readable card titles and the five-section
description template (目标 / 背景 / 范围 / 输入材料 / 验收) that every stage
card, node task card, human correction card and review gate card must follow.
Renderers in ``workflow_center``, ``human_correction``, ``g01_review``,
``g02_review`` and the node dispatch script go through these builders so the
Multica detail page stays readable and the copy stays consistent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .requirement_case_renderer import render_review_card

STAGE_CARD_COPY: dict[str, dict[str, Any]] = {
    "C1": {
        "goal": "冻结需求、技术方案与后端变更，确定流程路由，并完成需求-方案-变更对齐。",
        "background": "新需求进入 QA 流程的第一步：先固定输入快照与路由，再完成需求、可测性和后端变更分析；未选分支必须留下明确跳过原因。",
        "scope_includes": [
            "输入冻结与来源快照",
            "工作流路由与深度选择",
            "需求分析、技术可测性分析、后端变更分析",
            "需求-方案-变更对齐",
        ],
        "scope_excludes": ["不产出正式测试用例", "不审批生产发布", "不修改业务代码"],
        "inputs": [
            "需求原文与来源快照",
            "技术方案与后端 ChangeSet",
            "只读代码/OpenAPI 快照",
        ],
        "acceptance": [
            "路由确定，需求、方案和后端变更完成对齐",
            "未选分支有明确跳过原因",
            "需要人工确认的事项已并入 G01",
        ],
    },
    "C2": {
        "goal": "确认测试范围与需求口径，冻结风险等级、必测层级与 Gate 策略。",
        "background": "C1 对齐结论中仍有需要人工确认的事项；G01 人工审核范围，N24 按审核结论确定性生成测试策略。",
        "scope_includes": [
            "范围与口径人工审核（G01）",
            "风险等级、必测层级与 Gate 策略（N24）",
        ],
        "scope_excludes": ["不审批生产发布", "不代替研发补实现证据"],
        "inputs": ["C1 对齐结论", "G01 审核请求与决策模板", "N24 风险策略输入"],
        "acceptance": ["G01 审核完成并形成 Decision Artifact", "N24 测试策略已冻结"],
    },
    "C3": {
        "goal": "产出可执行的 Test Case IR 与覆盖矩阵，通过确定性校验，并把用例交付给 QA Owner 评审。",
        "background": "范围与策略冻结后进入测试设计；A08 设计、A09 审查、N04 确定性校验、G02 交付评审缺一不可。",
        "scope_includes": [
            "Test Case IR 设计与覆盖矩阵（A08）",
            "Oracle 与覆盖审查（A09）",
            "Test Case IR 确定性校验（N04）",
            "用例交付评审（G02）：评论缺场景后由 A08 按评论修正",
        ],
        "scope_excludes": ["不修改冻结需求与技术方案", "不执行自动化用例"],
        "inputs": ["冻结需求与 G01 结论", "N24 测试策略", "A08/A09/N04/G02 Artifact 链"],
        "acceptance": ["N04 校验通过", "G02 形成有效评审 Decision Artifact", "缺场景评论回流 A08 修正闭环"],
    },
    "C4": {
        "goal": "把已审核的父用例编译为可执行子用例，完成覆盖回查、测试选择与执行计划。",
        "background": "C3 交付有效 Test Case IR 后，需要确定哪些用例进入执行以及如何路由。",
        "scope_includes": [
            "父子 Case 编译（N25）",
            "拆分覆盖审查（A11）",
            "测试选择（N26）",
            "执行计划编译（N15）",
        ],
        "scope_excludes": ["不生成自动化代码", "不启动真实执行"],
        "inputs": ["C3 已审核 Test Case IR", "资产影响关系", "风险与策略"],
        "acceptance": ["父子 Case 编译、覆盖回查、测试选择与执行路由全部完成"],
    },
    "C5": {
        "goal": "生成所选自动化与测试数据计划，完成独立复核、安全校验和代码检查。",
        "background": "C4 确定执行计划后，为每个执行项准备自动化代码、测试数据与门禁结论。",
        "scope_includes": [
            "后端/契约自动化生成（A14/A15）",
            "测试数据计划（A22）",
            "独立复核（A18-BE/A18-CT）",
            "数据安全校验（N27）与确定性代码检查（N05）",
            "自动化代码人工审核（G03）",
        ],
        "scope_excludes": ["不执行自动化用例", "不修改业务仓库"],
        "inputs": ["C4 执行计划与 Test Case IR", "冻结 OpenAPI", "112 能力目录与测试数据能力"],
        "acceptance": ["自动化 Manifest、测试数据计划、审查与检查结论全部就绪"],
    },
    "C6": {
        "goal": "完成环境预检、受控自动化执行与人工/探索测试，给出重试预算结论。",
        "background": "C5 已就绪自动化与数据；本阶段在真实环境执行并收集证据。",
        "scope_includes": [
            "环境预检（N07）",
            "受控自动化执行（N08）",
            "人工与探索测试（N17）",
            "环境失败重试预算（N10）",
        ],
        "scope_excludes": ["不跳过安全校验直接执行", "不发布"],
        "inputs": ["C5 已就绪自动化与数据", "测试环境账号与资源"],
        "acceptance": ["预检通过，自动化与人工任务执行完毕", "重试预算有明确结论"],
    },
    "C7": {
        "goal": "归一执行证据与缺陷，做出确定性质量决策，登记可选豁免。",
        "background": "C6 产生原始证据；本阶段负责把失败聚类、跨运行去重并形成质量结论。",
        "scope_includes": [
            "运行质量信号采集（N18）",
            "证据标准化与失败聚类（N09）",
            "跨运行缺陷去重（N20）",
            "确定性质量决策（N11）",
            "质量豁免审计（N19）",
        ],
        "scope_excludes": ["不重新执行用例", "不代签豁免"],
        "inputs": ["C6 执行证据", "历史缺陷与失败指纹"],
        "acceptance": ["证据与缺陷归一完成", "质量结论及可选豁免已登记"],
    },
    "C8": {
        "goal": "发布质量报告，归档反馈，并按授权执行上线后验证与审计。",
        "background": "质量结论形成后进入收尾：报告、反馈、上线后验证与关闭。",
        "scope_includes": [
            "质量报告发布（N12）",
            "反馈归档（N13）",
            "按授权上线后验证与审计（N23）",
        ],
        "scope_excludes": ["不发布未经授权的内容", "不关闭未完成事项"],
        "inputs": ["C7 质量结论", "报告发布授权"],
        "acceptance": ["报告发布、反馈归档及上线后验证均终态"],
    },
}

NODE_CARD_COPY: dict[str, dict[str, Any]] = {
    "A02": {
        "goal": "把冻结需求转换为结构化需求分析，提取目标、规则、范围与歧义，为可测性分析与测试设计提供业务基线。",
        "background": "C1 输入冻结后由 A02 执行，输出需求语义基线供 A03/A05 分析与 A06 对齐使用；歧义与待确认项必须显式登记并并入 G01。",
        "scope_includes": [
            "提取需求目标、业务规则、范围与边界",
            "识别歧义、缺失与待人工确认项",
            "输出结构化需求清单并绑定来源引用",
        ],
        "scope_excludes": [
            "推测未提供的产品决策",
            "修改需求原文与技术方案",
            "执行测试或编写自动化代码",
        ],
        "inputs": ["输入参数包（附件）", "冻结需求快照", "需求原文与来源引用"],
        "acceptance": [
            "产出 a02-requirement-analysis Artifact 并入库",
            "需求规则可追溯、歧义显式，待确认项已并入 G01",
        ],
    },
    "A03": {
        "goal": "识别技术实现链路与可测性，明确接口、依赖、故障点与测试钩子，为 Case 绑定真实执行点。",
        "background": "A02 需求分析完成后由 A03 执行；本卡分析技术方案与实现链路，产出可测性结论与阻塞项，需要人工确认的测试注入或环境改造并入 G01。",
        "scope_includes": [
            "分析接口、依赖、故障点与测试钩子",
            "评估技术可测性并登记不可测项",
            "标记阻塞测试设计的待确认项",
        ],
        "scope_excludes": [
            "修改业务仓库或技术方案",
            "直接生成测试用例与自动化代码",
        ],
        "inputs": [
            "输入参数包（附件）",
            "A02 需求分析",
            "冻结技术方案与实现链路",
            "只读代码/产品文档快照",
        ],
        "acceptance": [
            "产出 a03-technical-testability-analysis Artifact 并入库",
            "执行链路与不可测项明确，阻塞项有修正方案并并入 G01",
        ],
    },
    "A05": {
        "goal": "分析后端代码变更及接口影响，用代码证据定位服务、接口、DTO 与数据路径。",
        "background": "自动化需要真实服务契约与实现证据；本卡只读分析后端 ChangeSet，产出变更事实与影响映射，供 A06 对齐与后续自动化使用。",
        "scope_includes": [
            "定位服务、接口、DTO 与数据路径",
            "关联变更代码与受影响接口",
            "产出带代码证据的变更事实清单",
        ],
        "scope_excludes": [
            "写入或修改业务仓库",
            "评估产品语义与业务决策",
        ],
        "inputs": [
            "输入参数包（附件）",
            "后端 ChangeSet 与变更差异",
            "只读代码/OpenAPI 快照",
        ],
        "acceptance": [
            "产出 a05-backend-change-analysis Artifact 并入库",
            "接口映射有代码证据支撑，跨服务影响范围明确",
        ],
    },
    "A06": {
        "goal": "合并 A02 需求分析、A03 可测性分析与 A05 后端变更，对齐需求-方案-变更并标记冲突与缺口。",
        "background": "A02/A03/A05 完成后由 A06 汇总对齐；对齐结论是 C2 范围确认与 G01 审核的输入，冲突与缺口必须显式列出。",
        "scope_includes": [
            "合并需求、技术实现与后端变更事实",
            "标记需求-方案-变更冲突与覆盖缺口",
            "输出可审核的对齐结论与待确认建议",
        ],
        "scope_excludes": [
            "自行裁决产品歧义与业务决策",
            "修改需求、技术方案或业务代码",
        ],
        "inputs": [
            "输入参数包（附件）",
            "A02 需求分析",
            "A03 技术可测性分析",
            "A05 后端变更分析",
        ],
        "acceptance": [
            "产出 a06-alignment-result Artifact 并入库",
            "冲突、缺口与建议可审核，待确认项已并入 G01",
        ],
    },
    "A08": {
        "goal": "按冻结需求、G01 审批结论与 N24 测试策略，产出可执行的 Test Case IR 与覆盖矩阵。",
        "background": "范围与策略已冻结，进入测试设计；本卡由 A08 Agent 执行，输入来自 C2 已批准的范围与策略。",
        "scope_includes": [
            "Test Case IR 设计（含中英文 locale 分支）",
            "覆盖矩阵与 Oracle 期望值",
        ],
        "scope_excludes": ["修改冻结需求/技术方案", "修改业务代码、提交或发布"],
        "inputs": ["输入参数包（附件）", "冻结需求快照与 G01 结论", "N24 测试策略"],
        "acceptance": ["产出 a08-test-design-ir Artifact 并入库", "通过 N04 校验，覆盖缺口由 A09 审查确认"],
    },
    "A09": {
        "goal": "审查 Oracle 期望值与测试覆盖，输出可执行结论或需要修正的问题清单。",
        "background": "A08 测试设计入库后，由 A09 Agent 独立审查 Oracle 与覆盖。",
        "scope_includes": ["Oracle 期望值审查", "覆盖缺口识别与修正建议"],
        "scope_excludes": ["修改测试设计本身", "代签人工决策"],
        "inputs": ["输入参数包（附件）", "A08 Test Case IR"],
        "acceptance": ["产出 a09-oracle-coverage-review Artifact 并入库", "阻塞问题有明确修正方案与来源引用"],
    },
    "A11": {
        "goal": "审查父子 Case 拆分与覆盖完整性，确保每条子用例原子、可执行且无无效重复。",
        "background": "N25 将已审核父用例编译为子用例后由 A11 独立审查；审查结论决定是否放行测试选择（N26）与执行计划（N15）。",
        "scope_includes": [
            "检查子用例原子性与拆分粒度",
            "核对父子用例覆盖映射与重复",
            "输出阻塞问题与合并/拆分建议",
        ],
        "scope_excludes": [
            "生成自动化代码或执行用例",
            "修改冻结的父用例与测试设计",
        ],
        "inputs": [
            "输入参数包（附件）",
            "N25 父子 Case 编译结果",
            "C3 已审核 Test Case IR",
        ],
        "acceptance": [
            "产出 a11-split-coverage-review Artifact 并入库",
            "覆盖无缺口、无无效重复，阻塞问题有明确修正建议",
        ],
    },
    "A14": {
        "goal": "按执行计划把后端用例生成独立 pytest 接口自动化候选，并产出自动化 Manifest。",
        "background": "C4 执行计划确定后由 A14 生成后端自动化；候选须绑定接口、测试数据计划与 Oracle，经 A18-BE 独立复核、N05 代码检查与 G03 人工审核后才可执行。",
        "scope_includes": [
            "绑定接口、数据计划与 Oracle 生成 pytest",
            "维护每条 Case 到用例的可追溯性",
            "产出自动化 Manifest 与 pytest 候选文件",
        ],
        "scope_excludes": [
            "直接写业务仓库或发布",
            "跳过独立复核与安全校验直接执行",
        ],
        "inputs": [
            "输入参数包（附件）",
            "C4 执行计划与 Test Case IR",
            "冻结 OpenAPI 与契约",
            "A22 测试数据计划",
        ],
        "acceptance": [
            "产出 a14-backend-automation-generation 与自动化 Manifest 并入库",
            "每条 Case 可追溯且断言有效，通过 N05 确定性代码检查",
        ],
    },
    "A15": {
        "goal": "生成接口契约自动化候选，保护 DTO 与接口兼容性。",
        "background": "契约层需要独立保护；A15 基于冻结契约生成契约校验与兼容性测试，经 A18-CT 复核、N05 检查与 G03 审核后放行。",
        "scope_includes": [
            "生成契约校验与兼容性测试",
            "绑定契约版本、断言与数据依赖",
            "产出自动化 Manifest 与 pytest 候选文件",
        ],
        "scope_excludes": [
            "修改服务契约或业务仓库",
            "代签人工审核 Gate",
        ],
        "inputs": [
            "输入参数包（附件）",
            "C4 执行计划与 Test Case IR",
            "冻结 OpenAPI 与契约快照",
        ],
        "acceptance": [
            "产出 a15-contract-automation-generation 并入库",
            "契约版本与断言明确，兼容性预期可审核",
        ],
    },
    "A22": {
        "goal": "从已审核用例提取测试数据意图，规划主题、资源、约束与数据关系，产出可执行的测试数据计划。",
        "background": "自动化生成前必须明确要创建什么数据与资产；A22 基于能力目录与数据意图解析 112 数据能力，产出测试数据计划供 A14/A15 绑定与 N27 安全校验。",
        "scope_includes": [
            "识别数据主题、资源、约束与数据关系",
            "结合 112 能力目录规划数据生成方式",
            "标记保留要求与高风险写入",
        ],
        "scope_excludes": [
            "直接猜测接口参数或执行未验证写入",
            "绕过 N27 数据安全校验",
        ],
        "inputs": [
            "输入参数包（附件）",
            "C4 执行计划与 Test Case IR",
            "112 能力目录与数据能力",
            "data-intent 数据意图解析",
        ],
        "acceptance": [
            "产出 a22-test-data-plan Artifact 并入库",
            "每条用例数据需求完整，可进入资源规划与 N27 安全校验",
        ],
    },
    "A18-BE": {
        "goal": "独立复核 A14 生成的服务端自动化候选，确认 Manifest、候选文件与用例 Oracle 绑定一致。",
        "background": "生成与复核职责分离；A18-BE 只看 A14 的 Manifest 与候选代码，不访问生成器推理，阻塞问题路由回 A14 修正。",
        "scope_includes": [
            "核对 Manifest 与候选文件绑定",
            "检查 Oracle 断言、执行绑定与安全红线",
            "输出阻塞问题清单与路由建议",
        ],
        "scope_excludes": [
            "修改候选代码或生成器输出",
            "访问生成器隐藏推理与评估 Oracle",
        ],
        "inputs": [
            "输入参数包（附件）",
            "A14 服务端自动化生成结果",
            "N25 已编译用例与安全规则",
        ],
        "acceptance": [
            "产出 a18-be-backend-automation-review Artifact 并入库",
            "阻塞问题有明确 case 与修正路由",
        ],
    },
    "A18-CT": {
        "goal": "独立复核 A15 生成的契约自动化候选，确认契约引用、兼容性断言与候选文件绑定一致。",
        "background": "契约层保护独立于生成器；A18-CT 只看 A15 的 Manifest 与候选代码，不访问生成器推理，阻塞问题路由回 A15 修正。",
        "scope_includes": [
            "核对契约引用与兼容性断言",
            "检查 Manifest、候选文件与安全红线",
            "输出阻塞问题清单与路由建议",
        ],
        "scope_excludes": [
            "修改候选代码或生成器输出",
            "访问生成器隐藏推理与评估 Oracle",
        ],
        "inputs": [
            "输入参数包（附件）",
            "A15 契约自动化生成结果",
            "N25 已编译用例与安全规则",
        ],
        "acceptance": [
            "产出 a18-ct-contract-automation-review Artifact 并入库",
            "契约兼容性预期可审核，阻塞问题有明确路由",
        ],
    },
}

DEFAULT_NODE_COPY: dict[str, Any] = {
    "goal": "按输入参数包执行本节点职责，产出对应 Artifact 并入库。",
    "background": "上游条件满足后由本节点 Agent 执行，结果进入工作流 Artifact 链。",
    "scope_includes": ["按输入参数包执行节点任务", "产出并入库本节点 Artifact"],
    "scope_excludes": ["越权修改其他节点产物", "代签人工 Gate", "修改业务代码或发布"],
    "inputs": ["输入参数包（附件）", "上游已验收 Artifact"],
    "acceptance": ["本节点 Artifact 已入库", "状态按结果推进或回流"],
}

_HUMAN_ISSUE_TITLES = {
    "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE": "预期结果无法解析",
    "LOCALE_NAME_PRECEDENCE_FIXTURE_CONFLICT": "中英文测试数据冲突",
    "RULE_CONFLICT": "规则冲突",
    "MISSING_EXPECTATION": "缺少期望值",
    "AMBIGUOUS_REQUIREMENT": "需求表述歧义",
    "COVERAGE_GAP": "覆盖缺口",
    "BLOCKING_GAP": "阻塞性缺口",
}


def stage_card_title(run_id: str, card_id: str, title: str) -> str:
    return f"[{run_id}] {card_id} {title}"


def stage_card_sections(card_id: str) -> dict[str, Any]:
    return STAGE_CARD_COPY.get(card_id, DEFAULT_NODE_COPY)


def node_issue_title(run_id: str, node_id: str, label: str) -> str:
    return f"[{run_id}] {node_id} {label}"


def _approval_section_lines(
    issues: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Render the human decision block for a waiting node card."""

    lines = ["## 你需要处理", ""]
    lines.append("本卡阻塞问题已路由人工处置，需要你决定下一步。")
    lines.append("")
    lines.append(f"待审批：`{len(issues)}` 项")
    lines.append("")
    for index, issue in enumerate(issues, 1):
        issue_id = str(issue.get("id") or "")
        title = str(
            issue.get("human_title")
            or _HUMAN_ISSUE_TITLES.get(str(issue.get("issue_code") or ""), "")
            or "阻塞问题"
        )
        severity = str(issue.get("severity") or "")
        summary = str(
            issue.get("plain_summary")
            or issue.get("summary")
            or issue.get("message")
            or ""
        )
        recommendation = str(issue.get("recommendation") or "")
        case_id = str(issue.get("case_id") or "")
        expected_id = str(issue.get("expected_id") or "")
        source_refs = (
            issue.get("source_refs")
            if isinstance(issue.get("source_refs"), list)
            else []
        )
        lines.extend(
            [
                f"{index}. **{title}**（`{issue_id}` · {severity}）",
                f"   - 问题：{summary}",
                f"   - 建议修正：{recommendation}",
            ]
        )
        if case_id:
            lines.append(f"   - 涉及用例：`{case_id}`")
        if expected_id:
            lines.append(f"   - 期望项：`{expected_id}`")
        if source_refs:
            lines.append("   - 来源：" + "、".join(f"`{item}`" for item in source_refs))
        lines.append("")
    lines.extend(
        [
            "操作选项：",
            "- 置 **done**：授权按上述建议定向修正，系统重新入库并重跑 A09/N04 校验。",
            "- 置 **cancelled**：终止当前流程。",
            "- 置 **blocked**：暂不处理，保持等待。",
            "",
        ]
    )
    return lines


def node_issue_description(
    node_id: str,
    label: str,
    *,
    input_name: str = "",
    approval_issues: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    copy = NODE_CARD_COPY.get(node_id, DEFAULT_NODE_COPY)
    input_line = f"- 输入参数包（附件：`{input_name}`）" if input_name else "- 输入参数包（附件）"
    background = str(copy["background"])
    if "修正" in label:
        background += " 本卡为修正轮，绑定上一版输入参数包与校验结论。"
    lines = [
        f"# {node_id} {label}",
        "",
        "## 目标",
        "",
        str(copy["goal"]),
        "",
        "## 背景",
        "",
        background,
        "",
        "## 范围",
        "",
        "包含：",
        *(f"- {item}" for item in copy["scope_includes"]),
        "",
        "不包含：",
        *(f"- {item}" for item in copy["scope_excludes"]),
        "",
        "## 输入材料",
        "",
        input_line,
        *(f"- {item}" for item in copy["inputs"][1:]),
        "",
        "## 验收",
        "",
        *(f"- {item}" for item in copy["acceptance"]),
        "",
    ]
    if approval_issues:
        lines.extend(_approval_section_lines(approval_issues))
    return "\n".join(lines)


def node_record_description(
    node_id: str,
    label: str,
    *,
    artifact_name: str = "",
    approval_block: Sequence[str] | None = None,
) -> str:
    """Five-section card for a deterministic node record Issue.

    Deterministic nodes (for example N25/N26/N15) run locally without an
    Agent. A record Issue is created so the stage-card detail page can link
    the subtask to its accepted Artifact evidence. ``approval_block`` appends
    a human-decision section when the record carries an actionable decision
    (for example a retryable automation failure that needs retry approval).
    """

    artifact_line = f"- 本节点 Artifact（附件：`{artifact_name}`）" if artifact_name else "- 本节点 Artifact（附件）"
    if approval_block:
        background = (
            "本节点由工作流自动执行；因执行失败判定可重试，"
            "需要你审批重试决策（本卡仍由系统自动创建并同步状态）。"
        )
        scope_excludes = [
            "修改其他节点产物",
        ]
    else:
        background = "本节点由工作流自动执行，无需 Agent 或人工操作；本卡由系统自动创建并同步状态。"
        scope_excludes = [
            "人工决策与审批",
            "修改其他节点产物",
        ]
    lines = [
        f"# {node_id} {label}",
        "",
        "## 目标",
        "",
        "记录本确定性节点的执行结果，作为阶段卡详情页的可点击入口与证据归档。",
        "",
        "## 背景",
        "",
        background,
        "",
        "## 范围",
        "",
        "包含：",
        "- 本节点 Artifact 证据",
        "- 节点状态同步（完成 / 阻塞 / 取消）",
        "",
        "不包含：",
        *(f"- {item}" for item in scope_excludes),
        "",
        "## 输入材料",
        "",
        "- 上游已验收 Artifact",
        "",
        "## 验收",
        "",
        "- 详情页可点击本卡查看 Artifact 证据",
        "- 状态与本节点一致",
        "",
        "## 产出",
        "",
        artifact_line,
    ]
    if approval_block:
        lines.extend(
            [
                "",
                "## 你需要处理",
                "",
                *approval_block,
            ]
        )
    return "\n".join(lines)


def human_correction_title(request: Mapping[str, Any]) -> str:
    count = len(request.get("directives") or [])
    return f"【人工修正】测试设计（A08）· {count} 个问题待授权"


def _first_plain_sentence(text: str) -> str:
    for separator in ("。", "；", "\n", ". "):
        position = text.find(separator)
        if position > 0:
            return text[: position + len(separator)]
    return text


def human_correction_description(request: Mapping[str, Any]) -> str:
    directives = request.get("directives") or []
    upstream = request.get("upstream_artifacts") or []
    budget = request.get("budget") or {}
    directive_lines: list[str] = []
    for index, item in enumerate(directives, start=1):
        headline = str(item.get("human_title") or "").strip() or _HUMAN_ISSUE_TITLES.get(
            str(item.get("issue_code") or ""), "测试设计问题"
        )
        severity = str(item.get("severity") or "error")
        directive_lines.append(f"{index}. **{headline}**（`{item['directive_id']}` · {severity}）")
        plain = str(item.get("plain_summary") or "").strip()
        problem = plain or _first_plain_sentence(str(item.get("message") or ""))
        if problem:
            directive_lines.append(f"   - 问题：{problem}")
        if item.get("recommendation"):
            directive_lines.append(f"   - 修正方案：{item['recommendation']}")
        if item.get("case_id"):
            directive_lines.append(f"   - 涉及用例：`{item['case_id']}`")
        if item.get("expected_id"):
            directive_lines.append(f"   - 期望项：`{item['expected_id']}`")
    return "\n".join(
        [
            "# 测试设计人工修正",
            "",
            "## 目标",
            "",
            f"决定是否授权修正测试设计中的 {len(directives)} 个问题；授权后系统自动生成新的 A08 修正版并重新校验。",
            "",
            "## 背景",
            "",
            f"工作流 `{request.get('workflow_run_id')}` 的 A08 测试设计、A09 Oracle 审查与 N04 校验后仍有 {len(directives)} 个阻塞问题；"
            f"自动修正预算（第 {budget.get('correction_attempt', '-')}/{budget.get('max_correction_attempts', '-')} 轮）已耗尽，需要人工授权。",
            "",
            "## 范围",
            "",
            "包含：",
            "- 仅修正下方“本次授权明细”列出的问题（Test Case IR 期望值与测试数据）。",
            "",
            "不包含：",
            "- 修改冻结需求/技术方案、其他用例、业务代码或发布。",
            "",
            "## 输入材料",
            "",
            *(f"- {item.get('artifact_id')}：`{item.get('artifact_hash')}`" for item in upstream),
            "- 本 Issue 附件：`human-correction-request.json`（完整修正指令与追溯信息）",
            "",
            "## 本次授权明细",
            "",
            *directive_lines,
            "",
            "## 验收",
            "",
            "- 置 **done**：授权全部修正，系统自动生成 A08 修正版并重新校验，通过后推进 G02。",
            "- 置 **cancelled**：不修正，终止当前流程。",
            "- 保持 **in_review**：流程保持暂停。",
            "",
        ]
    )


def scope_review_title(request: Mapping[str, Any]) -> str:
    return (
        f"[{request.get('workflow_run_id', '')}] G01 范围与口径审核 · "
        f"{request.get('issue_count', 0)} 项待确认"
    )


def g02_review_title(request: Mapping[str, Any]) -> str:
    summary = request.get("review_summary") or {}
    return (
        f"[{request.get('workflow_run_id', '')}] G02 测试用例审核 · "
        f"待审核 {summary.get('parent_case_count', 0)} 条用例"
    )


def g02_review_description(request: Mapping[str, Any]) -> str:
    summary = request["review_summary"]
    upstream = "\n".join(
        f"- `{item['artifact_id']}`：`{item['artifact_hash']}`"
        for item in request["upstream_artifacts"]
    )
    body = "\n".join(
        [
            "# 测试用例审核",
            "",
            "## 目标",
            "",
            f"确认 {summary['parent_case_count']} 条父用例的预期结果与覆盖可直接执行；批准后进入 N25 父子 Case 编译。",
            "",
            "## 背景",
            "",
            f"N04 校验已通过（阻塞问题 {summary['blocking_issue_count']} 个），A08 测试设计与 A09 Oracle 审查已完成。",
            "",
            "## 范围",
            "",
            "包含：",
            f"- {summary['parent_case_count']} 条父用例的预期结果、覆盖与来源引用。",
            "",
            "不包含：",
            "- 修改用例本身；需要修改时置 blocked 回流 A08。",
            "",
            "## 输入材料",
            "",
            upstream,
            "- 本 Issue 附件：`g02-review-request.json`",
            "",
            "## 你需要审核什么",
            "",
            f"- 每条用例的预期结果是否可执行、覆盖是否满足冻结规则（warning {summary['warning_count']} 个）。",
            f"- N04 结论（n04_valid={summary['n04_valid']}）与 A09 覆盖结论是否一致。",
            "",
            "## 怎么反馈",
            "",
            "这是交付评审，不是审批仪式：",
            "",
            "- 发现缺场景 / 预期不可执行 / 覆盖不够：**在评论里逐条写明缺什么**，然后置 **blocked**。",
            "- 评论内容会被作为 A08 的修正指令回流：A08 按评论修复 → A09 复审 → N04 重新校验 → 重新生成用例卡片给你。",
            "- 没有缺项：置 **done** 进入 N25 Case 编译。",
            "- 保持 **in_review**：流程保持暂停。",
            "",
            "## 验收",
            "",
            "- 置 **done**：用例无缺项，继续 N25。",
            "- 置 **blocked**（必须带评论）：回流 A08 按评论修正。",
            "- 置 **cancelled**：终止当前流程。",
            "",
        ]
    )
    review_items = request.get("review_items")
    if isinstance(review_items, list) and review_items:
        lines = ["", "## 待审核用例明细", ""]
        for index, item in enumerate(review_items, start=1):
            if not isinstance(item, Mapping):
                continue
            lines.append(render_review_card(item, index=index))
            lines.append("")
        body = body + "\n".join(lines)
    return body


def g03_review_title(request: Mapping[str, Any]) -> str:
    summary = request.get("summary") or {}
    return (
        f"[{request.get('workflow_run_id', '')}] G03 自动化代码审核 · "
        f"待审核 {summary.get('candidate_count', 0)} 个候选"
    )


def g03_review_description(request: Mapping[str, Any]) -> str:
    summary = request["summary"]
    upstream = "\n".join(
        f"- `{item['artifact_id']}`：`{item['artifact_hash']}`"
        for item in request["upstream_artifacts"]
    )
    items = []
    for item in request.get("issue_items", []):
        if "generator_id" in item:
            items.append(
                f"- `{item['generator_id']}` 生成 `{item['candidate_count']}` 个候选"
                f"（Manifest `{item.get('manifest_id') or '—'}`，拒绝 `{item['rejected_count']}`）"
            )
        else:
            items.append(
                f"- `{item['reviewer_id']}` 复核结论 approved="
                f"{item.get('approved')}，问题 `{item['issue_count']}` 个"
            )
    issue_lines = "\n".join(items) if items else "- 无生成与复核明细"
    lines = [
        "# 自动化代码审核",
        "",
        "**目标**",
        "",
        "确认 A14/A15 生成的自动化候选、独立复核结论与 N05 确定性代码检查结果一致，"
        "批准后进入 N08 受控自动化执行。",
        "",
        "**背景**",
        "",
        f"N05 确定性代码检查已通过（生成 `{summary['generation_count']}` 个、"
        f"候选 `{summary['candidate_count']}` 个、复核问题 `{summary['review_issue_count']}` 个）。",
        "",
        "**范围**",
        "",
        "包含：",
        f"- {summary['candidate_count']} 个自动化候选的 Manifest、候选代码与安全红线。",
        "- A18-BE / A18-CT 独立复核结论与阻塞问题。",
        "",
        "不包含：",
        "- 修改候选代码本身；需要修改时置 blocked 回流对应生成/复核节点。",
        "",
        "**输入材料**",
        "",
        upstream,
        "- 本 Issue 附件：`g03-review-request.json`",
        "",
        "**本批生成与复核明细**",
        "",
        issue_lines,
        "",
    ]
    case_lines = _render_generation_cases(request.get("generation_cases", []))
    if case_lines:
        lines.extend(
            [
                "**本批候选覆盖 Case**",
                "",
                *case_lines,
                "",
            ]
        )
    lines.extend(
        [
            "**怎么反馈**",
            "",
            "这是交付评审，不是审批仪式：",
            "",
            "- 发现候选不安全 / Manifest 绑定错误 / 复核结论不一致：**在评论里逐条写明问题**，然后置 **blocked**。",
            "- 评论内容会被作为修正指令回流：A14/A15 修正候选 → A18 复核 → N05 重新检查 → 重新生成审核卡给你。",
            "- 没有问题：置 **done** 进入 N08 受控自动化执行。",
            "- 保持 **in_review**：流程保持暂停。",
            "",
            "**验收**",
            "",
            "- 置 **done**：候选与复核结论一致，继续 N08。",
            "- 置 **blocked**（必须带评论）：回流生成/复核节点修正。",
            "- 置 **cancelled**：终止当前流程。",
            "",
        ]
    )
    return "\n".join(lines)



def _render_generation_cases(cases: list) -> list[str]:
    """Render one line per covered Case so the reviewer can approve the actual scope."""

    lines: list[str] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id", ""))
        if not case_id:
            continue
        title = str(case.get("title", "")).strip()
        meta = " / ".join(
            value
            for value in (str(case.get("risk", "")), str(case.get("priority", "")))
            if value
        )
        heading = f"{index}. `{case_id}`"
        if title:
            heading += f" {title}"
        if meta:
            heading += f"（{meta}）"
        lines.append(heading)
        path = str(case.get("candidate_path", "")).strip()
        if path:
            lines.append(f"   - 候选文件：`{path}`")
        expected_ids = [
            str(item) for item in case.get("expected_ids", []) if isinstance(item, str) and item
        ]
        manual_ids = [
            str(item)
            for item in case.get("manual_expected_ids", [])
            if isinstance(item, str) and item
        ]
        if expected_ids:
            lines.append(f"   - 覆盖预期：{'、'.join(expected_ids)}")
        if manual_ids:
            lines.append(f"   - 人工确认项：{'、'.join(manual_ids)}")
    return lines
