"""Content-addressed, path-confined Artifact storage."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .contracts import ArtifactEnvelope
from .errors import SecurityPolicyError


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if target != self.root and self.root not in target.parents:
            raise SecurityPolicyError(f"Artifact path escapes store: {relative_path}")
        return target

    def write_json(self, relative_path: str, value: Any) -> Path:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(value, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
            os.replace(temporary_name, target)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return target

    def write_text(self, relative_path: str, value: str) -> Path:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(value)
            os.replace(temporary_name, target)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return target

    def write_artifact(self, artifact: ArtifactEnvelope) -> Path:
        return self.write_json(f"artifacts/{artifact.artifact_id}.json", artifact.to_dict())

    def read_json(self, relative_path: str) -> Any:
        with self._resolve(relative_path).open(encoding="utf-8") as file:
            return json.load(file)
