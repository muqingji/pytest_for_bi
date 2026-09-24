# log-cep

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: CEP 网关访问日志，记录经过 CEP 网关的所有 API 请求，包括客户端信息、请求路径、响应状态、地理位置、服务端信息等。是全量 API 网关访问日志的核心表。

**租户ID字段**: `ei`, `ea`

**时间字段**: stamp

---

## 表：log_cep_dist

**说明**: CEP 网关访问日志，记录经过 CEP 网关的所有 API 请求，包括客户端信息、请求路径、响应状态、地理位置、服务端信息等。是全量 API 网关访问日志的核心表。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'log_cep', rand(); Distributed('cluster01', 'logger', 'log_cep', rand() |
| PARTITION BY | `toYYYYMMDD(stamp)` |
| PRIMARY KEY | `(biz, bizName, stamp)` |
| ORDER BY | `(biz, bizName, stamp)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(366)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志写入时间（纳秒级） |
| `_time_second_` | DateTime('Asia/Shanghai') | 日志写入时间（秒级） |
| `biz` | LowCardinality(String) | 业务分类标识 |
| `bizName` | LowCardinality(String) | 业务分类名称 |
| `clickId` | String | 点击/埋点 ID |
| `client_ip` | IPv4 | 客户端 IP |
| `client_ip_city` | LowCardinality(String) | 客户端 IP - 城市 |
| `client_ip_country` | LowCardinality(String) | 客户端 IP - 国家 |
| `client_ip_province` | LowCardinality(String) | 客户端 IP - 省份 |
| `cluster` | String | K8s 集群 |
| `companyName` | String | 企业名称 |
| `device_id` | String | 设备 ID |
| `ea` | String | 租户账号 |
| `ei` | String | 租户 ID |
| `error` | String | 错误信息 |
| `errorCode` | String | 错误码 |
| `gate_ip` | IPv4 | 网关 IP |
| `grayConfigs` | Array(String) | 灰度配置 |
| `ip_city` | LowCardinality(String) | IP - 城市 |
| `ip_country` | LowCardinality(String) | IP - 国家 |
| `ip_province` | LowCardinality(String) | IP - 省份 |
| `lang` | LowCardinality(String) | 语言标识 |
| `location` | String | 路由匹配规则 |
| `locationRateLimitAllowedFlag` | Nullable(Int32) | 地域限流放行标识 |
| `operate` | String | 操作类型 |
| `os_version` | LowCardinality(String) | 操作系统版本 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID，标识发起当前 span 的上游 span；根 span 或缺失上游时通常为空 |
| `platform` | Int32 | 平台标识（1103=Web 等） |
| `product_version` | LowCardinality(String) | 产品版本 |
| `profile` | String | 环境标识（K8s namespace / cms_profile） |
| `rateLimitAllowed` | Int32 | 限流放行标识 |
| `remote_addr` | String | 远端地址 |
| `reqId` | Array(String) | 请求 ID 列表 |
| `request_length` | Int32 | 请求体大小 |
| `request_time` | Int32 | 请求耗时（ms） |
| `requestMaliciousInterceptFlag` | Nullable(Int32) | 恶意请求拦截标识 |
| `response_length` | Int32 | 响应体大小 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `server_ip` | String | 服务端 IP:Port |
| `server_name` | LowCardinality(String) | 后端服务名称 |
| `server_namespace` | LowCardinality(String) | 后端服务命名空间 |
| `serverName` | LowCardinality(String) | 服务名称 |
| `service_type` | LowCardinality(String) | 服务类型 |
| `spanId` | String | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 traceId 组合可定位链路中的单个节点 |
| `stamp` | DateTime64(3, 'Asia/Shanghai') | 请求时间戳 |
| `status` | Int32 | HTTP 响应状态码 |
| `traceId` | String | 链路追踪 ID |
| `uid` | String | 用户 ID（格式：ea.userId） |
| `unknownError` | Bool | 是否未知错误 |
| `uri` | String | 完整请求 URI |
| `uri2` | LowCardinality(String) | 对 URI 做聚合和规范化处理后的路径；进行统计分析或筛选过滤时优先使用 uri2 |
| `user_agent` | LowCardinality(String) | 用户代理 |
| `version_name` | LowCardinality(String) | 版本名称 |
| `x_forwarded_for` | Array(IPv4) | X-Forwarded-For 链 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `uid` |
| 追踪ID | `traceId` |
| 请求ID | `reqId` |
| 时间 | `stamp` |

### 查询示例

RCA 默认投影（时间列是 **`stamp`**，不是 `_time_second_`；列名以字段定义为准）：

```bash
# 按 traceId + stamp 时间窗锁定入口行
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT traceId, stamp, bizName, uri, status, errorCode, error, reqId, ei, ea, request_time, server_name, server_ip, profile FROM log_cep_dist WHERE traceId = '<traceId>' AND stamp >= '<T0>' AND stamp <= '<T1>' ORDER BY stamp DESC LIMIT 50" -j
```

按租户 + 时间查（命中排序键 `biz/bizName/stamp`）：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, ei, ea, bizName, uri, status, request_time, traceId FROM log_cep_dist WHERE ei = '123' AND stamp > '2024-01-01' LIMIT 20" -j
```

按 CEP 错误码（`reqId` 数组）反查真实 traceId：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, ea, ei, bizName, uri, status, errorCode, error, traceId, reqId, request_time FROM log_cep_dist WHERE has(reqId, '15-84f875') AND stamp BETWEEN '<T-5min>' AND '<T+5min>' ORDER BY status DESC, request_time DESC LIMIT 20" -j
```

> - `reqId` 是 `Array(String)`：必须用 `has(reqId, '<code>')`，写成 `reqId = '<code>'` 会报类型错误。
> - `status` 是 `Int32`：用数值比较 `status >= 500`；`request_time` 单位为毫秒。

### URI / 路径查询（红线）

> 通用避坑见 `references/idp-query-clickhouse.md` §9。主键是 **`(biz, bizName, stamp)`**，**不是** `uri`；裸 `uri LIKE '%…%'` 会在 stamp 窗内扫大量业务。

1. **优先** `bizName`（或 `biz`）+ `stamp` 时间窗；有租户再带 `ei`/`ea`。
2. 路径优先 **`uri2` 等值**（LowCardinality 归一化路径）；仅知道片段时用 `position(uri, '…') > 0`。
3. **禁止**无 `bizName`/租户的数小时窗 + `uri LIKE '%…%'`。
4. 长窗 URI 失败/慢趋势优先 `cep_minute_dist` / `cep_daily_dist`（PK 含 `uri2`），再下钻本表。

```sql
-- ✅ 推荐：排序键 + uri2 等值
SELECT stamp, ei, ea, bizName, uri, uri2, status, request_time, traceId, reqId
FROM log_cep_dist
WHERE bizName = '<BIZNAME>'
  AND stamp >= '<T0>'
  AND stamp <= '<T1>'
  AND uri2 = '/FHH/EM1ANCRM/xxx'
  AND status >= 500
ORDER BY stamp DESC
LIMIT 100

-- ⚠️ 仅路径片段：缩窗 + 租户/biz + position
SELECT stamp, bizName, uri, uri2, status, request_time, traceId
FROM log_cep_dist
WHERE stamp >= '<T0>'
  AND stamp <= '<T1>'
  AND (ei = '<EI>' OR ea = '<EA>')
  AND position(uri, '/inner/rag/retrieval') > 0
ORDER BY stamp DESC
LIMIT 50
```

长窗趋势（聚合表，避免扫全量 CEP）：

```sql
SELECT stamp, bizName, uri2, totalCount, failCount, slowCount
FROM cep_minute_dist
WHERE bizName = '<BIZNAME>'
  AND stamp BETWEEN '<T-1h>' AND '<T+30m>'
  AND uri2 = '/path/to/api'
ORDER BY stamp
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
