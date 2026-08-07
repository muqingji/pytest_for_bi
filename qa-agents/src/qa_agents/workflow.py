"""Local reference orchestration for the implemented QA workflow slices."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from .agents import (
    AlignmentAgent,
    BackendAutomationAgent,
    BackendAutomationReviewAgent,
    ChangeAnalyzerAgent,
    RequirementAnalyzerAgent,
    RiskAdvisorAgent,
    SplitCoverageAgent,
    TechnicalTestabilityAgent,
    TestCoverageAgent,
    TestDesignerAgent,
    TestSelectionAdvisorAgent,
)
from .agents.base import AgentContext
from .automation import AutomationPolicy, check_automation_generation
from .case_compiler import compile_cases
from .case_provider import CaseProviderAdapter
from .change_set import normalize_change_set
from .contracts import ArtifactEnvelope, ArtifactStatus, Producer, content_hash
from .errors import InputError, QaAgentError, SecurityPolicyError
from .gates import scope_gate_issues
from .model_runtime import StructuredModelRuntime
from .reporting import render_html, render_text
from .risk import RiskPolicyEngine
from .security import SecurityPolicy
from .selection import compile_execution_plan, select_cases
from .storage import ArtifactStore
from .validation import validate_artifact, validate_test_case_ir


@dataclass(frozen=True)
class WorkflowResult:
    workflow_run_id: str
    status: str
    stopped_at: str
    output_dir: Path
    summary: Mapping[str, Any]


class PhaseOneWorkflow:
    """Reference runner for N00 through G03 on implemented branches.

    Multica remains the production orchestrator. This runner makes contracts and routing
    executable locally and is intentionally unable to read evaluation Oracle files.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        model_runtime: StructuredModelRuntime | None = None,
    ) -> None:
        self.project_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
        self.security = SecurityPolicy()
        self.model_runtime = model_runtime
        self.risk_engine = RiskPolicyEngine.from_file(
            self.project_root / "policies" / "risk-policy.json"
        )
        self.automation_policy = AutomationPolicy.from_file(
            self.project_root / "policies" / "automation-target-policy.json"
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
        if not isinstance(value, dict):
            raise InputError(f"Expected JSON object: {path}")
        return value

    def run(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        run_id: str | None = None,
        stop_after: str | None = None,
        approve_g01: bool = False,
        approve_g02: bool = False,
        approve_g03: bool = False,
    ) -> WorkflowResult:
        input_dir = input_dir.resolve()
        self.security.assert_agent_paths([str(input_dir)])
        workflow_input = self._read_json(input_dir / "workflow-input.json")
        source_snapshot = self._read_json(input_dir / "source-snapshot.json")
        material_path = input_dir / "source-material.json"
        source_material = self._read_json(material_path) if material_path.exists() else {}
        asset_path = input_dir / "asset-catalog.json"
        asset_catalog = self._read_json(asset_path) if asset_path.exists() else {}
        provider_path = input_dir / "case-provider-output.json"
        provider_capability = source_material.get("case_provider_capability", {})
        if provider_path.exists():
            if provider_capability.get("status") != "compatible":
                raise SecurityPolicyError(
                    "Case Provider output cannot be consumed without a compatible frozen capability"
                )
            provider_draft = CaseProviderAdapter().adapt(
                self._read_json(provider_path),
                expected_commit=str(provider_capability.get("provider_commit", "")),
            )
        else:
            provider_draft = {
                "candidate_count": 0,
                "candidates": [],
                "provider_status": provider_capability.get("status", "not_probed"),
                "external_side_effects": False,
            }

        self.security.validate_workflow_input(workflow_input)
        self.security.validate_snapshot(source_snapshot)
        self.security.assert_no_secret_values(source_material)
        self.security.assert_no_secret_values(asset_catalog)
        self.security.assert_no_secret_values(provider_draft)
        workflow_run_id = run_id or datetime.now(timezone.utc).strftime("qa-%Y%m%dT%H%M%SZ")
        workflow_mode = str(workflow_input.get("workflow_mode", "new_requirement"))
        snapshot_id = str(source_snapshot.get("snapshot_id", ""))
        if not snapshot_id:
            raise InputError("source_snapshot.snapshot_id is required")
        requested_stop = stop_after or str(workflow_input.get("requested_stage_end", "N15"))
        store = ArtifactStore(output_dir)
        nodes: list[dict[str, Any]] = []
        validation_issues: list[dict[str, Any]] = []

        def save(artifact: ArtifactEnvelope) -> ArtifactEnvelope:
            store.write_artifact(artifact)
            nodes.append(
                {
                    "id": artifact.producer.component_id,
                    "artifact_id": artifact.artifact_id,
                    "status": artifact.status.value,
                    "reason_code": artifact.reason_code,
                    "artifact_hash": artifact.artifact_hash,
                }
            )
            return artifact

        def node_artifact(
            node_id: str,
            name: str,
            payload: Mapping[str, Any],
            status: ArtifactStatus = ArtifactStatus.COMPLETED,
            reason_code: str | None = None,
        ) -> ArtifactEnvelope:
            return ArtifactEnvelope(
                workflow_run_id=workflow_run_id,
                workflow_mode=workflow_mode,
                artifact_id=f"{node_id.lower()}-{name}",
                source_snapshot_id=snapshot_id,
                producer=Producer(component_id=node_id, runtime="deterministic-node"),
                payload=payload,
                status=status,
                reason_code=reason_code,
            )

        agent_input_paths = [
            str(input_dir / "workflow-input.json"),
            str(input_dir / "source-snapshot.json"),
        ]
        for optional_path in (material_path, asset_path, provider_path):
            if optional_path.exists():
                agent_input_paths.append(str(optional_path))
        context = AgentContext(
            workflow_run_id=workflow_run_id,
            workflow_mode=workflow_mode,
            source_snapshot_id=snapshot_id,
            input_paths=tuple(agent_input_paths),
        )

        try:
            applicability = workflow_input.get("component_applicability", {})
            route = {
                "schema_version": "workflow-route/1.0",
                "workflow_mode": workflow_mode,
                "route_source": "deterministic",
                "nodes": {
                    "A01": "skipped_by_policy",
                    "A04": "run" if applicability.get("frontend", {}).get("status") == "applicable" else "skipped_by_policy",
                    "A05": "run" if applicability.get("backend", {}).get("status") == "applicable" else "skipped_by_policy",
                },
            }
            save(node_artifact("N00", "workflow-route", route))
            save(
                node_artifact(
                    "A01",
                    "workflow-route-advice",
                    {},
                    ArtifactStatus.SKIPPED_BY_POLICY,
                    "route_is_deterministic",
                )
            )

            manifest_status = ArtifactStatus.COMPLETED if source_material else ArtifactStatus.COMPLETED_WITH_GAPS
            save(
                node_artifact(
                    "N01",
                    "source-extraction-manifest",
                    {
                        "schema_version": "source-extraction-manifest/1.0",
                        "files": ["workflow-input.json", "source-snapshot.json"]
                        + (["source-material.json"] if source_material else []),
                        "source_material_available": bool(source_material),
                        "case_provider_capability": provider_capability
                        or {"status": "not_probed"},
                        "oracle_available_to_agents": False,
                    },
                    manifest_status,
                    None if source_material else "source_material_missing",
                )
            )

            change_set = normalize_change_set(source_snapshot)
            collected_diff = source_material.get("implementation_diff", {})
            collection = source_material.get("collection", {})
            if collected_diff:
                expected_location = f"{change_set['base_commit']}..{change_set['head_commit']}"
                if collected_diff.get("source_ref", {}).get("location") != expected_location:
                    raise InputError("Collected diff range does not match the frozen ChangeSet")
                if collection.get("implementation_base") != change_set["base_commit"]:
                    raise InputError("Collected implementation base does not match ChangeSet")
                if collection.get("implementation_head") != change_set["head_commit"]:
                    raise InputError("Collected implementation head does not match ChangeSet")
                change_set["diff_hash"] = collected_diff["content_hash"]
            save(node_artifact("N02", "source-snapshot", {"change_set": change_set}))
            asset_snapshot = {
                "schema_version": "test-asset-snapshot/1.0",
                "catalog_snapshot_id": asset_catalog.get(
                    "catalog_snapshot_id", f"empty-{snapshot_id}"
                ),
                "automation_assets": asset_catalog.get("automation_assets", {}),
                "asset_count": len(asset_catalog.get("automation_assets", {})),
                "catalog_hash": content_hash(asset_catalog),
            }
            save(
                node_artifact(
                    "N14",
                    "test-asset-snapshot",
                    asset_snapshot,
                    ArtifactStatus.COMPLETED
                    if asset_catalog
                    else ArtifactStatus.COMPLETED_WITH_GAPS,
                    None if asset_catalog else "asset_catalog_not_provided",
                )
            )

            requirement_material = source_material.get("requirement", {})
            if not requirement_material:
                requirement_material = {
                    "content": workflow_input.get("title", ""),
                    "source_ref": {
                        "type": "requirement",
                        "id": workflow_input.get("requirement_scope", {}).get("requirement_file", "requirement"),
                        "location": workflow_input.get("requirement_scope", {}).get("heading", "title"),
                    },
                }
            technical_material = source_material.get("technical_design", {})

            parallel_calls: dict[str, tuple[Any, Mapping[str, Any]]] = {
                "A02": (
                    RequirementAnalyzerAgent(),
                    {"workflow_input": workflow_input, "requirement": requirement_material},
                ),
                "A03": (
                    TechnicalTestabilityAgent(),
                    {"workflow_input": workflow_input, "technical_design": technical_material},
                ),
            }
            if route["nodes"]["A04"] == "run":
                parallel_calls["A04"] = (
                    ChangeAnalyzerAgent("frontend"),
                    {"change_set": change_set, "implementation_diff": source_material.get("implementation_diff", {})},
                )
            if route["nodes"]["A05"] == "run":
                parallel_calls["A05"] = (
                    ChangeAnalyzerAgent("backend"),
                    {"change_set": change_set, "implementation_diff": source_material.get("implementation_diff", {})},
                )

            with ThreadPoolExecutor(max_workers=len(parallel_calls)) as executor:
                futures = {
                    agent_id: executor.submit(
                        agent.run, context, inputs, self.security, self.model_runtime
                    )
                    for agent_id, (agent, inputs) in parallel_calls.items()
                }
                parallel_results = {agent_id: future.result() for agent_id, future in futures.items()}
            for agent_id in sorted(parallel_results):
                save(parallel_results[agent_id])
            for skipped_id in ("A04", "A05"):
                if skipped_id not in parallel_results:
                    save(
                        node_artifact(
                            skipped_id,
                            "change-analysis",
                            {"domain": "frontend" if skipped_id == "A04" else "backend"},
                            ArtifactStatus.SKIPPED_BY_POLICY,
                            "frontend_not_applicable" if skipped_id == "A04" else "backend_not_applicable",
                        )
                    )

            requirement_analysis = parallel_results["A02"].payload
            technical_analysis = parallel_results["A03"].payload
            frontend_analysis = parallel_results.get("A04")
            backend_analysis = parallel_results.get("A05")
            alignment = save(
                AlignmentAgent().run(
                    context,
                    {
                        "requirement_analysis": requirement_analysis,
                        "technical_analysis": technical_analysis,
                        "frontend_change_analysis": frontend_analysis.payload if frontend_analysis else {},
                        "backend_change_analysis": backend_analysis.payload if backend_analysis else {},
                    },
                    self.security,
                    self.model_runtime,
                )
            )

            n03_issues = []
            for artifact in [*parallel_results.values(), alignment]:
                n03_issues.extend(issue.to_dict() for issue in validate_artifact(artifact.to_dict()))
            validation_issues.extend(n03_issues)
            save(
                node_artifact(
                    "N03",
                    "artifact-validation",
                    {"valid": not n03_issues, "issues": n03_issues},
                    ArtifactStatus.COMPLETED if not n03_issues else ArtifactStatus.NEEDS_HUMAN,
                )
            )
            if n03_issues:
                return self._finish(store, workflow_run_id, workflow_mode, "needs_human", "N03", nodes, validation_issues)

            g01_issues = scope_gate_issues(
                requirement_analysis, technical_analysis, alignment.payload
            )
            if g01_issues:
                g01_reason = (
                    "product_acceptance_open_questions"
                    if any(
                        item.get("issue_code") == "product_acceptance_open_question"
                        for item in g01_issues
                    )
                    else "scope_confirmation_required"
                )
                if not approve_g01:
                    save(
                        node_artifact(
                            "G01",
                            "scope-review",
                            {"decision": "pending", "issues": g01_issues},
                            ArtifactStatus.NEEDS_HUMAN,
                            g01_reason,
                        )
                    )
                    return self._finish(
                        store,
                        workflow_run_id,
                        workflow_mode,
                        "needs_human",
                        "G01",
                        nodes,
                        validation_issues,
                    )
                save(
                    node_artifact(
                        "G01",
                        "scope-review",
                        {"decision": "approved", "issues": g01_issues},
                        reason_code=g01_reason,
                    )
                )

            strategy = self.risk_engine.evaluate(workflow_input, change_set, alignment.payload)
            if strategy["unresolved_items"]:
                advice = save(
                    RiskAdvisorAgent().run(
                        context,
                        {"unresolved_items": strategy["unresolved_items"]},
                        self.security,
                        self.model_runtime,
                    )
                )
                strategy = self.risk_engine.evaluate(workflow_input, change_set, alignment.payload, advice.payload)
            else:
                save(
                    node_artifact(
                        "A07",
                        "risk-strategy-advice",
                        {},
                        ArtifactStatus.SKIPPED_BY_POLICY,
                        "risk_policy_is_deterministic",
                    )
                )
            risk_status = ArtifactStatus.NEEDS_HUMAN if strategy["unresolved_items"] else ArtifactStatus.COMPLETED
            save(node_artifact("N24", "test-strategy", strategy, risk_status))
            if strategy["unresolved_items"]:
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "needs_human",
                    "N24",
                    nodes,
                    validation_issues,
                )

            design = save(
                TestDesignerAgent().run(
                    context,
                    {
                        "requirement_analysis": requirement_analysis,
                        "technical_analysis": technical_analysis,
                        "alignment": alignment.payload,
                        "test_strategy": strategy,
                        "case_provider_draft": provider_draft,
                    },
                    self.security,
                    self.model_runtime,
                )
            )
            review = save(
                TestCoverageAgent().run(
                    context,
                    {"requirement_analysis": requirement_analysis, "test_design": design.payload},
                    self.security,
                    self.model_runtime,
                )
            )
            n04_issues = [issue.to_dict() for issue in validate_test_case_ir(design.payload["parent_cases"])]
            n04_issues.extend(
                {
                    "issue_code": item.get("issue_code", "oracle_coverage_issue"),
                    "message": item.get("message", "A09 reported an Oracle or coverage issue"),
                    "path": item.get("path", "test_design"),
                    "route_to": item.get("route_to", "A08"),
                    "severity": item.get("severity", "error"),
                    "case_id": item.get("case_id"),
                    "expected_id": item.get("expected_id"),
                }
                for item in review.payload.get("issues", [])
            )
            validation_issues.extend(n04_issues)
            save(
                node_artifact(
                    "N04",
                    "test-case-ir-validation",
                    {"valid": not n04_issues, "issues": n04_issues, "oracle_review": review.artifact_id},
                    ArtifactStatus.COMPLETED if not n04_issues else ArtifactStatus.NEEDS_HUMAN,
                )
            )
            if n04_issues or requested_stop == "N04":
                status = "completed_with_gaps" if not n04_issues else "needs_human"
                return self._finish(store, workflow_run_id, workflow_mode, status, "N04", nodes, validation_issues)

            if not approve_g02:
                save(
                    node_artifact(
                        "G02",
                        "test-case-ir-review",
                        {"decision": "pending"},
                        ArtifactStatus.NEEDS_HUMAN,
                        "human_approval_required",
                    )
                )
                return self._finish(store, workflow_run_id, workflow_mode, "needs_human", "G02", nodes, validation_issues)
            save(node_artifact("G02", "test-case-ir-review", {"decision": "approved"}))

            child_cases = compile_cases(design.payload["parent_cases"], strategy)
            save(node_artifact("N25", "compiled-test-cases", {"child_cases": child_cases}))
            split_review = save(
                SplitCoverageAgent().run(
                    context,
                    {"parent_cases": design.payload["parent_cases"], "child_cases": child_cases},
                    self.security,
                    self.model_runtime,
                )
            )
            if not split_review.payload["approved"]:
                return self._finish(store, workflow_run_id, workflow_mode, "needs_human", "A11", nodes, validation_issues)

            selection = select_cases(child_cases, asset_catalog)
            save(
                node_artifact(
                    "N26",
                    "test-selection",
                    selection,
                    ArtifactStatus.NEEDS_HUMAN
                    if selection["unresolved_items"]
                    else ArtifactStatus.COMPLETED,
                )
            )
            if selection["unresolved_items"]:
                save(
                    TestSelectionAdvisorAgent().run(
                        context,
                        {"unresolved_items": selection["unresolved_items"]},
                        self.security,
                        self.model_runtime,
                    )
                )
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "needs_human",
                    "A12",
                    nodes,
                    validation_issues,
                )
            else:
                save(
                    node_artifact(
                        "A12",
                        "test-selection-advice",
                        {},
                        ArtifactStatus.SKIPPED_BY_POLICY,
                        "selection_is_deterministic",
                    )
                )
            plan = compile_execution_plan(selection, child_cases, asset_catalog)
            save(node_artifact("N15", "execution-plan", plan))
            if requested_stop == "N15":
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "completed_with_gaps",
                    "N15",
                    nodes,
                    validation_issues,
                )

            cases_by_id = {str(case["id"]): case for case in child_cases}
            generation_actions = [
                item
                for item in plan["actions"]
                if item["action"] in {"generate_new", "update_existing"}
            ]
            unsupported_actions = [
                item
                for item in generation_actions
                if cases_by_id[str(item["case_id"])].get("layer") != "backend"
            ]
            if unsupported_actions:
                issue = {
                    "issue_code": "generation_profile_not_implemented",
                    "message": "One or more selected layers do not yet have an implemented generator Profile",
                    "path": "execution_plan.actions",
                    "route_to": "Multica",
                    "severity": "error",
                    "case_ids": [item["case_id"] for item in unsupported_actions],
                }
                validation_issues.append(issue)
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "completed_with_gaps",
                    "N15",
                    nodes,
                    validation_issues,
                )

            backend_cases = [
                cases_by_id[str(item["case_id"])]
                for item in generation_actions
                if cases_by_id[str(item["case_id"])].get("layer") == "backend"
            ]
            if not backend_cases:
                save(
                    node_artifact(
                        "A14",
                        "backend-automation-generation",
                        {"manifest": None, "code_candidates": []},
                        ArtifactStatus.SKIPPED_BY_POLICY,
                        "no_backend_generation_action",
                    )
                )
                save(
                    node_artifact(
                        "A18-BE",
                        "backend-automation-review",
                        {"approved": False, "issues": []},
                        ArtifactStatus.SKIPPED_BY_POLICY,
                        "generator_not_run",
                    )
                )
                save(
                    node_artifact(
                        "N05",
                        "automation-code-check",
                        {"passed": False, "issues": []},
                        ArtifactStatus.NOT_APPLICABLE,
                        "no_automation_candidate",
                    )
                )
                save(
                    node_artifact(
                        "G03",
                        "automation-code-review",
                        {"decision": "not_applicable"},
                        ArtifactStatus.NOT_APPLICABLE,
                        "no_automation_candidate",
                    )
                )
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "completed_with_gaps",
                    "G03",
                    nodes,
                    validation_issues,
                )

            target = workflow_input.get("automation_target", {})
            generation = save(
                BackendAutomationAgent().run(
                    context,
                    {"cases": backend_cases, "target": target},
                    self.security,
                    self.model_runtime,
                )
            )
            if generation.status == ArtifactStatus.NOT_APPLICABLE:
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "completed_with_gaps",
                    "A14",
                    nodes,
                    validation_issues,
                )
            automation_review = save(
                BackendAutomationReviewAgent().run(
                    context,
                    {"cases": backend_cases, "generation": generation.payload},
                    self.security,
                    self.model_runtime,
                )
            )
            if not automation_review.payload.get("approved", False):
                review_issues = list(automation_review.payload.get("issues", []))
                validation_issues.extend(review_issues)
                save(
                    node_artifact(
                        "N06",
                        "automation-repair-route",
                        {"routes": ["A14"], "issues": review_issues, "attempt": 1},
                        ArtifactStatus.NEEDS_HUMAN,
                        "automation_review_failed",
                    )
                )
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "needs_human",
                    "N06",
                    nodes,
                    validation_issues,
                )

            code_check = check_automation_generation(generation.payload, self.automation_policy)
            validation_issues.extend(code_check["issues"])
            if code_check["passed"]:
                check_status = ArtifactStatus.COMPLETED
                check_reason = None
            elif code_check["fatal_security_violation"]:
                check_status = ArtifactStatus.FAILED_FATAL
                check_reason = "security_policy_violation"
            else:
                check_status = ArtifactStatus.NEEDS_HUMAN
                check_reason = "automation_code_check_failed"
            save(node_artifact("N05", "automation-code-check", code_check, check_status, check_reason))
            if not code_check["passed"]:
                if code_check["fatal_security_violation"]:
                    return self._finish(
                        store,
                        workflow_run_id,
                        workflow_mode,
                        "failed_fatal",
                        "N05",
                        nodes,
                        validation_issues,
                    )
                save(
                    node_artifact(
                        "N06",
                        "automation-repair-route",
                        {
                            "routes": code_check["repair_routes"],
                            "issues": code_check["issues"],
                            "attempt": 1,
                        },
                        ArtifactStatus.NEEDS_HUMAN,
                        "automation_repair_required",
                    )
                )
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "needs_human",
                    "N06",
                    nodes,
                    validation_issues,
                )

            if not approve_g03:
                save(
                    node_artifact(
                        "G03",
                        "automation-code-review",
                        {
                            "decision": "pending",
                            "manifest_id": generation.payload["manifest"]["manifest_id"],
                        },
                        ArtifactStatus.NEEDS_HUMAN,
                        "human_approval_required",
                    )
                )
                return self._finish(
                    store,
                    workflow_run_id,
                    workflow_mode,
                    "needs_human",
                    "G03",
                    nodes,
                    validation_issues,
                )
            save(
                node_artifact(
                    "G03",
                    "automation-code-review",
                    {
                        "decision": "approved",
                        "manifest_id": generation.payload["manifest"]["manifest_id"],
                    },
                )
            )
            return self._finish(
                store,
                workflow_run_id,
                workflow_mode,
                "completed_with_gaps",
                "G03",
                nodes,
                validation_issues,
            )
        except QaAgentError as error:
            save(
                node_artifact(
                    "SYSTEM",
                    "failure",
                    {"message": str(error), "retryable": error.retryable},
                    ArtifactStatus.FAILED_RETRYABLE if error.retryable else ArtifactStatus.FAILED_FATAL,
                    error.reason_code,
                )
            )
            return self._finish(store, workflow_run_id, workflow_mode, "failed_fatal", "SYSTEM", nodes, validation_issues)

    @staticmethod
    def _finish(
        store: ArtifactStore,
        workflow_run_id: str,
        workflow_mode: str,
        status: str,
        stopped_at: str,
        nodes: list[dict[str, Any]],
        validation_issues: list[dict[str, Any]],
    ) -> WorkflowResult:
        summary = {
            "schema_version": "workflow-summary/1.0",
            "workflow_run_id": workflow_run_id,
            "workflow_mode": workflow_mode,
            "status": status,
            "stopped_at": stopped_at,
            "nodes": nodes,
            "validation_issues": validation_issues,
        }
        store.write_json("run-summary.json", summary)
        store.write_text("report.txt", render_text(summary))
        store.write_text("report.html", render_html(summary))
        return WorkflowResult(workflow_run_id, status, stopped_at, store.root, summary)
