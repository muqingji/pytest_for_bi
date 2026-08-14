from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_four_product_sources_have_explicit_collector_routes() -> None:
    value = json.loads(
        (ROOT / "knowledge/product-test-knowledge-sources.json").read_text(
            encoding="utf-8"
        )
    )
    product = value["sources"][:4]
    assert {item["collector_skill"] for item in product} == {
        "kdocs-authorized-snapshot/1.0.0",
        "fxiaoke-help-snapshot/1.0.0",
        "lexiang-authorized-snapshot/1.0.0",
    }
    assert all(item["collector_status"] for item in product)


def test_collectors_reject_unapproved_hosts(tmp_path: Path) -> None:
    cases = [("fxiaoke-help-snapshot/scripts/capture_help.py", "https://example.com/help")]
    for relative, url in cases:
        result = subprocess.run(
            ["python3", str(ROOT / "skills" / relative), url, "--output", str(tmp_path / "out.json")],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "unapproved" in result.stderr


def test_registry_authorizes_snapshot_skills_only_for_k01() -> None:
    value = json.loads(
        (ROOT / "policies/backend-skill-registry.json").read_text(encoding="utf-8")
    )
    expected = {
        "kdocs-authorized-snapshot",
        "lexiang-authorized-snapshot",
        "fxiaoke-help-snapshot",
    }
    entries = [item for item in value["skills"] if item["id"] in expected]
    assert {item["id"] for item in entries} == expected
    assert all(item["agents"] == ["K01"] for item in entries)
    assert all(item["side_effect"] == "artifact_only" for item in entries)


def test_authorized_collectors_support_explicit_loopback_cdp() -> None:
    script = (ROOT / "skills/lexiang-authorized-snapshot/scripts/realtime_query.js").read_text()
    assert "connectOverCDP" in script
    assert "credentials:\"same-origin\"" in script
    assert "document.cookie" not in script
    assert "localStorage" not in script


def test_realtime_query_is_index_first_and_detail_is_explicit() -> None:
    script = (ROOT / "skills/lexiang-authorized-snapshot/scripts/realtime_query.js").read_text()
    assert 'command==="search"' in script
    assert 'command==="detail"' in script
    assert "slice(0,20)" in script
    assert 'querySelector(".thumbnail_workspace")' in script
    assert 'querySelectorAll(".thumbnail_slide")' in script
    assert "full-category" not in script
    assert not (ROOT / "skills/lexiang-authorized-snapshot/scripts/capture_category.py").exists()
    assert not (ROOT / "skills/kdocs-authorized-snapshot/scripts/capture.py").exists()


def test_product_sources_use_realtime_query_and_persistent_session() -> None:
    value = json.loads((ROOT / "knowledge/product-test-knowledge-sources.json").read_text())
    selected = [item for item in value["sources"] if item["id"] in {
        "bi-product-whitepaper-kdocs", "lexiang-bi-feature-wiki", "lexiang-bi-faq"
    }]
    assert all("realtime" in item["collection_mode"] for item in selected)
    assert all(item["session_skill"] == "authorized-product-browser-session/1.0.0" for item in selected)
    assert all("snapshot" not in item for item in selected)


def test_bug_finder_adapter_is_k01_only_and_historical_context() -> None:
    registry = json.loads(
        (ROOT / "policies/backend-skill-registry.json").read_text(encoding="utf-8")
    )
    entry = next(
        item for item in registry["skills"] if item["id"] == "bug-finder-test-knowledge"
    )
    assert entry["agents"] == ["K01"]
    assert entry["side_effect"] == "artifact_only"

    sources = json.loads(
        (ROOT / "knowledge/product-test-knowledge-sources.json").read_text(
            encoding="utf-8"
        )
    )
    source = next(item for item in sources["sources"] if item["id"] == "bug-finder-diagnostic-knowledge")
    assert source["trust_level"] == "historical_context_only"
    assert source["contract_authority"] is False


def test_bug_finder_adapter_returns_revision_bound_allowed_evidence(tmp_path: Path) -> None:
    repository = tmp_path / "bug-finder"
    (repository / ".agents/skills/fx-ops-bi/references").mkdir(parents=True)
    (repository / "docs/knowledge").mkdir(parents=True)
    (repository / "output").mkdir()
    (repository / ".agents/skills/fx-ops-bi/references/rules.md").write_text(
        "结果集筛选历史边界\n", encoding="utf-8"
    )
    (repository / "docs/knowledge/case.md").write_text(
        "结果集筛选曾出现权限缺陷\n", encoding="utf-8"
    )
    (repository / "output/secret.md").write_text("结果集筛选 token\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(repository), "-c", "user.name=QA", "-c",
            "user.email=qa@example.invalid", "commit", "-m", "fixture",
        ],
        check=True,
        capture_output=True,
    )

    output = tmp_path / "evidence.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills/bug-finder-test-knowledge/scripts/query.py"),
            "--repository", str(repository),
            "--keyword", "结果集筛选",
            "--output", str(output),
        ],
        check=True,
    )
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["revision"]
    assert value["contract_authority"] is False
    assert len(value["matches"]) == 2
    assert all(not item["path"].startswith("output/") for item in value["matches"])
    assert {item["authority"] for item in value["matches"]} == {"historical_context_only"}
