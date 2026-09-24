# 与 eye-observability-grafana 对照（吸收 / 不吸收）

对标 `ai/fs-ai-hub` 的 `skills/eye-observability-grafana`：**吸收** URL→看板只读→焦点查数编排；**不吸收**客户端直连凭据与 eye 查数栈。查数只走本仓 `idp prometheus`（必要时 query / pyroscope）。

> 本仓额外约束：Grafana 代理仅 `firstshare`/`foneshare`（对齐 oncall）；专属云无 Grafana。

## 对照表

| eye 能力 / 行为 | 本仓结论 | 说明 |
| --- | --- | --- |
| 客户端持有 token + `base_url` / 本机直连 Grafana | **不吸收** | 地址与凭据仅在各部署 IDP；禁止文档教用户配置 `grafana_token` / `grafana_base_url`；禁止 `--token`、`--base-url`、`--grafana-url` |
| URL 解析（uid / from-to / viewPanel / var-*） | **吸收** | 见 [url-parse.md](url-parse.md) |
| 全量执行看板所有面板 query | **吸收流程、收紧范围** | 定义可全量落盘；对话与查数只跑焦点面板，首轮 **5–8** 个；禁止无差别全板执行 |
| eye-query（经 eye 栈查指标） | **不引入** | 使用本地 / 本仓 `fx-ops idp … prometheus query`；metrics profile 跟集群（可与 grafana 不同） |
| `dashboard get` / `search` / home | **吸收为** `get` / `list` / `--home` | 无独立 `search` 动词；列表用 `dashboard list` + 强制过滤；home 用 `dashboard get --home` |
| 面板 inspect / ds query | **吸收为** `grafana query`（panel one-shot 或 `--queries`） | 变量门禁 `grafana_template_vars_unresolved`；无客户端 token |
| datasource 只读 | **吸收** | `datasource list` / `datasource get`（`--uid` \| `--name`） |
| folder 只读 | **吸收** | `folder list` / `folder get --uid`（导航辅助，不单独当 RCA） |
| alerting provisioning / 告警规则读写 | **MVP 不包含** | 用户要 alerting 时明确拒绝进本期范围；二期另议 |
| eye 式 `--action` 多动作打包 | **不吸收** | CLI 仅 `get`/`list` 叶子；编排在 skill，不在单条 CLI action |
| 多云：hostname 或默认环境直打 | **收紧** | Grafana：仅 firstshare/foneshare；专属云不回落「配 Grafana」；metrics 跟集群，禁止静默串 metrics 云 |

## 产品行为对齐摘要

| 阶段 | eye | fx-ops-monitoring |
| --- | --- | --- |
| 选环境 | 常依赖本机配置的 Grafana 端点 | Grafana → firstshare/foneshare；Prometheus → 目标集群 profile（可拆分） |
| 取定义 | HTTP API + token | `idp grafana dashboard get`（仅 firstshare/foneshare） |
| 查数 | eye-query / 面板内表达式执行面偏宽 | 焦点面板 → **按 DS 类型**分流：prometheus→`idp prometheus`；ClickHouse/ES→query skill；否则模板降级 |
| 失败 | 依赖客户端配置完整性 | 专属云无 Grafana 为预期；其余显式降级，见 [errors-and-degrade.md](errors-and-degrade.md) |
| 实测入口 | 无统一场景表 | [scenarios.md](scenarios.md)（foneshare 实跑） |

## 刻意不吸收的一句话清单

- 不吸收客户端 `grafana_token` / `grafana_base_url` 工作流。
- 不引入 **eye-query**。
- 不把 alerting 纳入 MVP。
- 不在 skill 内维护「云名 → Grafana 公网地址 + token」表。
- 不新增 Python Grafana 采集脚本或兄弟 `fx-ops-grafana` skill。
