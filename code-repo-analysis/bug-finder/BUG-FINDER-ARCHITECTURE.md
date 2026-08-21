# bug-finder 整体架构、能力与实现梳理

> 分析对象：`/Users/liushanshan/code/QA/bug-finder`
>
> 分析时间：2026-08-21
>
> 代码快照：`e6251222`（`docs(fx-ops-query): scope dbname-to-IP query to status=0 current records`）

## 1. 结论先行

`bug-finder` 不是一个传统的 Web 服务，也不是一个单独的 Python 命令行工具。它是一个由 AI Agent 驱动的故障诊断工作台，核心由三部分组成：

1. `AGENTS.md` 和各个 `SKILL.md`：定义用户意图分流、角色边界、取证流程、证据合同和报告门禁。
2. `.agents/skills/*/scripts/`：确定性执行层，负责调用 IDP、数据库、Prometheus、Sourcebot 等外部能力，产出 JSON 事实和证据文件。
3. AI 主会话与 sub-agent：负责理解用户问题、选择首跳编排器、决定是否升级、并行派发技能、解释事实、形成结论和读者报告。

可以把它概括为：

```text
用户问题
   |
   v
AI 主会话读取 AGENTS.md，选择一个 L1 入口
   |
   +-- fx-ops          单点故障 RCA
   +-- fx-ops-patrol   主动巡检 / 健康判断
   +-- fx-ops-postmortem 影响评估 / 故障复盘
   |
   v
L2 专业技能与基础能力（通过 Agent/sub-agent 调度）
   |
   v
Python/Node 确定性采集器调用 IDP、ClickHouse、Prometheus、对象 API、CMS、Oncall、K8s、Sourcebot
   |
   v
evidence_dir：原始证据、manifest、facts、状态、决策
   |
   v
AI 读取 facts + decision，按报告合同生成 Markdown / 可选 HTML
```

最重要的设计约束是“事实、调度、报告”分离：

```text
Python 采集 / 归一化 / 判定输入
        -> DIA/PAT/IMP 等结构化事实
AI 决定下一步、严重度、是否升级和根因解释
        -> decision / orchestration ledger
AI 根据证据和决策写 Markdown / HTML
```

Python 脚本不能代替 AI 做全局编排，不能凭空生成根因，也不能用模板程序拼接读者报告。

## 2. 仓库实际组成

### 2.1 根目录职责

| 路径 | 作用 |
| --- | --- |
| `AGENTS.md` | 总入口规则、三条用户意图路径、首跳硬规则、证据和安全红线 |
| `README.md` | 产品能力总览、技能分层和使用边界 |
| `QUICKSTART.md` | Node/pnpm、Token、bootstrap、编辑器技能同步的快速安装说明 |
| `.agents/skills/` | 所有技能定义、参考文档、采集脚本、契约、测试和 fixtures |
| `scripts/` | 仓库初始化、技能同步、Node/Token/Hook 配置、文档和触发规则检查 |
| `tests/` | 根目录的 Vitest/Node 测试，覆盖 bootstrap、触发、编排、报告和路径评分 |
| `docs/` | 架构、开发流程、Git、Issue、知识库、ADR 和长期设计文档 |
| `fixtures/` | 可重复测试和评估所需的快照、停止条件等固定输入 |
| `.pi/`、`.grok/`、`.mimocode/` 等 | AI 编辑器插件、Hook 或观测集成配置 |
| `package.json` | Node/pnpm 任务入口；主要用于维护、校验和测试，而非业务诊断服务端 |
| `pyproject.toml` | Python 3.12+、`jsonschema`、`PyYAML`、`sqlparse` 及 pytest/ruff 配置 |

当前快照没有 `src/` 目录，但 `package.json` 仍保留 `dev/build/start` 对 `src/index.ts` 的引用。因此根目录 Node 应用入口目前不是实际诊断运行时；实际运行面是技能目录中的脚本和 AI 编辑器加载的 Skill 文档。`pnpm` 脚本主要用于 bootstrap、lint、契约测试和回归测试。

### 2.2 技能规模

扫描当前快照得到：

- `.agents/skills/` 下 33 个技能目录。
- 约 284 个 Python 文件，约 61 个 JS/TS 文件，约 1115 个 Markdown 文件（包含 reference、playbook、对象字典、测试说明等）。
- 测试文件约 192 个，覆盖根目录和各技能的 Python/Node 测试。
- `fx-ops/scripts/fx_ops_cli.py` 注册 26 个公开 capability ID；未知 ID 会 fail-closed 返回退出码 2。

Markdown 数量很大是有意的：`SKILL.md` 保留运行时必须知道的最小协议，字段、表结构、SQL、PromQL、报告 HTML 和专项 playbook 放在 `references/`，按需渐进读取。

## 3. 分层架构

### 3.1 L1：三个平级编排器

主会话根据用户意图只选择一个首跳入口；三者职责互斥，不互相替代。

| L1 入口 | 负责什么 | 不负责什么 | 主要产物 |
| --- | --- | --- | --- |
| `fx-ops` | 报错、traceId/reqId、CEP、NPE/OOM、慢请求、实时故障 RCA | 不负责主动巡检和默认影响评估 | `DIA-incident-facts.json`、`DIA-verdict-bundle.json`、RCA decision、证据索引、报告 |
| `fx-ops-patrol` | 晨检、值班交接、健康判断、红黄绿巡检 | 不做单条请求的完整根因 RCA | `PAT-patrol-data.json`、`JDG-input.json`、`JDG-judgement-result.json`、巡检状态 |
| `fx-ops-postmortem` | 网关影响面、受影响企业/接口/时长、标准影响评估、完整复盘 | 不接实时单链路定位；完整复盘无根因上下文会阻断 | `IMP-impact-assessment.json`、`PMR-postmortem-report.json`、时间线及复盘证据 |

### 3.2 L2：专业执行技能

#### 业务域技能

这些技能按业务语义缩小范围，并执行本域取证；它们没有全局编排权：

- `fx-ops-sfa`：CRM 客户、线索、公海、订单、合同、CPQ、价格政策等。
- `fx-ops-fmcg`：快消外勤、考勤、陈列、定位、TPM、订货和预置对象接入。
- `fx-ops-oa`：OA 审批协同、菜单/按钮/角色、企信待办、组织选人。
- `fx-ops-plat`：登录、CEP 网关、SSO、沙盒、更改集和平台认证。
- `fx-ops-bi`：BI 报表、驾驶舱、数仓、copier、聚合、导出和订阅。
- `fx-ops-workflow`：审批流、BPM、OneFlow、定时触发、任务流和 APL 回调。
- `fx-ops-metadata`：对象描述、共享规则、数据权限、PG/ES 一致性、唯一性和多语言资源。
- `fx-ops-udobj`：自定义对象/字段、验证规则、自动编号、字段依赖、导入导出、打印模板和异步计算。
- `fx-ops-eservice`：制造/订货/售后工单、库存、信用、发货退货、BOM、SLA。
- `fx-ops-erp-sync`：ERP Sync、iPaaS、外部 OA、连接器、字段映射、回写和重试。
- `fx-ops-bfe`：iOS/Android/鸿蒙/小程序/H5/Web、企微/飞书/钉钉入口差异、附件、多语言、地图和登录会话。
- `fx-ops-er`：sync-data 1+n 策略、快照、过滤、目标写入和重试。
- `fx-ops-sms`：验证码、短信通道、回执、频控、黑名单和供应商异常。
- `fx-ops-rocketmq`：消费组、topic、积压、延迟、重复消费、发送失败和组件配置。

#### 通用基础能力

- `fx-ops-tracing`：从 CEP 网关到应用错误、慢 SQL、Tomcat、RPC 的单请求链路诊断。
- `fx-ops-monitoring`：Prometheus/PromQL、Grafana、RED + USE 运行时分析。
- `fx-ops-query`：ClickHouse、MySQL、PostgreSQL、MongoDB、对象 PG/ES 对账、APL 日志和 SQL 证据。
- `fx-ops-object`：CRM 对象 describe、SOQL、字段字典和对象数据查询。
- `fx-ops-knowledge`：负责人、服务等级、发布记录、配置变更、历史故障、Bug 和组织知识。
- `fx-ops-timeline`：指标、错误、发布、配置、K8s、MQ 等多源事件时间线和因果对齐。
- `fx-ops-apl`：APL 函数定义、版本、执行日志、限额、owner、性能和 `Fx.*` API 问题。

#### 专项、工具和维护技能

- `fx-ops-oncall`：告警记录、值班人、分派策略、升级链路、静默和通知历史。
- `fx-ops-pyroscope`：CPU/内存/线程异常下钻到方法、调用栈、大对象和锁竞争。
- `fx-ops-k8s-app`：应用/Pod 版本、状态、日志、构建、发布、回滚、滚动重启。
- `fx-ops-bfe-perf`：前端 trace 的 FCP/LCP/TTI、接口、资源和渲染分段。
- `fx-ops-team-alert-rca`：按研发团队汇总未关闭告警工单并对齐错误堆栈、K8s 和 Prometheus。
- `code-search`：使用 Sourcebot 跨仓库定位类、方法、行号和引用。
- `fetch-config`：CMS profile 搜索、拉取、比对和脱敏。
- `fx-ops-share`：通过 IDP 上传本地报告或文件并生成公网分享链接。
- `archive`：归档过期的 superpowers/spec/plan/review 文档。

## 4. 用户意图如何分流

首跳规则在根 `AGENTS.md` 和三个 L1 的 `SKILL.md` 中重复约束，核心顺序如下：

| 用户输入 | 首跳 |
| --- | --- |
| traceId、reqId、CEP 错误码、报错截图、NPE/OOM、超时、失败、慢请求 | 只加载 `fx-ops`，先采集再决定是否派域技能 |
| “巡检、晨检、值班交接、系统健康度、有没有风险” | 直接 `fx-ops-patrol` |
| “复盘、影响了哪些企业、客户影响、影响时长、索赔” | 直接 `fx-ops-postmortem` |
| 只查 SQL/表/Mongo/ClickHouse | `fx-ops-query` |
| 只看 CPU/内存/PromQL/Grafana | `fx-ops-monitoring` |
| 只查 CRM 对象字段、SOQL、数据字典 | `fx-ops-object` |
| 只查 CMS 配置 | `fetch-config` |
| 只查负责人、发布、历史故障、Bug | `fx-ops-knowledge` |
| 只查告警和值班 | `fx-ops-oncall` |

业务词不会抢技术故障的首跳。例如“订单保存报错 + traceId”仍先走 `fx-ops`；主控读到 facts 后，才把业务部分 handoff 给 SFA、UDOBJ 或工作流技能。

## 5. `fx-ops` 单点 RCA 是怎么实现的

### 5.1 上下文归一化

主控先把自然语言整理成 `env`、`tenant_context`、`time_window`、`channel_type`、`channel_value`、`app_context` 等字段。长上下文写到 `handoffs/HND-*`，prompt 只传 `handoff_ref` 和 `evidence_index_ref`，避免把整份日志复制给每个 sub-agent。

`CTX-diagnostic-context.json` 是采集锚点证据，不是 AI 的最终事实结论；它记录 trace/reqId、环境、租户、时间、playbook 和阶段信息。

### 5.2 effort 分档

所有核心编排器统一支持 `auto/low/medium/high`：

- `low`：快速 scout，目标是秒级确认有没有决定性信号。
- `medium`：标准证据覆盖，补链路、错误、依赖、慢表和上下文。
- `high`：全量深挖、代码定位、完整报告和跨域时间线。
- `auto`：先执行 low scout，再依据事实决定 `stay_low`、升级 medium 或直接 high。

`auto_effort.py` 只根据 `DIA-verdict-bundle.json`、严重度、用户是否要完整 RCA、多租户/爆发和代码位置做机械的 stay/escalate 建议；它不写根因报告。

### 5.3 单 trace/reqId 的快速路径

公开入口由 `fx_ops_cli.py` 注册：

- `trace_entry` / `reqid_lookup`：按 traceId 或 reqId 查 CEP 入口。
- `parse_traceid`、`extract_error_anchor`：解析 trace 结构或用户粘贴的报错文本。
- `resolve_tenant_cloud`：租户到云环境/profile 的映射。
- `fast_rca`：单进程执行 H1-H4 判别性采集。
- `playbook_collect`：按 YAML playbook 的 Phase 0-N 执行固定 DAG。
- `incident_refresh`：把已有 evidence 重新投影为事实文件。

`fast_rca.py` 的采集不是固定全量扫描：

1. 默认 error/default lane 先查 CEP 锚点和应用错误。
2. 用户明确慢/超时时，首波并行 CEP、error、Tomcat 慢请求、SQL/Mongo 慢表。
3. 只有出现对应信号，才打开 DB 限制、业务流、ERP、权限、MQ、计算、同步、OpenAPI、批量和 metadata storm 等域探针。
4. 产出 `DIA-verdict-bundle.json`，其中的 H1-H4 是路由和判别事实，不等于根因。

有两个 trace 以上时，主控先按 `batch-trace-split.md` 做 CEP 分类，再一条 trace 启动一个瘦身 sub-agent，禁止把完整 pipeline 复制执行 N 次。

### 5.4 Playbook/DAG 执行

`references/evidence-playbooks/trace-anchor-v1.yaml` 定义 Phase、任务、依赖、必选性、输出文件和 parse reference。`playbook_loader.py` 负责加载并验证 YAML，`collect_core.py` 使用线程池并发执行 `CollectTask`，每个任务记录：

- `status`：ok、empty、skipped、error、timeout 等。
- `duration_ms`、`row_count`、`phase`、`parse_ref`。
- 产物文件和失败证据 `ERR-collect-*.json`。
- 空结果语义，例如“没有观测到”与“尚未查询”严格区分。

这使得“exit=0 但没有产物”也会被视为失败，防止静默失败被 AI 当成正常空结果。

### 5.5 Facts、decision 和收敛

`incident_refresh.py` 固定执行 `inject_context -> incident_facts`：

- `incident_facts.py` 读取证据文件，提取锚点、错误、慢请求、域信号、证据缺口、质量冲突和覆盖率。
- 结果写在证据目录根部的 `DIA-incident-facts.json`。
- facts 带 `schema_version`、`evidence_snapshot`、`observations`、`evidence_gaps`、`quality`，不包含 AI 自由推断。

AI 读 facts 后写 `CTX-ai-decision.json`；Node 编排账本记录事件和活动决策。`decision_loader.py` 在使用 decision 前会验证：

- facts/decision/state 是否都存在且满足 JSON Schema。
- 三者的 evidence snapshot、decision id、active hypothesis、revision 是否一致。
- selected actions 是否可执行。

不一致、过期或缺文件时返回 `awaiting_ai_decision` / `projection_error`，不会把旧决策当成当前决策。

### 5.6 域技能与代码定位

主控通过 Agent 工具把 `handoff_ref`、短执行约束和证据索引交给域技能。域技能只能回抛结构化结果：`status`、`findings`、`evidence_files`、`confidence`、`route_hint`，不能自行接管全局路由。

如果证据层判断是代码缺陷，必须调用 `code-search`：

1. 从异常类、堆栈、类.方法、URI 或 appName 提取搜索锚点。
2. 用 `.agents/skills/code-search/scripts/sourcebot-cli.py` 调 Sourcebot 跨仓库搜索。
3. 输出源仓库、类、方法、行号、调用关系、最近变更和可落地的 Java/业务代码修复方向。

## 6. `fx-ops-patrol` 巡检是怎么实现的

巡检不经过 `fx-ops`，由 `fx-ops-patrol` 自己管理状态机和预算。

### 6.1 23 项检查注册表

`patrol_registry.py` 维护 check、collector、query version、支持 profile、规范化字段和是否需要基线。当前注册的检查包括：

`pod_anomaly`、`cep_5xx`、`error_log`、`slow_sql`、`tomcat_access_slow`、`rpc_slow`、`tomcat_thread`、`traffic_anomaly`、`redis_health`、`k8s_node`、`rate_limit`、`oncall_alerts`、`capacity`、`mq_lag`、`agg_backlog`、`jvm_gc`、`alert_storm`、`pg_health`、`mysql_health`、`mongo_health`、`rocketmq_broker`、`es_slow`、`sql_write_spike`。

分档覆盖：

- low：7 项核心脉搏（告警、Pod、CEP 5xx、error、MQ、Tomcat 线程）。
- medium：14 项核心+运行时和慢 SQL。
- high：注册表全部 23 项，并带完整历史基线。
- auto：先执行 low NOW；只有确有基线候选时定向补一次 OLD，不自动升级为完整 high。

### 6.2 采集、判定、深挖

`patrol_fetch.py` 按 collector 分组并行采集，写出：

```text
output/patrol/<id>-<env>/
├── evidence/       NOW / OLD / NRM / CTX / ERR
├── judgement/      JDG-input.json / JDG-judgement-result.json
├── deep-dive/
├── CTL-fetch-manifest.json
├── SUM-fetch-compact.json
└── CTL-patrol-state.json
```

快扫完成后必须调用 `judge`。红黄绿由 `judge.py` 的确定性阈值和服务等级规则决定，AI 只能解释、合并红灯和调度深挖，不能改写颜色。`empty` 只有在采集完整、证据文件存在且确认无观测行时才是有效空结果；查询失败、字段不完整或 envelope 非法不能伪装成空。

红灯深挖按 L0/L1/L2 服务等级、应用和信号类型合并。巡检只输出 L1 初步分析，不替代 RCA；如果发现具体请求错误，应把线索交回 `fx-ops`。

## 7. `fx-ops-postmortem` 复盘是怎么实现的

复盘默认是“影响评估优先”，不是一上来猜根因。

### 7.1 影响主数据源

受影响企业、接口/服务范围、错误时段和持续时间必须优先来自网关 `log_cep_dist` 且 `status >= 500`。后台 `log_error_dist` 只能作为应用异常/根因佐证，不能代替客户感知影响面。

当描述包含攻击、扫描、渗透时，必须额外生成 `security_assessment`；5xx、错误量或流量下降只能证明服务异常，不能单独确认攻击。

### 7.2 collector registry 和分档

`postmortem_registry.py` 注册 gateway、error、changes、alerts、tomcat、rpc、runtime、k8s、database、mq、Tomcat thread、slo、tenant、owners、impact gate、assemble 等 collector，并用 wave、依赖和 resource tag 控制并发。

- `impact_only` / low / auto：网关影响、租户、负责人和 impact gate。
- `standard_impact` / medium：增加后台错误聚类、Tomcat/SLO、告警响应等。
- `full` / high：增加变更、RPC、运行时、K8s、数据库、MQ、时间线、改进和完整报告所需事实。

`postmortem_fetch.py` 是唯一的标准采集入口，按 wave 执行、复用证据、生成 `SUM-postmortem-fetch.json` 和 `CTL-postmortem-manifest.json`。完整复盘若缺少已收敛的 `root_cause_summary` 会 blocked，不会自行编造根因。

## 8. 证据与文件合同

### 8.1 目录和命名

每次诊断由主控分配绝对路径 `evidence_dir`。常见前缀含义：

| 前缀 | 含义 |
| --- | --- |
| `TRC-` | trace、CEP、错误、慢请求、RPC、应用日志证据 |
| `QRY-` | 数据库/聚合查询结果 |
| `CTX-` | 诊断上下文、应用发现、AI decision、编排状态 |
| `DIA-` | 诊断 facts、verdict、质量和深挖事实 |
| `MON-` / `HOS-` | Prometheus、Grafana、主机和运行时指标 |
| `PAT-` / `JDG-` / `CTL-` / `SUM-` | 巡检数据、判定、控制面和压缩摘要 |
| `EVID-` / `IMP-` / `PMR-` | 复盘 collector 证据、影响聚合和复盘报告 |
| `ERR-` | 采集或 facts 阶段失败证据 |

`evidence_index.py` 为 AI 建立可复用证据索引，列出路径、说明、覆盖范围和建议消费方；报告决策只能引用 `evidence/` 下可解析的 JSON 指针，禁止引用 prompt、日志、临时文件或之前生成的报告作为证据。

### 8.2 原子写入和快照

`evidence_write.py` 使用临时文件 + `os.replace` 原子写 JSON，并统一处理 BOM、紧凑 JSON、时间戳、NaN 和敏感/超大字段裁剪。事实和 decision 通过 SHA-256 snapshot 绑定，避免“采集结果已更新但 AI 仍使用旧结论”。

### 8.3 报告门禁

中高档 RCA 的报告流水线是：

```text
facts -> AI decision -> converge -> RPT-report-decision.json
      -> JSON Schema / evidence ref / claim gate 校验
      -> AI 生成 Markdown 或按需 HTML
```

校验器会检查：至少有 symptom claim 和 root_cause claim、claim ID 唯一、证据引用路径合法、机制证据不能只有状态/URI/计数、`probable` 必须有未闭环项、`final` 不能是 hypothesis、required review 必须完成。证据不足时必须输出 probable/partial/hypothesis/未取证，而不是“已定位”。

## 9. 外部依赖和真实执行面

### 9.1 IDP / `fx-ops` CLI

诊断脚本不直接把数据库密码写在仓库里，而是调用外部 `fx-ops`/IDP CLI。主要能力包括：

- `idp query`：MySQL、PostgreSQL、MongoDB 和统一 ClickHouse 日志数据源 `biz-app-log`。
- `idp prometheus query`：PromQL instant/range 查询。
- `idp grafana`：看板、panel、datasource、folder 只读查询。
- `idp object describe/query`：CRM 对象元数据和 SOQL。
- `idp cms`：CMS profile/配置搜索和拉取。
- `idp` 的 tenant、route、cloud、oncall、share 等运维旁路。

查询技能强调实时 `show columns`、明确时间窗、tenant/profile、LIMIT、只读性和字段类型检查，避免 ClickHouse 大表扫描和把空结果误判成“没有问题”。

### 9.2 Sourcebot

`code-search` 使用 `SOURCEBOT_API_KEY` 调 Sourcebot CLI，不配置 Sourcebot MCP。它只在已建立代码级假设或需要明确源码位置时被调用，CEP 错误码本身不能触发全仓库 grep。

### 9.3 配置和初始化

`QUICKSTART.md` / `scripts/bootstrap.js` 负责：

1. 检查 Node >= 24、pnpm 和 Python 环境。
2. 从 `.env.local` 读取 `FS_AGENT_TOKEN`、IDP profile token、Sourcebot token。
3. 配置 fx-ops profiles 和 shell 环境。
4. 执行 `scripts/sync-skills.js`，把 `.agents/skills` 链接或复制到 Claude Code、Grok、Codex、DeepSeek、CodeBuddy、OpenCode、Reasonix、Kiro 等编辑器目录。
5. 配置 Hook、运行时版本和仓库校验。

## 10. 测试、质量和维护机制

测试不是只测 SQL 结果，而是重点验证“编排不可越权”和“证据不撒谎”：

- 根目录 Vitest/Node：触发规则、bootstrap、skill lint、编排 gate、report title、path score、GitLab CI Node setup。
- `fx-ops` Python：trace 入口、playbook、facts、decision、evidence index、空结果、复杂度、effort、慢 SQL、上下文、质量冲突、契约和 CLI。
- Patrol：检查注册表、query safety、窗口、平台上下文、collector、judge、manifest、baseline 和模块化架构。
- Postmortem：collector、影响 gate、状态、时间索引、报告契约和布局。
- Node 报告校验：JSON Schema、证据引用安全、HTML 产物、语义检查、布局检查。
- `ruff`、`tsc`、markdownlint、skill lint、IDP biz 文档 lint 和复杂度 gate 作为维护门禁。

重要维护约束：技能文档不得引用兄弟技能内部脚本路径；跨技能调度由 L1 决定；Python 不能写 AI 读者正文；报告必须能从 evidence 回指事实。

## 11. 一次典型请求的完整时序

以“用户给一个 traceId，反馈系统异常”为例：

1. AI 主会话读取 `AGENTS.md`，命中 traceId 硬规则，只加载 `fx-ops`。
2. 解析 trace/reqId、时间和租户，建立 `HND-*` 与 `evidence_dir`。
3. `fx_ops_cli.py run fast_rca` 执行 low scout，CEP/error 首波并行，慢表和域探针按信号门控。
4. 写入 `TRC-*`、`CTX-*`、`DIA-verdict-bundle.json`，再执行 `incident_refresh` 生成 `DIA-incident-facts.json`。
5. AI 读取 compact facts 和证据索引，判断 `stay_low` 或升级 medium/high。
6. 如果需要，派 `fx-ops-tracing`、`fx-ops-query`、`fx-ops-monitoring`、业务域技能、`fx-ops-knowledge` 或 `code-search` 并行/串行取证。
7. 子技能只回抛结构化结果，主控合并到当前 evidence 目录并刷新 facts。
8. AI 写 decision，校验器确认 claim、证据引用、snapshot 和收敛状态。
9. 生成短 RCA 或七章报告；用户明确要求 HTML 时才生成自包含 HTML。
10. 若用户还问影响企业或复盘，转 `fx-ops-postmortem`，以 `log_cep_dist status>=500` 重新做影响 gate。

## 12. 当前实现的优点和边界

### 已实现的核心能力

- 三入口意图分流，避免单一“万能诊断器”。
- 业务域、通用取证、工具和编排职责隔离。
- trace/reqId、CEP、慢请求、错误、资源、MQ、数据库、对象、配置、告警、发布、代码和复盘均有对应技能或 capability。
- 确定性采集与 AI 调度分离，支持并行、预算、effort、resume 和信号门控。
- evidence、manifest、facts、decision、state、report 形成可审计链路。
- 通过 schema、snapshot、claim gate、空结果协议和路径安全检查降低幻觉和旧决策复用风险。
- Patrol 的红黄绿由程序判定，Postmortem 的客户影响由网关证据主导，RCA 的根因结论必须回指证据。
- 具备报告、HTML、分享、归档、Hook、编辑器同步和回归测试等配套能力。

### 需要注意的边界

- 它依赖外部 IDP、Prometheus、ClickHouse、对象 API、CMS、Oncall、K8s 和 Sourcebot；脱离这些服务只能运行本地契约/fixture 测试，不能完成真实 RCA。
- 主控不是仓库里的常驻进程，真正的自然语言理解、sub-agent 调度和报告写作由接入的 AI 编辑器完成。
- `package.json` 的 `src/index.ts` 入口在当前快照不存在，不能把该仓库当成已经可直接启动的 Node Web 应用。
- 技能 Markdown 既包含长期架构，也包含大量场景门禁；实际运行必须按 `SKILL.md` 和 reference 导航渐进读取，不能把所有文档一次性塞进上下文。
- 证据为空、采集失败、上下文缺失和根因未收敛都有明确的 partial/blocked 语义；不能为了给出结论而跳过 gate。

## 13. 建议的阅读顺序

想继续维护或扩展时，推荐按以下顺序阅读：

1. `AGENTS.md`：全局触发、分层和红线。
2. `README.md`：能力地图和入口摘要。
3. `docs/knowledge/fx-ops-diagnosis-architecture.md`：稳定架构、严重度和事实/决策合同。
4. 目标 L1 的 `SKILL.md`：`fx-ops`、`fx-ops-patrol` 或 `fx-ops-postmortem`。
5. `fx-ops/scripts/fx_ops_cli.py`：公开 capability 注册表。
6. 对应脚本和 reference：`fast_rca.py`、`playbook_collect.py`、`incident_refresh.py`、`patrol_fetch.py`、`postmortem_fetch.py`。
7. 对应 schema、test 和 regression 脚本：确认修改不会破坏证据、状态和报告合同。

## 14. 最终架构判断

这个项目的本质不是“写了一堆查询脚本”，而是把运维故障诊断拆成了一个可审计的 Agent 操作系统：

- `SKILL.md` 是运行规约和意图路由器。
- Python/Node 是可重复、可测试、可失败闭合的取证执行器。
- `evidence_dir` 是事实总线和审计边界。
- facts/decision/state 是 AI 与程序之间的控制面协议。
- 三个 L1 编排器分别承担 RCA、巡检和复盘，避免职责混淆。
- 领域技能提供业务语义，基础技能提供数据/指标/链路能力，工具技能提供单一转换或上传能力。
- 报告不是采集脚本的副作用，而是 AI 在证据门禁通过后生成的读者产品。

因此，新增能力的正确方式不是再写一个“万能脚本”，而是同时补齐：触发/路由、L1 调度合同、确定性 collector、证据命名与 schema、facts/decision 投影、回归测试和对外文档。
