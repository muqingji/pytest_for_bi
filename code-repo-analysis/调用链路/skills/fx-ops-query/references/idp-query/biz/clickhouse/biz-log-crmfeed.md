# biz-log-crmfeed

> schema_verified_at: 2026-08-05 | platform: tenant-filters YAML | runtime: foneshare/ale `show columns` **404**（platform_gap）

**说明**: CRM 动态Feed操作日志分布式表，存储客户关系管理系统中动态消息、Feed 流的生成与流转详情。

**租户ID字段**: `ea`（keyFields.tenantAccount）；列上另有 `ei`

**时间字段**: `_time_second_`, `createTime`

> [!CAUTION]
> 当前默认 profile（`foneshare`）与 `ale` 上 `show tables/columns biz-app-log biz_log_crmfeed_dist` 返回 **Table not found**。
> 配置仓库（tenant-filters）有表 ≠ 当前 profile 可查。查询前先：
>
> ```bash
> fx-ops idp --profile <profile> show tables biz-app-log -j
> fx-ops idp --profile <profile> show columns biz-app-log biz_log_crmfeed_dist -j
> ```
>
> 若 404：结论标 `status=platform_gap`，`table=biz_log_crmfeed_dist`，不要改扫其他明细表赌数据。字段以下方 YAML 快照为准。

---

## 表：biz_log_crmfeed_dist

**说明**: CRM 动态Feed操作日志分布式表，存储客户关系管理系统中动态消息、Feed 流的生成与流转详情。

### 存储与索引

> schema_verified_at: 2026-08-05 | source: tenant-filters/clickhouse/biz-app-log/biz_log_crmfeed_dist.yaml

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_crmfeed', rand(); Distributed('cluster01', 'logger', 'biz_log_crmfeed', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | `DateTime64(9, 'Asia/Shanghai')` | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | `DateTime('Asia/Shanghai')` | 事件写入 ClickHouse 的秒级时间戳 |
| `cost` | `Int32` | 操作耗时，单位为毫秒 (ms) |
| `createTime` | `Nullable(DateTime64(3, 'Asia/Shanghai'))` | 记录创建时间 |
| `ea` | `String` | 企业账号/租户账号名称 |
| `ei` | `String` | 企业唯一标识 ID (Enterprise ID) |
| `parentSpanId` | `String` |  |
| `rpcId` | `String` |  |
| `spanId` | `String` |  |
| `traceId` | `String` | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户 | `ea` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
# 按企业账号 + 时间窗抽样
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT _time_second_, ea, ei, cost, createTime, traceId, rpcId, spanId
FROM biz_log_crmfeed_dist
WHERE ea = '<EA>'
  AND _time_second_ >= now() - INTERVAL 1 HOUR
ORDER BY _time_second_ DESC
LIMIT 50
" -j

# 按 traceId（必须带时间窗）
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT _time_second_, ea, ei, cost, createTime, traceId, rpcId
FROM biz_log_crmfeed_dist
WHERE traceId = '<traceId>'
  AND _time_second_ >= now() - INTERVAL 6 HOUR
LIMIT 50
" -j
```

---

## 相关文档

- [index.md](./index.md) - ClickHouse 表定义索引
- [known-gaps.md](./known-gaps.md) - 运行时缺口
- [../postgresql/feed.md](../postgresql/feed.md) - PG 工作圈主库 schema
