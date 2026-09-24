# tomcat-access-slow

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: Tomcat 慢请求日志分布式表（与 tomcat_access_slow 孪生，列同构）。Open/SQL 可用名：tomcat_access_slow 与 tomcat_access_slow_dist。查询须带 _time_second_ 时间窗（≤24h）并优先过滤 app/profile。

**租户ID字段**: `ei`, `ea`

**时间字段**: _time_second_

---

## 表：tomcat_access_slow_dist

**说明**: Tomcat 慢请求日志分布式表（与 tomcat_access_slow 孪生，列同构）。Open/SQL 可用名：tomcat_access_slow 与 tomcat_access_slow_dist。查询须带 _time_second_ 时间窗（≤24h）并优先过滤 app/profile。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | — |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(app, profile, _time_second_)` |
| ORDER BY | `(app, profile, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(60)` |
| 跳数/二级索引 | **INDEX**: `idx_trace_id`: trace_id TYPE set(10000), GRANULARITY 8; `idx_msg`: uri TYPE ngrambf_v1(3, 256, 2, 0) GRANULARITY 4, INDEX idx_caller caller TYPE set(1000), GRANULARITY 5; `idx_ea`: ea TYPE set(10000), GRANULARITY 8; `idx_uri`: uri TYPE tokenbf_v1(256, 2, 0) GRANULARITY 5, INDEX idx_code code TYPE set(10), GRANULARITY 3; `idx_req_cost`: time_cost TYPE minmax, GRANULARITY 5; `idx_res_size`: bytes_sent TYPE minmax, GRANULARITY 5 |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 请求时间（秒级；排序键前缀之一。查询须带时间窗，timeGuard≤24h） |
| `app` | String | 服务/应用名（K8s Deployment 名；慢查/聚合优先等值过滤） |
| `bytes_sent` | Int64 | 响应体字节数 |
| `caller` | String | 上游调用方服务名（"-" 表示未知） |
| `cluster` | Nullable(String) | K8s 集群标识 |
| `code` | Int16 | HTTP 状态码（200/4xx/5xx） |
| `company_name` | String | 企业名称（可能为空字符串） |
| `company_status` | String | 企业状态（可能为空字符串） |
| `ea` | String | 租户账号（企业账号；空或 "-" 表示未解析到租户） |
| `ei` | String | 租户 ID（企业 ID；空或 "-" 表示未解析到租户） |
| `method` | String | HTTP 方法（GET/POST/PUT/DELETE 等） |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `pod` | String | 处理请求的 Pod 名称 |
| `pod_ip` | IPv4 | 处理请求的 Pod IP |
| `profile` | String | 部署环境标识（与 app 同属排序键前缀，等值过滤可显著剪枝） |
| `protocol` | String | HTTP 协议版本（多为 HTTP/1.1） |
| `remote_host` | String | 远端主机 IP（常与 x_real_ip 一致或为直连对端） |
| `request_size` | Int64 | 请求体大小（字节） |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `spanId` | String | OpenTelemetry Span ID |
| `time_cost` | Int32 | 服务端处理耗时（毫秒）。本表仅含超过慢阈值的请求 |
| `time_for_ckibana` | DateTime | 查询黑名单列（物理存在，**禁止** SELECT/WHERE；时间过滤一律用 `_time_second_`） |
| `trace_id` | String | 链路追踪 ID（过滤优先本列；有 skip index）。与 traceId 驼峰列内容通常一致 |
| `traceId` | Nullable(String) | trace_id 的驼峰别名列（可空；过滤优先 trace_id） |
| `uid` | String | 用户标识（常见 {ea}.{uid}；未登录/系统调用可能为空） |
| `uri` | String | 原始请求 URI（可含 path + query；精确排查用） |
| `uri2` | String | 对 URI 做聚合和规范化处理后的路径；进行统计分析或筛选过滤时优先使用 uri2 |
| `x_forwarded_for` | String | X-Forwarded-For 头；链路代理 IP，"-" 表示缺失 |
| `x_real_ip` | String | X-Real-IP 头（常为入口侧客户端/上一跳 IP） |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 租户账号 | `ea` |
| 用户ID | `uid` |
| 追踪ID | `trace_id` |
| 时间 | `_time_second_` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, profile, app, ei, ea, trace_id, uri, code, time_cost FROM tomcat_access_slow_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
