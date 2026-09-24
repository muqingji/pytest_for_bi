# integration-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 数据同步日志汇总表，记录数据同步操作的统计信息（成功数、失败数、关联对象等）

**租户ID字段**: `tenantId`, `ea`

**时间字段**: `_time_second_`（分区/主过滤）；`createTime` 仅展示

---

## 表：data_sync_log_dist

**说明**: 数据同步日志汇总表，记录数据同步操作的统计信息（成功数、失败数、关联对象等）

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'data_sync_log', rand(); Distributed('cluster01', 'logger', 'data_sync_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime | 日志采集时间（秒级） |
| `action` | Nullable(String) | 操作类型 |
| `appName` | Nullable(String) | 应用名称 |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `ea` | Nullable(String) | 租户账号 |
| `errorNum` | Nullable(Int64) | 错误数量 |
| `fileName` | Nullable(String) | 文件名 |
| `message` | String |  |
| `objectApiName` | String |  |
| `objectIds` | Array(String) | 对象ID列表 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | Nullable(String) | 环境标识 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `source` | Nullable(String) | 数据来源 |
| `spanId` | String | OpenTelemetry Span ID |
| `successNum` | Nullable(Int64) | 成功数量 |
| `tenantId` | Nullable(String) | 租户ID |
| `totalNum` | Nullable(Int64) | 同步总数 |
| `traceId` | Nullable(String) | 追踪ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, ea, objectApiName, action, successNum, errorNum, totalNum, traceId FROM data_sync_log_dist WHERE tenantId = '<EI>' AND _time_second_ >= '<START>' AND _time_second_ <= '<END>' LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
