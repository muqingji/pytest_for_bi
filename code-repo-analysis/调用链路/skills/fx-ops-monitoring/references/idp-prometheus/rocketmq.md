# RocketMQ 指标

用于排查 **自建** RocketMQ topic 生产、consumer group 消费、堆积、消费延迟、broker 状态、exporter 采集状态。本文件只查询 Prometheus 指标，不能切到日志、ClickHouse、MQAdmin 或其它数据源。

腾讯云消息队列 RocketMQ 版（`qce_rocketmq_*`、`job="qcloud-exporter"`、集群主键 `tenant`，含 4.x / 5.x）见 [foneshare-tencent-rocketmq.md](foneshare-tencent-rocketmq.md)。两套指标不要合成一张表，也不要用 `cluster="FS-MQ"` 去指腾讯云实例。

## 本环境已验证结论

当前 Prometheus **自建采集**已验证为 RocketMQ 4.x exporter 风格：

| 项 | 结果 |
| --- | --- |
| exporter job | `find-exporter` 提供 RocketMQ 业务指标；`rocketmq-node-exporter` 提供节点指标 |
| 集群标签 | `cluster="FS-MQ"` |
| K8s 集群标签 | `k8s_cluster="k8s1"` |
| exporter 标识 | `monitor="172.17.0.165"` |
| 常用维度 | `topic`、`group`、`broker`、`brokerIP`、`host`、`instance` |
| 消费组状态标签 | `countOfOnlineConsumers`、`msgModel` |
| 已确认有数据 | `rocketmq_producer_tps`、`rocketmq_consumer_tps`、`rocketmq_group_diff`、`rocketmq_broker_tps`、`rocketmq_group_retrydiff`、`rocketmq_client_consume_fail_msg_tps` |
| 当前查询为空 | `rocketmq_group_get_latency_by_storetime`、`rocketmq_group_dlqdiff` |

自建 exporter 不要默认使用 RocketMQ 5.x observability 的 `rocketmq_messages_in_total`、`rocketmq_consumer_ready_messages`、`rocketmq_send_cost_time_bucket`。除非发现查询证明该 **exporter** 已经切换到 5.x observability 指标。这条限制 **不适用于** 腾讯云 `qce_rocketmq_*`（foneshare 同时有 4.x `rocketmq-*` tenant 和 5.x `rmq-*` tenant）。

## 腾讯云监控指标（qce_rocketmq_*）

由 `qcloud-exporter` 从腾讯云监控拉取，与自建 `rocketmq_*` 是另一套指标。完整 4.x / 5.x 对照、命名规则、单位和查询模板见 [foneshare-tencent-rocketmq.md](foneshare-tencent-rocketmq.md)。

要点：

- 集群主键是 `tenant`，不是 `cluster="FS-MQ"`，也不是 `instance_name` / `cluster_name`
- 5.x tenant 形如 `rmq-xxxxxxxxxx`（如 `rmq-8rgrpm9a3`，附加 `instance_name="rocketmq-001"`）；4.x tenant 形如 `rocketmq-xxxxxxxxxx`（如 `rocketmq-4k8kbv25z5ep`，附加 `cluster_name="rocketmq-009"`）
- `instance_name` 只出现在 5.x；`cluster_name` 只出现在 4.x。二者都是附加标签，不能代替 `tenant`
- 不要把 `rocketmq_*` 与 `qce_rocketmq_*` 写进同一张对照表，也不要用 `or` 把两套堆积指标合成一条模板

发现查询（`--profile foneshare`）：

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (tenant)({__name__=~"qce_rocketmq_.*"})' -j --limit-points 100
```

## 指标发现

全量按 `__name__=~"rocketmq_.*"` 发现可能触发 Prometheus 上游 502。优先查具体指标或聚合后的 `topk`。

```bash
# target 是否在线
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (job,instance)(up{job=~".*rocketmq.*"})' -j

# 4.x exporter 关键指标是否存在
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__)(rocketmq_producer_tps or rocketmq_consumer_tps or rocketmq_group_diff or rocketmq_broker_tps or rocketmq_group_retrydiff or rocketmq_client_consume_fail_msg_tps)' -j
```

再看关键标签：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__,cluster,k8s_cluster,monitor,topic,group,broker,brokerIP,countOfOnlineConsumers,msgModel)(rocketmq_producer_tps or rocketmq_consumer_tps or rocketmq_group_diff or rocketmq_broker_tps)' -j
```

如果该查询返回空，拆开单个指标查询，避免因为某个指标不存在导致表达式不可读。

## 常用标签

| 维度 | 常见标签 | 说明 |
| --- | --- | --- |
| 集群 | `cluster` / `cluster_name` / `rocketmq_cluster` | RocketMQ 集群 |
| Topic | `topic` / `topic_name` | topic 名称 |
| Consumer group | `group` / `consumer_group` / `consumerGroup` | 消费组 |
| Broker | `broker` / `broker_ip` / `brokerName` | broker 维度 |
| Queue | `queue_id` / `queueId` | 队列维度 |
| Namespace | `namespace` | 如果 exporter 跑在 K8s 中，可能有该标签 |
| Instance | `instance` | exporter 或 broker target |
| Exporter | `job` / `monitor` | 本环境为 `job="find-exporter"`、`monitor="172.17.0.165"` |
| 在线消费者数 | `countOfOnlineConsumers` | `rocketmq_group_diff` 上的标签，可用于识别 group 是否无人消费 |
| 消费模式 | `msgModel` | RocketMQ message model，按 exporter 原值展示 |

文档里的模板默认使用本环境已验证标签 `cluster`、`topic`、`group`、`broker`、`brokerIP`。如果其他环境发现结果不同，先替换标签名再执行。

## 已验证指标模板

| 目标 | PromQL 模板 |
| --- | --- |
| topic 生产 TPS | `sum by (cluster,topic)(rocketmq_producer_tps{cluster="${cluster}",topic="${topic}"})` |
| topic 生产消息量增长 | `sum by (topic)(increase(rocketmq_producer_offset{topic="${topic}"}[5m]))` |
| consumer 消费 TPS | `sum by (cluster,topic,group)(rocketmq_consumer_tps{cluster="${cluster}",topic="${topic}",group="${group}"})` |
| consumer 消费消息量增长 | `sum by (topic,group)(increase(rocketmq_consumer_offset{topic="${topic}",group="${group}"}[5m]))` |
| 消费堆积（自建 exporter） | `sum by (group)(rocketmq_group_diff{countOfOnlineConsumers!="0",msgModel!="0",topic=~"${topic}",group=~"${group}",k8s_cluster=~"${k8s_cluster}"})` |
| 重试队列堆积 | `sum by (topic,group)(rocketmq_group_retrydiff{group="${group}"})` |
| 客户端消费失败 TPS | `sum by (topic,group)(rocketmq_client_consume_fail_msg_tps{group="${group}"})` |
| broker 生产 TPS | `sum by (cluster,broker,brokerIP)(rocketmq_broker_tps{cluster="${cluster}"})` |
| broker 消息存储量 | `sum by (broker)(rocketmq_brokeruntime_msg_put_total_today_now)` |

4.x exporter 中部分指标已经是 TPS gauge，不需要再包 `rate()`；offset 和 total 类 counter 才用 `increase()` 或 `rate()`。

## 腾讯云监控查询模板

`qce_rocketmq_*` 的查询一律带 `tenant`，不要用 `instance_name` 当集群主键。完整模板见 [foneshare-tencent-rocketmq.md](foneshare-tencent-rocketmq.md)。

| 目标 | PromQL 模板 |
| --- | --- |
| 5.x 消费堆积（topic+group） | `sum by (tenant,topic,group)(qce_rocketmq_rocketmqtopicgroupconsumerlagmessages_sum{tenant="${tenant}"})` |
| 5.x 消费延迟（topic+group） | `max by (tenant,topic,group)(qce_rocketmq_rocketmqtopicgroupconsumerlaglatency_max{tenant="${tenant}"})` |
| 5.x 消费 TPS（topic） | `sum by (tenant,topic)(qce_rocketmq_rocketmqexpensepulltps_sum{tenant="${tenant}"})` |
| 4.x group 堆积 | `sum by (tenant,namespace,group)(qce_rocketmq_rocketmqgroupdiff_sum{tenant="${tenant}"})` |

延迟类 5.x 指标单位为毫秒（ms），值如 `579560000` 表示约 6.7 天的延迟。

## 典型 topk 查询

### Topic 生产 TPS

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (cluster,topic)(rocketmq_producer_tps))' -j
```

实际样例：`calculate-task-data-optool-gray` 约 `569.3`。

### Consumer group 消费 TPS

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (cluster,topic,group)(rocketmq_consumer_tps))' -j
```

实际样例：`fs-long-polling-notify / fs_long_polling_consumer` 约 `1045.09`。

### 消费堆积

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (cluster,topic,group,countOfOnlineConsumers,msgModel)(rocketmq_group_diff))' -j
```

实际样例中最大堆积多为 `countOfOnlineConsumers="0"` 的历史/离线 group，例如 `object-data / erpSyncData-paas-object-consumer-history` 超过 `50,780,652,482`。排查时要先判断该 group 是否仍应在线，避免把废弃消费组当作当前故障。

### 重试队列堆积

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (topic,group)(rocketmq_group_retrydiff))' -j
```

实际样例：`%RETRY%calculate-task-optool-sv / calculate-task-optool-sv` 为 `188`。

### 客户端消费失败 TPS

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (topic,group)(rocketmq_client_consume_fail_msg_tps))' -j
```

实际样例：`%RETRY%calculate-task-optool-sv / calculate-task-optool-sv` 约 `3.73`。

### Broker TPS

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (cluster,broker,brokerIP)(rocketmq_broker_tps))' -j
```

实际样例：`broker-2 / 172.17.41.147:10911` 约 `687.82`。

## 空值与版本差异

以下指标在当前查询时间点返回空 vector：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (cluster,topic,group)(rocketmq_group_get_latency_by_storetime))' -j

fx-ops idp --profile <profile> prometheus query --promql \
 'topk(10, sum by (cluster,topic,group)(rocketmq_group_dlqdiff))' -j
```

自建 RocketMQ 5.x observability 常见指标可作为其他环境参考，但当前 **自建 exporter** 未验证存在（腾讯云 5.x `qce_rocketmq_*` 另见 foneshare-tencent-rocketmq.md）：

| 目标 | 5.x 常见模板 |
| --- | --- |
| topic 生产速率 | `sum by (topic)(rate(rocketmq_messages_in_total{topic="${topic}"}[1m]))` |
| consumer ready messages | `sum by (topic,consumer_group)(rocketmq_consumer_ready_messages{topic="${topic}",consumer_group="${group}"})` |
| 发送耗时 P99 | `histogram_quantile(0.99, sum by (le,topic)(rate(rocketmq_send_cost_time_bucket{topic="${topic}"}[5m])))` |

## Broker 与 exporter 状态

先确认 broker 指标名：

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'count by (__name__,broker,brokerIP)(rocketmq_broker_tps or rocketmq_brokeruntime_msg_put_total_today_now or rocketmq_brokeruntime_msg_gettotal_today_now)' -j
```

常见模板：

| 目标 | PromQL 模板 |
| --- | --- |
| broker 生产 TPS | `sum by (broker)(rocketmq_broker_tps)` |
| 今日 put 总量 | `sum by (broker)(rocketmq_brokeruntime_msg_put_total_today_now)` |
| 今日 get 总量 | `sum by (broker)(rocketmq_brokeruntime_msg_gettotal_today_now)` |
| exporter target 是否在线 | `up{job=~".*rocketmq.*|find-exporter"}` |

如果 exporter 本身不稳定，先看 `up{job=~".*rocketmq.*"}`；Prometheus 只能判断 target 是否在线和指标是否缺失，不能查看采集任务日志。

## Range 查询模板

```bash
fx-ops idp --profile <profile> prometheus query --promql \
 'sum by (cluster,topic,group,countOfOnlineConsumers)(rocketmq_group_diff{cluster="${cluster}",topic="${topic}",group="${group}"})' \
 --start "$(date -u -v-30M +%Y-%m-%dT%H:%M:%SZ)" \
 --end "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
 --step "1m" -j
```

## Prometheus 查询边界

| 目标 | Prometheus 能否回答 | 说明 |
| --- | --- | --- |
| 当前堆积、TPS、趋势 | 能 | 查 `rocketmq_*` 指标 |
| 某 topic/group 是否持续堆积 | 能 | 对 `rocketmq_group_diff` 做 range 查询 |
| exporter / broker target 是否在线 | 能 | 查 `up{job=~".*rocketmq.*|find-exporter"}` |
| 客户端异常日志、堆栈、类名、消息 | 不能 | 当前 Prometheus 指标未采集这些明细 |
| consumer owner / producer owner | 不能 | 当前 Prometheus 指标未采集负责人信息 |
| MQAdmin 方法耗时、慢查询、错误 | 只能看 exporter 健康 | 当前 Prometheus 指标未采集 MQAdmin 调用明细 |
| 单条消息追踪 | 不能 | 当前 Prometheus 指标是聚合指标，不包含单条消息轨迹 |

## 解读

| 现象 | 优先检查 |
| --- | --- |
| 堆积持续增加 | 生产 TPS、消费 TPS、consumer 实例状态、broker 状态 |
| 生产速率突降 | producer 应用、broker、topic 路由、发送耗时 |
| 消费速率突降 | consumer group 在线状态、线程池、应用错误、JVM GC |
| 发送 P99 升高 | broker 负载、网络、磁盘 IO、producer 重试 |
| 某 group 无数据 | group 标签名是否正确、consumer 是否在线、exporter 是否采集该 group |
| 指标为空 | exporter 采集范围、topic/group 过滤、RocketMQ 版本指标名差异 |
