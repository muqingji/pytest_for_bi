# marketing-spread

**方言**: `mongodb` 
**说明**: 营销推广模块，记录用户营销行为统计数据 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns marketing-spread <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query marketing-spread`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables marketing-spread --dialect mongodb -j
fx-ops idp --profile <profile> show columns marketing-spread <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query marketing-spread --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **1**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **1**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `UserMarketingActionStatisticMongoEntity` | ea | `updateTime` | `{"ea":"$tenant_account"}` |
