# cross-notice

**方言**: `mysql`
**说明**: 互联通知公告（库 `open_material`），管理公告素材、访问权限与发送记录
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

> 正确 biz 名是 **`cross-notice`**。不要当成 Mongo **`open-material`**（开放素材）；二者库用途不同，只是 MySQL 物理库名同为 `open_material`。
> 查询走 `fx-ops idp query`（IDP 只读/从库路由），禁止直连主库或手写连接串。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns cross-notice <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query cross-notice`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables cross-notice --dialect mysql -j
fx-ops idp --profile <profile> show columns cross-notice <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query cross-notice --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **5**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **5**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。租户列名按表不同（`ea` / `fs_ea`）。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `material` | ea | `modified_time` | `ea`=$tenant_account |
| `message_record` | ea | `modified_time` | `ea`=$tenant_account |
| `article_category_switch` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
| `material_access_permission` | fs_ea | `modified_time` | `fs_ea`=$tenant_account |
| `service_comment_switch` | fs_ea | `gmt_modified` | `fs_ea`=$tenant_account |
