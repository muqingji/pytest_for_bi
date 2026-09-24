# link-eip-data-sync

**方言**: `mongodb`
**说明**: EIP 企业信息平台数据同步的 Mongo 分片缓冲（库 `fs-sync-data-all`）
**路由**: `fixed`（`show/query` 免传 `--tenant-id`）

> 本 biz **双方言**：未指定 dialect 会 `dialect_required`。策略 / 映射 / 快照在 [postgresql/link-eip-data-sync.md](../postgresql/link-eip-data-sync.md)。
> 禁止 `eip-data-sync` / `eip_data_sync` / `syncdata`。独立 PG 库是 `link-eip-data-sync-1` / `link-eip-data-sync-747125`，不是本集合。
> 查询走 `fx-ops idp query`（IDP 只读/从库路由），禁止直连主库或手写连接串。

下列为 **表级租户筛选** 参考；拼 filter 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show tables/columns link-eip-data-sync --dialect mongodb` 核对集合名。列元数据与 filterHint 当前为空。

**查询入口**: `fx-ops idp query link-eip-data-sync --dialect mongodb`（方言规则见 ../../../idp-query-mongodb.md，总览见 [../link-eip-data-sync.md](../link-eip-data-sync.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables link-eip-data-sync --dialect mongodb -j
fx-ops idp --profile <profile> show columns link-eip-data-sync <collection> --dialect mongodb -j
fx-ops idp --profile <profile> query link-eip-data-sync --dialect mongodb --collection <collection> --filter '<JSON>' --limit 20 -j
```

## 说明

- 集合几乎全是 `buf_*` 分片缓冲（foneshare 实测约 505 个）。**禁止**把全量集合名抄进文档或一次扫全库。
- 无 filterHint / 无列字典：必须自带可收敛条件 + `--limit`。
- 不要和 `link-erp-data-sync`（ERP 同步）混淆。

## 统计

- 表级筛选条目: **0**（catalog 未给单列租户模板）
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **0**
- 无默认租户模板: 全部 `buf_*`

## 无默认租户模板表

平台未给单列租户 filter；查询须自带可收敛条件 + LIMIT，禁止无过滤全表扫。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `buf_*` | - | - | - |
