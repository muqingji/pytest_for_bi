# fast-notifier

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 快速广播消息确认日志，记录消息通知的投递统计信息，包括生产者、耗时、成功/失败数、消息内容等。用于消息广播系统的监控和故障排查。

**租户ID字段**: `ei`

**时间字段**: _time_second_, createTime

---

## 表：notifier_broadcast_ack_dist

**说明**: 快速广播消息确认日志，记录消息通知的投递统计信息，包括生产者、耗时、成功/失败数、消息内容等。用于消息广播系统的监控和故障排查。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'notifier_broadcast_ack', rand(); Distributed('cluster01', 'logger', 'notifier_broadcast_ack', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(60)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime | 日志采集时间（秒级） |
| `avgCost` | Nullable(Int32) | 平均耗时(ms) |
| `broker` | Nullable(String) | 消息代理 |
| `content` | Nullable(String) | 消息内容 |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `ei` | String | 租户 ID |
| `extra` | Nullable(String) | 扩展信息 |
| `failNum` | Nullable(Int32) | 失败数量 |
| `maxCost` | Nullable(Int32) | 最大耗时(ms) |
| `minCost` | Nullable(Int32) | 最小耗时(ms) |
| `msgId` | Nullable(String) | 消息ID |
| `producer` | Nullable(String) | 生产者标识 |
| `room` | Nullable(String) | 消息房间 |
| `token` | Nullable(String) | 消息令牌 |
| `totalNum` | Nullable(Int32) | 总数量 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `ei` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, room, producer, totalNum, failNum, avgCost FROM notifier_broadcast_ack_dist WHERE ei = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY _time_second_ DESC LIMIT 20"

fx-ops idp --profile <profile> query biz-app-log --sql "SELECT room, COUNT(*) as cnt, sum(failNum) as fail_total FROM notifier_broadcast_ack_dist WHERE ei = '123' AND _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY room ORDER BY cnt DESC"
```

### 排障模板（失败率 / 延迟 / room·producer）

`failNum` 来自 `SendService.auditSendResult`：`!SendResult.isSuccess()`。失败率用 `sum(failNum)/sum(totalNum)`，不要只 count 行。`avgCost` 可能为负，不当 SLA。无时间窗的 `LIMIT 1` 可能扫到旧分区。

```bash
# 1) 按 room / producer 失败率与耗时
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT room, producer,
       count() AS cnt,
       sum(totalNum) AS total_num,
       sum(failNum) AS fail_num,
       if(sum(totalNum) > 0, round(sum(failNum) / sum(totalNum), 4), 0) AS fail_rate,
       avg(avgCost) AS avg_cost,
       max(maxCost) AS max_cost
FROM notifier_broadcast_ack_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
GROUP BY room, producer
ORDER BY fail_num DESC, cnt DESC
LIMIT 20
" -j

# 2) failNum>0 明细
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT _time_second_, room, producer, broker, totalNum, failNum, avgCost, maxCost, msgId
FROM notifier_broadcast_ack_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
  AND failNum > 0
ORDER BY failNum DESC, maxCost DESC
LIMIT 50
" -j

# 3) 按 room 延迟
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT room,
       count() AS cnt,
       avg(avgCost) AS avg_cost,
       max(maxCost) AS max_cost,
       sum(failNum) AS fail_num,
       sum(totalNum) AS total_num
FROM notifier_broadcast_ack_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
GROUP BY room
ORDER BY max_cost DESC
LIMIT 20
" -j
```

Grafana UID `ch-fast-notifier`（变量 room / producer）。Prometheus **无** `notifier_*` 指标，以本表为准。

foneshare 2026-09-18 某 1h **时窗样例（非基线、非阈值）**：room=`function_tenant_pool_change` 多 producer 的 fail_rate 可达 0.29。后续时窗该 room 失败率可回到 0，排障以当时 SQL 为准。

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
