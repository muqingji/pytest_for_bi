# biz-job-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 业务定时任务执行日志分布式表，存储系统中各类后台定时 Job（如 Task/Flow）的启动、耗时与执行结果。

**租户ID字段**: `tenantId`

**时间字段**: _time_second_, createTime

---

## 表：biz_job_log_dist

**说明**: 业务定时任务执行日志分布式表，存储系统中各类后台定时 Job（如 Task/Flow）的启动、耗时与执行结果。

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_job_log', rand(); Distributed('cluster01', 'logger', 'biz_job_log', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | DateTime | 事件写入 ClickHouse 的秒级时间戳 |
| `appName` | Nullable(String) | 应用name |
| `cost` | Nullable(Int64) | 操作耗时，单位为毫秒 (ms) |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 记录创建时间 |
| `error` | Nullable(String) | 错误信息、异常堆栈或异常详情 |
| `extra` | Nullable(String) | 扩展信息 |
| `jobName` | Nullable(String) | 任务/定时任务name |
| `message` | Nullable(String) | 日志消息或异常信息内容 |
| `objectApiName` | Nullable(String) | 对象/实体接口name |
| `objectId` | Nullable(String) | 对象/实体id |
| `profile` | Nullable(String) | 运行环境配置标识（如 prod, test, dev, ale 等） |
| `status` | Nullable(String) | 状态码或状态标识（如 200, 500, 或 SUCCESS, FAILED） |
| `tenantId` | Nullable(String) | 租户/企业 ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
# 查询失败的业务Job
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, tenantId, appName, jobName, status, error, cost FROM biz_job_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND status = 'FAILED' ORDER BY _time_second_ DESC LIMIT 50"

# 统计Job耗时TOP20
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT jobName, COUNT(*) as cnt, avg(cost) as avg_cost, max(cost) as max_cost FROM biz_job_log_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY jobName ORDER BY avg_cost DESC LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
