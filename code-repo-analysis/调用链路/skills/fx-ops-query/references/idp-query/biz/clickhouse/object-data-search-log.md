# object-data-search-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 对象实体数据全文搜索日志视图分布式表，分析低代码实体搜索的检索词、分词耗时与召回率。

**租户ID字段**: `tenantId`

**时间字段**: _time_second_, createTime

---

## 表：object_data_search_log_v_dist

**说明**: 对象实体数据全文搜索日志视图分布式表，分析低代码实体搜索的检索词、分词耗时与召回率。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'object_data_search_log_v', rand(); Distributed('cluster01', 'logger', 'object_data_search_log_v', rand() |
| PARTITION BY | `(logType, toYYYYMMDD(_time_second_))` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 事件写入 ClickHouse 的秒级时间戳 |
| `action` | LowCardinality(String) | 操作 |
| `appName` | LowCardinality(String) | 应用name |
| `clusterName` | LowCardinality(String) | 集群名称 |
| `cost` | Int32 | 操作耗时，单位为毫秒 (ms) |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `error` | String | 错误信息、异常堆栈或异常详情 |
| `extra` | String | 附加元数据或上下文的 JSON 结构数据 |
| `indices` | String | 索引列表(ES索引) |
| `message` | String | 日志消息或异常信息内容 |
| `num` | Int64 | 数量或统计计数值 |
| `objectApiName` | String | 对象/实体 API 名称，例如: ProductObj |
| `parameters` | String | 请求参数或上下文的 JSON 结构数据 |
| `profile` | LowCardinality(String) | 运行环境配置标识（如 prod, test, dev, ale 等） |
| `serverIp` | String | 服务端IP地址 |
| `stamp` | DateTime64(3, 'Asia/Shanghai') | 事件发生的时间戳 |
| `tenantId` | String | 租户/企业 ID |
| `traceId` | String | 分布式链路追踪 ID (Trace ID)，用于串联同一次请求的所有日志 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 追踪ID | `traceId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT * FROM object_data_search_log_v_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
