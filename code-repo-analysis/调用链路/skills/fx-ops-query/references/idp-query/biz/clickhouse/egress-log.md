# egress-log（出口日志）

> schema_verified_at: 2026-08-01 | platform: v5.10.0

覆盖：

1. **`egress_nginx_access_dist`**：HTTP 出口 Nginx 代理访问日志
2. **`egress_sms_dist_tbl`**：短信发送日志（租户字段 `tenantId`）

---

## 表：egress_nginx_access_dist

**说明**: 出口 Nginx 代理访问日志分布式表，记录经过平台出口反向代理向外部系统发起请求的请求信息与响应。

**租户ID字段**: **无**（不能按 `tenantId` / `trace_id` 过滤）

**时间字段**: `_time_second_`

**主键/排序**: `(host, _time_second_)` — 过滤优先带 `host`

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'egress_nginx_access_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(host, _time_second_)` |
| ORDER BY | `(host, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(30)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3) | 事件写入 ClickHouse 的秒级时间戳 |
| `bytes_sent` | Int64 | 发送字节数 |
| `cluster` | String | K8s 集群 |
| `connect_addr` | String | 连接目标地址 |
| `connect_host` | String | 连接目标主机 |
| `host` | String | 请求目标主机 |
| `http_version` | String | HTTP协议版本 |
| `method` | String | HTTP 请求方法（如 GET, POST）或调用方法 |
| `proxy_connect_time` | String | 代理连接耗时 |
| `remote_addr` | IPv4 | 客户端远程IP地址 |
| `request_length` | Int64 | 请求length |
| `request_time` | Float32 | 请求耗时（秒） |
| `request_url` | String | 请求url |
| `status` | Int16 | 状态码或状态标识（如 200, 500, 或 SUCCESS, FAILED） |
| `user_agent` | String | 客户端用户代理 |
| `x_peer_name` | String |  |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_` |

### 字段定义（实查 15 列）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3) | 入库秒级时间（WHERE 用） |
| `time_iso8601` | String | 事件时间字符串 |
| `host` | String | 请求目标主机（PK 前缀） |
| `remote_addr` | IPv4 | 客户端远程 IP |
| `method` | String | HTTP 方法 |
| `request_url` | String | 请求 URL（**无 `uri` 列**） |
| `http_version` | String | HTTP 版本 |
| `status` | Int16 | 状态码 |
| `request_time` | Float32 | 请求耗时 |
| `request_length` | Int64 | 请求长度 |
| `bytes_sent` | Int64 | 发送字节数 |
| `user_agent` | String | UA |
| `connect_host` | String | 连接目标主机 |
| `connect_addr` | String | 连接目标地址 |
| `proxy_connect_time` | String | 代理连接耗时 |

> **无** `profile` / `uri` / `tenantId` / `trace_id` / `upstream_status` / `upstream_response_time`。

### 查询示例

出站 HTTP 取证标准模板（无租户列，必须 `host` + `_time_second_`）：

```sql
SELECT _time_second_, host, method, request_url, status, request_time,
       connect_host, connect_addr, proxy_connect_time, bytes_sent
FROM egress_nginx_access_dist
WHERE _time_second_ >= '<START>' AND _time_second_ <= '<END>'
  AND host = '<EXTERNAL_HOST>'
ORDER BY _time_second_ DESC
LIMIT 50
```

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, host, method, request_url, status, request_time, connect_host, proxy_connect_time FROM egress_nginx_access_dist WHERE _time_second_ >= '{fromTime}' AND _time_second_ <= '{toTime}' AND host = '{externalHost}' LIMIT 20" -j --pretty
```

---

## 表：egress_sms_dist_tbl

**说明**: 短信发送日志，记录所有通过短信网关发出的短信，包括手机号、短信内容、发送状态、供应商信息等。用于短信发送追踪和故障排查。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'egress_sms_local', rand(); Distributed('cluster01', 'logger', 'egress_sms_local', rand() |
| PARTITION BY | — |
| PRIMARY KEY | `(phone, msgId)` |
| ORDER BY | `(phone, msgId)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(730)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 日志写入时间（秒级） |
| `stamp` | DateTime64(3, 'Asia/Shanghai') | 短信发送时间戳 |
| `phone` | String | 目标手机号 |
| `message` | String | 短信内容 |
| `tenantId` | String | 租户 ID |
| `smsType` | String | 短信类型（如 NOTIFICATION） |
| `providerId` | String | 短信供应商 ID |
| `providerName` | String | 短信供应商名称 |
| `bizName` | String | 业务名称 |
| `sendSuccess` | String | 发送是否成功（true/false） |
| `intl` | String | 是否国际短信（true/false） |
| `error` | String | 错误信息 |
| `msgId` | String | 短信消息 ID |
| `serialId` | String | 序列号 |
| `enc` | String | 加密内容 |
| `replyStatus` | String | 回复状态 |
| `replyCode` | String | 回复代码 |
| `replyMessage` | String | 回复消息 |
| `profile` | LowCardinality(String) | 环境标识 |
| `serverIp` | String | 服务端 IP |
| `smsLength` | Int64 | 短信长度 |
| `smsSize` | Int64 | 短信条数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 时间 | `_time_second_`, `stamp` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM egress_sms_dist_tbl WHERE tenantId = '123' AND _time_second_ > '2024-01-01' LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
