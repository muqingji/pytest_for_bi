"""gen-repo-catalog 的行为测试（不依赖真实 wiki-bot / ai-wiki 检出）。

覆盖：
- `domain_from_git_url`：gitUrl 最后两段（去 .git / 尾斜杠 / 嵌套 group）
- `describe`：front-matter description 优先；导航类噪声被跳过；`## 这是什么` 与
  profile 职责观察兜底；全部噪声时回落到首个非空候选
- `build_rows` / `render`：排序稳定、覆盖概览与主索引行数一致
- `main --check`：一致返回 0，数据源变化后返回 1（漂移可检出）

注：CLI 文件名是 `gen-repo-catalog.py`（带连字符），不是合法 Python 模块名，
故用 importlib spec 从路径加载。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

CLI_PATH = Path(__file__).resolve().parent / "gen-repo-catalog.py"

_spec = importlib.util.spec_from_file_location("gen_repo_catalog", CLI_PATH)
assert _spec is not None and _spec.loader is not None
catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catalog)


# ─── helpers ─────────────────────────────────────────────────────────────────


def _write_project(root: Path, group: str, project: str, name: str | None = None) -> Path:
    """在 ai-wiki 根下建一个域目录，含 README（带 description）。"""
    domain_dir = root / "domains" / group / project
    domain_dir.mkdir(parents=True)
    (domain_dir / "README.md").write_text(
        "---\n"
        f'title: "{project} 知识包"\n'
        f'description: "{project} 的职责说明"\n'
        "source_revision: abc123\n"
        "last_reviewed: 2026-09-10\n"
        "---\n"
        f"# {project}\n",
        encoding="utf-8",
    )
    return domain_dir


def _projects_json(tmp_path: Path, entries: list[tuple[str, str]]) -> Path:
    path = tmp_path / "projects.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "generatedAt": "2026-09-12T00:00:00.000Z",
                "projects": [
                    {
                        "name": f"{group}/{project}",
                        "gitUrl": f"https://git.example/{group}/{project}.git",
                        "aiWikiDomain": project,
                        "repoStatKeys": {"group": group, "project": project},
                        "layer": "backend",
                        "category": "java-service",
                        "techStack": ["maven"],
                    }
                    for group, project in entries
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


# ─── domain_from_git_url ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://git.example/paas/fs-metadata.git", "paas/fs-metadata"),
        ("https://git.example/paas/fs-metadata", "paas/fs-metadata"),
        ("https://git.example/AppServer/fs-crm-fmcg-wq/", "AppServer/fs-crm-fmcg-wq"),
        ("https://git.example/ai/deep/nested/repo.git", "nested/repo"),
        ("", ""),
        ("not-a-url", ""),
    ],
)
def test_domain_from_git_url(url: str, expected: str) -> None:
    assert catalog.domain_from_git_url(url) == expected


# ─── describe ────────────────────────────────────────────────────────────────


def test_describe_prefers_front_matter_description(tmp_path: Path) -> None:
    root = _write_project(tmp_path, "paas", "fs-metadata")
    result = catalog.describe(root, {}, "")
    assert result["desc"] == "fs-metadata 的职责说明"
    assert result["lastReviewed"] == "2026-09-10"
    assert result["revision"] == "abc123"


def test_describe_skips_navigation_noise(tmp_path: Path) -> None:
    domain_dir = tmp_path / "domains" / "sfa" / "fs-crm-sfa"
    domain_dir.mkdir(parents=True)
    (domain_dir / "README.md").write_text(
        "---\n"
        'description: "本页是任务路由入口：先说清覆盖范围"\n'
        "---\n"
        "# fs-crm-sfa\n"
        "\n"
        "## 这是什么\n"
        "\n"
        "SFA 售前售中业务前台，承载线索、客户、商机与订单主链路。\n"
        "\n"
        "## 页面清单\n"
        "\n"
        "见下表。\n",
        encoding="utf-8",
    )
    result = catalog.describe(domain_dir, {}, "")
    assert result["desc"].startswith("SFA 售前售中业务前台")


def test_describe_falls_back_to_observation(tmp_path: Path) -> None:
    domain_dir = tmp_path / "domains" / "x" / "svc"
    domain_dir.mkdir(parents=True)
    (domain_dir / "README.md").write_text(
        '---\ndescription: "本页是检索入口"\n---\n# svc\n\n本页是知识库目录：每个知识页一句话定位。\n',
        encoding="utf-8",
    )
    prof = {
        "observations": [
            {"id": "entrypoints-and-startup", "status": "answered", "answer": "无关内容。"},
            {
                "id": "responsibility-and-relationships",
                "status": "answered",
                "answer": "svc 是订单中心服务，负责下单与库存扣减。其余细节见源码。",
            },
        ]
    }
    result = catalog.describe(domain_dir, prof, "")
    assert result["desc"] == "svc 是订单中心服务，负责下单与库存扣减。"


def test_describe_survives_file_without_readme(tmp_path: Path) -> None:
    root = tmp_path / "domains" / "g" / "p"
    root.mkdir(parents=True)
    assert catalog.describe(root, {}, "兜底描述")["desc"] == "兜底描述"


# ─── build_rows / render ─────────────────────────────────────────────────────


def test_build_rows_and_render_are_stable(tmp_path: Path) -> None:
    ai_wiki = tmp_path / "ai-wiki"
    _write_project(ai_wiki, "sfa", "fs-crm-sfa")
    _write_project(ai_wiki, "paas", "fs-metadata")
    projects_json = _projects_json(tmp_path, [("sfa", "fs-crm-sfa"), ("paas", "fs-metadata")])

    rows, meta = catalog.build_rows(projects_json, tmp_path / "nonexistent", ai_wiki)
    assert [r["name"] for r in rows] == ["paas/fs-metadata", "sfa/fs-crm-sfa"]
    assert meta["projectTotal"] == 2
    assert meta["withWiki"] == 2
    assert meta["withDesc"] == 2

    md = catalog.render(rows, meta)
    assert "| `paas/fs-metadata` | fs-metadata 的职责说明 |" in md
    assert "| `sfa/fs-crm-sfa` | fs-crm-sfa 的职责说明 |" in md
    # 只保留必要列：不再输出 layer/category、页数、复核时间、统计与分组表
    for dropped in ("layer/category", "最近复核", "覆盖概览", "按 group 分布", "仓库总数"):
        assert dropped not in md
    # 幂等：同输入渲染两次完全一致
    assert md == catalog.render(*catalog.build_rows(projects_json, tmp_path / "nonexistent", ai_wiki))


def test_rows_missing_wiki_have_no_path(tmp_path: Path) -> None:
    ai_wiki = tmp_path / "ai-wiki"
    (ai_wiki / "domains").mkdir(parents=True)
    projects_json = _projects_json(tmp_path, [("ops", "dba")])
    rows, meta = catalog.build_rows(projects_json, tmp_path / "nonexistent", ai_wiki)
    assert rows[0]["hasWiki"] is False
    assert meta["withWiki"] == 0
    assert "| `ops/dba` | （暂无 ai-wiki 领域知识） |" in catalog.render(rows, meta)


# ─── main / --check ──────────────────────────────────────────────────────────


def _run(ai_wiki: Path, projects_json: Path, out: Path, *extra: str) -> int:
    return catalog.main(
        [
            "--projects-json",
            str(projects_json),
            "--ai-wiki-root",
            str(ai_wiki),
            "--out",
            str(out),
            *extra,
        ]
    )


def test_main_check_detects_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ai_wiki = tmp_path / "ai-wiki"
    _write_project(ai_wiki, "sfa", "fs-crm-sfa")
    projects_json = _projects_json(tmp_path, [("sfa", "fs-crm-sfa")])
    out = tmp_path / "repo-catalog.md"

    assert _run(ai_wiki, projects_json, out) == 0
    assert out.is_file()

    # 一致 → 0
    assert _run(ai_wiki, projects_json, out, "--check") == 0

    # 数据源变化（新增仓库）→ 漂移，非零
    (_write_project(ai_wiki, "paas", "fs-metadata"))
    projects_json.write_text(
        json.dumps(
            {
                "generatedAt": "2026-09-12T00:00:00.000Z",
                "projects": [
                    {
                        "name": "sfa/fs-crm-sfa",
                        "gitUrl": "https://git.example/sfa/fs-crm-sfa.git",
                        "repoStatKeys": {"group": "sfa", "project": "fs-crm-sfa"},
                    },
                    {
                        "name": "paas/fs-metadata",
                        "gitUrl": "https://git.example/paas/fs-metadata.git",
                        "repoStatKeys": {"group": "paas", "project": "fs-metadata"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    assert _run(ai_wiki, projects_json, out, "--check") == 1
    assert "DRIFT" in capsys.readouterr().err


def test_main_fails_visible_without_roots(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WIKI_BOT_ROOT", raising=False)
    out = tmp_path / "repo-catalog.md"
    assert catalog.main(["--out", str(out), "--ai-wiki-root", str(tmp_path)]) == 2
    assert "ERROR" in capsys.readouterr().err
