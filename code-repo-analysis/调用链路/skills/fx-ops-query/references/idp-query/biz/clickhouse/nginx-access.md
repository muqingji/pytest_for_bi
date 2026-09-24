# nginx-access

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: Nginx 反向代理访问日志分布式表，记录前端主入口 Nginx 代理的 HTTP 请求报文、耗时和状态码。

**租户ID字段**: `ea`

**时间字段**: _time_second_

---

## 表：nginx_access_dist

**说明**: Nginx 反向代理访问日志分布式表，记录前端主入口 Nginx 代理的 HTTP 请求报文、耗时和状态码。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster03', 'logger', 'nginx_access_local', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(ei, ea, _time_second_)` |
| ORDER BY | `(ei, ea, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(180)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 事件写入 ClickHouse 的秒级时间戳 |
| `app` | String | 应用名称，通常指运行的微服务名称，例如 fs-uc-provider |
| `biz` | String | 业务标识 |
| `bizName` | String | 业务名称 |
| `body_bytes_sent` | Int64 | 响应体字节数 |
| `companyName` | String | 企业名称 |
| `content_length` | Int64 | 请求内容长度 |
| `content_type` | String | 请求内容类型 |
| `ea` | String | 企业账号/租户账号名称 |
| `ei` | String | 企业唯一标识 ID (Enterprise ID) |
| `gate_ip` | String | 网关IP地址 |
| `host_ip` | Nullable(String) | 主机IP地址 |
| `http_referer` | String |  |
| `http_version` | String | HTTP协议版本 |
| `http_x_fs_trace_id` | String |  |
| `more` | String | 扩展信息 |
| `parameters` | String | 请求参数 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `path` | Nullable(String) | 请求路径 |
| `remote_addr` | String | 客户端远程IP地址 |
| `reqId` | String | 请求id |
| `request_length` | Int64 | 请求length |
| `request_method` | String | 请求method |
| `request_time` | Float64 | 请求耗时（秒） |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `sent_length` | Int64 | 发送长度 |
| `sent_type` | String | 发送类型 |
| `spanId` | String | OpenTelemetry Span ID |
| `ssl_protocol` | String |  |
| `status` | Int16 | 状态码或状态标识（如 200, 500, 或 SUCCESS, FAILED） |
| `traceId` | String | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `upstream_addr` | String | 上游服务地址 |
| `upstream_response_length` | Int64 | upstream响应length |
| `upstream_response_time` | Float64 | upstream响应time |
| `upstream_status` | Int16 | 上游服务状态码 |
| `uri` | String | HTTP 请求的 URI 路径 |
| `uri2` | String | 对 URI 做聚合和规范化处理后的路径；进行统计分析或筛选过滤时优先使用 uri2 |
| `user_agent` | String | 客户端用户代理 |
| `user_id` | String | 操作用户的唯一标识 ID |
| `x_forwarded_for` | Nullable(String) | 代理转发IP链 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `user_id` |
| 追踪ID | `traceId` |
| 请求ID | `reqId` |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查询近1小时Nginx 5xx错误
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, ei, uri, status, request_time, upstream_status, upstream_response_time FROM nginx_access_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND status >= 500 ORDER BY _time_second_ DESC LIMIT 50"

# 按URI统计请求量TOP20
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT uri, COUNT(*) as cnt, avg(request_time) as avg_rt, max(request_time) as max_rt FROM nginx_access_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY uri ORDER BY cnt DESC LIMIT 20"

# 查询慢请求（>3秒）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, ei, uri, request_time, upstream_addr, status, traceId FROM nginx_access_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND request_time > 3 ORDER BY request_time DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
