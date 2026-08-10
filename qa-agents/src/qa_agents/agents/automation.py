"""Phase 2 automation generation and independent review Profiles.

A13-A18-* share one deterministic generation engine and one independent review
engine. Domain differences (framework, candidate root, manifest identity and
review checks) are expressed through versioned :class:`AutomationProfile`
instances and the automation-target policy instead of duplicated agent classes.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
import re
from typing import Any

from .base import AgentOutput, BaseAgent
from ..contracts import ArtifactStatus, content_hash


def _python_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return normalized or "unnamed_case"


STABLE_LOCATOR = re.compile(r"^(role|testid|label|placeholder|text|name):", re.IGNORECASE)

CONTRACT_SOURCE_TYPES = {"contract", "openapi", "consumer_contract", "api_contract"}


class AutomationProfile:
    """Versioned generator + reviewer identity for one test layer or NF kind."""

    def __init__(
        self,
        *,
        agent_id: str,
        output_name: str,
        generator_profile: str,
        review_agent_id: str,
        review_profile: str,
        review_output_name: str,
        manifest_id: str,
        layer: str,
        candidate_root: str,
        framework: str = "pytest",
        kind: str = "",
        profile_version: str = "1.0.0",
        not_applicable_reason: str = "no_machine_executable_case",
        spec_builder: Callable[[Mapping[str, Any]], tuple[dict[str, Any], str | None]],
        spec_validator: Callable[[Mapping[str, Any], str], list[dict[str, Any]]],
    ) -> None:
        self.agent_id = agent_id
        self.output_name = output_name
        self.generator_profile = generator_profile
        self.review_agent_id = review_agent_id
        self.review_profile = review_profile
        self.review_output_name = review_output_name
        self.manifest_id = manifest_id
        self.layer = layer
        self.candidate_root = candidate_root
        self.framework = framework
        self.kind = kind
        self.profile_version = profile_version
        self.not_applicable_reason = not_applicable_reason
        self.spec_builder = spec_builder
        self.spec_validator = spec_validator


# --- domain CASE_SPEC builders -------------------------------------------------


def _spec_backend(case: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    return {}, None


def _spec_frontend(case: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    test_data = case.get("test_data", {}) if isinstance(case.get("test_data"), Mapping) else {}
    locators = [str(item) for item in test_data.get("locators", [])]
    if not locators or not all(STABLE_LOCATOR.match(item) for item in locators):
        return {}, "frontend_locator_not_stable"
    return {
        "driver": "playwright",
        "route": str(test_data.get("route", "")),
        "locators": locators,
    }, None


def _spec_contract(case: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    test_data = case.get("test_data", {}) if isinstance(case.get("test_data"), Mapping) else {}
    contract_ref = str(test_data.get("contract_ref", "") or "")
    if not contract_ref:
        for source in case.get("source_refs", []):
            if isinstance(source, Mapping) and source.get("type") in CONTRACT_SOURCE_TYPES:
                contract_ref = str(source.get("id", ""))
                break
    if not contract_ref:
        return {}, "contract_ref_missing"
    return {
        "driver": "contract",
        "contract_ref": contract_ref,
        "method": str(test_data.get("method", "")),
        "path": str(test_data.get("path", "")),
    }, None


def _spec_e2e(case: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    test_data = case.get("test_data", {}) if isinstance(case.get("test_data"), Mapping) else {}
    journey = str(test_data.get("journey", "") or "")
    if not journey:
        return {}, "e2e_journey_missing"
    return {
        "driver": "playwright",
        "journey": journey,
        "cross_service_evidence": bool(test_data.get("cross_service_evidence", False)),
    }, None


def _spec_non_functional(kind: str) -> Callable[[Mapping[str, Any]], tuple[dict[str, Any], str | None]]:
    def builder(case: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
        test_data = case.get("test_data", {}) if isinstance(case.get("test_data"), Mapping) else {}
        if str(case.get("non_functional_kind", "")) != kind:
            return {}, "non_functional_kind_mismatch"
        metric = str(test_data.get("metric", "") or "")
        threshold = test_data.get("threshold")
        threshold_source = str(test_data.get("threshold_source", "") or "")
        if not metric or threshold is None or not threshold_source:
            return {}, "non_functional_threshold_missing"
        return {
            "kind": kind,
            "metric": metric,
            "threshold": threshold,
            "threshold_source": threshold_source,
        }, None

    return builder


# --- domain review hooks -------------------------------------------------------


def _review_backend(case_spec: Mapping[str, Any], content: str) -> list[dict[str, Any]]:
    return []


def _review_frontend(case_spec: Mapping[str, Any], content: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if case_spec.get("driver") != "playwright":
        issues.append({"issue_code": "ui_driver_missing"})
    for locator in case_spec.get("locators", []):
        if not STABLE_LOCATOR.match(str(locator)):
            issues.append({"issue_code": "unstable_locator", "locator": str(locator)})
    return issues


def _review_contract(case_spec: Mapping[str, Any], content: str) -> list[dict[str, Any]]:
    if not case_spec.get("contract_ref"):
        return [{"issue_code": "contract_ref_missing"}]
    return []


def _review_e2e(case_spec: Mapping[str, Any], content: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not case_spec.get("journey"):
        issues.append({"issue_code": "e2e_journey_missing"})
    if case_spec.get("cross_service_evidence") is not True:
        issues.append({"issue_code": "cross_service_evidence_missing"})
    return issues


def _review_non_functional(kind: str) -> Callable[[Mapping[str, Any], str], list[dict[str, Any]]]:
    def validator(case_spec: Mapping[str, Any], content: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if case_spec.get("kind") != kind:
            issues.append({"issue_code": "non_functional_kind_mismatch"})
        if not case_spec.get("threshold_source"):
            issues.append({"issue_code": "threshold_source_missing"})
        return issues

    return validator


# --- versioned profile registry ------------------------------------------------


LAYER_PROFILES: dict[str, AutomationProfile] = {
    "backend": AutomationProfile(
        agent_id="A14",
        output_name="backend-automation-generation",
        generator_profile="A14/1.0.0",
        review_agent_id="A18-BE",
        review_profile="A18-BE/1.0.0",
        review_output_name="backend-automation-review",
        manifest_id="manifest-a14-backend",
        layer="backend",
        candidate_root="generated/backend",
        not_applicable_reason="no_machine_executable_backend_case",
        spec_builder=_spec_backend,
        spec_validator=_review_backend,
    ),
    "frontend": AutomationProfile(
        agent_id="A13",
        output_name="frontend-automation-generation",
        generator_profile="A13/1.0.0",
        review_agent_id="A18-FE",
        review_profile="A18-FE/1.0.0",
        review_output_name="frontend-automation-review",
        manifest_id="manifest-a13-frontend",
        layer="frontend",
        candidate_root="generated/frontend",
        framework="playwright",
        not_applicable_reason="no_machine_executable_frontend_case",
        spec_builder=_spec_frontend,
        spec_validator=_review_frontend,
    ),
    "contract": AutomationProfile(
        agent_id="A15",
        output_name="contract-automation-generation",
        generator_profile="A15/1.0.0",
        review_agent_id="A18-CT",
        review_profile="A18-CT/1.0.0",
        review_output_name="contract-automation-review",
        manifest_id="manifest-a15-contract",
        layer="contract",
        candidate_root="generated/contract",
        not_applicable_reason="no_machine_executable_contract_case",
        spec_builder=_spec_contract,
        spec_validator=_review_contract,
    ),
    "e2e": AutomationProfile(
        agent_id="A16",
        output_name="e2e-automation-generation",
        generator_profile="A16/1.0.0",
        review_agent_id="A18-E2E",
        review_profile="A18-E2E/1.0.0",
        review_output_name="e2e-automation-review",
        manifest_id="manifest-a16-e2e",
        layer="e2e",
        candidate_root="generated/e2e",
        framework="playwright",
        not_applicable_reason="no_machine_executable_e2e_case",
        spec_builder=_spec_e2e,
        spec_validator=_review_e2e,
    ),
}

NON_FUNCTIONAL_KINDS: dict[str, tuple[str, str]] = {
    "performance": ("A17-PERF", "A18-PERF"),
    "security": ("A17-SEC", "A18-SEC"),
    "accessibility": ("A17-A11Y", "A18-A11Y"),
    "compatibility": ("A17-COMPAT", "A18-COMPAT"),
    "resilience": ("A17-RES", "A18-RES"),
    "data_consistency": ("A17-DATA", "A18-DATA"),
}


def _non_functional_profile(kind: str, generator_id: str, reviewer_id: str) -> AutomationProfile:
    framework = "playwright" if kind in {"accessibility", "compatibility"} else "pytest"
    return AutomationProfile(
        agent_id=generator_id,
        output_name=f"{kind}-automation-generation",
        generator_profile=f"{generator_id}/1.0.0",
        review_agent_id=reviewer_id,
        review_profile=f"{reviewer_id}/1.0.0",
        review_output_name=f"{kind}-automation-review",
        manifest_id=f"manifest-{generator_id.lower()}",
        layer="non_functional",
        candidate_root="generated/non_functional",
        framework=framework,
        kind=kind,
        not_applicable_reason=f"no_machine_executable_{kind}_case",
        spec_builder=_spec_non_functional(kind),
        spec_validator=_review_non_functional(kind),
    )


NON_FUNCTIONAL_PROFILES: dict[str, AutomationProfile] = {
    kind: _non_functional_profile(kind, generator_id, reviewer_id)
    for kind, (generator_id, reviewer_id) in NON_FUNCTIONAL_KINDS.items()
}

AUTOMATION_PROFILES: dict[str, AutomationProfile] = {
    profile.agent_id: profile
    for profile in [*LAYER_PROFILES.values(), *NON_FUNCTIONAL_PROFILES.values()]
}


def profile_for_case(case: Mapping[str, Any]) -> AutomationProfile | None:
    layer = str(case.get("layer", ""))
    if layer == "non_functional":
        return NON_FUNCTIONAL_PROFILES.get(str(case.get("non_functional_kind", "")))
    return LAYER_PROFILES.get(layer)


# --- deterministic generation engine -------------------------------------------


class DomainAutomationAgent(BaseAgent):
    """Build artifact-only test candidates without writing any Git repository."""

    runtime = "automation-generation-runtime"
    output_contract = "automation-generation/1.0"

    def __init__(self, profile: AutomationProfile) -> None:
        self.profile = profile
        self.agent_id = profile.agent_id
        self.output_name = profile.output_name
        self.profile_version = profile.profile_version

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        cases = list(inputs.get("cases", []))
        target = dict(inputs.get("target", {}))
        candidates: list[dict[str, Any]] = []
        mappings: list[dict[str, Any]] = []
        rejected: list[dict[str, str]] = []

        for case in cases:
            case_id = str(case.get("id", ""))
            allowed_modes = set(case.get("execution_policy", {}).get("allowed_modes", []))
            expected_ids = [str(item.get("id", "")) for item in case.get("expected", [])]
            manual_oracle = any(
                item.get("oracle", {}).get("matcher") == "manual_confirmation"
                for item in case.get("expected", [])
            )
            if (
                case.get("layer") != self.profile.layer
                or not case.get("automation_candidate")
                or "automated" not in allowed_modes
                or not expected_ids
                or manual_oracle
            ):
                rejected.append(
                    {"case_id": case_id, "reason_code": "case_not_machine_executable"}
                )
                continue

            spec_extra, domain_reason = self.profile.spec_builder(case)
            if domain_reason is not None:
                rejected.append({"case_id": case_id, "reason_code": domain_reason})
                continue

            case_spec = {
                "case_id": case_id,
                "title": str(case.get("title", "")),
                "preconditions": list(case.get("preconditions", [])),
                "test_data": dict(case.get("test_data", {})),
                "steps": list(case.get("steps", [])),
                "expected": list(case.get("expected", [])),
                "cleanup": list(case.get("cleanup", [])),
            }
            case_spec.update(spec_extra)
            path = f"{self.profile.candidate_root}/test_{_python_name(case_id)}.py"
            literal = repr(case_spec)
            function_name = f"test_{_python_name(case_id)}"
            content = (
                '"""Artifact-only candidate generated from approved Test Case IR."""\n\n'
                f"CASE_SPEC = {literal}\n\n\n"
                f"def {function_name}(case_runner):\n"
                "    observations = case_runner.execute(CASE_SPEC)\n"
                "    case_runner.assert_oracles(observations, CASE_SPEC[\"expected\"])\n"
            )
            candidates.append(
                {"path": path, "content": content, "content_hash": content_hash(content)}
            )
            mappings.append(
                {"case_id": case_id, "expected_ids": expected_ids, "candidate_path": path}
            )

        if not candidates:
            return AgentOutput(
                payload={
                    "schema_version": "automation-generation/1.0",
                    "manifest": None,
                    "code_candidates": [],
                    "rejected_cases": rejected,
                },
                status=ArtifactStatus.NOT_APPLICABLE,
                reason_code=self.profile.not_applicable_reason,
            )

        candidate_files = [
            {"path": item["path"], "content_hash": item["content_hash"]}
            for item in candidates
        ]
        paths = [item["path"] for item in candidates]
        manifest = {
            "schema_version": "automation-manifest/1.0",
            "manifest_id": self.profile.manifest_id,
            "generator_profile": self.profile.generator_profile,
            "target_repository": {
                "repository_id": str(target.get("repository_id", "")),
                "access_class": str(target.get("access_class", "")),
                "write_mode": "artifact_only_candidate",
            },
            "framework": self.profile.framework,
            "language": "python",
            "case_mappings": mappings,
            "candidate_files": candidate_files,
            "execution": {
                "command": ["pytest", "-q", *paths],
                "timeout_seconds": int(target.get("timeout_seconds", 600)),
            },
            "permissions": {
                "business_repository_write": False,
                "network": bool(target.get("network", False)),
                "secrets": list(target.get("secrets", [])),
            },
            "expected_artifacts": ["junit_xml", "stdout", "stderr"],
        }
        return AgentOutput(
            payload={
                "schema_version": "automation-generation/1.0",
                "manifest": manifest,
                "code_candidates": candidates,
                "rejected_cases": rejected,
            }
        )


class BackendAutomationAgent(DomainAutomationAgent):
    """Backward-compatible A14 backend generator."""

    def __init__(self) -> None:
        super().__init__(LAYER_PROFILES["backend"])


# --- independent review engine --------------------------------------------------


def _extract_case_spec(content: str) -> dict[str, Any]:
    try:
        tree = ast.parse(content, filename="<candidate>")
    except SyntaxError:
        return {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "CASE_SPEC"
            for target in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                return {}
            return value if isinstance(value, dict) else {}
    return {}


class DomainAutomationReviewAgent(BaseAgent):
    """Independent review of generated candidates without generator context."""

    runtime = "automation-review-runtime"
    output_contract = "automation-review/1.0"

    def __init__(self, profile: AutomationProfile) -> None:
        self.profile = profile
        self.agent_id = profile.review_agent_id
        self.output_name = profile.review_output_name
        self.profile_version = profile.profile_version

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        cases = {str(item.get("id")): item for item in inputs.get("cases", [])}
        generation = inputs.get("generation", {})
        manifest = generation.get("manifest") or {}
        candidates = {
            str(item.get("path")): item for item in generation.get("code_candidates", [])
        }
        issues: list[dict[str, Any]] = []
        route = self.profile.agent_id

        for mapping in manifest.get("case_mappings", []):
            case_id = str(mapping.get("case_id", ""))
            case = cases.get(case_id)
            path = str(mapping.get("candidate_path", ""))
            candidate = candidates.get(path)
            if case is None:
                issues.append(
                    {"issue_code": "review_case_missing", "case_id": case_id, "route_to": "N25"}
                )
                continue
            if candidate is None:
                issues.append(
                    {"issue_code": "candidate_file_missing", "case_id": case_id, "route_to": route}
                )
                continue
            expected_ids = {str(item.get("id")) for item in case.get("expected", [])}
            mapped_ids = set(mapping.get("expected_ids", []))
            if expected_ids != mapped_ids:
                issues.append(
                    {
                        "issue_code": "oracle_mapping_incomplete",
                        "case_id": case_id,
                        "route_to": route,
                    }
                )
            content = str(candidate.get("content", ""))
            if "case_runner.execute(CASE_SPEC)" not in content:
                issues.append(
                    {"issue_code": "execution_binding_missing", "case_id": case_id, "route_to": route}
                )
            if "case_runner.assert_oracles" not in content:
                issues.append(
                    {"issue_code": "oracle_assertion_missing", "case_id": case_id, "route_to": route}
                )
            for expected_id in expected_ids:
                if expected_id not in content:
                    issues.append(
                        {
                            "issue_code": "expected_id_not_bound",
                            "case_id": case_id,
                            "expected_id": expected_id,
                            "route_to": route,
                        }
                    )
            case_spec = _extract_case_spec(content)
            for issue in self.profile.spec_validator(case_spec, content):
                issues.append({**issue, "case_id": case_id, "route_to": route})

        mapped_case_ids = {
            str(item.get("case_id")) for item in manifest.get("case_mappings", [])
        }
        for case_id in sorted(set(cases) - mapped_case_ids):
            issues.append(
                {"issue_code": "automation_case_not_mapped", "case_id": case_id, "route_to": route}
            )

        return AgentOutput(
            payload={
                "schema_version": "automation-review/1.0",
                "review_profile": self.profile.review_profile,
                "approved": not issues,
                "issues": issues,
                "generator_hidden_reasoning_accessed": False,
                "evaluation_oracle_accessed": False,
            },
            status=ArtifactStatus.COMPLETED if not issues else ArtifactStatus.NEEDS_HUMAN,
            reason_code=None if not issues else "automation_review_failed",
        )


class BackendAutomationReviewAgent(DomainAutomationReviewAgent):
    """Backward-compatible A18-BE backend reviewer."""

    def __init__(self) -> None:
        super().__init__(LAYER_PROFILES["backend"])
