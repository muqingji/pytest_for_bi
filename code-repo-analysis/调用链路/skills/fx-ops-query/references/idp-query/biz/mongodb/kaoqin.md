# kaoqin

**方言**: `mongodb` 
**说明**: 考勤管理模块，管理审批、补卡、考勤规则、月度统计及订阅配置 
**租户 ID**: 必填 `--tenant-id <EI>` 

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns kaoqin <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query kaoqin`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables kaoqin --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> show columns kaoqin <table> --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query kaoqin --tenant-id <EI> --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **20**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **20**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `approval` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `correct_approval` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `data_*` | EA | `-` | `{"EA":"$tenant_account"}` |
| `depart_year_stat` | EA | `-` | `{"EA":"$tenant_account"}` |
| `ea_info` | _id | `CT` | `{"_id":"$tenant_account"}` |
| `extra_data` | EA | `CrtTime` | `{"EA":"$tenant_account"}` |
| `import_log` | EA | `MfyTime` | `{"EA":"$tenant_account"}` |
| `month_stat_set` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `red_packet` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `rule` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `schedule` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `stat_*` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `stat_field_config` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `subscribe_conf` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `subscribe_data` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `subscribe_user` | EA | `-` | `{"EA":"$tenant_account"}` |
| `user_crm_year_stat` | EA | `-` | `{"EA":"$tenant_account"}` |
| `user_rule_index` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `xt-circle-statistics-*` | EA | `-` | `{"EA":"$tenant_account"}` |
| `xt-statistics-*` | EA | `-` | `{"EA":"$tenant_account"}` |

## 正则/通配表名

下列规则按 **正则或通配** 匹配表名；先用 `table list` 确认实际表名。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `data_*` | EA | `-` | `{"EA":"$tenant_account"}` |
| `stat_*` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `xt-circle-statistics-*` | EA | `-` | `{"EA":"$tenant_account"}` |
| `xt-statistics-*` | EA | `-` | `{"EA":"$tenant_account"}` |
