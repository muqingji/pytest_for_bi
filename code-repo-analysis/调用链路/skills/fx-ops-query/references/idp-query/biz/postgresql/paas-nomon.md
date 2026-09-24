# paas-nomon

**方言**: `postgresql` 
**说明**: PaaS数据库监控扫描任务管理，负责扫描任务调度、执行日志及历史记录追踪 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns paas-nomon <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query paas-nomon`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables paas-nomon --dialect postgresql -j
fx-ops idp --profile <profile> show columns paas-nomon <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query paas-nomon --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **5**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **5**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `c_task` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `c_task_log` | tenant_id | `start_time` | `tenant_id`=$tenant_id |
| `nomon_history` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `nomon_task` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `scan_db_task` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
