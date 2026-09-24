# kpi-cep

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: CEP 网关 KPI 明细表，记录错误/异常请求的完整链路信息，包含请求详情、客户端信息、服务端信息及分布式追踪数据。

**租户ID字段**: `ea`

**时间字段**: stamp, _time_second_

---

## 表：kpi_cep

**说明**: CEP 网关 KPI 明细表，记录错误/异常请求的完整链路信息，包含请求详情、客户端信息、服务端信息及分布式追踪数据。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_sla', 'kpi_cep_local', rand()) |
| PARTITION BY | `toYYYYMMDD(stamp)` |
| PRIMARY KEY | `(biz, bizName, stamp)` |
| ORDER BY | `(biz, bizName, stamp)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(366)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `stamp`, `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `stamp` | DateTime64(3, 'Asia/Shanghai') | 请求时间（毫秒精度） |
| `companyName` | String | 公司名称 |
| `ea` | String | 企业账号名称 |
| `ei` | String | 企业 ID |
| `biz` | LowCardinality(String) | 业务编码 |
| `bizName` | LowCardinality(String) | 业务名称 |
| `status` | Int32 | HTTP 状态码 |
| `unknownError` | Bool | 是否未知错误 |
| `error` | String | 错误信息 |
| `errorCode` | String | 错误码 |
| `uid` | String | 用户 ID |
| `uri2` | LowCardinality(String) | 对 URI 做聚合和规范化处理后的路径；进行统计分析或筛选过滤时优先使用 uri2 |
| `uri` | String | 原始 URI 路径 |
| `request_time` | Int32 | 请求耗时（毫秒） |
| `request_length` | Int32 | 请求体大小（字节） |
| `response_length` | Int32 | 响应体大小（字节） |
| `traceId` | String | 分布式链路追踪 ID |
| `reqId` | Array(String) | 请求 ID 列表 |
| `gate_ip` | IPv4 | 网关 IP 地址 |
| `server_ip` | String | 服务端 IP 地址 |
| `client_ip` | IPv4 | 客户端 IP 地址 |
| `remote_addr` | String | 远程地址 |
| `x_forwarded_for` | Array(IPv4) | X-Forwarded-For 代理链 |
| `platform` | Int32 | 平台标识 |
| `user_agent` | LowCardinality(String) | 客户端 User-Agent |
| `version_name` | LowCardinality(String) | 版本名称 |
| `os_version` | LowCardinality(String) | 操作系统版本 |
| `product_version` | LowCardinality(String) | 产品版本 |
| `service_type` | LowCardinality(String) | 服务类型 |
| `serverName` | LowCardinality(String) | 服务名称 |
| `device_id` | String | 设备 ID |
| `grayConfigs` | Array(String) | 灰度配置列表 |
| `_time_second_` | DateTime('Asia/Shanghai') | 写入秒级时间戳 |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 写入纳秒级时间戳 |
| `client_ip_country` | LowCardinality(String) | 客户端 IP 国家 |
| `client_ip_province` | LowCardinality(String) | 客户端 IP 省份 |
| `client_ip_city` | LowCardinality(String) | 客户端 IP 城市 |
| `ip_country` | LowCardinality(String) | 服务端 IP 国家 |
| `ip_province` | LowCardinality(String) | 服务端 IP 省份 |
| `ip_city` | LowCardinality(String) | 服务端 IP 城市 |
| `server_name` | LowCardinality(String) | 服务端主机名 |
| `server_namespace` | LowCardinality(String) | 服务端命名空间 |
| `lang` | LowCardinality(String) | 请求语言 |
| `operate` | String | 操作描述 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `spanId` | String | OpenTelemetry Span ID |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `uid` |
| 追踪ID | `traceId` |
| 请求ID | `reqId` |
| 时间 | `stamp`, `_time_second_` |

### 查询示例

按企业账号 + 时间查 KPI 异常样本：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, ea, ei, bizName, uri, status, errorCode, error, request_time, traceId, reqId FROM kpi_cep WHERE ea = '<EA>' AND stamp >= now() - INTERVAL 1 HOUR AND status >= 500 ORDER BY stamp DESC LIMIT 50"
```

按 CEP 错误码反查：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, ea, bizName, uri, status, error, traceId, reqId FROM kpi_cep WHERE has(reqId, '15-84f875') AND stamp BETWEEN '<T-5min>' AND '<T+5min>' ORDER BY stamp DESC LIMIT 20"
```

按 bizName 统计近 1 小时 5xx：

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT bizName, count() AS cnt, avg(request_time) AS avg_ms FROM kpi_cep WHERE stamp >= now() - INTERVAL 1 HOUR AND status >= 500 GROUP BY bizName ORDER BY cnt DESC LIMIT 20"
```

> - `reqId` 是 `Array(String)`：必须 `has(reqId, '<code>')`。
> - `status` 是 `Int32`：数值比较；`request_time` 单位毫秒。
> - 表名是 **`kpi_cep`**（无 `_dist` 后缀），SQL 写 `FROM kpi_cep`。

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
