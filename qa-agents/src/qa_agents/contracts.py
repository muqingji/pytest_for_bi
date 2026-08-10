"""Versioned workflow contracts shared by agents and deterministic nodes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


class ArtifactStatus(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_GAPS = "completed_with_gaps"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"
    BLOCKED_INPUT = "blocked_input"
    NOT_APPLICABLE = "not_applicable"
    SKIPPED_BY_POLICY = "skipped_by_policy"
    STALE = "stale"
    CANCELLED = "cancelled"
    INCONCLUSIVE = "inconclusive"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FATAL = "failed_fatal"


@dataclass(frozen=True)
class EvidenceRef:
    source_type: str
    source_id: str
    location: str
    content_hash: str | None = None


@dataclass(frozen=True)
class Producer:
    component_id: str
    component_version: str = "0.1.0"
    runtime: str = "qa-agents-local"
    profile_version: str = "1.0.0"
    model_provider: str = "none"
    model_snapshot: str = "deterministic"
    prompt_version: str = "none"
    inference_config_hash: str = "none"
    tool_bundle_version: str = "none"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


def artifact_hash_from_mapping(artifact: Mapping[str, Any]) -> str:
    """Recalculate an Artifact Envelope hash without trusting its stored hash."""

    return content_hash(
        {
            "artifact_id": artifact.get("artifact_id"),
            "workflow_mode": artifact.get("workflow_mode"),
            "schema_version": artifact.get("schema_version"),
            "source_snapshot_id": artifact.get("source_snapshot_id"),
            "producer": artifact.get("producer"),
            "payload": artifact.get("payload"),
            "status": artifact.get("status"),
            "evidence_refs": artifact.get("evidence_refs", []),
            "facts": artifact.get("facts", []),
            "inferences": artifact.get("inferences", []),
            "assumptions": artifact.get("assumptions", []),
            "blocking_questions": artifact.get("blocking_questions", []),
            "reason_code": artifact.get("reason_code"),
        }
    )


@dataclass(frozen=True)
class ArtifactEnvelope:
    workflow_run_id: str
    workflow_mode: str
    artifact_id: str
    source_snapshot_id: str
    producer: Producer
    payload: Mapping[str, Any]
    status: ArtifactStatus = ArtifactStatus.COMPLETED
    schema_version: str = "artifact-envelope/1.0"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    evidence_refs: tuple[EvidenceRef, ...] = ()
    facts: tuple[Mapping[str, Any], ...] = ()
    inferences: tuple[Mapping[str, Any], ...] = ()
    assumptions: tuple[Mapping[str, Any], ...] = ()
    blocking_questions: tuple[Mapping[str, Any], ...] = ()
    reason_code: str | None = None

    @property
    def artifact_hash(self) -> str:
        return content_hash(
            {
                "artifact_id": self.artifact_id,
                "workflow_mode": self.workflow_mode,
                "schema_version": self.schema_version,
                "source_snapshot_id": self.source_snapshot_id,
                "producer": asdict(self.producer),
                "payload": self.payload,
                "status": self.status.value,
                "evidence_refs": [asdict(item) for item in self.evidence_refs],
                "facts": self.facts,
                "inferences": self.inferences,
                "assumptions": self.assumptions,
                "blocking_questions": self.blocking_questions,
                "reason_code": self.reason_code,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["artifact_hash"] = self.artifact_hash
        return value


@dataclass(frozen=True)
class ValidationIssue:
    issue_code: str
    message: str
    path: str
    route_to: str
    severity: str = "error"
    case_id: str | None = None
    expected_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
