---
name: code-search
description: 当用户提供错误堆栈、异常类名、函数名、文件路径并说"帮我查下这段代码""是不是代码 bug""这个 NPE 在哪抛的""找到源码看看"，或问"这个仓库/服务是做什么的""XX 领域知识、业务规则、术语、代码逻辑去哪个仓库、在哪儿查"，或 fx-ops/fx-ops-tracing 在 RCA 中判定故障层为"代码缺陷"需要深入源码定位时使用。先查 references/repo-catalog.md 的仓库索引定位仓库与 ai-wiki 领域知识页，再用 sourcebot-cli 跨仓库搜索代码，分析堆栈、追踪符号定义与引用、对比最近变更，输出结构化代码级根因结论。
---

# code-search — 代码级根因定位

## CLI 执行目录（必须）

所有 Sourcebot 取证**只**用本 skill 的 `scripts/sourcebot-cli.py`（**禁止**挂载 Sourcebot MCP）。在仓库根执行：

```bash
cd .agents/skills/code-search
uv run --no-sync python scripts/sourcebot-cli.py <command> ...
```

能力登记见 [references/sourcebot-cli-capabilities.md](references/sourcebot-cli-capabilities.md)。

## 业务仓库索引与领域知识（先查表，再动手）

[references/repo-catalog.md](references/repo-catalog.md) 是**业务仓库索引**：每个业务仓的「一句话职责」，
其 `name` 列同时是 **ai-wiki 目录**（`<ai-wiki-root>/domains/<name>/`）与 sourcebot `--repo` 的 canonical 值。

**定位任何仓库前先查它**，避免靠 `list-repos --query` 猜名字。

| 目标 | 入口 |
| --- | --- |
| 这个仓库是做什么的 / `--repo` 该填什么 | `references/repo-catalog.md` 主索引 |
| 该仓库的领域知识、业务规则、术语、不变量 | `<ai-wiki-root>/domains/<name>/README.md` → 按页内「按任务路由 / 按读者场景导航」进具体页 |
| 术语 / 类名 → 代码锚点 | 该仓根 `glossary.md`（如有），条目形如 `path#Lx-Ly`，可直接喂 `read-file --path --offset` |
| app / bizName → 仓库 | `repo-catalog.md` 的「怎么定位仓库与知识页」，**多命中或 0 命中即停**，不猜 |

领域知识的典型用法（**知识给假设，源码给事实**）：

```text
查 repo-catalog 定仓库 name
  → 读 <ai-wiki-root>/domains/<name>/README.md 与域页，拿到机制/不变量/术语与行锚
  → 行锚喂 sourcebot-cli.py read-file --repo <name> --path <path> --offset <锚点行>
  → 结论必须由源码或运行时证据支撑
```

- `<ai-wiki-root>` 默认请用环境变量 `AI_WIKI_ROOT`；索引缺失或该仓不在表中时按「无领域知识」处理，**不得**臆造仓库职责或页面路径。
- 索引由 `scripts/gen-repo-catalog.py` 生成（`--check` 校验漂移），**勿手工编辑**。

## 核心纪律

> [!IMPORTANT]
> **Sourcebot 只搜索远程业务代码仓库**（即被排查的 CRM/SFA/OA/BI 等业务系统），**绝对禁止**搜索当前宿主仓库自身的 skill、工具或文档代码。宿主仓库代码对线上故障诊断通常没有意义。

- **允许**：检索 ai-wiki 领域知识库（`<ai-wiki-root>/domains/**`，本地 Markdown，非宿主仓），用于先建立领域模型与拿代码行锚；这不违反上面的宿主仓禁令
- **必须**：**除 Step 2 仓库发现外**，每次定库调用 sourcebot 时都带上 `--repo` 参数，限定到目标业务仓库
- **必须**：Step 2 仓库发现完成前，不得进入 Step 3 代码搜索
- **必须**：证据落盘到主控分配的 evidence_dir；独立调用时使用 `output/evidence/<YYYYMMDD-HHMMSS>-<short-topic>-<channel>/` 格式
- **必须**：grep/glob/search 等搜索类调用始终附加 `--compact` 节省 token；read-file 调用不加 --compact（需全量源码做分析）
- **必须**：read-file 及任何关键证据调用始终附加 `--evidence-dir`（落盘后 fx-ops 可引用而不必重读）
- **严禁**：将当前宿主仓库的 skill、文档或脚本路径传入任何 sourcebot 调用；严禁在未确认远程仓库范围时进行全量搜索
- **任务无效条件**：在**已完成仓库发现后**的 grep/glob/read_file/symbol/commits/diff 等定库调用中未传入 `--repo` 参数，本次任务视为无效

### 证据优先原则（Evidence-First）

> 与 fx-ops 协同的关键设计：**证据先行，结论后出**。
> fx-ops 主控通过 `evidence_dir/index.md` 和 `evidence_dir/evidence/SRC-*` 文件引用代码证据，而不是靠 AI 记忆。

每次 read-file 调用必须带 `--evidence-dir`，搜索类调用（grep/symbol-def/commits）
如果结果将在 Step 6 结论中引用，也必带 `--evidence-dir`。格式：

```bash
# 读源码 + 落盘
uv run --no-sync python scripts/sourcebot-cli.py read-file \
  --repo "AppServer/fs-fmcg" --path "OrderService.java" --offset 130 --limit 30 \
  --evidence-dir $evidence_dir

# 搜索 + 落盘（后续引用）
uv run --no-sync python scripts/sourcebot-cli.py grep \
  --repo "AppServer/fs-fmcg" --pattern "NullPointerException" --compact \
  --evidence-dir $evidence_dir
```

落盘后，根目录 `evidence_dir/index.md` 自动追加相对路径引用；业务证据默认写入 `evidence_dir/evidence/`，fx-ops `converge` 阶段可直接读取。

### 成本层级（Cost Tiers）

对齐 fx-ops `cost-optimization.md` 的成本模型：

| 层级 | 操作 | 对应 CLI | Token 成本 |
|------|------|---------|-----------|
| **廉价探测** | 跨仓库 group-by-repo | `grep --pattern --group-by-repo --compact` | ~300 tokens |
| **中等搜索** | 定库 grep/glob/symbol | `grep/glob/symbol-def --compact` | ~600 tokens |
| **昂贵读取** | 读源码（必须全量） | `read-file`（不加 `--compact`） | ~4000 tokens/80行 |
| **变更溯源** | commits / diff | `commits/diff --compact` | ~1000 tokens |

**决策规则**：先廉价探测缩小范围，确认目标后再进行昂贵读取。
禁止对话中连续多次 `read-file` 试错。

### 与 fx-ops 的 handoff 契约（Handoff Contract）

被 fx-ops 以 sub-agent 调度时，通过 `HND-<dispatch_id>-code-search.md` 接收上下文：
- 调度方传入：异常堆栈、应用名（如有）、`evidence_dir` 路径、`time_window`
- 本 skill 必须读取 HND 文件明确需求，不得猜测

输出按 `output_result()` 协议 JSON 落盘 + stdout 摘要：

```json
{
  "status": "completed|partial|empty|error",
  "findings": "代码级根因分析（异常摘要、根因描述、修复建议）",
  "evidence_files": ["SRC-code-snippet-*.json", "SRC-search-result-*.json"],
  "confidence": "high|medium|low",
  "next_skills": ["fx-ops-query", "fx-ops-tracing"],
  "need_further": "人类摘要，不作为唯一下一跳依据；机器路由使用 route_hint + target_capability"
}
```

### i18n 熔断（强制前置检查）

> [!CAUTION]
> 进入 Step 1 之前必须执行此检查。命中即**立即停止 code-search**，转交 `fx-ops-metadata` 的 `i18n-multilingual` 模块。

**触发条件**（任一命中）：

- 异常消息/堆栈含：`resource_bundle`、`I18n`、`i18n`、`Locale`、`ResourceBundle`、`LocalizedMessage`、`MissingResourceException`、`翻译`、`多语言`
- 业务异常携带 i18n key 形式参数（如 `SFABusinessException("crm.xxx.yyy")`、`throw new XxxException(I18nKeys.XXX)`）
- 报错文案是占位符未解析（如直接显示 `crm.lead.xxx.error` 这种 key 字面量）

**关键认知（避免误报）**：

- 本项目国际化通过 key 到**两个库的 `i18n_entry` 表**查找，**不是基于 properties 文件**：
- `paas-i18n` 系统库：同时含系统级（`tenant_id = 0`）与租户级覆盖
- `paas` 租户业务库：租户业务库内部维护的词条
 properties 仅用于少量遗留代码的开发期默认值。
- **抛异常携带 i18n key 是正确架构**：`throw new SFABusinessException(errorCode)` 由框架层在运行时按租户/语言解析为实际文本。**禁止**判定为"代码缺陷"或"缺失 properties 配置"。
- **禁止**给出"补充 properties 词条"类修复建议——会引入两套 i18n 机制的数据不一致。

**正确动作**：终止本次 code-search，告知用户/主控转 `fx-ops-metadata` 走 i18n-multilingual 模块，**同时查 `paas-i18n` 与 `paas` 两库的 `i18n_entry`**（两库都查不到才考虑是代码逻辑缺陷、才回到 code-search）。

### CEP / reqId 错误码熔断（强制前置检查）

页面/CEP 错误码（`s311…`、`1-hex` reqId）**不是**仓库里的枚举表；**禁止**以该串为 pattern 做 Sourcebot grep「查定义」。策略 C 亦不得用裸错误码当 pattern。

**触发条件**（任一命中即**立即停止**，回抛主控走 `fx-ops-query` / `fx-ops-tracing`）：

- 调度输入**仅有**页面/CEP 错误码：`s\d{6,}`（如 `s311034432`）或标准 `reqId`（`1-52bd16`），**无** Java 堆栈、无 `类.方法:行号`
- Step 1 解析结果只剩错误码字符串，拟用策略 C `sourcebot-cli.py grep` 搜该码「查含义/定义」
- 用户仅问「`s311…`/错误码是什么意思」— **本 skill 不适用**；**禁止**用 Sourcebot 或文字编造码义，应交编排方走日志定位

**正确动作**：不调用 Sourcebot；由主控用 `has(reqId, …)` / `log_cep_dist` + 时间窗反查 trace，再用 `error` 字段与 `log_error_dist` 堆栈决定是否**再次**进入 code-search。

## 执行流程

> **调用约定**：所有代码搜索/读取/变更溯源都通过 `sourcebot-cli.py` 直接调用
> （grep/glob/read-file/symbol-def/symbol-ref/commits/diff/list-repos/list-tree）。
> 搜索类调用附加 `--compact` 节省 token（保留缩进，仅删空行）；read-file 不加 `--compact`（需全量源码分析）。
> 关键证据调用附加 `--evidence-dir <path>` 落盘，fx-ops `converge` 阶段可直接引用而不重读。
> CLI 连接凭据来自环境变量 `SOURCEBOT_API_KEY`（或 `.env.local`），直接走 HTTP API，不依赖任何 server 配置。

```
输入（堆栈 / 函数名 / 文件名 / 错误消息）
 |
 v
Step 1: 输入解析 —— 提取关键符号
 |
 v
Step 2: 仓库发现 —— 确定搜索范围（MANDATORY 前置步骤）
 |
 v
Step 3: 代码搜索 —— 多策略并行（使用 sourcebot-cli.py --compact）
 |
 v
Step 4: 源码阅读 —— 理解上下文（使用 sourcebot-cli.py read-file + --evidence-dir）
 |
 v
Step 5: 变更溯源 —— 最近改动分析
 |
 v
Step 6: 结论输出 —— 结构化代码级 RCA
```

### Step 1: 输入解析

从用户输入提取：异常类名、异常消息、抛出位置（类+方法+行号）、调用链关键类/方法。缺什么问什么，不猜。

| 输入类型 | 提取目标 | 示例 |
|----------|----------|------|
| Java 堆栈 | 异常类名、抛出位置、调用链 | `NullPointerException` at `OrderService.create(OrderService.java:142)` |
| 函数名 | 函数/方法名、所属类名 | `createOrder`、`UserService.getById` |
| 文件名 | 文件路径 | `OrderService.java`、`application.yml` |
| 错误消息 | 异常类型、关键参数值 | `DuplicateKeyException: Duplicate entry '123'` |

### Step 2: 仓库发现（MANDATORY）

仓库名未知时，不得进入 Step 3。所有待发现的仓库均指**远程业务代码仓库**，不包含当前宿主仓库。

0. **先查索引**：读 [references/repo-catalog.md](references/repo-catalog.md)。已知业务名/服务名/app 名时，用它解析到 canonical `name`（= `--repo` 值）与该仓的 ai-wiki 领域知识路径；解析为 0 或多命中时**停下**，按「目录与命名规则」回退后一步，禁止猜
1. **已知仓库名**：直接使用（建议先用索引核对 `name` 是否为 canonical 形式）
2. **已知应用名 / K8s 部署名**：先用索引的「app → 仓库」规则解析；解析不出再 `sourcebot-cli.py list-repos --query <name> --compact` 匹配（来自 `KNO-service-owner` 的 `appName`、堆栈包名、或 URI 推断的模块名）
3. **仅知道服务类名**：先用 `sourcebot-cli.py symbol-def --symbol <ClassName> --repo <候选>` 定位，或用跨仓库 `grep --group-by-repo` 探测
4. **完全未知**：`sourcebot-cli.py list-repos --query <keyword> --compact` 列出候选，再用 `sourcebot-cli.py grep --pattern "堆栈类名" --group-by-repo --compact` 用**堆栈类名/异常消息**探测；**禁止**用 CEP `log_cep_dist.bizName`（如 `FUNC`、`DEV`、`SFA`）、页面「服务:XXX」缩写、或 `s311…`/`1-hex` reqId 当仓库检索键——这些字段不在业务源码仓库中，也无 bizName→repo 的 Sourcebot 映射
5. **顺带建立领域模型**：仓库确定后，先读该仓在 ai-wiki 的 `README.md`（再按需进 `domains/*`、`glossary.md`）拿到机制、不变量与行锚，再进入 Step 3 定库搜索——可显著减少盲目 grep 与试错读取

> 不确定仓库范围时，先用 `grep --group-by-repo --compact` 做探测。发现结果中出现当前宿主仓库时，**直接忽略**，它不是被排查对象。

### Step 3: 代码搜索

多策略并行，详情见 references/search-strategies.md。

所有搜索调用都通过 `sourcebot-cli.py` 执行，并附加 `--compact` 节省 token。
当需要保留结果供后续分析时，附加 `--evidence-dir $evidence_dir` 落盘。

简要：

- 策略A: 堆栈定位（有行号）→ `sourcebot-cli.py read-file`
- 策略B: 符号定义（有类名/方法名）→ `sourcebot-cli.py symbol-def`
- 策略C: 错误消息搜索 → `sourcebot-cli.py grep --compact`
- 策略D: 异常类搜索 → `sourcebot-cli.py grep --compact`
- 策略E: 文件名搜索 → `sourcebot-cli.py glob --compact` + `sourcebot-cli.py read-file`

### Step 4: 源码阅读

遵循**逐步展开**原则：先读异常行附近（20 行），不够扩大到方法（50-100 行），再不够读整个类。

- **异常行上下文**：`sourcebot-cli.py read-file --repo <repo> --path <path> --offset <start> --limit <count>`（不加 `--compact`，需要全量源码分析；`--offset` 1-indexed 最小 1，传 0 报错）
- **调用方分析**：`sourcebot-cli.py symbol-ref --symbol <method> --repo <repo> --compact` 查找调用方，理解入参来源
- **数据流追踪**：追踪空值/非法值来源（参数未校验？查询结果为空？并发竞争？）
- **防御性检查**：对比同仓库中同类异常的处理模式

### Step 5: 变更溯源

当代码缺陷疑似最近引入时：

- `sourcebot-cli.py commits --repo <repo> --path <path> --since "7 days ago" --compact` 查看最近提交
- `sourcebot-cli.py diff --repo <repo> --base <old> --head <new>` 查看可疑提交变更
- 关注：最近修改、空值风险引入、TODO/FIXME 标记
- 需要分支对比时用 `--ref` 参数指定分支名或 commit SHA

### Step 6: 结论输出

输出结构化代码级 RCA，包含：异常摘要（类型+位置+触发条件）、根因描述（2-3 句）、证据链（堆栈→源码→调用分析→变更溯源）、修复建议。

**证据落盘**：`read-file` 经 `sourcebot-cli.py` 写入 `evidence_dir/evidence/SRC-code-snippet-{ClassOrFile}-L{lineStart}-{6hex}.json`（语义段 + 短随机尾防并行撞名；glob 仍匹配 `SRC-code-snippet-*.json`）。若传入参数本身已是 `.../evidence`，则直接写该子目录。格式：
```json
{
 "meta": { "source": "code-search", "time": "<ISO_TIMESTAMP>" },
 "data": {
  "repo": "<仓库名>",
  "filePath": "<文件路径>",
  "lineStart": <起始行号>,
  "lineEnd": <结束行号>,
  "highlightedLines": [<问题行号数组>],
  "context": "<代码上下文文本>"
 }
}
```

## 输出回抛

按 fx-ops 总控回抛协议返回（见上方 handoff 契约）：

- **status**: completed / partial / empty / error
- **findings**: 代码级根因分析（异常摘要、根因描述、修复建议）
- **evidence_files**: 已落盘的证据文件列表（优先引用 `--evidence-dir` 落盘文件）
- **confidence**: high / medium / low
- **need_further**: 人类摘要，不作为唯一下一跳依据；机器路由使用 `route_hint` + `target_capability`

### 被调度时的约定

- 调度方传入：异常堆栈、应用名（如有）、时间窗口（如有）
- 本 skill 输出结构化代码级 RCA 回传给调度方
- 发现非代码层面问题时标注为"待其他 skill 继续验证"并建议能力类型
