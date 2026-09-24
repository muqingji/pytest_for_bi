# metadata-recycle

**方言**: `postgresql` 
**说明**: 元数据回收站，存储待回收的预删除元数据记录 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns metadata-recycle <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query metadata-recycle`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables metadata-recycle --dialect postgresql -j
fx-ops idp --profile <profile> show columns metadata-recycle <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query metadata-recycle --sql "<SQL>" -j
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
| `mt_pre_recycle` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
