# rocketmq-log（RocketMQ / MQ 消费 — 场景路由）

> schema_verified_at: 2026-07-25 | platform: v4.37.3
> 消费主表字段 / SQL / 抽样的**唯一权威**：[mq-dispatcher.md](./mq-dispatcher.md)

**说明**: 按意图选表，避免混用。

| 优先级 | 意图 | 表 | 文档 |
| --- | --- | --- | --- |
| **P0** | 消费成败、重试、延迟、重派、租户/对象 | **`biz_log_dispatch_dist`** | **[mq-dispatcher.md](./mq-dispatcher.md)** |
| P1 | 客户端内核 / 业务封装**文本**（路由、堆栈） | **`app_log_dist`** | 下文 + [app-log.md](./app-log.md) |
| P1 | msgId 级投递/消费审计 | **`biz_log_mq_audit_dist`** | [mq-audit.md](./mq-audit.md) |
| P2 | Broker 原始日志 | **`log_center_dist`** | [log-center.md](./log-center.md)（`service_name = 'rocketmq'`） |

> [!IMPORTANT]
> 消费健康度**不要**从 `app_log_dist` 做成功率统计。先 [mq-dispatcher.md](./mq-dispatcher.md)。

---

## P0：消费 → `biz_log_dispatch_dist`

直接使用 [mq-dispatcher.md](./mq-dispatcher.md) 的：

- 标准时间窗 + status 白名单  
- 状态分布 / fail 明细 / 高重试 SQL  
- status 语义（`success`+`succ`、`fail`、`delay`、`re-dispatch`）  
- 实测抽样与读数注意  

此处不重复字段表与长 SQL。

---

## P1：文本日志 → `app_log_dist`

**用途**: NameServer 路由、Remoting WARN、业务封装 `consumeMessage` 文本。  
**不能替代** dispatch 表。须遵守 [app-log.md](./app-log.md) 大表红线（时间窗默认 ≤6h，最大 ≤24h）。

| 类型 | logger 条件 |
| --- | --- |
| Apache 客户端 | `logger LIKE 'o.a.r.%'` 或 `logger = 'RocketmqRemoting'` |
| 业务封装 | `logger LIKE '%rocketmq%'` 或 `logger LIKE '%RocketMQ%'` |

勿单独 `msg LIKE '%rocketmq%'`（噪声大）。

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT _time_second_, app, level, logger, thread, substring(msg, 1, 400) AS msg
FROM app_log_dist
WHERE _time_second_ >= now() - INTERVAL 30 MINUTE
  AND (logger LIKE 'o.a.r.%' OR logger = 'RocketmqRemoting')
  AND level IN ('WARN', 'ERROR')
ORDER BY _time_second_ DESC
LIMIT 50
" -j
```

形态示例：

```text
logger=c.f.f.rocketmq.AbstractConsumer
msg=consumeMessage topic:…, msgId:…

logger=o.a.r.c.i.f.MQClientInstance
msg=… No topic route info in name server …
```

---

## P1：审计 → `biz_log_mq_audit_dist`

字段与示例见 [mq-audit.md](./mq-audit.md)。与 dispatch 互补：audit 偏 msg 结果，dispatch 偏业务调度过程。

---

## 选表速查

| 意图 | 表 |
| --- | --- |
| 消费失败/重试/延迟/重派 | **`biz_log_dispatch_dist`** → [mq-dispatcher.md](./mq-dispatcher.md) |
| 客户端路由/堆栈 | `app_log_dist` |
| msgId 成败 | `biz_log_mq_audit_dist` |
| Broker 水位原文 | `log_center_dist` |

---

## 相关文档

- [mq-dispatcher.md](./mq-dispatcher.md) — **消费主表权威**
- [mq-audit.md](./mq-audit.md) · [app-log.md](./app-log.md) · [log-center.md](./log-center.md) · [diagnostic-scenarios.md](./diagnostic-scenarios.md)
