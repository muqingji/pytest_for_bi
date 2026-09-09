from pathlib import Path
import subprocess

import pytest

from qa_agents.data_integrity import (
    integrity_evidence_valid,
    required_validity_contract,
    run_bug_finder_integrity_probes,
    validate_validity_contract,
)
from qa_agents.errors import SecurityPolicyError


def _root(tmp_path: Path) -> Path:
    cli = tmp_path / ".agents/skills/fx-ops/scripts/fx_ops_cli.py"
    cli.parent.mkdir(parents=True)
    cli.write_text("# public entrypoint\n", encoding="utf-8")
    return tmp_path


def test_bug_finder_adapter_requires_all_four_chart_layers(tmp_path: Path) -> None:
    seen = []

    def runner(command, **kwargs):
        seen.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '{"ok":true,"rows":[{"id":"1"}]}', "")

    packet = run_bug_finder_integrity_probes(
        [{"check": check, "argv": ["idp", "query", "bi", "--sql", "SELECT id FROM t WHERE ei='x' LIMIT 1", "-j"]}
         for check in ("source_data", "warehouse_dimension", "warehouse_aggregation", "chart_topology")],
        bug_finder_root=_root(tmp_path), runner=runner,
    )
    assert packet["valid"] is True
    assert integrity_evidence_valid(packet) is True
    assert all(call[0][5:8] == ["run", "fxops_query", "--"] for call in seen)


def test_bug_finder_adapter_fails_closed_on_empty_result(tmp_path: Path) -> None:
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, '{"ok":true,"rows":[]}', "")

    packet = run_bug_finder_integrity_probes(
        [{"check": "source_data", "argv": ["idp", "query", "paas", "--sql", "SELECT id FROM t WHERE tenant_id='x' LIMIT 1", "-j"]}],
        bug_finder_root=_root(tmp_path), runner=runner,
    )
    assert packet["valid"] is False
    assert packet["checks"][0]["status"] == "failed"


def test_bug_finder_adapter_rejects_mutating_sql(tmp_path: Path) -> None:
    with pytest.raises(SecurityPolicyError, match="not read-only"):
        run_bug_finder_integrity_probes(
            [{"check": "source_data", "argv": ["idp", "query", "bi", "--sql", "DELETE FROM t WHERE ei='x' LIMIT 1", "-j"]}],
            bug_finder_root=_root(tmp_path),
        )


def test_chart_validity_contract_is_exact_and_fail_closed() -> None:
    contract = required_validity_contract("stat_chart")
    validate_validity_contract(contract, resource_type="stat_chart", path="resource")
    contract["required_checks"].remove("chart_topology")
    with pytest.raises(SecurityPolicyError, match="incomplete"):
        validate_validity_contract(contract, resource_type="stat_chart", path="resource")
