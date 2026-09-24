# biz-audit

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 跨业务通用审计日志，汇聚多个应用/模块的操作记录。按 appName、action、module、eventId 区分场景，涵盖 MQ 消费（multiPull）、i18n Redis 访问、CRM 账户规则、数据权限事件（DataEvent）、互联 OpenAPI、对象数据同步（db_union_es）等；部分记录含 objectApiNames/objectIds 及 src/dest。

**租户ID字段**: `tenantId`

**时间字段**: _time_second_, createTime

---

## 表：biz_audit_log_dist

**说明**: 跨业务通用审计日志，汇聚多个应用/模块的操作记录。按 appName、action、module、eventId 区分场景，涵盖 MQ 消费（multiPull）、i18n Redis 访问、CRM 账户规则、数据权限事件（DataEvent）、互联 OpenAPI、对象数据同步（db_union_es）等；部分记录含 objectApiNames/objectIds 及 src/dest。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_audit_log', rand(); Distributed('cluster01', 'logger', 'biz_audit_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志写入时间（纳秒级） |
| `_time_second_` | DateTime | 日志写入时间（秒级） |
| `action` | Nullable(String) | 操作类型或接口标识（如 multiPull、I18N_CLIENT_REDIS_GET、account_rule.consumeSkip、db_union_es、DataEvent） |
| `appName` | Nullable(String) | 应用名称 |
| `caller` | String |  |
| `cost` | Nullable(Int64) | 总耗时（ms） |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `dest` | String |  |
| `ea` | String | 租户账号 |
| `error` | String | 错误信息 / 异常堆栈 |
| `eventId` | String |  |
| `extra` | String |  |
| `isImportPreProcessing` | String |  |
| `isUnionImport` | String |  |
| `message` | String |  |
| `module` | String |  |
| `num` | Nullable(Int32) | 操作数量 |
| `objectApiNames` | Array(String) | 涉及的对象 API 名称列表 |
| `objectIds` | Array(String) | 涉及的对象 ID 列表 |
| `parameters` | String |  |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | Nullable(String) | 环境标识 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | String |  |
| `spanId` | String | OpenTelemetry Span ID |
| `src` | String |  |
| `status` | String |  |
| `step1Cost` | Nullable(Int64) | 步骤1耗时（ms） |
| `step2Cost` | Nullable(Int64) | 步骤2耗时（ms） |
| `step3Cost` | Nullable(Int64) | 步骤3耗时（ms） |
| `step4Cost` | Nullable(Int64) | 步骤4耗时（ms） |
| `step5Cost` | Nullable(Int64) | 步骤5耗时（ms） |
| `step6Cost` | Nullable(Int64) | 步骤6耗时（ms） |
| `step7Cost` | Nullable(Int64) | 步骤7耗时（ms） |
| `tenantId` | String | 租户 ID |
| `traceId` | String | 链路追踪 ID |
| `userId` | String | 用户 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM biz_audit_log_dist WHERE tenantId = '123' AND _time_second_ > '2024-01-01' LIMIT 20"

fx-ops idp --profile <profile> query biz-app-log --sql "SELECT userId, COUNT(*) as cnt FROM biz_audit_log_dist WHERE tenantId = '123' AND _time_second_ > '2024-01-01' GROUP BY userId"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
