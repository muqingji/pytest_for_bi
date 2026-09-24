# call-center

**方言**: `mysql` 
**说明**: 呼叫中心，管理外呼记录、ASR语音识别、电话营销及配额统计 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns call-center <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query call-center`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables call-center --dialect mysql -j
fx-ops idp --profile <profile> show columns call-center <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query call-center --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **14**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **9**
- 使用 `$tenant_account` / EA: **5**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `advanced_setting` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `call_function_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `call_mapping` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `call_mapping_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `callout_obj` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `telemarket_setting` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `temporary_rights` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `tenant_bind` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `user_bind` | tenant_id | `update_time` | `tenant_id`=$tenant_id |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `call_asr_task` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `call_record` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `quota_statistics` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `quota_statistics_detail` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
| `tenant_advanced_setting` | fs_ea | `update_time` | `fs_ea`=$tenant_account |
