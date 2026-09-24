# mail

**方言**: `mysql` 
**说明**: 邮件服务，管理企业邮件收发、邮件规则、邮件通知及CRM邮件沉淀 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns mail <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query mail`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables mail --dialect mysql -j
fx-ops idp --profile <profile> show columns mail <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query mail --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **25**
- 复杂筛选（无租户列和/或子查询）: **16**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **9**

## 复杂筛选表（优先阅读）

下列表的 **queryTemplate** 为 **子查询/关联** 或未使用单列租户列，
不要写成 `WHERE tenant_id = <EI>`；需用 `tenant get` 得到 **tenantAccount（EA）** 并按模板拼 WHERE。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `crm_email_bind(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `crm_msg_read_record` | - | `create_time` | `msg_id` IN (SELECT DISTINCT `id` FROM `crm_message` WHERE `ea`=$tenant_account) |
| `crm_msg_sediment_content` | - | `update_time` | `email_id` IN (SELECT DISTINCT `email_id` FROM `crm_msg_sediment` WHERE `fs_corp_id`=$tenant_account) |
| `email_activity` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `email_config` | - | `update_time` | `id` IN (SELECT DISTINCT `email_config_id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) AND `type`='4' |
| `email_contracts(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `email_rule_action` | - | `update_time` | `rule_id` IN (SELECT DISTINCT `id` FROM `email_rule` WHERE `fs_ea`=$tenant_account) |
| `email_rule_condition` | - | `update_time` | `rule_id` IN (SELECT DISTINCT `id` FROM `email_rule` WHERE `fs_ea`=$tenant_account) |
| `email_setting` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `folder` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `message(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `message_content(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `message_read_record(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `operation` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `share_message` | source_corp_id | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `share_message_content` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `crm_email_relation(?:[\d_-]*)$` | ea | `create_time` | `ea`=$tenant_account |
| `crm_msg_sediment` | fs_corp_id | `update_time` | `fs_corp_id`=$tenant_account |
| `email` | fs_corp_id | `update_time` | `fs_corp_id`=$tenant_account |
| `email_notice_task` | fs_corp_id | `update_time` | `fs_corp_id`=$tenant_account |
| `email_notice_user` | fs_corp_id | `update_time` | `fs_corp_id`=$tenant_account |
| `email_notice_user_history` | fs_corp_id | `update_time` | `fs_corp_id`=$tenant_account |
| `email_rule` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `enterprise_email_config` | ea | `update_time` | `ea`=$tenant_account |
| `sync_all_message_schedule` | fs_ea | `update_time` | `fs_ea`=$tenant_account |

## 正则/通配表名

下列规则按 **正则或通配** 匹配表名；先用 `table list` 确认实际表名。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `crm_email_bind(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `crm_email_relation(?:[\d_-]*)$` | ea | `create_time` | `ea`=$tenant_account |
| `email_contracts(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `message(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `message_content(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
| `message_read_record(?:[\d_-]*)$` | - | `update_time` | `email_id` IN (SELECT DISTINCT `id` FROM `email` WHERE `fs_corp_id`=$tenant_account AND `status` IN (1,5)) |
