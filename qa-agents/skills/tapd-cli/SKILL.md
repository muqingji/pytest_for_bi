---
name: tapd-cli
display_name: TAPD CLI
version: "0.2.3"
author: TAPD
level: product
description: Use this skill when you need to query or update TAPD stories, bugs, tasks, comments, iterations, Wiki pages, timesheets, attachments, project document-library files, test cases, test plans, or users with tapd-cli. It distinguishes TAPD project documents from Wiki pages, supports URL parsing, field dictionary lookup, advanced queries, and file link handling.
metadata:
  tags: [tool]
  author: shangrp
  version: "0.2.3"
---

# tapd-cli

## 背景

`tapd-cli` 是 TAPD OpenAPI 命令行工具，把 TAPD 平台的常用和高级 OpenAPI 能力封装为统一的终端命令。Agent 通过 `tapd-cli <entity> <subcommand> [key=value ...]` 完成查询、创建、更新与统计，无需手动拼 `curl`。

需要在 TAPD 与企微智能表格之间同步数据时，`tapd-cli` 只负责 TAPD 侧读写；智能表格侧必须使用独立客户端。同步前阅读 `references/smartsheet-sync.md`。

## 按需加载

| 场景 | 参考文档 |
| --- | --- |
| 解析 TAPD 链接 / 自动提取 workspace 与 ID | [references/url-format.md](references/url-format.md) |
| 查字段枚举值 / 团队/模块/状态映射 / key 对应中文 label | [references/xiaoke-tapd-dict.md](references/xiaoke-tapd-dict.md) |
| 高频查询模板（团队 Bug、团队需求、Bug 影响企业） | [references/query-templates.md](references/query-templates.md) |
| 高级查询语法（LIKE/EQ/NOT_EQ/时间范围）/ fields + jq 探索未知字段 | [references/cli-advanced.md](references/cli-advanced.md) |
| API 响应结构 / 返回数据包装解析 / 回复摘要规范 | [references/response-structure.md](references/response-structure.md) |
| Bug description 中的 FSC 内部文件链接下载与转换 | [references/fsc-file-links.md](references/fsc-file-links.md) |
| 下拉/单选/多选自定义字段传值规则（传文案非序号） | [references/custom-fields.md](references/custom-fields.md) |
| 项目文档下载与实体附件/图片上传管理 | [references/documents.md](references/documents.md) |
| 智能表格双向同步 | [references/smartsheet-sync.md](references/smartsheet-sync.md) |
| 401 / 命令未找到 / 特殊字符引号 / 故障排查 | [references/troubleshooting.md](references/troubleshooting.md) |

## 智能表格同步边界

- `tapd-cli` 不提供智能表格的创建、查询或写入能力。
- 开始同步前，先确认当前环境存在可用的智能表格客户端，并阅读其帮助或接口文档，禁止猜测命令和参数。
- 智能表格客户端不可用时，只生成 TAPD 导出数据或 Diff 输入，并明确报告阻塞；禁止切换到未声明的调用路径。

## 项目文档与 Wiki / 附件判定（必须遵守）

- **项目文档（Document）**：用户说“下载项目文档”时使用 `tapd-cli document download` 获取文档下载链接。
- **实体附件（Attachment）**：用户说“上传附件/转存附件到需求/缺陷/任务”时使用 `tapd-cli attachment upload`，支持 `story` / `bug` / `task`；富文本图片使用 `tapd-cli attachment upload-image`。
- **Wiki 页面（Wiki）**：仅当用户明确说“Wiki”“Wiki 页面”或明确要求创建在线协同文档时，才使用 `tapd-cli wiki add/update`。

## 能力边界

该 skill 支持以下 TAPD 实体与子命令（以真实 CLI `--help` 为准）：

| 实体 | 真实子命令 | 说明 |
| --- | --- | --- |
| `comment` | add / list / count | 评论管理，`list` 支持 `--full` 查看完整 HTML，默认纯文本 |
| `story` | add / list / update / count / fields / related-bugs / link / link-bug / unlink-bug | 需求管理；Bug 关联必须使用需求 URL 中的全局 story id |
| `bug` | add / list / update / count / fields / link-tcase | 缺陷管理，`fields` 支持 `all_options=1` |
| `task` | add / list / update / count | 任务管理，`update` 支持 `auto_complete_effort=1` |
| `iteration` | list | 迭代列表查询 |
| `wiki` | add / list / update / count | Wiki 页面管理，支持 Markdown 与 HTML |
| `timesheet` | add / list / update / count | 工时记录管理 |
| `attachment` | list / by-entity / download / upload / upload-image / upload-image-base64 / get-image | 附件管理与图片上传下载 |
| `document` | download | 项目文档下载链接获取（`GET /documents/down`） |
| `tcase` | add / batch-add / list / update / count / fields / categories / add-category / execute / assign / result / link-plan / remove-from-plan / unlink-story / count-by-category / category-count / custom-fields / story-by-tcase / import-xmind | 测试用例与执行管理 |
| `testplan` | add / list / update / count / details / progress / tcases / bugs / stories / link-story / unlink-story / by-iteration / fields | 测试计划与执行进度管理 |
| `user` | info / workspaces | 当前用户信息与权限项目列表 |

## 核心纪律与操作规范

### 查询纪律

- **列表查询必须带 `fields`**：不带 `fields` 会导致返回全量字段，Token 消耗增加 5-21 倍。概览查询不带 `description`，只有需要实体详情时才追加 `description`。
- **精确查询流程**：用户意图模糊时（如“查 CRM 模块的 Bug”、“看看基础业务团队的缺陷”），先查阅 [references/xiaoke-tapd-dict.md](references/xiaoke-tapd-dict.md)；若不在词典中，用 `tapd-cli <entity> fields` 配合 `jq` 探索合法 options；再用精确枚举值构建查询，禁止盲猜。
- **自定义字段传值**：设置下拉/单选/多选类 `custom_field_*` 时，必须传候选项文案本身，禁止传数字序号或下标。详见 [references/custom-fields.md](references/custom-fields.md)。
- **全量字段查看**：CLI 默认省略空字符串的 `custom_field_*`，如需查看全量空值字段可加 `all-fields=1`。

### 字段约定

- **优先级**：使用 `priority_label`（`High` / `Middle` / `Low`），不用 `priority`。
- **缺陷字段**：标题用 `title`（不是 `name`），负责人用 `current_owner`（不是 `owner`）。
- **创建身份**：创建时显式传入 `reporter=<真实 TAPD 用户名>`，并将同一用户传给 `current_owner`；`creator`/`created_by` 不可传。TAPD 会把历史记录的创建人绑定到 Token，更新接口不能修正既有 Bug 的 reporter。
- **状态筛选**：使用 `v_status` 传中文状态名，避免因项目自定义状态英文 key 不一致导致查询为空。

### 本项目 Bug 创建字段基线

创建前必须执行 `tapd-cli bug fields workspaceid=<workspace_id> all_options=1`，以项目返回值为准。
当前已验证字段：`title`（标题）、`description`（Markdown/HTML 详情）、`severity`、`priority_label`、`current_owner`、`reporter`、`iteration_id`、`version_report`、`module`。创建 Bug 时必须显式传入 `reporter` 和 `current_owner` 的真实 TAPD 用户名（禁止使用 `tapd_my_token`），并传入需求关联字段 `story_id`；创建后必须查询回执确认关联需求，否则状态为 `blocked`。需求的 `iteration_id` 应先从 story 查询后回写到 Bug。

Bug 详情统一包含访问路径、实际执行账号的租户/账号/密码、前提条件、复现步骤、带 TraceID 的实际结果、预期结果、备注说明和“重现规律：可复现”。账号必须来自本次实际 Case 执行凭证，禁止用示例账号替代；密码只写入 TAPD 详情，不得写入代码、Artifact、日志或提交记录。

### Bug 关联需求与迭代

`bug add story_id=...` 在部分项目中会被 TAPD 忽略。创建成功后必须执行：

```bash
tapd-cli story link-bug workspaceid=<workspace> story-id=<URL末段全局story-id> bug-id=<bug-id>
tapd-cli bug related-stories workspaceid=<workspace> bug-id=<bug-id>
```

只有 `related-stories` 回读包含目标全局 story id 才算关联成功，否则结果必须标记为 `blocked`。需求短展示 ID 与 URL 末段全局 ID 不可混用。创建前查询需求 `iteration_id`，创建时传入；创建后回读 Bug 确认迭代非空。

软件平台必须先用 `bug fields` 查询合法枚举，并按被测系统填写：服务端使用 `platform=Server`，Web 前端使用 `platform=Web`，不可留空或猜测。测试阶段统一传 `testphase=业务测试`。Bug 引入时机字段为 `custom_field_22`：需求新增能力判定为 `新功能`，既有能力回归/修改判定为 `老功能`。版本字段为 `version_report`，必须从需求的 `version`/版本字段获取并校验为项目合法枚举后传入；需求无版本时标记待补，不得伪造版本。
（`fatal`/`serious`/`normal`/`prompt`/`advice`）、`module`（报表、拼表、统计图、目标、
驾驶舱、图表组件、订阅、CRM首页、权限、导出/分享/转发等、其他）、`current_owner`（TAPD
用户名）和 `story_id`（需求关联）。枚举为空或 CLI 非零时禁止猜测和创建；若 `story_id`
不被项目接受，创建成功后必须单独执行关联并记录回执。

### 创建实体字段引导

- **确定 `workspace_id`**：用户指定 > URL 解析提取 > 上下文上下文记忆 > 默认 `20019471` > 执行 `tapd-cli user workspaces` 供用户选择。不得用默认值覆盖用户明确提供或从 URL 提取的项目 ID。
- **确定处理人**：用户指定 > 上下文已知 TAPD 用户名 > 询问用户。
- **未指定优先级**：默认使用 `priority_label=Middle`。

### 写操作与读操作

- **读操作**：查询、计数、读取详情可直接执行。
- **写操作**：创建、更新状态、修改负责人、发表评论、上传附件、记录工时前，若用户未明确表示“直接执行”，先列出目标 `workspace_id`、实体类型、实体 ID、关键字段和值，等待用户确认。
- **Dry-run**：用户要求“只列命令”或“dry-run”时，仅输出命令参数，不调用 CLI。
- **本地文件处理**：生成的本地文件（截图、报告等）需上传为 TAPD 附件或项目文档，用户无法直接访问 Agent 本地文件系统。

## 输入约束

- 命令格式固定为 `tapd-cli <entity> <subcommand> [key=value ...]`。
- 所有业务参数使用 `key=value` 格式传入。
- 参数名支持 `-` 和 `_` 两种分隔符，例如 `entry-id` 等价于 `entry_id`。
- 命令行显式传参优先级高于环境变量默认值。
- 使用非快捷命令时，必须先执行 `tapd-cli <entity> <subcommand> --help` 查看参数说明，禁止猜测参数。
- 涉及 Token、密钥、Cookie 等敏感信息时禁止输出明文。

### 环境变量

| 变量 | 必须 | 用途 |
| --- | --- | --- |
| `TAPD_API_ENDPOINT` | 是 | API 端点，如 `https://api.tapd.cn` |
| `TAPD_TOKEN` | 是 | 个人令牌，从 TAPD 个人中心获取 |
| `TAPD_WORKSPACE_IDS` | 建议 | 项目 ID 列表，多个项目用英文逗号分隔，第一个为默认值 |
| `TAPD_NPC_ROLE` | 否 | NPC 登录名，作为默认 author/creator |
| `TAPD_SITE_URL` | 否 | TAPD 前端域名，用于拼接实体链接 |
| `TAPD_COMPANY_ID` | 否 | 公司 ID |
| `TAPD_ENTRY_TYPE` | 否 | 当前实体类型，如 `stories`、`bug`、`tasks` |
| `TAPD_ENTRY_ID` | 否 | 当前实体 ID |
| `TAPD_COMMENT_ID` | 否 | 触发评论 ID，回复时用作 `reply_id` |
| `TAPD_COMMENT_ROOT_ID` | 否 | 根评论 ID，回复时用作 `root_id` |
| `TAPD_COMMENT_LOCATION` | 否 | 评论来源位置标识 |
| `TAPD_USER_NAME` | 否 | 触发操作的用户名 |
| `TAPD_CONTEXT` | 否 | 当前上下文链接或描述 |
| `TAPD_NPC_QUERY` | 否 | NPC 收到的原始用户输入 |
| `TAPD_CLI_LOG` | 否 | 日志模式：`1` / `text` / `json` / `silent`，默认 `silent` |

调用命令前**优先使用系统已注入的环境变量**作为实体 ID / 项目 ID / 评论 ID 等参数。

## 输出格式

- 查询类命令优先保持 `tapd-cli` 原始输出，不要改写字段名。
- 面向用户总结时，应提取关键字段并用简洁列表或表格呈现（详见 [references/response-structure.md](references/response-structure.md)）。
- 创建、更新、上传类命令需要明确说明执行结果、目标实体和关键 ID。
- 命令失败时需要说明失败原因，并在必要时给出下一步可执行命令。
- 生成的本地文件必须上传或转换为用户可访问的结果，因为用户无法直接访问 Agent 本地文件系统。

## 使用示例

### 完整调用示例：查询需求

用户需求：查询项目 `12345678` 下状态为“规划中”的前 20 条需求。

调用命令：

```bash
tapd-cli story list workspaceid=12345678 v_status=规划中 limit=20 fields=id,name,status,owner,priority_label,created
```

参数说明：

- `story list`：查询需求列表。
- `workspaceid=12345678`：指定 TAPD 项目 ID。
- `v_status=规划中`：只返回状态为“规划中”的需求。
- `limit=20`：最多返回 20 条记录。
- `fields=...`：限制返回字段，减少 Token 消耗。

预期结果：返回符合条件的需求列表，包含需求 ID、标题、状态、负责人等字段。

### 完整调用示例：创建缺陷

用户需求：在项目 `12345678` 下创建一个严重级别为 `serious` 的缺陷，并分配给 `user1`。

调用命令：

```bash
tapd-cli bug add workspaceid=12345678 title="登录页崩溃" severity=serious current_owner=user1
```

预期结果：在指定项目下创建缺陷，并返回缺陷 ID、标题、状态、负责人等字段。

### 完整调用示例：回复当前评论

用户需求：在当前 TAPD 实体下回复触发 Agent 的评论。

调用命令：

```bash
tapd-cli comment add workspaceid=$TAPD_WORKSPACE_ID entry-type=$TAPD_ENTRY_TYPE entry-id=$TAPD_ENTRY_ID root-id=$TAPD_COMMENT_ROOT_ID reply-id=$TAPD_COMMENT_ID description="已收到，正在处理"
```

预期结果：在当前 TAPD 实体下新增一条评论回复，并返回评论 ID 或执行结果。

### 快捷命令

| 命令 | 作用 |
| --- | --- |
| `tapd-cli comment add entry-type=$TAPD_ENTRY_TYPE entry-id=$TAPD_ENTRY_ID description=内容` | 在当前实体发表评论 |
| `tapd-cli comment add entry-type=$TAPD_ENTRY_TYPE entry-id=$TAPD_ENTRY_ID root-id=X reply-id=X description=内容` | 回复评论，两个参数必须同时提供 |
| `tapd-cli comment list entry-type=stories entry-id=xxx` | 列出评论 |
| `tapd-cli story list fields=id,name,status,owner,priority_label,created` | 列出需求概览 |
| `tapd-cli story add name=标题 priority_label=High owner=用户名` | 创建需求 |
| `tapd-cli story update id=xxx status=developing` | 更新需求状态 |
| `tapd-cli story fields` | 查看需求字段定义 |
| `tapd-cli story related-bugs story-id=xxx` | 查看需求关联的缺陷 |
| `tapd-cli story link src-story-id=xxx target-story-id=yyy` | 关联需求 |
| `tapd-cli bug list fields=id,title,status,severity,current_owner,created` | 列出缺陷概览 |
| `tapd-cli bug add title=标题 severity=serious current_owner=用户名` | 创建缺陷 |
| `tapd-cli bug update id=xxx status=closed` | 更新缺陷状态 |
| `tapd-cli bug fields` | 查看缺陷字段定义 |
| `tapd-cli bug link-tcase bug-id=xxx` | 查看缺陷关联的用例执行结果 |
| `tapd-cli task list fields=id,name,status,owner,due_date,created` | 列出任务概览 |
| `tapd-cli task add name=标题` | 创建任务 |
| `tapd-cli task update id=xxx status=done` | 更新任务状态 |
| `tapd-cli iteration list fields=id,name,status,startdate,enddate` | 列出迭代 |
| `tapd-cli wiki list` | 列出 Wiki 页面 |
| `tapd-cli wiki add name=标题 creator=用户名 markdown_description=正文` | 创建 Wiki |
| `tapd-cli timesheet list owner=用户名 fields=id,owner,spent,created` | 查询工时记录 |
| `tapd-cli attachment by-entity entry-id=xxx` | 查询实体附件 |
| `tapd-cli attachment upload type=bug entry-id=xxx file=路径` | 上传附件 |
| `tapd-cli attachment upload-image file=路径` | 上传图片到富文本 |
| `tapd-cli document download id=xxx` | 获取项目文档下载链接 |
| `tapd-cli tcase list fields=id,name` | 列出测试用例 |
| `tapd-cli tcase import-xmind file=路径 creator=用户名` | 从 `.xmind` 文件导入测试用例 |
| `tapd-cli testplan list fields=id,name,status` | 列出测试计划 |
| `tapd-cli testplan progress id=xxx` | 查看测试计划执行进度 |
| `tapd-cli user info` | 查询当前用户信息 |
| `tapd-cli user workspaces` | 列出当前用户有权限的所有项目 |

## 已知限制

- 运行环境需要 Node.js 18+。
- 使用前必须配置有效的 `TAPD_API_ENDPOINT` 和 `TAPD_TOKEN`。
- `workspaceid` 未显式传入时，会使用 `TAPD_WORKSPACE_IDS` 的第一个项目 ID。
- 回复评论时，`root-id` 和 `reply-id` 必须同时提供。
- 上传附件、图片、导入 XMind 等文件类操作依赖本地文件路径可访问。
- `document download` 接口获取的是文档下载链接（有效期通常有限制）。
- 失败处理最多尝试 2 次，禁止无限重试。

## 安装 CLI

检查是否已安装：

```bash
tapd-cli --help
```

### 一键安装

**macOS / Linux**：

```bash
curl -fsSL https://cnb.cool/tapd.cn/skills/tapd-cli/-/git/raw/main/install.sh | sh
```

**Windows PowerShell**：

```powershell
irm https://cnb.cool/tapd.cn/skills/tapd-cli/-/git/raw/main/install.ps1 | iex
```

脚本会自动识别 OS + 架构，下载最新版到 `~/.local/bin/tapd-cli`（Windows: `%USERPROFILE%\.local\bin\tapd-cli.exe`），并配置 PATH。
所有历史版本见 <https://cnb.cool/tapd.cn/skills/tapd-cli/-/releases>。

## 查看帮助

```bash
tapd-cli --help
tapd-cli <entity> --help
tapd-cli <entity> <subcommand> --help
```

## 执行规则

- 优先使用快捷命令，不满足时再用 `--help` 逐步查找。
- 使用非快捷命令时，必须先 `--help` 获取帮助，禁止猜测参数。
- 用户已明确要求执行 TAPD 操作时，直接执行命令，不要重复询问确认。
- 禁止泄露 Token、密钥等敏感信息。
- 命令失败时最多重试 2 次。
