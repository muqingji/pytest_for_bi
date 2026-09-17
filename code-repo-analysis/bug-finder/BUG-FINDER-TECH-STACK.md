# Bug Finder 技术栈拆解分析

> **代码快照**：`devops/bug-finder` `main` @ `7e1b8157`（2026-09-16）
> **配套文档**：`BUG-FINDER-ARCHITECTURE.md`（架构与编排链路）
> **配套图解**：`BUG-FINDER-TECH-STACK-DIAGRAMS.html`（技术栈分层 / 依赖构成 / 调用时序 / 门禁拓扑）
> **统计口径**：排除 `.venv/`、`node_modules/`、`.git/`、`tmp/`、`output/`、`archived/`；文件计数用 `rg --files -uu`（含被 gitignore 的产物目录除外）。

---

## 0. 结论先行

这套仓库的技术栈可以用一句话概括：

> **一个 Node + Python 双引擎的「AI Agent 编排仓库」，运行时依赖加起来只有 4 个包，真正的复杂度不在代码里，而在 1500 个 Markdown 文档和一套 JSON Schema / YAML 契约里。**

六个核心判断：

| 判断 | 证据 | 含义 |
| --- | --- | --- |
| **零重依赖是刻意的架构约束** | Node 运行时依赖仅 `proper-lockfile` 1 个；Python 运行时依赖仅 3 个 | 诊断 Agent 要在离线 runner、受限网络、多团队机器上跑，依赖越少越不容易烂 |
| **标准库优先到了极致** | Python 侧 `__future__` 出现在 300 个文件、`pathlib` 237 个、`json` 196 个；Node 侧 `node:path` 142 个、`node:fs` 131 个 | 没有 web 框架、没有 ORM、没有 HTTP client 库，采集全部靠 subprocess 调 CLI |
| **代码规模被知识规模碾压** | Markdown 1495 个 vs Python 329 个 vs JS/MJS 122 个 vs TS 67 个 | 这是一个「写文档让 AI 读」的系统，不是「写代码让机器跑」的系统 |
| **双语言职责切得很干净** | Python 只做采集取证（329 个文件里 300 个在 fx-ops）；Node/MJS 只做编排账本、门禁校验、hook；TS 只做 lint / 打分工具 | 语言选择跟着「产物形态」走，不跟着「个人偏好」走 |
| **契约层是真正的骨架** | 10 张 ClickHouse 表的 `datasources.yaml`(391 行) + 21 个 Draft 2020-12 JSON Schema + evidence registry | 稳定性来自 schema 而不是测试覆盖率；契约漂移由断言测试红灯拦截 |
| **测试栈是「三套并存」而非一套** | pytest 148 个测试文件 + vitest 25 处引用 + `node:test` 18 处引用；CI 用 `pnpm agents:verify` 统一收口 | 每个语言用自己最自然的测试运行时，最后在一个入口汇总，而不是强推一套 |

---

## 1. 运行时与工具链基线

### 1.1 版本矩阵

| 维度 | 值 | 声明位置 | 说明 |
| --- | --- | --- | --- |
| Node.js | `>=24` | `package.json` → `engines.node` | `.nvmrc` 写 `24`，跟进当前 LTS 线 |
| Python | `>=3.12` | `pyproject.toml` → `requires-python` | `.python-version` 写 `3.12`，与 `.venv` 实际解释器一致 |
| 模块体系（Node） | ESM | `package.json` → `"type": "module"` | 全仓 `.mjs` / `.js` 一律 `import`，无 `require` |
| 构建后端（Python） | `hatchling` | `pyproject.toml` → `[build-system]` | 但仓库实际不发 wheel（见 9.3 残留） |
| Node 包管理器 | `pnpm` | `pnpm-lock.yaml`（66 KB） | `pnpm-workspace.yaml` 只声明 `allowBuilds: esbuild: true` |
| Python 包管理器 | `uv` | `uv.lock`（50 KB） | 所有 Python 命令都写作 `uv run --no-sync ...` |
| 依赖严格模式 | 开启 | `.npmrc` → `engine-strict=true` | Node 版本不符直接安装失败，避免"我这能跑" |
| 版本号 | `0.1.0` | `package.json` / `pyproject.toml` 双写 | 内网工具仓库，不发布版本，`private: true` |

补充说明：仓库**没有 `packageManager` 字段**，也没有在 `package.json` 里 pin pnpm 版本；CI 侧靠 `.gitlab/ci/install-node-linux.sh` 里 `corepack enable` 兜底（见第 8 章）。

### 1.2 包管理约定

- **Node 侧**：只用 `pnpm`。`package.json` 的 55 个脚本内部互相调用一律写 `pnpm run <script>`，从不写 `npm run`。
- **禁止 `npx`**：需要执行本地二进制时统一写 `pnpm exec <bin>`（例如 `pnpm exec node .agents/skills/archive/scripts/archive-superpowers.mjs`）。
- **Python 侧**：只用 `uv`。标准前缀是 `uv run --extra dev <cmd>`，`--extra dev` 用于把 `ruff` / `pytest` 拉进环境；业务脚本用 `uv run --no-sync python ...`（跳过同步，加速启动）。
- **锁文件都在版本控制内**：`pnpm-lock.yaml` + `uv.lock` 都提交，CI 用 `pnpm install --frozen-lockfile` 强校验。

### 1.3 本地环境激活链路

诊断脚本需要访问内网 IDP 和 Sourcebot，凭据走环境变量。仓库提供了一套跨平台激活脚本：

| 脚本 | 平台 | 行为 |
| --- | --- | --- |
| `scripts/env/activate.sh` | bash/zsh | 从当前目录**向上最多 32 层**查找 `.env.local`，用 `set -a` 全量导出 |
| `scripts/env/activate.ps1` | PowerShell | 同上语义的 Windows 实现 |
| `scripts/env/activate.cmd` | cmd.exe | 同上，供 Windows 原生终端用 |
| `scripts/env-local-merge.mjs` | 全平台 | 合并多来源 env，产出 `.env.local` |
| `scripts/setup-tokens.ts` | 全平台 | **用 Playwright 自动登录 IDP 抓 token**，支持 `--export-shell` / `--export-win` 输出 |

关键环境变量：

| 变量 | 用途 | 约束 |
| --- | --- | --- |
| `FS_AGENT_TOKEN` | 内网 IDP Agent 令牌（`fsp_` 前缀） | 只允许放 `.env.local`（已 gitignore） |
| `SOURCEBOT_API_KEY` | Sourcebot 代码搜索个人 Key | 同上，申请入口 `https://coder.firstshare.cn/settings/apiKeys` |
| `LANGFUSE_*` | AI-Eye 可观测上报（含 `LANGFUSE_BAGGAGE_PREFIX`、`LANGFUSE_TRACER_NAME`） | 默认关闭，不配就不上报 |
| `AI_EYE_FAIL_ON_ERROR` | AI-Eye 上报失败是否中断 | 默认不中断 |
| `ORCA_ROOT_PATH` / `ORCA_WORKTREE_PATH` | Orca / multica workspace 场景定位主仓库 | bootstrap 时从主仓库复制 `.env.local` |
| `TMPDIR` | 临时目录重定向 | CI 里必须指向 `$CI_PROJECT_DIR/tmp`，见第 8 章 |

> 设计要点：`.env.local` 是**唯一**的密钥落点，向上查找的设计让任意深度的子目录执行脚本都能命中同一份配置，不需要 `source ../../..`。

---

## 2. 语言构成与代码规模

### 2.1 文件类型分布

| 类型 | 文件数 | 角色 | 典型位置 |
| --- | --- | --- | --- |
| Markdown | **1495** | 知识、契约、协议、报告模板 | `.agents/skills/*/SKILL.md`、`.agents/skills/*/references/`、`docs/` |
| Python | **329** | 采集 / 取证 / 校验（数据面） | `.agents/skills/fx-ops/scripts/`（占 254） |
| MJS | **116** | 编排账本、门禁、hook、回归 | `.agents/hooks/`、`scripts/`、`*.mjs` 校验器 |
| TS | **67** | lint / 评分 / 类型检查工具 | `scripts/*.ts`、`.agents/hooks/**/*.test.ts` |
| JSON | **211** | Schema、配置、评测集 | `*.schema.json`、`evals/*.json`、编辑器配置 |
| YAML | **47** | 契约数据、CI、lint 配置 | `.agents/contracts/*.yaml`、`.gitlab-ci.yml` |
| JS | 6 | 极少量历史遗留 | —— |
| Shell | 9 | 环境激活、CI 工具链安装 | `scripts/env/`、`.gitlab/ci/` |

**比例读法**：Markdown : Python : Node 系 ≈ **1495 : 329 : 189**。文档是代码的 4.5 倍——这正是「AI Agent 仓库」和「普通服务仓库」最大的形态差异：服务仓库的复杂度在运行时，Agent 仓库的复杂度在**给模型看的说明书**里。

### 2.2 各语言职责边界

这不是「什么方便用什么」，而是一套**按产物形态选语言**的规则：

| 语言 | 允许做 | 禁止做 | 为什么 |
| --- | --- | --- | --- |
| **Python** | 查日志/指标/数据库、调 IDP CLI、落盘 JSON 证据、跑确定性校验 | 不做调度决策、不选 playbook、不渲染报告正文 | 有 `sqlparse` / `pyyaml` / `jsonschema` 生态，采集文本处理最顺；但流程编排写进 Python 会僵化 |
| **Node / MJS** | 编排状态账本、门禁断言、hook 引擎、回归脚本、契约一致性检查 | 不做数据采集 | 零依赖可跑（只用标准库），CI 上不用装 Python 之外的任何东西 |
| **TS** | 只用 `tsc --noEmit` 做类型检查、写 lint / 打分工具 | 不出现在运行时链路 | TS 的价值在编辑期，不在运行期；`noEmit: true` 明确表达这点 |
| **Markdown** | SKILL 定义、references 知识、报告模板、门禁协议 | —— | 这是唯一被 AI **直接读进上下文**的载体 |

> 仓库铁律（`AGENTS.md`）把这条边界写死了：**Python 采集 → AI 调度 → AI 报告**。禁止用 Python、模板脚本或渲染器程序拼接 HTML / Markdown 正文。技术栈的形态直接对应这条纪律。

### 2.3 单技能脚本与知识分布

这是全仓最有信息量的一张表——它揭示了「哪些技能是代码、哪些技能是知识」：

| 技能 | Python 脚本 | Node 脚本 | references 文档 | 形态判断 |
| --- | --- | --- | --- | --- |
| `fx-ops` | **254** | **42** | 98 | 代码 + 知识双密集（唯一的重型技能） |
| `fx-ops-patrol` | 3 | 11 | 22 | Node 主导（巡检门禁多） |
| `fx-ops-apl` | 10 | 7 | 19 | 混合 |
| `fx-ops-sfa` | 11 | 2 | 8 | Python 主导（业务数据校验多） |
| `fetch-config` | 6 | 0 | 3 | Python 主导 |
| `code-search` | 2 | 0 | 4 | 轻采集 |
| `fx-ops-erp-sync` / `fx-ops-er` / `fx-ops-scenario` / `fx-ops-share` / `fx-ops-pyroscope` / `fx-ops-mq` / `fx-ops-plat` / `fx-ops-postmortem`(0 py/5 js) / `tapd-bug-distill` | 2–6 | 0–5 | —— | 轻量采集 |
| `fx-ops-query` / `fx-ops-object` / `fx-ops-workflow` / `fx-ops-monitoring` / `fx-ops-knowledge` / `fx-ops-bfe` / `fx-ops-metadata` / `fx-ops-timeline` / `fx-ops-tracing` / `workcircle-knowledge-triage` 等 | **0** | **0–3** | 2–13 | **纯知识技能：不写一行脚本** |

**关键洞察**：36 个技能里只有约 18 个带 `scripts/` 目录。像 `fx-ops-query`（0 脚本 / 11 references）、`fx-ops-object`（0 / 6）、`workcircle-knowledge-triage`（0 / 0）这类技能，**全部能力由 Markdown 描述 + 复用 fx-ops 统一 CLI 入口实现**。这是"知识密集型技能不写代码，只写文档让 AI 读"的直接体现，也是这套系统能把 36 个领域覆盖在 189 个 Node 文件内的原因。

---

## 3. 依赖拆解

### 3.1 Node 依赖：运行时 1 个，开发期 7 个

**运行时依赖（`dependencies`）只有一个**：

| 包 | 版本 | 引用文件数 | 唯一用途 |
| --- | --- | --- | --- |
| `proper-lockfile` | `^4.1.2` | 11 | 跨进程互斥：多 Agent / 多终端同时写同一个 `output/evidence/<date-issue>/` 时，用目录锁保证证据文件不被交叉写坏 |

为什么是它？因为这是**标准库唯一给不了的能力**——Node 的 `fs` 没有原子目录锁，而并发跑诊断时两个 Agent 撞同一个证据目录是真实场景。其他所有能力都从标准库拿。

**开发期依赖（`devDependencies`）7 个**：

| 包 | 版本 | 引用文件数 | 用途 |
| --- | --- | --- | --- |
| `typescript` | `^5` | —— | 只做 `tsc --noEmit` 类型检查（`lint` 脚本） |
| `tsx` | `^4.19.0` | 7 | 直接执行 `.ts` 脚本，无需编译步骤（`lint:skills`、`path-eval-score.ts`） |
| `vitest` | `^3.2.4` | 25 | 根目录 `tests/` 单测运行时 |
| `playwright` | `^1.54` | 7 | 两类用途：① `setup-tokens.ts` 自动登录抓 IDP token；② 报告布局回归校验（`verify-report-layout.mjs`） |
| `ajv` | `^8.20.0` | 16 | JSON Schema Draft 2020-12 校验器（Node 侧契约断言） |
| `markdownlint-cli2` | `^0.21.0` | 1 | Markdown 规范检查（1495 个 md 的底线保障） |
| `@types/node` | `^22` | —— | 类型定义（注意：类型定义版本落后于 engines 声明的 Node 24） |

> **一个细节**：`package.json` 里 **没有 `dev` / `build` / `start` 脚本**，也没有 `src/` 目录。这不是遗漏——这个仓库不是 Node 应用，Node 只是它的「脚本宿主」。55 个 script 里最像入口的是 `bootstrap`、`agents:verify`、`sync:skills`。

### 3.2 Python 依赖：运行时 3 个，各有唯一职责

| 包 | 约束 | 真实 import 文件数 | 唯一职责 | 不可替代性 |
| --- | --- | --- | --- | --- |
| `jsonschema` | `>=4.23,<5` | 7 | 用 `Draft202012Validator` 校验 21 个 schema 的产物形状 | 手写校验器会漂移；上界 `<5` 防大版本破坏 |
| `pyyaml` | `>=6.0.3` | 11 | 读 YAML 契约：playbook 定义、阈值表、patrol 环境注册表、MQ 消费组映射、数据源目录 | YAML 是这些契约的载体，多行注释本身是契约的一部分 |
| `sqlparse` | `>=0.5.0` | **2** | 解析慢 SQL 的 `FROM` / `WHERE` / `GROUP BY` / `ORDER BY`，产出索引覆盖矩阵 | 正则解 SQL 会误判子查询；只有 2 个脚本用，但这两个脚本没有替代方案 |

`sqlparse` 的两个消费者：`.agents/skills/fx-ops/scripts/analyze_sql_index_coverage.py`（索引覆盖分析）与 `.agents/skills/fx-ops/scripts/collect_slow_sql_index.py`（慢 SQL 索引采集）。

**开发期依赖只有两个**（`[project.optional-dependencies].dev`）：

- `ruff` —— lint + format 一体（替代 flake8 + isort + black + pyupgrade 四件套）
- `pytest` —— 测试运行时

### 3.3 「标准库主导」的量化证据

**Python 侧导入频次**（`import X` / `from X import` 命中文件数，已排除 `.venv`）：

| 模块 | 文件数 | 模块 | 文件数 |
| --- | --- | --- | --- |
| `__future__` | **300** | `subprocess` | 45 |
| `pathlib` | **237** | `argparse` | 44 |
| `json` | **196** | `dataclasses` | 33 |
| `typing` | **165** | `unittest`（测试用） | 27 |
| `sys` | 126 | `hashlib` | 24 |
| `collections` | 70 | `os` | 18 |
| `re` | 70 | `urllib` | 11 |
| `datetime` | 63 | `tempfile` | 7 |

**Node 侧导入频次**（`node:*` 内置模块命中文件数）：

| 模块 | 文件数 | 模块 | 文件数 |
| --- | --- | --- | --- |
| `node:path` | **142** | `node:child_process` | 30 |
| `node:fs` | **131** | `node:assert/strict` | 29 |
| `node:url` | 67 | `node:fs/promises` | 25 |
| `node:os` | 42 | `node:test` | 18 |
| | | `node:crypto` | 7 |

读法：`pathlib` + `json` + `subprocess` 三个标准库模块就撑起了 Python 侧的采集主流程——读文件、解析 JSON、调外部 CLI。Node 侧同理，`node:path` + `node:fs` + `node:child_process` 是它的全部依赖骨架。

**没有出现的东西更能说明问题**：

| 常见依赖 | 为什么没有 |
| --- | --- |
| `requests` / `httpx` | HTTP 调用统一走 `subprocess` 调 IDP CLI，不在 Python 里直连 |
| `pandas` / `numpy` | 数据聚合在 ClickHouse 侧做完，Python 只搬运结果 |
| `pydantic` | 校验交给 `jsonschema` + 独立 schema 文件，schema 可被 Node 侧复用 |
| `jinja2` | 报告正文由 AI 撰写（仓库铁律），不走模板渲染 |
| `fastapi` / `flask` | 系统没有服务端，不暴露 HTTP 接口 |
| `rich` / `click` | CLI 输出就是 JSON（`columns` + `items` 信封），给人看的报告是 Markdown |

### 3.4 依赖健康度速评

| 维度 | 评价 | 依据 |
| --- | --- | --- |
| 运行时攻击面 | 极小 | 生产依赖 4 个（Node 1 + Python 3），均为纯逻辑库，无网络栈、无原生编译 |
| 升级风险 | 低 | `jsonschema` 显式上界 `<5`；其余用 `^` / `>=` 语义化范围 |
| 供应链风险 | 低 | `pnpm-workspace.yaml` 只放行 `esbuild` 一个构建脚本（`allowBuilds`），其余 postinstall 一律不执行 |
| 安装耗时 | 低 | `pnpm install --frozen-lockfile` + `uv sync` 在离线 runner 上可快速完成 |
| 潜在隐患 | 中 | `@types/node ^22` 落后于 `engines.node >= 24`，Node 24 新增 API 会缺类型提示 |

---

## 4. 契约与 Schema 栈

如果只挑一层来说明「这套系统为什么稳定」，那就是契约层。`.agents/contracts/` 只有 3 个文件，却管住了数据库表结构、环境映射和证据命名。

### 4.1 `datasources.yaml` —— 数据库契约（391 行 / 10 张表）

**全部 10 张表都是 `engine: clickhouse`**，也就是整个诊断系统的数据面只有一种存储引擎：

| 表名 | 时间列 | 租户列 | trace 列 | 用途 |
| --- | --- | --- | --- | --- |
| `log_cep_dist` | `stamp` | `ei` / `ea` | `traceId` | CEP 网关日志，**用户影响主依据**（`status >= 500` 定故障） |
| `fs_cep_slow_error_dist` | —— | —— | —— | CEP 慢 + 错误分布 |
| `log_error_dist` | —— | —— | —— | 应用错误分布（**不能替代用户影响证据**） |
| `paas_oplog_dist` | `_time_second_` | `ei` / `ea` | `null` | PaaS 操作日志；`op` 为 `I/U/D`，同一 id 相邻 `D+I` 是更新候选 |
| `logger.app_log_dist` | `_time_second_` | `[]`（无独立租户列） | `traceId` | 应用日志表（唯一带点号的表名） |
| `slow_log_dist` | `_time_second_` | —— | —— | 慢 SQL |
| `mongo_slow_dist` | —— | —— | —— | Mongo 慢查询 |
| `tomcat_access_dist` | —— | —— | —— | Tomcat 访问日志 |
| `tomcat_access_slow_dist` | —— | —— | —— | Tomcat 慢访问 |
| `biz_log_function_dist` | `_time_second_` | `tenantId` / `ea` | —— | APL 函数执行日志；按 `apiName` 聚合执行次数/失败数/`cost`/`waitingCost` |

契约里每张表还声明了 `columns:` 白名单与 `notes:` 业务口径。`notes` 是这份契约最有价值的部分——它把「同一时刻 `D` + `I` 不是删除后重建，而是更新候选」这种口头知识固化成了机器可读的字段。

> **技术栈含义**：因为表结构是声明的而不是写死在代码里的，所以新增一张日志表不需要改 Python；而且 `fx-ops-query` 这类技能可以做到 **0 个脚本**却支持全量查询——它读的是这份契约。

### 4.2 JSON Schema —— 产物契约（21 个，全是 Draft 2020-12）

| 归属 | 数量 | 文件 | 约束的对象 |
| --- | --- | --- | --- |
| `fx-ops` | **15** | `orchestration-state` / `orchestration-events` / `orchestration-summary` / `ai-decision` / `ai-decision-delta` / `diagnostic-context` / `incident-facts` / `verdict-bundle` / `report-decision` / `report-digest` / `rca-timing` / `rules/domain-signal-rules` / `rules/incident-signal-rules` / `evals/efficiency/rca-efficiency` | 编排状态机、AI 决策记录、诊断上下文、裁决包、报告决策 |
| `fx-ops-patrol` | 3 | `patrol-events` / `patrol-state` / `patrol-summary` | 巡检事件流、状态、摘要 |
| `fx-ops-postmortem` | 3 | `postmortem-events` / `postmortem-state` / `postmortem-summary` | 复盘事件流、状态、摘要 |
| `fx-ops-udobj` | 1 | `object-change-audit-report` | 对象变更审计报告 |

三个 L1 编排器共享**同一套三元组命名法**（`events` / `state` / `summary`），这意味着巡检和复盘的产物形状与 fx-ops 对齐——统一编排的收益直接体现在 schema 复用上。所有 schema 的 `$schema` 字段都指向 `https://json-schema.org/draft/2020-12/schema`（全仓 23 处引用）。

### 4.3 `evidence.yaml` —— 证据命名契约（44 行，试点）

这是 Issue #266 引入的**试点**，目前只登记 2 条证据：

| 字段 | 含义 |
| --- | --- |
| `canonical` | 当前权威文件名（唯一可写名） |
| `python_constant` | `evidence_names.py` 中登记的常量名 |
| `schema` | data 形状说明（通用形状见 `fx-ops/references/evidence-metadata.md`） |
| `producer` | 产出脚本 |
| `required_by` | 把该文件名列为允许值的质量门禁 |
| `aliases[]` | 历史旧名 + `remove_after`（兼容窗截止日） |

当前两条：

| 键 | canonical | producer | required_by |
| --- | --- | --- | --- |
| `similar_errors` | `QRY-similar-errors.json` | `gate_query_backend.py` | `QG-SIMILAR-ERRORS` / `QG-TIMELINE` / `QG-DEEP-RCA` |
| `db_limit_log` | `TRC-db-limit-log.json` | `collect_trace_phase1_tables.py` | `QG-DB-LIMIT` |

**机制设计亮点**：契约文件本身不建生成管线（「纯契约数据 + 一致性断言」），靠两个断言测试守住漂移——`test_evidence_registry.py`（pytest，MR CI 硬门禁）和 `test-effort-tiers-gates.mjs`（Evidence Registry 段）。`aliases` 带 `remove_after: "2026-11-30"`，到期后旧名必须从活代码清除，否则断言红灯。这是**带自动过期机制的兼容窗**，比"加个 TODO"强得多。

### 4.4 `cloud-registry.md` —— 云环境契约（142 行）

所有云环境的唯一真相源，一张 14+ 行的表格，列为 `source_id` / `profile` / `type` / `display_name` / `domain` / `dash_url` / `cms_profile` / `biz_app_log`。跨 skill 引用它获取 source ID、profile、域名映射。

覆盖场景：`resolve_tenant_cloud`（source ID → profile/domain）、`fx-ops-monitoring`（确定 `--profile` 查 Prometheus）、`fx-ops-tracing`（确定追踪目标环境）、`fx-ops-knowledge`（固定 `foneshare` 主租户）、`fetch-config`（确定配置中心环境）。

已登记环境包含：纷享-腾讯云（主站）、专属云-双胞胎集团、专属云-紫光云、纷享-香港 AWS、纷享-华为云、性能测试云、专属云-特变电工、纷享-阿里云、纷享-法兰克福 AWS、纷享-模板云、专属云-海信、专属云-许继电气等。

> **技术栈含义**：为什么用 Markdown 表格而不是 YAML？因为这张表的主要消费者是 **AI 的上下文**而不是程序——Markdown 表格在 token 效率上优于等价 YAML，且人也能直接读。这是一个典型的「按消费者选格式」决策：`datasources.yaml` 被脚本读，所以是 YAML；`cloud-registry.md` 被 AI 读，所以是 Markdown。

---

## 5. 测试与质量门禁栈

### 5.1 三套测试运行时并存

仓库**不追求统一测试框架**，而是每种语言用自己最自然的运行时：

| 运行时 | 触发入口 | 测试文件数 | 覆盖对象 |
| --- | --- | --- | --- |
| **pytest** | `pnpm test:py` → `uv run --extra dev pytest` | **133** 个 `test_*.py`（其中 fx-ops 内 108 个） | Python 采集脚本、契约一致性、门禁校验器 |
| **vitest** | `pnpm test` → `vitest run` | 根 `tests/` 下 **14** 个 `.test.ts` | TS 工具函数、trigger-eval 策略、path-eval 打分 |
| **`node:test`** | `pnpm test:hooks`、各 `test:*` 脚本 | 全仓 **54** 个 `.test.ts/.mjs/.js` | hook checker、报告校验器、回归脚本（`node --test` 直跑） |

**pytest 的四条关键配置**（`pyproject.toml`）：

```toml
addopts = "--basetemp=tmp/pytest"          # 临时目录落项目内，防撑爆 CI runner 的 tmpfs（#308）
testpaths = ["tests", "scripts", ".agents/skills"]   # 整树自动发现，新增测试零配置进 CI（#261）
python_files = ["test_*.py", "*_test.py"]  # 两种命名都收集
pythonpath = ["python", "tests", "scripts"]
```

`testpaths` 写成整树是刻意设计：**新增 Python 测试目录不需要改任何配置就自动进 CI**。为了防止有人把测试文件挪出收集范围，配套了审计脚本 `scripts/check_py_test_discovery.py`（`pnpm test:py-discovery`），磁盘侧预期范围与 pytest 实际收集范围做交叉核对。

### 5.2 静态检查矩阵

| 检查 | 命令 | 工具 | 配置 |
| --- | --- | --- | --- |
| Python lint + format | `pnpm lint:py` | `ruff` | `target-version=py312`、`line-length=120`、`select=E,W,F,I,B,C4,UP,N`、`ignore=E501,B008`、双引号、`mccabe max-complexity=15` |
| TypeScript 类型检查 | `pnpm lint` | `tsc --noEmit` | `strict: true`、`target ES2022`、`module esnext`、`moduleResolution bundler` |
| Markdown 规范 | `pnpm lint:md` | `markdownlint-cli2` | `.markdownlint.yaml`：`default: true` + 关闭 MD013 等 14 条规则 |
| Skill 结构规范 | `pnpm lint:skills` | 自研 `scripts/skill-lint.ts` | 13 条规则 + allowlist |
| 数据目录列名 | `pnpm lint:catalog` | `scripts/lint_catalog_columns.py` | 校验 `datasources.yaml` 列名与 biz 文档一致 |

**`skill-lint.ts` 的 13 条规则**（`scripts/skill-lint-rules/`）——这是这套系统最有特色的 lint，检查的是**文档的语义正确性**而不是格式：

| 规则 | 拦什么 |
| --- | --- |
| `no-hardcoded-operational-identity` | 文档里硬编码环境/租户标识 |
| `literal-sibling-internal-link` | 引用了兄弟 skill 的 `scripts/` 路径（仓库明令禁止） |
| `dangling-fragment` | 指向了不存在的锚点 |
| `module-hint-target-exists` | 提示的模块路径实际不存在 |
| `no-sibling-fxops-runner-copy` | 复制 fx-ops runner 的调用方式 |
| `python-help-command-use-no-sync` | Python 帮助命令漏了 `--no-sync` |
| `no-public-share-default` | 默认走公开分享 |
| `no-old-need-further-phrasing` | 使用了淘汰的回抛措辞 |
| `name-h1-consistency` | skill 名与 H1 标题不一致 |
| `missing-evals-escalation` | 缺 evals 却没标注豁免 |
| `control-character` | 混入控制字符 |
| `allowlist` / `types` | 豁免机制与规则类型 |

### 5.3 结构 / 复杂度 / 语义三类硬门禁

| 门禁 | 脚本 | 作用 | CI 阻断 |
| --- | --- | --- | --- |
| **结构审计** | `.agents/skills/fx-ops/scripts/structure-audit.mjs` | 校验 fx-ops skill 目录结构契约 | ✅ `allow_failure: false` |
| **行数预算** | `.agents/skills/fx-ops/scripts/complexity-line-gate.mjs` | 读同一份 `complexity_budgets.json`，对 scripts 目录做行数上限检查（默认 1000 行 + 豁免余量 50） | ✅ |
| **AST 复杂度** | `ruff check --select C901` + `fx_ops_cli.py run complexity_gate` | 真正的圈复杂度门禁（本地跑，因为需要 Python 3.12 + uv） | 本地 |
| **报告语义** | `scripts/assert-report-semantic-checks-sync.mjs` + `report-semantic-checks.test.mjs` | 报告语义检查项在文档与代码间同步 | ✅ 间接 |
| **SLO 同步** | `scripts/assert-agents-md-slo-sync.mjs` | `AGENTS.md` 里的分档表与各 skill SKILL.md 不矛盾 | ✅ 间接 |
| **报告布局** | `verify-report-layout.mjs` / `verify-production-skeleton-layout.mjs` | 用真实渲染校验 HTML 报告不破版 | ✅ 间接 |
| **触发器评测** | `scripts/lint-trigger-eval.ts` + `tests/trigger-eval-policy.test.ts` | 校验每个 skill 的 `description` 触发词策略合法 | ✅ 间接 |
| **路径评测** | `scripts/path-eval-score.ts` | 按 `evals.json` 给「用户意图 → 首跳 skill」的打分卡打分（支持 `--structure-only`、`--json`） | ✅ 间接 |
| **测试发现审计** | `scripts/check_py_test_discovery.py` | 防止测试文件移出 pytest 收集范围 | ✅ |

**复杂度门禁的双实现**很值得一提：`complexity-line-gate.mjs`（Node）和 `complexity_gate.py`（Python）读**同一份 `complexity_budgets.json`**。原因是 CI runner 是 shell runner，可能没有 Python 3.12/uv——所以给了 Node 版做行数近似门禁，本地则跑完整的 AST 版。这是「**门禁要在最弱的环境下也能跑**」这条原则的落地。

### 5.4 统一验证入口 `agents:verify`

`scripts/agents-verify.mjs` 是全仓**唯一**的验证入口（Issue #264），本地、pre-push、CI 三处跑同一个东西。它本身**不含任何检查逻辑**，只做「按改动文件路由到已有 pnpm script」：

| 顺序 | 步骤 | 触发路径 |
| --- | --- | --- |
| 1 | `lint` | `*.ts/.mts/.cts/.tsx`、`tsconfig.json`、`package.json`、`pnpm-lock.yaml` |
| 2 | `lint:py` | `*.py`、`pyproject.toml`、`uv.lock` |
| 3 | `lint:catalog` | `datasources.yaml`、`fx-ops-query` 的 clickhouse biz 文档 |
| 4 | `lint:skills` | `.agents/skills/**` |
| 5 | `test:py-discovery` | Python 路径 + 审计脚本自身 |
| 6 | `test:py` | Python 路径 + 数据目录路径 |
| 7 | `test:trigger-eval` | skill 路径 + 策略测试 |
| 8 | `test:path-eval` | skill 路径 + 打分脚本 |
| 9 | `test:core-contracts` | skill 路径 + `AGENTS.md` |
| 10 | `verify:fx-ops:gates` | skill 路径 + hook 路径 |

配套 `pnpm agents:verify:changed` 只跑与本次改动相关的子集。代码里有一段注释记录了踩过的坑：**不能用 `git()` 包装 `git status --porcelain`**，因为它的整体 `trim()` 会吃掉首行的前导空格，导致 `slice(3)` 切掉路径首字符而静默跳过该文件的检查——这类细节说明这个入口是被真实使用和打磨过的。

---

## 6. Hook 引擎与编辑器接入栈

### 6.1 组成

`.agents/hooks/` 是一套**独立于 AI 模型的门禁运行时**，由四部分组成：

| 组件 | 文件 | 作用 |
| --- | --- | --- |
| 引擎 | `hook-engine.mjs` | 读配置、按事件类型分发、聚合 checker 结果、决定放行/阻断 |
| 配置 | `hook-config.json` | 声明 20 个 checker 及其订阅的事件（唯一真相源） |
| checker | `checkers/*.mjs` | 20 个独立校验器（19 个有配套 `.test.ts`） |
| 工具库 | `lib/*.mjs` | `budget-rules`、`config-generators`、`detect-tool`、`hook-config-reconciler`、`node-test-compat`、`path-utils`、`respond`、`shell`、`skill-hint`、`state-finder`、`sub-skill-names` |
| AI-Eye | `ai-eye-hook.mjs` / `ai-eye-event.mjs` | 旁路可观测上报（不参与诊断决策） |

### 6.2 六类 Hook 事件

| 事件 | 触发时机 | 订阅它的 checker |
| --- | --- | --- |
| `session-start` | 会话开始 | `session-recover` |
| `pre-dispatch` | 派发子 skill 之前 | `ctx-valid`、`trace-prereq`、`evidence-index`、`dispatch-handoff`、`budget`、`converge-gate`、`return-format`、`render-dispatch`、`apl-context`、`impact-gate` |
| `pre-tool-use` | 调用工具之前 | `apl-artifact-write`、`query-safety`、`app-log-safety` |
| `pre-shell` | 执行 shell 之前 | `query-safety`、`app-log-safety` |
| `post-file-write` | 文件写入之后 | `apl-artifact-write`、`evidence-name`、`phase-guard` |
| `agent-stop` | Agent 收尾 | `evidence-index`、`converge-gate`、`return-format`、`report-structure`、`review-write`、`judge-author`、`impact-gate`、`apl-report-gate` |

### 6.3 20 个 checker 与 fail-closed 策略

| checker | failClosed | 订阅事件 | 拦什么 |
| --- | --- | --- | --- |
| `session-recover` | | `session-start` | 会话恢复 |
| `ctx-valid` | **✅** | `pre-dispatch` | 上下文合法性（**失败即阻断**） |
| `trace-prereq` | | `pre-dispatch` | traceId 前置条件 |
| `evidence-index` | **✅** | `pre-dispatch`、`agent-stop` | 证据索引完整性 |
| `dispatch-handoff` | **✅** | `pre-dispatch` | 派发交接契约 |
| `budget` | | `pre-dispatch` | 预算/配额 |
| `converge-gate` | | `pre-dispatch`、`agent-stop` | 收敛门禁 |
| `return-format` | | `pre-dispatch`、`agent-stop` | 回抛格式 |
| `render-dispatch` | | `pre-dispatch` | 渲染派发 |
| `apl-context` | | `pre-dispatch` | APL 上下文 |
| `apl-artifact-write` | **✅** | `pre-tool-use`、`post-file-write` | APL 产物写入 |
| `query-safety` | **✅** | `pre-shell`、`pre-tool-use` | 查询安全（配套 `query-safety.rules.json`） |
| `app-log-safety` | | `pre-shell`、`pre-tool-use` | 应用日志安全 |
| `evidence-name` | | `post-file-write` | 证据文件命名 |
| `phase-guard` | | `post-file-write` | 阶段守卫 |
| `report-structure` | | `agent-stop` | 报告结构 |
| `review-write` | | `agent-stop` | 评审写入 |
| `judge-author` | | `agent-stop` | 判定署名 |
| `impact-gate` | | `agent-stop`、`pre-dispatch` | 影响面门禁 |
| `apl-report-gate` | | `agent-stop` | APL 报告门禁 |

**`failClosed: true` 的 5 个 checker**（`ctx-valid`、`evidence-index`、`dispatch-handoff`、`apl-artifact-write`、`query-safety`）代表一旦校验失败就**阻断执行**，其余 checker 只告警不阻断。这个区分很重要：拦在「上下文/证据/派发/查询/产物」五个不可妥协的位置，其余交给模型判断。

### 6.4 配置生成链路

14 个编辑器各有自己的 hook 配置格式，仓库的做法是**「单一真相源 + 生成器」**，而不是手写 14 份配置：

```
.agents/hooks/hook-config.json   （真相源）
        │
        ├── scripts/sync-skills.js           技能 → 编辑器规则文件的同步
        ├── scripts/bootstrap-hooks.mjs      引导 Hook 依赖
        └── scripts/generate-hook-configs.mjs 物化所有宿主配置
                │
                ├── --dry-run   只打印 WOULD WRITE / WOULD REMOVE，零变更
                ├── （无参数）    apply（同目录临时文件 + rename 原子替换）
                └── --check      零变更，有 drift 则返回非零
```

生成器与 `pnpm bootstrap` **共用同一个 `hook-config-reconciler` 模块**：先算完整变更计划，成功后才 apply；异常路径也会清理临时文件。关闭 `aiEye.enabled` 时，生成器会从共享配置里移除 AI-Eye 命令但**保留 hook-engine**，并删除只服务 AI-Eye 的 Reasonix / Pi / ZCode / Grok 专用文件，避免宿主加载空壳配置。

### 6.5 生成的编辑器接入物

| 编辑器 | 生成物 | 形态 |
| --- | --- | --- |
| Claude Code | `.claude/hooks.json`、`.claude/hooks/langfuse_hook.py` | hooks + Python 深度转换器 |
| Codex | `.codex/hooks.json`、`.codex/hooks/langfuse_hook.mjs` | hooks + MJS 深度转换器 |
| Cursor | `.cursor/hooks.json`、`.cursor/rules/agents.mdc` | hooks + 规则文件 |
| OpenCode | `.opencode/plugins/fx-ops-hooks.ts` | TS 插件 |
| MiMoCode | `.mimocode/plugins/fx-ops-hooks.ts` | TS 插件（**同时承载 hook-engine 门禁**） |
| Pi | `.pi/extensions/ai-eye.ts` | TS 扩展（AI-Eye 专用） |
| ZCode | `.zcode/config.json` | JSON 配置（AI-Eye 专用） |
| Grok | `.grok/hooks/ai-eye.json` | JSON 配置（AI-Eye 专用） |
| CodeBuddy | `.codebuddy/hooks.json`、`.codebuddy/agents/general_purpose.md` | hooks + agent 描述 |
| Trae | `.trae/hooks.json` | hooks |
| Qoder | `.qoder/hooks.json` | hooks |
| Reasonix | `.reasonix/settings.json` | settings（AI-Eye 专用） |
| Kiro | `.kiro/steering/agents.md` | steering 文档 |
| Windsurf | `.windsurf/instructions.md` | 指令文档 |
| GitHub Copilot | `.github/copilot-instructions.md`、`.github/hooks/fx-ops.json` | 指令 + hooks |

### 6.6 AI-Eye 可观测接入（Langfuse）

| 维度 | 事实 |
| --- | --- |
| 覆盖编辑器 | **12 类**：Claude Code `2.1.232`、Codex `0.147.0`、OpenCode `1.18.16`、MiMoCode `0.1.10`、Reasonix `1.21.1`、Pi `0.84.2`、ZCode（桌面版）、CodeBuddy `2.127.3`、Trae `1.107.1`、Qoder `1.15.1`、Grok `1.0.0`、Cursor `3.16.17` |
| 上报端点 | Langfuse Public Ingestion API |
| 实现方式 | 零依赖事件 span（`ai-eye-event.mjs`），Claude/Codex 走上游 transcript/rollout 深度转换器 |
| 统一事件模型 | `session-start` / `prompt` / `tool-before` / `tool-after` / `tool-failure` / `assistant-response` / `stop` / `session-end` |
| 默认状态 | **关闭**。只有 `hook-config.json` 里严格布尔 `true` 才启用；字符串 `"true"`、数字 `1`、环境变量、缺失字段一律视为关闭 |
| 失败策略 | fail-open（包装器负责开关、凭据、HTTPS、超时；`AI_EYE_FAIL_ON_ERROR` 可改为中断） |
| 会话映射 | 原始 payload 无会话 ID 时，按「工具 + 工作目录 + 宿主父进程」在系统临时目录维护小映射；`SessionEnd` 删除，24 小时未更新自动清理；**只存随机 ID 与更新时间，不存 prompt / 工具输入输出 / 密钥** |
| 去重 | Grok 默认还扫 `.cursor/hooks.json`，收到 Grok 特有 camelCase payload 时跳过，统一由 `.grok/hooks/ai-eye.json` 上报一次，防重复 trace |
| 上游基线 | `ai/ai-eye` @ `2b0d0a81d182dc8fc2b35a42b3ded49e64df3d77` |
| 边界声明 | 文档明确区分「生成配置通过一致性检查」与「完成端到端真实上报」——不夸大验证结论 |

---

## 7. 外部系统依赖栈

这套仓库本身不存储任何诊断数据——它是**外部系统的编排器**。外部依赖按用途分四层：

### 7.1 诊断数据面（AI 判断的依据）

| 系统 | 接入方式 | 用在哪 |
| --- | --- | --- |
| **IDP / fx-ops Go CLI** | `fx-ops idp <subcommand>`（`fx_ops_cli.py run fxops_query` 包装） | 所有查询的统一入口：`query` / `object` / `cms` / `tenant` / `route` / `share` |
| **ClickHouse** | 经 IDP `query`，biz 统一走 `biz-app-log` | 10 张日志表的全部检索（见 4.1） |
| **Prometheus** | `idp --profile <p> prometheus query --promql '<expr>' -j` | 资源与运行时体征（CPU/内存/OOM/GC/线程池/MQ 堆积） |
| **Grafana** | `idp grafana …`（只读） | 看板 / datasource / folder 浏览；`https://grafana.foneshare.cn` |
| **Pyroscope** | 只走 `scripts/query_pyroscope.py` | 火焰图：方法级热点、大对象分配、锁竞争 |
| **Kubernetes** | `fs-k8s-cli`（接入 `fs-k8s-app-manager`） | Pod 状态、发布流程、运行日志；变更必须先只读 plan |
| **Sourcebot** | `sourcebot-cli`（`https://coder.firstshare.cn`，`SOURCEBOT_API_KEY`） | 跨仓库代码搜索，`code-search` 技能用它钻到源码级根因 |
| **Redis / RocketMQ / Kafka / MongoDB / MySQL / PG** | 经 IDP 对应 biz | MQ 消费组映射、Mongo 慢查询、MySQL/PG 直查 |

**环境规模**：`scripts/fx-ops-profiles.json` 登记了 **34 个 profile**（每个含 `base_url` / `cms_profile`），`.agents/contracts/cloud-registry.md` 登记 14+ 个云环境的 `source_id → profile → domain → dash_url` 映射。

### 7.2 知识 / 工单 / 协同面

| 系统 | 端点 | 用途 |
| --- | --- | --- |
| TAPD | `https://www.tapd.cn/20019471/bugtrace/bugs/view`（workspace `20019471`） | 历史缺陷库蒸馏（`tapd-bug-distill`）、超期 bug 汇总 |
| 乐享（lexiangla） | `https://lexiangla.com` | 知识库文档 |
| 纷享 wiki | `https://wiki.firstshare.cn` | 内部文档 |
| 纷享帮助中心 | `https://help.fxiaoke.com` | 产品能力问答 |
| 纷享开发者 | `https://developer.fxiaoke.com` | 开放平台文档（123 处引用，是最高频的业务文档源） |
| 纷享产品站 | `https://www.fxiaoke.com`（+ `/XV/UI/Home`） | 环境域名 |
| CMS | `http://oss.foneshare.cn` / `http://oss.firstshare.cn`（`/cs/core`） | 配置中心（`fetch-config`） |
| 企信 / 工作圈 | 经 IDP 对象查询 | oncall 通知、feedId 反查 |
| 自定义组件 | `https://a9.fspage.com/FSR/weex/uipaas_custom_*` | UIPaaS 自定义组件 |

### 7.3 CLI 调用协议（这是技术栈的关键接缝）

Python 采集层**不直连 HTTP**，而是统一通过 subprocess 调 Go CLI，并遵守一套严格的响应信封：

```json
{
  "code": 0,
  "data": {
    "columns": ["colA", "colB"],
    "items": [["a1", "b1"], ["a2", "b2"]],
    "returnedCount": 2,
    "hasMore": false,
    "truncated": false,
    "meta": {}
  }
}
```

三层命名刻意做了区分（**禁止混谈**）：

| 层 | key | 形态 |
| --- | --- | --- |
| CLI stdout | `data.columns` + `data.items` | 二维数组行 |
| `run_fxops` 返回 | 顶层 `rows` + 原始 `data` | `list[dict]`（已物化） |
| 证据落盘 | `data.rows` / `primary_row` | `list[dict]`，JSON Pointer 如 `#/data/rows/0` |

配套纪律：

- **空结果**是成功（`items: []`），不是错误。
- **禁止**再按旧字段 `data.rows` / `rowCount` 解析 stdout。
- 错误码优先看 `meta.errorCode`。
- 兄弟 skill **不得复制信封逻辑**，统一走 `fx_ops_cli.py run fxops_query -- …`，或 ≤30 行包装（超时 + 非零退出 + JSON 错误体）。
- **stdout 只出 JSON**（供编排器 `json.loads`），debug 不许进 stdout；采集日志追加写 `evidence_dir/logs/LOG-*.log`，每行带 `[HH:mm:ss.SSS]` 前缀。

### 7.4 fx-ops Python 取证能力的调用协议

```bash
# 查能力帮助（末尾带 Examples）
uv run --no-sync python scripts/fx_ops_cli.py help <能力ID>

# 执行能力
uv run --no-sync python scripts/fx_ops_cli.py run <能力ID> -- <参数>
```

三条硬约束：

1. **注册型入口禁止裸跑**——`fast_rca.py` / `playbook_collect.py` 直连会打印统一入口提示并以非零码退出。
2. **其余 `scripts/*.py` 是库模块**，直连无输出、静默退出 0，同样必须经统一入口。
3. **执行前先加载对应 skill 的 SKILL.md**，命令不确定时走 `help <能力ID>`，不靠 `which` 探测。

---

## 8. CI/CD 与工程卫生

### 8.1 GitLab CI（3 个 job，单 `check` stage）

| Job | 脚本 | allow_failure | 作用 |
| --- | --- | --- | --- |
| `check-sensitive-files` | Bash 函数 `is_sensitive_path` | `false` | 扫 MR 变更文件，命中敏感文件即阻断 merge |
| `fx-ops-gates` | `structure-audit.mjs` + `complexity-line-gate.mjs` | `false` | skill 结构与行数预算硬门禁 |
| `core-skill-contracts` | `pnpm run agents:verify` | `false` | 全量统一验证（tsc / ruff / catalog / skill lint / pytest + 发现审计 / trigger+path evals / core contracts / fx-ops gates） |

关键工程细节：

| 细节 | 值 | 原因 |
| --- | --- | --- |
| runner tag | `nvm` | 用 shell runner，不依赖 Docker image |
| 触发条件 | `merge_request_event` 且 target 为 `main` | main 直推防护交给 GitLab 服务端分支保护 |
| `GIT_DEPTH` | `1` | 浅克隆加速 |
| `TMPDIR` | `$CI_PROJECT_DIR/tmp` | **关键**：默认 `/tmp` 是 runner 的 tmpfs，pytest 的 `basetemp` 会撑爆它（#308），工具链回退下载也会写坏（#309） |
| `before_script` | `mkdir -p tmp` 先建目录 | `TMPDIR` 指向的目录不存在时，`tempfile` 会**静默回落**到系统 `/tmp`，防护失效 |
| `after_script` | `rm -rf tmp` + 尝试清理 `/tmp/pytest-of-*` | 自清理；`/tmp/pytest-of-root` 删不动时静默跳过避免日志噪音 |
| Node 兜底 | `.gitlab/ci/install-node-linux.sh` | runner 上没有 node 时按需下载 |
| uv 兜底 | `.gitlab/ci/install-uv-linux.sh` + `bash scripts/ci-setup-python.sh` | 同上 |
| 依赖安装 | `pnpm install --frozen-lockfile` | 锁文件强一致 |

`.gitlab/` 目录还包含：`merge_request_templates/default.md`、`issue_templates/default.md`、`ci/offline-runners.md`、`ci/runner-toolchain.md`。

### 8.2 Git Hooks（本地门禁）

| Hook | 行为 |
| --- | --- |
| `.githooks/pre-commit` | ① 拦截敏感文件（`.env.local`、`.mcp.json`、`opencode.json`、`.idea/`、`*.iml` 等）；② 自动修 markdown + ruff |
| `.githooks/pre-push` | 跑验证入口（与 CI 同一路径） |
| `.githooks/*.cmd` | 上述两个的 Windows cmd 版本 |

需要一次性配置：`git config core.hooksPath .githooks`。

### 8.3 敏感文件扫描清单（CI 与本地的共同红线）

| 类别 | 模式 |
| --- | --- |
| MCP 配置 | `.agents/mcp_config.json`、`.trae/mcp.json`、`.cursor/mcp.json`、`.codebuddy/mcp.json`、`.opencode/mcp.json`、`.mcp.json`、`opencode.json`、`mcp.json` |
| 云凭据 | `.aws/credentials`、`credentials.json`、`service-account*.json`、`.secrets`、`config.toml` |
| SSH 密钥 | `.ssh/id_*` |
| 证书 | `*.pem`、`*.key`、`*.p12`、`*.pfx` |
| 环境变量 | `.env`、`.env.*`、`*.env`（含 `.env.local` / `.env.production` / `.env.staging`） |
| 宿主本地设置 | `settings.local.json` |

### 8.4 协作与仓库治理

| 项 | 配置 |
| --- | --- |
| GitLab 仓库 | `git.firstshare.cn/devops/bug-finder` |
| Multica workspace | `bug-finder`（id `a68adb84-0d85-47fd-be51-a733318c5974`），配置在 `.multica/config.json` |
| MR 描述要求 | 必须含 `Closes #N` / `Related to #N` |
| 分支策略 | 禁止直接向 `main` 提交实现；`ff-only` 合并（历史上曾有依赖「HEAD 是 merge commit」的 job 因与之冲突而误报，已删除） |
| 工作区约定 | 默认在当前仓库工作区操作，不预先创建 worktree；只有用户明确要求时才建 |
| Markdown 规范 | 表格分隔符统一 `\| --- \|`，禁止填充式长横线 |

---

## 9. 一次诊断请求的技术链路（端到端）

把上面所有技术栈串起来，看一次「用户贴了个 traceId」的完整链路，每一跳用了什么技术：

| # | 环节 | 执行方 | 技术 | 输入 | 输出 |
| --- | --- | --- | --- | --- | --- |
| 1 | 用户输入 | 人 | 任意 AI 编辑器（12 类已接入） | traceId / 报错文本 / 截图 | 一条消息 |
| 2 | 宿主加载 hook | 编辑器 | `hook-engine.mjs`（读 `hook-config.json`） | 事件类型 | 注入的 skill 提示 + 门禁 |
| 3 | 首跳分流 | **AI** | `fx-ops/SKILL.md` 的触发矩阵 | 消息内容 | 选定 `fx-ops`，选定 effort 档 |
| 4 | 分诊 scout | **AI + Python** | `fx_ops_cli.py run fast_rca -- …`（`uv run --no-sync`） | traceId | `CTX-collect-manifest.json` + 核心证据 |
| 5 | Go CLI 查询 | Python | `subprocess` → `fx-ops idp query biz-app-log … -j` | SQL | `{code, data:{columns, items}}` |
| 6 | 数据检索 | 外部 | ClickHouse（`log_cep_dist` 等 10 张表） | SQL | 二维数组行 |
| 7 | 证据落盘 | Python | `proper-lockfile` 目录锁 + `pathlib` / `json` | CLI 结果 | `output/evidence/<date-issue>/QRY-*.json` |
| 8 | **证据校验** | Node | `ajv` + `*.schema.json`（Draft 2020-12） | 证据文件 | 通过 / 断言失败 |
| 9 | Hook 放行 | Node | `evidence-index`（failClosed）、`ctx-valid`（failClosed） | 证据索引 | 放行 / 阻断 |
| 10 | 域子 skill 归类 | **AI** | `fx-ops-sfa` / `fx-ops-udobj` 等 SKILL.md | 证据 | 领域假设 |
| 11 | 链路追踪 | Python + 外部 | `fx-ops-tracing` → CEP 日志 + app_log + 慢 SQL | traceId | Root Error Span + 时序表 |
| 12 | 源码钻透 | 外部 CLI | `sourcebot-cli`（`SOURCEBOT_API_KEY`） | 符号 / 堆栈 | 代码级根因 + 修复方案 |
| 13 | 裁决 | **AI** | `verdict-bundle.schema.json` 约束的结构 | 全部证据 | 根因结论 + 置信度 |
| 14 | 报告撰写 | **AI** | Markdown / HTML（**禁止脚本渲染**） | 裁决 | 读者报告 |
| 15 | 报告门禁 | Node | `report-structure` / `impact-gate` / `judge-author`（`agent-stop`） | 报告 | 放行 / 打回 |
| 16 | 外发（可选） | Python | `fx-ops-share` → `idp share` | 报告文件 | URL + 过期时间 |
| 17 | 可观测（旁路） | Node / Python | `ai-eye-hook.mjs` → Langfuse Ingestion API | 事件 | trace span（fail-open） |

**技术栈的读法**：紫色（AI）只出现在 3、4、10、13、14 五个环节，其余全是 Python（绿）和 Node（黄）。AI 负责**判断**，不负责**搬运**——这是整条链路最重要的技术分工。

---

## 10. 技术选型评价

### 10.1 做得好的地方

| 决策 | 收益 | 证据 |
| --- | --- | --- |
| **运行时依赖压到 4 个** | 离线 runner 能装、供应链风险低、升级不痛 | Node 1 个 + Python 3 个 |
| **标准库优先** | 不需要为「读文件、调命令行、拼 JSON」引入任何框架 | `pathlib` 237 / `node:fs` 131 |
| **按产物形态选语言** | 采集用 Python（文本处理强）、门禁用 Node（零依赖可跑）、知识用 Markdown（AI 直接读） | 见 2.2 |
| **契约前置** | 表结构和产物形状是声明的，不是硬编码的，新增表/新增技能不用改采集代码 | 10 张表 YAML + 21 个 schema |
| **门禁在最弱环境也能跑** | `complexity-line-gate.mjs` 与 `complexity_gate.py` 双实现读同一份预算文件 | 见 5.3 |
| **统一验证入口** | 本地 / pre-push / CI 跑同一个 `agents:verify`，杜绝「CI 过了本地没过」 | 见 5.4 |
| **按改动路径路由检查** | `agents:verify:changed` 只跑相关子集，300 个 Python 文件不必每次全跑 | `scripts/agents-verify.mjs` |
| **单一真相源 + 生成器** | 14 个编辑器的 hook 配置从 `hook-config.json` 生成，不是手抄 14 份 | 见 6.4 |
| **兼容窗有自动过期** | evidence alias 带 `remove_after` 日期，到期断言红灯 | `evidence.yaml` |
| **旁路可观测与主链路解耦** | AI-Eye 默认关闭、fail-open，不参与诊断决策 | 见 6.6 |

### 10.2 风险点

| 风险 | 表现 | 影响 | 建议 |
| --- | --- | --- | --- |
| **fx-ops 单点过重** | 254 个 Python + 42 个 Node + 98 个 references，占全仓代码的绝大部分 | 单技能承担全部编排、全部契约、全部采集；任何新人要改核心逻辑都必须理解这一个巨型技能 | 门禁里的 structure-audit / complexity-line-gate 已经是在防这个，但更彻底的方案是把「通用采集库」下沉到 `.agents/lib/` |
| **`@types/node ^22` 落后于 `engines.node >= 24`** | Node 24 新增 API 无类型提示 | `tsc --noEmit` 可能放过用法错误，或误报 | 升到 `@types/node ^24` |
| **三套测试运行时并存** | pytest + vitest + `node:test` | 认知成本；「这个测试该放哪」需要判断 | 现状是刻意的分工，文档里说明选择规则即可 |
| **`node:test` 与 vitest 边界模糊** | 全仓 54 个 `.test.ts/.mjs` 中既有 vitest 也有 `node --test` | 同一个目录可能出现两种风格 | 保持 `tests/**/*.test.ts` = vitest、`*.test.mjs` = node:test 的约定并写进 skill-development |
| **Markdown 规模难以人工维护** | 1495 个 md | 靠 skill-lint 的 13 条规则挡住语义漂移，但覆盖不到的地方只能靠 review | 继续把「口头规则」转成 lint 规则 |
| **CI 只有 1 个 stage / 3 个 job** | 门禁的绝大部分靠 `core-skill-contracts` 单个 job 串行跑 | 单 job 时长 = 全部检查时长；一个 check 挂掉整条流水线重跑 | 若耗时成为瓶颈，可按 `agents:verify` 的步骤拆成 parallel jobs |
| **Playwright 用于非 UI 场景** | ① 抓 token ② 校验 HTML 报告布局 | 增加了 ~300 MB 浏览器依赖 | 但这两个场景确实没有更轻的替代（真实渲染校验无法用静态分析替代） |

### 10.3 已确认的历史残留（不是 bug，但值得清理）

| 残留 | 位置 | 说明 |
| --- | --- | --- |
| `python/` 目录不存在却被引用 | `pyproject.toml` → `pythonpath = ["python", ...]` 与 `[tool.hatch.build.targets.wheel] packages = ["python"]` | 两处都指向不存在的目录。`pythonpath` 里多余一项无害；`packages = ["python"]` 说明 hatchling 配置是从模板继承来的 |
| `src/` 目录不存在却被引用 | `tsconfig.json` → `paths: {"@/*": ["./src/*"]}`；`vitest.config.ts` → `alias: {"@": ./src}` | 别名指向不存在的目录，实际无任何文件用 `@/` 导入 |
| `tsconfig.json` 开启 `declaration` / `declarationMap` / `sourceMap` / `outDir` | 同时 `noEmit: true` | 与 `noEmit` 组合无意义，属于模板残留 |
| `tsconfig.json` include 里有 `agents/**/*.ts`、`tools/**/*.ts` | 两个目录都不存在 | include 不存在的 glob 不报错，但会让人误以为有这两个目录 |
| `version` 双写 `0.1.0` | `package.json` + `pyproject.toml` | 内网工具仓库不发布，但两处版本号需要手工同步 |
| 旧命名的 biz 别名 | `AGENTS.md` 明令禁止使用 | 例如 `open-oauth` / `open-link-app` / `wechat-proxy` / `syncdata` 等，必须用新名 |

> 这些残留的共同特征是**从模板继承的配置没有被清理**。它们不影响运行，但会误导读者对新人的心智模型。建议在下次结构性重构时一并清除。

---

## 11. 一页速查表

| 维度 | 结论 |
| --- | --- |
| 仓库性质 | AI Agent 编排仓库（不是 Node 应用、不是 Python 包） |
| 语言配比 | Markdown 1495 : Python 329 : MJS 116 : TS 67 : JSON 211 : YAML 47 |
| Node 版本 | `>=24`（`.nvmrc` = 24），ESM，`engine-strict=true` |
| Python 版本 | `>=3.12`（`.python-version` = 3.12），hatchling |
| 包管理器 | pnpm（Node）+ uv（Python），禁止 npm/npx |
| Node 运行时依赖 | `proper-lockfile` **×1** |
| Python 运行时依赖 | `jsonschema` / `pyyaml` / `sqlparse` **×3** |
| 主导标准库 | Python：`pathlib` / `json` / `subprocess`；Node：`node:path` / `node:fs` / `node:child_process` |
| 脚本总数 | `package.json` 55 个 script |
| 测试 | pytest 133 文件 + Node 系 54 文件（其中 vitest 14 个、`node:test` 40 个）= **187 个测试文件** |
| 契约 | `datasources.yaml`(10 张 ClickHouse 表) + 21 个 JSON Schema + `evidence.yaml` + `cloud-registry.md` |
| Hook | 1 引擎 + 20 checker（5 个 failClosed）+ 6 类事件 + 11 个 lib 模块 |
| 编辑器接入 | 14 个宿主配置生成物；AI-Eye 覆盖 12 类编辑器 |
| 环境档案 | `fx-ops-profiles.json` 34 个 profile；cloud-registry 14+ 云环境 |
| CI | 3 个 job / 1 个 stage，全部 `allow_failure: false` |
| 统一验证入口 | `pnpm agents:verify`（本地 = pre-push = CI） |
| 数据面 | 全部 ClickHouse，经 IDP Go CLI 访问 |
| 最大风险 | fx-ops 单技能过重（254 py + 42 js + 98 refs） |
| 一句话 | **零重依赖 + 契约驱动 + 知识密集：真正的复杂度在 1500 个 Markdown 文档和 21 个 Schema 里，不在代码里。** |
