# fmcg-integral

**方言**: `mongodb` 
**说明**: 快消品积分体系，管理积分规则、兑换记录、部门积分设置及统计 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns fmcg-integral <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query fmcg-integral`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables fmcg-integral --dialect mongodb -j
fx-ops idp --profile <profile> show columns fmcg-integral <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query fmcg-integral --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **75**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **72**
- 使用 `$tenant_account` / EA: **3**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `EcpFileMeta` | ei | `-` | `{"ei":"$tenant_id"}` |
| `action` | EI | `-` | `{"EI":"$tenant_id"}` |
| `ai_account` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_account_detail` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_billing_account` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_billing_detail` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_charge_detail` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_classify_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_compensation_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_detect_count` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_detect_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_model` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_object_map` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_price` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_service_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `deptRankSetting` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `detail` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `detailExchangeRecord` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `detail_temp` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `enterpriseFlag` | EI | `-` | `{"EI":"$tenant_id"}` |
| `fmcg_ai_switch` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_biz_call_number` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_car_sales_member` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_coin_conversion_flow` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `fmcg_coin_conversion_rule` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `fmcg_coin_conversion_rule_bak` | EI | `-` | `{"EI":"$tenant_id"}` |
| `fmcg_device_photo_detail` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_audit_data` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_item` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_item_group` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_item_sort` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_manager` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_group_pile` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_group_pile_serial_number` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_import_record` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_integral_delay_calculate_task` | EI | `-` | `{"EI":"$tenant_id"}` |
| `fmcg_integral_setting` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `fmcg_mn_retry_task` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_payment_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_query_record` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_route_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_global_setting` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_order` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_statements_detail` | EI | `-` | `{"EI":"$tenant_id"}` |
| `fmcg_sales_ticket` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_ticket_header` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_transaction_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_transaction_record_detail` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_store_audit_task` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_storeaudit_workflow` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_timeline_audit_item` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_timeline_item` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_tpm_activity_node_template` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_activity_type` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_activity_type_draft_box` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_budget_accrual_rule` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_budget_template` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_budget_type` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_config` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_new_budget_consume_rule` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_poc_record` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_promotion_policy_rule` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_warehouse_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `functionalRule` | EI | `-` | `{"EI":"$tenant_id"}` |
| `icbc_bill` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `integral` | I | `-` | `{"I":"$tenant_id"}` |
| `pushMessageTask` | EI | `-` | `{"EI":"$tenant_id"}` |
| `rule` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `ruleGroup` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `tag` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `task` | EI | `-` | `{"EI":"$tenant_id"}` |
| `trigger` | EI | `CT` | `{"EI":"$tenant_id"}` |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `fmcg_exchange_setting` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `import_task` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `statisticsAdmin` | EA | `CT` | `{"EA":"$tenant_account"}` |
