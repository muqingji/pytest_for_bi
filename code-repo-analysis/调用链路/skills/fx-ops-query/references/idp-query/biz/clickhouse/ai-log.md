# ai-log（AI 业务日志）

> schema_verified_at: 2026-08-01 | platform: v5.10.0
> [!WARNING]
> **platform v5.10.0**：`biz_log_ai_dist` 已列入 `scan.yml` **exclude_names**，并已从 `tables.yaml` / 单表 YAML 移除，**不可查询**。
> 历史原因：底层 Distributed 指向视图 `biz_log_ai_v`（`string1` 误写为 `stirng1`），`SELECT *` 失败。
> 诊断结论须标 **`platform_gap`**；旧名 `ai_usage_detail_log_dist` 同样不存在。

**说明**: 业务 AI 日志，记录模型调用请求/响应、Token 消耗（`total_tokens` / `prompt_tokens` / `completion_tokens`）、对话 messages 等。

**租户ID字段**: `tenantId`

**时间字段**: `_time_second`（分区键，**无尾下划线**）、`createTime`、`stamp`

> [!CAUTION]
> 本表时间列名为 **`_time_second` / `_time_nanosecond`**（与多数 biz-app-log 表的 `_time_second_` **不同**）。拼 SQL 勿混用。

---

## 表：biz_log_ai_dist

### 存储与索引

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed → `biz_log_ai_v`（foneshare: cluster00；其他: cluster01） |
| PARTITION BY | `(logType, toYYYYMMDD(_time_second_))` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数索引 | `idx_trace_id` on `traceId`（platform yaml 登记；当前列交集无 `traceId` 列，勿假设可查） |
| 时间列（查询） | `_time_second`, `createTime`, `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second` | DateTime | 事件写入 ClickHouse 的秒级时间戳（**WHERE 时间窗首选**；列名无尾 `_`） |
| `_time_nanosecond` | DateTime64(9, 'Asia/Shanghai') | 事件写入纳秒时间戳（列名无尾 `_`） |
| `stamp` | DateTime64(3, 'Asia/Shanghai') | 业务时间戳 |
| `tenantId` | String | 租户 ID |
| `userId` | String | 用户 ID |
| `model` | String | AI 模型名称 |
| `action` | String | 操作类型 |
| `caller` | String | 调用方 |
| `messages` | String | 对话消息 JSON |
| `functions` | String | 函数调用定义 JSON |
| `result` | String | 调用结果 |
| `requestLength` | Nullable(Int64) | 请求体长度 |
| `responseLength` | Nullable(Int64) | 响应体长度 |
| `total_tokens` | Nullable(Int64) | 总 Token 数 |
| `prompt_tokens` | Nullable(Int64) | 提示 Token 数 |
| `completion_tokens` | Nullable(Int64) | 补全 Token 数 |
| `createTime` | DateTime64(3, 'Asia/Shanghai') | 记录创建时间 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 用户ID | `userId` |
| 时间 | `_time_second`, `createTime`, `stamp` |

### 查询示例

> **禁止 `SELECT *`**。下列示例仅列出 yaml 列交集内字段；若 query 仍失败，按 [known-gaps.md](./known-gaps.md) 标 `platform_gap`。

```bash
# 查租户 AI 调用（显式列 + 时间窗；注意 _time_second 无尾下划线）
fx-ops idp --profile <profile> query biz-app-log --tenant-id <tenantId> --sql \
  "SELECT _time_second, tenantId, userId, model, total_tokens, prompt_tokens, completion_tokens, action
   FROM biz_log_ai_dist
   WHERE tenantId = '<tenantId>'
     AND _time_second > now() - INTERVAL 1 HOUR
   LIMIT 20" -j

# 按模型统计 Token（短窗）
fx-ops idp --profile <profile> query biz-app-log --tenant-id <tenantId> --sql \
  "SELECT model, count() AS cnt, sum(total_tokens) AS tokens
   FROM biz_log_ai_dist
   WHERE tenantId = '<tenantId>'
     AND _time_second > now() - INTERVAL 1 HOUR
   GROUP BY model
   ORDER BY tokens DESC
   LIMIT 20" -j
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
- ./known-gaps.md - `biz_log_ai_dist` runtimeQueryable 缺口
