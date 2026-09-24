# fx-ops idp query — ClickHouse

ClickHouse 用于日志、审计、traceId 和慢查询排查。`--tenant-id` / `-t`：ClickHouse 场景下可选。建议传 `--tenant-id` 用于鉴权，但数据过滤必须写进 SQL WHERE 条件中（如 `WHERE ei = '<EI>' OR ea = '<EA>'`），不依赖 CLI 参数做数据过滤。

已接入的 ClickHouse 数据源在 sql-query 元数据路径上**默认开放 `system` 库**。查库/表是否存在、当前进程、`query_log` 时优先走 `system`，不要当成不可访问。命令、允许/拒绝边界与 `query_log`/`processes` 可见性见 [system-db.md](idp-query/biz/clickhouse/system-db.md)。

## Schema 权威来源

`biz-app-log` 的完整表结构快照以本目录现有单表 Markdown 为载体，覆盖
191 张表（platform v5.10.0 `tables.yaml`，来源 tenant-filters/clickhouse/biz-app-log），字段与索引以
单表 YAML + tables.yaml 为准；运行时仍建议 `show columns` 校验。表全集以
platform 配置为准。快照中的 `indexes` 只接受最终 local MergeTree 表的证据，包含
`PARTITION BY`、`PRIMARY KEY`、`ORDER BY`、TTL 和索引；Distributed、View、MaterializedView
只作为路由入口，不能反向推断这些物理属性。

单表 Markdown 是查询场景和 SQL 示例的补充。字段、类型、alias、时间列、黑名单和物理索引
发生冲突时，以 schema 快照为准；快照没有证据的属性必须重新执行 `show columns` 或 local
元数据查询，不能使用旧文档猜测。

> `<biz>` 常见值：`biz-app-log`、`crm-audit-log`、`bi`。
> ClickHouse 版 `bi` 查询需加 `--dialect clickhouse`，详见 clickhouse.md。

## biz-app-log 表选择

应用日志、CEP 网关、慢请求、慢 SQL、SQL 统计、工作流、MQ、K8s 等日志统一查询 `biz-app-log`，并在 SQL 中写真实表名。只知道诊断场景时先读 `idp-query/biz/clickhouse/diagnostic-scenarios.md` 选表；已知表名时直接读单表文档。执行前可用 `show columns biz-app-log <table>` 校验字段。

`biz-app-log` 后端可能按真实表路由到不同 ClickHouse 集群；示例 SQL 和连通性探测都不要写 `SELECT 1`。需要验证目标表可查时，使用：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM <table> LIMIT 1" -j
```

### 旧 biz 参数与真实表映射关系

查询时必须统一指定为 `biz-app-log`，并根据以下映射在 SQL `FROM` 语句中写真实表名：

* `error-log` 对应 `FROM log_error_dist`（错误日志）
* `cep-log` 对应 `FROM log_cep_dist`（CEP 网关日志）
* `cep-slow-log` 对应 `FROM fs_cep_slow_error_dist`（CEP 慢请求）
* `tomcat-log` 对应 `FROM tomcat_access_dist`（Tomcat 访问日志）
* `tomcat-slow-log` 对应 `FROM tomcat_access_slow_dist`（Tomcat 慢访问日志）
* `oplog` 对应 `FROM paas_oplog_dist`（操作审计日志）
* `sql-slow` 对应 `FROM sql_slow_dist`（数据库慢 SQL）
* `rpc-log` 对应 `FROM rpc_dist`（RPC 调用日志）
* `service-log` 对应 `FROM service_dist`（微服务日志）
* `page-log` 对应 `FROM page_dist`（页面访问日志）
* `function-log` 对应：
* `FROM biz_log_function_dist`（自定义函数执行监控）
* `FROM biz_log_function_user_execute_dist`（自定义函数入参/出参）
* `FROM biz_log_inner_function_api_dist`（自定义函数内部 API 聚合）
* `FROM biz_log_function_user_api_dist`（自定义函数日志输出/报错明细）

## 必做流程

```bash
# 1. 只知道诊断场景时，先读 diagnostic-scenarios.md 选候选表；
#  已知表名时，直接读目标单表文档，确认表名、租户字段、时间字段
# 例如：references/idp-query/biz/clickhouse/log-error.md

# 2. 如需探测目标表，必须查真实表，不使用 SELECT 1
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM <table> LIMIT 1" -j

# 3. 用 10 分钟采样估算 1 小时数据量
fx-ops idp --profile <profile> query <biz> --sql "SELECT count() * 6 AS hourly_est FROM <table> WHERE <time_field> > now() - INTERVAL 10 MINUTE" -j

# 4. 根据量级缩小时间窗口，再查明细
fx-ops idp --profile <profile> query <biz> --sql "SELECT <fields> FROM <table> WHERE <tenant_filter> AND <time_field> > now() - INTERVAL 1 HOUR LIMIT 50" -j
```

## 时间窗口

| 1 小时估算量 | 最大窗口 |
| --- | --- |
| > 5000 万 | 10 分钟 |
| 500 万到 5000 万 | 1 小时 |
| 10 万到 500 万 | 6 小时 |
| < 10 万 | 24 小时 |

用户未给时间范围时，默认先查最近 1 小时；超大表必须进一步缩小。

> [!CAUTION]
> **`app_log_dist`（应用日志，每天约百亿条）专属红线**：① 任何查询必须带 `_time_second_` 时间戳过滤；② 时间跨度**默认不超过 6 小时，绝对不能超过 24 小时**（无论上表估算量如何，24 小时是硬上限）；③ **禁止仅用 `traceId` 而不带时间范围查询**——`traceId` 非分区键，裸 traceId 查询会全分区扫描整个保留期的百亿数据、导致集群失去响应，`traceId` 必须与时间窗（默认 ≤6 小时、最大 ≤24 小时）同时使用。

## 字段规则

* 租户字段按表不同，常见为 `ei`、`tenantId`、`tenant_id`、`ea`，也可能没有租户字段。
* 时间字段按表不同，常见为 `_time_second_`、`createTime`、`stamp`、`operationTime`；筛选条件必须使用快照中标记为分区/索引的时间列。
* 有 `_time_second_` 的表，`WHERE` 用 `_time_second_`，展示时再 `SELECT _time_nanosecond_`。
* traceId、rpcId、spanId、requestId 等字段只在部分表存在，按单表文档确认。
* 多数日志表按时间路由；不确定路由时先用 `idp route get` 确认。
* `stamp` 可能是业务事件或聚合时间，不能因为它是时间类型就作为筛选条件；`page_dist`、`rpc_dist`、`service_dist` 应优先使用 `_time_second_`。
* alias 不是额外的物理字段：只有 alias 的目标字段存在于 query 交集时才可使用；`time_for_ckibana` 是数据列黑名单，即使是 alias 也不能保留或查询。

## 常用模式

```sql
-- 租户 + 时间窗口
SELECT <fields> FROM <table>
WHERE <tenant_field> = '<tenant>' AND <time_field> > now() - INTERVAL 1 HOUR
LIMIT 50

-- traceId 追踪
SELECT <fields> FROM <table>
WHERE traceId = '<trace_id>' AND <time_field> > now() - INTERVAL 1 HOUR
LIMIT 50

-- 聚合排查
SELECT <dimension>, COUNT(*) AS cnt FROM <table>
WHERE <tenant_filter> AND <time_field> > now() - INTERVAL 1 HOUR
GROUP BY <dimension>
ORDER BY cnt DESC
LIMIT 20
```

## 按需索引

* 只知道问题类型（如慢 SQL、PG 锁、MQ 延迟、工作流异常、Nginx 5xx）时，先读 `idp-query/biz/clickhouse/diagnostic-scenarios.md` 选表。
* 已知表名或文档名时，从 `idp-query/biz/clickhouse/index.md` 找单表文档。
* 查 `system` 库（`SHOW DATABASES` / `SHOW TABLES FROM system` / `system.tables` / `query_log` / `processes`）时读 `idp-query/biz/clickhouse/system-db.md`。
* 需要按集群浏览时读 clickhouse.md。
* 只读取目标表的单表文档，不要预读整个 `clickhouse/` 目录。

---

## ClickHouse SQL 避坑指南

### 1. 不建议使用中文别名

建议直接使用英文别名，避免兼容性问题。如果确实需要中文别名，必须用反引号包裹，否则语法报错。

### 2. 时间戳字段是 13 位毫秒，不是秒

`_time_second_`、`stamp`、`Time` 等字段是 **13 位 Unix 毫秒时间戳**。格式化时 DateTime64(3) 类型直接用 `formatDateTime(toDateTime(_time_second_), ...)`，UInt64/Int64 毫秒类型需先除以 1000 再转换。不确定时先用 `SELECT formatDateTime(toDateTime(<value> / 1000), '%Y-%m-%d %H:%i:%s')` 验证。

时间范围过滤：`log_cep_dist` 用 `stamp` 字段，其他表用 `_time_second_` 字段。

### 3. 禁止无 WHERE 条件的全表查询

业务日志表必须带时间范围过滤，否则拒绝执行。`system` 元数据语句（`SHOW DATABASES`、`SHOW TABLES FROM system`、无库过滤的 `SELECT FROM system.tables`）不走这条日志表红线；`system.query_log` / `system.query_thread_log` 仍须时间窗 + `LIMIT`，见 [system-db.md](idp-query/biz/clickhouse/system-db.md)。

### 4. ei、ea、uid、tenantId、tenant_id 等租户字段是 String 类型，值必须加引号

直接写 `tenantId = '815408'` / `ei = '815408'`。**禁止**为“保险”再包一层类型转换：

| 禁止 | 正确 | 说明 |
| --- | --- | --- |
| `toString(tenantId) = '815408'` | `tenantId = '815408'` | 列已是 String；函数转换破坏跳数索引/谓词下推，宽窗易超时（如 `paas_metadata_changes_dist` 30s） |
| `toInt64(tenantId) = 815408` | `tenantId = '815408'` | 租户列按文档类型直比，先 `show columns` 确认，勿猜类型强转 |

拼 SQL 前以单表文档或 `show columns` 的类型为准；类型已是 String 就只加引号，不再 `toString`。

### 5. 其他默认规则

* 未指定排序：默认按时间字段 DESC
* 未指定 LIMIT：默认 `LIMIT 1000`
* 涉及 `LIKE`：自动加 `LIMIT 1000` 防全表扫描
* 生成 SQL 前必须先确认表结构，不允许猜字段

### 6. SHOW COLUMNS 用法

* `SHOW COLUMNS FROM <table>` 在 `--sql` 中**不支持**（返回 `sql_query.invalid_request`）。
* 正确用法：`fx-ops idp --profile <p> show columns <biz> <table> -j`。
* `system` 列元数据用 `SELECT … FROM system.columns`，不要把 `SHOW COLUMNS FROM system.<table>` 写进 `--sql`。

### 7. 高频表误用列名速查

> 完整速查表与标准 SQL 模板见：[`references/idp-query/biz/clickhouse/high-frequency-cheatsheet.md`](references/idp-query/biz/clickhouse/high-frequency-cheatsheet.md)。

| 表 | AI 常见误用/陷阱 | 正确用法 |
| --- | --- | --- |
| `app_log_dist` | `message`/`stamp`/`loggerName`；无 ei/ea；裸 `traceId` | `msg`/`_time_second_`/`logger`（**不是 loggerName**）；**必须** `app` + 时间窗（可加 `traceId`） |
| `log_error_dist` | `errorCode`/`stamp`/`logger` | `msg`/`error`/`_time_second_`/`loggerName`（**不是 logger**）；`reqId` 为 Array，无 errorCode |
| `slow_log_dist` | `sqlText`/`database`/`table`/`latency` | `query`/`dbName`/`cost`/`_time_second_`/`traceId` |
| `rpc_dist` | 按 `traceId` 过滤；`interface`；`WHERE stamp` | 无 `traceId`/`interface`；按 `app`+**`module`**；时间过滤用 **`_time_second_`** |
| `paas_metadata_changes_dist` | `toString(tenantId)=…`；无时间窗或超宽窗 `SELECT *` | `tenantId = '…'` 直比（`Nullable(String)`）；`_time_second_` 半开窗 + `objectId`/`objectApiName`/`traceId` |
| `log_cep_dist` | 无 `bizName` 宽窗 `uri LIKE`；用 `uri` 当主键；时间写 `_time_second_` | `bizName`/`biz` + **`stamp`**；路径优先 `uri2` 等值 |
| `fs_cep_slow_error_dist` | 写 `uri`/`uri2` | 路径字段是 **`reqUrl`**；带 `bizName` 或 `tenantId` + 时间 |
| `tomcat_access_dist` | 无 `app` 宽窗 `uri LIKE`；`time_for_ckibana` | **`app` + `_time_second_`**；路径优先 `uri2`；**禁止**黑名单列 `time_for_ckibana` |
| `biz_log_function_dist` | `createTime` / `create_time` | **只有 `_time_second_`**；`createTime` 列不存在 |
| `biz_log_openapi_dist` | `uri`/`method`/`tenantId`；`WHERE createTime` | **`openApiUrl` + `ei`/`ea` + `_time_second_`** |
| `biz_log_erp_ipaas_log_dist` / `biz_log_erp_sync_log_dist` | `_time_second_` | **erp_sync 库强制 `createTime`**，无 `_time_second_` |
| `tomcat_access_slow_dist` | 无 `app`；`traceId` | **`app` + 时间**；`trace_id`/`traceId` |

> 权威以本次多环境 query 交集和 local 表元数据核验结果为准（schema snapshot: 2026-08-01）；单表文档维护字段列表与查询语义。

### 8. PowerShell / Windows 调用约定

* SQL 字符串字面量用单引号（SQL 标准）；整个 `--sql` 值用双引号包裹传给 shell。
* 禁用 `cmd /c` 包裹 CLI（破坏 SQL 引号，被网关误判为写操作返回 `403 select_only`）。
* 禁用 `| head` / `| cat`（PowerShell 无此命令，静默失败）；输出用 `*> tmp/q.json` 重定向后用 read_file 读，规避 CLIXML 包装。
* PowerShell 下 LIKE 可正常书写（转义简单）；**大表路径模糊匹配的性能策略见 §9**，与本条不冲突。
* 创建 evidence / 临时目录用 PowerShell：`New-Item -ItemType Directory -Force -Path 'C:\path\to\dir'`；探测用 `Test-Path`，勿在 Bash 工具里写 PS cmdlet。
* 仓库根与 skill 目录切换：跑 fx-ops 采集脚本时 `Set-Location` / `cd` 到 **`.agents/skills/fx-ops`**（该 skill 的 uv 项目根）再 `uv run --no-sync python scripts/...` / `uv run pytest`。

### 9. 访问类大表：URI / 路径过滤

适用：`log_cep_dist`、`fs_cep_slow_error_dist`、`tomcat_access_dist`、`tomcat_access_slow_dist`（及 CEP 聚合 `cep_*` 下钻前）。

| 优先级 | 做法 | 说明 |
| --- | --- | --- |
| 1 | **先命中排序键** | CEP：`bizName`/`biz` + `stamp`；Tomcat：`app`（+`profile`）+ `_time_second_` |
| 2 | **优先归一化路径等值** | `uri2 = '…'`（CEP/Tomcat）；CEP 慢表用 `reqUrl` |
| 3 | 子串用 `position(col, '…') > 0` | 语义接近 `LIKE '%…%'`；有 ngram 时可能剪枝，**不能替代**主键过滤 |
| 4 | 宽窗先聚合/慢表 | `cep_minute_dist` / `cep_daily_dist`、`tomcat_access_slow_dist`、`fs_cep_slow_error_dist` |
| 5 | `LIMIT` + 先 count/Top-N | 禁止无维度宽窗拉全量明细 |

**禁止**：

* 无 `app` / `bizName` / 租户 + 数小时窗 + `uri LIKE '%…%'` / `reqUrl LIKE '%…%'`
* `hasToken(uri, '/a/b/c')`：把带 `/` 的整段 path 当 token（`hasToken` 按非字母数字切词，常恒假或语义偏离）
* 在 `fs_cep_slow_error_dist` 上写 `uri`/`uri2`（列不存在，正确字段是 `reqUrl`）

**选型速查**：

| 意图 | 优先表 | 路径字段 + 必带过滤 |
| --- | --- | --- |
| CEP 全量按 API 查 5xx/耗时 | `log_cep_dist` | `uri2`/`uri` + **`bizName` + `stamp`** |
| CEP 只关心慢/错 | `fs_cep_slow_error_dist` | **`reqUrl`** + `bizName` 或 `tenantId` + 时间 |
| Tomcat 全量入口 | `tomcat_access_dist` | `uri2`/`uri` + **`app` + `_time_second_`** |
| Tomcat 慢路径 | `tomcat_access_slow_dist` | `uri2` + **`app` + 时间**；`uri2` 空则回退 path |
| 长窗 URI 失败/慢趋势 | `cep_minute_dist` / `cep_daily_dist` | **`uri2` + `bizName` + 时间/day**（PK 含 uri2） |

单表细则：`biz/clickhouse/log-cep.md`、`fs-cep-slow-error.md`、`tomcat-log.md`、`tomcat-access-slow.md`。
