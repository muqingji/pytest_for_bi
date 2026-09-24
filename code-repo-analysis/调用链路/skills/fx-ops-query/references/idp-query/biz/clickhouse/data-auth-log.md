# data-auth-log

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**说明**: 数据权限查询日志，记录用户对 CRM 对象的数据权限验证结果，包含各类权限规则（CRM、部门、团队、临时授权等）

**租户ID字段**: `tenantId`

**时间字段**: _time_second_, queryTime

---

## 表：data_auth_log_dist

**说明**: 数据权限查询日志，记录用户对 CRM 对象的数据权限验证结果，包含各类权限规则（CRM、部门、团队、临时授权等）

### 存储与索引

> schema_verified_at: 2026-08-01 | platform: v5.10.0

| 项 | 值 |
| --- | --- |
| ENGINE | Distributed('cluster01', 'logger', 'data_auth_log_local', rand() |
| PARTITION BY | `toYYYYMMDD(_time_second_)` |
| PRIMARY KEY | `(_time_second_, tenantId, dataId, describeApiName, queryTime)` |
| ORDER BY | `(_time_second_, tenantId, dataId, describeApiName, queryTime)` |
| TTL | `_time_second_ + toIntervalDay(90)` |
| 跳数/二级索引 | **INDEX**: |
| 时间列（查询） | `_time_second_`, `queryTime` |

### 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `_time_second_` | DateTime | 记录时间 |
| `allAuth` | String |  |
| `basicAuth` | String |  |
| `crmAuth` | String |  |
| `dataId` | String | 数据ID |
| `dataOwnDeptAuth` | String |  |
| `dataShareAuth` | String |  |
| `deptRuleAuth` | String |  |
| `deptTeamAuth` | String |  |
| `describeApiName` | String | 对象描述 API 名称 |
| `dimAuth` | String |  |
| `outTenantId` | String |  |
| `outUserId` | String |  |
| `queryTime` | DateTime | 查询时间 |
| `teamAuth` | String |  |
| `temporaryAuth` | String |  |
| `tenantId` | String | 租户ID |
| `userId` | Nullable(String) | 用户ID |

### 索引字段

| 概念 | 字段 |
| --- | --- |
| 租户ID | `tenantId` |
| 用户ID | `userId` |
| 时间 | `_time_second_`, `queryTime` |

### 查询示例

```bash
# 查询租户数据权限日志
fx-ops idp --profile <profile> query biz-app-log --tenant-id 1 --sql "SELECT _time_second_, tenantId, userId, describeApiName, crmAuth FROM data_auth_log_dist WHERE _time_second_ > now() - INTERVAL 1 HOUR LIMIT 20"
```

---

## 相关文档

- ./index.md - ClickHouse 表定义索引
