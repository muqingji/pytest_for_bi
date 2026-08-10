"""Conservative built-in Phase 1 Agent Profiles.

These profiles provide a deterministic local baseline. A production model adapter may
replace their semantic extraction, but it must return the same versioned contracts.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any

from .base import AgentOutput, BaseAgent
from ..contracts import ArtifactStatus, EvidenceRef


MARKDOWN_PREFIX = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]+|[\u4e00-\u9fff]{2,}")
ALIGNMENT_STOP_TOKENS = {
    "使用",
    "需要",
    "查看",
    "明细",
    "提示",
    "支持",
    "数据",
    "统计",
    "指标",
    "场景",
    "当前",
}


def _statements(text: str) -> list[str]:
    values: list[str] = []
    paragraph: list[str] = []
    in_code = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            if paragraph:
                values.append(" ".join(paragraph))
                paragraph = []
            continue
        if line.startswith("#"):
            continue
        if MARKDOWN_PREFIX.match(line):
            values.append(MARKDOWN_PREFIX.sub("", line).strip())
        elif len(line) >= 12:
            paragraph.append(line)
    if paragraph:
        values.append(" ".join(paragraph))
    unique: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _tokens(value: str) -> set[str]:
    tokens = {item.lower() for item in WORD.findall(value)}
    han = "".join(character for character in value if "\u4e00" <= character <= "\u9fff")
    tokens.update(han[index : index + 2] for index in range(max(0, len(han) - 1)))
    return tokens


def _deduplicate_statements(values: list[str]) -> list[str]:
    selected: list[str] = []
    for value in values:
        tokens = _tokens(value) - ALIGNMENT_STOP_TOKENS
        duplicate_index = None
        for index, existing in enumerate(selected):
            existing_tokens = _tokens(existing) - ALIGNMENT_STOP_TOKENS
            denominator = max(1, min(len(tokens), len(existing_tokens)))
            if len(tokens & existing_tokens) / denominator >= 0.65:
                duplicate_index = index
                break
        if duplicate_index is None:
            selected.append(value)
        elif len(value) > len(selected[duplicate_index]):
            selected[duplicate_index] = value
    return selected


def _source_ref(material: Mapping[str, Any], fallback: str) -> dict[str, str]:
    source = material.get("source_ref")
    if isinstance(source, Mapping):
        return {
            "type": str(source.get("type", "document")),
            "id": str(source.get("id", fallback)),
            "location": str(source.get("location", "unknown")),
        }
    return {"type": "document", "id": fallback, "location": "unknown"}


class WorkflowRouteAdvisorAgent(BaseAgent):
    """A01: suggest a workflow template only when N00 cannot route by rule.

    N00 remains the decision point; this Profile is advice-only and can never
    create or execute a route on its own.
    """

    agent_id = "A01"
    output_name = "workflow-route-advice"
    output_contract = "workflow-route-advice/1.0"
    runtime = "analysis-runtime"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        unresolved = list(inputs.get("unresolved_items", []))
        candidates = {str(item) for item in inputs.get("candidate_templates", [])}
        items: list[dict[str, Any]] = []
        recommended: str | None = None
        for item in unresolved:
            requested = str(item.get("requested_template", "") or "")
            if not requested or requested not in candidates:
                items.append(
                    {
                        **dict(item),
                        "recommendation": "needs_human",
                        "candidate_templates": sorted(candidates),
                    }
                )
                continue
            if recommended is None:
                recommended = requested
            items.append(
                {
                    **dict(item),
                    "recommendation": requested,
                    "candidate_templates": sorted(candidates),
                }
            )
        agreed = {i["recommendation"] for i in items if i["recommendation"] != "needs_human"}
        if len(agreed) > 1:
            recommended = None
            for item in items:
                if item["recommendation"] != "needs_human":
                    item["recommendation"] = "needs_human"
                    item["reason_code"] = "conflicting_template_advice"
        needs_human = any(i["recommendation"] == "needs_human" for i in items)
        return AgentOutput(
            payload={
                "schema_version": "workflow-route-advice/1.0",
                "recommended_template": recommended,
                "items": items,
                "advisor_authority": "advice_only",
            },
            status=ArtifactStatus.NEEDS_HUMAN if needs_human else ArtifactStatus.COMPLETED,
            reason_code="route_ambiguity" if needs_human else None,
        )


class RequirementAnalyzerAgent(BaseAgent):
    agent_id = "A02"
    output_name = "requirement-analysis"
    output_contract = "requirement-analysis/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        material = inputs.get("requirement", {})
        text = str(material.get("content", "")) if isinstance(material, Mapping) else ""
        source_ref = _source_ref(material, "requirement") if isinstance(material, Mapping) else _source_ref({}, "requirement")
        statements = _statements(text)
        title = str(inputs.get("workflow_input", {}).get("title", "")).strip()
        ignored_prefixes = ("背景和现状描述", "预期效果", "优化逻辑/交互说明")
        statements = [
            statement
            for statement in statements
            if statement.strip() != title and not statement.startswith(ignored_prefixes)
        ]
        statements = _deduplicate_statements(statements)
        gaps: list[dict[str, str]] = []
        if not statements:
            statements = [title or "未命名需求"]
            gaps.append(
                {
                    "issue_code": "requirement_content_missing",
                    "message": "Only the requirement title is available; detailed acceptance criteria are missing.",
                }
            )
        requirements = [
            {
                "id": f"REQ-{index:03d}",
                "summary": statement,
                "acceptance_criteria": [statement],
                "source_refs": [source_ref],
            }
            for index, statement in enumerate(statements, 1)
        ]
        status = ArtifactStatus.COMPLETED_WITH_GAPS if gaps else ArtifactStatus.COMPLETED
        return AgentOutput(
            payload={
                "schema_version": "requirement-analysis/1.0",
                "requirements": requirements,
                "ambiguities": gaps,
            },
            status=status,
            evidence_refs=[EvidenceRef(source_ref["type"], source_ref["id"], source_ref["location"])],
        )


class TechnicalTestabilityAgent(BaseAgent):
    agent_id = "A03"
    output_name = "technical-testability-analysis"
    output_contract = "technical-analysis/1.0"

    TESTABILITY_SIGNALS = {
        "observability": ("log", "trace", "metric", "日志", "监控", "埋点"),
        "controllability": ("api", "接口", "flag", "配置", "mock"),
        "data_setup": ("test data", "测试数据", "初始化", "fixture"),
        "cleanup": ("cleanup", "清理", "回滚", "reset"),
    }

    @staticmethod
    def _open_questions(text: str, source_ref: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Extract explicit acceptance questions from the technical design table."""

        lines = text.splitlines()
        section_start = None
        for index, line in enumerate(lines):
            if re.match(r"^##\s+待确认项\s*$", line.strip()):
                section_start = index + 1
                break
        if section_start is None:
            return []

        section: list[str] = []
        for line in lines[section_start:]:
            if re.match(r"^##\s+", line.strip()):
                break
            section.append(line)

        questions: list[dict[str, Any]] = []
        for line in section:
            stripped = line.strip()
            if not (stripped.startswith("|") and stripped.endswith("|")):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) < 4:
                continue
            if cells[0] == "问题" or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            questions.append(
                {
                    "id": f"OPEN-{len(questions) + 1:03d}",
                    "issue_code": "product_acceptance_open_question",
                    "summary": cells[0],
                    "recommendation": cells[1],
                    "owner": cells[2],
                    "start_condition": cells[3],
                    "source_refs": [dict(source_ref)],
                }
            )
        return questions

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        material = inputs.get("technical_design", {})
        text = str(material.get("content", "")) if isinstance(material, Mapping) else ""
        source_ref = _source_ref(material, "technical-design") if isinstance(material, Mapping) else _source_ref({}, "technical-design")
        statements = _statements(text)
        blocking_items = self._open_questions(text, source_ref)
        lowered = text.lower()
        testability = []
        missing = []
        for capability, signals in self.TESTABILITY_SIGNALS.items():
            present = any(signal.lower() in lowered for signal in signals)
            item = {"capability": capability, "status": "present" if present else "not_evidenced"}
            testability.append(item)
            if not present:
                missing.append(item)
        status = ArtifactStatus.COMPLETED if text else ArtifactStatus.COMPLETED_WITH_GAPS
        return AgentOutput(
            payload={
                "schema_version": "technical-analysis/1.0",
                "technical_facts": [
                    {"id": f"TECH-{index:03d}", "summary": statement, "source_refs": [source_ref]}
                    for index, statement in enumerate(statements, 1)
                ],
                "testability": testability,
                "testability_gaps": missing,
                "blocking_items": blocking_items,
            },
            status=status,
            evidence_refs=[EvidenceRef(source_ref["type"], source_ref["id"], source_ref["location"])],
        )


class ChangeAnalyzerAgent(BaseAgent):
    output_name = "change-analysis"
    output_contract = "change-analysis/1.0"

    def __init__(self, domain: str) -> None:
        if domain not in {"frontend", "backend"}:
            raise ValueError(f"Unsupported change domain: {domain}")
        self.domain = domain
        self.agent_id = "A04" if domain == "frontend" else "A05"
        self.output_name = f"{domain}-change-analysis"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        change_set = inputs.get("change_set", {})
        files = list(change_set.get("changed_files", []))
        diff_material = inputs.get("implementation_diff", {})
        diff_text = str(diff_material.get("content", "")) if isinstance(diff_material, Mapping) else ""
        facts = [
            {
                "id": f"CHANGE-{self.domain.upper()}-{index:03d}",
                "path": path,
                "change_set_id": change_set.get("change_set_id"),
                "summary": self._summarize_path_diff(path, diff_text),
                "evidence_class": self._evidence_class(path),
                "eligible_for_business_alignment": self._evidence_class(path) == "business_source",
                "source_refs": [
                    {
                        "type": "change_set",
                        "id": str(change_set.get("change_set_id", "unknown")),
                        "location": path,
                    }
                ],
            }
            for index, path in enumerate(files, 1)
        ]
        return AgentOutput(
            payload={
                "schema_version": "change-analysis/1.0",
                "domain": self.domain,
                "change_set_id": change_set.get("change_set_id"),
                "facts": facts,
                "changed_file_count": len(files),
            },
            evidence_refs=[
                EvidenceRef("change_set", str(change_set.get("change_set_id", "unknown")), "changed_files")
            ],
        )

    @staticmethod
    def _summarize_path_diff(path: str, diff_text: str) -> str:
        if not diff_text:
            return f"Changed file: {path}"
        marker = f"diff --git a/{path} b/{path}"
        start = diff_text.find(marker)
        if start < 0:
            return f"Changed file: {path}"
        next_file = diff_text.find("\ndiff --git ", start + len(marker))
        section = diff_text[start : next_file if next_file >= 0 else None]
        added = [
            line[1:].strip()
            for line in section.splitlines()
            if line.startswith("+") and not line.startswith("+++") and line[1:].strip()
        ]
        excerpt = " ".join(added[:8])
        return f"Changed file: {path}. Added evidence: {excerpt}" if excerpt else f"Changed file: {path}"

    @staticmethod
    def _evidence_class(path: str) -> str:
        lowered = path.lower()
        name = lowered.rsplit("/", 1)[-1]
        if name in {"agents.md", "readme.md"} or lowered.endswith((".md", ".txt")):
            return "untrusted_documentation"
        if "/src/test/" in f"/{lowered}" or lowered.startswith("test/") or "/tests/" in f"/{lowered}":
            return "test_source"
        return "business_source"


class AlignmentAgent(BaseAgent):
    agent_id = "A06"
    output_name = "alignment-result"
    output_contract = "alignment-result/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        requirements = inputs.get("requirement_analysis", {}).get("requirements", [])
        change_facts: list[Mapping[str, Any]] = []
        for key in ("frontend_change_analysis", "backend_change_analysis"):
            change_facts.extend(inputs.get(key, {}).get("facts", []))
        findings: list[dict[str, Any]] = []
        mappings: list[dict[str, Any]] = []
        for requirement in requirements:
            requirement_tokens = _tokens(str(requirement.get("summary", "")))
            matches = []
            for fact in change_facts:
                if not fact.get("eligible_for_business_alignment", False):
                    continue
                fact_text = f"{fact.get('path', '')} {fact.get('summary', '')}"
                shared_tokens = (
                    requirement_tokens & _tokens(fact_text)
                ) - ALIGNMENT_STOP_TOKENS
                if len(shared_tokens) >= 2:
                    matches.append(str(fact.get("id")))
            mappings.append(
                {
                    "requirement_id": requirement["id"],
                    "change_fact_ids": matches,
                    "status": "evidence_matched" if matches else "implementation_not_evidenced",
                }
            )
            if not matches:
                findings.append(
                    {
                        "id": f"ALIGN-{len(findings) + 1:03d}",
                        "severity": "medium",
                        "type": "implementation_evidence_gap",
                        "summary": f"No direct implementation evidence mapped to {requirement['id']}",
                        "requirement_ids": [requirement["id"]],
                        "implementation_ids": [],
                    }
                )
        return AgentOutput(
            payload={
                "schema_version": "alignment-result/1.0",
                "mappings": mappings,
                "findings": findings,
            },
            assumptions=[
                {
                    "message": "Path-level evidence cannot prove business implementation correctness.",
                    "requires_review": True,
                }
            ],
        )


class RiskAdvisorAgent(BaseAgent):
    agent_id = "A07"
    output_name = "risk-strategy-advice"
    output_contract = "risk-strategy-advice/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        unresolved = inputs.get("unresolved_items", [])
        return AgentOutput(
            payload={
                "schema_version": "risk-strategy-advice/1.0",
                "suggested_layers": [],
                "items": [
                    {**dict(item), "recommendation": "needs_human"} for item in unresolved
                ],
            },
            status=ArtifactStatus.NEEDS_HUMAN if unresolved else ArtifactStatus.NOT_APPLICABLE,
            reason_code="risk_policy_ambiguity" if unresolved else "risk_policy_is_deterministic",
        )


class TestDesignerAgent(BaseAgent):
    agent_id = "A08"
    output_name = "test-design-ir"
    runtime = "test-design-runtime"
    output_contract = "test-design-ir/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        requirements = inputs.get("requirement_analysis", {}).get("requirements", [])
        strategy = inputs.get("test_strategy", {})
        risk = str(strategy.get("risk_level", "medium"))
        priority = {"critical": "P0", "high": "P1", "medium": "P2", "low": "P3"}[risk]
        layers = list(strategy.get("required_layers", [])) or ["backend"]
        intents: list[dict[str, Any]] = []
        cases: list[dict[str, Any]] = []
        for index, requirement in enumerate(requirements, 1):
            intent_id = f"INTENT-{index:03d}"
            case_id = f"CASE-{index:03d}"
            source_refs = deepcopy(requirement.get("source_refs", []))
            statement = str(requirement.get("summary", ""))
            intents.append(
                {
                    "id": intent_id,
                    "objective": statement,
                    "risk": risk,
                    "required_layers": layers,
                    "source_refs": source_refs,
                }
            )
            cases.append(
                {
                    "id": case_id,
                    "parent_case_id": None,
                    "intent_ids": [intent_id],
                    "title": statement,
                    "layer": "scenario",
                    "required_layers": layers,
                    "risk": risk,
                    "priority": priority,
                    "source_refs": source_refs,
                    "preconditions": ["准备满足需求定义的测试环境和测试数据"],
                    "test_data": {},
                    "steps": ["按照需求描述执行场景"],
                    "expected": [
                        {
                            "id": "EXP-01",
                            "description": statement,
                            "oracle": {
                                "type": "human_review",
                                "observation_point": "structured_manual_result",
                                "matcher": "manual_confirmation",
                                "source_ref": f"{source_refs[0]['id']}:{source_refs[0]['location']}" if source_refs else "missing",
                            },
                        }
                    ],
                    "cleanup": [],
                    "execution_policy": {
                        "allowed_modes": ["manual"],
                        "required_evidence": ["structured_manual_result"],
                    },
                    "automation_candidate": False,
                }
            )
        return AgentOutput(
            payload={
                "schema_version": "test-design-ir/1.0",
                "test_intents": intents,
                "parent_cases": cases,
                "provider_candidate_count": int(
                    inputs.get("case_provider_draft", {}).get("candidate_count", 0)
                ),
                "provider_status": inputs.get("case_provider_draft", {}).get(
                    "provider_status", "compatible"
                ),
                "coverage_matrix": [
                    {"requirement_id": req["id"], "case_ids": [f"CASE-{index:03d}"]}
                    for index, req in enumerate(requirements, 1)
                ],
            },
            status=ArtifactStatus.COMPLETED_WITH_GAPS,
            assumptions=[
                {
                    "message": "Built-in baseline keeps ambiguous outcomes manual until a model or rule supplies an executable Oracle.",
                    "requires_review": True,
                }
            ],
        )


class TestCoverageAgent(BaseAgent):
    agent_id = "A09"
    output_name = "oracle-coverage-review"
    runtime = "coverage-review-runtime"
    output_contract = "oracle-review/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        design = inputs.get("test_design", {})
        requirements = inputs.get("requirement_analysis", {}).get("requirements", [])
        cases = design.get("parent_cases", [])
        covered = {
            requirement_id
            for item in design.get("coverage_matrix", [])
            for requirement_id in [item.get("requirement_id")]
            if item.get("case_ids")
        }
        issues = []
        for requirement in requirements:
            if requirement["id"] not in covered:
                issues.append(
                    {
                        "issue_code": "requirement_not_covered",
                        "requirement_id": requirement["id"],
                        "route_to": "A08",
                    }
                )
        manual_count = sum(
            1
            for case in cases
            for expected in case.get("expected", [])
            if expected.get("oracle", {}).get("matcher") == "manual_confirmation"
        )
        return AgentOutput(
            payload={
                "schema_version": "oracle-review/1.0",
                "approved": not issues,
                "issues": issues,
                "manual_oracle_count": manual_count,
                "code_coverage_reviewed": False,
                "evaluation_oracle_accessed": False,
            },
            status=ArtifactStatus.COMPLETED_WITH_GAPS if manual_count else ArtifactStatus.COMPLETED,
        )


class SplitCoverageAgent(BaseAgent):
    agent_id = "A11"
    output_name = "split-coverage-review"
    runtime = "coverage-review-runtime"
    output_contract = "split-review/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        parents = {case["id"]: case for case in inputs.get("parent_cases", [])}
        children = inputs.get("child_cases", [])
        issues = []
        for child in children:
            parent = parents.get(child.get("parent_case_id"))
            if parent is None:
                issues.append({"issue_code": "parent_missing", "case_id": child.get("id")})
                continue
            parent_expected = {item["id"] for item in parent.get("expected", [])}
            child_expected = {item["id"] for item in child.get("expected", [])}
            if parent_expected != child_expected:
                issues.append({"issue_code": "oracle_changed_during_compile", "case_id": child.get("id")})
        return AgentOutput(
            payload={"schema_version": "split-review/1.0", "approved": not issues, "issues": issues},
            status=ArtifactStatus.COMPLETED if not issues else ArtifactStatus.NEEDS_HUMAN,
        )


class TestSelectionAdvisorAgent(BaseAgent):
    agent_id = "A12"
    output_name = "test-selection-advice"
    runtime = "test-design-runtime"
    output_contract = "test-selection-advice/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        unresolved = inputs.get("unresolved_items", [])
        case_index = inputs.get("compiled_case_index", {})
        asset_evidence = inputs.get("asset_evidence", {})
        if not isinstance(unresolved, list) or not unresolved:
            return AgentOutput(
                payload={
                    "schema_version": "test-selection-advice/1.0",
                    "advice_items": [],
                    "uncertainty_notes": ["N26 选择已确定，无需 A12 建议。"],
                },
                status=ArtifactStatus.NOT_APPLICABLE,
                reason_code="selection_is_deterministic",
            )
        items: list[dict[str, Any]] = []
        notes: list[str] = []
        for index, item in enumerate(unresolved, 1):
            if not isinstance(item, Mapping):
                continue
            topic = str(item.get("advisory_topic", ""))
            case_id = str(item.get("case_id", ""))
            if topic in {"missing_call_graph", "cross_repo_impact_conflict"}:
                related = self._related_cases(case_id, case_index, asset_evidence)
                if related:
                    recommendation = "expand_selection"
                    notes.append(
                        f"{case_id} 影响关系不确定，保守扩大到 {', '.join(related)}。"
                    )
                else:
                    recommendation = "request_human"
                    notes.append(f"{case_id} 影响关系不确定且无相关 Case，升级人工。")
            else:
                recommendation = "request_human"
                notes.append(f"{case_id} 资产映射不确定，升级人工确认。")
            items.append(
                {
                    "id": f"A12-{index:03d}",
                    "unresolved_item_id": str(item.get("id", "")),
                    "case_id": case_id,
                    "advisory_topic": topic,
                    "recommendation": recommendation,
                    "suggested_case_ids": related if recommendation == "expand_selection" else [],
                    "evidence": list(item.get("evidence", [])),
                    "uncertainty": str(item.get("uncertainty", "")),
                    "source_refs": [f"unresolved:{item.get('id', '')}"],
                }
            )
        return AgentOutput(
            payload={
                "schema_version": "test-selection-advice/1.0",
                "advice_items": items,
                "uncertainty_notes": notes,
            },
            status=ArtifactStatus.COMPLETED if items else ArtifactStatus.NOT_APPLICABLE,
            reason_code="selection_advice_provided" if items else "selection_is_deterministic",
        )

    @staticmethod
    def _related_cases(
        case_id: str,
        case_index: Mapping[str, Any],
        asset_evidence: Mapping[str, Any],
    ) -> list[str]:
        if not isinstance(case_index, Mapping):
            return []
        current = case_index.get(case_id, {})
        current_layer = str(current.get("layer", "")) if isinstance(current, Mapping) else ""
        impact_index = asset_evidence.get("impact_index", {})
        if isinstance(impact_index, Mapping):
            by_module: list[str] = []
            current_modules = (
                set(current.get("evidence_modules", []))
                if isinstance(current, Mapping)
                else set()
            )
            for module, case_ids in impact_index.items():
                if current_modules and module not in current_modules:
                    continue
                if isinstance(case_ids, list):
                    by_module.extend(str(cid) for cid in case_ids if str(cid) != case_id)
            if by_module:
                return sorted(set(by_module))
        related: list[str] = []
        for candidate_id, candidate in case_index.items():
            if str(candidate_id) == case_id:
                continue
            if isinstance(candidate, Mapping) and str(candidate.get("layer", "")) == current_layer:
                related.append(str(candidate_id))
        return sorted(related)
