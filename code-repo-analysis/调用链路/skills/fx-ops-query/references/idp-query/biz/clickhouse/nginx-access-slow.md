# nginx-access-slow

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: Nginx慢访问日志表，记录响应时间超阈值的HTTP请求详情，包含客户端、服务端、链路追踪及业务维度的信息

**租户ID字段**: `ei`

**时间字段**: _time_second_

---

## 表：nginx_access_slow_dist

**说明**: Nginx慢访问日志表，记录响应时间超阈值的HTTP请求详情，包含客户端、服务端、链路追踪及业务维度的信息

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster04', 'logger', 'nginx_access_slow_local', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(ei, ea, _time_second_)` |
| ORDER BY | `(ei, ea, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(180)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 事件写入ClickHouse的秒级时间戳 |
| `app` | String | 应用名称 |
| `biz` | String | 业务线标识 |
| `bizName` | String | 业务线名称 |
| `body_bytes_sent` | Int64 | 响应体发送字节数 |
| `companyName` | String | 公司名称 |
| `content_length` | Int64 | 请求体内容长度 |
| `content_type` | String | 请求内容类型 |
| `ea` | String | 企业账号(Enterprise Account) |
| `ei` | String | 企业ID |
| `gate_ip` | String | 网关IP地址 |
| `http_version` | String | HTTP协议版本 |
| `more` | String | 扩展信息 |
| `parameters` | String | 请求参数 |
| `remote_addr` | String | 客户端远程地址 |
| `reqId` | String | 请求ID |
| `request_method` | String | HTTP请求方法 |
| `request_time` | Float64 | 请求响应总时间（秒） |
| `sent_length` | Int64 | 发送数据长度 |
| `sent_type` | String | 发送数据类型 |
| `status` | Int16 | HTTP状态码 |
| `traceId` | String | 分布式链路追踪ID |
| `upstream_addr` | String | 上游服务地址 |
| `upstream_response_length` | Int64 | 上游响应长度 |
| `upstream_response_time` | Float64 | 上游响应时间（秒） |
| `upstream_status` | Int16 | 上游HTTP状态码 |
| `uri` | String | 请求URI |
| `uri2` | String | 次要请求URI |
| `user_agent` | String | 客户端User-Agent |
| `user_id` | String | 用户ID |
| `http_x_fs_trace_id` | Nullable(String) | 自定义链路追踪请求头 |
| `request_length` | Int64 | 请求长度 |
| `http_referer` | Nullable(String) | HTTP来源页面 |
| `host_ip` | Nullable(String) | 主机IP地址 |
| `x_forwarded_for` | Nullable(String) | X-Forwarded-For请求头 |
| `ssl_protocol` | Nullable(String) | SSL协议版本 |
| `path` | Nullable(String) | 请求路径 |
| `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `spanId` | Nullable(String) | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 traceId 组合可定位链路中的单个节点 |
| `parentSpanId` | Nullable(String) | OpenTelemetry 父 Span ID，标识发起当前 span 的上游 span；根 span 或缺失上游时通常为空 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `user_id` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查询近1小时最慢的Nginx请求
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, ei, uri, request_time, upstream_response_time, status, traceId FROM nginx_access_slow_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY request_time DESC LIMIT 20"

# 按租户统计慢请求
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT ei, COUNT(*) as cnt, avg(request_time) as avg_rt FROM nginx_access_slow_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY ei ORDER BY cnt DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
