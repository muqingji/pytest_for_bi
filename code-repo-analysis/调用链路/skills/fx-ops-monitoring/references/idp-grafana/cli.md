# idp grafana CLI 契约

消费侧契约：Grafana 的地址与凭据只存在于 **IDP 服务端**（当前仅 **firstshare / foneshare** 两套实例接了 Grafana）；Agent / skill **不持有、不传递、不提示用户配置**客户端 token。`--profile` 选择该套 IDP 上已配置的 Grafana。

> 环境约束：专属云（mengniu 等）**无** Grafana 部署，与 oncall「仅 foneshare」同类。详见 [index.md §环境约束](index.md)。

## 命令树

```text
fx-ops idp --profile <firstshare|foneshare> grafana
├── dashboard get  (--uid <uid> | --home)
├── dashboard list (--query|--tag|--folder-uid) [--limit] [--page]
├── datasource get (--uid <uid> | --name <name>)
├── datasource list
├── folder get --uid <uid>
├── folder list
└── query
    ├── panel 路径：--dashboard-uid + --panel-id [--var k=v…] [--from] [--to]
    └── 原始路径：--queries <json> | --queries-file <path>  [--from] [--to]
```

执行前先探测：`fx-ops idp grafana -h` 与 `fx-ops idp grafana query -h`。若失败（未知子命令、旧 binary、帮助不可用），按 [errors-and-degrade.md](errors-and-degrade.md) 降级；**禁止臆造**未出现在帮助中的子命令或 flag。

## 规则

| 规则 | 说明 |
| --- | --- |
| Grafana profile 白名单 | `idp grafana` 的 `--profile` **仅** `firstshare` / `foneshare`；禁止专属云 |
| 与 prometheus 可拆分 | 看板定义 / `grafana query` 用 `grafana_profile`；直连 prometheus 用 `metrics_profile`（可专属云）。二者**可以不同** |
| list 必过滤 | `dashboard list` 至少提供 `--query` / `--tag` / `--folder-uid` 之一；无过滤则禁止发请求 |
| get 互斥 | `dashboard get`：`--uid` 与 `--home` 二选一；`datasource get`：`--uid` 与 `--name` 二选一 |
| query 二选一 | **panel 路径**（`--dashboard-uid` + `--panel-id`）与 **原始路径**（`--queries` / `--queries-file`）二选一；不要混用 |
| 模板变量门禁 | panel 路径下，看板 `templating` 中仍未解析的 `$var` 会 `grafana_template_vars_unresolved`；用可重复的 `--var key=value` 补齐（URL 的 `var-*` 映射过来） |
| datasource 传 UID | `--var datasource=…` 传 **datasource UID**（如 `000000032`），不要传显示名 `Prometheus` |
| All / 空值 | UI「All」对应 `$__all` 或看板默认；空串是否等价以 CLI 门禁返回的 `unresolvedTemplateVars` 为准 |
| 插件宏可保留 | `$__timeFilter` / `$__from` / `$__to` / `$__interval` 等由上游 ds/query 处理，**不要**当 dashboard 变量去 `--var` |
| 动词边界 | 元数据仅 `get` / `list`；查数用 `query`；**无** eye 式 `--action`；**无** alerting |
| 采集入口 | 只走 Go `fx-ops idp … grafana`；不新增 Python Grafana 脚本，不直连 Grafana HTTP |

## 禁止项

| 禁止 | 原因 |
| --- | --- |
| `--token` | 凭据在 IDP，客户端不得传 token |
| `--base-url` / `--grafana-url` | 请求级指定任意 Grafana 地址会破坏多云隔离 |
| 请求体/参数携带上游 URL 或 token | 与 IDP 代理模型冲突 |
| 对专属云调 `idp grafana` | 无部署；应改 `foneshare`/`firstshare`，勿要求「给 mengniu 配 Grafana」 |
| 引导用户设置客户端 `grafana_token` | 凭据只在 IDP；见 [errors-and-degrade.md](errors-and-degrade.md) |
| 未补齐 `--var` 就反复重试 panel query | 先读 `unresolvedTemplateVars` / `dashboard get` → `templating` |

## 与指标查询解耦

取看板定义后，查数优先顺序：

1. **焦点面板 one-shot**：`grafana query --dashboard-uid … --panel-id … --var …`（同一 `grafana_profile`；专属云选云靠 `env` 等变量，见 [env-var-options.md](env-var-options.md)）
2. **Prom 面板降级 / 无 panel 路径**：`fx-ops idp --profile <metrics_profile> prometheus query --promql '<expr>' -j`
3. **ClickHouse / ES 面板**：优先仍试 `grafana query`（面板原生 SQL/DSL）；失败再委托 **fx-ops-query**

模板与占位符见 [../idp-prometheus/promql-rules.md](../idp-prometheus/promql-rules.md)；观察层路由见 [../idp-prometheus/index.md](../idp-prometheus/index.md)。

## 典型调用示例

```bash
# 按 UID 取看板定义（全量响应落盘，对话内只消费焦点面板）
fx-ops idp --profile foneshare grafana dashboard get --uid <uid> -j

# home 看板
fx-ops idp --profile foneshare grafana dashboard get --home -j

# 带过滤的看板列表
fx-ops idp --profile foneshare grafana dashboard list --query 'jvm' --limit 20 -j

# 数据源 / 文件夹（只读导航）
fx-ops idp --profile foneshare grafana datasource list -j
fx-ops idp --profile foneshare grafana datasource get --uid <ds-uid> -j
fx-ops idp --profile foneshare grafana folder list -j
fx-ops idp --profile foneshare grafana folder get --uid <folder-uid> -j

# 面板 one-shot（模板变量必须补齐；datasource 用 UID）
fx-ops idp --profile foneshare grafana query \
  --dashboard-uid pod-jvm-monitor --panel-id 39 \
  --from now-15m --to now \
  --var datasource=000000032 \
  --var k8s_cluster=k8s0 \
  --var namespace=foneshare \
  --var app=fs-oncall \
  --var pod=fs-oncall-xxx \
  --var interval=1m \
  --var job='.+-jvm-exporter' \
  -j

# 原始 ds/query 载荷（已自行展开变量时）
fx-ops idp --profile foneshare grafana query --queries-file tmp/ds-query.json --from now-1h --to now -j

# 专属云租户：看板 / grafana query 仍走 foneshare（+ env 变量）；直连 prometheus 可走专属云
fx-ops idp --profile foneshare grafana dashboard get --uid <uid> -j
fx-ops idp --profile foneshare grafana query --dashboard-uid <uid> --panel-id <id> --var env=mengniu … -j
fx-ops idp --profile mengniu prometheus query --promql '<expr>' -j
```

`-j` 等输出 flag 以本机 `fx-ops idp grafana … -h` 为准；帮助未列出的 flag 不要使用。
