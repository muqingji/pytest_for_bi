---
symptom: traceId 端到端链路追踪 / 单次请求异常定位
inputs:
 required: [trace_id]
 optional: [tenant_id, error_code, screenshot, time_window]
outputs:
 signals: [service_timeline, first_error_hop, error_stack, slow_sql, rpc_tree]
 next_skills: [fx-ops-query, code-search, extract_error_anchor, resolve_tenant_cloud]
escalate_when:
 - 应用代码异常栈明确指向缺陷时，进入 code-search
 - 仅有聚合现象而无单次请求线索时，交回 fx-ops 主控
---

# traceId 端到端链路追踪

> 本 playbook 面向 HND 要求完整链路、慢/超时、Phase1 证据不足、用户要求继续深挖或质量门禁命中的场景。单 traceId 首轮已由主控 playbook_collect / 索引证据覆盖时，直接复用已有证据，不重复取证。

输入：一个 traceId（或多个）。
输出：这条调用链经过了哪些服务、在哪一跳出错、错误堆栈是什么。

## 核心流程：证据驱动的诊断 (Evidence-First Workflow)

在开始查询前，必须遵循以下标准化诊断路径：

1. **取证初始化**：创建证据目录 `output/evidence/<YYYYMMDD-TraceId>/`。
2. **感知与环境锚定**：

   - 优先复用 HND 与 `index.md` 已列证据中的 `traceIdParsed`、`env`、`tenant_context`、`time_window`。
   - 若有明确 traceId 但缺少 `traceIdParsed`，先调用 `extract_error_anchor` / `parse_traceid` 解析时间、企业、用户与来源。
   - 若只有 reqId / CEP 错误码，先走 `cep-error-code.md` 反查真实 traceId；回填 `traceId/traceIdParsed` 后再回到本 playbook。
   - 若解析出 `ea` 但缺少 `env/tenant_context`，调用 `resolve_tenant_cloud` 确定物理云环境。
3. **分阶段取证**：

   - 执行下述 Step 1 ~ Step 7 查询。
   - **关键：** 每次 `fx-ops` 查询的结果必须重定向保存至证据目录（如使用 `> output/evidence/xxx/query_result.json`）。
4. **结论输出**：引用上述保存的文件。

## 触发条件
...

- 用户说"这个 traceId 是什么情况"、"帮我追下这条链路"。
- 用户粘了告警内容、错误截图，里面带 traceId（格式不固定，常见 `E-...`、`FSA-...`、`xxx/xxx`）。
- 排查中其他 playbook 命中了 traceId，转入本 playbook。

## 边界

- 适用于**已经有 traceId、错误码或单次请求线索**的定向追踪。
- 如果只有“某应用最近报错很多”“最近 5 分钟错误突增”这类聚合现象，没有单条请求线索，先调用 `fx-ops` skill，让它从应用级聚合报错排查入口开始编排。

## 涉及表（按价值密度排序）

| 表 | biz | 用途 | 时间字段 | 租户字段 |
| --- | --- | --- | --- | --- |
| `fs_cep_slow_error_dist` | `biz-app-log` | 网关慢请求，traceId 第一现场 | `_time_second_` | `tenantId` |
| `slow_log_dist` / `sql_slow_dist` | `biz-app-log` | 慢 SQL，定位 DB 瓶颈 | `_time_second_` | `ei` / `ea` |
| `tomcat_access_slow_dist` | `biz-app-log` | 应用层慢请求 | `_time_second_` | `ei` / `ea` |
| `log_error_dist` | `biz-app-log` | 同 traceId 的 ERROR 堆栈 | `_time_second_` | `ei` / `ea` |
| `log_cep_dist` | `biz-app-log` | 网关入口请求，看响应码 | `stamp` | `ei` / `ea` |
| `eye_trace_dist` | `biz-app-log` | 方法级 RPC 链路（最详细但最贵） | `_time_second_` | `tenantId` |

字段名不要跨 skill 直接查文档路径；需要确认 ClickHouse 单表字段定义时，调用 `fx-ops-query` skill，由它按目标 biz 和单表文档完成校验。

> 注意：`tomcat_access_slow_dist` 字段命名是 `trace_id`（snake_case），与其它日志表的 `traceId`（camelCase）不一致；查询时用 `trace_id`，不是 `traceId`。

## 标准步骤

### Step 0 — 先确定时间范围（强制前置）

下面所有查询都要带 `_time_second_` / `stamp` 时间窗。**若用户未给时间、或 traceId 可能较旧**，不要写未展开的 `now() - INTERVAL`：先用 `extract_error_anchor` / `parse_traceid` 从 traceId 解析时间点并算出字面量 T0/T1；解析不出就转 [traceid-time-unknown.md](traceid-time-unknown.md) 用小表分天反查出 `first_seen` / `last_seen`，再回到本流程。**时间范围未确定前，禁止查询 `app_log_dist`。**

### Step 1 — 先在高价值密度表里命中

从四张高信号表开始；需要完整链路或专项门禁时，在此基础上补完整拓扑和专项证据。并行查 4 张 slow / error 表（traceId 是精确等值，不需要租户过滤）：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, traceId, rpcId, reqUrl, status, errorCode, cost, tenantId, ea
 FROM fs_cep_slow_error_dist
 WHERE traceId = '<TRACE_ID>' AND _time_second_ BETWEEN '<TIME_MINUS_1HOUR>' AND '<TIME_PLUS_1HOUR>'
 ORDER BY _time_second_ ASC LIMIT 50" -j

fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, ei, ea, traceId, rpcId, query, cost, dbName
 FROM slow_log_dist
 WHERE traceId = '<TRACE_ID>' AND _time_second_ BETWEEN '<TIME_MINUS_1HOUR>' AND '<TIME_PLUS_1HOUR>'
 ORDER BY _time_second_ ASC LIMIT 50" -j

fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, ei, ea, trace_id, uri, code, time_cost
 FROM tomcat_access_slow_dist
 WHERE trace_id = '<TRACE_ID>' AND _time_second_ BETWEEN '<TIME_MINUS_1HOUR>' AND '<TIME_PLUS_1HOUR>'
 ORDER BY _time_second_ LIMIT 50" -j

fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, ei, ea, traceId, rpcId, level, loggerName, msg, error
 FROM log_error_dist
 WHERE traceId = '<TRACE_ID>' AND _time_second_ BETWEEN '<TIME_MINUS_1HOUR>' AND '<TIME_PLUS_1HOUR>'
 ORDER BY _time_second_ ASC LIMIT 50" -j
```

> **排序**: 默认按时间。仅当样本 rpcId 仍是旧层级形态 `x.y.z` 时，可改用 `ORDER BY length(rpcId), rpcId` 辅助看调用深度；**字符串形态 rpcId 禁止用 length 建树**。

**运行时日志级别降级检索机制**：如果常规 `log_error_dist` 物理表没有查询到该 `traceId` 的任何报错记录，必须立即启动降级检索——使用该 `traceId` 检索 `app_log_dist` 表（全量运行日志），**遵循“ERROR > WARN > INFO”的日志级别顺序过滤**。检索时应当全面扫描并寻找任何包含异常堆栈特征（如各类型 `Exception`、`at com.`、`error`、`fail` 或是其他带有业务拦截性质的关键字）的运行日志，以防止由于业务层仅作较轻日志打印而导致排查受阻。⚠ 检索 `app_log_dist` 时必须带上该 traceId 命中的 `_time_second_` 时间窗（跨度默认 ≤6 小时、最大 ≤24 小时），**绝不能仅用 traceId 裸查全量 `app_log_dist`**——该表每天约百亿条，`traceId` 非分区键，裸 traceId 全分区扫描会拖垮整个集群。

- 如需确认字段名，调用 `fx-ops-query` skill 按目标 biz 做单表字段校验；如果某表没有 `rpcId` 字段，去掉再查。
- 这一步通常已经能拿到：调用了哪些 app、谁报了 ERROR、瓶颈是 DB 还是接口。

> **rpcId 噪声防范**：**traceId = 一次点击/开页**，其下常有多个 rpcId（各代表一次 RPC）。Step 1 多条记录必须**按 rpcId 分组判读**，避免把同操作下其他正常 RPC 的日志当根因。若 `context_updates.traceIdLookup.resolved_rpcId` 已回传，有 rpcId 列的表可 `AND rpcId = '<R>'`。多 rpcId 时结论必须写明选了哪个及其排除理由。rpcId 语义/覆盖矩阵见 `fx-ops-query` → `reqId-traceId-rpcId.md`。
>
> **兼容旧合同**：如未提供 `resolved_rpcId`，仍按 `traceId + 窄时间窗` 查询并按 rpcId 分组判读即可，不视为错误或阻塞条件。

### Step 2 — 还原调用顺序（时间 / span；层级 rpcId 仅兼容）

slow / error 命中后是一组散点。**默认按时间 + span 还原顺序**（适配字符串形态 rpcId）：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT
  formatDateTime(_time_second_, '%Y-%m-%d %H:%i:%S') AS ts,
  rpcId,
  serverName,
  spanId,
  parentSpanId
 FROM eye_trace_dist
 WHERE traceId = '<TRACE_ID>'
  AND _time_second_ BETWEEN '<TIME_MINUS_1HOUR>' AND '<TIME_PLUS_1HOUR>'
 ORDER BY _time_second_ ASC, spanId
 LIMIT 200" -j
```

判读规则：

- **目标语义**：每个 **rpcId = 一次 RPC 请求**（字符串 ID 为后续标准形态）。
- **旧层级形态**（逐步废弃）：若样本仍是 `0` / `0.1` / `1.2.3`，可用 `ORDER BY length(rpcId), rpcId` 看深度；`'0'` 入口、`'0.1'` 子调用等前缀建树**仅对此形态**有效。
- **字符串形态**：禁止 `length(rpcId)` 建树；用 `spanId / parentSpanId`（`parentSpanId IS NULL` 找根）+ 时间序关联。
- 同 traceId 下多个 rpcId 时，先分组再谈根因，不要把「整个操作」当成「单次 RPC」。

### Step 3 — 慢 / 超时场景必跑：`app_log_dist`（StopWatch）+ `biz_log_function_dist` 同步取证

只要主诉是**超时 / 慢 / latency 高 / request_time 偏长**（不区分 cep-slow 是否命中），traceId 已知时立即并行查两张表，不要等 Step 1 完全收敛再补：

#### 1. `app_log_dist` 抽 StopWatch 段（Spring StopWatch 是慢请求的核心证据源）

业务代码里大量用 Spring `StopWatch` 打分阶段耗时（`getPlanInfoCommon finish ea:xxx, stopWatch:StopWatch '': running time (millis) = N` + 多行 Task name 占比）。这部分日志只在 `biz-app-log` 数据源下的 `app_log_dist` 表里，`log_error_dist` / 慢 SQL 表都没有。

> **模板硬约束（BUG-74）**：时间列固定用 **`_time_second_`**（`app_log_dist` 无 `stamp`）；**必须带 app 过滤**（取自 `CTX-app-discovery.json` 的候选，先 `show columns biz-app-log app_log_dist` 校验列）；保留 LIMIT。`_time_nanosecond_` 仅用于同表内排序精度，不作为查询投影。

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT _time_second_, app, pod, level, logger, rpcId, substring(msg, 1, 1500) AS msg
 FROM app_log_dist
 WHERE traceId = '<TRACE_ID>'
  AND app IN ('<APP_1>', '<APP_2>')
  AND positionCaseInsensitive(msg, 'StopWatch') > 0
  AND _time_second_ BETWEEN '<TIME_MINUS_5MIN>' AND '<TIME_PLUS_5MIN>'
 ORDER BY _time_second_ ASC LIMIT 50" -j
```

读取要点：
- 抓 `running time (millis) = N` 总耗时和 Task name 各分段占比；占比 ≥ 50% 的 task 是首选嫌疑
- StopWatch 通常分布在多个 app/pod，按 rpcId 排序还原跨服务时序
- 如果 traceId 精确等值 + StopWatch 关键字过滤后命中条数 < 5，可去掉 StopWatch 关键字放宽，但**必须保留 `_time_second_` 时间窗（跨度默认 ≤6 小时、最大 ≤24 小时，如 `BETWEEN '<TIME_MINUS_5MIN>' AND '<TIME_PLUS_5MIN>'`）与 app 过滤（app IN 候选）**；**绝不能仅用 `traceId` 裸查全量 `app_log_dist`**——该表每天约百亿条，裸 traceId 全分区扫描会拖垮整个集群

#### 2. `biz_log_function_dist` 抓 APL 自定义函数执行（包括失败和超时）

很多慢请求根因是租户写的 APL 自定义函数（前置触发器、计算字段、APL 回调）执行慢或在循环中 N+1。`biz_log_function_dist` 按 traceId 等值能直接定位：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT createTime, apiName, type, version, fail, cost, totalCost,
     bindingObjectApiName, substring(error, 1, 500) AS error
 FROM biz_log_function_dist
 WHERE traceId = '<TRACE_ID>'
  AND createTime BETWEEN '<TIME_MINUS_5MIN>' AND '<TIME_PLUS_5MIN>'
 ORDER BY createTime ASC LIMIT 50" -j
```

读取要点：
- 命中即代表请求经过 APL Runtime；按 `cost` / `totalCost` 倒序找最慢函数
- `fail = true` 或 `error` 非空 → 函数本身抛错，转 Step 2 看源码
- 若多次同名函数累计 cost 占总 request_time ≥ 30%，根因高度可能在 APL 循环逻辑（N+1、穿透缓存、重聚合），无需等 Step 2 进一步验证就可以拉源码深挖

#### 协同判读

| `app_log_dist` StopWatch 命中 | `biz_log_function_dist` 命中 | 结论方向 |
| --- | --- | --- |
| 命中且某 task 占比高 | 未命中 | Java 业务代码热点，Step 2 改为查代码 |
| 命中 + 命中 | 命中 | APL 函数耗时主导，直接进 Step 2 拉源码 |
| 未命中 | 命中 | 仅函数链路慢，看 cost 分布选最慢函数进 Step 2 |
| 都未命中 | 都未命中 | 慢点不在应用层，回 Step 1 看 `slow_log_dist` / `sql_slow_dist` 或下游依赖 |

> traceId 等值查询不需要租户过滤；但 `app_log_dist` 体量大，**StopWatch 关键字 + traceId 等值是双过滤**，不要去掉关键字裸跑。

### Step 4 — 异常识别与 APL 专项审计

如果 Step 1 或 Step 2 识别到耗时瓶颈在 APL Runtime（如 `fs-paas-function-service-runtime`），或链路/时间线中 **function 相关服务名单跳耗时 >5s**（见主控 `fx-ops` `report-quality-gate.md` §2b）：

1. **确定函数名**：在 `fx-ops` 编排下 **回抛主控派发 `fx-ops-apl`**（`function-slow.md` / §2b），由 apl 驱动查询；tracing 子会话不得单独替代 apl 直查。取证口径示例（由 query 执行）：
 ```bash
 fx-ops idp --profile <profile> query biz-app-log --sql "SELECT apiName, cost, totalCost, error FROM biz_log_function_dist WHERE traceId = '<TRACE_ID>'"
 fx-ops idp --profile <profile> query paas --tenant-id <id> --sql "SELECT body FROM mt_udef_function WHERE api_name = '<apiName>' AND is_current = true"

 fx-ops idp --profile <profile> query biz-app-log --sql "
 SELECT stamp, bizName, serverName, ei, ea, traceId, reqId, uri, status, request_time
 FROM log_cep_dist
 WHERE traceId = '<TRACE_ID>' AND stamp BETWEEN '<TIME_MINUS_1HOUR>' AND '<TIME_PLUS_1HOUR>'
 LIMIT 20" -j
```

## 输出格式

不要堆原始日志。整理为：

1. **链路时序**：`序号 | 时间 | elapsed | app | 操作 | 状态 | 本跳耗时` 表格（按时间排）。

   - **elapsed（累计耗时）是必填列**：取链路中最早时间戳为 `t0`，每个节点计算 `elapsed = 当前节点时间 - t0`，格式为 `+Xms`。
   - **本跳耗时**：当前节点自身处理耗时（如有 `cost`/`time_cost`/`request_time` 字段）。
   - 超时场景下，通过 elapsed 列可立即定位瓶颈跳——例如 `+50ms → +3200ms` 说明这一跳耗时 3 秒+。
2. **异常节点**：哪个 app、哪一跳报 ERROR / 超时 / 慢 SQL。
3. **结论**：故障根因 + 受影响租户（ei / ea）。
4. **下一步建议**：要不要看 Pod 资源（→ pod-resource-rca）/ 错误堆栈细节。

### 证据文件与报告生成

所有查询结果已按"证据落盘"规则保存到 `evidence_dir`。当调用链涉及 3+ 服务节点或多跳异常传播时，主控 `fx-ops` 可直接读取这些证据文件生成 HTML 诊断报告。若堆栈指向具体代码缺陷，主控会调用 `code-search` 获取源码信息。

## 反模式

- ❌ 一上来就查 `eye_trace_dist` 或 `app_log_dist`，token 直接打满。
- ❌ HND / `index.md` 已有同源同窗直接证据时仍重复进入端到端链路追踪。
- ❌ 用 `LIKE '%trace%'`，traceId 必须精确等值。
- ❌ 跳过 ClickHouse `WHERE` 直接用 `--tenant-id`，租户没生效（不过 traceId 等值场景租户过滤可省）。
- ❌ 时间窗口一开始就 1 天。
- ❌ 把字符串形态 `rpcId` 用 `ORDER BY length(rpcId)` 建树 —— 仅旧层级 `x.y.z` 可用 length；默认按时间 / span。
- ❌ 把 **traceId** 当成单次 RPC —— traceId 是一次点击/开页，失败分支用 **rpcId** 区分。
- ❌ 链路时序表不标注累计耗时（elapsed）——超时场景下无法快速定位瓶颈跳。
- ❌ 多语言相关异常时在代码库搜索 i18n key —— 应查 i18n 业务表（租户 0 + 租户自己）。
- ❌ 慢/超时场景只查 `fs_cep_slow_error_dist` / `slow_log_dist` / `sql_slow_dist` / `tomcat_access_slow_dist`，不查 `app_log_dist` 的 StopWatch 段 —— Spring StopWatch 分阶段耗时只在 `app_log_dist` 里，跳过会丢失关键时间分布证据。
- ❌ 慢/超时场景不顺手查 `biz_log_function_dist` —— 大量慢请求根因是租户 APL 自定义函数循环或穿透缓存，必须按 traceId 同步排查。
