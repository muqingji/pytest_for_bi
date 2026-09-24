# link-erp-data-sync

**方言**: `postgresql` 
**说明**: ERP数据同步服务，管理同步配置、同步策略、字段映射及历史同步任务 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns link-erp-data-sync <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query link-erp-data-sync`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables link-erp-data-sync --dialect postgresql -j
fx-ops idp --profile <profile> show columns link-erp-data-sync <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query link-erp-data-sync --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **44**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **43**
- 使用 `$tenant_account` / EA: **1**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `erp_alarm_rule` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_connect_info` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_custom_interface` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_data_feature` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_db_proxy_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_debug_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_feature_sync` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_field_data_mapping` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_field_extend` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_history_data_task` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_interface_log` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_k3_ultimate_token` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_obj_groovy` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_obj_id_number_mapping` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_obj_interface_checked` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_object` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_object_field` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_object_relationship` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_ploy_shard` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_polling_monitor` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `erp_processed_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_push_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_push_identify` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_resync_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_sync_time` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_tenant_configuration` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_u8_eai_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `erp_user_operation_log` | tenant_id | `-` | `tenant_id`=$tenant_id |
| `oa_connect_info` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `oa_flow_mq_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `oa_object_field` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `oa_sync_api` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `oa_sync_log` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `relation_manage_group` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_*` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_\d+` | tenant_id | `update_time` | `tenant_id`='$tenant_id' |
| `sync_data_mappings_74164` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_data_mappings_\d+` | tenant_id | `update_time` | `tenant_id`='$tenant_id' |
| `sync_ploy` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sync_ploy_detail` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `tb_material` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `wechat_interface_license` | tenant_id | `create_time` | `tenant_id`=$tenant_id |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `qyweixin_business_info_bind` | fs_ea | `update_time` | `fs_ea`=$tenant_account |

## 正则/通配表名

下列规则按 **正则或通配** 匹配表名；先用 `table list` 确认实际表名。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `sync_data_*` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
