# idp-grafana 主场景与实测

对标 eye-observability-grafana 的产品能力，在 bug-finder 中经 **IDP 代理 + 本仓查数** 落地。本文给出**可直接复制的命令**与 **foneshare 实测结果**（2026-07-23）。

## 相对 eye 的吸收与改进

| eye | 本仓改进 |
| --- | --- |
| 本机 `token` + `base_url` | `--profile` → IDP；无客户端凭据 |
| `search` / `--action` | `dashboard list` + 强制过滤；叶子动词仅 `get`/`list` |
| 跑**全部**面板 + eye-query | 焦点面板 5–8；优先 **`grafana query` panel one-shot**；失败再按 DS 类型降级 |
| 仅 Grafana HTTP 三类 | 额外吸收 **folder** + **query**；alerting **不做** |
| 串环境风险 | Grafana 仅 firstshare/foneshare；专属云 `not_configured` 为预期，改走主站取定义；metrics 仍跟集群 |

### 查数后端选择（改进点）

优先：`grafana query --dashboard-uid --panel-id --var …`（面板原生 query，含 Prom/CH/ES）。失败或未就绪时：

| datasource.type | 降级查数 |
| --- | --- |
| `prometheus` | `fx-ops idp --profile <metrics_profile> prometheus query`（可与 grafana_profile 不同） |
| `grafana-clickhouse-datasource` / ClickHouse | 委托 **fx-ops-query**（ClickHouse / `biz-app-log` 等），**不**用 prometheus 硬套 |
| `elasticsearch` | 委托 **fx-ops-query**（或既有 ES 诊断路径）；本仓不直连 Grafana ES API 查数 |
| 未知 / 空 | 按症状走 monitoring 观察层 PromQL **模板**，并声明「未用面板原生 query」 |

> 实测：`CEP报错 / KPI 看板` 全部面板为 **ClickHouse**（`foneshare-clickHouse`）；`pod-jvm-monitor` 面板为 **Prometheus**，panel query 在补齐 `--var` 后 `code=0`。

---

## 场景矩阵（实测）

Profile 默认：`foneshare`。命令均加 `-j`。

### S1 搜看板（eye: dashboard search）

```bash
fx-ops idp --profile foneshare grafana dashboard list --query cep --limit 5 -j
```

| 结果 | 值 |
| --- | --- |
| code | `0` |
| items | `5`（示例含 CEP 相关看板） |

### S2 按 UID 取定义（eye: get-by-uid）

```bash
fx-ops idp --profile foneshare grafana dashboard get --uid fe884bd1-166e-4426-b73e-1fd40aef995f -j
```

| 结果 | 值 |
| --- | --- |
| code | `0` |
| title | `CEP报错 / KPI 看板` |
| panels | `15`（均为 grafana-clickhouse-datasource） |

### S3 home 看板（eye: get-home-dashboard）

```bash
fx-ops idp --profile foneshare grafana dashboard get --home -j
```

| 结果 | 值 |
| --- | --- |
| code | `0` |

### S4 列数据源（eye: datasource list）

```bash
fx-ops idp --profile foneshare grafana datasource list -j
```

| 结果 | 值 |
| --- | --- |
| code | `0` |
| items | `349`（ES 176 / CH 48 / PG 37 / Prom 36 / …） |

### S5/S6 按名 / UID 取数据源（eye: get-by-name / get-by-uid；不单独提供 get-id-by-name）

```bash
fx-ops idp --profile foneshare grafana datasource get --name log-cep -j
fx-ops idp --profile foneshare grafana datasource get --uid 0bpW7cnMz -j
```

| 结果 | 值 |
| --- | --- |
| code | `0` |
| name / uid / type | `log-cep` / `0bpW7cnMz` / `elasticsearch` |

### S7/S8 文件夹（eye 无；IDP P0+P1 吸收）

```bash
fx-ops idp --profile foneshare grafana folder list -j
fx-ops idp --profile foneshare grafana folder get --uid PDBKlpgVz -j
```

| 结果 | 值 |
| --- | --- |
| list | code `0`，items `49` |
| get | code `0`，title `alert` |

### S9 无过滤 list（纪律）

```bash
fx-ops idp --profile foneshare grafana dashboard list -j
```

| 结果 | 值 |
| --- | --- |
| CLI | `filter_required: provide at least one of --query, --tag, or --folder-uid`（未发上游） |

### S10 专属云无 Grafana（预期；对齐 oncall「仅 foneshare」）

> **部署事实**：Grafana 只接 `firstshare` / `foneshare`。专属云上的 `grafana_not_configured` **不是漏配**，而是无部署。正确做法：看板定义改走 `foneshare`（或线下 `firstshare`）；指标仍用专属云 profile。

```bash
# 错误示范：专属云调 grafana（会 503）
fx-ops idp --profile mengniu grafana dashboard list --query cep --limit 1 -j

# 正确：看板定义走 foneshare；指标走 mengniu（示意）
fx-ops idp --profile foneshare grafana dashboard get --uid <uid> -j
fx-ops idp --profile mengniu prometheus query --promql 'up' -j
```

| 结果（错误示范：`--profile mengniu`） | 值 |
| --- | --- |
| code | `503` |
| errorCode | `grafana_not_configured` |
| 语义 | **预期**：专属云无 Grafana；应改 `foneshare`/`firstshare` 取定义 |

### S11 Prometheus 查数（可与 grafana_profile 不同）

```bash
fx-ops idp --profile foneshare prometheus query --promql 'count by (k8s_cluster)(up{k8s_cluster="k8s1"})' -j --limit-points 20
```

| 结果 | 值 |
| --- | --- |
| code | `0` |
| series | `1`（示例 value≈1767） |

### S12 按 folder 列看板

```bash
fx-ops idp --profile foneshare grafana dashboard list --folder-uid caa35578-493d-4398-91cf-7726f0ed2994 --limit 8 -j
```

| 结果 | 值 |
| --- | --- |
| code | `0` |
| folder | `开发平台`，返回 8 条 |

### S13 URL/看板分析主路径（编排，非单命令）

示例意图：分析 `https://grafana.foneshare.cn/d/fe884bd1-166e-4426-b73e-1fd40aef995f/...`

1. 解析 UID → `fe884bd1-166e-4426-b73e-1fd40aef995f`，profile=`foneshare`
2. `dashboard get --uid …`（S2，已通）
3. 识别面板 DS = ClickHouse `foneshare-clickHouse`（uid `f0086e53-…`）
4. 优先 `grafana query --dashboard-uid … --panel-id … --var …`；失败再委托 query skill，**不要**用 prometheus 硬查该板
5. 若用户要资源体征，另开 **metrics_profile** 的 prometheus 模板（与看板定义 profile 解耦；专属云指标仍走专属云）

资源侧同 profile 实测（IDP 自身 Pod）：

```bash
fx-ops idp --profile foneshare prometheus query --promql \
  'count by (k8s_cluster,namespace,app,pod)(container_cpu_usage_seconds_total{pod=~"fs-developer-platform-.*",container!="",container!="sandbox"})' \
  -j --limit-points 40
```

| 结果 | 值 |
| --- | --- |
| code | `0` |
| series | `3`（`k8s_cluster=tke70-k8s1`，`namespace=devops`） |

### S14 面板 one-shot（变量门禁 + 成功路径；2026-07-25）

```bash
# 未补变量 → 门禁
fx-ops idp --profile foneshare grafana query \
  --dashboard-uid pod-jvm-monitor --panel-id 39 --from now-15m --to now -j

# 补齐后 → 成功（datasource 必须用 UID）
fx-ops idp --profile foneshare grafana query \
  --dashboard-uid pod-jvm-monitor --panel-id 39 \
  --from now-15m --to now \
  --var datasource=000000032 \
  --var k8s_cluster=k8s0 \
  --var namespace=foneshare \
  --var app=fs-oncall \
  --var pod=fs-oncall-6f9f8c7ccd-2jgxq \
  --var interval=1m \
  --var job='.+-jvm-exporter' \
  -j
```

| 步骤 | 结果 |
| --- | --- |
| 无 `--var` | code `400`，`errorCode=grafana_template_vars_unresolved`，`unresolvedTemplateVars` 列出缺口 |
| 补齐后 | code `0`，`data.results.*.status=200`（帧可为空，仍算查询成功） |
| 错误 `panelId` | code `404`，`errorCode=grafana_panel_not_found` |

### S15 错误 panelId

```bash
fx-ops idp --profile foneshare grafana query \
  --dashboard-uid fe884bd1-166e-4426-b73e-1fd40aef995f --panel-id 28 \
  --from now-1h --to now -j
```

| 结果 | 值 |
| --- | --- |
| code | `404` |
| errorCode | `grafana_panel_not_found` |
| 说明 | 该板无 id=28；有效 id 见 `dashboard get` → `panels[].id`（如 5/6/7…） |

---

## 不做的场景（eye 有 / 本仓拒绝）

```text
Alerting provisioning（contact-points / alert-rules / …）→ 明确拒绝 MVP
get-id-by-name 独立动作 → 用 datasource get --name，响应含 id 即可
客户端 --token / --base-url
```

---

## Agent 速查命令树

```text
fx-ops idp --profile <firstshare|foneshare> grafana
├── dashboard get  (--uid <uid> | --home)
├── dashboard list (--query|--tag|--folder-uid) [--limit] [--page]
├── datasource get (--uid <uid> | --name <name>)
├── datasource list
├── folder get --uid <uid>
├── folder list
└── query (--dashboard-uid + --panel-id [--var…] | --queries|--queries-file) [--from] [--to]
```

取定义 / `grafana query`：仅 `firstshare` / `foneshare`。  
降级查数：`prometheus query`（可专属云）或委托 query skill。
