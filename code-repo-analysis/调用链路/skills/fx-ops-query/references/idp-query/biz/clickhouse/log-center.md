# log-center

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 日志中心统一入口日志分布式表，存储日志收集层（Fluentbit/Logstash）自身状态与传输速率。

**租户ID字段**: 无（日志中心为基础设施层日志，不含租户信息）

**时间字段**: _time_second_

---

## 表：log_center_dist

**说明**: 日志中心统一入口日志分布式表，存储日志收集层（Fluentbit/Logstash）自身状态与传输速率。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'log_center_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(_time_second_, service_name, log_type, host_ip)` |
| ORDER BY | `(_time_second_, service_name, log_type, host_ip)` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3) | 事件写入 ClickHouse 的秒级时间戳 |
| `host_ip` | LowCardinality(String) | 主机IP地址 |
| `log_type` | LowCardinality(String) | 日志type |
| `msg` | String | 日志主体消息内容 |
| `service_name` | LowCardinality(String) | 服务名称 |
| `source_file` | String | source文件 |
| `tags` | Nullable(String) | 标签 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM log_center_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
