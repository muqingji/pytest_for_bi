# waiqin

**方言**: `mongodb` 
**说明**: 外勤管理模块，管理签到记录、路线规划、拜访计划、客户对象及费用报销 
**租户 ID**: 必填 `--tenant-id <EI>` 

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns waiqin <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query waiqin`（方言规则见 ../../../idp-query-mongodb.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables waiqin --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> show columns waiqin <table> --dialect mongodb --tenant-id <EI> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query waiqin --tenant-id <EI> --collection <collection> --filter '<JSON>' -j
```

## 统计

- 表级筛选条目: **41**
- 复杂筛选（无租户列和/或子查询）: **0**
- 使用 `$tenant_id` / EI: **0**
- 使用 `$tenant_account` / EA: **41**

## 租户账号（EA）筛选表

模板占位符含 `$tenant_account` / `$ea`；需 `tenant get` 解析 **tenantAccount** 再替换。

| 表名 | 租户列 | 时间列 | 筛选模板 |
| --- | --- | --- | --- |
| `CheckinsIndex` | EA | `-` | `{"EA":"$tenant_account"}` |
| `CheckinsLog` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `CheckinsRule` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `UnRecommendDataEntity` | ea | `CT` | `{"ea":"$tenant_account"}` |
| `UserAccount` | EA | `-` | `{"EA":"$tenant_account"}` |
| `account_addr` | EA | `-` | `{"EA":"$tenant_account"}` |
| `account_info_stat` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `action_data` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `app_home` | EA | `-` | `{"EA":"$tenant_account"}` |
| `app_home_page` | EA | `-` | `{"EA":"$tenant_account"}` |
| `check_investigate_type_t` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `check_type` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `check_type_group_t` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `checkin_field` | ea | `ct` | `{"ea":"$tenant_account"}` |
| `checkins_counter` | EA | `-` | `{"EA":"$tenant_account"}` |
| `checkins_location_relation` | EA | `-` | `{"EA":"$tenant_account"}` |
| `custom_object` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `customer_action` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `data_stat` | EA | `-` | `{"EA":"$tenant_account"}` |
| `ea_info` | _id | `CT` | `{"_id":"$tenant_account"}` |
| `ea_initialize` | _id | `-` | `{"_id":"$tenant_account"}` |
| `fees_r` | EA | `-` | `{"EA":"$tenant_account"}` |
| `image_source_slave_data` | EA | `-` | `{"EA":"$tenant_account"}` |
| `interconnect_checkins` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `keyboard_entity` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `object_checkins_stat` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `object_detail` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `outOfTheBox_log` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `outer_rule` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `planRepeater` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `qrcode` | EA | `-` | `{"EA":"$tenant_account"}` |
| `report_info` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `report_stat` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `route` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `route_visit_plan` | EA | `-` | `{"EA":"$tenant_account"}` |
| `stat_field_config` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `sync_obj_fail_dataId` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `test_outer_user_index` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `user_date_stat` | EA | `-` | `{"EA":"$tenant_account"}` |
| `water_mark` | EA | `CT` | `{"EA":"$tenant_account"}` |
| `wx_kx_ea_info` | _id | `-` | `{"_id":"$tenant_account"}` |

> **分库差异**: 上表为聚合清单。实际可见 collection 随租户所在分库而异 —— 例如租户 76830（Shard-35）仅 38 张、759589（Shard-57）39 张，部分表（`report_info`、`route_visit_plan`、`test_outer_user_index` 等）在某些分库上不存在；同时生产中也存在上表未收录的 collection（如 `locationArea`）。以 `show tables waiqin --tenant-id <EI> -j` 的返回为准，勿凭清单硬查。

## 俗称速查

用户口语 → 表名映射，辅助意图识别；表名来自上方 collection 清单。

| 用户说                | 表名 |
| --- | --- |
| 外勤记录 / 签到记录 / 外勤数据 | `CheckinsLog` |
| 外勤人员索引             | `CheckinsIndex` |
| 外勤规则               | `CheckinsRule` |
| 签到类型               | `check_type` |
| 签到类型分组             | `check_type_group_t` |
| 签到字段配置             | `checkin_field` |
| 外勤动作               | `customer_action` |
| 外勤人员               | `UserAccount` |
| 路线                 | `route` |
| 拜访计划               | `route_visit_plan` |
| 计划重复器              | `planRepeater` |
| 水印                 | `water_mark` |
| 动作执行数据             | `action_data` |
| 自定义对象              | `custom_object` |
| 外勤计数器              | `checkins_counter` |
| 用户日期统计             | `user_date_stat` |
| 键盘实体               | `keyboard_entity` |
| 对象外勤统计             | `object_checkins_stat` |
| 对象详情               | `object_detail` |
| 互联外勤规则 / 外部外勤规则    | `outer_rule` |
| 签到互联               | `interconnect_checkins` |
| 同步失败               | `sync_obj_fail_dataId` |
| 企业信息               | `ea_info` |

## 高频字段提示

- 外勤记录常看：`CheckinsLog.CS`、`OUA`、`CBTS`、`CBSD`、`CtT`
- 外勤人员索引常看：`CheckinsIndex.RID`、`DF`、`IsS`
- 外勤规则常看：`CheckinsRule.RN`、`CTIds`、`UIds`、`RUIds`、`nc`
- 同步失败常看：`sync_obj_fail_dataId.Ss`、`EC`、`EM`、`APIN`

字段全集和类型以 `show columns waiqin <table> -j` 及实际样本为准。

## 通用约定

- **时间字段**：均为毫秒时间戳（int64），`datetime.fromtimestamp(ts/1000)` 转 UTC+8。
- **用户标识**：统一格式 `E.{ea}.{userId}`；`OUA`（CheckinsLog 操作用户）、`CU`（CheckinsRule 创建人）。
- **空值**：部分字段仅在有值时才出现在 JSON 中，空值字段可能缺失。
