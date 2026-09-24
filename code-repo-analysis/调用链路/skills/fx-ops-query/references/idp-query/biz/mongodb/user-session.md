# user-session

**方言**: `mongodb` 
**说明**: 用户登录会话管理（fs-active-session-provider），维护活跃会话、过期策略、终端信息 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；filter 中建议带 `EI` 缩小范围）


下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns user-session <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query user-session`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 统计

- 表级筛选条目: **1**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **1**（可选，建议带以缩小范围）
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；传 `--tenant-id <EI>` 时自动替换。**不传时查询整个集合**（单库场景适用）。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `FSActiveSessions` | EI | `CT` / `ET` / `LAT` | `{"EI":$tenant_id}` |

## 推荐查询（不传 --tenant-id）

```bash
fx-ops idp --profile <profile> query user-session \
  --collection FSActiveSessions \
  --filter '{"SId":"<session_uuid>"}' \
  --limit 20 -j
```

## 注意事项

1. **`EI` 类型为 int**：filter 中 `$tenant_id` 不加引号，即 `{"EI":85494}` 而非 `{"EI":"85494"}`。
2. **`AET` 恒为哨兵值**：全表 `AET = 2998-12-31`（永不过期标记），**禁止用于时间范围过滤**。有效时间字段为 `CT`（创建）、`ET`（过期，有索引）、`LAT`（最后访问）。
3. **`SId` 为 UNIQUE 索引**：查单会话用 `{"SId":"<uuid>"}` 最高效。
4. **`ET` 有过期索引 `ET_1`**：查"已过期会话"用 `{"ET":{"$lt":{"$date":"<ISO_DATE>"}}}`。
5. **敏感字段**：`M`（手机号，PII）、`PVT`（token/凭证），查询时**禁止 `SELECT *`**，仅取所需字段。
