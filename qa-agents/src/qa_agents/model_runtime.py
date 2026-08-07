"""Structured model Runtime boundary supplied by Multica in production."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import content_hash
from .errors import ContractError, SecurityPolicyError
from .security import SecurityPolicy


@dataclass(frozen=True)
class ModelRuntimeResult:
    output: Mapping[str, Any]
    provider: str
    model_snapshot: str
    prompt_version: str
    inference_config_hash: str
    tool_bundle_version: str


class StructuredModelRuntime:
    """Validate a model call around an injected executor; it owns no network client."""

    def __init__(
        self,
        policy: Mapping[str, Any],
        executor: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        security: SecurityPolicy | None = None,
    ) -> None:
        self.policy = dict(policy)
        self.executor = executor
        self.security = security or SecurityPolicy()

    def supports(self, profile_id: str) -> bool:
        return bool(self.policy.get("enabled", False)) and profile_id in self.policy.get(
            "profile_bindings", {}
        )

    def invoke(
        self,
        *,
        profile_id: str,
        profile_version: str,
        output_contract: str,
        workflow_run_id: str,
        source_snapshot_id: str,
        inputs: Mapping[str, Any],
    ) -> ModelRuntimeResult:
        if not self.supports(profile_id):
            raise ContractError(f"No enabled model binding for {profile_id}")
        binding = self.policy["profile_bindings"][profile_id]
        provider = str(binding.get("provider", ""))
        model_snapshot = str(binding.get("model_snapshot", ""))
        prompt_version = str(binding.get("prompt_version", ""))
        allowed = {
            (str(item.get("provider")), str(item.get("model_snapshot")))
            for item in self.policy.get("allowed_deployments", [])
        }
        if (provider, model_snapshot) not in allowed:
            raise SecurityPolicyError("Model deployment is not allowed by the frozen policy")
        if not model_snapshot or model_snapshot.endswith("latest"):
            raise SecurityPolicyError("Model snapshot must be immutable")
        if not prompt_version:
            raise ContractError("Model binding must pin prompt_version")
        if binding.get("output_contract") != output_contract:
            raise ContractError("Model binding output contract does not match the Agent Profile")
        if binding.get("tools", []) != []:
            raise SecurityPolicyError("Semantic analysis Runtime must not receive direct tools")
        if self.policy.get("data_retention_allowed") is not False:
            raise SecurityPolicyError("Model Runtime must disable provider data retention")

        self.security.assert_no_secret_values(inputs)
        request = {
            "schema_version": "model-invocation/1.0",
            "profile_id": profile_id,
            "profile_version": profile_version,
            "output_contract": output_contract,
            "workflow_run_id": workflow_run_id,
            "source_snapshot_id": source_snapshot_id,
            "prompt_version": prompt_version,
            "inputs": inputs,
        }
        response = self.executor(request)
        if not isinstance(response, Mapping):
            raise ContractError("Model Runtime response must be an object")
        self.security.assert_no_secret_values(response)
        if not isinstance(response.get("payload"), Mapping):
            raise ContractError("Model Runtime response payload must be an object")
        if response["payload"].get("schema_version") != output_contract:
            raise ContractError("Model Runtime returned an unexpected output contract")
        inference_config = dict(binding.get("inference_config", {}))
        return ModelRuntimeResult(
            output=dict(response),
            provider=provider,
            model_snapshot=model_snapshot,
            prompt_version=prompt_version,
            inference_config_hash=content_hash(inference_config),
            tool_bundle_version=str(binding.get("tool_bundle_version", "none")),
        )
