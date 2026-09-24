# paas-crm-biz

**方言**: `mysql` 
**说明**: PaaS CRM业务，管理CRM企业信息、线索、付费租户及模板功能 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns paas-crm-biz <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query paas-crm-biz`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables paas-crm-biz --dialect mysql -j
fx-ops idp --profile <profile> show columns paas-crm-biz <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query paas-crm-biz --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **12**
- 复杂筛选（无租户列和/或子查询）: **1**
- 使用 `$tenant_id` / EI: **8**
- 使用 `$tenant_account` / EA: **3**

## 复杂筛选表（优先阅读）

下列表的 **queryTemplate** 为 **子查询/关联** 或未使用单列租户列，
不要写成 `WHERE tenant_id = <EI>`；需用 `tenant get` 得到 **tenantAccount（EA）** 并按模板拼 WHERE。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `template_range` | - | `modify_time` | `template_id IN (SELECT template_id FROM template_ext WHERE tenant_id=$tenant_id)` |

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `brush_database_record` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `email_template_ext` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `expired_tenants` | ei | `-` | `ei`=$tenant_id |
| `leads_log` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `payment_plan_update_status` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `sku_migration_brush_record` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
| `template_ext` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `tenant_function` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `crm_enterprise` | ea | `update_time` | `ea`=$tenant_account |
| `crm_enterprise_error` | ea | `create_time` | `ea`=$tenant_account |
| `paid_tenants` | ea | `-` | `ea`=$tenant_account |
