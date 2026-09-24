# paas-bpm

**方言**: `mongodb` 
**说明**: PaaS层BPM流程引擎，管理审批流程配置、流程草稿、流程触发器及任务委托 
**租户 ID**: 必填 `--tenant-id <EI>` 

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns paas-bpm <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query paas-bpm`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables paas-bpm --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> show columns paas-bpm <table> --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query paas-bpm --tenant-id <EI> --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **13**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **13**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `AfterActionRecord` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `AfterActionRecordOwnerIndex` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `FlowConfig` | tenantId | `lastModifyTime` | `{"tenantId":"$tenant_id"}` |
| `STAGE` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `StageObjectReference` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `TaskDelegateSetting` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `Tenant` | TId | `MT` | `{"TId":"$tenant_id"}` |
| `WorkflowConfig` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `WorkflowDraft` | TId | `-` | `{"TId":"$tenant_id"}` |
| `WorkflowExtension` | TId | `-` | `{"TId":"$tenant_id"}` |
| `WorkflowOutline` | TId | `MT` | `{"TId":"$tenant_id"}` |
| `WorkflowTaskData` | TId | `-` | `{"TId":"$tenant_id"}` |
| `WorkflowTrigger` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
