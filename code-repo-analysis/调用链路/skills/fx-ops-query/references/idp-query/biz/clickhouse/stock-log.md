# stock-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 库存操作日志，记录库存变更操作（如出入库），包含操作详情、耗时、关联对象等信息

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_

---

## 表：stock_log_dist

**说明**: 库存操作日志，记录库存变更操作（如出入库），包含操作详情、耗时、关联对象等信息

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'stock_log', rand(); Distributed('cluster01', 'logger', 'stock_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | — |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 纳秒时间 |
| `_time_second_` | DateTime | 记录时间 |
| `action` | String | 操作类型 |
| `appName` | String | 应用名 |
| `caller` | String | 调用方 |
| `cost` | Int32 | 耗时（ms） |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 创建时间 |
| `ea` | String | 租户账号 |
| `error` | String | 错误信息 |
| `errorCode` | String | 错误码 |
| `eventId` | String | 事件ID |
| `extra` | String | 扩展信息 |
| `message` | String | 消息 |
| `module` | String | 模块 |
| `num` | Int32 | 数量 |
| `objectApiNames` | String | 对象 API 名称 |
| `objectIds` | String | 对象ID |
| `parameters` | String | 参数 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `profile` | String | 环境 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `serverIp` | String | 服务器IP |
| `spanId` | String | OpenTelemetry Span ID |
| `status` | String | 状态 |
| `tenantId` | String | 租户ID |
| `traceId` | String | 链路追踪ID |
| `userId` | String | 用户ID |

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
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM stock_log_dist WHERE tenantId = '123' AND _time_second_ > '2024-01-01' LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
