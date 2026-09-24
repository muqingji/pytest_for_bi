# Sourcebot 工具速查表

> 在 `.agents/skills/code-search` 目录下执行 `uv run --no-sync python scripts/sourcebot-cli.py`（见 [sourcebot-cli-capabilities.md](sourcebot-cli-capabilities.md)）。
> `--compact` 标志节省 token（保留缩进，仅删空行）；搜索/定位类调用推荐。

## 调用方式速查

所有命令通过 `uv run --no-sync python scripts/sourcebot-cli.py <command> [options]` 执行。

> 定库前先读 [repo-catalog.md](repo-catalog.md)：用业务/服务名查 canonical `--repo` 与该仓 ai-wiki 领域知识路径。

**节省 token 的核心习惯**：
- 搜索/定位/汇总类调用：始终加 `--compact`
- 源码阅读（read-file）：不加 `--compact`（需要全量内容分析）
- 证据落盘：加 `--evidence-dir <path>`（结果写入证据目录）
- 高频查询复用：无需手动处理，CLI 自带 5 分钟缓存

## 命令速查

| 需求 | 命令 | 必需参数 | 可选参数 |
|------|------|---------|---------|
| 按内容搜索 | `grep` | `--pattern` | `--repo`, `--include`, `--path`, `--ref`, `--group-by-repo`, `--limit` |
| 按文件名搜索 | `glob` | `--pattern` | `--repo`, `--path`, `--ref`, `--limit` |
| 查符号定义 | `symbol-def` | `--symbol`, `--repo` | — |
| 查符号引用 | `symbol-ref` | `--symbol`, `--repo` | — |
| 读源码 | `read-file` | `--path`, `--repo` | `--ref`, `--offset`, `--limit` |
| 查提交历史 | `commits` | `--repo` | `--query`, `--since`, `--until`, `--author`, `--ref`, `--path`, `--page`, `--per-page` |
| 看变更差异 | `diff` | `--repo`, `--base`, `--head` | `--path` |
| 列出仓库 | `list-repos` | — | `--query`, `--page`, `--per-page`, `--sort`, `--direction` |
| 浏览目录 | `list-tree` | `--repo` | `--path`, `--ref`, `--depth`, `--include-files`, `--include-dirs`, `--max-entries` |
| 列出模型 | `list-models` | — | — |
| 探测工具面 | `list-tools` | — | — |
| 列出分支 | `list-branches` | `--repo` | `--query`, `--page`, `--per-page`（自建实例可能不可用） |
| 自然语言问答 | `ask` | `--query` | `--repos`, `--provider`, `--model`, `--visibility`, `--structured`（非 RCA 主路径） |

## 全局选项

| 选项 | 用途 |
|------|------|
| `--compact` | 精简输出（JSON 原地保留；文本去除空行和多余缩进）— 搜索/定位类调用推荐 |
| `--json` | 机读 JSON（`ok`/`tool`/`params`/`content`）；失败时 `ok: false` |
| `--evidence-dir <path>` | 将结果写入证据目录：若传入 run 根目录，则业务证据写入 `evidence/` 子目录并更新根 `index.md`；若传入的已是 `.../evidence`，则直接写该子目录并更新父目录 `index.md` |
| `--no-cache` | 绕过缓存 |
| `--timeout <sec>` | 网络超时秒数（默认 30）|

自建实例工具面以 `list-tools` 为准（当前无 `list_branches` / skills）。`ask --structured --json` 可解析 citations，但 RCA 主路径仍是 grep/symbol/read + `--evidence-dir`。

## 典型组合

```bash
# 仓库探测（最省 token）
uv run --no-sync python scripts/sourcebot-cli.py grep --pattern "NullPointerException" --group-by-repo --compact

# 异常类定位（紧凑+落盘证据）
uv run --no-sync python scripts/sourcebot-cli.py grep --repo "AppServer/fs-fmcg" --pattern "NullPointerException" --include "*.java" --compact --evidence-dir output/evidence/20260703-npe/

# 符号定义（紧凑）
uv run --no-sync python scripts/sourcebot-cli.py symbol-def --repo "AppServer/fs-fmcg" --symbol "OrderService" --compact

# 源码阅读（不加 --compact）
uv run --no-sync python scripts/sourcebot-cli.py read-file --repo "AppServer/fs-fmcg" --path "OrderService.java" --offset 130 --limit 30

# 提交历史（紧凑）
uv run --no-sync python scripts/sourcebot-cli.py commits --repo "AppServer/fs-fmcg" --since "7 days ago" --path "OrderService.java" --compact

# 变更差异
uv run --no-sync python scripts/sourcebot-cli.py diff --repo "AppServer/fs-fmcg" --base "abc123" --head "def456"
```

## 限制说明

- grep 单次最多 100 条（`--group-by-repo` 时 10000 条）
- read-file 单次最多 500 行 / 5KB，长行截断 2000 字符
- read-file `--offset` 为 1-indexed，**最小 1**；传 `0` 或负数 CLI 报错退出
- CLI 自带 5 分钟缓存（grep/symbol）或 60 秒（commits/read-file）
