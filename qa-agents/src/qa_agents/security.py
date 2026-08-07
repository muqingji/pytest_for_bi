"""Non-bypassable input and repository safety checks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

from .errors import SecurityPolicyError


SECRET_KEY = re.compile(r"(token|cookie|password|secret|authorization|fsauth)", re.IGNORECASE)
SECRET_VALUE = re.compile(
    r"(?i)(authorization\s*:\s*(?:bearer\s+)?\S{12,}|cookie\s*:\s*\S{12,}|"
    r"fs_token=[A-Za-z0-9]{8,}|(?:password|passwd)\s*[:=]\s*['\"]?[^\s'\"]{8,})"
)


class SecurityPolicy:
    def validate_workflow_input(self, workflow_input: Mapping[str, Any]) -> None:
        self.assert_no_secret_values(workflow_input)
        policy = workflow_input.get("source_access_policy", {})
        required = {
            "business_repositories": "read_only",
            "use_mutable_local_worktree": False,
            "allow_business_repository_metadata_writes": False,
        }
        for key, expected in required.items():
            if policy.get(key) != expected:
                raise SecurityPolicyError(
                    f"source_access_policy.{key} must be {expected!r}"
                )

        writable_targets = set(policy.get("writable_targets", []))
        allowed = {"workflow_artifact_store", "approved_automation_repository"}
        if not writable_targets <= allowed:
            raise SecurityPolicyError("Workflow declares an unapproved write target")

    def validate_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        self.assert_no_secret_values(snapshot)
        integrity = snapshot.get("integrity", {})
        if integrity.get("business_repository_write_allowed") is not False:
            raise SecurityPolicyError("Business repository writes must be disabled")
        if integrity.get("oracle_included_in_agent_input") is not False:
            raise SecurityPolicyError("Oracle must not be included in agent input")
        if integrity.get("source_credentials_embedded") is not False:
            raise SecurityPolicyError("Source credentials must not be embedded")

        sources: list[Mapping[str, Any]] = []
        implementation = snapshot.get("implementation_source")
        if isinstance(implementation, Mapping):
            sources.append(implementation)
        sources.extend(
            item
            for item in snapshot.get("reference_sources", [])
            if isinstance(item, Mapping)
        )
        for source in sources:
            access_class = str(source.get("access_class", ""))
            if "business_source" in access_class and not access_class.endswith("read_only"):
                raise SecurityPolicyError("Business source is not marked read-only")

    def assert_agent_paths(self, paths: Iterable[str]) -> None:
        for path in paths:
            lowered = path.replace("\\", "/").lower()
            if "/oracle/" in f"/{lowered.strip('/')}/" or lowered.endswith("/oracle"):
                raise SecurityPolicyError("Oracle Registry is not accessible to agents")

    def redact_secrets(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: "[REDACTED]" if SECRET_KEY.search(str(key)) else self.redact_secrets(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.redact_secrets(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact_secrets(item) for item in value)
        if isinstance(value, str) and SECRET_VALUE.search(value):
            return "[REDACTED]"
        return value

    def assert_no_secret_values(self, value: Any, path: str = "$") -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                child_path = f"{path}.{key}"
                empty_or_redacted = item is None or item is False
                if isinstance(item, str):
                    empty_or_redacted = item in {"", "[REDACTED]"}
                elif isinstance(item, (list, tuple, dict)):
                    empty_or_redacted = not item
                if SECRET_KEY.search(str(key)) and not empty_or_redacted:
                    raise SecurityPolicyError(f"Credential-like field found at {child_path}")
                self.assert_no_secret_values(item, child_path)
            return
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                self.assert_no_secret_values(item, f"{path}[{index}]")
            return
        if isinstance(value, str) and SECRET_VALUE.search(value):
            raise SecurityPolicyError(f"Credential-like value found at {path}")
