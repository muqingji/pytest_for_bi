# tomcat-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: Tomcat 访问日志分布式表，记录 HTTP 请求的完整访问日志，包括请求方法、URI、状态码、耗时、请求/响应大小、链路追踪信息等，用于接口性能分析和问题排查。

**租户ID字段**: `ei`, `ea`

**时间字段**: `_time_second_`（分区/主过滤）。**禁止**查询黑名单列 `time_for_ckibana`（物理存在，不得 SELECT/WHERE）。

---

## 表：tomcat_access_dist

**说明**: Tomcat 访问日志分布式表，记录 HTTP 请求的完整访问日志，包括请求方法、URI、状态码、耗时、请求/响应大小、链路追踪信息等，用于接口性能分析和问题排查。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster03', 'logger', 'tomcat_access_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(app, profile, _time_second_)` |
| ORDER BY | `(app, profile, _time_second_)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(7)` |
| 跳数/二级索引 | **INDEX**: `idx_rpc_id`: rpc_id TYPE bloom_filter(0.025), GRANULARITY 8 |
| 时间列（查询） | `_time_second_`（**禁止** `time_for_ckibana`） |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(3, 'Asia/Shanghai') | 更高精度时间戳（毫秒/纳秒级，带时区）；常规过滤仍用 _time_second_ |
| `_time_second_` | DateTime | 请求时间（秒级，表主键/排序键前缀之一；查询须带时间窗，slow 表 timeGuard≤24h） |
| `app` | String | 服务/应用名（K8s Deployment 名，如 fs-bi-cloud、action-router-service；慢查/聚合优先等值过滤） |
| `bytes_sent` | Int64 | 响应体字节数 |
| `caller` | String | 上游调用方服务名（样本：fs-cep-provider、fs-bi-udf-report/...；"-" 表示未知） |
| `click_id` | String |  |
| `cluster` | Nullable(String) | K8s 集群标识（样本：tke70-k8s1、mengniu-k8s1） |
| `code` | Int16 | HTTP 状态码（200/4xx/5xx） |
| `company_name` | String | 企业名称（可能为空字符串） |
| `company_status` | String | 企业状态（可能为空字符串） |
| `ea` | String | 租户账号（企业账号；空或 "-" 表示未解析到租户） |
| `ei` | String | 租户 ID（企业 ID，数字字符串；空或 "-" 表示未解析到租户） |
| `method` | String | HTTP 方法（GET/POST/PUT/DELETE 等） |
| `parent_span_id` | String |  |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `pod` | String | 处理请求的 Pod 名称 |
| `pod_ip` | IPv4 | 处理请求的 Pod IP |
| `profile` | String | 部署环境标识（样本：foneshare、mengniu-public-prod；与 app 同属排序键前缀，过滤可显著剪枝） |
| `protocol` | String | HTTP 协议版本（样本多为 HTTP/1.1） |
| `remote_host` | String | 远端主机 IP（常与 x_real_ip 一致或为直连对端） |
| `request_size` | Int64 | 请求体大小（字节） |
| `rpc_id` | Nullable(String) | RPC 调用 ID（可空） |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `span_id` | Nullable(String) | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 trace_id 组合可定位链路中的单个节点 |
| `spanId` | String | OpenTelemetry Span ID |
| `time_cost` | Int32 | 服务端处理耗时（毫秒）。tomcat_access_slow 仅含超过慢阈值的请求（样本 p50 常为数秒～数十秒） |
| `time_for_ckibana` | DateTime | 查询黑名单列（物理存在，**禁止** SELECT/WHERE；时间过滤一律用 `_time_second_`） |
| `trace_id` | String | 链路追踪 ID（样本形态 E-E.{ea}.{uid}-{n}；与 traceId 列同义/并存时优先用本列过滤，有 skip index） |
| `traceId` | String | 链路追踪 ID |
| `uid` | String | 用户标识（常见 {ea}.{userId}，如 mengniu777.1087；未登录/系统调用可能为空） |
| `uri` | String | 原始请求 URI（可含 path + query，如 /fs-bi-sqlengine/.../query_from_pg?user_id=1087；精确排查用） |
| `uri2` | String | 对 URI 做聚合和规范化处理后的路径；进行统计分析或筛选过滤时优先使用 uri2 |
| `x_forwarded_for` | String | X-Forwarded-For 头；链路代理 IP，"-" 表示缺失 |
| `x_real_ip` | String | X-Real-IP 头（常为入口侧看到的客户端/上一跳 IP；内网调用多为集群网段） |

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
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, profile, app, ei, ea, trace_id, uri, code, time_cost FROM tomcat_access_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
