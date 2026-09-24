# tenant-router

**方言**: `postgresql`
**说明**: 租户路由元数据库，记录租户到物理库/实例的路由映射（`pod_metadata_resource` / `pod_metadata_router` 等）
**路由**: `fixed`（`show/query` 免传 `--tenant-id`）

平台未提供完整表级 `query.csv` 筛选文档。执行前**必须** `show tables` / `show columns` 实测。

**查询入口**: `fx-ops idp query tenant-router`

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables tenant-router -j
fx-ops idp --profile <profile> show columns tenant-router <table> -j
fx-ops idp --profile <profile> query tenant-router --sql "SELECT ... LIMIT 20" -j
```

## dbName → 实例 IP（物理节点定位）

> 适用：在 `slow_log_dist` / `biz_sql_stat_dist` 等日志里看到 `dbName`（如 `fsdb017053066001` / `fsdb052040001`）后，想知道该库落在哪个物理实例 / 节点 IP 时。

### 核心命令

`pod_metadata_resource` 表以 `db_name` 记录物理库名，`master` / `slave` 为节点地址（`host:port`）。**定位当前生效实例必须带 `AND status = 0`**——同一 `db_name` 会同时保留历史/迁移记录（`status=1`），不带过滤会把旧 IP 一起带出来：

```bash
fx-ops idp --profile foneshare query tenant-router --sql \
  "SELECT db_name, master, slave, master_proxy_url, dialect, biz, status \
   FROM pod_metadata_resource \
   WHERE db_name IN ('fsdb017053066001','fsdb052040001') AND status = 0" -j
```

示例结果：

| db_name | master (host:port) | slave | master_proxy_url | status |
| --- | --- | --- | --- | --- |
| `fsdb017053066001` | `10.17.53.66:5432` | `10.17.53.66:5432` | `10.17.50.206:5432` | 0 |
| `fsdb052040001` | `10.17.52.40:5432` | `10.17.52.40:5432` | `10.17.50.204:5432` | 0 |

> 如需查看某库的迁移/历史记录（如旧地址 `172.17.56.40:5432`），去掉 `AND status = 0` 过滤，并以 `status=1` 行对照 `route_transfer_history` 确认迁移时间线。

关键字段：

| 字段 | 含义 |
| --- | --- |
| `db_name` | 物理库名，与日志中的 `dbName` 对应 |
| `master` / `slave` | 主 / 从实例地址（`host:port`），`slave` 为 ARRAY |
| `master_proxy_url` / `slave_proxy_url` | 主 / 从代理地址（应用实际连接入口） |
| `status` | `0` = 当前生效；`1` = 迁移/历史记录（`route_transfer_history` 有迁移明细） |
| `biz` / `dialect` | 归属业务线 / 方言 |

### dbName 命名规律（辅助判断）

`fsdb` 后的数字段基本编码了 IP 后两段 + 实例号，可快速目测但**以 `master` 字段为准**：

- `fsdb052040001` → `10.17.**52.40**:5432`
- `fsdb017053066001` → `10.17.**53.66**:5432`

### 注意事项

- `pod_metadata_resource` 为**高敏感**物理资源表，直接暴露内网数据库地址与主从拓扑，仅限定位用途，不得外发。
- 同一 `db_name` 可能返回多条：以 `status=0` 为当前生效，`status=1` 多为历史 / 迁移遗留。
- 若已知的是**租户 ID** 而非 dbName，用 `pod_metadata_router`（`tenant_id` → `resource_id`）关联 `pod_metadata_resource.resource_id` 定位。

## 相关文档

- [业务线总览](../index.md)
- [方言索引](./index.md)
- [filterHint 拼 SQL](../../../idp-query-filter-hint.md)
