# bi-system

**方言**: `postgresql` 
**说明**: BI系统数据同步与聚合引擎，负责元数据拓扑、聚合规则及调度任务管理 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns bi-system <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query bi-system`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables bi-system --dialect postgresql -j
fx-ops idp --profile <profile> show columns bi-system <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query bi-system --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **106**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **106**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `agg_rule` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `agg_rule_gray` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_agg_sync_info` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_data_sync_log` | tenant_id | `start_time` | `tenant_id`=$tenant_id |
| `bi_enterprise_knowledge` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_database` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_describe` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_describe_merge` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_detail` | tenant_id | `sys_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_dim_table_lang` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_dimension` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_field` | tenant_id | `sys_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_field_merge` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `bi_mt_measure` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_topology_describe` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_topology_status` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_topology_table` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_mt_topology_table_merge` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `bi_scheduler_task` | ei | `create_time` | `ei`=$tenant_id |
| `bi_user_profile` | ei | `create_time` | `ei`=$tenant_id |
| `bi_user_view_favorites` | tenant_id | `sys_modified_time` | `tenant_id`=$tenant_id |
| `bi_user_view_history` | tenant_id | `sys_modified_time` | `tenant_id`=$tenant_id |
| `bill_board_config` | ei | `update_time` | `ei`=$tenant_id |
| `board_category` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `chart_permission` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `chart_private_permission` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `custom_rpt_view_field` | ei | `update_time` | `ei`=$tenant_id |
| `dash_board` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `dash_board_component` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `dash_board_config` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `dash_board_customize_filter` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `dash_board_defined_style` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `dash_board_global_filter_config` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `dash_board_group` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `dash_board_view` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `db_migrate_info` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `db_table_sync_info` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `diff_field_record` | tenant_id | `-` | `tenant_id`=$tenant_id |
| `dim_rule` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `dim_rule_gray_diff` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `dim_sys_enum` | ei | `-` | `ei`=$tenant_id |
| `enterprise_config` | ei | `update_time` | `ei`=$tenant_id |
| `enterprise_info` | enterprise_id | `end_time` | `enterprise_id`=$tenant_id |
| `fc_func` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `fc_func_access` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `fc_role` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `fc_user_role` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `global_filter_config` | ei | `update_time` | `ei`=$tenant_id |
| `goal_rule` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `goal_rule_apply_circle` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `goal_rule_detail` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `large_wide_table_config` | tenant_id | `sys_modified_time` | `tenant_id`=$tenant_id |
| `large_wide_table_data_source` | tenant_id | `sys_modified_time` | `tenant_id`=$tenant_id |
| `md_field` | ei | `update_time` | `ei`=$tenant_id |
| `mt_country_area_info` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `paas2bi_task` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `pivot_rpt_view_field` | ei | `update_time` | `ei`=$tenant_id |
| `predefined_board` | ei | `update_time` | `ei`=$tenant_id |
| `reconciliation_rule` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `regular_deletion` | ei | `update_time` | `ei`=$tenant_id |
| `resource_lock` | ei | `update_time` | `ei`=$tenant_id |
| `rpt_category` | ei | `update_time` | `ei`=$tenant_id |
| `rpt_filter` | ei | `update_time` | `ei`=$tenant_id |
| `rpt_view` | ei | `update_time` | `ei`=$tenant_id |
| `rpt_view_field` | ei | `update_time` | `ei`=$tenant_id |
| `stat_agg_calc_field` | ei | `update_time` | `ei`=$tenant_id |
| `stat_charts_relationship` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `stat_field` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `stat_field_gray` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `stat_field_gray_diff` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `stat_field_level` | ei | `update_time` | `ei`=$tenant_id |
| `stat_schema` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `stat_schema_gray` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `stat_schema_gray_diff` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `stat_template` | ei | `update_time` | `ei`=$tenant_id |
| `stat_template_agg_calc_field` | ei | `update_time` | `ei`=$tenant_id |
| `stat_template_field` | ei | `update_time` | `ei`=$tenant_id |
| `stat_template_filter` | ei | `update_time` | `ei`=$tenant_id |
| `stat_template_property` | ei | `update_time` | `ei`=$tenant_id |
| `stat_view` | ei | `update_time` | `ei`=$tenant_id |
| `stat_view_field` | ei | `update_time` | `ei`=$tenant_id |
| `stat_view_filter` | ei | `update_time` | `ei`=$tenant_id |
| `stat_view_property` | ei | `update_time` | `ei`=$tenant_id |
| `tenant_event_status` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |
| `udf_board` | ei | `update_time` | `ei`=$tenant_id |
| `udf_board_config` | ei | `update_time` | `ei`=$tenant_id |
| `udf_board_view` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj_diff` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj_field` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj_field_diff` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj_field_gray` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj_gray` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj_relation` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj_relation_diff` | ei | `update_time` | `ei`=$tenant_id |
| `udf_obj_relation_gray` | ei | `update_time` | `ei`=$tenant_id |
| `udf_rpt_filter` | ei | `update_time` | `ei`=$tenant_id |
| `udf_rpt_template_field` | ei | `update_time` | `ei`=$tenant_id |
| `udf_rpt_template_field_gray` | ei | `update_time` | `ei`=$tenant_id |
| `udf_rpt_template_filter` | ei | `update_time` | `ei`=$tenant_id |
| `udf_rpt_template_filter_gray` | ei | `update_time` | `ei`=$tenant_id |
| `udf_rpt_view_field` | ei | `update_time` | `ei`=$tenant_id |
| `udf_template_obj_relation` | ei | `update_time` | `ei`=$tenant_id |
| `udf_template_obj_relation_gray` | ei | `update_time` | `ei`=$tenant_id |
| `udf_view_obj_relation` | ei | `update_time` | `ei`=$tenant_id |
| `view_backstage_query_info` | ei | `update_time` | `ei`=$tenant_id |
