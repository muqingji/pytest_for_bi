# Grafana URL 解析与 profile 推断

将用户粘贴的 Grafana 看板链接解析为编排输入：UID、时间窗、焦点面板、全部 `var-*`，再推断 `--profile`，并把变量映射到本仓 PromQL 占位符。

## 1. URL 解析

典型形态：

```text
https://<grafana-host>/d/<uid>/<slug>?from=<from>&to=<to>&viewPanel=<id>&var-<name>=<value>&…
```

| 提取项 | 来源 | 说明 |
| --- | --- | --- |
| `uid` | 路径 `/d/<uid>/…` | 看板 UID；后续 `grafana dashboard get --uid` |
| `from` / `to` | query `from` / `to` | Grafana 时间窗（epoch ms、相对串如 `now-1h` 等原样保留，查数时再归一） |
| `viewPanel` | query `viewPanel` | 焦点面板 ID；有则优先纳入首轮 |
| `vars` | 全部 `var-*` | 键去掉 `var-` 前缀；值保留原串（含 `|` 多选等） |

解析时保留**完整** `var-*`，尤其关注：`k8s_cluster` / `cluster`、`namespace`、`app` / `app_name`、`pod` / `pod_name`、`host_ip` / `node`、中间件相关 `topic` / `group` / `broker` 等。

无法解析 UID（非 `/d/<uid>/` 形态）时：不要猜 UID；可改走 `dashboard list`（须带过滤）或请用户补充 UID / 合法链接。

## 2. Profile 推断（两类，勿混用）

> **Grafana 仅 `firstshare` / `foneshare` 有部署**（对齐 oncall：专属云无该平台能力）。Prometheus 仍可按集群走专属云 profile。详见 [index.md §环境约束](index.md)。

产出两个字段写入证据：`grafana_profile`、`metrics_profile`（可与旧字段 `inferred_profile` 并存时：`inferred_profile` 表示 metrics；grafana 用 `grafana_profile`）。

### 2.1 `grafana_profile`（仅用于 `idp grafana`）

| 优先级 | 规则 |
| --- | --- |
| 1 | 主机 `grafana.foneshare.cn` → `foneshare` |
| 2 | 主机 `grafana.firstshare.cn` → `firstshare` |
| 3 | 未给主机、默认线上语境 → `foneshare` |
| 禁止 | `mengniu` / `hsyk` / `sbt` / 其它专属云 profile 调 `idp grafana` |

### 2.2 `metrics_profile`（用于 `idp prometheus` / 资源查数）

1. **`var-k8s_cluster`（或上下文 cluster）** → 对照本 skill **SKILL.md § Profile 选择规则**
2. 对话/告警中的专属云线索（主控按 cloud-registry 裁决）
3. 与 grafana hostname **解耦**：专属云租户看主站 Grafana 板时，常见组合是 `grafana_profile=foneshare` + `metrics_profile=mengniu`（等）
4. 不确定 → 探测或确认；**禁止**静默换云

`profile_confidence`（`high` / `medium` / `low`）针对 **metrics_profile**；`low` 时先确认再查 prometheus。grafana 侧只需确认主机落在 firstshare/foneshare。

## 3. 变量 → PromQL 标签映射

与 [../idp-prometheus/promql-rules.md](../idp-prometheus/promql-rules.md) 占位符对齐；标签名不完全一致时，用小范围 instant 查询确认（见 [../idp-prometheus/index.md](../idp-prometheus/index.md)）。

| URL / Grafana 变量 | PromQL 占位符 / 常用标签 | 备注 |
| --- | --- | --- |
| `var-k8s_cluster` / `var-cluster`（K8S） | `${k8s_cluster}` → `k8s_cluster` | 多集群必填；优先于其它过滤 |
| `var-namespace` | `${namespace}` → `namespace` | |
| `var-app` / `var-application` | `${app_name}`；容器侧常为 `app` | JVM 侧多为 `app_name` |
| `var-pod` / `var-pod_name` | `${pod_name}` → `pod` | |
| `var-host_ip` / `var-node` | `${host_ip}`；node-exporter 常看 `instance` | |
| `var-container` | `${container}` | 常等于 app 名 |
| `var-topic` / `var-consumer_group` / `var-broker` | `${topic}` / `${group}` 等 | RocketMQ；见 rocketmq 文档 |
| `var-interval` | 无标签 | 仅影响 `rate()` 等窗口，不当作 selector |

看板内 PromQL 若已写死标签，URL 变量用于**覆写/收窄**时间窗与过滤；变量缺失时按观察层模板补齐，并在 findings 中说明假设。

## 4. 证据形状：`MON-grafana-url-parsed.json`

落盘字段（可含 URL，**永不含 token**）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `uid` | string \| null | 看板 UID |
| `from` | string \| null | 时间窗起点原串 |
| `to` | string \| null | 时间窗终点原串 |
| `viewPanel` | string \| null | 焦点面板 ID |
| `vars` | object | `var-*` 去前缀后的键值表 |
| `grafana_profile` | string | 仅 `firstshare` / `foneshare`；供 `idp grafana` |
| `metrics_profile` | string \| null | 供 `idp prometheus`；可专属云 |
| `inferred_profile` | string \| null | 兼容旧字段：等同 `metrics_profile`（勿当作 grafana profile） |
| `profile_confidence` | string | 针对 `metrics_profile`：`high` / `medium` / `low` |
| `source_url` | string | 用户提供的原始 URL（可脱敏 query 中的敏感业务值，但不得出现凭据） |

示例骨架：

```json
{
  "uid": "abc123",
  "from": "now-6h",
  "to": "now",
  "viewPanel": "12",
  "vars": {
    "k8s_cluster": "tke70-k8s1",
    "namespace": "foneshare",
    "app": "fs-paas-app-udobj"
  },
  "grafana_profile": "foneshare",
  "metrics_profile": "foneshare",
  "inferred_profile": "foneshare",
  "profile_confidence": "high",
  "source_url": "https://grafana.foneshare.cn/d/abc123/slug?from=now-6h&to=now&viewPanel=12&var-k8s_cluster=tke70-k8s1"
}
```

专属云租户示例（看板在主站、指标在专属云）：`grafana_profile=foneshare`，`metrics_profile=mengniu`。

证据目录：被调度时用调用方 `evidence_dir`；独立使用用 `output/evidence/<YYYYMMDD-…>-monitoring/`。前缀约定见 [index.md](index.md)。
