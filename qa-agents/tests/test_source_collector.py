import subprocess
from pathlib import Path

import pytest

from qa_agents.errors import InputError, SecurityPolicyError
from qa_agents.source_collector import ReadOnlyGitCollector, RepositoryRegistry


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def init_repo(path: Path) -> None:
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.name", "QA Test")
    git(path, "config", "user.email", "qa@example.test")


def test_collector_reads_fixed_commits_from_disposable_clones(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    business = tmp_path / "business"
    provider = tmp_path / "provider"
    init_repo(docs)
    init_repo(business)
    init_repo(provider)

    story = docs / "stories" / "story-1"
    (story / "product").mkdir(parents=True)
    (story / "dev").mkdir()
    (story / "product" / "prd.md").write_text(
        "# Requirement\n- 返回明确错误码\n# Sibling\n- 不属于目标需求\n",
        encoding="utf-8",
    )
    (story / "dev" / "tech.md").write_text("# Design\n- API exposes trace logs\n", encoding="utf-8")
    git(docs, "add", ".")
    git(docs, "commit", "-qm", "documents")
    docs_commit = git(docs, "rev-parse", "HEAD")

    source = business / "Service.java"
    source.write_text("class Service {}\n", encoding="utf-8")
    git(business, "add", "Service.java")
    git(business, "commit", "-qm", "base")
    base = git(business, "rev-parse", "HEAD")
    source.write_text("class Service { int code = 403; }\n", encoding="utf-8")
    git(business, "commit", "-qam", "change")
    head = git(business, "rev-parse", "HEAD")

    (provider / "skills" / "requirement-analyze").mkdir(parents=True)
    (provider / "skills" / "testcase-generate").mkdir(parents=True)
    (provider / "skills" / "requirement-analyze" / "SKILL.md").write_text(
        "# Requirement Analyze\n", encoding="utf-8"
    )
    (provider / "skills" / "testcase-generate" / "SKILL.md").write_text(
        "### Step 10.1：强制检查点——FS 对象上传（禁止跳过）\n",
        encoding="utf-8",
    )
    git(provider, "add", ".")
    git(provider, "commit", "-qm", "provider")
    provider_commit = git(provider, "rev-parse", "HEAD")

    registry = RepositoryRegistry(
        [
            {"id": "docs", "url": str(docs), "access_class": "document_source_read_only"},
            {"id": "business", "url": str(business), "access_class": "business_source_read_only"},
            {
                "id": "provider",
                "url": str(provider),
                "access_class": "case_capability_provider_read_only",
            },
        ]
    )
    snapshot = {
        "document_source": {"repository": str(docs), "commit": docs_commit},
        "implementation_source": {
            "repository": str(business),
            "repository_id": "business",
            "comparison": {"mode": "first_parent", "base": base, "head": head},
            "change_summary": {"changed_paths": ["Service.java"]},
        },
        "reference_sources": [
            {
                "repository_id": "provider",
                "repository": str(provider),
                "commit": provider_commit,
                "access_class": "case_capability_provider_read_only",
            }
        ],
    }
    workflow_input = {
        "requirement_scope": {
            "story_path": "stories/story-1",
            "requirement_file": "product/prd.md",
            "technical_design_files": ["dev/tech.md"],
            "heading": "Requirement",
        }
    }

    material = ReadOnlyGitCollector(registry).collect(snapshot, workflow_input)
    assert "返回明确错误码" in material["requirement"]["content"]
    assert "不属于目标需求" not in material["requirement"]["content"]
    assert "trace logs" in material["technical_design"]["content"]
    assert "+class Service { int code = 403; }" in material["implementation_diff"]["content"]
    assert material["collection"]["mode"] == "remote_read_only_disposable_clone"
    assert material["case_provider_capability"]["status"] == "incompatible"
    assert material["case_provider_capability"]["provider_commit"] == provider_commit
    assert {item["code"] for item in material["case_provider_capability"]["blockers"]} == {
        "provider_manifest_missing",
        "mandatory_external_side_effect_workflow",
    }


def test_collector_rejects_unregistered_repository() -> None:
    registry = RepositoryRegistry([])
    with pytest.raises(SecurityPolicyError):
        registry.require("git@example/unknown.git", {"business_source_read_only"})


def test_frozen_line_range_must_still_contain_expected_heading() -> None:
    content = "intro\n6. Target requirement\nbody\n7. Sibling\n"
    selected = ReadOnlyGitCollector._select_line_range(content, "2-3", "Target requirement")
    assert selected == "6. Target requirement\nbody\n"
    with pytest.raises(InputError, match="stale"):
        ReadOnlyGitCollector._select_line_range(content, "3-4", "Target requirement")


def test_declared_blob_mismatch_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "doc.md").write_text("content\n", encoding="utf-8")
    git(repo, "add", "doc.md")
    git(repo, "commit", "-qm", "document")
    commit = git(repo, "rev-parse", "HEAD")
    collector = ReadOnlyGitCollector(RepositoryRegistry([]))
    with pytest.raises(InputError, match="blob mismatch"):
        collector._verify_blob(repo, commit, "doc.md", "0" * 40)


@pytest.mark.parametrize("path", ["../secret", "/absolute/path"])
def test_collector_rejects_unsafe_repository_paths(path: str) -> None:
    with pytest.raises(SecurityPolicyError):
        ReadOnlyGitCollector._safe_repo_path(path)
