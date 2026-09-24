# link-eip-data-sync

**方言**: `postgresql`
**说明**: EIP企业信息平台数据同步，对接ERP/OA系统的接口配置及数据收发（库 `eip_data_sync`）
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

> 本 biz **双方言**：未指定 dialect 会 `dialect_required`。Mongo 缓冲见 [mongodb/link-eip-data-sync.md](../mongodb/link-eip-data-sync.md)；总览见 [../link-eip-data-sync.md](../link-eip-data-sync.md)。
> 正确 biz 名是 **`link-eip-data-sync`**。禁止 `eip-data-sync` / `eip_data_sync` / `syncdata`。
> **独立入口**（不是 dialect）：`link-eip-data-sync-1`（`eip_data_sync_1`）、`link-eip-data-sync-747125`（`eip_data_sync_747125`）。
> 查询走 `fx-ops idp query`（IDP 只读/从库路由），禁止直连主库或手写连接串。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns link-eip-data-sync <name> --dialect postgresql -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query link-eip-data-sync --dialect postgresql`（或 `link-eip-data-sync-postgresql`）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables link-eip-data-sync --dialect postgresql -j
fx-ops idp --profile <profile> show columns link-eip-data-sync <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 EI 供 filterHint
fx-ops idp --profile <profile> query link-eip-data-sync --dialect postgresql --sql "<SQL>" -j
```

## 说明

- 默认实例 **没有** `sync_data` / `sync_config` / `sync_sys_config` / `sync_field_variable`。`sync_data` 在 `link-eip-data-sync-1`；`sync_field_variable` 在 `-1` 与 `-747125`。
- 不要和 `link-erp-data-sync` 混淆。
- 表清单以当前 profile 的 `show tables` 为准。

## 统计

- 表级筛选条目: **12**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **12**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `priority_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_error_mappings` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_history_task` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_mappings` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_field_variable_mappings` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_fields_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_fields_history_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail_history` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail_modify_record` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail_snapshot` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
