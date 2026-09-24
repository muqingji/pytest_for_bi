# Kafka 指标（kafka-exporter）

用于排查 **集群侧** Kafka 消费组 lag、broker / 分区健康、topic 生产位点。本文件只查询 Prometheus，不切到 ClickHouse 或 CMS。

应用侧 fs-kafka-support **不暴露** Micrometer 指标、**不上报** `biz_log_mq_audit_dist`。TDMQ / CKafka 托管 Kafka 指标名在 foneshare **未采集**（env-blocked，见文末）。**禁止**把 `rocketmq_*` / `qce_rocketmq_*` 套到 Kafka。`ClickHouseMetrics_Kafka*` 是 ClickHouse Kafka table engine，不是业务消费组。

## 本环境已验证结论（foneshare，2026-09-18）

| 项 | 结果 |
| --- | --- |
| lag 主指标 | `kafka_consumergroup_lag`（分区级，3381 系列） |
| lag job | `kafka-log-exporter`（3237）/ `kafka-audit-log-exporter`（144），均 `k8s_cluster="tke70-k8s1"` |
| 关键标签 | `consumergroup` / `topic` / `partition` / `job` / `instance` / `k8s_cluster` / `monitor` / `monitoring_instance` |
| 组级合计 | `kafka_consumergroup_lag_sum` |
| 消费位点 | `kafka_consumergroup_current_offset` / `_sum` |
| 组成员 | `kafka_consumergroup_members` |
| broker 数 | `kafka_brokers` |
| topic 写入位点 | `kafka_topic_partition_current_offset` |
| Grafana | UID `i8HLvrkiz`（变量 datasource / job / cluster=`monitoring_instance` / topic_name / group_id）；默认 job 当前值可能是 `kafka3-prometheus-kafka-exporter`，与 lag 采集 job 不同，下拉切换 |

样例：`consumergroup=clickhouse-20241201`、`topic=tomcat-access`、`partition=15`、`job=kafka-log-exporter`、`instance=10.71.145.97:9308`。历史 top lag 可达数百万，先确认该 group 是否仍应在线。

## 发现

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (job, k8s_cluster)(kafka_consumergroup_lag)' -j

fx-ops idp --profile foneshare prometheus query --promql \
 'count by (__name__)({__name__=~"(?i).*kafka.*"})' -j
```

宽前缀会混入 `ClickHouseMetrics_Kafka*` / `kafka_mm2_*` / `spring_kafka_template_seconds_*` / 少量 `kafka_producer_*`，诊断消费积压只用 `kafka_consumergroup_*`。

## 模板

```bash
# 组 × topic lag
fx-ops idp --profile foneshare prometheus query --promql \
 'sum by (consumergroup, topic)(kafka_consumergroup_lag{job=~"kafka-.*-exporter",k8s_cluster="tke70-k8s1"})' -j

# TopN 分区 lag
fx-ops idp --profile foneshare prometheus query --promql \
 'topk(10, kafka_consumergroup_lag{job=~"kafka-.*-exporter",k8s_cluster="tke70-k8s1",topic!="__consumer_offsets"})' -j
```

看板积压面板另排除 `biz-log-function.*`。预计延迟 = lag / `clamp_min(rate(kafka_consumergroup_current_offset[...]))`。

## TDMQ / CKafka（env-blocked）

以下查询空向量（`result: []`，2026-09-18T08:35Z），**不要编造** `qce_ckafka_*` / `tdmq_kafka_*`：

```bash
fx-ops idp --profile foneshare prometheus query --promql \
 'count by (__name__)({__name__=~"(?i)qce_.*kafka.*|tdmq.*kafka.*|ckafka.*"})' -j

fx-ops idp --profile foneshare prometheus query --promql \
 'count by (__name__)({__name__=~"(?i).*ckafka.*|qce_tdmq.*"})' -j
```

## notifier / dispatcher

`{__name__=~"(?i).*notifier.*"}` foneshare 空向量（2026-09-18T09:55Z 复跑仍 `result: []`）。fast-notifier 以 ClickHouse `notifier_broadcast_ack_dist` 为准。

`{__name__=~"(?i).*dispatcher_.*"}` **不是**空向量：同窗命中 Grafana 告警调度器自身指标 `grafana_alerting_dispatcher_aggregation_groups`、`grafana_alerting_dispatcher_alert_processing_duration_seconds_count`、`grafana_alerting_dispatcher_alert_processing_duration_seconds_sum`（2026-09-18T09:55:27Z）。这不是 fs-mq-dispatcher exporter。排障请用锚定、大小写敏感查询 `{__name__=~"^dispatcher_.*"}`（同窗空向量）。dispatcher 堆积走 `logger.metrics_dist` tag `dispatcher-delay`（Grafana `KYxTQz87k`）与 `biz_log_dispatch_dist.remainNum`。禁止编造 `notifier_*` / `dispatcher_*`。
