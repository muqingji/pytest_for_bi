# bug-finder 整体架构、能力与实现梳理

> 分析对象：`/Users/liushanshan/code/bug-finder`
>
> 分析时间：2026-09-17
>
> 代码快照：`7e1b8157`（`docs(fx-ops-monitoring): add foneshare public CLB metric catalog`），`main` 分支
>
> 上一版快照：`e6251222`（2026-08-21），对应本文档旧版
>
> 配套图解：`BUG-FINDER-ARCHITECTURE-DIAGRAMS.html`（同一目录，含读图指南 + 6 张图 + 术语表，打开方式见第 17 节）
>
> 配套技术栈分析：`BUG-FINDER-TECH-STACK.md`（运行时/依赖/契约/门禁/Hook/CI 的完整拆解）与 `BUG-FINDER-TECH-STACK-DIAGRAMS.html`（技术栈图解，9 张图，打开方式见第 17.5 节）

## 1. 结论先行

`bug-finder` 不是一个 Web 服务，也不是一个单体 Python 工具。它是一个由 AI Agent 驱动的故障诊断工作台，由三层构成：

1. `AGENTS.md` 与各 `SKILL.md`：定义意图分流、角色边界、取证流程、证据合同和报告门禁。
2. `.agents/skills/*/{scripts,references}/`：确定性执行层，调用 IDP、数据库、Prometheus、对象 API、CMS、Oncall、K8s、Sourcebot 等外部能力，产出 JSON 事实和证据文件；`references/` 承载按需加载的领域知识与 playbook。
3. AI 主会话与 sub-agent：理解问题、选择 L1 编排器、决定升级、并行派发技能、解释事实、收敛结论并撰写读者报告。

整体形态：

```text
用户问题
   |
   v
AI 主会话读取 AGENTS.md，按意图选择一个 L1 入口
   |
   +-- fx-ops              单点故障机制级 RCA（唯一跨域调度器）
   +-- fx-ops-patrol       主动广度巡检 + 红灯 L1 初步分析
   +-- fx-ops-postmortem   影响评估（默认）/ 完整复盘（显式）
   |
   v
L2 域子 skill / 基础能力 skill / 专项分析 skill / 工具 skill（subagent 派发）
   |
   v
Python / Node 确定性采集器 -> IDP、ClickHouse、Prometheus、对象 API、CMS、Oncall、K8s、Sourcebot
   |
   v
evidence_dir：原始证据、manifest、facts、decision、state、报告决策
   |
   v
AI 按报告合同生成 Markdown / 按需 HTML
```

最核心的设计约束是**三层分工铁律**（`AGENTS.md` 明确定义）：

| 层级 | 负责方 | 职责 | 禁止 |
| --- | --- | --- | --- |
| 采集层 | Python CLI 脚本 | 查询日志/指标/链路/数据库/API，落盘结构化证据 | 不做调度决策、不选 playbook、不编排流程 |
| 调度层 | AI Agent（当前 L1 编排器） | 意图路由、playbook 选择、skill 派发、取证策略、升级决策 | 不用 Python 脚本做 if/else 流程编排 |
| 报告层 | AI Agent（当前 L1 编排器） | 按 contract/guide 撰写 Markdown/HTML 读者报告 | 禁止用模板、字符串拼接或渲染器生成报告正文 |

对应的数据链路是：

```text
Python collector/interpreter  ->  DIA-incident-facts.json
AI scheduling decision        ->  CTX-ai-decision.json（Node 编排账本记录）
AI reader decision            ->  RPT-report-decision.json（schema report-decision-v2）
AI report                     ->  Markdown / 按需 HTML
```

即：Python 写事实，AI 做决定，Node 只记录与校验决定，报告正文只能消费 `RPT-report-decision.json`。

## 2. 与上一版（2026-08-21）的主要差异

这一版梳理时最重要的事实是：距上一版约 4 周内仓库有 442 次提交（其中 70 次 `feat`），主要变化集中在技能扩容、BFE 收敛、知识沉淀层和门禁自动化四条线。

| 变化 | 上一版 | 当前 |
| --- | --- | --- |
| 技能目录数 | 33 | 37 |
| `fx_ops_cli.py` 公开 capability | 26 | 31 |
| `fx-ops` 单技能规模 | — | 254 个 Python 文件、44 个 JS/MJS、161 个 Markdown、98 个 references 条目 |
| 测试 | 约 192 个测试文件 | 133 个 `test_*.py` + 54 个 JS/TS 测试 |
| Markdown 文档 | 约 1115（skills 内） | 1245（skills 内）/ 1500（全仓） |

具体变化：

- **技能新增**：`fx-ops-ai-agent`（ShareAgent / AI Gateway 会话诊断）、`fx-ops-resource-recommend`（K8s requests/limits 与容量建议）、`fx-ops-scenario`（企业使用场景与数据量趋势）、`tapd-bug-distill`（TAPD 历史缺陷蒸馏回写）、`workcircle-knowledge-triage`（协同/PaaS 产品知识咨询）。
- **技能改名**：`fx-ops-rocketmq` → `fx-ops-mq`（从 RocketMQ 专用泛化为 MQ 域，纳入 `fs-kafka-support` / `fs-mq-dispatcher`）。
- **技能收敛**：独立的大前端专项技能（`fx-ops-bfe-perf`、`fx-ops-bfe-client-logs`、`fx-ops-bfe-error-autofix`、后端日报技能等）先被收敛为 `fx-ops-bfe` 路由的嵌套子目录，最终合并为单入口 router：`fx-ops-bfe/SKILL.md` + `routes/{client-logs,error-autofix,perf,functional}`，通过 `route_hint` 选择入口。
- **reviewer skill 移除**：`fx-ops-patrol` / `fx-ops-postmortem` 明确声明“reviewer skill 已移除”，二级评审改为用户显式要求时的人工动作，`review_recommended` 不再自动启审计。
- **patrol 能力扩展**：新增「节点资源饱和度/容量评估」专项（独立 playbook + `collect_node_capacity.py`，不走 `patrol_fetch`/`judge` 管线）；`pod_anomaly` 事件类型扩展到 `cpu_sustained_high`、`hpa_scale`、`single_pod_risk`；注册表引入 `schedule_group` 调度分组。
- **postmortem 能力扩展**：collector 增至 15 个（含 `k8s`、`database`、`mq`、`slo`），新增 `context_only` group 与按资源标签的并发配额。
- **知识沉淀层成型**：`docs/knowledge/scenarios/`（17 大领域、1026 个实战缺陷场景）、`team-domain-responsibilities.md`（28 个研发团队职责全景）、`cross-domain-diagnostic-patterns.md`（跨域交叉诊断模式）。
- **门禁自动化增强**：新增 `.agents/hooks/`（hook 引擎 + 20 个 checker）、`.agents/contracts/`（`datasources.yaml` / `evidence.yaml` / `cloud-registry.md`）、`scripts/agents-verify.mjs`（单一验证入口）、`docs/guidelines/skill-lint` 的 13 条规则、`assert-agents-md-slo-sync.mjs`（AGENTS.md 只允许指针、禁止裸 SLO 数字）等。
- **旧版遗留问题已消失**：`package.json` 不再引用 `src/index.ts`，`dev`/`build`/`start` 脚本已删除，仓库定位更干净——“根目录不是 Node 应用，运行面在 skills”。

## 3. 仓库实际组成

### 3.1 根目录职责

| 路径 | 作用 |
| --- | --- |
| `AGENTS.md` | 总入口规则、三条用户意图路径、首跳硬规则、effort 分档契约、使用纪律与红线（约 16 KB） |
| `README.md` | 产品能力总览、技能分层、环境准备与多编辑器支持 |
| `QUICKSTART.md` | 5 分钟环境配置（Node/pnpm、Token、bootstrap、编辑器技能同步） |
| `.agents/skills/` | 37 个技能目录：`SKILL.md` + `scripts/` + `references/` + `assets/` + `evals/` |
| `.agents/hooks/` | Hook 引擎与 checker（证据命名、预算、编排门禁、查询安全、报告结构、AI-Eye 事件） |
| `.agents/contracts/` | 共享合同：`datasources.yaml`（日志表定义）、`evidence.yaml`（证据命名）、`cloud-registry.md` |
| `scripts/` | 初始化、技能同步、Token 配置、skill lint、trigger/path eval、CI 辅助、验证入口 |
| `tests/` | 根目录 Vitest/Node 测试（14 个 `.test.ts` + fixtures） |
| `docs/` | 架构、开发流程、Git/Issue、知识库、PaaS 产品知识、集成、ADR |
| `fixtures/` | 可重复评估所需的固定快照（如 `idp-datasources.snapshot.json`） |
| `archived/` | 历史 spec/plan/review/sdd 与旧文档归档 |
| `.superpowers/` | 进行中的 spec/plan/review（由 `archive` skill 归档） |
| `output/`、`tmp/` | 运行产物与临时文件（gitignore，不提交） |
| `package.json` | pnpm 任务入口：测试、lint、报告校验、eval、验证；**无 dev/build/start** |
| `pyproject.toml` | Python 3.12+、`jsonschema`、`PyYAML`、`sqlparse`、pytest/ruff 配置 |

**重要更正**：上一版指出的“`package.json` 仍引用不存在的 `src/index.ts`”问题已修复——当前既无 `src/`，也无 `dev`/`build`/`start` 脚本。仓库的运行时就是 skills 目录中的脚本加 AI 编辑器加载的 Skill 文档。

### 3.2 规模统计（当前快照）

- `.agents/skills/` 下 **37 个技能目录**。
- 全仓 Python 文件 329 个、JS 6 个、MJS 116 个、TS 67 个、Markdown 1500 个、YAML 51 个、JSON 377 个（排除 `.venv` / `node_modules`）。
- 测试：`test_*.py` 133 个 + JS/TS 测试 54 个；另有 vitest 根测试、patrol/sfa 技能内测试目录。
- `fx-ops` 单技能占用最大：254 个 Python（含约 120 个自测）、98 个 references 条目、35 个 playbook。
- `fx-ops-query` 有 196 个 Markdown（大量单表查询文档与 biz 索引），`fx-ops-apl` 163 个，`fx-ops-sfa` 139 个，`fx-ops-object` 102 个——印证“知识放 references、协议放 SKILL.md”的分工。
- `fx-ops/scripts/fx_ops_cli.py` 注册 **31 个公开 capability**，未知 ID fail-closed（退出码 2）。

Markdown 体量如此之大是有意的：`SKILL.md` 只保留运行时必须知道的最小协议（`fx-ops/SKILL.md` 仅 127 行，且受 `skill-line-limit`（≤500 行）门禁约束），字段、表结构、SQL、PromQL、报告组件和专项 playbook 全部放 `references/`，按需渐进读取。

## 4. 分层架构

### 4.1 L1：三个平级独立编排器

主会话按用户意图只选一个首跳入口；三者职责互斥，各自在职责域内持有跨 skill 调度权，`fx-ops` 是唯一跨域 RCA 调度器，patrol/postmortem 需要跨域根因编排时以 `need_further` + `route_hint` / `target_capability` 回抛。

| L1 入口 | 负责 | 不负责 | 主要产物 |
| --- | --- | --- | --- |
| `fx-ops` | 报错、traceId/reqId/CEP、NPE/OOM、慢请求、实时故障机制级 RCA | 主动巡检、默认影响评估 | `DIA-verdict-bundle.json`、`DIA-incident-facts.json`、`CTX-ai-decision.json`、`RPT-report-decision.json`、RCA 报告 |
| `fx-ops-patrol` | 晨检、值班交接、健康判断、红黄绿巡检、节点容量专项 | 单请求完整 RCA | `PAT-patrol-data.json`、`JDG-judgement-result.json`、`CTL-patrol-state.json`、巡检摘要 |
| `fx-ops-postmortem` | 网关影响面、受影响企业/接口/时长、标准影响评估、显式完整复盘 | 实时单链路定位；完整复盘缺根因上下文会 blocked | `IMP-impact-assessment.json`、`SUM-postmortem-fetch.json`、`PMR-postmortem-report.json` |

### 4.2 L2：执行层技能（37 个的完整归类）

**域子 skill（15 个）**——业务模块归类 + 本领域取证，**不持有全局编排权**：

- `fx-ops-sfa`：L2O（线索/客户/公海/线索池分配回收查重）与 O2C（报价/合同/订单/回款）、CPQ、价格政策、AI 会议、销售记录、项目管理。
- `fx-ops-fmcg`：外勤陈列/巡店、考勤打卡/排班/定位、里程、人脸识别、订货价目、TPM 核销、积分、促销员、快消小程序、快消 PAAS 预置对象接入。
- `fx-ops-oa`：功能/字段/视图/菜单/按钮权限与角色、企信消息与待办、组织架构同步、协同审批、工作圈。
- `fx-ops-plat`：登录链路、验证码登录方式、账号停用、登录企业错乱、沙盒、更改集、CEP 网关卡顿、SSO/SAML2.0/OIDC。
- `fx-ops-bi`：同步/推送延迟（BI 消费视角）、copier、BI 与源数据一致性、慢查询、拼表、报表/驾驶舱渲染、字段权限缓存、目标管理、订阅推送。
- `fx-ops-workflow`：审批流、BPM 工作流、OneFlow 后动作、阶段推进器、定时触发、任务流、方法论实例、死循环校验。
- `fx-ops-metadata`：对象 describe/定义、唯一性查重、索引与搜索、ES/PG 一致性、license、i18n 资源包、共享规则与数据权限重算。
- `fx-ops-udobj`：自定义对象/字段、布局(Layout)与布局方案/规则、组件树与按钮树、导航视图、字段取值与计算/统计字段、验证规则、自动编号、导入导出、打印模板、异步计算。
- `fx-ops-eservice`：库存、发货退货、信用、订货通、BOM/设备、服务通工单（六大模块）。
- `fx-ops-erp-sync`：ERP Sync Data 1.0、iPaaS 2.0 集成流、高代码连接器、企微/飞书/钉钉外部 OA 渠道与待办推送。
- `fx-ops-er`：企业互联 sync-data（互联上下游企业间），六条固定查询车道。
- `fx-ops-bfe`：大前端统一入口 router，`routes/` 下分 `client_logs` / `error_autofix` / `perf` / `functional`。
- `fx-ops-sms`：验证码与短信发送链路（发送记录 → 应用日志 → 终端/账号自查）、通道回执、频控、黑名单。
- `fx-ops-mq`：RocketMQ/Kafka/事件分发的消费链路归因，消费组映射、日志取证、指标比对、订阅配置解读。
- `fx-ops-ai-agent`：ShareAgent / Flow-Agent / DataAddAgent 会话诊断，CEP 握手与 Agent 失败分类分离，SSE empty stream、工具次数上限、主动中断。

**基础能力 skill（7 个）**——通用取证能力，可被 L1 与域子 skill 单向调用：

- `fx-ops-tracing`：单请求级链路追踪（CEP → app 错误 → 慢 SQL → RPC → APL 耗时），输出 Root Error Span 与累计耗时时序表。
- `fx-ops-monitoring`：Prometheus/PromQL、Grafana 只读、RED+USE 运行时分析。
- `fx-ops-query`：MySQL/PostgreSQL/MongoDB/ClickHouse 直查、统一日志数据源 `biz-app-log`、双方言 biz 处理。
- `fx-ops-object`：CRM 对象 describe、SOQL、字段字典、对象数据查询。
- `fx-ops-knowledge`：服务/模块负责人、团队归属、发布记录、配置变更、历史故障、实战场景库与已知问题。
- `fx-ops-timeline`：多源事件（变更/错误/资源/流量）时间线聚合与因果提示。
- `fx-ops-apl`：APL 函数引擎与知识服务，执行限制、语法与 FQL、工具链、PWC 客开组件。

**专项分析 skill（5 个）**：

- `fx-ops-oncall`：fs-oncall 告警平台的告警记录、处理轨迹、分派策略、升级链路、静默规则、通知历史、AI 根因分析结果。
- `fx-ops-pyroscope`：Grafana-Pyroscope 火焰图，方法级热点、大对象分配路径、锁竞争。
- `fx-ops-scenario`：无故障语境的企业使用场景/测试场景/外部集成摸底与数据量趋势（可直达，不进 `SUB_SKILL_NAMES`）。
- `fx-ops-resource-recommend`：K8s 历史资源规格分析，输出回收/短缺/配置失配/排名建议（不执行变更）。
- `fx-ops-team-alert-rca`：按研发团队批量拉取未关闭告警工单，逐条做异常类与堆栈级根因分析。

**工具 skill（4 个）**——单一提取/转换/执行，不调用其他 skill：

- `code-search`：`sourcebot-cli` 跨仓库代码搜索（class/method/行号/引用）。
- `fetch-config`：CMS profile 搜索、拉取、跨环境比对与脱敏。
- `fx-ops-share`：受控外发分享（plan-first，仅允许仓内 `output/` 等白名单路径）。
- `fx-ops-k8s-app`：`fs-k8s-cli` 接入发布系统；只读可直查（镜像版本/Pod 状态/发布流程/日志），变更操作必须 plan-first + 落回滚点 + 五要素确认。这是体系中**唯一具备写操作能力**的 skill。

**知识与维护 skill（3 个）**：

- `workcircle-knowledge-triage`：无故障语境的协同/PaaS 产品知识咨询（工作圈、企信、通讯录、权限、管理后台、日程；知识库在 `docs/paas/`）。
- `tapd-bug-distill`：从 TAPD 历史缺陷库按业务领域批量提取 Bug/RCA/方案/评论/截图，蒸馏为排查 playbook 与模块规则并增量回写业务 skill（本地断点续跑 + 缓存隔离）。这是**反向沉淀**能力：把线上缺陷经验回流成 skill 知识。
- `archive`：归档过期的 superpowers spec/plan/review 文档到 `archived/`。

### 4.3 调度原则（`AGENTS.md` + 诊断架构文档）

1. 三个 L1 各自在职责域内发起跨 skill 调度，不互相替代。
2. 普通子 skill 可通过名称请求兄弟能力，但下一跳由当前 L1 裁决；**禁止在文档中引用兄弟 skill 的 `scripts/` / `references/` 路径**（由 skill-lint 规则强制）。
3. 域子 skill 做业务归类与取证，基础能力 skill 做执行，工具 skill 做单一转换。
4. 域子 skill 通过 Agent 工具以 subagent 启动，独立上下文，S1/S2 时并行多个。
5. 统一回抛 `status / findings / evidence_files / confidence / route_hint`（`need_further` 只作人类摘要；上下文修正通过 `context_updates` 提议，由主控裁决）。

### 4.4 L3：结论与行动层

- 形成根因判断或候选根因列表，区分“已证实 / 高概率 / 待补证”。
- 触发升级值班、代码修复跟进、`fx-ops idp feedback`、外发报告（`fx-ops-share`）。
- 需要复盘时沉淀统一时间线与改进建议。
- 重点不是多跑一个查询，而是**防止证据不足时过早宣称“已定位”**。

## 5. 用户意图如何分流

首跳规则在根 `AGENTS.md`、三个 L1 的 `SKILL.md` 和 `fx-ops/references/triage-extended.md` 中重复约束，核心顺序：

| 用户输入 | 首跳 |
| --- | --- |
| 用户消息里已有 traceId / reqId / CEP 错误码（含 `1-9f0e07`、`15-84f875`、`s311030117`）、报错截图 | 只加载 `fx-ops` |
| ≥2 条 resolved traceId | `fx-ops` + `batch-trace-split.md`：先 CEP 分类，再 1:1 瘦身 subagent |
| 报错/NPE/OOM/重启/超时/慢/CPU 飙/内存飙/QPS 突增/流量突降/字段缺失 | `fx-ops` |
| “为什么报错”“怎么挂了”“帮我排查/定位/看看” | `fx-ops` |
| 业务域关键词（客户/线索/订单/外勤/自定义对象/审批/AI-Agent…）**+ 任一故障症状** | 仍先 `fx-ops`，由主控派域子 skill |
| “巡检 / 晨检 / 值班交接检查 / 系统健康度 / 有没有风险” | `fx-ops-patrol` |
| “复盘 / 影响了哪些企业 / 影响范围 / 客户影响 / 影响时长 / 索赔 / 是否被攻击” | `fx-ops-postmortem`（默认 `impact_only`） |
| 只查表/SQL/日志/Mongo/ClickHouse | `fx-ops-query` |
| 只看指标/CPU/内存/曲线/PromQL/Grafana URL/看板 | `fx-ops-monitoring` |
| K8s requests/limits 合理性、历史冗余回收、资源不足风险、容量边界、TopN/BottomN | `fx-ops-resource-recommend` |
| 只获取/导出 Android/iOS/H5/Web 客户端日志（无 RCA 诉求） | `fx-ops-bfe`（`route_hint=client_logs`） |
| 只查 CRM 对象字段、SOQL、数据字典 | `fx-ops-object` |
| 只查 CMS profile/配置内容 | `fetch-config` |
| 只查负责人/发布/历史故障/已知 BUG/实战场景/SOP | `fx-ops-knowledge` |
| 只查告警/值班人/通知/静默/升级策略 | `fx-ops-oncall` |
| 无故障语境的企业使用场景/测试场景摸底、数据量趋势 | `fx-ops-scenario` |
| 无报错的协同产品规则咨询（是否支持/入口在哪/怎么配置） | `workcircle-knowledge-triage` |

路由原则：**技术症状优先于业务关键词**；**明确查询不走 RCA**（若同时问“为什么失败/超时”则回到故障路径）；Grafana URL 与 traceId 并存时仍先 `fx-ops`，但 handoff 必须携带 `grafana_url`；域子 skill 激活受 `domain-skill-activation-gate.md` 约束。

## 6. `fx-ops` 单点 RCA 是怎么实现的

### 6.1 上下文归一化与 handoff

主控先把自然语言归一为 `env`、`tenant_context`、`time_window`、`channel_type`、`channel_value`、`app_context`，形成 HND 的 `anchor_context` / `request_anchor`；长上下文写 `handoffs/HND-*`，prompt 只传 `handoff_ref` 与 `evidence_index_ref`，避免把整份日志复制给每个 sub-agent。`CTX-diagnostic-context.json` 只是采集锚点证据（记录 trace/reqId、环境、租户、时间、`playbook_id`、`playbook_phase`），不是 AI 的最终事实结论；子 skill 只能通过 `context_updates` 提议修正 HND。

### 6.2 effort 分档与 scout 双 lane

四个核心 skill（`fx-ops` / `fx-ops-patrol` / `fx-ops-postmortem` / `fx-ops-apl`）统一使用 `--effort auto|low|medium|high`。SLO 数字只在各 skill 的权威文档中维护，`AGENTS.md` 只放指针（由 `scripts/assert-agents-md-slo-sync.mjs` 断言，防止文档漂移）。

`fx-ops` 的档位绑定的是 **turn 预算 + 产物合同**，不是“查多少表”：

| 交付 | 执行态 | SLO | 回答什么 |
| --- | --- | --- | --- |
| Triage（默认 auto） | `low` | 典型 ≤1 min，硬顶 ≤2 min | 这个请求为什么失败？机制类别？下一步？ |
| Investigate | `medium` | 无 2 min 承诺，目标 ≤5 min | 失败在哪一段/哪条 SQL/哪个函数/哪个下游？ |
| Problem | `high` | 不设上限 | 为何发生、影响谁、何时引入、如何防再发？ |

未指定 `--effort` 即 `auto`：从 `low` 起跑 scout（`fast_rca`），按症状选 lane：

- **error/default lane**：未明确慢意图或主诉 NPE/报错——第一波只采 CEP + error，命中后再按需查慢表、函数与领域表。
- **latency lane**：用户明确说慢/超时——CEP、error、CEP 慢体、tomcat、Mongo、SQL 慢表首波并行；只有观察到慢证据才补 DB limit。无 traceId 时先读 `latency-rca`，在 10 分钟窄窗 tomcat 慢请求面抽 1 条代表 trace。

scout 后由 `auto_effort.decide_after_scout` 做**机械判定**（`fast_rca` 内联，也可单独 `auto_effort`）：

| 条件 | action |
| --- | --- |
| 锁定 medium/high，或用户要完整复盘/七章/HTML | `skip_scout` |
| 一个假设 `supported` 且至少一个竞争假设有真实反证，或命中代码定位 | `stay_low` |
| 恰好一个假设 `supported` 且带具名异常类或明确 SQL 指纹 | `stay_low` |
| 多个 supported 竞争、信号模糊、域关键词但无堆栈、多租户/爆发、无决定性信号 | `escalate_medium` |
| 用户要完整复盘（已 scout） | `skip_to_high` |
| 锁定 low 且不能 stay | `stop_locked`（短报告写明需升档） |

禁止 M0 拍档、禁止降档；锁定 low 时不偷偷升档，锁定 medium/high 时跳过 scout。

### 6.3 公开 CLI 与关键入口

`fx-ops` 的两层命令模型（防臆造子命令）：

- **Go 入口**：`fx-ops idp …`（query/prometheus/grafana/object/cms/tenant/route/share）、`fx-ops config`、`fx-ops doctor`。
- **Python 取证**：在 fx-ops skill 目录统一执行 `uv run --no-sync python scripts/fx_ops_cli.py run <capability> -- …`，查看帮助用 `… help <capability>`。`fast_rca.py` / `playbook_collect.py` 直连会打印统一入口提示并非零退出；其余 `scripts/*.py` 为库模块。

31 个公开 capability 可分为：

- **单点 RCA 主链路**：`fast_rca`、`playbook_collect`、`incident_refresh`、`update_dispatch_refresh`、`cep_trace_pipeline`、`auto_effort`、`code_location_probe`。
- **入口与锚点**：`trace_entry`、`reqid_lookup`、`parse_traceid`、`extract_error_anchor`、`resolve_tenant_cloud`、`endpoint_to_appname`、`context_lookup`、`inject_incident_context`。
- **门禁与报告**：`conditional_gate_probe`、`pre_report_gate`、`report_digest`、`rca_timing_snapshot`、`complexity_gate`、`rca_efficiency_benchmark`。
- **慢 SQL 深挖**：`collect_explain`、`collect_slow_sql_index`、`analyze_sql_index_coverage`、`collect_slow_sql_code_location`。
- **其它编排器**：`patrol_fetch`、`judge`、`postmortem_fetch`。
- **共享底座**：`datasource_catalog`、`fxops_query`、`cep_impact_aggregate`。

三个 L1 的技能文档都要求：调用后必须断言产物存在（如 `CTL-fetch-manifest.json` / `DIA-incident-facts.json`），**exit=0 但无产物 = 失败**。

### 6.4 Playbook / DAG 执行

`references/evidence-playbooks/trace-anchor-v1.yaml` 定义 Phase、任务、依赖、必选性、输出文件与 parse reference；`playbook_loader.py` 加载校验，`collect_core.py` 用线程池并发执行 `CollectTask`，每个任务记录 `status`（ok/empty/skipped/error/timeout）、`duration_ms`、`row_count`、`phase`、`parse_ref`、产物文件与失败证据 `ERR-collect-*.json`。

`references/playbooks/` 还有 35 个场景 playbook（`error-log-rca`、`latency-rca`、`oom-rca`、`pod-restart-rca`、`pod-resource-rca`、`change-rollback-rca`、`config-error-rca`、`downstream-*`（sql/redis/mongodb/elasticsearch/dubbo-rest/clickhouse）、`data-storm-*`、`db-load-rca`、`disk-io-rca`、`gateway-late-success`、`client-payload-rca`、`rate-limit-degrade-rca`、`traffic-fluctuation-rca`、`column-not-found`、`data-id-trace-sop` 等），每个都要声明 `inputs.required` 与 `outputs.next_skills`。

### 6.5 Facts / decision / 收敛门禁

`incident_refresh.py` 固定执行 `inject_context -> incident_facts`，把证据投影为根目录 `DIA-incident-facts.json`（带 `schema_version`、`evidence_snapshot`、`observations`、`evidence_gaps`、`quality`，不含 AI 自由推断）。`decision_loader.py` 在使用 AI decision 前校验 facts/decision/state 是否齐全、schema 是否通过、三方 evidence snapshot / decision id / active hypothesis / revision 是否一致；不一致或过期时返回 `awaiting_ai_decision` / `projection_error`，绝不把旧决策当当前决策。

门禁体系通过 `master-gate-index.md` 做「阶段 → 合同」映射，`QG-*` 细则只在 high 档加载 `report-quality-gate.md`：

```text
facts -> AI decision -> converge -> RPT-report-decision.json
      -> validate-report-decision.mjs / 语义检查 / 证据引用检查 / 布局检查
      -> AI 生成 Markdown（low 走 text-report-guide-fast.md）或按需 HTML
```

报告门禁要求：至少 symptom + root_cause claim、claim ID 唯一、证据引用路径合法、机制证据不能只有状态/URI/计数、`probable` 必须列未闭环项、`final` 不能是 hypothesis。证据不足时必须输出 probable/partial/hypothesis/未取证。

### 6.6 批量 trace 与域技能 / 代码定位

- **≥2 条 resolved traceId**：主控只做 CEP 分类，再一条 trace 一个瘦身 subagent（读 `batch-rca-entry.md`），**禁止**把完整 pipeline 复制执行 N 次。
- **域技能 handoff**：主控把 `handoff_ref`、短执行约束与证据索引交给域技能；域技能只能回抛结构化结果，不能接管全局路由。
- **代码定位**：CEP/`s311…` 错误码**禁止**做全库 code-search；只有证据层判定代码缺陷或需要明确源码位置时，才走 `code-search`（`sourcebot-cli.py` + `SOURCEBOT_API_KEY`），输出源仓库、类、方法、行号、调用关系与修复方向。`code_location_probe` 提供内联 Sourcebot 定位（`类.方法:行号`）。

## 7. `fx-ops-patrol` 巡检是怎么实现的

巡检不经 `fx-ops`，由 `fx-ops-patrol` 自己管理状态机、预算和判定。

### 7.1 23 项 check 注册表

`patrol_registry.py` 维护 check、collector、`schedule_group`、query version、支持 profile、必需规范化字段、是否需要基线和行校验器。当前 23 项：

`pod_anomaly`、`cep_5xx`、`error_log`、`slow_sql`、`tomcat_access_slow`、`rpc_slow`、`tomcat_thread`、`traffic_anomaly`、`redis_health`、`k8s_node`、`rate_limit`、`oncall_alerts`、`capacity`、`mq_lag`、`agg_backlog`、`jvm_gc`、`alert_storm`、`pg_health`、`mysql_health`、`mongo_health`、`rocketmq_broker`、`es_slow`、`sql_write_spike`。

`schedule_group` 取值为 `platform_events` / `realtime` / `frequent` / `standard` / `full_scan`，配合 `patrol-schedule.yaml` 支持定时触发。`pod_anomaly` 的 `event_type` 已扩展到 `OOMKilled`、`CrashLoopBackOff`、`Pending`、`restart`、`cpu_throttle`、`cpu_sustained_high`、`hpa_scale`、`single_pod_risk`。

### 7.2 effort 分档

| 档位 | 覆盖范围 | SLO | 交付 |
| --- | --- | --- | --- |
| `low` | 核心 7 项脉搏（oncall_alerts、alert_storm、pod_anomaly、cep_5xx、error_log、mq_lag、tomcat_thread），只查 NOW | ≤10~15s | 3~5 行极简卡片 |
| `medium` | 14 项核心+运行时（+流量环比、容器容量、聚合积压、JVM GC、Node、Redis、慢 SQL），仅对 NOW 有候选行的 check 查日历基线 | ≤30~45s | 标准 Markdown 报告 |
| `high` | 全部 23 项 + 1d/7d/14d 完整历史基线 + 慢调用/锁等待/配置 Diff | ≤90~120s | 完整报告 + 可选 HTML |
| `auto`（默认） | 有界阶梯：先跑核心 7 项 NOW；有基线候选只做一次定向补证，不扩成 14/23 项 | 健康 ≤10~15s | 同 low/medium |

### 7.3 采集、判定、深挖

`patrol_fetch.py` 按 collector 分组并行采集，写出：

```text
output/patrol/<YYYYMMDD-HHMMSS>-<env>/
├── evidence/       NOW / OLD / NRM / CTX / ERR
├── judgement/      JDG-input.json / JDG-judgement-result.json
├── deep-dive/
├── CTL-fetch-manifest.json
├── SUM-fetch-compact.json
└── CTL-patrol-state.json
```

快扫后必须调用 `judge`（能力 ID）——红黄绿由 `patrol_judge.py` 的确定性阈值和服务等级规则决定，AI 只能解释、合并红灯和调度深挖，**不能改写颜色**。`empty` 只有在采集完整、证据文件存在且确认无观测行时才有效；查询失败、字段不完整或 envelope 非法不能伪装成空。

红灯深挖按 L0/L1/L2 服务等级、应用和信号类型合并；同 app 且窗口重叠的同类型 request 红灯合并为一个深挖组。每个红灯项最多 3 轮查询（最小闭环计 1 轮），同一验证项单数据源试探最多 5 轮，超出即停并记录“查询预算耗尽”。巡检只输出 L1 初步分析，发现 S1/S2 必须标注“建议使用 fx-ops 进行深入诊断”。

### 7.4 节点容量专项与报告边界

- **节点资源饱和度/容量评估**是独立专项：走 `references/node-capacity-assessment.md` + `collect_node_capacity.py`，默认工作时段采样 7 天（可 `--days 30`），产出六章 HTML，**不经** `patrol_fetch`/`judge` 管线。
- 默认只输出 Markdown 摘要 + `PAT-patrol-data.json` / `JDG-judgement-result.json` 路径；**只有用户明确要求 HTML/可视化**才读 `references/html-report-guide.md` 并由 AI 直接生成自包含 HTML。成本默认不展示（≤4 行）。
- 默认不启动人工审计（reviewer skill 已移除），`review_recommended` 只写入 state 与 `PAT-patrol-data.json.meta`。
- ad-hoc ClickHouse 查询必须委托 `fx-ops-query`，Patrol 不猜列名、不在主入口复制表结构。

## 8. `fx-ops-postmortem` 复盘是怎么实现的

复盘默认是“影响评估优先”，不是一上来猜根因。

### 8.1 影响主数据源与安全事件

- 受影响企业、接口/服务范围、错误时段和持续时间必须来自网关 `log_cep_dist` 且 `status >= 500`；后台 `log_error_dist` 只能作为应用异常/根因佐证。
- 描述包含攻击/扫描/渗透时，必须单独输出 `security_assessment`，结论分 `confirmed` / `suspected` / `unconfirmed` 三档；只有 CEP 5xx、错误量或流量下降时必须写“未确认渗透攻击”并列出待补采证据。正文必须区分**事实 / 模式 / 机制**。
- 最低上下文门禁：`env` 非 pending、`time_window` 绝对且 start < end、`app_context` 非空。缺 `root_cause_summary` 不阻塞 `impact_only`，但显式完整复盘必须 blocked 并转故障 RCA。

### 8.2 collector registry 与分档

`postmortem_registry.py` 注册 15 个 collector（`gateway`、`error`、`changes`、`alerts`、`tomcat`、`rpc`、`runtime`、`k8s`、`database`、`mq`、`slo`、`tenant`、`owners`、`impact_gate`、`assemble`），每个带 wave、resource tag、证据文件名与 companion（如 `IMP-impact-aggregation.json`、`DEP-deploy-changes.json`、`CFG-config-changes.json`、`K8S-incident-events.json`）。

| group | collector | 说明 |
| --- | --- | --- |
| `impact_only`（low/auto） | gateway、tenant、owners、impact_gate、assemble | 网关 5xx + 租户级别 + 接口与起止时间 |
| `standard_impact`（medium） | + error、alerts、tomcat、slo | 标准技术通报 |
| `context_only` | owners、changes、alerts、slo、tomcat、rpc、runtime、k8s、assemble | 上下文补充 |
| `full`（high） | 全部 15 个 | 完整复盘所需事实 |

并发按资源标签配额控制（global 4 / clickhouse 2 / prometheus 2 / tenant_knowledge 1 / oncall 1）；条件 collector 必须由 AI 基于证据用 `--checks` 显式选择，`root_cause_layer` / `symptom_tags` 只作 hints，不自动选活。`postmortem_fetch.py` 是唯一标准采集入口，生成 `SUM-postmortem-fetch.json` 与 `CTL-postmortem-manifest.json`。

### 8.3 证据复用与状态

- 只复用 identity、profile、env、窗口、fingerprint、exact companion set 和 SHA-256 digest **全部匹配**的证据，并记录 `evidence_reused`；禁止只按文件名复用。
- 维护 `PMR-postmortem-state.json` 与 `EVT-postmortem-events.jsonl`；缺 `root_cause_summary` 且要求完整复盘时 `blocked`，不生成完整 PMR，也不自行综合新根因。
- 优先消费 `KNO-service-owner.json`，缺口再补负责人；无法匹配写 `owner: "未匹配"`，不得猜测。
- 显式 full 且存在 `SUM-hypothesis-disposition-ledger.json`（或可从 `CTX-ai-decision.json` + EVT 投影）时展示竞争假设演化；缺失则标明未提供账本。

## 9. 知识沉淀层（本版新增的重要变化）

上一版把仓库定义为“诊断系统”；当前版本已经额外长出一层**可复用知识资产**，这是本次梳理最需要补充的部分。

### 9.1 `docs/knowledge/` 结构

| 资产 | 内容 |
| --- | --- |
| `fx-ops-diagnosis-architecture.md` | 长期稳定架构基线：三编排器模型、facts/decision 合同、严重度模型、执行面边界（346 行） |
| `scenarios/`（18 个文件） | 17 大业务/架构领域共 **1026 个实战缺陷场景**，每个按「业务背景 → 触发链路 → 根因 RCA → 解决方案与 SOP → 避坑防呆」五段式编写 |
| `team-domain-responsibilities.md` | **28 个研发团队**职责全景（按 TAPD `custom_field_8` 统计近一年 11,148 条缺陷），含团队 → skill 映射与缺陷排行榜 |
| `cross-domain-diagnostic-patterns.md` | 跨域交叉诊断模式与避坑手册 |
| `evidence-prefix-impact-ledger.md` | evidence 语义前缀迁移的影响面台账（owned / delegated / legacy_allowed / new_unowned 归属规则） |
| `20xx-xx-xx-*.md` | 单案例知识文档（打印模板渲染、导出附件路径、鸿蒙旧版首页、Web 移动端不适配、多币种返利等） |

场景库与团队全景的定位很明确：**主控用它快速生成排查假设**（避免盲目全库扫描），**域子 skill 用对应场景的 SOP 精准取证证伪**。

### 9.2 反向沉淀闭环

`tapd-bug-distill` 把 TAPD 历史缺陷库变成 skill 知识来源：`distill_preparer`（准备/分页）→ `distill_collector`（拉取 Bug、RCA、解决方案、评论与多模态截图，`fsc_downloader` 下载图片）→ `target_recommender`（领域 → 目标 skill 推荐）→ `distill_patcher`（增量回写 skill）；`checkpoint_manager` 支持本地断点续跑与缓存隔离，避免重复消耗 Token 与 API 配额。`references/domain-mapping.md` 保存 17 领域 → skill 的映射。

### 9.3 产品知识咨询

`workcircle-knowledge-triage` + `docs/paas/`（`admin-console`、`contacts-org`、`qixin`、`workcircle`、`misc`、`outlook`）承担**无故障语境**的“是否支持/入口在哪/怎么配置/为什么没有某功能/权限与可见性规则”类咨询，与线上异常排查明确解耦。

## 10. 证据与文件合同

### 10.1 目录与命名

诊断证据放 `output/evidence/<YYYYMMDD-Issue>/`，巡检放 `output/patrol/<时间戳>-<env>/`；每次诊断由主控分配绝对路径 `evidence_dir`。常见前缀：

| 前缀 | 含义 |
| --- | --- |
| `TRC-` | trace、CEP、错误、慢请求、RPC、应用日志证据 |
| `QRY-` | 数据库/聚合查询结果 |
| `CTX-` | 诊断上下文、应用发现、AI decision、编排状态 |
| `DIA-` | 诊断 facts、verdict、质量与深挖事实 |
| `MON-` / `HOS-` | Prometheus、Grafana、主机与运行时指标 |
| `PAT-` / `JDG-` / `CTL-` / `SUM-` | 巡检数据、判定、控制面与压缩摘要 |
| `EVID-` / `IMP-` / `PMR-` | 复盘 collector 证据、影响聚合与复盘报告 |
| `DEP-` / `CFG-` / `K8S-` / `ONC-` / `KNO-` | 发布变更、配置变更、K8s 事件、oncall 记录、负责人知识 |
| `SRC-` | 代码定位（Sourcebot）结果 |
| `ERR-` | 采集或 facts 阶段失败证据 |

命名与字段合同由 `.agents/contracts/evidence.yaml` 统一维护，`.agents/contracts/datasources.yaml` 维护共享日志表定义（`datasource_catalog` 能力与 `lint:catalog` 门禁都消费它）。

### 10.2 写入与快照

`evidence_write.py` 用临时文件 + `os.replace` 原子写 JSON，统一处理 BOM、紧凑 JSON、时间戳、NaN 与敏感/超大字段裁剪。事实与 decision 通过 SHA-256 snapshot 绑定，避免“采集结果已更新但 AI 仍用旧结论”。`evidence_index.py` 为 AI 建立可复用证据索引（路径、说明、覆盖范围、建议消费方）；报告只能引用 `evidence/` 下可解析的 JSON 指针，禁止引用 prompt、日志、临时文件或历史报告。

### 10.3 机器输出纪律

三个编排器统一要求：取证 / facts / manifest / AI 机器 JSON 默认**单行紧凑**（按 `json.loads` 消费），`--pretty` 仅供人工查看且不得进入默认产物或 AI 回抛；Markdown/HTML 正文仍按报告合同生成。`evidence_dir` 必须为绝对路径；optional 任务失败 ≠ blocked，hard-block 仅当 required task `status ∈ {error, timeout}`。

## 11. 外部依赖与真实执行面

### 11.1 `fx-ops` / IDP CLI

诊断脚本不在仓库里存数据库凭据，而是调用外部 `fx-ops`/IDP CLI（`FS_AGENT_TOKEN`）：

- `idp query`：MySQL、PostgreSQL、MongoDB，以及统一 ClickHouse 日志数据源 `biz-app-log`（CEP/错误/慢 SQL/Tomcat/RPC 等表名写在 SQL `FROM`）。
- `idp prometheus query` / `idp grafana`：PromQL 与看板、panel、datasource、folder 只读。
- `idp object describe/query`：CRM 对象元数据与 SOQL。
- `idp cms`：CMS profile 与配置搜索、拉取。
- `idp tenant` / `route` / `share` / `whoami` 等运维旁路；`fx-ops config`、`fx-ops doctor`。

查询纪律：实时 `show columns` 确认列名、明确时间窗与 tenant/profile、LIMIT、只读、双方言 biz 必须显式 `--dialect`、`-t` 是否必填按 routeMode 决定；禁止把空结果误判成“没有问题”。

### 11.2 Sourcebot

`code-search` 用 `SOURCEBOT_API_KEY` 调 skill 内 `scripts/sourcebot-cli.py`，**不配置 Sourcebot MCP**。只在已建立代码级假设或需要明确源码位置时调用；CEP 错误码本身不能触发全仓库搜索（`cep-reqid-code-search-ban.md` 明确禁止）。

### 11.3 Hook 运行时与可观测

`.agents/hooks/` 是这套系统里容易被忽略但很关键的一层：

- `hook-engine.mjs` + `hook-config.json` 定义 hook 运行时；`scripts/bootstrap-hooks.mjs` / `generate-hook-configs.mjs` 生成各编辑器配置。
- 20 个 checker 覆盖证据命名（`evidence-name`）、证据索引（`evidence-index`）、上下文合法性（`ctx-valid`）、预算（`budget`）、查询安全（`query-safety`）、收敛门禁（`converge-gate`）、影响门禁（`impact-gate`）、判定归属（`judge-author`）、阶段守卫（`phase-guard`）、派发信封（`dispatch-handoff`）、报告结构（`report-structure`）、回抛格式（`return-format`）、trace 前置条件（`trace-prereq`）、APL 上下文与报告门禁、会话恢复等。
- AI-Eye（Langfuse）旁路可观测默认关闭；开启会上报 prompt、reasoning、工具参数与输出，数据边界见 `docs/integrations/ai-eye-agent-observability.md`。

### 11.4 初始化与多编辑器

`QUICKSTART.md` / `scripts/bootstrap.js` / `scripts/sync-skills.js`：检查 Node >= 24（`.nvmrc` 基线）与 pnpm、uv；从 `.env.local` 读取 `FS_AGENT_TOKEN`、`SOURCEBOT_API_KEY`；配置 fx-ops profiles 与 shell 环境；把 `.agents/skills` 以 symlink/junction 同步到 Claude Code、Codex CLI、Grok、Kiro、OpenCode、Reasonix 等目录，并为 Cursor/Windsurf/Copilot 生成规则文件；支持 worktree 与 Orca/multica workspace 的 `.env.local` 复制。`pnpm setup:tokens` 用 Playwright 自动化完成 IDP Token 配置。

## 12. 测试、质量与维护门禁

测试重点不是“SQL 结果对不对”，而是**编排不可越权**和**证据不撒谎**。

### 12.1 测试分层

- 根目录 Vitest/Node（`tests/`，14 个 `.test.ts`）：触发规则、bootstrap（fx-ops/workspace）、skill lint、编排决策/门禁/锁、报告标题指南、path eval 评分、CI Node 环境、foneShare CLB 指标目录、BFE 单技能布局。
- `fx-ops` Python（133 个 `test_*.py` 中的主体）：trace 入口、playbook、facts/深挖 facts、decision loader、evidence index/registry/paths/summary、空结果、复杂度、effort、慢 SQL 索引覆盖、上下文、质量冲突、契约、CLI、架构边界。
- Patrol：注册表、query safety、窗口、平台上下文、collector、judge、manifest、baseline、模块化架构、shadow、文档合同。
- Postmortem：collector、影响 gate、状态、时间索引、报告契约与布局、证据复用。
- Node 报告校验：JSON Schema、证据引用安全、HTML 产物、语义检查、布局检查（`validate-report-decision.mjs`、`report-semantic-checks.mjs`、`verify-report-layout.mjs`、`validate-report-guides.mjs`）。

### 12.2 门禁与 lint

- `pnpm lint:skills`（`scripts/skill-lint.ts` + `scripts/skill-lint-rules/`，约 20 条规则）：禁止引用兄弟 skill 内部路径、禁止硬编码运营身份、禁止复制兄弟 runner、控制字符、悬空片段、name/H1 一致性、module hint 目标存在、Python 帮助命令必须 `--no-sync`、默认不公开分享、缺 evals 升级说明等。
- `pnpm lint:py` / `format:py`（ruff）、`pnpm lint:md`（markdownlint）、`pnpm lint:catalog`（日志表列名目录）、`pnpm lint:trigger-eval`、`pnpm lint:path-eval:*`。
- `pnpm agents:verify`（`scripts/agents-verify.mjs`）：单一验证入口，按改动路径映射到对应门禁子集，支持 `--changed`。
- `scripts/assert-agents-md-slo-sync.mjs`：断言 `AGENTS.md` 对 SLO 只放指针、不含裸数字，且四个核心 skill 的权威文档保留预期 SLO token。
- `scripts/assert-report-semantic-checks-sync.mjs`：保证报告语义检查规则在各 skill 间同步。
- `complexity_gate` + `complexity-line-gate.mjs`：复杂度预算门禁（`complexity_budgets.json`）。
- `pnpm test:core-contracts` / `verify:fx-ops:gates` / `test:fx-ops:efficiency`：核心合同、编排门禁、RCA 效率基准。
- GitLab CI（`.gitlab-ci.yml`，单 `check` stage）三个 job：`check-sensitive-files`、`fx-ops-gates`、`core-skill-contracts`。

### 12.3 关键维护约束

技能文档不得引用兄弟技能内部脚本路径；跨技能调度由 L1 决定；Python 不能写 AI 读者正文；报告必须能从 evidence 回指事实；新增能力必须同时补齐触发/路由、L1 调度合同、确定性 collector、证据命名与 schema、facts/decision 投影、回归测试和文档。AGENTS.md 还明确：仓库工作区默认直接操作（不使用 `.worktrees/`），该约定覆盖 `docs/guidelines/git.md` 中“复杂任务默认用 worktree”的通用说明，但 Issue、分支、验证与 MR 门禁仍然有效。

## 13. 一次典型请求的完整时序

以“用户给一个 traceId，反馈系统异常”为例：

1. AI 主会话读 `AGENTS.md`，命中 traceId 硬规则，**只加载 `fx-ops`**。
2. 解析 trace/reqId、时间与租户，建立 `HND-*` 与绝对路径 `evidence_dir`。
3. auto 先跑 `fast_rca` scout（按症状选 error/default 或 latency lane），写 `TRC-*`、`CTX-*`、`DIA-verdict-bundle.json`。
4. `auto_effort` 依据 bundle 机械判定 `stay_low` / `escalate_medium` / `skip_to_high` / `stop_locked`。
5. `stay_low`：只读 bundle 与它明确引用的证据（`TRC-log-error.json`、`TRC-slow-log.json`、`SRC-code-location.json`），直接输出「结论 + 证据 + 处置」三段短报告。
6. `escalate_medium`：复用同一 `evidence_dir`，按 AI 选择的 `--through-phase N` 跑 `playbook_collect`（`trace-anchor-v1`）补齐 Phase0–N 与 manifest，再 `incident_refresh` 生成 `DIA-incident-facts.json`。
7. 按需派 `fx-ops-tracing`、`fx-ops-query`、`fx-ops-monitoring`、域子 skill、`fx-ops-apl`、`code-search`（并行/串行）；子 skill 通过 `handoff_ref` + `evidence_index_ref` 接收上下文，只回抛结构化结果。
8. 主控合并结果并刷新 facts，写 `CTX-ai-decision.json`（Node 账本 `record-decision` 校验 schema、预算与 evidence snapshot）。
9. 过收敛门禁与报告门禁，写 `RPT-report-decision.json`（`report-decision-v2`），跑 `validate-report-decision.mjs` 等校验。
10. AI 生成短 RCA 或完整报告；用户明确要求 HTML 时才生成自包含 HTML。
11. 收尾问一次是否分享，确认才交 `fx-ops-share`。
12. 若用户还问影响企业或复盘，转 `fx-ops-postmortem`，以 `log_cep_dist status>=500` 重新做影响 gate。

## 14. 当前实现的优点和边界

### 已实现的核心能力

- 三入口意图分流 + 五类技能层级（域/基础/专项/工具/知识），职责边界清晰，域子 skill 无全局编排权。
- 覆盖度显著扩充：从 traceId/CEP/慢请求/错误/资源/MQ/数据库/对象/配置/告警/发布/代码/复盘，扩展到 AI Agent 会话、K8s 资源建议、企业场景探查、团队告警批量 RCA、产品知识咨询。
- 确定性采集与 AI 调度分离，支持并行、预算、effort 分档、resume、shadow、信号门控和机械判定。
- 证据链路完整可审计：`evidence_dir` + manifest + facts + decision + state + report decision 一体化，schema/snapshot/claim gate/空结果协议/路径安全共同降低幻觉与旧决策复用风险。
- 门禁自动化程度高：hook 引擎 20 个 checker + skill-lint 13 条规则 + SLO 指针断言 + 复杂度预算 + 报告语义/布局校验 + CI 三 job。
- 知识资产成型：1026 个领域场景 + 28 团队职责 + 跨域诊断模式 + 症状 playbook 库，主控可快速生成假设。
- 具备反向沉淀能力（TAPD 缺陷蒸馏回写 skill）与文档归档治理（`archive` + `archived/`）。
- 三编排器的结论边界明确：patrol 红黄绿由程序判定、postmortem 影响面由网关证据主导、RCA 根因必须回指证据。

### 需要注意的边界

- 强依赖外部 `fx-ops`/IDP、Prometheus、ClickHouse、对象 API、CMS、Oncall、K8s、Sourcebot；脱离这些服务只能跑本地契约/fixture 测试，无法完成真实 RCA。
- 主控不是常驻进程：自然语言理解、subagent 调度和报告写作由接入的 AI 编辑器完成；仓库交付的是规约 + 采集器 + 校验器。
- 技能文档数量已到 1500 个 Markdown，必须靠渐进加载；任何“把全文塞进上下文”的用法都会失效。
- 三层技能的规模差异极大：`fx-ops` 单技能 254 个 Python 文件，是全仓最大的单点复杂度；改动风险集中在 `fx-ops/scripts/`。
- 事实/决策/报告三层合同仍在演进（如 `report-decision-v1 → v2`、evidence 前缀迁移台账），阅读旧案例时需注意合同版本差异。
- `docs/` 中的分层描述与 skills 实际清单存在小幅漂移（例如架构文档写“域子 skill 15 个 / 域(14)”，而工具/专项/知识类技能的分类未覆盖 `fx-ops-k8s-app`、`fx-ops-team-alert-rca`、`tapd-bug-distill`、`workcircle-knowledge-triage`、`archive`）。以 `.agents/skills/` 实际目录和 `AGENTS.md` 触发规则为准。
- 证据为空、采集失败、上下文缺失和根因未收敛都有明确的 partial/blocked 语义；不能为了给出结论而跳过 gate。

## 15. 建议的阅读顺序

想继续维护或扩展时，推荐按以下顺序阅读：

> 想先建立整体印象：直接打开 `BUG-FINDER-ARCHITECTURE-DIAGRAMS.html`，从「① 怎么看这些图」读起，再按下面顺序读本文档。

1. `AGENTS.md`：全局触发、分层、effort 契约、红线。
2. `README.md` + `QUICKSTART.md`：能力地图与上手路径。
3. `docs/knowledge/fx-ops-diagnosis-architecture.md`：稳定架构、严重度、facts/decision 合同。
4. 目标 L1 的 `SKILL.md`：`fx-ops` / `fx-ops-patrol` / `fx-ops-postmortem`。
5. `.agents/skills/fx-ops/scripts/fx_ops_cli.py`：31 个公开 capability 注册表；再按需读 `references/fx-ops-cli-capabilities.md`。
6. 关键脚本：`fast_rca.py`、`playbook_collect.py`、`incident_refresh.py`、`auto_effort.py`、`patrol_fetch.py` / `patrol_judge.py` / `patrol_registry.py`、`postmortem_fetch.py` / `postmortem_registry.py`。
7. 共享底座：`.agents/contracts/{datasources.yaml,evidence.yaml}`、`.agents/hooks/`、`scripts/skill-lint-rules/`。
8. 知识资产：`docs/knowledge/scenarios/index.md`、`team-domain-responsibilities.md`、`cross-domain-diagnostic-patterns.md`。
9. 对应 schema、test 与 regression 脚本：确认修改不会破坏证据、状态和报告合同。
10. 开发流程：`docs/guidelines/agent-workflow.md`、`git.md`、`guardrails.md`、`skill-development.md`。

## 16. 最终架构判断

这个项目的本质不是“写了一堆查询脚本”，而是把运维故障诊断拆成了一个**可审计的 Agent 操作系统**：

- `SKILL.md` 是运行规约与意图路由器（且被字节预算和结构 lint 约束）。
- `references/` 是可渐进加载的领域知识库（playbook、单表文档、阈值、报告组件）。
- Python/Node 是可重复、可测试、可失败闭合的取证执行器。
- `evidence_dir` 是事实总线与审计边界。
- facts / decision / state / report-decision 是 AI 与程序之间的控制面协议。
- 三个 L1 编排器分别承担 RCA、巡检和影响评估，`fx-ops` 是唯一跨域调度器。
- hook 与 lint 把“文档约定”变成可执行的 CI 门禁。
- 报告不是采集脚本的副作用，而是 AI 在证据门禁通过后生成的读者产品。

因此，新增能力的正确方式不是再写一个“万能脚本”，而是同时补齐：触发/路由、L1 调度合同、确定性 collector、证据命名与 schema、facts/decision 投影、回归测试、对外文档——以及（当知识可复用时）把它沉淀进场景库与知识库，让下一次诊断少走弯路。

## 17. 配套图示与打开方式

### 17.1 文件

| 文件 | 内容 |
| --- | --- |
| `BUG-FINDER-ARCHITECTURE-DIAGRAMS.html` | 完整图解页：读图指南（颜色/符号/总纲）+ 6 张图 + 术语表；单文件自包含（无 CDN、无脚本），可离线打开 |
| `BUG-FINDER-ARCHITECTURE.md` | 本文档，与图解页配套的完整文字梳理 |
| `BUG-FINDER-TECH-STACK.md` | 技术栈拆解分析：运行时与工具链、语言与依赖构成、契约与 Schema、测试与质量门禁、Hook 与多编辑器接入、外部系统、CI 与工程卫生、选型评价（含风险与历史残留） |
| `BUG-FINDER-TECH-STACK-DIAGRAMS.html` | 技术栈图解页：读图指南 + 9 张图（全景分层 / 语言与依赖 / 端到端链路 / 测试门禁 / Hook 接入 / 契约 Schema / CI 卫生 / 速查评价）；单文件自包含，可离线打开 |

图解页包含以下 8 个部分，页首有目录可直接跳转：

| 序号 | 内容 | 回答的问题 |
| --- | --- | --- |
| ① | 怎么看这些图 | 颜色代表谁执行、符号含义、三个入口的分工 |
| ② | 图 1 分流决策树 | 我这句话会被送到哪条链路（含触发词与两条特殊分支） |
| ③ | 图 2 故障 RCA 详解 | fx-ops 内部 12 步怎么走，两个岔路口如何分派 |
| ④ | 图 3 巡检详解 | 巡检档位、23 项检查、红黄绿判定与红灯深挖 |
| ⑤ | 图 4 复盘详解 | 影响评估与完整复盘的分岔、安全事件、阻断条件 |
| ⑥ | 图 5 系统架构 | 六层结构 + 每层之间的下行指令与上行结果 |
| ⑦ | 图 6 真实例子时序 | 一条 traceId 的 14 步真实过程（含实际命令） |
| ⑧ | 术语表 | 图中出现的 25 个术语的通俗解释 |

页面上每张卡片都标注了「做什么 / 输入 / 输出 / 谁执行」，因此不需要背景知识也能读懂。页面按 1200px 内容宽度自适应，窄窗口下自动换行，不会挤压变形。

### 17.2 打开方式（macOS）

| 方式 | 操作 |
| --- | --- |
| Finder 双击 | 打开 `bug-finder` 分析目录，双击 `BUG-FINDER-ARCHITECTURE-DIAGRAMS.html`，用系统默认浏览器打开 |
| 终端命令 | `open /Users/liushanshan/code/my/pytest_for_bi/code-repo-analysis/bug-finder/BUG-FINDER-ARCHITECTURE-DIAGRAMS.html` |
| 指定浏览器 | `open -a "Google Chrome" <同一路径>`；Safari 则换成 `open -a "Safari" <同一路径>` |
| 浏览器地址栏 | 直接输入 `file:///Users/liushanshan/code/my/pytest_for_bi/code-repo-analysis/bug-finder/BUG-FINDER-ARCHITECTURE-DIAGRAMS.html` |
| 编辑器 | 在 VS Code / Cursor 中打开该文件后右键「Reveal in Finder」再双击；或安装 HTML 预览类扩展直接预览 |

Windows 下同样支持：双击该文件，或在文件所在目录执行 `start BUG-FINDER-ARCHITECTURE-DIAGRAMS.html`。

### 17.3 阅读与导出

- 建议阅读顺序：先看「① 怎么看这些图」建立颜色与符号的直觉，再按 ②→⑦ 顺序看，遇到不认识的词查 ⑧ 术语表。
- 页面顶部有目录导航，点击即可跳到对应图解。
- 导出 PDF：浏览器执行 `Cmd + P`，方向选横向、缩放选「适应页面」，即可得到分页正常的 PDF。
- 页面为浅色主题，并显式声明 `color-scheme: light`，在深色模式浏览器下不会出现色块反转。
- 图上的关键数字（37 个 skill、31 个 capability、23 项巡检、20 个 hook checker 等）与本文档第 3、6、7、12 章一致。

### 17.4 维护说明

- 页面由 AI 直接手写 HTML/CSS/SVG，没有构建步骤、模板或渲染脚本；改文案只需编辑该 HTML 本身。
- 仓库结构或技能分层变化时，需同时更新该页面与本文档对应章节，避免两处数字漂移。

### 17.5 技术栈文档与图解（同一目录）

技术栈相关的两个文件与本文档、架构图解页放在同一目录：

| 文件 | 是什么 |
| --- | --- |
| `BUG-FINDER-TECH-STACK.md` | 技术栈拆解分析正文，共 11 章：结论先行、运行时与工具链基线、语言构成与代码规模、依赖拆解、契约与 Schema 栈、测试与质量门禁栈、Hook 引擎与编辑器接入栈、外部系统依赖栈、CI/CD 与工程卫生、一次诊断的端到端技术链路、技术选型评价与速查表 |
| `BUG-FINDER-TECH-STACK-DIAGRAMS.html` | 对应的图解页，共 9 张图：① 读图指南 ② 技术栈全景分层（7 层）③ 语言与依赖构成 ④ 一次诊断的技术链路（17 跳）⑤ 测试与质量门禁栈 ⑥ Hook 与多编辑器接入 ⑦ 契约与 Schema 栈 ⑧ CI 与工程卫生 ⑨ 速查表与选型评价 |

打开方式与架构图解页完全相同，把文件名替换即可：

| 方式 | 操作 |
| --- | --- |
| Finder 双击 | 打开 `bug-finder` 分析目录，双击 `BUG-FINDER-TECH-STACK-DIAGRAMS.html`，用系统默认浏览器打开 |
| 终端命令 | `open /Users/liushanshan/code/my/pytest_for_bi/code-repo-analysis/bug-finder/BUG-FINDER-TECH-STACK-DIAGRAMS.html` |
| 指定浏览器 | `open -a "Google Chrome" <同一路径>`；Safari 则换成 `open -a "Safari" <同一路径>` |
| 浏览器地址栏 | 直接输入 `file:///Users/liushanshan/code/my/pytest_for_bi/code-repo-analysis/bug-finder/BUG-FINDER-TECH-STACK-DIAGRAMS.html` |

Windows 下同样支持：双击该文件，或在文件所在目录执行 `start BUG-FINDER-TECH-STACK-DIAGRAMS.html`。

阅读建议：先看文档的「0. 结论先行」拿到六个核心判断，再打开图解页按 ①→⑨ 顺序看；图中的每个数字（4 个运行时依赖、1495 个 Markdown、21 个 Schema、20 个 hook checker、187 个测试文件等）都与文档正文一一对应。
