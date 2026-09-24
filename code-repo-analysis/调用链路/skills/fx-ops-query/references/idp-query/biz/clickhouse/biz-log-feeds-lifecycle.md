# biz-log-feeds-lifecycle

> schema_verified_at: 2026-08-05 | platform: tenant-filters YAML | runtime: foneshare/ale `show columns` **404**（platform_gap）

**说明**: Feed 动态生命周期日志分布式表，记录 Feed 数据从创建、流转、修改到归档销毁的完整生命轨迹。

**租户ID字段**: `tenantId`

**时间字段**: `_time_second_`, `createTime`

> [!CAUTION]
> 当前默认 profile（`foneshare`）与 `ale` 上 `show tables/columns biz-app-log biz_log_feeds_lifecycle_dist` 返回 **Table not found**。
> 配置仓库（tenant-filters）有表 ≠ 当前 profile 可查。查询前先：
>
> ```bash
> fx-ops idp --profile <profile> show tables biz-app-log -j
> fx-ops idp --profile <profile> show columns biz-app-log biz_log_feeds_lifecycle_dist -j
> ```
>
> 若 404：结论标 `status=platform_gap`，`table=biz_log_feeds_lifecycle_dist`，不要改扫其他明细表赌数据。字段以下方 YAML 快照为准。

---

## 表：biz_log_feeds_lifecycle_dist

**说明**: Feed 动态生命周期日志分布式表，记录 Feed 数据从创建、流转、修改到归档销毁的完整生命轨迹。

### 存储与索引

> schema_verified_at: 2026-08-05 | source: tenant-filters/clickhouse/biz-app-log/biz_log_feeds_lifecycle_dist.yaml

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster00', 'logger', 'biz_log_feeds_lifecycle', rand(); Distributed('cluster01', 'logger', 'biz_log_feeds_lifecycle', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `_time_nanosecond_` |
| ORDER BY | `_time_nanosecond_` |
| TTL | `toDateTime(_time_second_) + toIntervalDay(90)` |
| 时间列（查询） | `_time_second_`, `createTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_nanosecond_` | `DateTime64(9, 'Asia/Shanghai')` | 事件写入 ClickHouse 的纳秒级时间戳 |
| `_time_second_` | `DateTime` | 事件写入 ClickHouse 的秒级时间戳 |
| `allReceiptId` | `Array(Int32)` | 所有需回执的员工ID列表（旧字段） |
| `allReceiptIdCount` | `String` |  |
| `allReceiptIdList` | `String` |  |
| `alreadyReceiptId` | `Array(Int32)` | 已回执的员工ID列表（旧字段） |
| `alreadyReceiptIdCount` | `String` |  |
| `alreadyReceiptIdList` | `String` |  |
| `atDepartmentId` | `Array(Int32)` | 被@提及的部门ID列表（旧字段） |
| `atDepartmentIdCount` | `String` |  |
| `atDepartmentIdList` | `String` |  |
| `atEmployeeId` | `Array(Int32)` | 被@提及的员工ID列表（旧字段） |
| `atEmployeeIdCount` | `String` |  |
| `atEmployeeIdList` | `String` |  |
| `attachments` | `Array(String)` | Feed附件列表 |
| `attachmentsCount` | `String` |  |
| `attachmentsList` | `String` |  |
| `bizAllId` | `Array(Int32)` | 业务allid |
| `bizAllIdCount` | `String` |  |
| `bizAllIdList` | `String` |  |
| `bizExecutedId` | `Array(Int32)` | 业务executedid |
| `bizExecutedIdCount` | `String` |  |
| `bizExecutedIdList` | `String` |  |
| `bizExecutingId` | `Array(Int32)` | 业务executingid |
| `bizExecutingIdCount` | `String` |  |
| `bizExecutingIdList` | `String` |  |
| `bizStatus` | `Nullable(Int32)` | 业务status |
| `createTime` | `Nullable(DateTime64(3, 'Asia/Shanghai'))` | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `crmObjects` | `Array(String)` | 客户关系管理(CRM)objects |
| `crmObjectsCount` | `String` |  |
| `crmObjectsList` | `String` |  |
| `currentTime` | `Nullable(DateTime64(3, 'Asia/Shanghai'))` | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `eventId` | `String` |  |
| `feedId` | `Nullable(Int64)` | 动态/Feedid |
| `feedType` | `Nullable(String)` | 动态/Feedtype |
| `followEmployeeId` | `Array(Int32)` | 关注此Feed的员工ID列表（旧字段） |
| `followEmployeeIdCount` | `String` |  |
| `followEmployeeIdList` | `String` |  |
| `importerId` | `Nullable(Int32)` | 导入者用户ID |
| `importTime` | `Nullable(DateTime64(3, 'Asia/Shanghai'))` | 记录创建或发生时间（格式：YYYY-MM-DD HH:mm:ss） |
| `leadingContent` | `Nullable(String)` | Feed引导/摘要内容 |
| `operation` | `Nullable(String)` | 操作类型（如create/update/delete/转发等） |
| `outTenantId` | `Nullable(Int64)` | out租户id |
| `outUserId` | `Nullable(Int64)` | 外部/跨租户用户ID |
| `permissionEmployeeId` | `Array(Int32)` | 有权限查看此Feed的员工ID列表（旧字段） |
| `permissionEmployeeIdCount` | `String` |  |
| `permissionEmployeeIdList` | `String` |  |
| `rangeDepartmentId` | `Array(Int32)` | Feed可见范围内的部门ID列表（旧字段） |
| `rangeDepartmentIdCount` | `String` |  |
| `rangeDepartmentIdList` | `String` |  |
| `rangeEmployeeId` | `Array(Int32)` | Feed可见范围内的员工ID列表（旧字段） |
| `rangeEmployeeIdCount` | `String` |  |
| `rangeEmployeeIdList` | `String` |  |
| `senderId` | `Nullable(Int64)` | 发送者/发布者用户ID |
| `sendingFrom` | `Nullable(String)` | 发送来源（如客户端类型、平台标识） |
| `status` | `Nullable(Int32)` | 状态码或状态标识（如 200, 500, 或 SUCCESS, FAILED） |
| `tenantId` | `Nullable(String)` | 租户/企业 ID |
| `topics` | `Array(String)` | 话题/Topic列表 |
| `topicsCount` | `String` |  |
| `topicsList` | `String` |  |
| `uuid` | `Nullable(String)` | 全局唯一标识符（UUID） |
| `version` | `Nullable(Int64)` | 版本 |
| `waitingReceiptId` | `Array(Int32)` | 等待回执的员工ID列表（旧字段） |
| `waitingReceiptIdCount` | `String` |  |
| `waitingReceiptIdList` | `String` |  |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户 | `tenantId` |
| 时间 | `_time_second_`, `createTime` |

### 查询示例

```bash
# 截图反查 feedId：租户 + 时间窗 + 正文关键词
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT
  feedId,
  senderId,
  tenantId,
  createTime,
  currentTime,
  operation,
  feedType,
  sendingFrom,
  substring(leadingContent, 1, 800) AS leadingContent,
  topics,
  atEmployeeId,
  atDepartmentId
FROM biz_log_feeds_lifecycle_dist
WHERE tenantId = '<tenant_id>'
  AND _time_second_ >= toDateTime('<start_time>')
  AND _time_second_ <= toDateTime('<end_time>')
  AND (
    leadingContent LIKE '%<keyword_1>%'
    OR leadingContent LIKE '%<keyword_2>%'
  )
ORDER BY _time_second_ DESC
LIMIT 50
" -j

# 按 feedId 看生命周期事件
fx-ops idp --profile <profile> query biz-app-log --sql "
SELECT _time_second_, tenantId, feedId, operation, feedType, senderId,
       status, substring(leadingContent, 1, 400) AS leadingContent
FROM biz_log_feeds_lifecycle_dist
WHERE tenantId = '<tenant_id>'
  AND feedId = <feedId>
  AND _time_second_ >= now() - INTERVAL 24 HOUR
ORDER BY _time_second_ DESC
LIMIT 50
" -j
```

---

## 相关文档

- [index.md](./index.md) - ClickHouse 表定义索引
- [known-gaps.md](./known-gaps.md) - 运行时缺口
- [../postgresql/feed.md](../postgresql/feed.md) - PG 工作圈主库 schema
