# link-eip-data-sync-747125

**方言**: `postgresql`
**说明**: EIP 数据同步大客户 747125 独立库（`eip_data_sync_747125`）
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

> 这是 **独立查询入口**，不是 `link-eip-data-sync` 的 dialect。默认策略库用 `link-eip-data-sync --dialect postgresql`；instance1 用 `link-eip-data-sync-1`。
> 禁止 `eip-data-sync` / `eip_data_sync` / `syncdata`。
> 查询走 `fx-ops idp query`（IDP 只读/从库路由），禁止直连主库或手写连接串。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns link-eip-data-sync-747125 <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query link-eip-data-sync-747125`（方言规则见 ../../../idp-query-sql.md，总览见 [../link-eip-data-sync.md](../link-eip-data-sync.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables link-eip-data-sync-747125 --dialect postgresql -j
fx-ops idp --profile <profile> show columns link-eip-data-sync-747125 <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 EI 供 filterHint
fx-ops idp --profile <profile> query link-eip-data-sync-747125 --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **13**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **13**
- 使用 `$tenant_account` / EA: **0**

本实例有 `sync_field_variable`，无 `sync_data`。默认 `link-eip-data-sync`（postgresql）两者都没有。

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `priority_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_error_mappings` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_history_task` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_mappings` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_field_variable` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_field_variable_mappings` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_fields_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_fields_history_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail_history` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail_modify_record` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail_snapshot` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
