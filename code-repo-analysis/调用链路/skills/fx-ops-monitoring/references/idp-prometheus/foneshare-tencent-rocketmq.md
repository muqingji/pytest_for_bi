# foneshare 腾讯云 RocketMQ 指标

用于按指标名解释 **foneshare** 环境、腾讯云 **消息队列 RocketMQ 版**（**4.x 与 5.x 两套集群**）的 Prometheus 监控信号。覆盖 `qce_rocketmq_*`（`job="qcloud-exporter"`）。

本文件只做腾讯云指标说明。不覆盖自建 `rocketmq_*` exporter（见 `rocketmq.md`）、其他云厂商、其他环境；不改告警规则或采集配置；不写入凭据或采集地址。

查询时 `--profile foneshare`。先按 `tenant` 确认是 4.x 还是 5.x，再按指标名对照下表。不要把自建 `rocketmq_*` 与 `qce_rocketmq_*` 写成一张表，也不要用自建 exporter 的 `cluster` 标签去指腾讯云实例。

权威文档：腾讯云「消息队列 RocketMQ 版监控指标」（248/80467）；含义补充见「监控指标说明」（1493/124895）。

## 命名规则

文档英文名转小写后加 `qce_rocketmq_` 前缀和聚合后缀。聚合后缀以 foneshare Prometheus 实际 `__name__` 为准（常见 `_sum` / `_max` / `_expr` / `_avg`），不要只按英文名臆造。

| 文档英文名 | Prometheus 指标 |
| --- | --- |
| `RocketmqExpensePullTps` | `qce_rocketmq_rocketmqexpensepulltps_sum` |

其它指标同理。冲突时同时保留「文档单位 / 文档英文名」和「Prometheus 名 / 后缀」，不自行换算或改名。

## 集群主键 tenant（4.x / 5.x 对照）

集群主键是 `tenant`，例如 `{tenant="rmq-8rgrpm9a3"}`。4.x 与 5.x 用不同 tenant。248/80467 的 4.x 集群 ID 形如 `rocketmq-xxxxxxxxxx`，5.x 实例 ID 形如 `rmq-xxxxxxxxxx`；foneshare 实测与此一致。

`instance_name`（如 `rocketmq-001`）是 `qcloud-exporter` 在 **5.x** 序列上的附加标签，**不是**腾讯云集群 ID，不能代替 `tenant`。4.x 序列没有 `instance_name`，改用 `cluster_name`（如 `rocketmq-009`）做可读名；`cluster_name` 同样不能代替 `tenant`。

| tenant | 版本 | 附加标签 | 依据 |
| --- | --- | --- | --- |
| `rmq-8rgrpm9a3` | 5.x | `instance_name="rocketmq-001"` | 需求示例；有 `qce_rocketmq_rocketmqexpensepulltps_sum` 等 5.x 指标 |
| `rmq-8pne9x95a` | 5.x | `instance_name="rocketmq-002"` | 同上 |
| `rmq-8vje9q7ox` | 5.x | `instance_name="rocketmq-003"` | 同上（旧文档曾只拿它当 tenant 示例） |
| `rmq-8dve3mpa8` | 5.x | `instance_name="rocketmq-004"` | 同上 |
| `rmq-8929jmvb4` | 5.x | `instance_name="rocketmq-005"` | 同上 |
| `rocketmq-zjw7zdzvkx57` | 4.x | `cluster_name="rocketmq-006"` | 有 `qce_rocketmq_clusterdiskratio_avg` / `qce_rocketmq_rocketmqgroupdiff_sum` 等 4.x 指标 |
| `rocketmq-jmdnep54znmo` | 4.x | `cluster_name="rocketmq-007"` | 同上 |
| `rocketmq-rd5qvwge5mpr` | 4.x | `cluster_name="rocketmq-008"` | 同上 |
| `rocketmq-4k8kbv25z5ep` | 4.x | `cluster_name="rocketmq-009"` | 同上 |

盘点：

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (tenant)({__name__=~"qce_rocketmq_.*"})' -j --limit-points 100
```

## 单位约定

单位以本表「单位（文档）」为准。与控制台/文档冲突时，同时保留文档单位，**不自行换算**。

| 差异项 | 文档单位 | 不要改成 |
| --- | --- | --- |
| 5.x `RocketmqTopicMessageStorageSize` / `RocketmqNamespaceMessageStorageSize` | GBytes | Bytes / GiB |
| 4.x `RocketmqMessageStorageSize` | Bytes | GBytes |
| 4.x `RocketmqThroughputIn` / `RocketmqThroughputOut`（文档有、当前未采集） | Bytes/s | MBytes/s |
| 5.x 消费滞后 `*LagLatency` | ms | s |
| 4.x `RocketmqGroupTimeDiff`（文档有、当前未采集） | s | ms |
| `ClusterDiskCapacityTotal` | 待对照 | 不要编造成 GBytes 或与 Free 同一单位后直接相减展示为结论 |
| 4.x 流量类（如 `RocketmqGroupConsumerMessageSize`） | 248 为 MBytes | 不要按 1493 的 MBytes/s 自行改单位 |

延迟类 5.x 指标单位为毫秒。读数很大时按 ms 解释（例如 `579560000` ms 约 6.7 天），不要改写成秒再当文档单位。

## 发现查询

确认 `qce_rocketmq_*` 是否存在后再按名称解释。宽前缀查询可能 502，优先 instant、限制点数，并带 `tenant`：

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (__name__,tenant)({__name__=~"qce_rocketmq_.*"})' -j --limit-points 500
```

若仍 502，按版本拆开具体指标，例如：

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (tenant)(qce_rocketmq_rocketmqexpensepulltps_sum)' -j --limit-points 50

fx-ops idp --profile foneshare prometheus query --promql \
 'count by (tenant)(qce_rocketmq_rocketmqgroupdiff_sum)' -j --limit-points 50
```

常用标签：`tenant`（集群主键）、`topic`、`group`、`namespace`（4.x 文档维度，实测均为 `tdmq_default`；5.x 消费 TPS 等序列无此标签）、`instance_name`（仅 5.x 附加）、`cluster_name`（仅 4.x 附加，如 `rocketmq-009`）、`k8s_cluster`、`job="qcloud-exporter"`。以实际 series 为准。

## 5.x 已采集

以下指标在 foneshare Prometheus 有 `__name__`，且只出现在 `rmq-*` tenant。含义与单位来自 248/80467。

### 集群 / namespace

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 |
| --- | --- | --- | --- | --- | --- |
| `qce_rocketmq_rocketmqnamespaceconsumerconnections_sum` | RocketmqNamespaceConsumerConnections | 在线消费者数量 | Count | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespaceconsumerlaglatency_max` | RocketmqNamespaceConsumerLagLatency | 消费处理滞后时间 | ms | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespaceconsumerqueueinglatency_max` | RocketmqNamespaceConsumerQueueingLatency | 已就绪消息的排队时间 | ms | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespaceexpensealltps_expr` | RocketmqNamespaceExpenseAllTps | 集群总 TPS（生产+消费，按计费规则折算） | Count/s | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespaceexpensepulllimittps_sum` | RocketmqNamespaceExpensePullLimitTps | 被限流的消费 TPS | Count/s | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespaceexpensepulltps_sum` | RocketmqNamespaceExpensePullTps | 消费 TPS | Count/s | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespaceexpensesendlimittps_sum` | RocketmqNamespaceExpenseSendLimitTps | 被限流的生产 TPS | Count/s | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespaceexpensesendtps_sum` | RocketmqNamespaceExpenseSendTps | 生产 TPS | Count/s | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespacemessagestoragesize_sum` | RocketmqNamespaceMessageStorageSize | 消息存储空间 | GBytes | 5.x | tenant |
| `qce_rocketmq_rocketmqnamespaceproducerconnections_sum` | RocketmqNamespaceProducerConnections | 生产者数量 | Count | 5.x | tenant |

### Topic

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 |
| --- | --- | --- | --- | --- | --- |
| `qce_rocketmq_rocketmqconsumerlagmessages_sum` | RocketmqConsumerLagMessages | 消息堆积条数 | Count | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqexpensepulllimittps_sum` | RocketmqExpensePullLimitTps | 被限流的消费 TPS | Count/s | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqexpensepulltps_sum` | RocketmqExpensePullTps | 消费 TPS | Count/s | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqexpensesendlimittps_sum` | RocketmqExpenseSendLimitTps | 被限流的生产 TPS | Count/s | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqexpensesendtps_sum` | RocketmqExpenseSendTps | 生产 TPS | Count/s | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqproducerconnections_max` | RocketmqProducerConnections | 生产者数量 | Count | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqthroughputintotal_sum` | RocketmqThroughputInTotal | 生产流量 | MBytes/s | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqthroughputouttotal_sum` | RocketmqThroughputOutTotal | 消费流量 | MBytes/s | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqtopicconsumerconnections_max` | RocketmqTopicConsumerConnections | 消费者数量 | Count | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqtopicconsumerlaglatency_max` | RocketmqTopicConsumerLagLatency | 消费处理滞后时间 | ms | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqtopicconsumerqueueinglatency_max` | RocketmqTopicConsumerQueueingLatency | 已就绪消息的排队时间 | ms | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqtopicexpensealltps_expr` | RocketmqTopicExpenseAllTps | 总 TPS | Count/s | 5.x | tenant、topic |
| `qce_rocketmq_rocketmqtopicmessagestoragesize_sum` | RocketmqTopicMessageStorageSize | 消息存储空间 | GBytes | 5.x | tenant、topic |

### Group

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 |
| --- | --- | --- | --- | --- | --- |
| `qce_rocketmq_rocketmqgroupconsumerconnections_max` | RocketmqGroupConsumerConnections | 在线消费者数量 | Count | 5.x | tenant、group |
| `qce_rocketmq_rocketmqgroupconsumerlaglatency_max` | RocketmqGroupConsumerLagLatency | 消费处理滞后时间 | ms | 5.x | tenant、group |
| `qce_rocketmq_rocketmqgroupconsumerlagmessages_sum` | RocketmqGroupConsumerLagMessages | 消息堆积条数 | Count | 5.x | tenant、group |
| `qce_rocketmq_rocketmqgroupconsumerqueueinglatency_max` | RocketmqGroupConsumerQueueingLatency | 已就绪消息的排队时间 | ms | 5.x | tenant、group |
| `qce_rocketmq_rocketmqgroupexpensepulllimittps_sum` | RocketmqGroupExpensePullLimitTps | 被限流的消费 TPS | Count/s | 5.x | tenant、group |
| `qce_rocketmq_rocketmqgroupexpensepulltps_sum` | RocketmqGroupExpensePullTps | 消费 TPS | Count/s | 5.x | tenant、group |

### Topic + Group

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 |
| --- | --- | --- | --- | --- | --- |
| `qce_rocketmq_rocketmqtopicgroupconsumerconnections_max` | RocketmqTopicGroupConsumerConnections | 在线消费者数量 | Count | 5.x | tenant、topic、group |
| `qce_rocketmq_rocketmqtopicgroupconsumerlaglatency_max` | RocketmqTopicGroupConsumerLagLatency | 消费处理滞后时间 | ms | 5.x | tenant、topic、group |
| `qce_rocketmq_rocketmqtopicgroupconsumerlagmessages_sum` | RocketmqTopicGroupConsumerLagMessages | 消息堆积条数 | Count | 5.x | tenant、topic、group |
| `qce_rocketmq_rocketmqtopicgroupconsumerqueueinglatency_max` | RocketmqTopicGroupConsumerQueueingLatency | 已就绪消息的排队时间 | ms | 5.x | tenant、topic、group |
| `qce_rocketmq_rocketmqtopicgroupmessagesouttotal_sum` | RocketmqTopicGroupMessagesOutTotal | 消费消息条数 | Count/s | 5.x | tenant、topic、group |
| `qce_rocketmq_rocketmqtopicgroupthroughputouttotal_sum` | RocketmqTopicGroupThroughputOutTotal | 消费流量 | MBytes/s | 5.x | tenant、topic、group |

## 4.x 已采集

以下指标在 foneshare Prometheus 有 `__name__`，且只出现在 `rocketmq-*` tenant。248/80467 4.x 表未列出的，标明来源，不把 1493 英文名冒充成 248 已列。

### 存储 / 节点

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 |
| --- | --- | --- | --- | --- | --- |
| `qce_rocketmq_clusterdiskcapacityfree_sum` | ClusterDiskCapacityFree | 磁盘可用空间 | MBytes | 4.x | tenant |
| `qce_rocketmq_clusterdiskcapacitytotal_sum` | ClusterDiskCapacityTotal | 磁盘总容量（命名对应 ClusterDiskCapacityTotal） | 待对照 | 4.x | tenant |
| `qce_rocketmq_clusterdiskratio_avg` | ClusterDiskRatio | 磁盘使用比例 | % | 4.x | tenant |
| `qce_rocketmq_rocketmqbrokerbizload_expr` | RocketmqBrokerBizLoad | 节点业务负载 | % | 4.x | tenant |

### Topic

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 |
| --- | --- | --- | --- | --- | --- |
| `qce_rocketmq_rocketmqmessagestoragesize_sum` | RocketmqMessageStorageSize | 主题存储消息量大小 | Bytes | 4.x | tenant、namespace、topic |

### Group

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 |
| --- | --- | --- | --- | --- | --- |
| `qce_rocketmq_rocketmqgroupconsumercount_max` | RocketmqGroupConsumerCount | 在线消费者数 | Count | 4.x | tenant、namespace、group |
| `qce_rocketmq_rocketmqgroupconsumerdlqtps_sum` | RocketmqGroupConsumerDlqTps | 每秒被保存的死信消息条数 | Count/s | 4.x | tenant、namespace、group |
| `qce_rocketmq_rocketmqgroupconsumermessagesize_sum` | RocketmqGroupConsumerMessageSize | 每秒消费流量 | MBytes | 4.x | tenant、namespace、group |
| `qce_rocketmq_rocketmqgroupconsumertps_sum` | RocketmqGroupConsumerTps | 消息消费速率 | Count/s | 4.x | tenant、namespace、group |
| `qce_rocketmq_rocketmqgroupdiff_sum` | RocketmqGroupDiff | 消息堆积数 | Count | 4.x | tenant、namespace、group |

`ClusterDiskCapacityFree` / `ClusterDiskRatio` / `RocketmqBrokerBizLoad` / `RocketmqGroupConsumerDlqTps` 的含义取自 1493/124895（248/80467 4.x 表未列这些英文名；近义名 `RocketmqGroupDlqMessageCount` 在 248 有、当前未采集）。`ClusterDiskCapacityTotal` 仅 Prometheus 出现，含义只解释到命名对应，不编造业务定义。

## 文档有、当前未采集

248/80467 列出、但当前 foneshare Prometheus 没有对应 `__name__` 的指标。**不要当成已验证存在**。预期 Prometheus 名为 `qce_rocketmq_` + 英文名小写 + 聚合后缀；后缀未观测到，故不写死。

### 5.x（248/80467）

| 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 | 采集状态 |
| --- | --- | --- | --- | --- | --- |
| RocketmqMessagesInTotal | 生产消息条数 | Count/s | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessagesOutTotal | 消费消息条数 | Count/s | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessageSizeAverage | 消息平均大小 | Bytes | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessageSize1k | 大于0并且小于1KB 的消息数量 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessageSize4k | 大于1KB 并且小于4KB 的消息数量 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessageSize512k | 大于4KB 并且小于512KB 的消息数量 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessageSize1024k | 大于512KB 并且小于1MB 的消息数量 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessageSize2048k | 大于1MB 并且小于2MB 的消息数量 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessageSize4096k | 大于2MB 并且小于4MB 的消息数量 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqMessageSizeOverflow | 大于4MB 的消息数量 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqProduceCostTimeP95 | 生产 P95耗时 | us | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqProduceCostTimeP99 | 生产 P99耗时 | us | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicConsumerCachedBytes | 本地缓存队列中的消息总大小 | Bytes | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicConsumerCachedMessages | 本地缓存队列中的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicAwaitAverageTime | 本地缓存队列中的平均排队时间 | ms | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicConsumerReadyMessages | 已就绪消息数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicConsumerInflightMessages | 处理中的消息数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendToDlqMessagesTotal | 新增的状态为 DLQ 的消息数量 | Count/s | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTime1 | 生产耗时小于1ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTime5 | 生产耗时大于1ms 小于5ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTime10 | 生产耗时大于5ms 小于10ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTime20 | 生产耗时大于10ms 小于20ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTime50 | 生产耗时大于20ms 小于50ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTime200 | 生产耗时大于50ms 小于200ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTime500 | 生产耗时大于200ms 小于500ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTimeOverflow | 生产耗时大于500ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTime1 | 消费耗时小于1ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTime5 | 消费耗时大于1ms 小于5ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTime10 | 消费耗时大于5ms 小于10ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTime100 | 消费耗时大于10ms 小于100ms 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTime1000 | 消费耗时大于100ms 小于1s 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTime10000 | 消费耗时大于1s 小于10s 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTime60000 | 消费耗时大于10s 小于1min 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTimeOverflow | 消费耗时大于1min 的消息条数 | Count | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendSuccessPercentage | 生产成功率 | % | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicSendCostTimeAverage | 平均生产耗时 | ms | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqTopicProcessTimeAverage | 消费耗时 | ms | 5.x | tenant、topic | 文档有、当前未采集 |
| RocketmqGroupMessagesOutTotal | 消费消息条数 | Count/s | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupThroughputOutTotal | 消费流量 | MBytes/s | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupConsumerCachedBytes | 本地缓存队列中的消息总大小 | Bytes | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupConsumerCachedMessages | 本地缓存队列中的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupAwaitAverageTime | 本地缓存队列中的平均排队时间 | ms | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupConsumerReadyMessages | 已就绪消息数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupConsumerInflightMessages | 处理中的消息数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupSendToDlqMessagesTotal | 新增的状态为 DLQ 的消息数量 | Count/s | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupConsumeCostTimeP95 | 消费 P95耗时 | us | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupConsumeCostTimeP99 | 消费 P99耗时 | us | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTime1 | 消费耗时小于1ms 的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTime5 | 消费耗时大于1ms 小于5ms 的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTime10 | 消费耗时大于5ms 小于10ms 的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTime100 | 消费耗时大于10ms 小于100ms 的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTime1000 | 消费耗时大于100ms 小于1s 的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTime10000 | 消费耗时大于1s 小于10s 的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTime60000 | 消费耗时大于10s 小于1min 的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTimeOverflow | 消费耗时大于1min 的消息条数 | Count | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqGroupProcessTimeAverage | 消费耗时 | ms | 5.x | tenant、group | 文档有、当前未采集 |
| RocketmqTopicGroupExpensePullLimitTps | 被限流的消费 TPS | Count/s | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupExpensePullTps | 消费 TPS | Count/s | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumerReadyMessages | 已就绪的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumerInflightMessages | 处理中的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupSendToDlqMessagesTotal | 新增的状态为 DLQ 的消息数量 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumeCostTimeP95 | 消费 P95耗时 | us | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumeCostTimeP99 | 消费 P99耗时 | us | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumerCachedBytes | 本地缓存队列中的消息总大小 | Bytes | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumerCachedMessages | 本地缓存队列中的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupAwaitAverageTime | 本地缓存队列中的平均排队时间 | ms | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTime1 | 消费耗时小于1ms 的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTime5 | 消费耗时大于1ms 小于5ms 的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTime10 | 消费耗时大于5ms 小于10ms 的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTime100 | 消费耗时大于10ms 小于100ms 的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTime1000 | 消费耗时大于100ms 小于1s 的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTime10000 | 消费耗时大于1s 小于10s 的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTime60000 | 消费耗时大于10s 小于1min 的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTimeOverflow | 消费耗时大于1min 的消息条数 | Count | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupProcessTimeAverage | 消费耗时 | ms | 5.x | tenant、topic、group | 文档有、当前未采集 |
| RocketmqConsumerClientCachedBytes | 本地缓存队列中的消息总大小 | Bytes | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqConsumerClientCachedMessages | 本地缓存队列中的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientAwaitAverageTime | 本地缓存队列中的平均排队时间 | ms | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTime1 | 消费耗时小于1ms 的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTime5 | 消费耗时大于1ms 小于5ms 的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTime10 | 消息耗时大于5ms 小于10ms 的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTime100 | 消费耗时大于10ms 小于100ms 的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTime1000 | 消费耗时大于100ms 小于1s 的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTime10000 | 消费耗时大于1s 小于10s 的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTime60000 | 消费耗时大于10s 小于1min 的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTimeOverflow | 消费耗时大于1min 的消息条数 | Count | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqClientProcessTimeAverage | 消费耗时 | ms | 5.x | client_id、group、tenant、topic | 文档有、当前未采集 |
| RocketmqNamespaceConsumerLagMessages | 消息堆积条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessagesInTotal | 生产消息条数 | Count/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessagesOutTotal | 消费消息条数 | Count/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceThroughputInTotal | 生产流量 | MBytes/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceThroughputOutTotal | 消费流量 | MBytes/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceNormalMessagesInTotal | 生产普通消息条数 | Count/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceFifoMessagesInTotal | 生产 FIFO 消息条数 | Count/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceDelayMessagesInTotal | 生产延迟消息条数 | Count/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceTransactionMessagesInTotal | 生产事务消息条数 | Count/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendSuccessPercentage | 生产成功率 | % | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTime1 | 生产耗时小于1ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTime5 | 生产耗时大于1ms 小于5ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTime10 | 生产耗时大于5ms 小于10ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTime20 | 生产耗时大于10ms 小于20ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTime50 | 生产耗时大于20ms 小于50ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTime200 | 生产耗时大于50ms 小于200ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTime500 | 生产耗时大于200ms 小于500ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTimeOverflow | 生产耗时大于500ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceConsumerCachedMessages | 本地缓存队列中的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceConsumerCachedBytes | 本地缓存队列中的消息总大小 | Bytes | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceAwaitAverageTime | 本地缓存队列中的平均排队时间 | ms | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessageSize1k | 小于1KB 的消息数量 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessageSize4k | 大于1KB 小于4KB 的消息数量 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessageSize512k | 大于4KB 小于512KB 的消息数量 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessageSize1024k | 大于512KB 小于1MB 的消息数量 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessageSize2048k | 大于1MB 小于2MB 的消息数量 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessageSize4096k | 大于2MB 小于4MB 的消息数量 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessageSizeOverflow | 大于4MB 的消息数量 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceConsumerReadyMessages | 已就绪消息数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceConsumerInflightMessages | 处理中的消息数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendToDlqMessagesTotal | 新增的状态为 DLQ 的消息数量 | Count/s | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTime1 | 消费耗时小于1ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTime5 | 消费耗时大于1ms 小于5ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTime10 | 消费耗时大于5ms 小于10ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTime100 | 消费耗时大于10ms 小于100ms 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTime1000 | 消费耗时大于100ms 小于1s 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTime10000 | 消费耗时大于1s 小于10s 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTime60000 | 消费耗时大于10s 小于1min 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTimeOverflow | 消费耗时大于1min 的消息条数 | Count | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceSendCostTimeAverage | 生产耗时 | ms | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceProcessTimeAverage | 消费耗时 | ms | 5.x | tenant | 文档有、当前未采集 |
| RocketmqNamespaceMessageSizeAverage | 消息平均大小 | Bytes | 5.x | tenant | 文档有、当前未采集 |

### 4.x（248/80467）

| 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 | 采集状态 |
| --- | --- | --- | --- | --- | --- |
| RocketmqTenantConsumerTps | 消息消费速率 | Count/s | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTenantProducerTps | 消息生产速率 | Count/s | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTenantDiff | 消息堆积数 | Count | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTenantProduceMessageSize | 集群每秒生产流量 | MBytes | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTenantConsumerMessageSize | 集群每秒消费流量 | MBytes | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTenantRetrydiff | 重试消息堆积数 | Count | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTenantNumberOfSendApiCalls | 集群生产消息每秒 API 调用次数 | Count/s | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTenantNumberOfPullApiCalls | 集群消费消息每秒 API 调用次数 | Count/s | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTenantNumberOfSendLimit | 集群每秒被限流次数 | Count/s | 4.x | tenant | 文档有、当前未采集 |
| RocketmqTopicProducerTps | 消息生产速率 | Count/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqTopicConsumerTps | 消息消费速率 | Count/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqTopicProducerMessageSize | 每秒生产流量 | MBytes | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqTopicConsumerMessageSize | 每秒消费流量 | MBytes | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqTopicDiff | 消息堆积数 | Count | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqTopicRetrydiff | 重试消息堆积数 | Count | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqProducerOffset | 发送最大 offset 进度 | Count | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqTopicNumberOfSendApiCalls | topic 生产消息每秒 API 调用次数 | Count/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqTopicNumberOfPullApiCalls | topic 消费消息每秒 API 调用次数 | Count/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqTopicNumberOfSendLimit | 单 topic 每秒被限流次数 | Count/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqRateIn | rocketmq 消息生产速率 | Count/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqRateOut | rocketmq 消息消费速率 | Count/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqThroughputIn | rocketmq 消息生产流量 | Bytes/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqThroughputOut | rocketmq 消息消费流量 | Bytes/s | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqMsgBacklog | rocketmq 消息积压数量 | Count | 4.x | tenant、namespace、topic | 文档有、当前未采集 |
| RocketmqGroupRetryMessageCount | 消费组重试消息数量 | Count | 4.x | tenant、namespace、group | 文档有、当前未采集 |
| RocketmqGroupDlqMessageCount | 消费组死信数量 | Count | 4.x | tenant、namespace、group | 文档有、当前未采集 |
| RocketmqGroupRetrydiff | 重试消息堆积数 | Count | 4.x | tenant、namespace、group | 文档有、当前未采集 |
| RocketmqGroupTimeDiff | 消费组正常订阅时间积压 | s | 4.x | tenant、namespace、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumerTps | 消息消费速率 | Count/s | 4.x | tenant、namespace、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupGroupDiff | 消息堆积数 | Count | 4.x | tenant、namespace、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumerMessageSize | 每秒消费流量 | MBytes | 4.x | tenant、namespace、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupConsumerCount | 在线消费者数 | Count | 4.x | tenant、namespace、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupTimeDiff | 消费组正常订阅时间积压 | s | 4.x | tenant、namespace、topic、group | 文档有、当前未采集 |
| RocketmqTopicGroupDlqMessageCount | 消费组死信数量 | Count | 4.x | tenant、namespace、topic、group | 文档有、当前未采集 |

1493/124895 另列的公网带宽类（4.x `RocketmqPublicNetwork*`、5.x `Rocketmq5PublicNetwork*`）以及客户端异常类（`RocketmqException*`）当前 Prometheus 也未见；248/80467 主表未列这些英文名，这里不展开、不编造 Prometheus 后缀。

## Prometheus 有、文档无对应英文名

| Prometheus 指标 | 文档英文名 | 含义 | 单位（文档） | 适用版本 | 主要维度 |
| --- | --- | --- | --- | --- | --- |
| `qce_rocketmq_clusterdiskcapacitytotal_sum` | ClusterDiskCapacityTotal | 磁盘总容量（命名对应 ClusterDiskCapacityTotal） | 待对照 | 4.x | tenant |

## 查询模板

一律带 `tenant`。5.x 示例用需求给定的 `rmq-8rgrpm9a3`；4.x 示例用 `rocketmq-4k8kbv25z5ep`。

| 目标 | PromQL 模板 |
| --- | --- |
| 5.x 消费 TPS（topic） | `sum by (tenant,topic)(qce_rocketmq_rocketmqexpensepulltps_sum{tenant="${tenant}"})` |
| 5.x 生产 TPS（topic） | `sum by (tenant,topic)(qce_rocketmq_rocketmqexpensesendtps_sum{tenant="${tenant}"})` |
| 5.x 堆积（topic+group） | `sum by (tenant,topic,group)(qce_rocketmq_rocketmqtopicgroupconsumerlagmessages_sum{tenant="${tenant}"})` |
| 5.x 消费延迟（topic+group） | `max by (tenant,topic,group)(qce_rocketmq_rocketmqtopicgroupconsumerlaglatency_max{tenant="${tenant}"})` |
| 5.x 集群总 TPS | `sum by (tenant)(qce_rocketmq_rocketmqnamespaceexpensealltps_expr{tenant="${tenant}"})` |
| 5.x topic 存储 | `sum by (tenant,topic)(qce_rocketmq_rocketmqtopicmessagestoragesize_sum{tenant="${tenant}"})` |
| 4.x group 堆积 | `sum by (tenant,namespace,group)(qce_rocketmq_rocketmqgroupdiff_sum{tenant="${tenant}"})` |
| 4.x group 消费 TPS | `sum by (tenant,namespace,group)(qce_rocketmq_rocketmqgroupconsumertps_sum{tenant="${tenant}"})` |
| 4.x 磁盘使用比例 | `max by (tenant)(qce_rocketmq_clusterdiskratio_avg{tenant="${tenant}"})` |
| 4.x 节点业务负载 | `max by (tenant)(qce_rocketmq_rocketmqbrokerbizload_expr{tenant="${tenant}"})` |

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'topk(10, sum by (tenant,topic)(qce_rocketmq_rocketmqexpensepulltps_sum{tenant="rmq-8rgrpm9a3"}))' -j --limit-points 50

fx-ops idp --profile foneshare prometheus query --promql \
 'topk(10, sum by (tenant,namespace,group)(qce_rocketmq_rocketmqgroupdiff_sum{tenant="rocketmq-4k8kbv25z5ep"}))' -j --limit-points 50
```
