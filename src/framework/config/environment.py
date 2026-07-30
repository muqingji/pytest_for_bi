"""Environment configuration and data-file discovery."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_ENV_VALUE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")

def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    values: dict[str, Any]

    @classmethod
    def load(cls, name: str | None = None, root: Path | None = None) -> "EnvironmentConfig":
        environment = name or os.getenv("TEST_ENV", "test")
        base = root or project_root()
        path = base / "config" / f"environment.{environment}.json"
        if not path.is_file():
            raise FileNotFoundError(
                f"Environment config does not exist: {path}. Set TEST_ENV or create the file."
            )
        with path.open(encoding="utf-8") as file:
            values = json.load(file)
        local_path = base / "config" / f"environment.{environment}.local.json"
        if local_path.is_file():
            with local_path.open(encoding="utf-8") as file:
                values = _deep_merge(values, json.load(file))
        values = _expand_environment_variables(values)
        return cls(name=environment, values=values)

    def get(self, path: str, default: Any = None) -> Any:
        current: Any = self.values
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def require(self, *paths: str) -> None:
        """Raise a clear error when a request would use missing secret/config values."""
        missing = [path for path in paths if _is_missing(self.get(path))]
        if missing:
            rendered = ", ".join(missing)
            raise ValueError(
                f"Environment '{self.name}' is missing configuration: {rendered}. "
                f"Set the matching environment variables or config/environment.{self.name}.local.json"
            )

    def require_section(self, path: str) -> None:
        value = self.get(path)
        if value is None:
            self.require(path)
            return
        unresolved = _find_missing_values(value, path)
        if unresolved:
            rendered = ", ".join(unresolved)
            raise ValueError(
                f"Environment '{self.name}' has unresolved configuration: {rendered}. "
                f"Set environment variables or config/environment.{self.name}.local.json"
            )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _expand_environment_variables(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_environment_variables(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_environment_variables(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        variable, default = match.groups()
        return os.getenv(variable, default if default is not None else match.group(0))

    return _ENV_VALUE.sub(replace, value)


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or (isinstance(value, str) and "${" in value)


def _find_missing_values(value: Any, path: str) -> list[str]:
    if _is_missing(value):
        return [path]
    if isinstance(value, dict):
        return [item for key, child in value.items() for item in _find_missing_values(child, f"{path}.{key}")]
    if isinstance(value, list):
        return [item for index, child in enumerate(value) for item in _find_missing_values(child, f"{path}[{index}]")]
    return []


def load_cases(
    environment: str,
    data_dir: Path | None = None,
    priorities: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Load and expand every ``*.{environment}.json`` case file."""
    directory = data_dir or project_root() / "test_data"
    cases: list[dict[str, Any]] = []
    for path in sorted(directory.rglob(f"*.{environment}.json")):
        with path.open(encoding="utf-8") as file:
            document = json.load(file)
        if isinstance(document, dict) and "test_case" in document:
            cases.extend(_expand_test_subject(document, path, priorities))
            continue
        entries = document["cases"] if isinstance(document, dict) else document
        if not isinstance(entries, list):
            raise ValueError(f"{path}: root must be a list or an object with a cases list")
        for case in entries:
            if not isinstance(case, dict) or not case.get("id") or not case.get("steps"):
                raise ValueError(f"{path}: every case needs id and steps")
            case = {**case, "__source__": str(path)}
            cases.append(case)
    return cases


def _expand_test_subject(
    document: dict[str, Any],
    path: Path,
    priorities: set[str] | None,
) -> list[dict[str, Any]]:
    subject = document["test_case"]
    entries = document.get("cases")
    if not isinstance(subject, dict) or not subject.get("id") or not subject.get("api"):
        raise ValueError(f"{path}: test_case needs id and api")
    if not isinstance(entries, list):
        raise ValueError(f"{path}: cases must be a list")

    expanded = []
    for instance in entries:
        if not isinstance(instance, dict):
            raise ValueError(f"{path}: every case must be an object")
        required = [key for key in ("id", "priority", "req", "resp") if key not in instance]
        if required:
            raise ValueError(f"{path}: case is missing {', '.join(required)}")
        priority = str(instance["priority"]).upper()
        if priorities is not None and priority not in priorities:
            continue
        request = _normalize_case_request(instance["req"], subject["api"])
        expanded.append(
            {
                "id": f"{subject['id']}::{instance['id']}",
                "subject_id": subject["id"],
                "case_id": instance["id"],
                "name": instance.get("name") or instance["id"],
                "priority": priority,
                "enabled": subject.get("enabled", True) and instance.get("enabled", True),
                "tags": list(dict.fromkeys([*subject.get("tags", []), *instance.get("tags", [])])),
                "variables": {**subject.get("variables", {}), **instance.get("variables", {})},
                "steps": [
                    {
                        "name": instance.get("name") or instance["id"],
                        "request": request,
                        "expect": instance["resp"],
                    }
                ],
                "__source__": str(path),
            }
        )
    return expanded


def _normalize_case_request(request: Any, operation_id: str) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("case req must be an object")
    normalized = dict(request)
    if "body" in normalized:
        if "json" in normalized:
            raise ValueError("case req cannot contain both body and json")
        normalized["json"] = normalized.pop("body")
    normalized["protocol"] = "http"
    normalized["api"] = operation_id
    return normalized
