"""Deterministic-first QA multi-agent system."""

from .contracts import ArtifactEnvelope, ArtifactStatus, EvidenceRef
from .workflow import PhaseOneWorkflow, WorkflowResult

__all__ = [
    "ArtifactEnvelope",
    "ArtifactStatus",
    "EvidenceRef",
    "PhaseOneWorkflow",
    "WorkflowResult",
]

__version__ = "0.1.0"
