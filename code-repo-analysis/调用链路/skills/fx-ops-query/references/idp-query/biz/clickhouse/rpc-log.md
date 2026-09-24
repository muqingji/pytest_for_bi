# rpc

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: RPC 调用统计汇总表，按 app/module 等维度聚合调用次数、失败数、慢调用与耗时分布；无 interface 字段（接口维度用 module）；时间范围过滤请用 _time_second_

**时间字段**: _time_second_, stamp

---

## 表：rpc_dist

**说明**: RPC 调用统计汇总表，按 app/module 等维度聚合调用次数、失败数、慢调用与耗时分布；无 interface 字段（接口维度用 module）；时间范围过滤请用 _time_second_

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'rpc', rand(); Distributed('cluster01', 'logger', 'rpc', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(120)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime | 日志采集时间（秒级）；时间范围过滤推荐字段（PARTITION BY toYYYYMMDD(_time_second_)） |
| `app` | Nullable(String) | 应用名称 |
| `caller` | Nullable(String) | 调用方IP |
| `consumer` | String |  |
| `failCount` | Nullable(Int32) | 失败次数 |
| `hostname` | Nullable(String) | 主机名 |
| `module` | Nullable(String) | RPC 模块/接口名（按接口维度聚合；本表无 interface 字段，请用 module） |
| `ms1` | Nullable(Int32) | <1ms 请求数 |
| `ms10` | Nullable(Int32) | 1-10ms 请求数 |
| `ms100` | Nullable(Int32) | 10-100ms 请求数 |
| `ms1000` | Nullable(Int32) | 100-1000ms 请求数 |
| `ms10000` | Nullable(Int32) | 1000-10000ms 请求数 |
| `msMore` | Nullable(Int32) | >10000ms 请求数 |
| `profile` | Nullable(String) | 环境标识 |
| `provider` | String |  |
| `proxy` | String |  |
| `server` | Nullable(String) | 服务端地址 |
| `serverName` | String | 服务名称 |
| `slowCount` | Nullable(Int32) | 慢调用次数 |
| `stamp` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 业务统计时间戳；勿用于时间范围过滤（非分区键，WHERE stamp 无法分区裁剪易超时） |
| `totalCost` | Nullable(Int64) | 总耗时(ms) |
| `totalCount` | Nullable(Int32) | 调用总次数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_`, `stamp` |

### 查询示例

```bash
# 查应用 RPC 汇总
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT app, module, sum(totalCount) AS total, sum(failCount) AS fail, sum(slowCount) AS slow FROM rpc_dist WHERE app = '<APP>' AND _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY app, module ORDER BY slow DESC LIMIT 20"

# 按 module 聚合慢调用
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT app, module, sum(totalCount) AS total_calls, sum(failCount) AS total_failures, sum(slowCount) AS total_slow FROM rpc_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND _time_second_ < now() GROUP BY app, module ORDER BY total_slow DESC LIMIT 20"
```

---

## 表：rpc_daily_dist

**说明**: RPC 调用按天聚合统计表，按应用和模块维度汇总调用量、耗时、失败数、慢调用数及分位分布。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_daily', 'rpc_daily_local', rand()) |
| PARTITION BY | `toYYYYMMDD(day)` |
| PRIMARY KEY | `(app, module, day)` |
| ORDER BY | `(app, module, day)` |
| TTL | `day + toIntervalDay(740)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `day` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `day` | Date | 统计日期 |
| `app` | LowCardinality(String) | 应用名称 |
| `module` | LowCardinality(String) | RPC 模块名称 |
| `totalCount` | Int64 | 总调用次数 |
| `totalCost` | Float64 | 总耗时（毫秒） |
| `failCount` | Int64 | 失败调用次数 |
| `slowCount` | Int64 | 慢调用次数 |
| `ms1` | Int64 | 耗时 < 1ms 的调用次数 |
| `ms10` | Int64 | 耗时 1-10ms 的调用次数 |
| `ms100` | Int64 | 耗时 10-100ms 的调用次数 |
| `ms1000` | Int64 | 耗时 100-1000ms 的调用次数 |
| `ms10000` | Int64 | 耗时 1-10s 的调用次数 |
| `msMore` | Int64 | 耗时 > 10s 的调用次数 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `day` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM rpc_daily_dist WHERE day > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
