# mq-dispatcher（消息队列调度 / 消费主表）

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 消息队列聚合框架调度日志，记录事件调度的详细过程，包括调度时间、耗时、重试次数、事件ID、对象信息等。用于监控消息调度状态和排查调度延迟。
**排查消费失败、重试、重派、延迟过大时优先本表**；客户端堆栈见 [rocketmq-log.md](./rocketmq-log.md) → `app_log_dist`；msgId 审计见 [mq-audit.md](./mq-audit.md)。

> **写入方口径**：`fs-mq-dispatcher` 的 `DispatcherReporter.afterListen` **硬编码 `status="success"`**。本表还有其他写入方（1h 实测可见 `succ` / `fail` / `re-dispatch`）。排 **dispatcher 本体** 卡死/堆积看 `tries` / `delayCost` / `remainNum`（可加 `status='success'` 收窄 reporter 样本），**不要**把 `status='fail'` 当成 DispatcherReporter 失败。Prometheus **无** `dispatcher_*`。

**租户字段**: `tenantId`, `ea`
**时间字段**: _time_second_

---

## 为什么优先本表

| 对比 | `biz_log_dispatch_dist` | `app_log_dist` | `biz_log_mq_audit_dist` |
| --- | --- | --- | --- |
| 视角 | 业务调度/消费框架 | 客户端/封装文本 | 投递/消费结构化审计 |
| 租户/对象 | 有 | 通常无 | 有 |
| 重试/延迟 | `tries` / `delayCost` / `dispatchCost` | 从 msg 猜 | `reconsumeTimes` / `delayMs` |
| 调度器 | `dispatcherName` | 无 | 无 |

> 问「有没有被消费 / 为何一直重试 / 某租户某对象慢」→ **先本表**。  
> 问「NameServer / topic 路由 / 堆栈」→ `app_log_dist`（[rocketmq-log.md](./rocketmq-log.md)）。

---

## 标准过滤模板（所有示例复用）

```sql
-- 时间窗：下界用业务窗，上界防脏未来时间戳
_time_second_ >= now() - INTERVAL 1 HOUR
AND _time_second_ < now() + INTERVAL 1 HOUR

-- status 白名单（表为混写：success=DispatcherReporter；succ/fail/re-dispatch=其他写入方）
AND status IN ('success', 'succ', 'fail', 'delay', 're-dispatch')
-- 仅 reporter 样本：AND status = 'success'

-- 可选：更稳的耗时聚合（dispatchCost 可能为负）
-- avg(if(dispatchCost > 0 AND dispatchCost < 600000, dispatchCost, null))
```

短窗把 `1 HOUR` 换成 `30 MINUTE` 等即可。`traceId` **经常为空**，串联优先 `eventId`。

---

## 表：biz_log_dispatch_dist

**说明**: 消息队列聚合框架调度日志，记录事件调度的详细过程，包括调度时间、耗时、重试次数、事件ID、对象信息等。用于监控消息调度状态和排查调度延迟。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_dispatch', rand(); Distributed('cluster01', 'logger', 'biz_log_dispatch', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(7)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime | 日志采集时间（秒级） |
| `appName` | Nullable(String) | 应用名称 |
| `bornTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 产生时间 |
| `caller` | Nullable(String) | 调用方 |
| `category` | Nullable(String) | 分类 |
| `commits` | Nullable(Int32) | 提交次数 |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `delayCost` | Nullable(Int32) | 延迟耗时(ms) |
| `dispatchCost` | Nullable(Int32) | 调度耗时(ms) |
| `dispatcherName` | String |  |
| `dispatchThread` | Nullable(String) | 调度线程 |
| `dispatchTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 调度时间 |
| `ea` | Nullable(String) | 租户账号 |
| `eventId` | Nullable(String) | 事件ID |
| `eventUniqId` | Nullable(String) | 事件唯一ID |
| `extra` | Nullable(String) | 扩展信息 |
| `modifiedTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 修改时间 |
| `objectApiName` | Nullable(String) | 对象API名称 |
| `objectId` | Nullable(String) | 对象ID |
| `order` | Nullable(Int32) | 顺序 |
| `parentSpanId` | String | OpenTelemetry 父 Span ID |
| `porterName` | String |  |
| `profile` | Nullable(String) | 环境标识 |
| `remainNum` | Nullable(Int32) | 剩余数量 |
| `rpcId` | String | 该 traceId 下的一次 RPC 请求标识 |
| `spanId` | String | OpenTelemetry Span ID |
| `status` | Nullable(String) | 状态 |
| `tenantId` | Nullable(String) | 租户ID |
| `topic` | Nullable(String) | 主题 |
| `traceId` | String | 链路追踪 ID |
| `tries` | Nullable(Int32) | 重试次数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM biz_log_dispatch_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```
## 查询示例

```bash
# 1) 状态分布
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT status, count() AS cnt,
       avg(if(dispatchCost > 0 AND dispatchCost < 600000, dispatchCost, null)) AS avg_dispatch_ms,
       avg(tries) AS avg_tries, max(tries) AS max_tries
FROM biz_log_dispatch_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
  AND status IN ('success','succ','fail','delay','re-dispatch')
GROUP BY status
ORDER BY cnt DESC
LIMIT 20
" -j

# 2) fail 明细（其他写入方，非 DispatcherReporter）
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT _time_second_, appName, dispatcherName, topic, status,
       dispatchCost, delayCost, tries, tenantId, ea,
       objectApiName, eventId, substring(extra, 1, 300) AS extra_preview
FROM biz_log_dispatch_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
  AND status = 'fail'
ORDER BY _time_second_ DESC
LIMIT 50
" -j

# 2b) fs-mq-dispatcher reporter 路径：高 tries / remainNum / delayCost
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT appName, dispatcherName, porterName,
       count() AS cnt,
       max(tries) AS max_tries,
       quantile(0.9)(if(delayCost > 0, delayCost, null)) AS p90_delay,
       max(remainNum) AS max_remain,
       countIf(tries >= 3) AS tries_ge3
FROM biz_log_dispatch_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
  AND status = 'success'
GROUP BY appName, dispatcherName, porterName
HAVING max_tries >= 3 OR max_remain > 100
ORDER BY max_remain DESC, max_tries DESC
LIMIT 15
" -j

# 3) 高重试 / 重派 / 延迟
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT _time_second_, appName, dispatcherName, topic, status, tries, delayCost, dispatchCost,
       tenantId, ea, objectApiName, eventId
FROM biz_log_dispatch_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
  AND (status IN ('re-dispatch','fail','delay') OR tries >= 5)
ORDER BY tries DESC, delayCost DESC
LIMIT 50
" -j

# 4) 指定租户
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT status, dispatcherName, topic, count() AS cnt,
       max(tries) AS max_tries
FROM biz_log_dispatch_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
  AND tenantId = '<TENANT_ID>'
  AND status IN ('success','succ','fail','delay','re-dispatch')
GROUP BY status, dispatcherName, topic
ORDER BY cnt DESC
LIMIT 30
" -j

# 5) fail Top by app/dispatcher/topic
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT appName, dispatcherName, topic, count() AS fail_cnt, max(tries) AS max_tries
FROM biz_log_dispatch_dist
WHERE _time_second_ >= now() - INTERVAL 1 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
  AND status = 'fail'
GROUP BY appName, dispatcherName, topic
ORDER BY fail_cnt DESC
LIMIT 30
" -j

# 6) 按 eventId 串联（优先于 traceId）
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT _time_second_, appName, dispatcherName, topic, status, tries, delayCost, objectApiName, extra
FROM biz_log_dispatch_dist
WHERE _time_second_ >= now() - INTERVAL 6 HOUR
  AND _time_second_ < now() + INTERVAL 1 HOUR
  AND eventId = '<EVENT_ID>'
ORDER BY _time_second_
LIMIT 100
" -j
```

---

## 实测抽样（foneshare，2026-07-15）

> 近 1h 量级**随业务波动**，只作形态/语义参考，**不当 SLA**。  
> 样例中的租户/账号已**脱敏**为占位符。

### 状态分布（近 1h，量级）

| status | 约 cnt | avg_tries | max_tries | 解读 |
| --- | --- | --- | --- | --- |

### 常见 dispatcherName（Top 形态）

`fast` / `slow` / `batch`（通道）≫ `metaDataDispatcher`（元数据/对象变更，eservice fail 常见）> `normal` 等。  
**部分行 dispatcherName 为空**（如部分 sync/datax），勿强制 `IS NOT NULL`。

### 行级形态（脱敏）

**success（干净）**

```text
appName=fs-paas-calculate-task  dispatcherName=batch
topic=buf_fsdb…@default  status=success
dispatchCost≈2s  delayCost≈4s  tries=0
tenantId=<TENANT_ID>  ea=<EA>
objectApiName=SalesOrderProductObj
```

**fail 首次（tries=1）**

```text
appName=fs-eservice-mq-listener  dispatcherName=metaDataDispatcher
topic=buf_fsdb…  status=fail
dispatchCost≈0.5～1s  delayCost 同量级  tries=1
objectApiName=DeliveryNoteObj  eventId=<EVENT_ID>
extra≈ {"op":"i","bodyList":[... context.appId=CRM ...]}
```

**fail 反复（高 tries）**

```text
appName=fs-eservice-mq-listener  dispatcherName=metaDataDispatcher
status=fail  tries 数百  delayCost 极大（1e7+ ms）
objectApiName=EmployeeSkillObj
```

**fail Top 形态**: 多为 `fs-eservice-mq-listener` + `metaDataDispatcher` + 不同 `buf_fsdb*`；`fs-sync-data-all` 也可见（dispatcher 常空）。

**re-dispatch 互联**

```text
appName=fs-sync-data-all  topic=buf_fsdb…_af  status=re-dispatch
tries 数百  delayCost 极大
objectApiName=AccountObj
extra≈ {"destTenantId":"<DEST_TENANT>","ORDER_BATCH_BASE":1000,"eventList":[...]}
```

→ 可并联 `crm_syncfirststage_dist` / `crm_syncsecondstage_dist` / `sync_data_error_dist`。

**re-dispatch 扫描类**

```text
appName=pg-scanner-ui  status=re-dispatch  tries 极高
extra≈ {"schema":"sch_…","database":"…","host":"…","action":"freeze","table":"…"}
```

**delay（datax）**

```text
appName=datax-sync  status=delay
dispatchCost 十余秒级  delayCost 极大  tries 两百+
objectApiName=UserVisitObj / CheckinsObj
```

`delay` ≠ `fail`，但高 tries + 巨大 delayCost 表示通道滞后。

### 读数注意

| 现象 | 建议 |
| --- | --- |
| `success` + `succ` | 成功量二者之和；`success` 含 DispatcherReporter 硬编码行 |
| reporter vs 混写 | 排 fs-mq-dispatcher 本体用 `tries`/`delayCost`/`remainNum`，可加 `status='success'`；`status='fail'` 是其他写入方 |
| 负 `dispatchCost` | 聚合用 `if(dispatchCost > 0 AND …)` |
| `delayCost` 1e7+ | 用数量级判断积压 |
| `traceId` 常空 | 用 `eventId` / `extra` |
| `topic`=`buf_*` | 非业务 API 名；对象看 `objectApiName` |

---

## 推荐排查顺序

1. **fs-mq-dispatcher reporter 路径先看 2b**：`status='success'` 下的 `tries` / `delayCost` / `remainNum`（reporter 的 status 恒 success，不能当失败依据）
2. 混写面：`status` 分布（`succ`/`fail`/`re-dispatch` 是其他写入方）
3. 同 `eventId` 拉全量行
4. 客户端堆栈 → [rocketmq-log.md](./rocketmq-log.md)
5. msgId 审计 → [mq-audit.md](./mq-audit.md)
6. Broker → [log-center.md](./log-center.md)；Prometheus **无** `dispatcher_*`，堆积看 Grafana `KYxTQz87k`（tag `dispatcher-delay`）  

---

## 相关文档

- [rocketmq-log.md](./rocketmq-log.md) — 场景路由（本表为 P0）
- [mq-audit.md](./mq-audit.md)
- [app-log.md](./app-log.md)
- [diagnostic-scenarios.md](./diagnostic-scenarios.md)
