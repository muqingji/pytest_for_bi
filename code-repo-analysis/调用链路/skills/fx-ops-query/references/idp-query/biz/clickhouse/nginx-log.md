# nginx-log（Nginx日志）

> schema_verified_at: 2026-08-01 | platform: v5.10.0
> [!WARNING]
> **已废弃 / 不可查询**：platform v4.37.0 已将 `nginx_log_dist` 从 tenant-filters 移除（variant `all_inactive` / scan 排除）。请改用 [nginx-access.md](./nginx-access.md)。

**说明**: Nginx 访问日志表，记录 HTTP 请求的详细信息

**租户ID字段**: `ei`

**时间字段**: `_time_second_`

---

## 表：nginx_log_dist

### 存储与索引

| 项 | 值 |
| --- | --- |
| 状态 | **已废弃**，platform 无 `nginx_log_dist.yaml` |

### 字段定义（历史参考，勿查询）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 日志采集时间 |
| `app` | String | 应用名称 |
| `biz` | String | 业务标识 |
| `bizName` | String | 业务名称 |
| `body_bytes_sent` | Float64 | 响应体大小（字节） |
| `companyName` | String | 企业名称 |
| `content_length` | String | Content-Length 头 |
| `content_type` | String | Content-Type 头 |
| `ea` | String | 租户账号 |
| `ei` | String | 租户ID |
| `gate_ip` | String | 网关 IP |
| `http_version` | String | HTTP 协议版本 |
| `more` | String | 扩展信息 |
| `parameters` | String | 请求参数 |
| `remote_addr` | String | 客户端 IP |
| `reqId` | String | 请求唯一 ID |
| `request_method` | String | HTTP 方法（GET/POST 等） |
| `request_time` | Float64 | 请求耗时（秒） |
| `request_length` | Float64 | 请求体大小（字节） |
| `sent_length` | Float64 | 发送数据大小（字节） |
| `sent_type` | String | 发送数据类型 |
| `status` | Int32 | HTTP 状态码 |
| `traceId` | String | 链路追踪 ID |
| `upstream_addr` | String | 上游服务器地址 |
| `upstream_response_length` | Float64 | 上游响应大小（字节） |
| `upstream_response_time` | Float64 | 上游响应耗时（秒） |
| `upstream_status` | String | 上游 HTTP 状态码 |
| `uri` | String | 请求 URI |
| `uri2` | String | 简化 URI（去掉路径参数） |
| `user_agent` | String | User-Agent |
| `user_id` | String | 用户ID |
| `http_x_fs_trace_id` | String | 自定义追踪 ID 头 |
| `http_referer` | String | Referer 头 |
| `host_ip` | String | 主机 IP |
| `x_forwarded_for` | String | X-Forwarded-For 头 |
| `ssl_protocol` | String | SSL 协议版本 |
| `path` | String | 请求路径 |
| `rpcId` | String | RPC 调用ID |
| `spanId` | String | Span ID |
| `parentSpanId` | String | 父 Span ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 业务名称 | `bizName` |
| 链路追踪 | `traceId` |
| 请求ID | `reqId` |
| 时间 | `_time_second_` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, request_method, uri, status, request_time, upstream_response_time FROM nginx_log_dist WHERE ei = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20"

# 查上游 5xx 错误
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, uri, status, upstream_status, upstream_addr, upstream_response_time FROM nginx_log_dist WHERE ei = '123' AND upstream_status >= '500' AND _time_second_ >= now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
