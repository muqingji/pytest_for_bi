# ClickHouse 高频日志表字段、索引与筛选避坑速查手册

> **更新时间**: 2026-08-21 | **适用数据源**: `biz-app-log`  
> **用途**: 本手册汇总高频日志表核心字段、**时间列权威规约**、过滤禁忌与标准 SQL 模板。时间列以 foneshare `system.columns` / local `PARTITION BY` 为准（2026-08-21）。

---

## 一、 核心避坑铁律 (Top Anti-Patterns)

1. **时间列严禁错用**：
   - `log_cep_dist` 表强制使用 **`stamp`**（`DateTime64`）。分区 `toYYYYMMDD(stamp)`。
   - `log_error_dist`、`app_log_dist`、`slow_log_dist`、`rpc_dist`、`service_dist`、`biz_log_function_dist`、`tomcat_access_dist` 强制使用 **`_time_second_`**（`DateTime`）。
   - **`logger.biz_log_function_dist` 没有 `createTime` / `create_time`**。写成 `WHERE createTime ...` 会 `sql_query.column_not_found`（实测 `Column createtime does not exist.`）。仅历史库 `function_log.biz_log_function_dist` 才有 `createTime`；`biz-app-log` 的 `FROM biz_log_function_dist` **不走**该历史库。
   - **`erp_sync` 库无 `_time_second_`**：`biz_log_erp_ipaas_log_dist` / `biz_log_erp_ipaas_probe_log_dist` / `biz_log_erp_sync_log_dist` 强制 **`createTime`**。
   - **【血泪教训】`log_error_dist` 与 `app_log_dist` 表中绝对没有 `stamp` 列！误用 `stamp` 会触发 `Missing columns: 'stamp'` 语法报错。**
2. **黑名单列 `time_for_ckibana`**：
   - `tomcat_access_dist` 物理上存在该列，**禁止 SELECT / WHERE / 文档字段表当作可用列**。过滤只用 `_time_second_`。
3. **易混字段精准区分**：
   - `log_error_dist` 表的 Logger 列名是 **`loggerName`**（**不是 `logger`**）。
   - `app_log_dist` 表的 Logger 列名是 **`logger`**（**不是 `loggerName`**），消息列是 **`msg`**（**不是 `message`**）。
   - `slow_log_dist` 表的 SQL 文本列名是 **`query`**（**不是 `sqlText` / `sql`**），耗时列名是 **`cost`** (ms)。
   - `log_cep_dist` 表的请求 ID `reqId` 是 **`Array(String)`** 类型，等值匹配必须使用 **`has(reqId, '<CODE>')`**，严禁使用 `reqId = '...'`。
   - `rpc_dist` 与 `service_dist` 是聚合表，**没有 `traceId` 与 `interface` 字段**。
   - `biz_log_openapi_dist` **没有** `uri` / `method` / `tenantId`；路径列是 **`openApiUrl`**，租户是 **`ei` / `ea`**。
4. **`app_log_dist` 扫表防爆红线**：
   - `app_log_dist` 每天百亿条日志，**必须联合 `app` 字段与 `_time_second_` 时间窗**（默认 ≤6h，绝对 ≤24h）查询，**绝对禁止裸 `traceId` 全表扫描**。

---

## 二、 Top 12 高频表权威速查表

| 表名 (`FROM <table>`) | 单表文档路径 | 核心用途 | 强制时间列 | 强过滤 / 索引列 | 特殊字段处理规则 |
| --- | --- | --- | --- | --- | --- |
| `log_cep_dist` | [`log-cep.md`](./log-cep.md) | CEP 网关访问日志 (HTTP 状态码/错误码) | **`stamp`** | `bizName`, `uri2`, `companyName`, `status` | `reqId` 为 Array，用 `has(reqId, 'code')` |
| `log_error_dist` | [`log-error.md`](./log-error.md) | Java 应用未捕获 ERROR 堆栈 | **`_time_second_`** | `app`, `traceId`, `loggerName`, `ei`/`ea` | 无 `stamp` 列；Logger 为 `loggerName` |
| `app_log_dist` | [`app-log.md`](./app-log.md) | 后端 Java/Dubbo 应用全量日志 | **`_time_second_`** | **`app`** (必带), `profile`, `pod`, `traceId` | 无 `stamp` 列；必带 `app` + 时间窗；Logger 为 `logger` |
| `slow_log_dist` | [`slow-log.md`](./slow-log.md) | 数据库慢 SQL 日志 | **`_time_second_`** | `dbName`, `traceId`, `ei`/`ea` | SQL 文本为 `query`，耗时为 `cost` (ms) |
| `biz_log_function_dist` | [`biz-log-function.md`](./biz-log-function.md) | APL 自定义函数执行与监控 | **`_time_second_`** | `tenantId`, `apiName`, `traceId`, `errorCode` | 查函数入参出参用 `biz_log_function_user_execute_dist` |
| `rpc_dist` | [`rpc-log.md`](./rpc-log.md) | Dubbo RPC 服务间调用汇总 | **`_time_second_`** | `app`, `module`, `caller` | **无 `traceId` / `interface` 列** |
| `service_dist` | [`service-log.md`](./service-log.md) | 微服务 Method 级调用统计 | **`_time_second_`** | `app`, `module`, `method` | **无 `traceId` 列**；含 `method` 维度 |
| `paas_oplog_dist` | [`paas-op-log.md`](./paas-op-log.md) | PaaS CDC 数据变更日志 | **`_time_second_`** | `schema`, `op`, `object_describe_api_name`, `ei`/`ea` | 记录 insert/update/delete 的 before/after |
| `tomcat_access_dist` | [`tomcat-log.md`](./tomcat-log.md) | Tomcat 容器 HTTP 访问日志 | **`_time_second_`** | `app`, `profile`, `uri2`, `code` (**非 `status`**), `trace_id` | 必须带 `app` + `_time_second_` |
| `k8s_events_dist` | [`k8s-event-log.md`](./k8s-event-log.md) | K8s Pod 调度 / OOM / 扩缩容事件 | **`_time_second_`** | `involvedObject_namespace`, `involvedObject_name`, `reason`, `type` | 查 OOMKilled / Unhealthy / Evicted |
| `fs_cep_slow_error_dist` | [`fs-cep-slow-error.md`](./fs-cep-slow-error.md) | CEP 慢请求与错误专项日志 | **`_time_second_`** | `bizName`, `tenantId`, `reqUrl` | 路径字段是 **`reqUrl`** (无 `uri`/`uri2`) |
| `kpi_cep` | [`kpi-cep.md`](./kpi-cep.md) | CEP 网关异常样本与 SLA 明细 | **`stamp`** | `bizName`, `status`, `reqId`, `traceId` | 用于异常请求样本打标与 SLA 分析 |

---

## 三、 时间列权威对照（物理库已验证）

过滤列必须是分区/排序相关列。`createTime` 存在 ≠ 可以当 WHERE 主过滤。

| 表名 | 数据库 | 主过滤/分区列 | 事件/创建时间 | 纳秒列 | 避坑 |
| --- | --- | --- | --- | --- | --- |
| `biz_log_function_dist` | `logger` | **`_time_second_`** | **无 `createTime`** | `_time_nanosecond_` | 严禁 `createTime` / `create_time`；历史库 `function_log` 才有 |
| `biz_flow_runtime_log_dist` | `logger` | **`_time_second_`** | `createTime` | `_time_nanosecond_` | 分区走 `_time_second_` |
| `biz_log_openapi_dist` | `logger` | **`_time_second_`** | `createTime` | `_time_nanosecond_` | 无 `uri`/`method`/`tenantId`；用 `openApiUrl` / `ei` / `ea` |
| `biz_log_erpsyncdata_dist` | `logger` | **`_time_second_`** | `createTime` | `_time_nanosecond_` | 含 `sendDoDispatcherTime` / `parseTime` / `listenTime` / `allFinishTime` |
| `data_sync_log_dist` | `logger` | **`_time_second_`** | `createTime` | `_time_nanosecond_` | TTL 90 天 |
| `log_cep_dist` | `logger` | **`stamp`** | `stamp` | `_time_nanosecond_` | 唯一强制 `stamp` 的网关全量表；`PARTITION BY toYYYYMMDD(stamp)` |
| `tomcat_access_dist` | `logger` | **`_time_second_`** | `_time_second_` | `_time_nanosecond_` | **禁止**黑名单列 `time_for_ckibana`；空 uid 可能为 `'-'` |
| `erp_sync_monitor_dist` | `logger` | **`_time_second_`** | `createTime` | `_time_nanosecond_` | 通道健康度 |
| `biz_log_erp_ipaas_log_dist` | `erp_sync` | **`createTime`** | `startTime` / `endTime` / `updateTime` | 无 | **无 `_time_second_`**；分区 **`toYYYYMM(createTime)`**（按月） |
| `biz_log_erp_ipaas_probe_log_dist` | `erp_sync` | **`createTime`** | `execTime` / `startTime` / `endTime` | 无 | **无 `_time_second_`**、**无 `traceId`**；分区 `toYYYYMMDD(createTime)` |
| `biz_log_erp_sync_log_dist` | `erp_sync` | **`createTime`** | `callTime` / `returnTime`（Int64 ms）/ `updateTime` | 无 | **无 `_time_second_`**；无 `rpcId`/`spanId` |
| `mt_udef_function`（PG，非 CK） | `paas` | **`last_modified_time`** (`bigint`) | **`create_time`** (`bigint`) | 无 | 有效版本必须 `is_current = true AND is_deleted = false`；走 `idp query paas` |

PG 函数定义表不在 `biz-app-log`。ClickHouse 函数执行日志是 `biz_log_function_dist`。

---

## 四、 出站 HTTP 与集成取证标准 SQL

出站 HTTP 与集成取证的标准 SQL。单表字段见 [egress-log.md](./egress-log.md)、[openapi-log.md](./openapi-log.md)、[erp-sync.md](./erp-sync.md)。

### A. 出站 HTTP（平台出口 Nginx）

`egress_nginx_access_dist` **无** `tenantId` / `trace_id` / `uri`。过滤 `host` + `_time_second_`。路径列是 `request_url`。

```sql
SELECT _time_second_, host, method, request_url, status, request_time,
       connect_host, connect_addr, proxy_connect_time, bytes_sent
FROM egress_nginx_access_dist
WHERE _time_second_ >= '<START>' AND _time_second_ <= '<END>'
  AND host = '<EXTERNAL_HOST>'
ORDER BY _time_second_ DESC
LIMIT 50
```

### B. 入站 OpenAPI（外部调入）

```sql
SELECT _time_second_, createTime, ei, ea, appId, apiName, openApiUrl,
       cost, errorType, openApiErrorCode, traceId
FROM biz_log_openapi_dist
WHERE ei = '<EI>'
  AND _time_second_ >= '<START>' AND _time_second_ <= '<END>'
ORDER BY _time_second_ DESC
LIMIT 50
```

### C. iPaaS 2.0 集成流结束态

```sql
SELECT createTime, startTime, endTime, tenantId, traceId, workflowInstanceId,
       flowApiName, flowVersion, dataId, endState, remark, cost, nodeLogs
FROM biz_log_erp_ipaas_log_dist
WHERE tenantId = '<EI>'
  AND createTime >= '<START>' AND createTime <= '<END>'
ORDER BY createTime DESC
LIMIT 50
```

### D. ERP 吞吐 / 分阶段耗时

```sql
SELECT _time_second_, tenantId, ea, sourceObjApiName, sourceDataId,
       allCost, syncCost, writeCost, processCost,
       sendDoDispatcherTime, parseTime, listenTime, allFinishTime,
       throwable, throwableMsg, traceId
FROM biz_log_erpsyncdata_dist
WHERE tenantId = '<EI>'
  AND _time_second_ >= '<START>' AND _time_second_ <= '<END>'
ORDER BY _time_second_ DESC
LIMIT 50
```

### E. ERP Sync 1.0 全链路

```sql
SELECT createTime, tenantId, traceId, objApiName, sourceObjectApiName,
       destObjectApiName, syncDataStatus, errorCode, costTime, id
FROM biz_log_erp_sync_log_dist
WHERE tenantId = '<EI>'
  AND createTime >= '<START>' AND createTime <= '<END>'
ORDER BY createTime DESC
LIMIT 50
```

---

## 五、 常用诊断标准 SQL 模板库

### 1. 单 TraceID 错误堆栈检索 (`log_error_dist`)
```sql
SELECT _time_second_, app, pod, serverIp, loggerName, msg, substring(error, 1, 1000) AS stack_trace
FROM log_error_dist
WHERE traceId = '<TRACE_ID>'
  AND _time_second_ BETWEEN '<START_TIME>' AND '<END_TIME>'
ORDER BY _time_second_ DESC
LIMIT 20;
```

### 2. 网关 CEP 错误码 / reqId 反查 TraceID (`log_cep_dist`)
```sql
SELECT stamp, companyName, ei, ea, bizName, status, errorCode, error, uri2, traceId, reqId
FROM log_cep_dist
WHERE has(reqId, '<ERROR_CODE_OR_REQ_ID>')
  AND stamp BETWEEN '<TIME_MINUS_10M>' AND '<TIME_PLUS_10M>'
ORDER BY status DESC, stamp DESC
LIMIT 10;
```

### 3. 应用日志明细与 StopWatch 耗时下钻 (`app_log_dist`)
```sql
SELECT _time_second_, app, pod, level, logger, msg, traceId
FROM app_log_dist
WHERE app = '<APP_NAME>'
  AND traceId = '<TRACE_ID>'
  AND _time_second_ BETWEEN '<START_TIME>' AND '<END_TIME>'
ORDER BY _time_second_ ASC
LIMIT 50;
```

### 4. 数据库慢 SQL 检索 (`slow_log_dist`)
```sql
SELECT _time_second_, dbName, cost, substring(query, 1, 500) AS sql_text, traceId, ei, ea
FROM slow_log_dist
WHERE cost >= 1000  -- 耗时 >= 1000ms
  AND _time_second_ BETWEEN '<START_TIME>' AND '<END_TIME>'
ORDER BY cost DESC
LIMIT 20;
```

### 5. APL 自定义函数执行日志检索 (`biz_log_function_dist`)
```sql
SELECT _time_second_, tenantId, apiName, cost, errorCode, traceId
FROM biz_log_function_dist
WHERE traceId = '<TRACE_ID>'
  AND _time_second_ BETWEEN '<START_TIME>' AND '<END_TIME>'
ORDER BY _time_second_ DESC
LIMIT 10;
```

---

## 六、 快速校验命令

在编写复杂的 SQL 之前，如对字段名存在隐患，强制运行下述命令确认实时 Schema：

```bash
fx-ops idp --profile <profile> show columns biz-app-log <table_name> -j
```
