# cross-enterprise-sharedisk

**方言**: `mongodb`
**说明**: 互联网盘（sharedisk），管理文件、目录与动态
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

> 正确 biz 名是 **`cross-enterprise-sharedisk`**。不要当成 `oa-netdisk`（OA 网盘，另一套集合）。
> 查询走 `fx-ops idp query`（IDP 只读/从库路由），禁止直连主库或手写连接串。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns cross-enterprise-sharedisk <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query cross-enterprise-sharedisk`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables cross-enterprise-sharedisk --dialect mongodb -j
fx-ops idp --profile <profile> show columns cross-enterprise-sharedisk <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query cross-enterprise-sharedisk --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **7**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **4**
- 无默认租户模板: **3**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。租户列名按集合不同（`CrEA` / `FEA` / `EA`），禁止统一写成 `EA`。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `file` | CrEA | `UpT` | `{"CrEA":"$tenant_account"}` |
| `folder` | CrEA | `UpT` | `{"CrEA":"$tenant_account"}` |
| `dynamic` | FEA | `UpT` | `{"FEA":"$tenant_account"}` |
| `dynamic_viewpoint` | EA | `UpT` | `{"EA":"$tenant_account"}` |

## 无默认租户模板表

平台未给单列租户 filter；查询须自带可收敛条件 + LIMIT，禁止无过滤全表扫。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `read_status` | - | `UpT` | - |
| `migrate_record` | - | `UpT` | - |
| `a_file_from_bc` | - | `UpT` | - |
