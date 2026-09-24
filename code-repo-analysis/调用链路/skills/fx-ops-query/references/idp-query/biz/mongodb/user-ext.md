# user-ext

**方言**: `mongodb` 
**说明**: 用户扩展配置，管理员工配置、首页布局模板、菜单模板及对象关联 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns user-ext <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query user-ext`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables user-ext --dialect mongodb -j
fx-ops idp --profile <profile> show columns user-ext <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query user-ext --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **3**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **3**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `MenuTemplatePO` | EI | `-` | `{"EI":"$tenant_id"}` |
| `PageTemplateV*` | EI | `-` | `{"EI":"$tenant_id"}` |
| `PageTemplateV2` | EI | `-` | `{"EI":"$tenant_id"}` |

## 正则/通配表名

下列规则按 **正则或通配** 匹配表名；先用 `table list` 确认实际表名。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `PageTemplateV*` | EI | `-` | `{"EI":"$tenant_id"}` |
