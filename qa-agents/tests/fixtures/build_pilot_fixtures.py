"""Build the hermetic pilot fixture tree under ``tests/fixtures/pilot``.

The real frozen upstream Artifacts (stage1-3, G01, multica-inputs) come from a
live Multica pilot run and are not tracked by git (``qa-agents/runs/`` is
ignored).  This script copies them into the committed fixture tree and then
deterministically regenerates the round-1 and round-2 A08/A09/N04 chains, the
automatic correction input, and the human-directed recovery input that the test
suite asserts against.

Regeneration is byte-stable: every generated Artifact Envelope pins
``created_at`` to a fixed timestamp, and the review request/decision files are
idempotent once written.

Usage::

    PYTHONPATH=src python3 tests/fixtures/build_pilot_fixtures.py

The committed fixture tree is the test source of truth; ``qa-agents/runs/`` is
only needed when you want to re-baseline from a newer live pilot run.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from qa_agents.contracts import (
    ArtifactEnvelope,
    ArtifactStatus,
    EvidenceRef,
    Producer,
    artifact_hash_from_mapping,
)
from qa_agents.human_correction import (
    prepare_human_correction_request,
    sync_multica_human_correction,
)
from qa_agents.multica import prepare_multica_test_design_correction_input
from qa_agents.storage import ArtifactStore
from qa_agents.validation import validate_test_case_ir


ROOT = Path(__file__).resolve().parents[2]
SOURCE_RUN = ROOT / "runs" / "pilot-001"
FIXTURE_RUN = ROOT / "tests" / "fixtures" / "pilot"
POLICY = ROOT / "policies"

WORKFLOW_RUN_ID = "multica-pilot-001"
WORKFLOW_MODE = "new_requirement"
SOURCE_SNAPSHOT_ID = "pilot-001-source-v1"
FIXED_CREATED_AT = "2026-08-07T00:00:00+00:00"

WORKSPACE_ID = "457d700f-6c27-4a59-871d-c2c56bca9f46"
PROJECT_ID = "c2c84f1f-20af-456d-9eca-c9fbbd253840"
MEMBER_ID = "c2c6b9c6-4fb9-4439-a4a5-de4e93784c54"

N04_RECOMMENDATIONS = {
    "invalid_test_data_type": "将 test_data 改为结构化对象，并保留数据集和变体字段。",
    "missing_execution_modes": "在 execution_policy.allowed_modes 中声明 automated 或 manual。",
    "oracle_required_field": "补齐 Oracle 的 type、observation_point、matcher 和单值 source_ref。",
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_artifact(output: Path, artifact: ArtifactEnvelope) -> None:
    ArtifactStore(output).write_artifact(artifact)


def round1_case(index: int) -> dict[str, Any]:
    """Round-1 parent Case that deterministically triggers the three N04 codes."""
    return {
        "id": f"CASE-{index:03d}",
        "title": f"第一轮父 Case {index}：查看明细提示",
        "intent_ids": [f"INTENT-{index:03d}"],
        "layer": "scenario",
        "required_layers": ["backend", "contract", "e2e"],
        "risk": "critical",
        "priority": "P0",
        "source_refs": ["REQ-001"],
        "preconditions": ["准备目标场景数据"],
        "test_data": "raw-string-data",
        "steps": ["调用查看明细接口"],
        "expected": [
            {
                "id": f"EXP-{index:03d}-1",
                "description": "返回当前语言提示",
                "oracle": {"type": "deterministic"},
            },
            {
                "id": f"EXP-{index:03d}-2",
                "description": "返回单值指标",
                "oracle": {"matcher": "exact"},
            },
        ],
        "cleanup": [],
        "execution_policy": {"allowed_modes": []},
        "automation_candidate": True,
    }


def valid_case(index: int) -> dict[str, Any]:
    """Round-2 parent Case shaped like the accepted corrected design."""
    return {
        "id": f"CASE-{index:03d}",
        "title": f"人工修正后父 Case {index}",
        "intent_ids": [f"INTENT-{index:03d}"],
        "layer": "scenario",
        "required_layers": ["backend", "contract", "e2e"],
        "risk": "critical",
        "priority": "P0",
        "source_refs": ["REQ-001"],
        "preconditions": ["准备目标场景数据"],
        "test_data": {"dataset": ["zh-CN", "en"], "scenario": ["detail"]},
        "steps": ["调用查看明细接口"],
        "expected": [
            {
                "id": f"EXP-{index:03d}-1",
                "description": "返回冻结的当前语言提示",
                "oracle": {
                    "type": "deterministic",
                    "observation_point": "response.message",
                    "matcher": "template_equals",
                    "source_ref": "G01:test_rules.localization",
                },
            }
        ],
        "cleanup": [],
        "execution_policy": {"allowed_modes": ["automated"]},
        "automation_candidate": True,
    }


def n04_issue_from_validation(issue: Any, case_sources: Mapping[str, list[str]], index: int) -> dict[str, Any]:
    value = issue.to_dict()
    value.update(
        {
            "id": f"N04-{index:04d}",
            "category": "schema"
            if issue.issue_code
            in {
                "case_required_field",
                "duplicate_case_id",
                "duplicate_expected_id",
                "invalid_test_data_type",
                "invalid_execution_policy_type",
                "missing_execution_modes",
            }
            else "oracle",
            "source_refs": case_sources.get(issue.case_id or "", []),
            "recommendation": N04_RECOMMENDATIONS.get(
                issue.issue_code,
                "按正式 Test Case IR 契约定向修正后重新运行 A09/N04。",
            ),
            "origin": "N04",
        }
    )
    return value


def build_round1_chain(a08_input: Mapping[str, Any]) -> dict[str, str]:
    """Generate stage4 (A08), stage5 (A09) and stage6 (N04) and return hashes."""
    payload = {
        "schema_version": "test-design-ir/1.1",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "input_bundle_hash": a08_input["bundle_hash"],
        "status": "completed",
        "test_intents": [
            {
                "id": f"INTENT-{index:03d}",
                "objective": f"验证第一轮父意图 {index}",
                "risk": "critical",
                "required_layers": ["backend", "contract", "e2e"],
                "source_refs": ["REQ-001"],
            }
            for index in range(1, 11)
        ],
        "parent_cases": [round1_case(index) for index in range(1, 11)],
        "coverage_matrix": [
            {"requirement_id": "REQ-001", "case_ids": [f"CASE-{index:03d}" for index in range(1, 11)]}
        ],
        "test_rule_coverage": [
            {"rule_id": item["id"], "case_ids": ["CASE-001"]}
            for item in a08_input["allowed_inputs"]["approved_scope"]["test_rule_obligations"]
        ],
    }
    design = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="a08-test-design-ir",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(
            component_id="A08",
            runtime="multica",
            profile_version="1.1.1",
            model_provider="codex",
            model_snapshot="gpt-5.6-sol",
            prompt_version="1.1.1",
        ),
        payload=payload,
        status=ArtifactStatus.COMPLETED,
        created_at=FIXED_CREATED_AT,
        evidence_refs=(
            EvidenceRef(
                source_type="multica_agent_input",
                source_id="A08",
                location="a08-input.json",
                content_hash=a08_input["bundle_hash"],
            ),
        ),
        facts=(
            {
                "type": "multica_tool_trace_audit",
                "result": "not_available",
                "task_id": "3e91044f-9b07-4d0c-a83c-f6ee60739d34",
                "issue_id": "frozen-issue",
                "attachment_id": "frozen-attachment",
                "commands": [],
            },
        ),
    )
    stage4 = FIXTURE_RUN / "multica-stage4"
    write_artifact(stage4, design)
    design_dict = design.to_dict()

    review_issues = [
        {
            "id": f"A09-{index:03d}",
            "issue_code": "ORACLE_REQUIRED_FIELDS_MISSING",
            "severity": "error",
            "category": "oracle",
            "message": f"Oracle 缺少 type 与 source_ref（第一轮第 {index} 项）",
            "path": f"parent_cases[0].expected[{index - 1}].oracle",
            "route_to": "A08",
            "case_id": "CASE-001",
            "expected_id": "EXP-001-1",
            "source_refs": ["REQ-001"],
            "recommendation": "补齐 Oracle 的 type、observation_point、matcher 和单值 source_ref。",
        }
        for index in range(1, 23)
    ]
    requirements = a08_input["allowed_inputs"]["validated_analysis"]["requirement_analysis"]["requirements"]
    obligations = a08_input["allowed_inputs"]["approved_scope"]["test_rule_obligations"]
    review_payload = {
        "schema_version": "oracle-review/1.1",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "input_bundle_hash": a08_input["bundle_hash"],
        "status": "needs_human",
        "approved": False,
        "issues": review_issues,
        "coverage_dimensions": [
            {
                "dimension": item,
                "status": "gap",
                "case_ids": ["CASE-001"],
                "source_refs": ["CASE-001"],
                "rationale": "第一轮 A09 覆盖率不足",
            }
            for item in ("deterministic", "human_review", "negative", "localization", "authorization")
        ],
        "requirement_coverage": [
            {"requirement_id": item["id"], "status": "covered", "case_ids": ["CASE-001"]}
            for item in requirements
        ],
        "test_rule_coverage": [
            {"rule_id": item["id"], "status": "covered", "case_ids": ["CASE-001"]}
            for item in obligations
        ],
        "manual_case_recommendations": [],
        "code_coverage_reviewed": False,
        "evaluation_oracle_accessed": False,
    }
    review = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="a09-oracle-coverage-review",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(
            component_id="A09",
            runtime="multica",
            profile_version="1.1.0",
            model_provider="codex",
            model_snapshot="gpt-5.6-sol",
            prompt_version="1.1.0",
        ),
        payload=review_payload,
        status=ArtifactStatus.NEEDS_HUMAN,
        created_at=FIXED_CREATED_AT,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a08-test-design-ir",
                location="a08-test-design-ir.json",
                content_hash=design_dict["artifact_hash"],
            ),
        ),
        reason_code="oracle_coverage_gaps",
    )
    stage5 = FIXTURE_RUN / "multica-stage5"
    write_artifact(stage5, review)
    review_dict = review.to_dict()

    case_sources = {
        str(case.get("id")): list(case.get("source_refs", []))
        for case in payload["parent_cases"]
    }
    n04_issues = [
        n04_issue_from_validation(issue, case_sources, index)
        for index, issue in enumerate(
            validate_test_case_ir(payload["parent_cases"]), 1
        )
    ]
    n04_payload = {
        "schema_version": "test-case-ir-validation/1.0",
        "valid": False,
        "test_design_artifact_id": "a08-test-design-ir",
        "test_design_artifact_hash": design_dict["artifact_hash"],
        "oracle_review_artifact_id": "a09-oracle-coverage-review",
        "oracle_review_artifact_hash": review_dict["artifact_hash"],
        "issues": n04_issues,
        "issue_count": len(n04_issues),
        "blocking_issue_count": len(n04_issues),
        "route_summary": {"A08": len(n04_issues)},
        "correction_attempt": 1,
        "max_correction_attempts": 2,
        "next_node": "A08",
        "g02_status": "not_started",
    }
    n04 = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="n04-test-case-ir-validation",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(component_id="N04", runtime="deterministic"),
        payload=n04_payload,
        status=ArtifactStatus.NEEDS_HUMAN,
        created_at=FIXED_CREATED_AT,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a08-test-design-ir",
                location="a08-test-design-ir.json",
                content_hash=design_dict["artifact_hash"],
            ),
            EvidenceRef(
                source_type="artifact",
                source_id="a09-oracle-coverage-review",
                location="a09-oracle-coverage-review.json",
                content_hash=review_dict["artifact_hash"],
            ),
        ),
        reason_code="test_case_ir_requires_correction",
    )
    stage6 = FIXTURE_RUN / "multica-stage6"
    write_artifact(stage6, n04)
    return {
        "design4": design_dict["artifact_hash"],
        "review5": review_dict["artifact_hash"],
        "n046": n04.to_dict()["artifact_hash"],
    }


def build_round2_chain(correction_bundle: Mapping[str, Any]) -> dict[str, str]:
    """Generate stage7 (A08), stage8 (A09) and stage9 (N04) and return hashes."""
    payload = {
        "schema_version": "test-design-ir/1.1",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "input_bundle_hash": correction_bundle["bundle_hash"],
        "status": "completed",
        "test_intents": [
            {
                "id": f"INTENT-{index:03d}",
                "objective": f"验证人工修正后父意图 {index}",
                "risk": "critical",
                "required_layers": ["backend", "contract", "e2e"],
                "source_refs": ["REQ-001"],
            }
            for index in range(1, 14)
        ],
        "parent_cases": [valid_case(index) for index in range(1, 14)],
        "coverage_matrix": [
            {"requirement_id": "REQ-001", "case_ids": [f"CASE-{index:03d}" for index in range(1, 14)]}
        ],
        "test_rule_coverage": [
            {"rule_id": item["id"], "case_ids": ["CASE-001"]}
            for item in correction_bundle["allowed_inputs"]["approved_scope"]["test_rule_obligations"]
        ],
    }
    design = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="a08-test-design-ir",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(
            component_id="A08",
            runtime="multica",
            profile_version="1.2.1",
            model_provider="codex",
            model_snapshot="gpt-5.6-sol",
            prompt_version="1.2.1",
        ),
        payload=payload,
        status=ArtifactStatus.COMPLETED,
        created_at=FIXED_CREATED_AT,
        evidence_refs=(
            EvidenceRef(
                source_type="multica_agent_input",
                source_id="A08",
                location="a08-input.json",
                content_hash=correction_bundle["bundle_hash"],
            ),
        ),
    )
    stage7 = FIXTURE_RUN / "multica-stage7"
    write_artifact(stage7, design)
    design_dict = design.to_dict()

    directive_issues = [
        {
            "id": "A09-R001",
            "issue_code": "RESULT_SET_METRIC_PARAM_LOCALE",
            "severity": "error",
            "category": "oracle",
            "message": "结果集筛选的中英文指标名参数未按 locale 配对。",
            "path": "parent_cases[2].test_data.dataset",
            "route_to": "A08",
            "case_id": "CASE-003",
            "expected_id": "EXP-003-1",
            "source_refs": ["REQ-001"],
            "recommendation": "按 locale 配对 zh_CN/en 指标名参数。",
        },
        {
            "id": "A09-R002",
            "issue_code": "UNRESOLVED_EXPECTATION_REFERENCE",
            "severity": "error",
            "category": "oracle",
            "message": "期望引用不可解析。",
            "path": "parent_cases[4].expected[0].source_ref",
            "route_to": "A08",
            "case_id": "CASE-005",
            "expected_id": "EXP-005-1",
            "source_refs": ["REQ-001"],
            "recommendation": "将期望引用指向冻结证据中的精确位置。",
        },
        {
            "id": "A09-R003",
            "issue_code": "KEYLESS_LOCALIZED_SET_MATCH",
            "severity": "error",
            "category": "oracle",
            "message": "无键本地化集合匹配不可判定。",
            "path": "parent_cases[6].expected[0].oracle.matcher",
            "route_to": "A08",
            "case_id": "CASE-007",
            "expected_id": "EXP-007-1",
            "source_refs": ["REQ-001"],
            "recommendation": "为本地化集合匹配补充固定 key。",
        },
        {
            "id": "A09-R004",
            "issue_code": "COMPOSITE_ORACLE_SOURCE_SCOPE",
            "severity": "warning",
            "category": "oracle",
            "message": "复合 Oracle 来源范围过大。",
            "path": "parent_cases[8].expected[0].oracle.source_ref",
            "route_to": "A08",
            "case_id": "CASE-009",
            "expected_id": "EXP-009-1",
            "source_refs": ["REQ-001"],
            "recommendation": "收窄复合 Oracle 的来源范围。",
        },
    ]
    review_payload = {
        "schema_version": "oracle-review/1.1",
        "workflow_run_id": WORKFLOW_RUN_ID,
        "source_snapshot_id": SOURCE_SNAPSHOT_ID,
        "status": "needs_human",
        "approved": False,
        "issues": directive_issues,
        "coverage_dimensions": [
            {
                "dimension": item,
                "status": "covered",
                "case_ids": ["CASE-001"],
                "source_refs": ["CASE-001"],
                "rationale": "已覆盖",
            }
            for item in ("deterministic", "human_review", "negative", "localization", "authorization")
        ],
        "requirement_coverage": [
            {"requirement_id": item["id"], "status": "covered", "case_ids": ["CASE-001"]}
            for item in correction_bundle["allowed_inputs"]["validated_analysis"]["requirement_analysis"]["requirements"]
        ],
        "test_rule_coverage": [
            {"rule_id": item["id"], "status": "covered", "case_ids": ["CASE-001"]}
            for item in correction_bundle["allowed_inputs"]["approved_scope"]["test_rule_obligations"]
        ],
        "manual_case_recommendations": [],
        "code_coverage_reviewed": False,
        "evaluation_oracle_accessed": False,
    }
    review = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="a09-oracle-coverage-review",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(
            component_id="A09",
            runtime="multica",
            profile_version="1.1.1",
            model_provider="codex",
            model_snapshot="gpt-5.6-sol",
            prompt_version="1.1.1",
        ),
        payload=review_payload,
        status=ArtifactStatus.NEEDS_HUMAN,
        created_at=FIXED_CREATED_AT,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a08-test-design-ir",
                location="a08-test-design-ir.json",
                content_hash=design_dict["artifact_hash"],
            ),
        ),
        reason_code="oracle_coverage_gaps",
    )
    stage8 = FIXTURE_RUN / "multica-stage8"
    write_artifact(stage8, review)
    review_dict = review.to_dict()

    n04_issues = [
        {**dict(issue), "origin": "A09"} for issue in directive_issues
    ]
    n04_payload = {
        "schema_version": "test-case-ir-validation/1.0",
        "valid": False,
        "test_design_artifact_id": "a08-test-design-ir",
        "test_design_artifact_hash": design_dict["artifact_hash"],
        "oracle_review_artifact_id": "a09-oracle-coverage-review",
        "oracle_review_artifact_hash": review_dict["artifact_hash"],
        "issues": n04_issues,
        "issue_count": len(n04_issues),
        "blocking_issue_count": 3,
        "route_summary": {"A08": 4},
        "correction_attempt": 2,
        "max_correction_attempts": 2,
        "next_node": "human",
        "g02_status": "not_started",
    }
    n04 = ArtifactEnvelope(
        workflow_run_id=WORKFLOW_RUN_ID,
        workflow_mode=WORKFLOW_MODE,
        artifact_id="n04-test-case-ir-validation",
        source_snapshot_id=SOURCE_SNAPSHOT_ID,
        producer=Producer(component_id="N04", runtime="deterministic"),
        payload=n04_payload,
        status=ArtifactStatus.NEEDS_HUMAN,
        created_at=FIXED_CREATED_AT,
        evidence_refs=(
            EvidenceRef(
                source_type="artifact",
                source_id="a08-test-design-ir",
                location="a08-test-design-ir.json",
                content_hash=design_dict["artifact_hash"],
            ),
            EvidenceRef(
                source_type="artifact",
                source_id="a09-oracle-coverage-review",
                location="a09-oracle-coverage-review.json",
                content_hash=review_dict["artifact_hash"],
            ),
        ),
        reason_code="test_case_ir_correction_budget_exhausted",
    )
    stage9 = FIXTURE_RUN / "multica-stage9"
    write_artifact(stage9, n04)
    return {
        "design7": design_dict["artifact_hash"],
        "review8": review_dict["artifact_hash"],
        "n049": n04.to_dict()["artifact_hash"],
    }


class FakeMultica:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.issue = {
            "id": "human-correction-issue-1",
            "workspace_id": WORKSPACE_ID,
            "project_id": PROJECT_ID,
            "assignee_id": MEMBER_ID,
            "assignee_type": "member",
            "metadata": {},
            "status": "todo",
            "updated_at": "2026-08-10T10:00:00Z",
        }

    def __call__(self, args: list[str], cwd: Path) -> dict[str, Any]:
        if args[:2] == ["issue", "create"]:
            return dict(self.issue)
        if args[:3] == ["issue", "metadata", "set"]:
            self.issue["metadata"][args[args.index("--key") + 1]] = args[
                args.index("--value") + 1
            ]
            return {"ok": True}
        if args[:2] == ["issue", "status"]:
            self.issue["status"] = args[3]
            return dict(self.issue)
        if args[:2] == ["issue", "get"]:
            return json.loads(json.dumps(self.issue))
        raise AssertionError(args)


def main() -> None:
    if not SOURCE_RUN.exists():
        raise SystemExit(
            "runs/pilot-001 is missing; the fixtures already committed are the "
            "test source of truth and only need regeneration when re-baselining "
            "from a newer live pilot run."
        )
    FIXTURE_RUN.mkdir(parents=True, exist_ok=True)
    for name in (
        "multica-stage1",
        "multica-stage2",
        "multica-stage3",
        "g01",
        "multica-inputs",
        "multica-outputs",
    ):
        source = SOURCE_RUN / name
        target = FIXTURE_RUN / name
        if target.exists():
            shutil.rmtree(target)
        if source.exists():
            shutil.copytree(source, target)
        else:
            target.mkdir(parents=True, exist_ok=True)

    a08_input_path = FIXTURE_RUN / "multica-inputs" / "a08-input.json"
    a08_input = read_json(a08_input_path)

    hashes = build_round1_chain(a08_input)

    correction_input_dir = FIXTURE_RUN / "multica-inputs" / "a08-correction-01"
    prepare_multica_test_design_correction_input(
        FIXTURE_RUN / "multica-stage4" / "artifacts" / "a08-test-design-ir.json",
        a08_input_path,
        FIXTURE_RUN / "multica-stage5" / "artifacts" / "a09-oracle-coverage-review.json",
        FIXTURE_RUN / "multica-stage6" / "artifacts" / "n04-test-case-ir-validation.json",
        correction_input_dir,
    )
    correction_bundle = read_json(correction_input_dir / "a08-input.json")

    hashes.update(build_round2_chain(correction_bundle))

    stage7 = FIXTURE_RUN / "multica-stage7" / "artifacts" / "a08-test-design-ir.json"
    stage8 = FIXTURE_RUN / "multica-stage8" / "artifacts" / "a09-oracle-coverage-review.json"
    stage9 = FIXTURE_RUN / "multica-stage9" / "artifacts" / "n04-test-case-ir-validation.json"
    review_dir = FIXTURE_RUN / "human-correction"
    request = prepare_human_correction_request(
        stage7, stage8, stage9, POLICY / "human-correction-policy.json", review_dir
    )
    multica = FakeMultica()
    from qa_agents.human_correction import open_multica_human_correction

    open_multica_human_correction(
        review_dir / "human-correction-request.json",
        POLICY / "human-correction-policy.json",
        review_dir,
        runner=multica,
    )
    multica.issue["status"] = "done"
    multica.issue["updated_at"] = "2026-08-10T10:05:00Z"
    sync_multica_human_correction(
        review_dir / "human-correction-request.json",
        stage9,
        POLICY / "human-correction-policy.json",
        review_dir,
        runner=multica,
    )

    recovery_dir = FIXTURE_RUN / "multica-inputs" / "a08-human-correction-01"
    prepare_multica_test_design_correction_input(
        stage7,
        correction_input_dir / "a08-input.json",
        stage8,
        stage9,
        recovery_dir,
        human_correction_request_path=review_dir / "human-correction-request.json",
        human_correction_decision_path=review_dir / "human-correction-decision.json",
        human_correction_policy_path=POLICY / "human-correction-policy.json",
    )

    run_messages = [
        {
            "type": "tool_use",
            "tool": "exec_command",
            "task_id": "ef5825a9-71c1-4938-ba70-23939896fa9a",
            "issue_id": "1cd41070-3051-49bb-82e2-020e7f6281f4",
            "input": {
                "command": "/bin/zsh -lc 'cat a08-input.json > /tmp/qaa20-leak.json'"
            },
        },
        {
            "type": "text",
            "content": json.dumps(
                {
                    "status": "completed",
                    "test_intents": [],
                    "parent_cases": [],
                    "coverage_matrix": [],
                    "test_rule_coverage": [],
                },
                ensure_ascii=False,
            ),
        },
    ]
    output_dir = FIXTURE_RUN / "multica-outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "a08-human-correction-01-run-messages.json").write_text(
        json.dumps(run_messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("fixture hashes:")
    for key, value in sorted(hashes.items()):
        print(f"  {key}: {value}")
    print(f"fixtures written to {FIXTURE_RUN}")


if __name__ == "__main__":
    main()
