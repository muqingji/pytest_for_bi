"""N01 read-only remote Git evidence collector.

Only this deterministic component receives Git read credentials. It clones registered
repositories into disposable directories and never exposes Git commands to an Agent.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Any

from .case_provider import CaseProviderCapabilityProbe
from .contracts import content_hash
from .errors import InputError, SecurityPolicyError


class RepositoryRegistry:
    def __init__(self, entries: list[Mapping[str, Any]]) -> None:
        self.by_url = {str(item["url"]): dict(item) for item in entries}

    @classmethod
    def from_file(cls, path: Path) -> "RepositoryRegistry":
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
        return cls(value["repositories"])

    def require(self, url: str, expected_access: set[str]) -> Mapping[str, Any]:
        entry = self.by_url.get(url)
        if entry is None:
            raise SecurityPolicyError(f"Repository is not registered: {url}")
        if entry.get("access_class") not in expected_access:
            raise SecurityPolicyError(f"Repository has unexpected access class: {url}")
        return entry


class ReadOnlyGitCollector:
    def __init__(
        self,
        registry: RepositoryRegistry,
        max_bytes: int = 5_000_000,
        command_timeout_seconds: int = 300,
    ) -> None:
        self.registry = registry
        self.max_bytes = max_bytes
        self.command_timeout_seconds = command_timeout_seconds

    @staticmethod
    def _safe_repo_path(path: str) -> str:
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts:
            raise SecurityPolicyError(f"Unsafe repository path: {path}")
        return str(pure)

    def _git(self, arguments: list[str], cwd: Path | None = None) -> bytes:
        environment = dict(os.environ)
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=cwd,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.command_timeout_seconds,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise InputError(
                f"Read-only Git command timed out after {self.command_timeout_seconds}s"
            ) from error
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise InputError(f"Read-only Git command failed: {message}")
        return result.stdout

    def _clone(self, url: str, target: Path) -> None:
        self._git(["clone", "--no-checkout", "--filter=blob:none", "--quiet", url, str(target)])

    def _verify_blob(
        self,
        repo: Path,
        commit: str,
        path: str,
        expected_blob: str | None,
    ) -> None:
        if not expected_blob:
            return
        actual = self._git(["rev-parse", f"{commit}:{path}"], repo).decode().strip()
        if actual != expected_blob:
            raise InputError(
                f"Frozen blob mismatch for {path}: expected {expected_blob}, got {actual}"
            )

    def _bounded(self, value: bytes, label: str) -> str:
        if len(value) > self.max_bytes:
            raise InputError(f"{label} exceeds the configured {self.max_bytes}-byte limit")
        return value.decode("utf-8", errors="replace")

    @staticmethod
    def _select_markdown_heading(content: str, heading: str, occurrence: int = 1) -> str:
        if not heading:
            raise InputError("Requirement heading is required")
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
        matches: list[tuple[int, int]] = []
        lines = content.splitlines()
        for index, line in enumerate(lines):
            match = heading_pattern.match(line.strip())
            if match and match.group(2).strip() == heading.strip():
                matches.append((index, len(match.group(1))))
        if occurrence < 1 or len(matches) < occurrence:
            raise InputError(
                f"Requirement heading occurrence not found: {heading!r} #{occurrence}"
            )
        start, level = matches[occurrence - 1]
        end = len(lines)
        for index in range(start + 1, len(lines)):
            match = heading_pattern.match(lines[index].strip())
            if match and len(match.group(1)) <= level:
                end = index
                break
        return "\n".join(lines[start:end]).strip() + "\n"

    @staticmethod
    def _select_line_range(content: str, observed_lines: str, expected_text: str) -> str:
        match = re.fullmatch(r"(\d+)-(\d+)", observed_lines.strip())
        if not match:
            raise InputError(f"Invalid observed line range: {observed_lines}")
        start, end = (int(value) for value in match.groups())
        lines = content.splitlines()
        if start < 1 or end < start or end > len(lines):
            raise InputError(f"Observed line range is outside document: {observed_lines}")
        selected = "\n".join(lines[start - 1 : end]).strip() + "\n"
        if expected_text and expected_text not in selected:
            raise InputError(
                "Frozen requirement selection is stale: expected heading is outside observed lines"
            )
        return selected

    def collect(self, snapshot: Mapping[str, Any], workflow_input: Mapping[str, Any]) -> dict[str, Any]:
        document_source = snapshot.get("document_source", {})
        document_url = str(document_source.get("repository", ""))
        self.registry.require(document_url, {"document_source_read_only"})
        document_commit = str(document_source.get("commit", ""))
        if not document_commit:
            raise InputError("Document source commit is required")

        implementation = snapshot.get("implementation_source", {})
        implementation_url = str(implementation.get("repository", ""))
        self.registry.require(implementation_url, {"business_source_read_only"})
        comparison = implementation.get("comparison", {})
        base = str(comparison.get("base", ""))
        head = str(comparison.get("head", ""))
        if comparison.get("mode") != "first_parent":
            raise InputError("Current collector requires the frozen first-parent ChangeSet")

        scope = workflow_input.get("requirement_scope", {})
        story_path = self._safe_repo_path(str(scope.get("story_path", "")))
        requirement_path = self._safe_repo_path(f"{story_path}/{scope.get('requirement_file', '')}")
        requirement_heading = str(scope.get("heading", ""))
        heading_occurrence = int(scope.get("heading_occurrence", 1))
        requirement_selection: Mapping[str, Any] = {}
        document_files = {
            str(item.get("path")): item
            for item in document_source.get("files", [])
            if isinstance(item, Mapping)
        }
        for file_entry in document_source.get("files", []):
            if isinstance(file_entry, Mapping) and file_entry.get("path") == requirement_path:
                candidate = file_entry.get("selection", {})
                if isinstance(candidate, Mapping):
                    requirement_selection = candidate
                break
        technical_paths = [
            self._safe_repo_path(f"{story_path}/{path}")
            for path in scope.get("technical_design_files", [])
        ]
        provider_source = next(
            (
                item
                for item in snapshot.get("reference_sources", [])
                if isinstance(item, Mapping)
                and item.get("access_class") == "case_capability_provider_read_only"
            ),
            None,
        )
        provider_capability: dict[str, Any] | None = None

        with tempfile.TemporaryDirectory(prefix="qa-agent-source-") as temporary:
            temporary_root = Path(temporary)
            document_repo = temporary_root / "documents"
            implementation_repo = temporary_root / "implementation"
            self._clone(document_url, document_repo)
            self._verify_blob(
                document_repo,
                document_commit,
                requirement_path,
                document_files.get(requirement_path, {}).get("git_blob"),
            )
            requirement_document = self._bounded(
                self._git(["show", f"{document_commit}:{requirement_path}"], document_repo),
                requirement_path,
            )
            observed_lines = str(requirement_selection.get("observed_lines", ""))
            if observed_lines:
                requirement = self._select_line_range(
                    requirement_document, observed_lines, requirement_heading
                )
                requirement_location = f"lines:{observed_lines}"
            else:
                requirement = self._select_markdown_heading(
                    requirement_document, requirement_heading, heading_occurrence
                )
                requirement_location = f"heading:{requirement_heading}#{heading_occurrence}"
            technical_parts = []
            for path in technical_paths:
                self._verify_blob(
                    document_repo,
                    document_commit,
                    path,
                    document_files.get(path, {}).get("git_blob"),
                )
                technical_parts.append(
                    self._bounded(
                        self._git(["show", f"{document_commit}:{path}"], document_repo), path
                    )
                )

            self._clone(implementation_url, implementation_repo)
            changed_paths = list(implementation.get("change_summary", {}).get("changed_paths", []))
            diff_arguments = ["diff", "--no-ext-diff", "--unified=40", base, head, "--"]
            diff_arguments.extend(self._safe_repo_path(path) for path in changed_paths)
            implementation_diff = self._bounded(
                self._git(diff_arguments, implementation_repo), "implementation diff"
            )

            if provider_source:
                provider_url = str(provider_source.get("repository", ""))
                self.registry.require(provider_url, {"case_capability_provider_read_only"})
                provider_commit = str(provider_source.get("commit", ""))
                if not provider_commit:
                    raise InputError("Case Provider commit is required")
                provider_repo = temporary_root / "case-provider"
                try:
                    self._clone(provider_url, provider_repo)
                    skill_paths = [
                        "skills/requirement-analyze/SKILL.md",
                        "skills/testcase-generate/SKILL.md",
                    ]
                    skill_documents = {
                        path: self._bounded(
                            self._git(["show", f"{provider_commit}:{path}"], provider_repo),
                            path,
                        )
                        for path in skill_paths
                    }
                    manifest: Mapping[str, Any] | None = None
                    try:
                        manifest_text = self._bounded(
                            self._git(
                                ["show", f"{provider_commit}:qa-agent-provider.json"],
                                provider_repo,
                            ),
                            "qa-agent-provider.json",
                        )
                        parsed_manifest = json.loads(manifest_text)
                        if not isinstance(parsed_manifest, Mapping):
                            raise InputError("Case Provider manifest must be a JSON object")
                        manifest = parsed_manifest
                    except InputError as error:
                        message = str(error)
                        if "does not exist" not in message and "exists on disk" not in message:
                            raise
                    provider_capability = CaseProviderCapabilityProbe().probe(
                        provider_commit, skill_documents, manifest
                    )
                except InputError as error:
                    provider_capability = {
                        "schema_version": "case-provider-capability/1.0",
                        "provider_id": str(
                            provider_source.get("repository_id", "fs-qa-knowledge")
                        ),
                        "provider_commit": provider_commit,
                        "status": "unavailable",
                        "supported_mode": None,
                        "external_side_effects": False,
                        "blockers": [
                            {"code": "provider_collection_failed", "message": str(error)}
                        ],
                        "evidence": [],
                        "mutable_worktree_used": False,
                    }

        material = {
            "schema_version": "source-material/1.0",
            "requirement": {
                "content": requirement,
                "content_hash": content_hash(requirement),
                "source_ref": {
                    "type": "requirement",
                    "id": requirement_path,
                    "location": requirement_location,
                },
            },
            "technical_design": {
                "content": "\n\n".join(technical_parts),
                "content_hash": content_hash(technical_parts),
                "source_ref": {
                    "type": "technical_design",
                    "id": ",".join(technical_paths),
                    "location": "whole_file",
                },
            },
            "implementation_diff": {
                "content": implementation_diff,
                "content_hash": content_hash(implementation_diff),
                "source_ref": {
                    "type": "change_set",
                    "id": f"{implementation.get('repository_id')}:{head}",
                    "location": f"{base}..{head}",
                },
            },
            "collection": {
                "mode": "remote_read_only_disposable_clone",
                "document_commit": document_commit,
                "implementation_base": base,
                "implementation_head": head,
                "credentials_embedded": False,
            },
        }
        if provider_capability is not None:
            material["case_provider_capability"] = provider_capability
        return material
