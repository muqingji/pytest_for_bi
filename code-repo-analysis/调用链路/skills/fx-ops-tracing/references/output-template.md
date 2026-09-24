# 链路追踪输出模板

## 链路时序表

链路时序表必须包含累计耗时列。标准格式：

```
序号 | 时间 | elapsed | app | 操作 | 状态 | 耗时
1  | 14:30:00.100 | +0ms  | cep-gateway  | 请求入口     | 200 | 50ms
2  | 14:30:00.150 | +50ms  | fs-sfa    | 查询客户列表   | 200 | 120ms
3  | 14:30:00.170 | +70ms  | fs-metadata  | 获取对象描述   | 200 | 30ms
4  | 14:30:00.200 | +100ms | fs-paas-udobj | 查询自定义字段  | 500 | 3100ms ← 瓶颈！
5  | 14:30:00.250 | +150ms | fs-flow    | 查流程配置    | 200 | 80ms
```

其中 `elapsed = 当前节点时间 - 链路起始时间（t0）`，取链路中最早的时间戳作为 t0。**超时场景下，通过 elapsed 列可以立即定位耗时瓶颈跳**。

## 证据文件说明

所有查询结果已落盘到 `evidence_dir`，主控可直接读取这些文件生成 HTML 报告。典型证据文件包含：

| 文件 | 来源表 | 关键字段 | 报告用途 |
| --- | --- | --- | --- |
| `cep_slow_*.json` | `fs_cep_slow_error_dist` | `traceId`, `rpcId`, `reqUrl`, `status`, `errorCode`, `cost`, `tenantId` | 入口节点、耗时、错误码 |
| `sql_slow_*.json` | `slow_log_dist` | `traceId`, `app`, `query`, `cost`, `dbName` | 慢 SQL 详情 |
| `tomcat_slow_*.json` | `tomcat_access_slow_dist` | `trace_id`, `uri`, `code`, `time_cost` | 应用层慢请求 |
| `error_*.json` | `log_error_dist` | `traceId`, `app`, `rpcId`, `level`, `msg` | 异常堆栈、根因 |
| `app_log_*.json` | `app_log_dist` | `traceId`, `app`, `level`, `msg` | 降级检索后的运行日志 |
| `backend_trace_*.json` | `eye_trace_dist` | `traceId`, `rpcId`, `serverName`, `spanId`, `parentSpanId` | 完整调用拓扑 |

这些文件是**采集落盘后的证据 JSON**（通常为 dict 行列表，字段名因采集器而异，常见 `data.rows` / `primary_row`），**不是** fx-ops CLI 原始 stdout。CLI 结构化查询响应为 `data.columns` + `data.items`（见 fx-ops `references/fx-ops-cli-capabilities.md`「Go CLI 查询响应信封」）；物化后再写入证据。主控读取证据后**按时间戳排序构建时间线**。rpcId 标识 **一次 RPC**（字符串为目标态）；旧层级 `x.y.z` 可标注深度，**均不参与时间线排序**。

## 时间线自动组装规则

从已落盘的证据文件自动组装请求时间线：

1. **数据源**：`TRC-cep-target.json`（t0 入口时间）、`TRC-app-stopwatch.json`（StopWatch 耗时层级）、`TRC-app-log-analysis.json`（关键事件时间点）、`biz_log_function_dist`（如有 APL 调用）
2. **排序依据**：所有事件按 `_time_nanosecond_` 或 `_time_second_` 升序排列，**不按 rpcId**
3. **elapsed 计算**：取 CEP `stamp` 作为 t0，每个事件的 `elapsed = 当前时间 - t0`
4. **delta 计算**：与前一事件的时间差，用于标识耗时跳跃
5. **调用层级**：从 StopWatch 的 `call_chain` 提取 level 字段，用于缩进展示，但不影响排序

### 耗时图形化

HTML 报告中应包含两种可视化：
- **水平条形图**：展示各方法/阶段的耗时占比，瓶颈（≥50%）标红
- **垂直时间线**：事件序列 + 时间戳 + elapsed + delta，关键事件用颜色区分（红=错误、橙=警告、蓝=关键节点、绿=完成）

## StopWatch 自动解析规则

从 `app_log_dist` 的 StopWatch 行自动提取结构化调用链：

**识别模式**：
- `StopWatch 'xxx': running time (millis) = N` → 总耗时入口
- `| xxx | Nms | X%` 或 `|--- xxx | Nms | X%` → 各 task 耗时（`---` 表示嵌套层级）

**解析步骤**：
1. 提取总耗时：`running time (millis) = (\d+)` → `total_ms`
2. 提取各 task：按 `|` 分割，取 task name、time_ms、percentage
3. 重建层级：`---` 数量表示嵌套深度（1 个 `---` = level 2，2 个 = level 3）
4. 标记瓶颈：percentage ≥ 50% 的 task 标记为 `bottleneck: true`
5. 输出结构化 JSON：`call_chain` 数组，每项含 `level`、`name`、`time_ms`、`pct`、`bottleneck`

**输出示例**：
```json
{
 "total_ms": 16697,
 "call_chain": [
  {"level": 1, "name": "DesignerUpdateLayout", "time_ms": 16697, "pct": "100%"},
  {"level": 4, "name": "updateLayoutAndUpdateDescribe", "time_ms": 15976, "pct": "96%"},
  {"level": 5, "name": "validateByObjectDescribe", "time_ms": 14626, "pct": "92%", "bottleneck": true},
  {"level": 6, "name": "fields.doValidate", "time_ms": 14226, "pct": "98%", "bottleneck": true}
 ],
 "bottleneck": "fields.doValidate",
 "bottleneck_ms": 14226,
 "bottleneck_pct": "98%"
}
```
