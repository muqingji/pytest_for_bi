# metadata-option

> **非默认路径**。对象字段与选项优先 `idp object describe` / `object query`。仅当用户**明确**要求查 `metadata_option` 表、或 describe 选项明显缺失且需核对 `option_json` 时使用。  
> 多数租户可能 `No route found`（含 `tenantId=-100`）。object 链路服务端日志中的 `METADATA-OPTION` 是平台内部加载，**不是**要求 agent 来查本 biz。

**方言**: `postgresql`
**说明**: 元数据选项管理，维护下拉选项及其关联关系的配置数据
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns metadata-option <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query metadata-option`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables metadata-option --dialect postgresql -j
fx-ops idp --profile <profile> show columns metadata-option <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query metadata-option --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **2**
- 复杂筛选（无租户列和/或子查询）: **1**
- 使用 `$tenant_id` / EI: **1**
- 使用 `$tenant_account` / EA: **0**

## 复杂筛选表（优先阅读）

下列表的 **queryTemplate** 为 **子查询/关联** 或未使用单列租户列，
不要写成 `WHERE tenant_id = <EI>`；需用 `tenant get` 得到 **tenantAccount（EA）** 并按模板拼 WHERE。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `metadata_option` | - | `modified_time` | `md5 in (select md5 from metadata_option_relation where tenant_id='$tenant_id')` |

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `metadata_option_relation` | tenant_id | `create_time` | `tenant_id`=$tenant_id |
