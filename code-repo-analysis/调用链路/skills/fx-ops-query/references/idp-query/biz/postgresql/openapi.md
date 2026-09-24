# openapi

**方言**: `postgresql`  
**说明**: 开放平台 API 与 OAuth 认证授权，管理应用授权、授权码、Token、账号绑定、开放接口及调用统计  
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns openapi <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query openapi`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables openapi -j
fx-ops idp --profile <profile> show columns openapi <table> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 模板含 $tenant_account 时取 EA
fx-ops idp --profile <profile> query openapi --sql "<SQL>" -j
```

## 说明

- 2026-08-07 起：原 MySQL/`open-oauth` 已迁 PG 并**合并**入本 biz（库 `openapi_platform`）
- **禁止**再使用 `open-oauth` 作为 biz 名
- 物理库：`openapi_platform`

## 统计

- 表级筛选条目: **26**
- 复杂筛选（无租户列和/或子查询）: **7**
- 使用 `$tenant_id` / EI: **4**
- 使用 `$tenant_account` / EA: **11**
- 无默认租户模板: **4**

## 复杂筛选表（优先阅读）

下列表的 **queryTemplate** 为 **子查询/关联** 或未使用单列租户列，
不要写成 `WHERE tenant_id = <EI>`；需用 `tenant get` 得到 **tenantAccount（EA）** 并按模板拼 WHERE。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `access_token_meta` | - | `gmt_modified` | `app_id` IN (SELECT DISTINCT `app_id` FROM `app_ea_auth` WHERE `fs_ea`=$tenant_account) |
| `app_level` | - | `time_modified` | `app_id` IN (SELECT DISTINCT `app_id` FROM `app_ea_auth` WHERE `fs_ea`=$tenant_account) |
| `app_service_ref` | - | `gmt_modified` | `app_id` IN (SELECT DISTINCT `app_id` FROM `app_ea_auth` WHERE `fs_ea`=$tenant_account) |
| `custom_app_dev_status` | - | `gmt_modified` | `app_id` IN (SELECT DISTINCT `app_id` FROM `app_ea_auth` WHERE `fs_ea`=$tenant_account) |
| `fs_app` | - | `gmt_modified` | `app_id` IN (SELECT DISTINCT `app_id` FROM `app_ea_auth` WHERE `fs_ea`=$tenant_account) |
| `fs_open_user_id` | - | `gmt_modified` | `fs_user_id` LIKE CONCAT('E.',$tenant_account,'.%') |
| `fs_user_unid` | - | `gmt_modified` | `fs_user_id` IN (SELECT DISTINCT `fs_user_id` FROM `fs_open_user_id` WHERE `fs_user_id` LIKE CONCAT('E.',$tenant_account,'.%')) |

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；拼 WHERE 时用 EI。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `fs_authorization_code` | fs_corp_id | `gmt_modified` | `fs_corp_id`=$tenant_id |
| `fs_open_corp_id` | fs_corp_id | `gmt_modified` | `fs_corp_id`=$tenant_id |
| `openapi_callback_event_subscription_config` | enterprise_id | `update_time` | `enterprise_id`=$tenant_id |
| `user_secret` | tenant_id | `last_modified_time` | `tenant_id`=$tenant_id |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account`；先 `tenant get` 取 EA。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `app_auth` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `app_department_auth` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `app_ea_auth` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `bind_account` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `department_auth` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `ea_access_auth` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `ea_auth` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `ea_unid_key` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `fs_auth` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `init_app` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `supporter_call_count_hour` | ea | `create_time` | `ea`=$tenant_account |

## 无默认租户模板表

平台未给单列租户 filter；查询须自带可收敛条件 + LIMIT，禁止无过滤全表扫。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `interface` | - | `last_modify_time` | - |
| `interface_category` | - | `last_modify_time` | - |
| `interface_doc` | - | `last_modify_time` | - |
| `openapi_config` | - | `update_time` | - |

## 相关文档

- [业务线总览](../index.md)
- [方言索引](./index.md)
- [filterHint 拼 SQL](../../../idp-query-filter-hint.md)
