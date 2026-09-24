# bi-stat

**方言**: `mongodb` 
**说明**: BI统计分析模块，管理统计字段的定义与配置 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns bi-stat <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query bi-stat`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables bi-stat --dialect mongodb -j
fx-ops idp --profile <profile> show columns bi-stat <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query bi-stat --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **1**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **1**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `stat_field` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
