"""Side-effect-free adapter for the external fs-qa-knowledge Case Provider."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .contracts import content_hash
from .errors import ContractError, SecurityPolicyError

INSPECTION_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "case-provider-inspection.json"
LAYER_HINTS = (
    ("contract", "contract"),
    ("契约", "contract"),
    ("e2e", "e2e"),
    ("端到端", "e2e"),
    ("frontend", "frontend"),
    ("前端", "frontend"),
    ("backend", "backend"),
    ("后端", "backend"),
    ("接口", "backend"),
    ("api", "backend"),
)
CONCRETE_ORACLE = re.compile(r"\b(?:s\d{8,}|\d{9,})\b|FailureCode\s*==|Error\.Code")


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
            if manifest.get("schema_version") not in {None, "qa-agent-provider/1.0"}:
                blockers.append(
                    {
                        "code": "provider_manifest_schema_unsupported",
                        "message": "Provider manifest schema_version must be qa-agent-provider/1.0",
                    }
                )
            if manifest.get("mode") != "artifact_only":
                blockers.append(
                    {
                        "code": "artifact_only_mode_not_declared",
                        "message": "Provider manifest does not declare artifact_only mode",
                    }
                )
            if manifest.get("input_contract") != "case-provider-input/1.0":
                blockers.append(
                    {
                        "code": "provider_input_contract_unsupported",
                        "message": "Provider input contract must be case-provider-input/1.0",
                    }
                )
            if manifest.get("output_contract") != "case-provider-output/1.0":
                blockers.append(
                    {
                        "code": "provider_output_contract_unsupported",
                        "message": "Provider output contract must be case-provider-output/1.0",
                    }
                )
            if not isinstance(manifest.get("entrypoint"), str) or not str(
                manifest.get("entrypoint")
            ).strip():
                blockers.append(
                    {
                        "code": "provider_entrypoint_invalid",
                        "message": "Provider entrypoint must be a non-empty string",
                    }
                )
            if manifest.get("side_effects"):
                blockers.append(
                    {
                        "code": "provider_side_effects_declared",
                        "message": "Provider manifest declares external side effects",
                    }
                )
            elif manifest.get("side_effects") != []:
                blockers.append(
                    {
                        "code": "provider_side_effects_invalid",
                        "message": "Provider side_effects must be an empty array",
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
            for field in ("feature", "title", "case_type"):
                if not str(candidate.get(field) or "").strip():
                    raise ContractError(
                        f"Case Provider candidate {index}.{field} must be non-empty"
                    )
            if candidate.get("priority") not in {"P0", "P1", "P2"}:
                raise ContractError(
                    f"Case Provider candidate {index}.priority is unsupported"
                )
            for field in ("preconditions", "steps", "expected", "source_refs"):
                value = candidate.get(field)
                if not isinstance(value, list) or (
                    field in {"steps", "expected", "source_refs"} and not value
                ):
                    raise ContractError(
                        f"Case Provider candidate {index}.{field} must be a valid list"
                    )
            candidate_ids.add(candidate_id)
        return {
            "schema_version": "case-provider-draft/1.0",
            "provider_id": "fs-qa-knowledge",
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


def validate_provider_case_mappings(
    provider_draft: Mapping[str, Any],
    test_design: Mapping[str, Any],
) -> None:
    """Require every Provider Case to map to one distinct Test Case IR parent."""

    candidates = provider_draft.get("candidates", [])
    if not isinstance(candidates, list):
        raise ContractError("Case Provider draft candidates must be a list")
    provider_case_ids = {
        str(item.get("id") or "") for item in candidates if isinstance(item, Mapping)
    }
    if not provider_case_ids:
        return
    if "" in provider_case_ids or len(provider_case_ids) != len(candidates):
        raise ContractError("Case Provider draft Case IDs must be unique and non-empty")

    parent_cases = test_design.get("parent_cases", [])
    mappings = test_design.get("provider_case_mappings")
    if not isinstance(parent_cases, list) or not isinstance(mappings, list):
        raise ContractError(
            "A08 must include provider_case_mappings when Provider Cases are present"
        )
    parent_case_ids = {
        str(item.get("id") or "")
        for item in parent_cases
        if isinstance(item, Mapping)
    }
    mapped_provider_ids: list[str] = []
    mapped_ir_ids: list[str] = []
    for index, item in enumerate(mappings):
        if not isinstance(item, Mapping):
            raise ContractError(f"provider_case_mappings[{index}] must be an object")
        provider_case_id = str(item.get("provider_case_id") or "")
        test_case_ir_id = str(item.get("test_case_ir_id") or "")
        if not provider_case_id or not test_case_ir_id:
            raise ContractError(
                f"provider_case_mappings[{index}] must bind both Case IDs"
            )
        mapped_provider_ids.append(provider_case_id)
        mapped_ir_ids.append(test_case_ir_id)
    if len(mapped_provider_ids) != len(set(mapped_provider_ids)):
        raise ContractError("A08 maps a Provider Case more than once")
    if len(mapped_ir_ids) != len(set(mapped_ir_ids)):
        raise ContractError("A08 maps multiple Provider Cases to one Test Case IR")
    if set(mapped_provider_ids) != provider_case_ids:
        raise ContractError("A08 must map every Provider Case exactly once")
    if not set(mapped_ir_ids) <= parent_case_ids:
        raise ContractError("A08 Provider mapping references an unknown Test Case IR")


def load_case_provider_inspection() -> dict[str, Any]:
    with INSPECTION_PATH.open(encoding="utf-8") as handle:
        record = json.load(handle)
    if not isinstance(record, dict):
        raise ContractError("Case Provider inspection record must be an object")
    return record


def reviewed_provider_commits(
    inspection: Mapping[str, Any] | None = None,
) -> set[str]:
    record = dict(inspection or load_case_provider_inspection())
    commits = {str(record.get("reviewed_commit") or "")}
    for item in record.get("historical_commits", []):
        if isinstance(item, Mapping):
            commits.add(str(item.get("commit") or ""))
        elif isinstance(item, str):
            commits.add(item)
    commits.discard("")
    return commits


def apply_reviewed_provider_commit_gate(
    capability: Mapping[str, Any],
    *,
    repository_id: str,
) -> dict[str, Any]:
    result = dict(capability)
    if repository_id != "fs-qa-knowledge":
        return result
    commit = str(result.get("provider_commit") or "")
    if commit in reviewed_provider_commits():
        result["reviewed_commit_pinned"] = True
        return result
    blockers = [
        item
        for item in result.get("blockers", [])
        if isinstance(item, Mapping)
    ]
    blockers.append(
        {
            "code": "unreviewed_provider_commit",
            "message": (
                f"fs-qa-knowledge commit {commit} is not the reviewed pin; "
                "update knowledge/case-provider-inspection.json after a new review"
            ),
        }
    )
    result["blockers"] = blockers
    result["status"] = "incompatible"
    result["supported_mode"] = None
    result["reviewed_commit_pinned"] = False
    return result


def source_ref_ids(source_refs: Any) -> set[str]:
    ids: set[str] = set()
    if not isinstance(source_refs, list):
        return ids
    for ref in source_refs:
        if isinstance(ref, str) and ref:
            ids.add(ref)
            ids.add(ref.split(":", 1)[0])
        elif isinstance(ref, Mapping):
            value = str(ref.get("id") or "")
            if value:
                ids.add(value)
    return ids


def infer_provider_case_layer(case_type: str, title: str) -> str:
    text = f"{case_type} {title}".lower()
    for hint, layer in LAYER_HINTS:
        if hint.lower() in text:
            return layer
    return "scenario"


def complete_provider_parent_case(
    candidate: Mapping[str, Any],
    *,
    index: int,
    risk: str,
    priority: str,
    required_layers: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]] | None:
    provider_case_id = str(candidate.get("id") or "")
    expected_raw = candidate.get("expected", [])
    if not provider_case_id or not isinstance(expected_raw, list) or not expected_raw:
        return None
    intent_id = f"PROVIDER-INTENT-{index:03d}"
    case_id = f"PROVIDER-CASE-{index:03d}"
    source_refs = deepcopy(candidate.get("source_refs", []))
    if not isinstance(source_refs, list):
        source_refs = []
    source_ref = ""
    if source_refs:
        first = source_refs[0]
        if isinstance(first, str):
            source_ref = first
        elif isinstance(first, Mapping):
            source_ref = str(first.get("id") or "")
    if not source_ref:
        source_ref = f"provider:{provider_case_id}"
    layer = infer_provider_case_layer(
        str(candidate.get("case_type") or ""),
        str(candidate.get("title") or ""),
    )
    expected_items: list[dict[str, Any]] = []
    for expected_index, description in enumerate(expected_raw, 1):
        text = str(description)
        if CONCRETE_ORACLE.search(text):
            oracle = {
                "type": "deterministic",
                "observation_point": "backend_exception.code",
                "matcher": "equals",
                "source_ref": source_ref,
            }
        else:
            oracle = {
                "type": "human_review",
                "observation_point": "structured_manual_result",
                "matcher": "manual_confirmation",
                "source_ref": source_ref,
            }
        expected_items.append(
            {
                "id": f"EXP-{expected_index:02d}",
                "description": text,
                "oracle": oracle,
            }
        )
    human_oracles = any(item["oracle"]["type"] == "human_review" for item in expected_items)
    deterministic_oracles = any(
        item["oracle"]["type"] == "deterministic" for item in expected_items
    )
    automation_candidate = (
        deterministic_oracles
        and not human_oracles
        and layer in {"backend", "contract"}
    )
    if automation_candidate:
        allowed_modes = ["automated"]
        required_evidence = ["response_body"]
    elif deterministic_oracles and human_oracles:
        allowed_modes = ["automated", "manual"]
        required_evidence = ["response_body", "structured_manual_result"]
    else:
        allowed_modes = ["manual"]
        required_evidence = ["structured_manual_result"]
    preconditions = deepcopy(candidate.get("preconditions", []))
    if not isinstance(preconditions, list):
        preconditions = []
    intent = {
        "id": intent_id,
        "objective": str(candidate.get("feature") or candidate.get("title") or ""),
        "risk": risk,
        "required_layers": list(required_layers),
        "source_refs": source_refs,
    }
    case = {
        "id": case_id,
        "parent_case_id": None,
        "intent_ids": [intent_id],
        "title": str(candidate.get("title") or provider_case_id),
        "layer": layer,
        "required_layers": list(required_layers),
        "risk": risk,
        "priority": priority,
        "source_refs": source_refs,
        "preconditions": preconditions,
        "test_data": {
            "provider_case_id": provider_case_id,
            "feature": str(candidate.get("feature") or ""),
            "case_type": str(candidate.get("case_type") or ""),
            "preconditions": deepcopy(preconditions),
        },
        "steps": deepcopy(candidate.get("steps", [])),
        "expected": expected_items,
        "cleanup": [],
        "execution_policy": {
            "allowed_modes": allowed_modes,
            "required_evidence": required_evidence,
        },
        "automation_candidate": automation_candidate,
    }
    return intent, case, {
        "provider_case_id": provider_case_id,
        "test_case_ir_id": case_id,
    }


def compare_provider_shadow(
    provider_draft: Mapping[str, Any],
    test_design: Mapping[str, Any],
    *,
    requirements: list[Mapping[str, Any]] | None = None,
    provider_status: str = "incompatible",
    a09_approved: bool = False,
    n04_valid: bool = False,
    g02_mapping_complete: bool = False,
) -> dict[str, Any]:
    mapping_error = None
    try:
        validate_provider_case_mappings(provider_draft, test_design)
        mapping_ok = True
    except ContractError as error:
        mapping_ok = False
        mapping_error = str(error)
    requirement_items = requirements or []
    covered = {
        str(item.get("requirement_id"))
        for item in test_design.get("coverage_matrix", [])
        if isinstance(item, Mapping) and item.get("case_ids")
    }
    uncovered = [
        str(item.get("id"))
        for item in requirement_items
        if isinstance(item, Mapping) and str(item.get("id") or "") not in covered
    ]
    parent_ids = {
        str(item.get("id"))
        for item in test_design.get("parent_cases", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    mapped_ir_ids = {
        str(item.get("test_case_ir_id"))
        for item in test_design.get("provider_case_mappings", [])
        if isinstance(item, Mapping) and item.get("test_case_ir_id")
    }
    production_enabled = (
        provider_status == "compatible"
        and mapping_ok
        and not uncovered
        and a09_approved
        and n04_valid
        and g02_mapping_complete
    )
    return {
        "schema_version": "case-provider-shadow-comparison/1.0",
        "provider_status": provider_status,
        "mapping_complete": mapping_ok,
        "mapping_error": mapping_error,
        "uncovered_requirement_ids": uncovered,
        "supplemental_case_ids": sorted(parent_ids - mapped_ir_ids),
        "a09_approved": a09_approved,
        "n04_valid": n04_valid,
        "g02_mapping_complete": g02_mapping_complete,
        "production_enabled": production_enabled,
        "mode": "enabled" if production_enabled else "shadow_only",
    }
