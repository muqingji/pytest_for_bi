# oa-todo

**方言**: `mongodb` 
**说明**: OA待办事项管理，管理待办定义、待办事项、待办处理记录及业务统计 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns oa-todo <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query oa-todo`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables oa-todo --dialect mongodb -j
fx-ops idp --profile <profile> show columns oa-todo <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query oa-todo --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **9**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **8**
- 使用 `$tenant_account` / EA: **1**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `CustomTodoBizItemEntity` | EI | `-` | `{"EI":"$tenant_id"}` |
| `Todo` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `TodoBizLayoutEntity` | EI | `-` | `{"EI":"$tenant_id"}` |
| `TodoBizStatV*` | EI | `-` | `{"EI":"$tenant_id"}` |
| `TodoDeal` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `TotoBizStat` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `TotoBizStatV*` | EI | `-` | `{"EI":"$tenant_id"}` |
| `UserTodo` | EI | `CT` | `{"EI":"$tenant_id"}` |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `CTODODefinition` | EA | `UT` | `{"EA":"$tenant_account"}` |

## 正则/通配表名

下列规则按 **正则或通配** 匹配表名；先用 `table list` 确认实际表名。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `TodoBizStatV*` | EI | `-` | `{"EI":"$tenant_id"}` |
| `TotoBizStatV*` | EI | `-` | `{"EI":"$tenant_id"}` |
