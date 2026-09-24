# hospital-spider

**方言**: `postgresql`
**说明**: 医疗主数据（库 `hospital_spider`），医院 / 科室 / 医生主数据
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

> 正确 biz 名是 **`hospital-spider`**。不要当成 paas/bi 里的 `biz_hospital` 对象表。
> `hospital` / `doctor` 含电话、邮箱、证件号、姓名等 PII，查询只取诊断所需列。
> 查询走 `fx-ops idp query`（IDP 只读/从库路由），禁止直连主库或手写连接串。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns hospital-spider <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query hospital-spider`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables hospital-spider --dialect postgresql -j
fx-ops idp --profile <profile> show columns hospital-spider <table> --dialect postgresql -j
fx-ops idp --profile <profile> query hospital-spider --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **3**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **0**
- 无默认租户模板: **3**

## 无默认租户模板表

平台未给单列租户 filter；查询须自带可收敛条件 + LIMIT，禁止无过滤全表扫。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `hospital` | - | `update_time` | - |
| `doctor` | - | `update_time` | - |
| `department` | - | `update_time` | - |
