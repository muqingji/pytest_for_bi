# oncall

**方言**: `postgresql` 
**说明**: 运维告警与值班平台，管理告警事件、通知渠道、静默策略及值班排班 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`）


下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns oncall <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query oncall`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables oncall --dialect postgresql -j
fx-ops idp --profile <profile> show columns oncall <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query oncall --sql "<SQL>" -j
```

## 告警主表特殊路由

- 下面的 `<profile>` 用法适用于大多数 oncall 表的通用探查。
- **但 `alert` 主表及所有通过 `alert` 关联的告警查询是特例**：统一使用 `fx-ops idp --profile foneshare query oncall --sql "<SQL>" -j`。
- 目标业务环境不要直接写成 CLI profile，而应通过 SQL 的 `alert_env` 条件表达：
  - 普通环境 → `alert_env IN ('<env>-k8s1')`
  - `foneshare` → `alert_env IN ('k8s1', 'k8s0', 'tke70-k8s1')`
- 这类告警查询优先使用 `alert.create_time`，并把用户输入的北京时间窗口等价换算成 UTC 边界；用户已明确给出窗口时，禁止擅自扩窗。
- `notify_channel_history` 等非 `alert` 主表查询仍按自身场景选择路由，不要把这条规则误套到所有 oncall 表。

## 统计

- 表级筛选条目: **17**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **0**

## 其他表

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `ai_analysis` | - | `update_time` | - |
| `alert` | - | `update_time` | - |
| `alert_process` | - | `update_time` | - |
| `alert_request` | - | `update_time` | - |
| `alert_rule` | - | `update_time` | - |
| `alert_upgrade` | - | `update_time` | - |
| `duty_setting` | - | `update_time` | - |
| `duty_user` | - | `update_time` | - |
| `notify_channel` | - | `update_time` | - |
| `notify_channel_history` | - | `update_time` | - |
| `route_link` | - | `update_time` | - |
| `route_policy` | - | `update_time` | - |
| `route_policy_condition` | - | `update_time` | - |
| `self_healing` | - | `update_time` | - |
| `silent_policy` | - | `update_time` | - |
| `silent_policy_condition` | - | `update_time` | - |
| `subscribe_policy` | - | `update_time` | - |
