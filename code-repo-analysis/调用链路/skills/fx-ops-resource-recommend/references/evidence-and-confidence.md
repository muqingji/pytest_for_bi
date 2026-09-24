# 证据、覆盖与置信度合同

## 结构化证据

独立执行时将证据保存到 `output/evidence/<case>/`；由上游调用时使用其分配的 `evidence_dir`。查询响应、计算输入和计算结果必须可追溯，读者报告由 AI 撰写，不能由脚本/模板拼接。

建议的最小信封：

```json
{
  "meta": {
    "source": "fx-ops-resource-recommend",
    "metrics_datasource": "prometheus",
    "metrics_profile": "<profile>",
    "k8s_cluster": "<cluster>",
    "namespace": "<namespace>",
    "service_scope": "<workload-or-pods>",
    "container_scope": "all-containers|application-only",
    "time_window": {"start": "<utc-iso>", "end": "<utc-iso>", "step": "<duration>"},
    "scope_mapping": {
      "user_input": "<original-natural-language-scope>",
      "mapping_basis": ["<confirmed-cluster-prefix|cloud-registry|controlled-discovery>"],
      "mapping_status": "confirmed|ambiguous|blocked",
      "conflicts": []
    }
  },
  "queries": [],
  "coverage": {},
  "stability": {},
  "statistics": {},
  "assumptions": [],
  "limitations": []
}
```

每条 `queries[]` 至少包含：`id`、PromQL、标签/容器范围、start/end/step、预期点数、有效点数、状态（`observed|missing|error|empty`）、证据文件和简化错误摘要。`meta.scope_mapping` 必须记录采用的 profile/cluster 映射的原始用户范围、知识库或受控发现依据、状态和冲突；`ambiguous|blocked` 不能进入实际 Prometheus 取证。不要在结构化证据或报告中回显 token、cookie、密码、手机号或原始敏感匹配值。

## 覆盖与稳定性字段

每种资源和每个建议对象单独计算以下字段：

| 字段 | 含义 |
| --- | --- |
| `expected_samples` | 根据窗口和 step 预计的点数 |
| `valid_samples` | 成功、可解析且范围一致的点数 |
| `coverage_ratio` | `valid_samples / expected_samples` |
| `longest_gap_intervals` | 最长连续缺失的采样间隔数 |
| `history_days` | 实际分析窗口日数 |
| `effective_runtime_days` | 工作负载可解释的连续运行时长 |
| `peak_coverage` | `covered|partial|unknown`，并给出依据 |
| `release_or_churn` | `none|observed|unknown` |
| `sidecar_scope` | `all-containers|application-only|unknown` |
| `autoscaling_status` | `present|absent|unknown`，分别记录 HPA/VPA |

CPU、内存、requests、limits、Pod 生命周期/副本数是关键维度。任一关键维度为 `missing`、`error` 或范围不一致时，任何涉及该维度的结论必须降级；CPU 的完整性不能代替内存的完整性。

## 置信度判定

`confidence` 表示本次证据能支持何种强度的结论，不表示服务健康度。

| 级别 | 最低条件 | 可使用的结论 |
| --- | --- | --- |
| `high` | 28 天以上、覆盖 ≥90%、高峰覆盖、配置一致、无未解释稳定性/所有权阻断 | `supported recommendation`，仍需分阶段验证 |
| `medium` | 14 天以上、覆盖 ≥90%、已知高峰覆盖、关键维度完整 | `supported recommendation` 或明确风险建议 |
| `low` | 7–13 天或覆盖 80–89%、部分峰值/配置所有权未知 | `validation-only recommendation` 或观察 |
| `none` | 少于 7 天、覆盖 <80%、关键维度缺失/失败、范围无法确认 | `insufficient evidence` 或 `blocked` |

任何安全门命中会将“下调资源”降级，即使一般观测的 `confidence` 较高。示例：28 天 CPU 利用低但 memory request 缺失，CPU 观察可为 medium/high，workload 统一降配仍是 `insufficient evidence`。

## 输出状态与措辞

| 状态 | 含义 | 最低说明 |
| --- | --- | --- |
| `completed` | 所需关键证据成功，结论可交付 | 覆盖、假设、风险、证据引用 |
| `partial` | 部分关键维度缺失或失败，但可交付局部观察 | 已覆盖/未覆盖维度、失败原因、禁止得出的结论 |
| `empty` | 复核范围后无匹配样本 | 过滤与窗口、空结果不是正常的说明 |
| `error` | 无法完成主要查询 | 简化失败原因、保留的成功证据、下一步 |
| `blocked` | 必要上下文或门禁条件尚未具备 | 缺少的环境/范围/窗口/确认项 |

推荐标题或句尾应明确为以下之一：

- `confirmed observation`：事实已经被本次证据直接支持；
- `supported recommendation`：算法、历史质量和安全门支持的建议，仍未执行；
- `validation-only recommendation`：数值可供测试，但存在所有权、HPA/VPA、峰值或策略限制；
- `insufficient evidence`：不得从现有证据推导请求/限制或副本调整。

## 失败处理

错误必须以最小必要信息记录：查询 ID、维度、HTTP/CLI 类别、是否已缩小范围复核。已成功的 CPU 查询可以保留，但不得据此写“内存正常”或“资源整体可回收”。

对于指标空结果，顺序是：核验 profile/cluster → 核验 namespace/标签/指标名 → 在受控范围内尝试已确认兼容名称 → 标记 `empty|missing`。只允许有限复核；不要通过扩大到全局集群的查询掩盖范围错误。
