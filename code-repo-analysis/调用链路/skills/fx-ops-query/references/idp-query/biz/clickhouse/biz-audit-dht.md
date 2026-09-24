# biz-audit-dht

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 业务审计日志（DHT 分布式哈希表版本），结构与 biz_audit_log_dist 类似，但缺少 src/dest 字段。可能用于特定的审计场景或数据来源。

**租户ID字段**: `tenantId`

**时间字段**: _time_second_

---

## 表：biz_audit_log_dht_dist

**说明**: 业务审计日志（DHT 分布式哈希表版本），结构与 biz_audit_log_dist 类似，但缺少 src/dest 字段。可能用于特定的审计场景或数据来源。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_audit_log_dht', rand(); Distributed('cluster01', 'logger', 'biz_audit_log_dht', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志写入时间（纳秒级） |
| `_time_second_` | DateTime | 日志写入时间（秒级） |
| `action` | Nullable(String) | 操作类型 |
| `appName` | Nullable(String) | 应用名称 |
| `caller` | String |  |
| `cost` | Nullable(Int64) | 总耗时（ms） |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `ea` | String | 租户账号 |
| `error` | String | 错误信息 / 异常堆栈 |
| `eventId` | String |  |
| `extra` | String |  |
| `isImportPreProcessing` | String |  |
| `isUnionImport` | String |  |
| `message` | Nullable(String) | 消息内容 |
| `module` | Nullable(String) | 模块名称 |
| `num` | Nullable(Int32) | 操作数量 |
| `objectApiNames` | Array(String) | 涉及的对象 API 名称列表 |
| `objectIds` | Array(String) | 涉及的对象 ID 列表 |
| `parameters` | String |  |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | Nullable(String) | 环境标识 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | Nullable(String) | 服务端 IP |
| `spanId` | String | OpenTelemetry Span ID |
| `status` | String |  |
| `step1Cost` | Nullable(Int64) | 步骤1耗时（ms） |
| `step2Cost` | Nullable(Int64) | 步骤2耗时（ms） |
| `step3Cost` | Nullable(Int64) | 步骤3耗时（ms） |
| `step4Cost` | Nullable(Int64) | 步骤4耗时（ms） |
| `step5Cost` | Nullable(Int64) | 步骤5耗时（ms） |
| `step6Cost` | Nullable(Int64) | 步骤6耗时（ms） |
| `step7Cost` | Nullable(Int64) | 步骤7耗时（ms） |
| `tenantId` | Nullable(String) | 租户 ID |
| `traceId` | Nullable(String) | 链路追踪 ID |
| `userId` | String | 用户 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM biz_audit_log_dht_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
