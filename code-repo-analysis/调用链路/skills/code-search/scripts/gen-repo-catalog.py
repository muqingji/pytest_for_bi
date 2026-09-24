#!/usr/bin/env python3
"""生成/校验 code-search 的业务仓库索引（repo catalog）。

数据源（三个外部位置，全部可参数化，缺失即 fail-visible）：
  - wiki-bot 目录清单：``<wiki-bot-root>/config/projects.json``
  - wiki-bot 重画像（可选）：``<wiki-bot-root>/config/profiles/<group>/<project>.json``
  - ai-wiki 知识库：``<ai-wiki-root>/domains/<group>/<project>/README.md``

目录规则（权威）：ai-wiki 域目录 = gitUrl 最后两段 ``<group>/<project>``（项目段去 ``.git``）。
``projects.json`` 的 ``aiWikiDomain`` 只是声明式别名，**不参与路径推导**。
依据：wiki-bot ``skills/repo-wiki-ops/references/publish-runbook.md``。

用法：
    # 生成（默认写 references/repo-catalog.md）
    uv run --no-sync python scripts/gen-repo-catalog.py

    # 只校验是否漂移（非零退出表示需要重新生成）
    uv run --no-sync python scripts/gen-repo-catalog.py --check

    # 显式指定外部根（CI / 换机）
    uv run --no-sync python scripts/gen-repo-catalog.py \
      --wiki-bot-root ~/gitlab/wiki-bot --ai-wiki-root ~/gitlab/ai-wiki

环境变量兜底：``WIKI_BOT_ROOT`` / ``AI_WIKI_ROOT``。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT = SKILL_DIR / "references" / "repo-catalog.md"

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

# README front-matter description / 首段里属于"页面导航"而非"仓库职责"的噪声
NOISE_MARKERS = (
    "本页是",
    "本页回答",
    "本页给出",
    "本页说明",
    "本页提供",
    "推荐阅读顺序",
    "阅读顺序",
    "阅读路径",
    "数据源：",
    "唯一事实源",
    "事实源",
    "知识包",
    "知识库索引",
    "知识索引",
    "任务路由索引",
    "目录索引",
    "索引页",
    "检索入口",
    "判断入口",
    "快速上手",
    "必须回答",
    "本仓库知识",
    "claims 必须",
    "能力鸟瞰",
    "mermaid",
    "flowchart",
    "sequenceDiagram",
    "stateDiagram",
)

# 部署单元名相对仓库名常见的后缀（app → repo 归一化用）
APP_SUFFIXES = (
    "-service-gray",
    "-service-urgent",
    "-service",
    "-provider",
    "-web",
    "-job-service",
    "-job",
    "-api",
    "-server",
)


def domain_from_git_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    parts = [p for p in u.split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else ""


def count_md(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("*.md"))


def read_front_matter(path: Path) -> tuple[dict[str, str], str]:
    if not path.is_file():
        return {}, ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = FRONT_MATTER.match(text)
    if not m:
        return {}, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return fm, text[m.end() :]


def is_noise(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 10:
        return True
    head = s[:60]
    return any(marker in head for marker in NOISE_MARKERS)


def clean_text(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\[\s*([^\]]+)\s*\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"^[#>|*\-]+\s*", "", text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def first_sentence(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    for sep in ("。", "\n"):
        idx = text.find(sep)
        if 0 < idx < limit:
            text = text[: idx + 1]
            break
    return clean_text(text, limit)


def observation_text(prof: dict) -> str:
    """profile 的职责观察（enrich 产物）——描述缺失时的兜底。"""
    obs = prof.get("observations") or []
    for want in ("responsibility-and-relationships",):
        for o in obs:
            if o.get("id") == want and o.get("status") == "answered" and o.get("answer"):
                return first_sentence(o["answer"])
    for o in obs:
        if o.get("status") == "answered" and o.get("answer"):
            return first_sentence(o["answer"])
    return ""


def describe(root: Path, prof: dict, fallback: str = "") -> dict[str, str]:
    """从 ai-wiki 域目录的 README 提取"这是做什么的"。"""
    fm, body = read_front_matter(root / "README.md")

    m = re.search(r"^##\s*这是什么\s*\n+(.+?)(?=\n##|\Z)", body, re.S | re.M)
    section_what = clean_text(m.group(1)) if m else ""

    first_para = ""
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|", "```")):
            continue
        first_para = clean_text(s)
        break

    candidates = [
        clean_text(fm.get("description", "")),
        section_what,
        first_para,
        observation_text(prof),
        clean_text(fallback),
    ]
    desc = next((c for c in candidates if c and not is_noise(c)), "")
    if not desc:
        desc = next((c for c in candidates if c), "")

    return {
        "desc": desc,
        "lastReviewed": fm.get("last_reviewed", ""),
        "revision": fm.get("source_revision", ""),
    }


def clean_summary(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s or s.startswith("Tool ") or "failed:" in s:
        return ""
    return s


def load_profile(profiles_root: Path, name: str) -> dict:
    prof = profiles_root / f"{name}.json"
    if not prof.is_file():
        return {}
    try:
        return json.loads(prof.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_rows(projects_json: Path, profiles_root: Path, ai_wiki_root: Path) -> tuple[list[dict], dict]:
    catalog = json.loads(projects_json.read_text(encoding="utf-8"))
    projects = catalog.get("projects", [])

    rows: list[dict] = []
    for p in projects:
        name = p.get("name", "")
        dom = domain_from_git_url(p.get("gitUrl", ""))
        domain_dir = ai_wiki_root / "domains" / dom if dom else None
        md_count = count_md(domain_dir) if domain_dir else 0

        prof = load_profile(profiles_root, name) if name else {}
        summary = clean_summary(prof.get("summary", ""))
        d = describe(domain_dir, prof, summary) if md_count and domain_dir else {}

        rows.append(
            {
                "name": name,
                "group": (p.get("repoStatKeys") or {}).get("group") or name.split("/")[0],
                "gitUrl": p.get("gitUrl", ""),
                "sourcebotName": p.get("sourcebotName", ""),
                "aiWikiDomain": p.get("aiWikiDomain", ""),
                "domainPath": dom,
                "hasWiki": md_count > 0,
                "wikiMdCount": md_count,
                "wikiDesc": d.get("desc", ""),
                "lastReviewed": d.get("lastReviewed", ""),
                "layer": p.get("layer", ""),
                "category": p.get("category", ""),
                "techStack": p.get("techStack", []),
                "summary": summary,
            }
        )

    rows.sort(key=lambda r: (r["group"], r["name"]))

    meta = {
        "projectTotal": len(rows),
        "withWiki": sum(1 for r in rows if r["hasWiki"]),
        "withDesc": sum(1 for r in rows if r["wikiDesc"]),
        "groups": len({r["group"] for r in rows}),
        "catalogGeneratedAt": catalog.get("generatedAt", ""),
    }
    return rows, meta


def render(rows: list[dict], meta: dict) -> str:
    md: list[str] = []
    a = md.append

    a("# 业务仓库索引（repo catalog）")
    a("")
    a(
        "本表是 `code-search` 的入口索引：把「业务 / 服务 / 模块名」落到"
        "「仓库 → sourcebot `--repo` → ai-wiki 领域知识路径」。"
    )
    a("")
    a("> 本文件由 `scripts/gen-repo-catalog.py` 生成，**请勿手工编辑**。")
    a("> 重新生成：`uv run --no-sync python scripts/gen-repo-catalog.py`；")
    a("> 校验漂移：`uv run --no-sync python scripts/gen-repo-catalog.py --check`。")
    a("")
    a("## 怎么用")
    a("")
    a("| 你要做的事 | 怎么做 |")
    a("| --- | --- |")
    a(
        "| 读某仓领域知识 | 打开 `<ai-wiki-root>/domains/<仓库 name>/README.md`，按页内「按任务路由 / 按读者场景导航」进具体页 |"
    )
    a(
        "| 找术语 / 类名对应代码 | 该仓根目录 `glossary.md`（如有），条目自带 `path#Lx-Ly` 行锚，可直接喂 `read-file --path --offset` |"
    )
    a('| 搜真源码 | `uv run --no-sync python scripts/sourcebot-cli.py grep --repo "<name>" --pattern ... --compact` |')
    a(
        "| 只有 app / bizName | 按下方「怎么定位仓库」的规则解析；解析不出即**停**，用 `list-repos --query` 兜底，禁止猜 |"
    )
    a("")
    a("## 怎么定位仓库与知识页")
    a("")
    a("- **仓库 name = ai-wiki 目录**：`<ai-wiki-root>/domains/<name>/`，`name` 同时就是 sourcebot `--repo` 的值。")
    a("- ai-wiki 域目录 = gitUrl 最后两段 `<group>/<project>`（项目段去 `.git`）；")
    a("  `projects.json` 的 `aiWikiDomain` 只是声明式别名，**不参与路径推导**，不要用它拼路径。")
    a(
        "- **app / bizName ≠ 仓库名**：部署单元名常带 `-service` / `-provider` / `-wq` / `-job` / `-web` / `-server` 后缀；"
    )
    a("  解析顺序 ① 精确匹配下表 name → ② 匹配 project 段 → ③ 去上述后缀再匹配 project 段。")
    a(
        "  命中 **0 个或多个即停**（多命中 = 猜）；解析不出时用 `sourcebot-cli.py list-repos --query <name> --compact` 兜底。"
    )
    a("")
    a("## 主索引")
    a("")
    a("| 仓库 name（= ai-wiki 目录 = sourcebot `--repo`） | 这是做什么的 |")
    a("| --- | --- |")
    for r in rows:
        if r["hasWiki"]:
            desc = clean_text(r["wikiDesc"] or r["summary"], 120) or "—"
        else:
            desc = "（暂无 ai-wiki 领域知识）"
        a(f"| `{r['name']}` | {desc} |")
    a("")
    return "\n".join(md)


def resolve_root(value: str | None, env: str) -> Path | None:
    raw = value or os.environ.get(env)
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成/校验 code-search 业务仓库索引")
    parser.add_argument("--wiki-bot-root", help="wiki-bot 仓库根（含 config/projects.json）；环境变量 WIKI_BOT_ROOT")
    parser.add_argument("--ai-wiki-root", help="ai-wiki 仓库根（含 domains/）；环境变量 AI_WIKI_ROOT")
    parser.add_argument("--projects-json", help="直接指定 projects.json（优先于 --wiki-bot-root）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"输出 Markdown 路径（默认 {DEFAULT_OUT}）")
    parser.add_argument("--check", action="store_true", help="只校验现有文件是否为最新，漂移则非零退出")
    args = parser.parse_args(argv)

    wiki_bot_root = resolve_root(args.wiki_bot_root, "WIKI_BOT_ROOT")
    ai_wiki_root = resolve_root(args.ai_wiki_root, "AI_WIKI_ROOT")

    projects_json = Path(args.projects_json).expanduser().resolve() if args.projects_json else None
    if projects_json is None:
        if wiki_bot_root is None:
            print(
                "ERROR: 缺少 wiki-bot 位置。请传 --wiki-bot-root 或 --projects-json，或设置环境变量 WIKI_BOT_ROOT。",
                file=sys.stderr,
            )
            return 2
        projects_json = wiki_bot_root / "config" / "projects.json"
    if not projects_json.is_file():
        print(f"ERROR: 找不到 projects.json：{projects_json}", file=sys.stderr)
        return 2

    if ai_wiki_root is None:
        print(
            "ERROR: 缺少 ai-wiki 根目录。请传 --ai-wiki-root 或设置环境变量 AI_WIKI_ROOT。",
            file=sys.stderr,
        )
        return 2
    if not (ai_wiki_root / "domains").is_dir():
        print(f"ERROR: {ai_wiki_root}/domains 不存在，ai-wiki 路径不正确。", file=sys.stderr)
        return 2

    profiles_root = (wiki_bot_root / "config" / "profiles") if wiki_bot_root else Path("/nonexistent")
    rows, meta = build_rows(projects_json, profiles_root, ai_wiki_root)
    rendered = render(rows, meta)

    out_path = Path(args.out).expanduser().resolve()
    if args.check:
        if not out_path.is_file():
            print(f"DRIFT: 索引文件不存在：{out_path}", file=sys.stderr)
            return 1
        current = out_path.read_text(encoding="utf-8")
        if current.strip() != rendered.strip():
            print(f"DRIFT: {out_path} 与当前数据源不一致，请重新生成。", file=sys.stderr)
            return 1
        print(f"OK: {out_path} 与数据源一致（{meta['projectTotal']} 个仓库）。")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {"out": str(out_path), **meta},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
