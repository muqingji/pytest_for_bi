# code-search 取证 CLI 能力登记

> **隔离规则**：Sourcebot 跨仓搜索**只**通过本 skill 的 `scripts/sourcebot-cli.py`（直连 Sourcebot HTTP API）。**禁止**在编辑器中挂载 Sourcebot MCP；**禁止**在其它 skill 文档中写本目录的绝对路径——跨 skill 只写 **能力 ID** `sourcebot_cli`，由执行方在 **本 skill 目录** 拼命令。

**执行目录（必须）**：仓库根下 `cd .agents/skills/code-search`，再执行：

```bash
uv run --no-sync python scripts/sourcebot-cli.py -h
```

**环境**：`SOURCEBOT_API_KEY` 或 `SOURCEBOT_ACCESS_TOKEN`（`.env.local` 或环境变量）。

> **定库前先查 [repo-catalog.md](repo-catalog.md)**（业务仓库索引）：把业务/服务/app 名解析到 canonical `name`（即 `--repo` 取值）与该仓 ai-wiki 领域知识路径，避免靠 `list-repos --query` 猜名字；解析 0 命中或多命中即停。

## 能力总表

| 能力 ID | 入口名 | 子命令 | 主要产出（`--evidence-dir`） |
|--------|--------|--------|------------------------------|
| `sourcebot_cli` | `sourcebot-cli.py` | `grep` / `glob` / `read-file` / `symbol-def` / `symbol-ref` / `commits` / `diff` / `list-repos` / `list-tree` | `evidence/SRC-search-result-*.json`、`SRC-code-snippet-*.json`；根 `index.md` |

全局选项：`--compact`（搜索类推荐）、`--json`（机读）、`--evidence-dir`、`--no-cache`、`--timeout`。

辅助命令（非 RCA 主路径）：`list-tools`（探测自建实例工具面）、`list-models`、`ask [--structured]`（偶发辅助；主路径仍是 grep/symbol/read）。`list-branches` 仅当实例开放；当前自建 Sourcebot 实测不可用。

自建实例（coder.firstshare.cn）已验证工具面：`grep` `glob` `read_file` `list_tree` `list_repos` `list_commits` `get_diff` `find_symbol_*` `list_language_models` `ask_codebase`。无 `list_branches` / skills。

命令与参数细节见 [tool-reference.md](tool-reference.md)、[sourcebot-query-syntax.md](sourcebot-query-syntax.md)。

## fx-ops 主控 subprocess 契约

慢 SQL 代码定位等场景由 **fx-ops** 登记能力 `collect_slow_sql_code_location` 内部 **subprocess** 调用 `sourcebot_cli`（不 import 本 skill 模块）。子进程 **cwd** 为 `.agents/skills/code-search`，命令形如：

`uv run --no-sync python scripts/sourcebot-cli.py grep --repo ... --pattern ... --compact --evidence-dir <dir>`