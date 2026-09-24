# open-app-pay

**方言**: `mysql` 
**说明**: 开放应用付费，管理应用开关、企业付费、额度记录及试用到期 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns open-app-pay <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query open-app-pay`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables open-app-pay --dialect mysql -j
fx-ops idp --profile <profile> show columns open-app-pay <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query open-app-pay --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **7**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **7**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `app_on_off` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `employee_trial` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `enterprise_auth` | ea | `-` | `ea`=$tenant_account |
| `enterprise_pay` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `quota_record` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `trial_termination_task` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `upgrade_view` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
