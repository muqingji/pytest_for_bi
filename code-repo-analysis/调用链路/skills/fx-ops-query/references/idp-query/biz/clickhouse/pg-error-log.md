# pg-error-log（PostgreSQL错误日志）

> schema_verified_at: 2026-08-01 | platform: v5.10.0
> [!WARNING]
> **已废弃 / 不可查询**：platform v4.37.0 已将 `pg_error_log` 从 tenant-filters 移除（variant `all_inactive` / scan 排除）。请改用 [log-error.md](./log-error.md)。

**说明**: PostgreSQL 底层引擎报错日志，存储物理数据库抛出的严重语法、连接或资源报错

**租户ID字段**: 无

**时间字段**: `_time_second_`

---

## 表：pg_error_log

### 存储与索引

| 项 | 值 |
| --- | --- |
| 状态 | **已废弃**，platform 无 `pg_error_log.yaml` |

### 字段定义（历史参考，勿查询）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime64(3) | 日志采集时间（秒级） |
| `process_id` | UInt32 | PG进程ID |
| `session_id` | String | PG会话ID |
| `session_line_number` | UInt32 | 会话行号 |
| `transaction_id` | UInt32 | 事务ID |
| `virtual_transaction_id` | String | 虚拟事务ID |
| `user_name` | String | 数据库用户名 |
| `database_name` | String | 数据库名称 |
| `app_name` | String | 应用名称 |
| `remote_host` | String | 远程客户端主机地址 |
| `level` | String | 日志级别 |
| `message` | String | 日志消息或异常信息 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 数据库 | `database_name` |
| 应用名 | `app_name` |
| 用户 | `user_name` |
| 事务ID | `transaction_id` |
| 时间 | `_time_second_` |

### 查询示例

```bash
# 查询近1小时PG ERROR级别报错
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT _time_second_, database_name, app_name, user_name, level, message FROM pg_error_log WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND level = 'ERROR' ORDER BY _time_second_ DESC LIMIT 50"

# 统计各数据库错误分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT database_name, level, COUNT(*) as cnt FROM pg_error_log WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY database_name, level ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
- ./biz-log-pg-lock.md - PG锁日志
