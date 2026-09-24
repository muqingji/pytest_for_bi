# sync-data-error

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 数据同步错误明细表，记录每次同步失败的具体错误信息

**租户ID字段**: `tenantId`, `ea`

**时间字段**: _time_second_, createTime

---

## 表：sync_data_error_dist

**说明**: 数据同步错误明细表，记录每次同步失败的具体错误信息

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'sync_data_error', rand(); Distributed('cluster01', 'logger', 'sync_data_error', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | DateTime64(9, 'Asia/Shanghai') | 日志采集时间（纳秒级） |
| `_time_second_` | DateTime('Asia/Shanghai') | 日志采集时间（秒级） |
| `appName` | String | 应用名称 |
| `createTime` | Nullable(DateTime64(3, 'Asia/Shanghai')) | 创建时间 |
| `dataId` | String | 数据ID |
| `destObjApiName` | String | 目标对象API名称 |
| `ea` | String | 租户账号 |
| `errorCode` | String | 错误码 |
| `errorMsg` | String | 错误信息 |
| `serverIp` | String | 服务器IP |
| `sourceObjApiName` | String | 源对象API名称 |
| `syncDataId` | String | 同步数据ID |
| `syncLogId` | String | 同步日志ID |
| `syncPloyDetailSnapshotId` | String | 同步策略详情快照ID |
| `tenantId` | String | 租户ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 租户账号 | `ea` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
# 查询某租户近1小时同步错误
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT createTime, tenantId, sourceObjApiName, destObjApiName, errorCode, errorMsg, dataId FROM sync_data_error_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR ORDER BY createTime DESC LIMIT 50"

# 按同步方向统计错误分布
fx-ops idp --profile <profile> query biz-app-log --sql "SELECT sourceObjApiName, destObjApiName, errorCode, COUNT(*) as cnt FROM sync_data_error_dist WHERE _time_second_ >= now() - INTERVAL 1 HOUR GROUP BY sourceObjApiName, destObjApiName, errorCode ORDER BY cnt DESC"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
