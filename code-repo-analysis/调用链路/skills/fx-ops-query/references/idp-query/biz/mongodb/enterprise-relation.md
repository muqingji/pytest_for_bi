# enterprise-relation

**方言**: `mongodb` 
**说明**: 企业关系管理，涵盖审批流程、企业元数据、上下游企业关系及CRM续费订单等 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

**双方言**: 同名还有 `postgresql`（企业关系/微信/名片主库）。查 Mongo **必须** `--dialect mongodb` 或 `enterprise-relation-mongodb`。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns enterprise-relation <name> --dialect mongodb -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query enterprise-relation --dialect mongodb`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables enterprise-relation --dialect mongodb -j
fx-ops idp --profile <profile> show columns enterprise-relation <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query enterprise-relation --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **22**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **10**
- 使用 `$tenant_account` / EA: **12**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `Approval` | EI | `updateTime` | `{"EI":"$tenant_id"}` |
| `CreateFsAccountForNoTenantTask` | tenantId | `CT` | `{"tenantId":"$tenant_id"}` |
| `DownstreamMonthUseStatistics` | tenantId | `CT` | `{"tenantId":"$tenant_id"}` |
| `DownstreamWeekUseStatistics` | tenantId | `CT` | `{"tenantId":"$tenant_id"}` |
| `ERAccountActiveConfig` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `EnterpriseLinkWxServiceMetaData` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `EnterpriseLinkWxServiceSmsGuideRecord` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `RelationLog` | tenantId | `updateTime` | `{"tenantId":"$tenant_id"}` |
| `ThirdSysRegisterInfo` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `UpstreamOpenedEnterpriseRecord` | tenantId | `CT` | `{"tenantId":"$tenant_id"}` |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `CustomerLinkAccount` | ea | `-` | `{"ea":"$tenant_account"}` |
| `CustomerLinkWxAppletsAccountAssociation` | EA | `-` | `{"EA":"$tenant_account"}` |
| `EmployeeCard` | EA | `-` | `{"EA":"$tenant_account"}` |
| `EmployeeInfo` | EA | `-` | `{"EA":"$tenant_account"}` |
| `EnterpriseAdmin` | EA | `-` | `{"EA":"$tenant_account"}` |
| `EnterpriseLinkWxServiceAccountAssociation` | EA | `-` | `{"EA":"$tenant_account"}` |
| `EnterpriseMetaData` | _id | `CT` | `{"_id":"$tenant_account"}` |
| `EnterpriseRelationUpdateLogEntity` | EA | `-` | `{"EA":"$tenant_account"}` |
| `FxiaokeEmployeeAssociation` | ea | `-` | `{"ea":"$tenant_account"}` |
| `FxiaokeEnterpriseAssociation` | ea | `-` | `{"ea":"$tenant_account"}` |
| `OuterEiCustomerIdMapper` | ea | `-` | `{"ea":"$tenant_account"}` |
| `RelationPatternConfig` | EA | `-` | `{"EA":"$tenant_account"}` |
