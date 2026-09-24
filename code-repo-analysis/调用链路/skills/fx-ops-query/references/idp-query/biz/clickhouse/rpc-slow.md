# rpc-slow

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: RPC 慢调用统计汇总表，结构与 rpc_dist 相同，专门记录慢调用的聚合数据；无 interface 字段（用 module）；时间范围过滤请用 _time_second_

**租户ID字段**: 无

**时间字段**: _time_second_, stamp

---

## 表：rpc_slow

**说明**: RPC 慢调用统计汇总表，结构与 rpc_dist 相同，专门记录慢调用的聚合数据；无 interface 字段（用 module）；时间范围过滤请用 _time_second_

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | `Distributed('cluster00', 'logger', 'rpc_slow_local', rand())` |
| PARTITION BY | 待从底层 `rpc_slow_local` local 表核验 |
| PRIMARY KEY | 待从底层 `rpc_slow_local` local 表核验 |
| ORDER BY | 待从底层 `rpc_slow_local` local 表核验 |
| TTL | 待从底层 `rpc_slow_local` local 表核验 |
| 跳数/二级索引 | — |
| 时间列（查询） | `_time_second_`, `stamp` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `profile` | Nullable(String) | 环境标识 |
| `server` | Nullable(String) | 服务端地址 |
| `module` | Nullable(String) | RPC 模块/接口名（按接口维度聚合；本表无 interface 字段，请用 module） |
| `caller` | Nullable(String) | 调用方IP |
| `hostname` | Nullable(String) | 主机名 |
| `totalCount` | Nullable(Int32) | 调用总次数 |
| `failCount` | Nullable(Int32) | 失败次数 |
| `slowCount` | Nullable(Int32) | 慢调用次数 |
| `totalCost` | Nullable(Int64) | 总耗时(ms) |
| `ms1000` | Nullable(Int32) | 100-1000ms 请求数 |
| `ms10000` | Nullable(Int32) | 1000-10000ms 请求数 |
| `msMore` | Nullable(Int32) | >10000ms 请求数 |
| `consumer` | Nullable(String) | 消费者 |
| `stamp` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 业务统计时间戳；勿用于时间范围过滤（非分区键，WHERE stamp 无法分区裁剪易超时） |
| `app` | Nullable(String) | 应用名称 |
| `ms10` | Nullable(Int32) | 1-10ms 请求数 |
| `ms100` | Nullable(Int32) | 10-100ms 请求数 |
| `ms1` | Nullable(Int32) | <1ms 请求数 |
| `provider` | Nullable(String) | 提供者 |
| `_time_second_` | DateTime | 日志采集时间（秒级）；时间范围过滤推荐字段（PARTITION BY toYYYYMMDD(_time_second_)） |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `serverName` | String | 服务名称 |
| `proxy` | Nullable(String) | 代理地址 |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 时间 | `_time_second_`, `stamp` |

### 查询示例

```bash
# 查询近1小时RPC慢调用模块统计
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT stamp, app, module, caller, totalCount, failCount, slowCount, totalCost FROM rpc_slow_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR AND slowCount > 0 ORDER BY slowCount DESC LIMIT 20"

# 按模块查看耗时分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT module, COUNT(*) as cnt, sum(totalCount) as total, sum(failCount) as fails, sum(msMore) as super_slow FROM rpc_slow_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY module HAVING fails > 0 ORDER BY fails DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
