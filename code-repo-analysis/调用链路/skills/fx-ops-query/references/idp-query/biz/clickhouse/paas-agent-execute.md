# paas-agent-execute

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: PaaS Agent执行日志表，记录每次Agent调用的模型、指令、回答、Token消耗和执行结果

**租户ID字段**: `tenantId`

**时间字段**: _time_second_, _time_nanosecond_, createTime

---

## 表：paas_agent_execute_log_dist

**说明**: PaaS Agent执行日志表，记录每次Agent调用的模型、指令、回答、Token消耗和执行结果

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'paas_agent_execute_log', rand(); Distributed('cluster01', 'logger', 'paas_agent_execute_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `_time_nanosecond_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenantId` | String | 租户ID |
| `userId` | String | 用户ID |
| `apiName` | String | API接口名称 |
| `instanceId` | String | Agent实例ID |
| `traceId` | String | 分布式链路追踪ID |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建时间 |
| `cost` | Nullable(Int64) | 执行耗时（毫秒） |
| `model` | String | 使用的模型名 |
| `instruction` | String | 指令/提示词 |
| `answer` | String | 模型输出结果 |
| `token` | Nullable(Int64) | Token消耗数 |
| `history` | String | 对话历史 |
| `variables` | String | 变量信息 |
| `_time_second_` | DateTime('Asia/Shanghai') | 事件写入ClickHouse的秒级时间戳 |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入ClickHouse的纳秒级时间戳 |
| `buttonApiName` | String | 触发按钮的API名称 |
| `action` | String | 操作类型 |
| `success` | Nullable(Bool) | 是否执行成功 |
| `errorMessage` | String | 错误消息 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 用户ID | `userId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `_time_nanosecond_`, `createTime` |

### 查询示例

```bash
# 查询Agent执行失败记录
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, userId, instanceId, apiName, model, token, errorMessage FROM paas_agent_execute_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND success = false ORDER BY _time_second_ DESC LIMIT 50"

# 统计各模型Token消耗
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT model, COUNT(*) as cnt, avg(cost) as avg_cost, sum(token) as total_tokens FROM paas_agent_execute_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY model ORDER BY total_tokens DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
