# paas-license

**方言**: `postgresql` 
**说明**: PaaS许可证管理，管理产品许可、模块配置、租户授权、灰度发布及用量概览 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns paas-license <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query paas-license`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables paas-license --dialect postgresql -j
fx-ops idp --profile <profile> show columns paas-license <table> --dialect postgresql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query paas-license --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **14**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **14**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `gray_new_module` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `gray_new_opportunity` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `license_log` | tenant_id | `last_modify_time` | `tenant_id`=$tenant_id |
| `license_relation` | tenant_id | `-` | `tenant_id`=$tenant_id |
| `module_info` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `module_para` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `opportunity_tenants` | tenant_id | `-` | `tenant_id`=$tenant_id |
| `overview_info` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `overview_info_detail` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `product_config` | tenant_id | `-` | `tenant_id`=$tenant_id |
| `product_gray` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `product_info` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `product_license` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |
| `tenant_license` | tenant_id | `modify_time` | `tenant_id`=$tenant_id |

## 常见场景：客户互动语料存储配额 / 剩余

客户会议 / 客户互动录音的专属存储参数：

- `para_key`：`ai_interactive_assistant_big_files_storage_limit`（单位 MiB，多条有效行累加）
- 配额表：`module_para`（可靠，用于总包大小）
- `overview_info.used_value`：**不可**当作累计已用。实测 BFM 回写 `OverviewChangeMessage.usedValue` 常约等于**本次文件 MiB**，会覆盖成「单文件大小」，与 BFM 累计 `usedSpace` 严重分叉
- 已用/剩余权威：BFM 运行时日志 `updateUsedSpace.usedSpace` 与 `业务配置.quotaSpace`（见 SFA playbook `customer-interaction-storage-quota.md`）

注意：连接库 `fs_paas_license` 后表名写 `public.module_para`，**不要**写 `FROM fs_paas_license.module_para`。

```sql
-- 配额汇总（MiB）——可单独交付
SELECT COALESCE(SUM(para_value::numeric), 0) AS quota_mib_sum
FROM public.module_para
WHERE tenant_id = '<EI>'
  AND para_key = 'ai_interactive_assistant_big_files_storage_limit'
  AND COALESCE(del_flag, false) = false;

-- overview 仅对照，禁止用 quota - used_value 报剩余
SELECT used_value, modify_time
FROM public.overview_info
WHERE tenant_id = '<EI>'
  AND para_key = 'ai_interactive_assistant_big_files_storage_limit'
  AND COALESCE(del_flag, false) = false
ORDER BY modify_time DESC
LIMIT 5;
```

fx-ops 查询账号通常只读；测试造数需 DBA 写 `module_para.para_value`，且压配额前先用 BFM `usedSpace` 作基线。不要只改 `overview_info`。
