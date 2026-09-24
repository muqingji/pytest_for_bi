# org-data

**方言**: `mongodb` 
**说明**: 组织架构数据管理，涵盖部门信息、员工信息、密码管理、企业配置及IP管控等 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns org-data <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query org-data`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables org-data --dialect mongodb -j
fx-ops idp --profile <profile> show columns org-data <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query org-data --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **20**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **17**
- 使用 `$tenant_account` / EA: **3**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `DepartmentPo` | EI | `UT` | `{"EI":"$tenant_id"}` |
| `DomainInfo` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `EmpProperty_email` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `EmpProperty_phone` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `EmpProperty_relation_email` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `EmpProperty_relation_mobile` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `EmpProperty_user_name` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `EmployeeConfigEntity` | ENT_EI | `-` | `{"ENT_EI":"$tenant_id"}` |
| `EmployeePasswordExpirePo` | EI | `-` | `{"EI":"$tenant_id"}` |
| `EmployeePasswordPo` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `EmployeePo` | EI | `UT` | `{"EI":"$tenant_id"}` |
| `EnterpriseConfigEntity` | ENT_EI | `-` | `{"ENT_EI":"$tenant_id"}` |
| `EnterpriseIncrease` | EI | `UT` | `{"EI":"$tenant_id"}` |
| `EnterpriseInfoPo` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `IpCtrlPo` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `OrganizationUpdate` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `transfer_tenant_support` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `DataTransfer` | EA | `-` | `{"EA":"$tenant_account"}` |
| `EnterpriseMetaData` | _id | `CT` | `{"_id":"$tenant_account"}` |
| `OrganizationTree` | _id | `-` | `{"_id":"$tenant_account"}` |
