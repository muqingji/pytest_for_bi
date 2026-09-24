# qixin-message

**方言**: `mongodb` 
**说明**: 企信消息路由与合并模块，管理消息合并、路由信息及定时数据 
**租户 ID**: 必填 `--tenant-id <EI>` 

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns qixin-message <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query qixin-message`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables qixin-message --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> show columns qixin-message <table> --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query qixin-message --tenant-id <EI> --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **10**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **10**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `C_BizSessionProfile` | EA | `UT` | `{"EA":"$tenant_account"}` |
| `C_CrmDepartmentInfo` | EA | `-` | `{"EA":"$tenant_account"}` |
| `C_MetaData` | EA | `-` | `{"EA":"$tenant_account"}` |
| `C_MetaSession` | EA | `UTS` | `{"EA":"$tenant_account"}` |
| `C_ModifiedMessage` | EA | `MTS` | `{"EA":"$tenant_account"}` |
| `C_SessionMessage` | EA | `MTS` | `{"EA":"$tenant_account"}` |
| `C_UserMessageStatus` | EA | `-` | `{"EA":"$tenant_account"}` |
| `C_UserProfile` | EA | `-` | `{"EA":"$tenant_account"}` |
| `C_UserSession` | EA | `UTS` | `{"EA":"$tenant_account"}` |
| `C_UserSessionStatus` | EA | `UTS` | `{"EA":"$tenant_account"}` |
