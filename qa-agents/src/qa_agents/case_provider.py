"""Side-effect-free adapter for the external fs-qa-knowledge Case Provider."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any

from .contracts import content_hash
from .errors import ContractError, SecurityPolicyError


FULL_COMMIT = re.compile(r"[0-9a-f]{40}")
TABLE_SEPARATOR = re.compile(r"^:?-{3,}:?$")


class CaseProviderCapabilityProbe:
    """Determine compatibility from a frozen provider commit, never from a mutable worktree."""

    REQUIRED_MANIFEST = {
        "schema_version",
        "mode",
        "entrypoint",
        "input_contract",
        "output_contract",
        "side_effects",
    }

    def probe(
        self,
        provider_commit: str,
        skill_documents: Mapping[str, str],
        provider_manifest: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not FULL_COMMIT.fullmatch(provider_commit):
            raise ContractError("Case Provider capability must pin a full 40-character commit")

        blockers: list[dict[str, str]] = []
        manifest = dict(provider_manifest or {})
        if not manifest:
            blockers.append(
                {
                    "code": "provider_manifest_missing",
                    "message": "Frozen provider commit has no qa-agent-provider.json manifest",
                }
            )
        else:
            for key in sorted(self.REQUIRED_MANIFEST - set(manifest)):
                blockers.append(
                    {
                        "code": "provider_manifest_field_missing",
                        "message": f"Provider manifest is missing {key}",
                    }
                )
            if manifest.get("mode") != "artifact_only":
                blockers.append(
                    {
                        "code": "artifact_only_mode_not_declared",
                        "message": "Provider manifest does not declare artifact_only mode",
                    }
                )
            if manifest.get("side_effects"):
                blockers.append(
                    {
                        "code": "provider_side_effects_declared",
                        "message": "Provider manifest declares external side effects",
                    }
                )

        combined = "\n".join(skill_documents.values())
        mandatory_upload_signals = (
            "FS 对象上传（禁止跳过）",
            "强制调用**，通过 `md2excel`",
            "未执行 Step 10.1",
        )
        if any(signal in combined for signal in mandatory_upload_signals):
            blockers.append(
                {
                    "code": "mandatory_external_side_effect_workflow",
                    "message": "Provider workflow mandates conversion or upload side effects",
                }
            )

        return {
            "schema_version": "case-provider-capability/1.0",
            "provider_id": "fs-qa-knowledge",
            "provider_commit": provider_commit,
            "status": "compatible" if not blockers else "incompatible",
            "supported_mode": "artifact_only" if not blockers else None,
            "input_contract": manifest.get("input_contract"),
            "output_contract": manifest.get("output_contract"),
            "entrypoint": manifest.get("entrypoint"),
            "external_side_effects": bool(manifest.get("side_effects")),
            "blockers": blockers,
            "evidence": [
                {"path": path, "content_hash": content_hash(content)}
                for path, content in sorted(skill_documents.items())
            ],
            "mutable_worktree_used": False,
        }


class CaseProviderAdapter:
    def adapt(
        self,
        provider_output: Mapping[str, Any],
        *,
        expected_commit: str | None = None,
    ) -> dict[str, Any]:
        metadata = provider_output.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ContractError("Case Provider metadata must be an object")
        if metadata.get("mode") != "artifact_only":
            raise SecurityPolicyError("Case Provider must run in artifact_only mode")
        provider_commit = str(metadata.get("provider_commit", ""))
        if not FULL_COMMIT.fullmatch(provider_commit):
            raise ContractError("Case Provider output must pin a full 40-character commit")
        if expected_commit is not None and provider_commit != expected_commit:
            raise ContractError("Case Provider output commit does not match the frozen capability")
        if metadata.get("output_contract") != "case-provider-output/1.0":
            raise ContractError("Case Provider output contract is unsupported")
        side_effects = metadata.get("side_effects", [])
        if side_effects:
            raise SecurityPolicyError("Case Provider output declares external side effects")
        candidates = provider_output.get("candidates", [])
        if not isinstance(candidates, list):
            raise ContractError("Case Provider candidates must be a list")
        candidate_ids: set[str] = set()
        required = {
            "id",
            "feature",
            "title",
            "priority",
            "case_type",
            "preconditions",
            "steps",
            "expected",
            "source_refs",
        }
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                raise ContractError(f"Case Provider candidate {index} must be an object")
            missing = required - set(candidate)
            if missing:
                raise ContractError(
                    f"Case Provider candidate {index} is missing {sorted(missing)}"
                )
            candidate_id = str(candidate.get("id", ""))
            if not candidate_id or candidate_id in candidate_ids:
                raise ContractError("Case Provider candidate IDs must be unique and non-empty")
            candidate_ids.add(candidate_id)
        return {
            "schema_version": "case-provider-draft/1.0",
            "provider_commit": provider_commit,
            "candidates": deepcopy(candidates),
            "candidate_count": len(candidates),
            "external_side_effects": False,
            "source_format": metadata.get("source_format", "json"),
        }

    def from_markdown_bundle(
        self,
        testcase_markdown: str,
        metadata: Mapping[str, Any],
        *,
        expected_commit: str | None = None,
    ) -> dict[str, Any]:
        """Parse the provider's documented merged Markdown table into draft candidates."""

        rows: list[list[str]] = []
        for line in testcase_markdown.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("|") and stripped.endswith("|")):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) != 8 or all(TABLE_SEPARATOR.fullmatch(cell) for cell in cells):
                continue
            rows.append(cells)
        if not rows or rows[0] != [
            "用例ID",
            "功能点",
            "用例标题",
            "优先级",
            "用例类型",
            "前置条件",
            "测试步骤",
            "预期结果",
        ]:
            raise ContractError("Case Provider Markdown does not use the required merged table")

        source_refs = metadata.get("source_refs", [])
        if not isinstance(source_refs, list) or not source_refs:
            raise ContractError("Case Provider bundle must declare source_refs")
        candidates = []
        for cells in rows[1:]:
            candidates.append(
                {
                    "id": cells[0],
                    "feature": cells[1],
                    "title": cells[2],
                    "priority": cells[3],
                    "case_type": cells[4],
                    "preconditions": self._split_steps(cells[5]),
                    "steps": self._split_steps(cells[6]),
                    "expected": self._split_steps(cells[7]),
                    "source_refs": deepcopy(source_refs),
                }
            )
        return self.adapt(
            {
                "metadata": {**dict(metadata), "source_format": "markdown_table"},
                "candidates": candidates,
            },
            expected_commit=expected_commit,
        )

    @staticmethod
    def _split_steps(value: str) -> list[str]:
        return [item.strip() for item in re.split(r"<br\s*/?>", value) if item.strip()]
