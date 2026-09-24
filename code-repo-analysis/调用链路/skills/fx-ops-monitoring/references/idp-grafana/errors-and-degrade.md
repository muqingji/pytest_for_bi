# Grafana 错误语义与降级

IDP Grafana 代理未就绪、本 profile 无 Grafana、或上游失败时，**显式处理**：能改走 `firstshare`/`foneshare` 取定义则改走；否则保留 URL 变量与时间窗，用现有 `idp-prometheus` 模板查数。禁止引导用户配置客户端 token。

> **部署事实**：Grafana 只接在 `firstshare` / `foneshare`。专属云（mengniu 等）上的 `grafana_not_configured` 是**预期**，对齐 oncall「仅 foneshare」——不是「漏配、要给专属云补 Grafana」。详见 [index.md §环境约束](index.md)。

## 错误表

| 场景 / 信号 | 处理 | 禁止 |
| --- | --- | --- |
| CLI 无 `grafana` 子命令（`fx-ops idp grafana -h` 失败 / 未知命令） | 判定平台或本机 binary 未就绪 → 走「无定义」降级步骤 | 臆造子命令、Python 直连 Grafana |
| **专属云**上 `grafana_not_configured`（mengniu/hsyk/sbt/…） | **预期无部署**。声明限制后，将 `idp grafana` 改走 `foneshare`（线上）或 `firstshare`（线下）；`metrics_profile` 仍用目标云 | 要求「给 mengniu 配 Grafana」；把 metrics 也静默切到 foneshare |
| **firstshare/foneshare** 上 `grafana_not_configured` | 该套本应有 Grafana：说明平台侧接入缺失；本会话降级查数；推动平台修 **该** profile | 静默改另一套云「碰运气」当常态；不引导客户端 token |
| `grafana_upstream_auth`（HTTP 502；上游鉴权失败） | 说明该 profile **已声明 Grafana**，但平台侧 token/SA 无效；降级查数；推动**平台修 token** | 引导用户填客户端 token；用专属云 profile 调 grafana |
| 401 / 403 / 缺少 `grafana.read`（或等价只读权限） | 指向平台/IDP 侧 Grafana 只读权限与部署配置 | **不**让用户在本机填 token；不建议 `--token` |
| 404 / `grafana_not_found` | 核对 UID 与 `grafana_profile`（须为 firstshare/foneshare）；可选：带过滤的 `dashboard list`。panel 路径下也可能因错误 datasource UID 表现为 not_found | 无过滤的 list；对专属云盲扫 grafana |
| 400 / `grafana_template_vars_unresolved` | 读 `meta.unresolvedTemplateVars`；用 URL `var-*` + `dashboard get`→`templating` 默认值补 `--var` 后重试 | 忽略门禁硬猜 PromQL；把未展开变量当「无数据」 |
| 404 / `grafana_panel_not_found` | 核对 `panelId`（`viewPanel` 或定义里的 `panels[].id`）；嵌套 row 内面板仍以数字 id 为准 | 臆造 panelId；把整板当 panel |
| 502 / `grafana_upstream_error`（或同类上游失败） | 已过变量门禁仍失败：核对 DS UID/类型、时间窗；可降级 `prometheus query` 或委托 fx-ops-query | 盲目改 `--profile` 到专属云 |
| 上游超时 / 不可达 / EOF（无稳定 errorCode） | 有限重试或立即降级；findings 写明上游失败 | 把超时当「无指标」；乱换 metrics profile |
| `dashboard list` 无 `--query` / `--tag` / `--folder-uid` | **禁止发请求**（CLI 亦会报 `filter_required`）；要求补过滤条件 | 宽泛全量列表 |
| `grafana query` 缺 panel/queries 参数 | 按 `query -h` 补齐：panel 路径或 `--queries`/`--queries-file` 二选一 | 臆造 inspect API / 客户端直连 `/api/ds/query` |

实测备注：`mengniu` / `sbt` / `iflytek` 等专属云返回 `grafana_not_configured`（无部署）；`foneshare`/`firstshare` 为 Grafana 可用面。无过滤 `dashboard list` 由 CLI 本地拒绝。

话术方向：

- ✅ 专属云：「当前环境无 Grafana 部署（仅 firstshare/foneshare 有），看板定义改走 `foneshare`；指标仍用 `--profile mengniu`（示例）。」
- ✅ firstshare/foneshare 真缺配：「本套 IDP 的 Grafana 接入异常，请平台侧修复；本会话按模板查 prometheus。」
- ❌「请设置 `grafana_token` / `grafana_base_url`」或「用 `--base-url` 指定地址」
- ❌「请在平台侧为 mengniu 补齐 Grafana 接入」（除非产品明确立项）

## 降级步骤（无看板定义时）

1. **保留上下文**：已解析的 `uid`、全部 `var-*`、`from`/`to`、`viewPanel`、`grafana_profile`、`metrics_profile`。
2. **专属云误用 grafana profile**：先纠正为 `foneshare`/`firstshare` 再试一次 `dashboard get`；仍失败再跳过定义。
3. **不加载看板定义**：跳过或放弃 `grafana dashboard get`；不伪造 panel JSON。
4. **按观察层选模板**：根据症状与变量读 [../idp-prometheus/index.md](../idp-prometheus/index.md)，用 [../idp-prometheus/promql-rules.md](../idp-prometheus/promql-rules.md) 填 URL 变量。
5. **按 metrics_profile 查数**：`fx-ops idp --profile <metrics_profile> prometheus query --promql '<expr>' -j`；未确认则先确认/探测，禁止静默串 **metrics** 环境。
6. **findings 强制声明**：写明是否加载看板定义、`grafana_profile` / `metrics_profile`、专属云无 Grafana 限制（若适用）、RED+USE 结论；无定义时 `confidence` 通常下调。
7. **证据**：落盘 `MON-grafana-url-parsed`；Prometheus 用 `MON-prometheus-metrics`；不要假装写入完整 `MON-grafana-dashboard`。

## 降级后的回抛要点

| 字段 | 要求 |
| --- | --- |
| `status` | 反映部分成功（指标或有）与定义缺失 |
| `findings` | 含「未加载看板定义」或「专属云无 Grafana、已改走 foneshare 取定义」+ 原因摘要 |
| `evidence_files` | URL 解析 + prometheus；无看板定义文件则不编造 |
| `confidence` | 无定义时下调；可注明待 firstshare/foneshare 侧恢复后补 `dashboard get` |
