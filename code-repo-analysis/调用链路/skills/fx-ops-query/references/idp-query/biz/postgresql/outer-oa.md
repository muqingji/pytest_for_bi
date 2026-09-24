# outer-oa

**方言**: `postgresql`  
**说明**: 外部 OA 对接，管理企微/钉钉/飞书等通道的企业与员工绑定、连接配置、应用授权、消息与订购数据  
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns outer-oa <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query outer-oa`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables outer-oa -j
fx-ops idp --profile <profile> show columns outer-oa <table> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 模板含 $tenant_account 时取 EA
fx-ops idp --profile <profile> query outer-oa --sql "<SQL>" -j
```

## 说明

- 外部 OA（企微/钉钉/飞书等）绑定与配置；`routeMode=fixed`

## 统计

- 表级筛选条目: **23**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **22**
- 使用 `$tenant_account` / EA: **0**
- 无默认租户模板: **1**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；拼 WHERE 时用 EI。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `outer_oa_enterprise_bind` | fs_ea | `update_time` | `fs_ea`=$tenant_id |
| `outer_oa_employee_bind` | fs_ea | `update_time` | `fs_ea`=$tenant_id |
| `outer_oa_department_bind` | fs_ea | `update_time` | `fs_ea`=$tenant_id |
| `outer_oa_config_info` | fs_ea | `update_time` | `fs_ea`=$tenant_id |
| `outer_oa_app_info` | out_ea | `update_time` | `out_ea`=$tenant_id |
| `outer_oa_message_bind` | fs_ea | `update_time` | `fs_ea`=$tenant_id |
| `outer_oa_employee_data` | out_ea | `update_time` | `out_ea`=$tenant_id |
| `outer_oa_dept_data` | out_ea | `update_time` | `out_ea`=$tenant_id |
| `outer_oa_message_template` | out_ea | `update_time` | `out_ea`=$tenant_id |
| `outer_oa_schedule_bind` | fs_ea | `update_time` | `fs_ea`=$tenant_id |
| `outer_oa_order_info` | paid_out_ea | `update_time` | `paid_out_ea`=$tenant_id |
| `outer_oa_external_contacts` | out_ea | `update_time` | `out_ea`=$tenant_id |
| `outer_oa_calendar_template` | out_ea | `update_time` | `out_ea`=$tenant_id |
| `qyweixin_business_info_bind` | fs_ea | `update_time` | `fs_ea`=$tenant_id |
| `qyweixin_file` | fs_ea | `update_time` | `fs_ea`=$tenant_id |
| `qyweixin_id_to_openid` | out_ea | `update_time` | `out_ea`=$tenant_id |
| `huawei_instance_id_bind` | out_ea | `update_time` | `out_ea`=$tenant_id |
| `dingtalk_isv_crm_sync_obj_info` | ei | `update_time` | `ei`=$tenant_id |
| `dingtalk_isv_ding_obj_sync` | tenant_id | `-` | `tenant_id`=$tenant_id |
| `dingtalk_isv_ding_refuse_data` | ei | `modify_time` | `ei`=$tenant_id |
| `dingtalk_isv_object_data_cache` | ei | `update_time` | `ei`=$tenant_id |
| `dingtalk_isv_sync_data_mappings` | ei | `update_time` | `ei`=$tenant_id |

## 无默认租户模板表

平台未给单列租户 filter；查询须自带可收敛条件 + LIMIT，禁止无过滤全表扫。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `dingtalk_isv_polling_sync_time` | - | `update_time` | - |

## 相关文档

- [业务线总览](../index.md)
- [方言索引](./index.md)
- [filterHint 拼 SQL](../../../idp-query-filter-hint.md)
