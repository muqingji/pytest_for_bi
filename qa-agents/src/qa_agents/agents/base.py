"""Base types for isolated, versioned Agent Profile calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..contracts import ArtifactEnvelope, ArtifactStatus, EvidenceRef, Producer
from ..errors import ContractError
from ..model_runtime import StructuredModelRuntime
from ..security import SecurityPolicy


@dataclass(frozen=True)
class AgentContext:
    workflow_run_id: str
    workflow_mode: str
    source_snapshot_id: str
    input_paths: tuple[str, ...] = ()


@dataclass
class AgentOutput:
    payload: dict[str, Any]
    status: ArtifactStatus = ArtifactStatus.COMPLETED
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    facts: list[Mapping[str, Any]] = field(default_factory=list)
    inferences: list[Mapping[str, Any]] = field(default_factory=list)
    assumptions: list[Mapping[str, Any]] = field(default_factory=list)
    blocking_questions: list[Mapping[str, Any]] = field(default_factory=list)
    reason_code: str | None = None


class BaseAgent:
    agent_id = "A00"
    profile_version = "1.0.0"
    output_name = "agent-output"
    runtime = "analysis-runtime"
    output_contract = "agent-output/1.0"

    def analyze(self, inputs: Mapping[str, Any]) -> AgentOutput:
        raise NotImplementedError

    def run(
        self,
        context: AgentContext,
        inputs: Mapping[str, Any],
        security: SecurityPolicy,
        model_runtime: StructuredModelRuntime | None = None,
    ) -> ArtifactEnvelope:
        security.assert_agent_paths(context.input_paths)
        model_result = None
        if model_runtime is not None and model_runtime.supports(self.agent_id):
            model_result = model_runtime.invoke(
                profile_id=self.agent_id,
                profile_version=self.profile_version,
                output_contract=self.output_contract,
                workflow_run_id=context.workflow_run_id,
                source_snapshot_id=context.source_snapshot_id,
                inputs=inputs,
            )
            value = model_result.output
            try:
                status = ArtifactStatus(str(value.get("status", "completed")))
            except ValueError as error:
                raise ContractError("Model Runtime returned an invalid Artifact status") from error
            output = AgentOutput(
                payload=dict(value["payload"]),
                status=status,
                evidence_refs=[EvidenceRef(**item) for item in value.get("evidence_refs", [])],
                facts=list(value.get("facts", [])),
                inferences=list(value.get("inferences", [])),
                assumptions=list(value.get("assumptions", [])),
                blocking_questions=list(value.get("blocking_questions", [])),
                reason_code=value.get("reason_code"),
            )
        else:
            output = self.analyze(inputs)
        return ArtifactEnvelope(
            workflow_run_id=context.workflow_run_id,
            workflow_mode=context.workflow_mode,
            artifact_id=f"{self.agent_id.lower()}-{self.output_name}",
            source_snapshot_id=context.source_snapshot_id,
            producer=Producer(
                component_id=self.agent_id,
                runtime=self.runtime,
                profile_version=self.profile_version,
                model_provider=model_result.provider if model_result else "none",
                model_snapshot=model_result.model_snapshot
                if model_result
                else "deterministic",
                prompt_version=model_result.prompt_version if model_result else "none",
                inference_config_hash=model_result.inference_config_hash
                if model_result
                else "none",
                tool_bundle_version=model_result.tool_bundle_version
                if model_result
                else "none",
            ),
            payload=security.redact_secrets(output.payload),
            status=output.status,
            evidence_refs=tuple(output.evidence_refs),
            facts=tuple(security.redact_secrets(output.facts)),
            inferences=tuple(security.redact_secrets(output.inferences)),
            assumptions=tuple(security.redact_secrets(output.assumptions)),
            blocking_questions=tuple(security.redact_secrets(output.blocking_questions)),
            reason_code=output.reason_code,
        )
