# open-sail

**方言**: `mysql` 
**说明**: 售后服务管理，管理工单流转、服务派工、SLA规则及知识库 
**路由**: `fixed`（`show/query` 免传 `--tenant-id`；表级 WHERE 仍按 filterHint 拼）

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns open-sail <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query open-sail`（方言规则见 ../../../idp-query-sql.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables open-sail --dialect mysql -j
fx-ops idp --profile <profile> show columns open-sail <table> --dialect mysql -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query open-sail --sql "<SQL>" -j
```

## 统计

- 表级筛选条目: **24**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **24**
- 使用 `$tenant_account` / EA: **0**

## 租户 ID（EI）筛选表

模板占位符含 `$tenant_id` / `$ei`；`--tenant-id` 传 EI 即可。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `biz_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `bom_cart_record` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `cart` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `collect` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `customer_account_bill` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `customer_account_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `customer_account_consume_fail_mq_msg` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `daily_abnormal_customer_account` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `daily_bill` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `employee_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `home_layout` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `online_contact` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `online_customer` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `online_pay_record` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `open_app_link` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `order_agreement_view_record` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `order_wcontact_record` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `payment_account` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `payment_fail_msg` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `price_book` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `print_code_record` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `record_layout_config` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `sub_product_cart_record` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
| `tied_product` | tenant_id | `update_time` | `tenant_id`=$tenant_id |
