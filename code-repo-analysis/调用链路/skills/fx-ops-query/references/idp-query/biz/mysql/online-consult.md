# online-consult

**方言**: `mysql` 
**说明**: 在线咨询/在线客服，管理多渠道客服会话、智能分配、快捷回复及服务助手 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns online-consult <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query online-consult`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables online-consult --dialect mysql -j
fx-ops idp --profile <profile> show columns online-consult <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query online-consult --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **50**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **1**
- 使用 `$tenant_account` / EA: **49**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `corpid_to_ei` | ei | `-` | `ei`=$tenant_id |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `app_channel` | ea | `create_time` | `ea`=$tenant_account |
| `assignment_group_app` | ea | `create_time` | `ea`=$tenant_account |
| `assignment_rule` | ea | `update_time` | `ea`=$tenant_account |
| `assignment_rule_assign_group` | ea | `update_time` | `ea`=$tenant_account |
| `assignment_rule_assign_group_record` | ea | `update_time` | `ea`=$tenant_account |
| `channel_verify_config` | ea | `update_time` | `ea`=$tenant_account |
| `column_customized` | ea | `update_time` | `ea`=$tenant_account |
| `consult_form_config` | ea | `update_time` | `ea`=$tenant_account |
| `consult_form_record` | ea | `update_time` | `ea`=$tenant_account |
| `consultant_expert` | ea | `update_time` | `ea`=$tenant_account |
| `consultant_info` | ea | `update_time` | `ea`=$tenant_account |
| `consultant_workbench_status` | ea | `create_time` | `ea`=$tenant_account |
| `custom_channel` | ea | `update_time` | `ea`=$tenant_account |
| `customer_exclusive_consultant` | ea | `update_time` | `ea`=$tenant_account |
| `customer_session` | ea | `update_time` | `ea`=$tenant_account |
| `customer_transfer_info` | ea | `update_time` | `ea`=$tenant_account |
| `data_statistics` | ea | `update_time` | `ea`=$tenant_account |
| `department_group` | ea | `update_time` | `ea`=$tenant_account |
| `ea_bind_info` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `email_info` | ea | `update_time` | `ea`=$tenant_account |
| `email_info_config` | ea | `update_time` | `ea`=$tenant_account |
| `general_setting` | ea | `update_time` | `ea`=$tenant_account |
| `group_info` | ea | `update_time` | `ea`=$tenant_account |
| `knowledge_generate_ai_assistant_config` | ea | `update_time` | `ea`=$tenant_account |
| `layout_template_config` | ea | `update_time` | `ea`=$tenant_account |
| `marketing_setting` | ea | `update_time` | `ea`=$tenant_account |
| `notice_template` | ea | `update_time` | `ea`=$tenant_account |
| `online_app_order` | ea | `create_time` | `ea`=$tenant_account |
| `open_kf_info` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `quick_button_config` | ea | `update_time` | `ea`=$tenant_account |
| `quick_reply_category` | ea | `update_time` | `ea`=$tenant_account |
| `quick_reply_category_channel` | ea | `create_time` | `ea`=$tenant_account |
| `quick_reply_detail` | ea | `update_time` | `ea`=$tenant_account |
| `quick_reply_user` | ea | `update_time` | `ea`=$tenant_account |
| `quick_transfer_record` | ea | `update_time` | `ea`=$tenant_account |
| `satisfaction_appraise_config` | ea | `update_time` | `ea`=$tenant_account |
| `scene_bind_config` | ea | `update_time` | `ea`=$tenant_account |
| `service_assistant_agent` | ea | `update_time` | `ea`=$tenant_account |
| `service_assistant_auto_reply` | ea | `update_time` | `ea`=$tenant_account |
| `service_assistant_base_config` | ea | `update_time` | `ea`=$tenant_account |
| `service_assistant_config` | ea | `update_time` | `ea`=$tenant_account |
| `service_request_config` | ea | `update_time` | `ea`=$tenant_account |
| `session_group_config` | ea | `update_time` | `ea`=$tenant_account |
| `web_im_info` | ea | `update_time` | `ea`=$tenant_account |
| `wechat_kf_account` | ea | `update_time` | `ea`=$tenant_account |
| `wechat_user_auth` | ea | `update_time` | `ea`=$tenant_account |
| `whats_app_info` | ea | `update_time` | `ea`=$tenant_account |
| `work_flow_config` | ea | `update_time` | `ea`=$tenant_account |
| `workbench_expansion` | ea | `update_time` | `ea`=$tenant_account |
