# appserver-fmcg

**方言**: `mongodb` 
**说明**: 快消品业务核心模块，涵盖AI识别、销售订单、门店审计、TPM促销及费用支付等 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns appserver-fmcg <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query appserver-fmcg`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables appserver-fmcg --dialect mongodb -j
fx-ops idp --profile <profile> show columns appserver-fmcg <table> --dialect mongodb -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query appserver-fmcg --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **49**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **47**
- 使用 `$tenant_account` / EA: **2**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `ai_account` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_account_detail` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `ai_charge_detail` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `ai_classify_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_detect_count` | TI | `-` | `{"TI":"$tenant_id"}` |
| `ai_detect_record` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `ai_model` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `ai_object_map` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `ai_price` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_ai_switch` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_biz_call_number` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_car_sales_member` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_device_photo_detail` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_audit_data` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_item` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_item_group` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_item_sort` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_efficiency_manager` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_license` | TID | `CT` | `{"TID":"$tenant_id"}` |
| `fmcg_mn_retry_task` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_payment_record` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_route_record` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_global_setting` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_order` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_statements_detail` | EI | `CT` | `{"EI":"$tenant_id"}` |
| `fmcg_sales_ticket` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_ticket_header` | TI | `-` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_transaction_record` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_sales_transaction_record_detail` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_store_audit_task` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_storeaudit_workflow` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_tenant_config` | TID | `CT` | `{"TID":"$tenant_id"}` |
| `fmcg_tenant_config_record` | TID | `CT` | `{"TID":"$tenant_id"}` |
| `fmcg_timeline_audit_item` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_timeline_item` | TI | `CT` | `{"TI":"$tenant_id"}` |
| `fmcg_tpm_activity_node_template` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_activity_type` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_activity_type_draft_box` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_budget_accrual_rule` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_budget_consume_rule` | tenant_id | `-` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_budget_template` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_budget_type` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_config` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_new_budget_consume_rule` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_poc_record` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_tpm_promotion_policy_rule` | tenant_id | `last_update_time` | `{"tenant_id":"$tenant_id"}` |
| `fmcg_warehouse_record` | EI | `CT` | `{"EI":"$tenant_id"}` |

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `ai_face_info` | GI | `-` | `{"GI":"$tenant_account"}` |
| `fmcg_pay_ccb` | EA | `CT` | `{"EA":"$tenant_account"}` |
