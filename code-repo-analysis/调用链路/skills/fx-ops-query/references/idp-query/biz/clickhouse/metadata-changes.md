# metadata-changes

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 业务元数据变更 oplog，记录元数据变更事件的详细过程，包括操作类型、涉及对象、各步骤耗时等。用于追踪业务层发出的元数据变更操作。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_

**历史覆盖**: TTL 为 120 天。TTL 只说明当前表的理论保留期，不证明任意历史日期都有数据；报告必须输出本次实际查询窗口、最早/最晚命中时间和 `before/after` 之外的内容缺口。

**空结果语义**: 本表为空只表示当前租户、时间窗和过滤条件下没有 metadata 事件，不能证明没有布局操作。需要与 `audit_log`、CEP 和 oplog 分别记录 `empty`、`error` 或 `out_of_range`。

---

## 表：paas_metadata_changes_dist

**说明**: 业务元数据变更 oplog，记录元数据变更事件的详细过程，包括操作类型、涉及对象、各步骤耗时等。用于追踪业务层发出的元数据变更操作。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'paas_metadata_changes', rand(); Distributed('cluster01', 'logger', 'paas_metadata_changes', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime | 日志采集时间（秒级） |
| `action` | Nullable(String) | 操作类型 |
| `appName` | Nullable(String) | 应用名称 |
| `caller` | String |  |
| `cost` | Nullable(Int64) | 总耗时(ms) |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `ea` | Nullable(String) | 租户账号 |
| `error` | String | 错误信息 / 异常堆栈 |
| `eventId` | String |  |
| `extra` | Nullable(String) | 扩展信息 |
| `isImportPreProcessing` | String |  |
| `isUnionImport` | String |  |
| `message` | String |  |
| `module` | String |  |
| `num` | Nullable(Int32) | 数量 |
| `objectApiName` | String | 对象API名称 |
| `objectApiNames` | Array(String) | 对象API名称列表 |
| `objectId` | String | 对象ID |
| `objectIds` | Array(String) | 对象ID列表 |
| `parameters` | String |  |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | Nullable(String) | 环境标识 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | Nullable(String) | 服务端IP |
| `spanId` | String | OpenTelemetry Span ID |
| `status` | String |  |
| `step1Cost` | Nullable(Int64) | 步骤1耗时(ms) |
| `step2Cost` | Nullable(Int64) | 步骤2耗时(ms) |
| `step3Cost` | Nullable(Int64) | 步骤3耗时(ms) |
| `step4Cost` | Nullable(Int64) | 步骤4耗时(ms) |
| `step5Cost` | Nullable(Int64) | 步骤5耗时(ms) |
| `step6Cost` | Nullable(Int64) | 步骤6耗时(ms) |
| `step7Cost` | Nullable(Int64) | 步骤7耗时(ms) |
| `tenantId` | Nullable(String) | 租户ID |
| `traceId` | Nullable(String) | 链路追踪ID |
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
# 租户 + 对象 + 半开时间窗（推荐）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_nanosecond_, _time_second_, action, objectApiName, objectApiNames, traceId, userId, status, parameters, extra, error FROM paas_metadata_changes_dist WHERE tenantId = '815408' AND objectApiName = 'ObjectApiName' AND _time_second_ >= toDateTime('2026-06-09 00:00:00') AND _time_second_ < toDateTime('2026-06-24 00:00:00') ORDER BY _time_nanosecond_ ASC LIMIT 200"

# 近 1 小时变更摘要
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, action, objectApiName, status, cost, error FROM paas_metadata_changes_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20"

# 按 action / 对象聚合
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT action, objectApiName, status, COUNT(*) as cnt, avg(cost) as avg_cost FROM paas_metadata_changes_dist WHERE tenantId = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY action, objectApiName, status ORDER BY cnt DESC"
```

对象 API 为空或批量事件时，同时检查 `objectApiNames`、`objectId`、`objectIds`、`parameters`、`extra` 和 `traceId`。不要把 `action` 的某个字符串值直接当作布局操作，先以实时样本和同一 trace 的 CEP/oplog 交叉确认。

对象布局审计至少记录：

- metadata 事件数量、唯一 trace 数和首末时间。
- `userId`、`traceId`、`objectApiName/objectApiNames` 是否存在。
- `status`、`error`、`parameters`/`extra` 是否足以解释对象和布局。
- 本表与 `audit_log`、CEP、oplog 的对齐方式；没有对齐时标记缺口。

**禁止示例（超时高发）**：

```sql
-- ❌ 函数转换 tenantId；易宽窗超时
SELECT * FROM paas_metadata_changes_dist
WHERE toString(tenantId) = '815408'
  AND objectId = '6920214e0ca2a800075a358f'
  AND _time_second_ >= toDateTime('2026-06-09 00:00:00')
  AND _time_second_ < toDateTime('2026-06-24 00:00:00')
ORDER BY _time_second_ DESC LIMIT 40
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
