# open-yunzhijia

**方言**: `mysql`  
**说明**: 云之家对接，管理云之家组织架构同步、通讯录绑定及外部联系人  
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns open-yunzhijia <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query open-yunzhijia`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables open-yunzhijia -j
fx-ops idp --profile <profile> show columns open-yunzhijia <table> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 模板含 $tenant_account 时取 EA
fx-ops idp --profile <profile> query open-yunzhijia --sql "<SQL>" -j
```

## 说明

- 云之家对接；勿与已废弃文档名 `open-qywx` 混淆——平台 live biz 为 **`open-yunzhijia`**

## 统计

- 表级筛选条目: **8**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **4**
- 无默认租户模板: **4**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account`；先 `tenant get` 取 EA。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `department_account_bind` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `enterprise_account_bind` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `jdy_order_event` | fs_ea | `last_modify_time` | `fs_ea`=$tenant_account |
| `oa_notify_enterprise_list` | ea | `modifiedTime` | `ea`=$tenant_account |

## 无默认租户模板表

平台未给单列租户 filter；查询须自带可收敛条件 + LIMIT，禁止无过滤全表扫。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `employee_account_bind` | - | `gmt_modified` | - |
| `enterprise_new_event` | - | `gmt_modified` | - |
| `kis_cloud_order_event` | - | `last_modify_time` | - |
| `kis_enterprise_token_meta` | - | `gmt_modified` | - |

## 相关文档

- [业务线总览](../index.md)
- [方言索引](./index.md)
- [filterHint 拼 SQL](../../../idp-query-filter-hint.md)
