# paas-workflow

**方言**: `mongodb` 
**说明**: PaaS层工作流引擎，管理工作流定义、实例、定时任务、自动任务及执行错误记录 
**租户 ID**: 必填 `--tenant-id <EI>` 

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns paas-workflow <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query paas-workflow`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables paas-workflow --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> show columns paas-workflow <table> --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query paas-workflow --tenant-id <EI> --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **18**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **18**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `ApprovalConfig` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `NoticeMessage` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `QixinScheduleMessage` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `apply_job_records` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `auto_tasks` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `backup` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `batch_operation_record` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `block_tasks` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `delay_task_queue` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `execution_error_record` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `subProcessTasks` | tenantId | `-` | `{"tenantId":"$tenant_id"}` |
| `tasks` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `todo_tasks` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `workflowInstances` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `workflow_quartz` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `workflow_rules` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `workflow_tasks` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
| `workflows` | tenantId | `modifyTime` | `{"tenantId":"$tenant_id"}` |
