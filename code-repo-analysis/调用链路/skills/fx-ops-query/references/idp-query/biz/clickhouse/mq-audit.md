# mq-audit

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 业务消息队列审计日志分布式表，审计 RocketMQ/Kafka 消息的生产、发送确认与消费成功率。

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_, createTime

---

## 表：biz_log_mq_audit_dist

**说明**: 业务消息队列审计日志分布式表，审计 RocketMQ/Kafka 消息的生产、发送确认与消费成功率。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'biz_log_mq_audit_local', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime('Asia/Shanghai') | 事件写入 ClickHouse 的秒级时间戳 |
| `bodySize` | Int32 | 大小或数据包容量（字节数） |
| `bornTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `broker` | String | 消息代理Broker名称/地址 |
| `consumeMs` | Int64 | 消息消费耗时（毫秒） |
| `consumeTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `delayMs` | Int64 | 消息投递延迟（毫秒） |
| `ea` | String | 企业账号/租户账号名称 |
| `group` | String | 消费者组名称 |
| `keys` | String | 消息键 |
| `msgId` | String | 消息唯一标识ID |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `reason` | String | 操作结果原因描述 |
| `reconsumeTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `reconsumeTimes` | Int32 | 消息重复消费次数 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `spanId` | String | OpenTelemetry Span ID |
| `status` | String | 状态码或状态标识（如 200, 500, 或 SUCCESS, FAILED） |
| `tags` | String | 消息标签（RocketMQ Tag过滤标识） |
| `tenantId` | String | 租户/企业 ID |
| `topic` | String | 消息主题 |
| `traceId` | String | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |
| `worker` | String | 消费工作节点标识 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

> ⚠️ **`status` 取值口径待复核**（2026-08，来源 `fx-ops-mq` 源码验证，见 `.agents/skills/fx-ops-mq/references/log-surface.md`「hook 审计上报语义」）：`status` 实际取值多为并发消费 `CONSUME_SUCCESS`/`RECONSUME_LATER`、顺序消费 `SUCCESS`/`SUSPEND_CURRENT_QUEUE_A_MOMENT`，**未见 `FAIL`**。下方 `status='FAIL'` 模板可能恒返回空行（导致「无失败记录」的误结论）；失败样本建议改用 `status IN ('RECONSUME_LATER','SUSPEND_CURRENT_QUEUE_A_MOMENT')`。本模板待凭据环境实测复核后对齐。

```bash
# 查询MQ消费失败记录
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, topic, group, msgId, status, reason, delayMs, consumeMs FROM biz_log_mq_audit_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND status = 'FAIL' ORDER BY _time_second_ DESC LIMIT 50"

# 统计各Topic消费成功率
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT topic, group, COUNT(*) as total, sum(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success, avg(delayMs) as avg_delay FROM biz_log_mq_audit_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY topic, group ORDER BY total DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
- ./rocketmq-log.md - RocketMQ / 消费排查总览
- ./mq-dispatcher.md - **消费主表** `biz_log_dispatch_dist`（调度/重试/延迟）
