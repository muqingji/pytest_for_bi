# enterprise-relation

**方言**: `postgresql`  
**说明**: 企业关系管理，覆盖关联应用、微信代理、微信联盟、微信通知与企业名片等全局关系数据  
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

**双方言**: 同名还存在其它 dialect。**必须** `--dialect postgresql` 或使用别名 `enterprise-relation-postgresql`。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns enterprise-relation <name> --dialect postgresql -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query enterprise-relation --dialect postgresql`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables enterprise-relation --dialect postgresql -j
fx-ops idp --profile <profile> show columns enterprise-relation <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 模板含 $tenant_account 时取 EA
fx-ops idp --profile <profile> query enterprise-relation --dialect postgresql --sql "<SQL>" -j
```

## 说明

- 2026-08-07 起：同库合并原 `open-link-app`、`wechat-proxy`、`wechat-union`(pg)、`wechat-notice`、`link-enterprise-relation`
- **禁止**再使用上述旧 biz 名；mongodb 同名 biz 仍存在，查 PG 必须带 dialect
- 物理库：`enterprise_relation`。`link-enterprise-relation-biz`（库 `enterprise_relation_biz`）**未**合并，仍独立
- 表族：`er_*` 关联应用、`wx_*` 微信、`employee_card`/`enterprise_card`/global_* 名片关系

## 统计

- 表级筛选条目: **39**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **5**
- 使用 `$tenant_account` / EA: **27**
- 无默认租户模板: **7**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；拼 WHERE 时用 EI。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `employee_card` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `enterprise_card` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `global_enterprise_relation` | upstream_tenant_id | `update_time` | `upstream_tenant_id`=$tenant_id |
| `global_public_employee` | upstream_tenant_id | `update_time` | `upstream_tenant_id`=$tenant_id |
| `upstream_public_employee` | upstream_tenant_id | `update_time` | `upstream_tenant_id`=$tenant_id |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account`；先 `tenant get` 取 EA。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `er_upstream_enterprise_link_app_relation` | upstream_ea | `update_time` | `upstream_ea`=$tenant_account |
| `wx_account_book_config` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `wx_account_book_user` | fs_ea | `-` | `fs_ea`=$tenant_account |
| `wx_custom_menu_bind` | ea | `create_time` | `ea`=$tenant_account |
| `wx_ea_bind_info` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `wx_material` | ea | `update_time` | `ea`=$tenant_account |
| `wx_miniprogram_bind` | ea | `update_time` | `ea`=$tenant_account |
| `wx_qr_code` | ea | `update_time` | `ea`=$tenant_account |
| `wx_shared_file` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `wx_platform_config` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `wx_user_bind_info` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `wx_user_qr_scene` | enterprise_account | `update_time` | `enterprise_account`=$tenant_account |
| `wx_customer_crm_info` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `wx_fan_base_info` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `wx_fan_extra` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `wx_fan_tag` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `wx_fan_tag_detail` | fs_ea | `-` | `fs_ea`=$tenant_account |
| `wx_open_customer` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `wx_open_customer_expert` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `wx_open_customer_group` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `wx_outer_service_crm_role` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `wx_outer_service_wechat` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `wx_miniprogram_subscribe_message_info` | ea | `update_time` | `ea`=$tenant_account |
| `wx_miniprogram_subscribe_message_mapping` | ea | `update_time` | `ea`=$tenant_account |
| `wx_notice_send_record` | ea | `update_time` | `ea`=$tenant_account |
| `wx_notice_timed_task` | ea | `update_time` | `ea`=$tenant_account |
| `wx_template_message_config` | ea | `update_time` | `ea`=$tenant_account |

## 无默认租户模板表

平台未给单列租户 filter；查询须自带可收敛条件 + LIMIT，禁止无过滤全表扫。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `er_fs_link_app` | - | `update_time` | - |
| `er_link_app` | - | `update_time` | - |
| `er_link_app_enterprise_type_association` | - | `update_time` | - |
| `er_link_app_object_association` | - | `update_time` | - |
| `er_link_app_outer_role_association` | - | `update_time` | - |
| `er_link_app_range_association` | - | `update_time` | - |
| `er_wechat_link_app` | - | `update_time` | - |

## 相关文档

- [业务线总览](../index.md)
- [方言索引](./index.md)
- [filterHint 拼 SQL](../../../idp-query-filter-hint.md)
