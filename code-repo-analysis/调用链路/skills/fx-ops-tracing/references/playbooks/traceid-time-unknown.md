---
symptom: traceId 时间未知 / 旧 traceId 搜索
inputs:
 required: [trace_id]
 optional: [app_name, ea, profile]
outputs:
 signals: [derived_time_hint, discovered_time_window, matched_log_source]
 next_skills: [fx-ops-query]
escalate_when:
 - 找到稳定时间窗后，转入 trace-end-to-end
 - 扩窗到 24 小时仍为空时，停止并提示 traceId 可能错误或已过保留期
---

# 时间未知时按 traceId 搜索

输入：一个 traceId，但不确定产生时间（可能是几天甚至几周前的）。
输出：找到该 traceId 对应的日志记录，确定时间窗口，转入端到端链路追踪。

> [!IMPORTANT]
> **【解析 traceId 时间 = 链路追踪的强制第一步】** 拿到 traceId 后，**在查询任何日志之前，必须先确定它的时间范围**：① 先用 `extract_error_anchor` / `parse_traceid` 从 traceId 解析时间点；② 解析不出时间时，必须走本 playbook 的小表分天反查，拿到 `first_seen` / `last_seen`。**时间范围未确定前，绝对禁止查询 `app_log_dist` 等大表**（裸 traceId 全分区扫描会拖垮集群）。只有确定时间范围后，才带着该时间窗进入 trace-end-to-end.md。

## 触发条件

- 用户给了一个 traceId，但没有给出时间范围
- traceId 格式不包含时间信息（如协议格式、appName/uuid 格式、互联格式）
- traceId 包含 ULID 时间但用户未意识到可反解

## Step 0 — 先从 traceId 提取时间和辅助信息

调用 `extract_error_anchor` / `parse_traceid` 解析 traceId，获取结构化输出。

- 如果输出含 `time` 字段，**直接用该时间作为锚点**，跳到 [Step 2](#step-2--确定时间窗口)。
- 如果无 `time` 字段，进入 Step 1 分天搜索。

从 `extract_error_anchor` / `parse_traceid` 输出中提取辅助过滤条件：

| 字段 | SQL 过滤 |
|------|---------|
| `source` (appName) | `AND app = '<appName>'` |
| `uid` 中的 ea | `AND ea = '<ea>'` |
| `profile` | `AND profile = '<profile>'` |

**只要有可能，必须在查询中加上这些过滤条件**，避免全表扫描。

## Step 1 — 优先小表、严格分天限制时间窗进行日志反查

为了减少全表日志查询范围、避免引发 ClickHouse 全表扫描，如果无法从 TraceId 本身解析出时间，或者需要双重确认，必须以**“表保留性质与密度优先、优先查小表锁定时间、单次查询严禁跨天”**的策略反查发生时间。

**核心红线**：为了防止单次查询跨越多个分区导致扫描性能退化，**单次 ClickHouse 查询的时间范围绝对不能超过 24 小时（即单次不跨天查询）**。必须采用分天、向前推进的循环查询策略：

### 1. 第一优先级（按天向前推进，并行查询高密度、高保留期小表）
- **最大推进深度**：最近 7 天（按天分步进行，当前时间向前推进最多 7 次，每次单天查询）。
- **表与 biz**：
- `fs_cep_slow_error_dist` (biz: `biz-app-log`) - 网关慢请求/错误日志
- `log_error_dist` (biz: `biz-app-log`) - 错误日志
- `tomcat_access_slow_dist` (biz: `biz-app-log`，注意 traceId 字段名为 `trace_id`) - 访问慢日志
- **执行方式**：从今天（最近 24 小时）开始，在此单天窗口内并行执行小表查询，若命中立即终止返回；若无结果，再推进到前一天（单天），以此类推。

### 2. 第二优先级（若小表未命中，按天向前查询中等量级网关日志）
- **最大推进深度**：最近 3 天（按天分步进行，当前时间向前推进最多 3 次）。
- **表与 biz**：
- `log_cep_dist` (biz: `biz-app-log`) - 网关普通/全量日志
- **执行方式**：同样按单天窗口从今天起向前尝试，命中即止，防止大表大范围一次性扫描。

### 3. 第三优先级（访问日志兜底，单次范围缩到最小）
- **限制窗口**：仅查询最近 12 小时（或最多 24 小时），**绝对禁查 24 小时以上**。
- **表与 biz**：
- `tomcat_access_dist` (biz: `biz-app-log`，注意 traceId 字段为 `trace_id`)
- **执行方式**：访问日志依然较多，仅在以上各表全部落空，且推断该请求发生在最近一天内时，才能在此超窄的 12-24 小时单次非跨天窗口内执行等值过滤。

*注：`J-E.` 开头的 traceId（代表集成平台）不经过 CEP 网关，查询时应当自动跳过网关相关表（如 `log_cep_dist`、`fs_cep_slow_error_dist`），直接从错误日志 `log_error_dist` 开始查询（绝对禁止在数据量极大的 app_log_dist 中反查 traceId 的时间点）。*

```
对于每个优先级（第一优先级小表、第二优先级网关表、第三优先级访问表）：
  # 每次切换至新优先级表时，必须将时间窗口重置回当前时间开始计算
  day_end = now()
  day_start = now() - 1 day
  max_days = 7 (对于小表) 或 3 (对于网关表) 或 1 (对于访问日志表)
  
  循环最多 max_days 次:
    对当前优先级的表并行执行该单天窗口查询:
      查询: WHERE traceId = '<TRACE_ID>'
         AND _time_second_ >= day_start AND _time_second_ < day_end
         [AND 辅助过滤]
      如果有结果 → 记录返回的 first_seen 与 last_seen，进入 Step 2，并立即退出全部反查流程。
    day_end = day_start
    day_start = day_start - 1 day
```

### 查询模板

```sql
SELECT min(_time_second_) AS first_seen, max(_time_second_) AS last_seen, count() AS cnt
FROM <表名>
WHERE traceId (或者对于访问日志为 trace_id) = '<TRACE_ID>'
 AND _time_second_ >= '<day_start>'
 AND _time_second_ < '<day_end>'
 AND ea = '<ea>'     -- 如果 extract_error_anchor 解析出了 ea
 AND app = '<appName>'  -- 如果 traceId 是 appName/uuid 格式
```

> 用 `count()` + `min/max` 而非 `SELECT *`，先判断命中数和跨度，避免拉回大量数据。
> `tomcat_access_slow_dist` 和 `tomcat_access_dist` 的 traceId 字段名是 `trace_id`（snake_case）。

### 未找到（或超出限制深度）

- 向用户说明已向前搜索最近 7 天小表（及 3 天网关日志）未命中。
- 询问是否继续搜索更早的时间范围。
- 提醒可能原因：日志已过保留期、traceId 不完整、有误，或由于 app-log 表过于庞大限制了反查范围。

## Step 2 — 确定时间窗口

拿到 `first_seen` 和 `last_seen` 后，**必须判断时间跨度是否异常**：

### 正常情况（跨度 ≤ 1 小时）

以 `first_seen` 为锚点，取 `first_seen - 30min ~ last_seen + 30min` 作为时间窗口，进入 trace-end-to-end.md。

### 异常情况（跨度 > 1 小时）

程序 bug 可能让同一个 traceId 持续数小时甚至数天产生大量日志。此时：

1. **不要直接用完整跨度查全量日志**，会导致海量数据。
2. 先查首条异常记录定位首发时间：

```sql
SELECT _time_second_, app, rpcId, level, loggerName, msg, error
FROM log_error_dist
WHERE traceId = '<TRACE_ID>'
 AND _time_second_ >= '<first_seen>'
 AND _time_second_ < '<first_seen + 1 hour>'
 [AND 辅助过滤]
ORDER BY _time_second_
LIMIT 20
```

3. 如果 1 小时内日志已超过 50 条，进一步缩到 10 分钟：

```sql
SELECT _time_second_, app, rpcId, level, loggerName, msg, error
FROM log_error_dist
WHERE traceId = '<TRACE_ID>'
 AND _time_second_ >= '<first_seen>'
 AND _time_second_ < '<first_seen + 10 min>'
ORDER BY _time_second_
LIMIT 50
```

4. 告知用户：该 traceId 跨度异常（`<first_seen>` ~ `<last_seen>`，共 `<N>` 小时），已聚焦首发时段排查。如需查看其他时段，请指定具体时间范围。

## 找到后

确定合理的时间窗口后，进入 trace-end-to-end.md 执行标准链路追踪流程。
