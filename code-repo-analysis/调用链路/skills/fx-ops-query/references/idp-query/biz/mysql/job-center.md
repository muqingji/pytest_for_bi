# job-center

**方言**: `mysql` 
**说明**: 任务中心，管理数据导入导出异步任务 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns job-center <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query job-center`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables job-center --dialect mysql -j
fx-ops idp --profile <profile> show columns job-center <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query job-center --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **3**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **3**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `export_job` | enterprise_id | `create_date` | `enterprise_id`=$tenant_id |
| `import_job` | enterprise_id | `create_date` | `enterprise_id`=$tenant_id |
| `import_job_relation` | enterprise_id | `create_date` | `enterprise_id`=$tenant_id |
