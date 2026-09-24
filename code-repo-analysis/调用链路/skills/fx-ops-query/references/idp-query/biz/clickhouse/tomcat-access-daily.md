# tomcat-access-daily

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: Tomcat 访问日志按小时聚合统计表，按应用和 URI 维度汇总每小时请求量及链路追踪信息。

**租户ID字段**: 无

**时间字段**: _time_hour_

---

## 表：tomcat_access_daily_dist

**说明**: Tomcat 访问日志按小时聚合统计表，按应用和 URI 维度汇总每小时请求量及链路追踪信息。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'agg_sla', 'tomcat_access_daily_local', rand()) |
| PARTITION BY | `toYYYYMMDD(_time_hour_)` |
| PRIMARY KEY | `(_time_hour_, app, uri, traceId)` |
| ORDER BY | `(_time_hour_, app, uri, traceId)` |
| TTL | `toDateTime(_time_hour_) + toIntervalDay(30)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_hour_` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_hour_` | DateTime64(3, 'Asia/Shanghai') | 聚合到小时的起始时间 |
| `app` | LowCardinality(String) | 应用名称 |
| `uri` | String | 请求 URI |
| `traceId` | String | 分布式链路追踪 ID |
| `totalCount` | Int64 | 总请求次数 |
| `rpcId` | Nullable(String) | 该 traceId 下的一次 RPC 请求标识。形态 A：层级路径如 0/0.1/1.2.3（旧，逐步废弃）；形态 B：字符串 ID（目标形态，等值匹配；精查时用 traceId + rpcId） |
| `spanId` | Nullable(String) | OpenTelemetry Span ID，标识当前调用跨度（span）的唯一 ID；与 traceId 组合可定位链路中的单个节点 |
| `parentSpanId` | Nullable(String) | OpenTelemetry 父 Span ID，标识发起当前 span 的上游 span；根 span 或缺失上游时通常为空 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 追踪ID | `traceId` |
| 时间 | `_time_hour_` |

### 查询示例

```bash
# 某应用近 24 小时按 URI 访问量
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_hour_, app, uri, sum(totalCount) AS cnt FROM tomcat_access_daily_dist WHERE app = '<APP>' AND _time_hour_ >= now() - INTERVAL 24 HOUR GROUP BY _time_hour_, app, uri ORDER BY cnt DESC LIMIT 50"

# 按 traceId 看聚合命中（再下钻 tomcat_access_dist / app_log_dist）
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_hour_, app, uri, totalCount, traceId, rpcId, spanId FROM tomcat_access_daily_dist WHERE traceId = '<TRACE_ID>' AND _time_hour_ BETWEEN '<T-2h>' AND '<T+1h>' LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
