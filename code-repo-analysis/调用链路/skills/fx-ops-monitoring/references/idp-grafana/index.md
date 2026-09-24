# idp-grafana：看板 URL 编排入口

在 `fx-ops-monitoring` 内吸收 Grafana 看板 URL / 只读看板意图：解析链接 → 选定 **Grafana 可用的 `--profile`** → `idp grafana` 取定义 → 焦点面板 → 再按 DS 类型与**目标集群 profile** 查数。密钥与 Grafana 地址只在 IDP；本目录不写 token 配置教程。

## 环境约束（必读，对齐 oncall）

> **Grafana 只部署在 `firstshare`（线下）与 `foneshare`（主站）两套 IDP。**  
> 专属云 / 私有化（如 `mengniu`、`hsyk`、`sbt`、`iflytek` …）**没有** Grafana **IDP 接入**（`idp grafana --profile mengniu` 会 `grafana_not_configured`），与「oncall 只能在 foneshare 查」同类。  
> **但是**：主站 `foneshare` 上大量看板通过模板变量（常见 **`env`**，以及联动的 datasource / cluster）**选择专属云**，经主站 Grafana 数据源查询专属云数据。查专属云业务体征时，优先走 **`idp grafana --profile foneshare` + 展开 `var-env=…`**，而不是去专属云 profile 调 grafana。

| 能力 | 可用 `--profile` | 说明 |
| --- | --- | --- |
| `idp grafana …` | **仅** `firstshare` / `foneshare` | 看板定义、搜看板、datasource/folder 只读、`grafana query` 出数 |
| `idp prometheus …` | 仍按目标 K8S 集群选 profile（可专属云） | 指标实例按云隔离，与 Grafana 部署无关 |

纪律：

1. 调用 `idp grafana` 前，把 profile **归一到** `firstshare` 或 `foneshare`（见下表），**禁止**对 `mengniu` 等专属云发 grafana 请求「碰运气」。
2. 专属云故障：优先用 **foneshare 看板 + `env`/云变量**（若看板支持）经 `grafana query` 出数；或取定义后按 `metrics_profile` 走专属云 `prometheus` / query。二者可并存。
3. 专属云上出现 `grafana_not_configured` 是**预期**（无 Grafana IDP）：改走 `firstshare`/`foneshare` 取定义/出数，**不要**要求平台给专属云补 Grafana（除非产品另开需求）。
4. 解析看板时识别 `env` 等云变量；`grafana query` **必须展开**后再发，避免查错云或上游 502。选项清单见 [env-var-options.md](env-var-options.md)。

| Grafana 主机 / 语境 | `idp grafana` 使用的 profile |
| --- | --- |
| `grafana.foneshare.cn` / 线上主站 | `foneshare` |
| `grafana.firstshare.cn` / 线下 | `firstshare` |
| 用户未给主机、默认线上 | `foneshare` |
| 专属云业务 profile（mengniu 等） | **不用于** `idp grafana`；grafana 改走 `foneshare` 或 `firstshare` |

CLI 契约、错误降级、与 eye 对照、场景实测见下方链接。指标模板仍以 [../idp-prometheus/index.md](../idp-prometheus/index.md) 为准。

## 意图路由

| 用户意图 | 行为 |
| --- | --- |
| Grafana URL / UID 看板分析 | 走下方主路径；证据含 URL 解析 +（若成功）看板定义 + 查数 |
| 搜 / 列看板 | `dashboard list`，**必须** `--query` / `--tag` / `--folder-uid` 之一；profile 限 firstshare/foneshare |
| home 看板 | `dashboard get --home` |
| 数据源只读 | `datasource list` / `datasource get` |
| 文件夹只读 | `folder list` / `folder get`（导航辅助，不单独当 RCA） |
| 焦点面板出数 | `grafana query --dashboard-uid --panel-id --var …`（见 [cli.md](cli.md)） |
| Alerting | **拒绝进 MVP**；说明本期不支持 Grafana alerting provisioning |

仅 PromQL / 资源症状、无看板意图时：不要强制走本包，沿用现有 prometheus 路由即可（prometheus **可以**用专属云 profile）。

## 主路径（6 步）

1. **解析 URL**：`uid`、`from`/`to`、`viewPanel`、全部 `var-*` → 落盘 `MON-grafana-url-parsed`（见 [url-parse.md](url-parse.md)）。
2. **拆分两类 profile**：
   - **grafana_profile**：按上表归一到 `firstshare` / `foneshare`（禁止专属云）
   - **metrics_profile**：按 `var-k8s_cluster` / 租户云 → SKILL § Profile 选择规则（可专属云）；hostname 仅线索
3. **`grafana dashboard get`**：`--profile <grafana_profile>` + `--uid` 或 `--home`；**全量定义落盘**，不整份塞进对话。探测 CLI：`fx-ops idp grafana -h`，失败则 [errors-and-degrade.md](errors-and-degrade.md)。
4. **变量与时间窗**：用 URL 的 `var-*` 与 `from`/`to` 初始化/覆写看板变量；映射到 [../idp-prometheus/promql-rules.md](../idp-prometheus/promql-rules.md) 占位符。
5. **焦点面板**（见下节）：有界选取；记下 `panels[].id` 与 `templating` / URL `var-*`。
6. **查数并总结**（优先同一 `grafana_profile` 的 panel one-shot；直连 prometheus 时可用不同 `metrics_profile`）：
   - **优先**：`grafana query --dashboard-uid <uid> --panel-id <id> --var k=v …`（补齐门禁要求的变量；`datasource` 传 UID）
   - 门禁/`grafana_upstream_error` / 无 panel 路径 → `prometheus` 面板可降级 `idp prometheus query`（`--profile <metrics_profile>`）
   - ClickHouse / ES 面板：先试 `grafana query`；仍失败再委托 **fx-ops-query**（biz 文档定 profile）
   - 无可用原生 query → 降级 monitoring 观察层模板，并声明「未用面板原生 query」
   - findings 写明：grafana_profile、metrics_profile、是否加载看板定义、是否走 panel query、DS 类型、RED+USE/业务结论

主场景命令与实测见 [scenarios.md](scenarios.md)。

## 焦点面板规则

| 优先级 | 规则 |
| --- | --- |
| 1 | 有 `viewPanel` 或用户点名的面板 → **优先**纳入 |
| 2 | 否则按观察层匹配面板标题 / targets：`Pod` → `JVM` → `Tomcat` → `Node` → `中间件` |
| 上限 | 首轮最多 **5–8** 个面板；禁止「执行全部面板」 |
| 落盘 vs 对话 | 定义全量进证据；对话与查数只消费焦点子集 |

## 证据前缀

| 前缀 | 用途 |
| --- | --- |
| `MON-grafana-url-parsed` | uid、时间窗、var-*、viewPanel、`grafana_profile` / `metrics_profile`（可含 URL，不含 token） |
| `MON-grafana-dashboard` | `dashboard get` 响应（定义侧） |
| `MON-grafana-datasource` | 按需 datasource 只读 |
| `MON-grafana-folder` | 按需 folder 只读 |
| `MON-grafana-query` | `grafana query`（panel / raw）响应 |
| `MON-prometheus-metrics` | 焦点面板或模板查数（沿用现有格式） |

目录：被调度用调用方 `evidence_dir`；独立使用用 `output/evidence/<YYYYMMDD-…>-monitoring/`。

## 本包文档

| 文档 | 内容 |
| --- | --- |
| [env-var-options.md](env-var-options.md) | 看板 `env` 专属云选项全集与 profile 对照（skill 可加载；勿用 output/） |
| [cli.md](cli.md) | `idp grafana` 命令树、规则、禁止项、与 prometheus 解耦 |
| [url-parse.md](url-parse.md) | URL 解析、两类 profile、变量映射、解析证据形状 |
| [errors-and-degrade.md](errors-and-degrade.md) | 错误表与「未加载看板定义」降级 |
| [eye-compare.md](eye-compare.md) | 相对 eye 的吸收 / 不吸收对照 |
| [scenarios.md](scenarios.md) | 主场景命令树与 foneshare 实测结果 |

指标发现与各观察层模板：[../idp-prometheus/index.md](../idp-prometheus/index.md)。
