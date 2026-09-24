# bi

> schema_verified_at: 2026-08-01 | platform: v5.10.0

**方言**: `clickhouse` 
**说明**: 数据仓库BI，支撑产品、许可证与模块维度的BI分析与报表 
**租户 ID**: 按表而定，见下文 

## 多方言：必须指明 dialect

`bi` 同时注册 **`clickhouse` / `postgresql`**。 本文档仅描述 **`clickhouse`** 侧；另一方言见 [`postgresql/bi.md`](../postgresql/bi.md) 或总览 [bi.md](../bi.md)。

| 操作 | 本方言（clickhouse） |
| --- | --- |
| `table list` / `table get` | 必须加 `--dialect clickhouse` |
| 执行 SQL | `query bi-clickhouse`（勿用无后缀的 `query bi`） |

另一方言 CLI：`--dialect postgresql` / `query bi-postgresql`。

**不要** 省略 `--dialect` 调用 `table list bi`，否则可能推断到错误库。

下列为 **表级租户筛选**（租户列、时间列、WHERE 模板）参考；拼 SQL 见 [filter-hint 通用规则](../../../idp-query-filter-hint.md)。

执行前用 `show columns bi <name> -j` 核对 `filterHint` 与列类型。

**查询入口**: `fx-ops idp query bi-clickhouse`（方言规则见 ../../../idp-query-clickhouse.md，biz 索引见 [index.md](./index.md)）

## 推荐流程

```bash
fx-ops idp --profile <profile> show tables bi --dialect clickhouse --tenant-id <EI> -j
fx-ops idp --profile <profile> show columns bi <table> --dialect clickhouse --tenant-id <EI> -j
fx-ops idp --profile <profile> tenant get --tenant-id <EI> -j  # 取 tenantAccount（EA）
fx-ops idp --profile <profile> query bi-clickhouse --tenant-id <EI> --sql "<SQL>" -j
```

## 表级筛选

无预置筛选模板表清单时，使用 `table get -j` 的 `filterHint`（租户/时间列推断）。

## 表字段说明

以下为已整理的表/字段含义（与筛选规则配合使用）。运行时仍以 `table get -j` 为准。

### `agg_data`

**说明**: 聚合数据主表，存储 BI 视图的聚合计算结果（含维度、指标、去重、求和等通用列）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `hash_code_without_date` | `UInt64` | - |
| `object_id` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `lang` | `LowCardinality(String)` | - |
| `owner` | `String` | - |
| `out_owner` | `String` | - |
| `life_status` | `LowCardinality(String)` | - |
| `create_time` | `String` | - |
| `last_modified_time` | `String` | - |
| `data_auth_code` | `String` | - |
| `out_tenant_id` | `String` | - |
| `out_data_auth_code` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `out_data_own_department` | `String` | - |
| `data_own_department` | `String` | - |
| `data_own_organization` | `String` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_10` | `String` | - |
| `dim_string_11` | `String` | - |
| `dim_string_12` | `String` | - |
| `dim_string_13` | `String` | - |
| `dim_string_14` | `String` | - |
| `dim_string_15` | `String` | - |
| `dim_string_16` | `String` | - |
| `dim_string_17` | `String` | - |
| `dim_string_18` | `String` | - |
| `dim_string_19` | `String` | - |
| `dim_string_20` | `String` | - |
| `dim_string_21` | `String` | - |
| `dim_string_22` | `String` | - |
| `dim_string_23` | `String` | - |
| `dim_string_24` | `String` | - |
| `dim_string_25` | `String` | - |
| `dim_string_26` | `String` | - |
| `dim_string_27` | `String` | - |
| `dim_string_28` | `String` | - |
| `dim_string_29` | `String` | - |
| `dim_string_30` | `String` | - |
| … | … | （更多列请 `table get -j`） |

### `agg_data_history`

**说明**: 聚合数据历史表，存储 BI 视图的聚合计算历史快照

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `hash_code_without_date` | `UInt64` | - |
| `object_id` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `lang` | `LowCardinality(String)` | - |
| `owner` | `String` | - |
| `out_owner` | `String` | - |
| `life_status` | `LowCardinality(String)` | - |
| `create_time` | `String` | - |
| `last_modified_time` | `String` | - |
| `data_auth_code` | `String` | - |
| `out_tenant_id` | `String` | - |
| `out_data_auth_code` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `out_data_own_department` | `String` | - |
| `data_own_department` | `String` | - |
| `data_own_organization` | `String` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_10` | `String` | - |
| `dim_string_11` | `String` | - |
| `dim_string_12` | `String` | - |
| `dim_string_13` | `String` | - |
| `dim_string_14` | `String` | - |
| `dim_string_15` | `String` | - |
| `dim_string_16` | `String` | - |
| `dim_string_17` | `String` | - |
| `dim_string_18` | `String` | - |
| `dim_string_19` | `String` | - |
| `dim_string_20` | `String` | - |
| `dim_string_21` | `String` | - |
| `dim_string_22` | `String` | - |
| `dim_string_23` | `String` | - |
| `dim_string_24` | `String` | - |
| `dim_string_25` | `String` | - |
| `dim_string_26` | `String` | - |
| `dim_string_27` | `String` | - |
| `dim_string_28` | `String` | - |
| `dim_string_29` | `String` | - |
| `dim_string_30` | `String` | - |
| … | … | （更多列请 `table get -j`） |

### `agg_data_sync_info`

**说明**: 聚合数据同步信息表，记录数据同步策略和同步状态

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | 租户id |
| `view_id` | `String` | 图id |
| `stat_view_unique_key` | `String` | 图合并stat_view_unique_key |
| `policy_id` | `String` | 同步策略的policy_id |
| `view_version` | `UInt32` | 统计图版本 |
| `batch_num` | `UInt64` | 同步批次 |
| `status` | `Int8` | sync_able:-2,sync_error:-1,sync_ing:0,sync_ed:1 |
| `timestamp` | `DateTime64(9)` | - |
| `is_deleted` | `UInt8` | - |
| `max_sync_timestamp` | `UInt64` | - |

### `agg_downstream_data`

**说明**: 聚合下游数据表，存储推送到下游系统的聚合数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `policy_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `hash_code_without_date` | `UInt64` | - |
| `object_id` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `owner` | `String` | - |
| `out_owner` | `String` | - |
| `life_status` | `LowCardinality(String)` | - |
| `create_time` | `String` | - |
| `last_modified_time` | `String` | - |
| `data_auth_code` | `String` | - |
| `out_tenant_id` | `String` | - |
| `out_data_auth_code` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `out_data_own_department` | `String` | - |
| `data_own_department` | `String` | - |
| `data_own_organization` | `String` | - |
| `ds_dim_string_1` | `String` | - |
| `ds_dim_string_2` | `String` | - |
| `ds_dim_string_3` | `String` | - |
| `ds_dim_string_4` | `String` | - |
| `ds_dim_string_5` | `String` | - |
| `ds_dim_string_6` | `String` | - |
| `ds_dim_string_7` | `String` | - |
| `ds_dim_string_8` | `String` | - |
| `ds_dim_string_9` | `String` | - |
| `ds_dim_string_10` | `String` | - |
| `ds_dim_string_11` | `String` | - |
| `ds_dim_string_12` | `String` | - |
| `ds_dim_string_13` | `String` | - |
| `ds_dim_string_14` | `String` | - |
| `ds_dim_string_15` | `String` | - |
| `ds_dim_string_16` | `String` | - |
| `ds_dim_string_17` | `String` | - |
| `ds_dim_string_18` | `String` | - |
| `ds_dim_string_19` | `String` | - |
| `ds_dim_string_20` | `String` | - |
| `ds_dim_string_21` | `String` | - |
| `ds_dim_string_22` | `String` | - |
| `ds_dim_string_23` | `String` | - |
| `ds_dim_string_24` | `String` | - |
| `ds_dim_string_25` | `String` | - |
| `ds_dim_string_26` | `String` | - |
| `ds_dim_string_27` | `String` | - |
| `ds_dim_string_28` | `String` | - |
| `ds_dim_string_29` | `String` | - |
| `ds_dim_string_30` | `String` | - |
| … | … | （更多列请 `table get -j`） |

### `agg_log_data`

**说明**: 聚合日志数据表，存储日志类型数据的聚合结果

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `hash_code_without_date` | `UInt64` | - |
| `object_id` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `owner` | `String` | - |
| `life_status` | `LowCardinality(String)` | - |
| `create_time` | `String` | - |
| `last_modified_time` | `String` | - |
| `data_auth_code` | `String` | - |
| `out_tenant_id` | `String` | - |
| `out_data_auth_code` | `String` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_10` | `String` | - |
| `dim_string_11` | `String` | - |
| `dim_string_12` | `String` | - |
| `dim_string_13` | `String` | - |
| `dim_string_14` | `String` | - |
| `dim_string_15` | `String` | - |
| `dim_string_16` | `String` | - |
| `dim_string_17` | `String` | - |
| `dim_string_18` | `String` | - |
| `dim_string_19` | `String` | - |
| `dim_string_20` | `String` | - |
| `dim_string_21` | `String` | - |
| `dim_string_22` | `String` | - |
| `dim_string_23` | `String` | - |
| `dim_string_24` | `String` | - |
| `dim_string_25` | `String` | - |
| `dim_string_26` | `String` | - |
| `dim_string_27` | `String` | - |
| `dim_string_28` | `String` | - |
| `dim_string_29` | `String` | - |
| `dim_string_30` | `String` | - |
| `dim_string_31` | `String` | - |
| `dim_string_32` | `String` | - |
| `dim_string_33` | `String` | - |
| `dim_string_34` | `String` | - |
| `dim_string_35` | `String` | - |
| `dim_string_36` | `String` | - |
| … | … | （更多列请 `table get -j`） |

### `agg_log_data_v1`

**说明**: 聚合日志数据 V1 版本

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_51` | `String` | - |
| `dim_string_51_min_5` | `String` | - |
| `dim_string_51_min_10` | `String` | - |
| `dim_string_51_min_30` | `String` | - |
| `dim_string_51_hour_1` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `agg_count_1` | `AggregateFunction(sum, Nullable(Int64))` | - |
| `agg_sum_1` | `AggregateFunction(sum, Nullable(Decimal(38, 20)))` | - |
| `agg_sum_2` | `AggregateFunction(sum, Nullable(Decimal(38, 20)))` | - |

### `agg_log_data_v2`

**说明**: 聚合日志数据 V2 版本

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_51` | `String` | - |
| `dim_string_51_min_5` | `String` | - |
| `dim_string_51_min_10` | `String` | - |
| `dim_string_51_min_30` | `String` | - |
| `dim_string_51_hour_1` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `agg_count_2` | `AggregateFunction(sum, Nullable(Int64))` | - |
| `agg_uniq_1` | `AggregateFunction(uniqExact, Nullable(String))` | - |
| `agg_sum_3` | `AggregateFunction(sum, Nullable(Decimal(38, 20)))` | - |

### `agg_log_data_v3`

**说明**: 聚合日志数据 V3 版本

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_51` | `String` | - |
| `dim_string_51_min_5` | `String` | - |
| `dim_string_51_min_10` | `String` | - |
| `dim_string_51_min_30` | `String` | - |
| `dim_string_51_hour_1` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `agg_count_6` | `AggregateFunction(sum, Nullable(Int64))` | - |

### `agg_log_data_v4`

**说明**: 聚合日志数据 V4 版本

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_51` | `String` | - |
| `dim_string_51_min_5` | `String` | - |
| `dim_string_51_min_10` | `String` | - |
| `dim_string_51_min_30` | `String` | - |
| `dim_string_51_hour_1` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `agg_count_3` | `AggregateFunction(sum, Nullable(Int64))` | - |
| `agg_uniq_2` | `AggregateFunction(uniqExact, Nullable(String))` | - |

### `agg_log_data_v5`

**说明**: 聚合日志数据 V5 版本

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_51` | `String` | - |
| `dim_string_51_min_5` | `String` | - |
| `dim_string_51_min_10` | `String` | - |
| `dim_string_51_min_30` | `String` | - |
| `dim_string_51_hour_1` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `agg_uniq_3` | `AggregateFunction(uniqExact, Nullable(String))` | - |

### `agg_log_data_v6`

**说明**: 聚合日志数据 V6 版本

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_51` | `String` | - |
| `dim_string_51_min_5` | `String` | - |
| `dim_string_51_min_10` | `String` | - |
| `dim_string_51_min_30` | `String` | - |
| `dim_string_51_hour_1` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `agg_count_4` | `AggregateFunction(sum, Nullable(Int64))` | - |

### `agg_log_data_v7`

**说明**: 聚合日志数据 V7 版本

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_version` | `UInt32` | - |
| `hash_code` | `UInt64` | - |
| `dim_string_1` | `String` | - |
| `dim_string_2` | `String` | - |
| `dim_string_3` | `String` | - |
| `dim_string_4` | `String` | - |
| `dim_string_5` | `String` | - |
| `dim_string_6` | `String` | - |
| `dim_string_7` | `String` | - |
| `dim_string_8` | `String` | - |
| `dim_string_9` | `String` | - |
| `dim_string_51` | `String` | - |
| `dim_string_51_min_5` | `String` | - |
| `dim_string_51_min_10` | `String` | - |
| `dim_string_51_min_30` | `String` | - |
| `dim_string_51_hour_1` | `String` | - |
| `action_date` | `LowCardinality(String)` | - |
| `agg_count_5` | `AggregateFunction(sum, Nullable(Int64))` | - |

### `bi_agg_flow`

**说明**: BI 聚合流程表，记录聚合任务的执行流程

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `api_name` | `String` | - |
| `sys_modified_time` | `Int64` | - |
| `bi_sys_batch_id` | `Int64` | - |
| `bi_sys_version` | `DateTime` | - |

### `bi_agg_log`

**说明**: BI 聚合日志表，记录聚合计算的运行日志

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | 租户id |
| `view_id` | `String` | 统计图去重key |
| `view_version` | `Int32` | 图版本 |
| `batch_num` | `Int64` | 批次 |
| `field_id` | `String` | 指标id |
| `start_time` | `DateTime` | - |
| `cost` | `Int64` | 指标计算耗时 |
| `is_deleted` | `Int8` | - |
| `cal_type` | `String` | 计算类型 |
| `wide_id` | `String` | 宽表id |

### `bi_chart_clustering_features`

**说明**: BI 图表聚类特征表，存储图表聚类分析的特征向量

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | 租户ID |
| `view_id` | `String` | 图表ID（用于关联） |
| `view_name` | `String` | 图表名称 |
| `chart_type` | `String` | 图表类型 |
| `schema_name` | `String` | 数据模型名称 |
| `dimensions` | `Array(String)` | 维度名称列表 |
| `measures` | `Array(String)` | 指标名称列表 |
| `filters` | `Array(String)` | 筛选条件名称列表 |
| `visit_count` | `UInt32` | 访问次数 |
| `user_count` | `UInt32` | 使用用户数 |
| `is_deleted` | `Int16` | 业务删除标记 |
| `bi_sys_is_deleted` | `UInt8` | MergeTree删除标记 |
| `bi_sys_version` | `DateTime` | 版本时间 |

### `bi_chart_knowledge`

**说明**: BI 图表知识库表，存储图表相关的知识信息

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `view_id` | `String` | - |
| `view_name` | `String` | - |
| `chart_type` | `String` | 图表类型 |
| `schema_id` | `String` | - |
| `spec` | `String` | 图表详细定义 |
| `dimension_names` | `Array(String)` | 维度名称列表 |
| `measure_names` | `Array(String)` | 指标名称列表 |
| `filter_names` | `Array(String)` | 筛选条件名称列表 |
| `field_ids` | `Array(String)` | 图表涉及的所有字段ID |
| `sys_modified_time` | `Int64` | 时间戳-精度更高 |
| `is_deleted` | `Int16` | 状态 |
| `bi_sys_flag` | `Int8` | 增量计算(变更前后标记)，默认1，变更后 |
| `bi_sys_batch_id` | `Int64` | 增量同步批次，默认0 |
| `bi_sys_is_deleted` | `UInt8` | 为mergeTree提供标记是否删除，默认0 |
| `bi_sys_version` | `DateTime` | 写入时间 |
| `bi_sys_ods_part` | `String` | 增量计算的分区(i-增量、c-计算、s-存量) |
| `usage_count` | `Int64` | 使用次数 |
| `last_modified_time` | `Int64` | - |
| `is_industry_view` | `Nullable(Int16)` | 是否行业图表 |
| `spec_markdown` | `String` | 图表详细定义-markdown格式 |
| `product_codes` | `Array(String)` | 图表关联的多个产品编码 |

### `bi_data_sync_policy_log`

**说明**: BI 数据同步策略日志表，记录数据同步策略的执行日志

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `tenant_id` | `String` | 1端企业 |
| `policy_id` | `String` | 同步策略id |
| `log_type` | `LowCardinality(String)` | 同步策略同步信息日志类型 |
| `msg` | `String` | 同步策略异常信息 |
| `is_deleted` | `UInt8` | - |
| `timestamp` | `DateTime` | - |
| `source_tenant_id` | `String` | - |

### `bi_erp_data_screen`

**说明**: BI ERP 数据大屏表，存储 ERP 数据大屏展示数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `tenantId` | `String` | - |
| `name` | `String` | - |
| `ployDetailId` | `String` | - |
| `dataCenterId` | `String` | - |
| `outSideObjApiName` | `String` | - |
| `outSideObjId` | `String` | - |
| `outDataCount` | `Nullable(Int32)` | - |
| `crmObjApiName` | `String` | - |
| `crmObjId` | `String` | - |
| `operationType` | `String` | - |
| `operationTypeDetail` | `String` | - |
| `sourceSystemType` | `String` | - |
| `operateStatus` | `String` | - |
| `historyDataType` | `Nullable(Int32)` | - |
| `executeTime` | `Nullable(Int64)` | - |
| `executeCost` | `Nullable(Int64)` | - |
| `createTime` | `Nullable(Int64)` | - |
| `updateTime` | `Nullable(Int64)` | - |
| `dataCreateTime` | `DateTime64(9)` | - |

### `bi_knowledge_embedding`

**说明**: BI 知识库向量嵌入表，存储知识文本的向量嵌入

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `knowledge_type` | `String` | 知识类型 |
| `knowledge_id` | `String` | 知识唯一标识 |
| `embedding` | `Array(Float32)` | 向量值 |
| `feature` | `String` | 特征 |
| `weight` | `Float64` | - |
| `hash_code` | `UInt64` | - |
| `sys_modified_time` | `Int64` | 时间戳-精度更高 |
| `is_deleted` | `Int16` | 状态 |
| `bi_sys_flag` | `Int8` | 增量计算(变更前后标记)，默认1，变更后 |
| `bi_sys_batch_id` | `Int64` | 增量同步批次，默认0 |
| `bi_sys_is_deleted` | `UInt8` | 为mergeTree提供标记是否删除，默认0 |
| `bi_sys_version` | `DateTime` | 写入时间 |
| `bi_sys_ods_part` | `String` | 增量计算的分区(i-增量、c-计算、s-存量) |
| `id` | `String` | - |
| `tags` | `Array(String)` | 知识标签 |
| `knowledge_sub_type` | `Nullable(String)` | 知识子类型 |
| `related_knowledge_id` | `Nullable(String)` | 关联知识ID列表 |
| `business_rules` | `String` | 业务规则JSON配置 |

### `bi_query_annotation`

**说明**: BI 查询标注表，存储用户查询的人工标注数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | 标注记录唯一标识 |
| `request_id` | `String` | 关联的问答记录ID |
| `session_id` | `String` | 关联的会话ID |
| `tenant_id` | `String` | 租户ID |
| `component_annotations` | `String` | 4个组件标注详情，JSON格式：{reasoning:{score:3, tags:["推理准确"], comments:"逻辑清晰"}, chartData:{score:4, tags:["数据准确"], comments:"图表效果好"}, insight:{score:2, tags:["解读浅显"], comments:"需更深入"}, followUp:{score:5, tags:["建议实用"], comments:"很有价值"}} |
| `round_score` | `UInt8` | 单轮回答整体评分：1-5分 |
| `round_tags` | `Array(String)` | 单轮标签：["回答质量好", "用户体验佳", "解决程度高"] |
| `round_comments` | `String` | 单轮回答的综合评价 |
| `attachments` | `String` | 附件信息JSON：[{id:"att_001", filename:"screenshot.png", url:"/uploads/xxx.png", type:"screenshot", description:"问题截图", size:1024000, hash:"md5hash"}] |
| `created_by` | `LowCardinality(String)` | 标注人ID |
| `create_time` | `Int64` | 标注时间戳(毫秒) |
| `last_modified_time` | `Int64` | 最后修改时间戳(毫秒) |
| `sys_modified_time` | `Int64` | 时间戳-精度更高 |
| `is_deleted` | `Int16` | 状态 |
| `bi_sys_flag` | `Int8` | 增量计算(变更前后标记)，默认1，变更后 |
| `bi_sys_batch_id` | `Int64` | 增量同步批次，默认0 |
| `bi_sys_is_deleted` | `UInt8` | 为mergeTree提供标记是否删除，默认0 |
| `bi_sys_version` | `DateTime` | 写入时间 |
| `bi_sys_ods_part` | `String` | 增量计算的分区(i-增量、c-计算、s-存量) |
| `processing_tags` | `Array(String)` | 处理标签：用于记录处理过程中添加的标记，例如：["需要进一步分析", "数据不完整", "优先处理"] |
| `status` | `String` | 标注处理状态：PENDING-待处理，VERIFYING-待验证，VERIFICATION_FAILED-验证失败，APPROVED-已通过，SUGGESTED_FOR_TESTCASE-建议转换测试用例 |
| `process_remark` | `String` | 处理备注：记录处理过程中的备注信息 |

### `bi_query_log`

**说明**: BI 查询日志表，记录用户的查询行为和结果

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | 问答记录唯一标识 |
| `trace_id` | `String` | 链路追踪ID，用于跟踪整个请求处理流程 |
| `session_id` | `String` | 会话ID，用于关联同一会话中的多次交互 |
| `tenant_id` | `String` | 租户ID |
| `user_id` | `String` | 用户ID |
| `request_data` | `String` | ChatBiRequest完整JSON数据，包含sessionId、instructions、history、llmModel等所有请求信息 |
| `tags` | `Array(String)` | 标签列表，包含响应类型标记、业务场景、质量标记等 |
| `query` | `String` | 用户问题文本（当前轮次的问题，冗余存储便于查询） |
| `response_components` | `String` | 响应组件信息，JSON格式，包含ReasoningResponse/ChartDataResponse/InsightResponse/FollowUpResponse四个组件内容 |
| `response_time` | `UInt32` | 响应时间(毫秒) |
| `is_context_enabled` | `UInt8` | 是否启用上下文：1-启用，0-不启用 |
| `source` | `LowCardinality(String)` | 来源：WEB/MOBILE/API/TEST等 |
| `feedback` | `Int8` | 用户反馈：1-点赞，-1-点踩，0-无反馈 |
| `feedback_comment` | `String` | 反馈备注 |
| `is_annotated` | `UInt8` | 是否已标注：1-已标注，0-未标注 |
| `query_time` | `Int64` | 问询时间戳(毫秒) |
| `created_by` | `LowCardinality(String)` | 创建人ID |
| `create_time` | `Int64` | 创建时间戳(毫秒) |
| `action_logs` | `String` | 执行日志JSON数据，包含意图识别、知识检索、数据查询、图表生成等各个Action步骤的详细日志信息 |
| `sys_modified_time` | `Int64` | 时间戳-精度更高 |
| `is_deleted` | `Int16` | 状态 |
| `bi_sys_flag` | `Int8` | 增量计算(变更前后标记)，默认1，变更后 |
| `bi_sys_batch_id` | `Int64` | 增量同步批次，默认0 |
| `bi_sys_is_deleted` | `UInt8` | 为mergeTree提供标记是否删除，默认0 |
| `bi_sys_version` | `DateTime` | 写入时间 |
| `bi_sys_ods_part` | `String` | 增量计算的分区(i-增量、c-计算、s-存量) |
| `status` | `String` | 问答状态：SUCCESS-成功，ERROR-错误，RESOLVED-已解决 |
| `error_code` | `Nullable(String)` | 错误代码：用于分类和统计错误类型 |
| `error_msg` | `Nullable(String)` | 错误消息：详细错误信息，便于调试和问题定位 |
| `intent_recognition_llm` | `String` | 意图识别阶段大模型入参和返回结果（JSON格式，含input和output字段） |
| `dsl_llm` | `String` | DSL生成阶段大模型入参和返回结果（JSON格式，含input和output字段） |
| `insight_llm` | `String` | 洞察生成阶段大模型入参和返回结果（JSON格式，含input和output字段） |
| `followup_llm` | `String` | 追问生成阶段大模型入参和返回结果（JSON格式，含input和output字段） |

### `bi_session_annotation`

**说明**: BI 会话标注表，存储用户会话的人工标注数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | Session标注记录唯一标识 |
| `session_id` | `String` | 关联的会话ID |
| `tenant_id` | `String` | 租户ID |
| `user_id` | `String` | 用户ID |
| `session_score` | `UInt8` | Session整体质量评分：1-5分 |
| `session_tags` | `Array(String)` | Session标签：["逻辑连贯", "用户满意", "完整解答", "需改进", "体验良好"] |
| `session_comments` | `String` | Session的综合文字评价 |
| `created_by` | `LowCardinality(String)` | 标注人ID |
| `create_time` | `Int64` | 创建时间戳(毫秒) |
| `last_modified_by` | `LowCardinality(String)` | 最后修改人ID |
| `last_modified_time` | `Int64` | 最后修改时间戳(毫秒) |
| `sys_modified_time` | `Int64` | 时间戳-精度更高 |
| `is_deleted` | `Int16` | 状态 |
| `bi_sys_flag` | `Int8` | 增量计算(变更前后标记)，默认1，变更后 |
| `bi_sys_batch_id` | `Int64` | 增量同步批次，默认0 |
| `bi_sys_is_deleted` | `UInt8` | 为mergeTree提供标记是否删除，默认0 |
| `bi_sys_version` | `DateTime` | 写入时间 |
| `bi_sys_ods_part` | `String` | 增量计算的分区(i-增量、c-计算、s-存量) |

### `bi_test_case`

**说明**: BI 测试用例表，存储 BI 产品的测试用例

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | 测试用例唯一标识 |
| `tenant_id` | `String` | - |
| `test_set_id` | `String` | 测试集ID |
| `case_id` | `String` | 测试用例标识，如：TC001 |
| `description` | `String` | 测试用例描述 |
| `name` | `String` | 测试用例名称，如：enterprise-82313-case1 |
| `query` | `String` | 查询语句 |
| `status` | `LowCardinality(String)` | 状态：ACTIVE-激活，INACTIVE-停用 |
| `tags` | `Array(String)` | 标签列表，包含测试场景、业务分类等 |
| `sort_order` | `UInt32` | 排序序号 |
| `difficulty_level` | `LowCardinality(String)` | 难度级别：EASY/MEDIUM/HARD |
| `expected_confidence` | `Float64` | 期望置信度 |
| `expected_intent_type` | `LowCardinality(String)` | 期望意图类型 |
| `expected_result` | `String` | 期望结果JSON数据 |
| `sys_modified_time` | `Int64` | 时间戳-精度更高 |
| `is_deleted` | `Int16` | 状态 |
| `bi_sys_flag` | `Int8` | 增量计算(变更前后标记)，默认1，变更后 |
| `bi_sys_batch_id` | `Int64` | 增量同步批次，默认0 |
| `bi_sys_is_deleted` | `UInt8` | 为mergeTree提供标记是否删除，默认0 |
| `bi_sys_version` | `DateTime` | 写入时间 |
| `bi_sys_ods_part` | `String` | 增量计算的分区(i-增量、c-计算、s-存量) |
| `last_modified_time` | `Int64` | - |
| `create_time` | `Int64` | - |

### `bi_test_run`

**说明**: BI 测试运行表，记录测试用例的执行结果

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | 测试运行唯一标识 |
| `test_set_id` | `String` | 测试集ID |
| `test_case_id` | `String` | 测试用例ID |
| `case_id` | `String` | 测试用例标识，如：TC001 |
| `tenant_id` | `String` | 租户ID |
| `user_id` | `String` | 执行用户ID |
| `agent_url` | `String` | 测试服务地址 |
| `query` | `String` | 执行的查询语句 |
| `expected_result` | `String` | 期望结果JSON |
| `actual_result` | `String` | 实际结果JSON |
| `success` | `UInt8` | 是否成功：1-成功，0-失败 |
| `error_code` | `Nullable(String)` | 错误代码 |
| `error_message` | `Nullable(String)` | 错误消息 |
| `execution_time_ms` | `UInt64` | 执行耗时(毫秒) |
| `confidence` | `Float64` | 置信度 |
| `intent_type` | `String` | 实际识别的意图类型 |
| `needs_clarification` | `UInt8` | 是否需要澄清 |
| `llm_model` | `String` | LLM模型 |
| `started_at` | `Int64` | 开始时间戳(毫秒) |
| `finished_at` | `Int64` | 结束时间戳(毫秒) |
| `sys_modified_time` | `Int64` | 时间戳-精度更高 |
| `is_deleted` | `Int16` | 状态 |
| `bi_sys_flag` | `Int8` | 增量计算(变更前后标记)，默认1，变更后 |
| `bi_sys_batch_id` | `Int64` | 增量同步批次，默认0 |
| `bi_sys_is_deleted` | `UInt8` | 为mergeTree提供标记是否删除，默认0 |
| `bi_sys_version` | `DateTime` | 写入时间 |
| `bi_sys_ods_part` | `String` | 增量计算的分区(i-增量、c-计算、s-存量) |
| `last_modified_time` | `Int64` | - |
| `create_time` | `Int64` | - |

### `bi_test_set`

**说明**: BI 测试集表，管理测试用例集合

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `tenant_id` | `String` | - |
| `name` | `String` | 测试集名称，如：enterprise-82313 |
| `description` | `String` | 测试集描述 |
| `version` | `String` | 版本号 |
| `status` | `LowCardinality(String)` | 状态：ACTIVE-激活，INACTIVE-停用 |
| `test_case_count` | `UInt32` | 测试用例数量 |
| `tags` | `Array(String)` | 标签列表，包含测试场景、业务分类等 |
| `config_info` | `String` | 配置信息 |
| `sys_modified_time` | `Int64` | 时间戳-精度更高 |
| `is_deleted` | `Int16` | 状态 |
| `bi_sys_flag` | `Int8` | 增量计算(变更前后标记)，默认1，变更后 |
| `bi_sys_batch_id` | `Int64` | 增量同步批次，默认0 |
| `bi_sys_is_deleted` | `UInt8` | 为mergeTree提供标记是否删除，默认0 |
| `bi_sys_version` | `DateTime` | 写入时间 |
| `bi_sys_ods_part` | `String` | 增量计算的分区(i-增量、c-计算、s-存量) |
| `last_modified_time` | `Int64` | - |
| `create_time` | `Int64` | - |

### `bi_view_last_access_log`

**说明**: BI 视图最近访问日志表，记录视图的最后访问时间

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `user_id` | `String` | - |
| `view_id` | `String` | - |
| `view_type` | `String` | - |
| `from` | `String` | - |
| `from_id` | `String` | - |
| `is_first_screen` | `UInt8` | - |
| `arg` | `String` | - |
| `is_deleted` | `UInt8` | - |
| `terminal` | `String` | - |
| `timestamp` | `DateTime` | - |

### `billboard_daily`

**说明**: 排行榜日表，存储每日排行榜数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `user_id` | `String` | - |
| `date` | `String` | - |
| `index_type` | `Int32` | - |
| `index_type_detail` | `String` | - |
| `ranking` | `Int32` | - |
| `value` | `Nullable(Decimal(30, 4))` | - |
| `check_type` | `Int32` | - |
| `timestamp` | `DateTime64(9)` | - |
| `part` | `String` | - |

### `billboard_monthly`

**说明**: 排行榜月表，存储每月排行榜数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `user_id` | `String` | - |
| `date` | `String` | - |
| `index_type` | `Int32` | - |
| `index_type_detail` | `String` | - |
| `ranking` | `Int32` | - |
| `value` | `Nullable(Decimal(30, 4))` | - |
| `check_type` | `Int32` | - |
| `timestamp` | `DateTime64(9)` | - |
| `part` | `String` | - |

### `billboard_quarter`

**说明**: 排行榜季度表，存储每季度排行榜数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `user_id` | `String` | - |
| `date` | `String` | - |
| `index_type` | `Int32` | - |
| `index_type_detail` | `String` | - |
| `ranking` | `Int32` | - |
| `value` | `Nullable(Decimal(30, 4))` | - |
| `check_type` | `Int32` | - |
| `timestamp` | `DateTime64(9)` | - |
| `part` | `String` | - |

### `billboard_weekly`

**说明**: 排行榜周表，存储每周排行榜数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `user_id` | `String` | - |
| `date` | `String` | - |
| `index_type` | `Int32` | - |
| `index_type_detail` | `String` | - |
| `ranking` | `Int32` | - |
| `value` | `Nullable(Decimal(30, 4))` | - |
| `check_type` | `Int32` | - |
| `timestamp` | `DateTime64(9)` | - |
| `part` | `String` | - |

### `billboard_year`

**说明**: 排行榜年表，存储每年排行榜数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `user_id` | `String` | - |
| `date` | `String` | - |
| `index_type` | `Int32` | - |
| `index_type_detail` | `String` | - |
| `ranking` | `Int32` | - |
| `value` | `Nullable(Decimal(30, 4))` | - |
| `check_type` | `Int32` | - |
| `timestamp` | `DateTime64(9)` | - |
| `part` | `String` | - |

### `biz_user_api_name_operation`

**说明**: 业务用户 API 调用统计表，按 API 名称汇总用户操作

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `name` | `String` | - |
| `tenant_id` | `String` | - |
| `operator` | `String` | - |
| `operator_dept` | `String` | - |
| `operate_time` | `Int64` | - |
| `api_name` | `String` | - |
| `operate_data_id` | `String` | - |
| `operate_type` | `String` | - |
| `app_name` | `String` | - |
| `last_modified_time` | `Int64` | - |
| `last_modified_by` | `String` | - |
| `create_time` | `Int64` | - |
| `created_by` | `String` | - |
| `data_own_department` | `String` | - |
| `owner_department` | `String` | - |
| `owner` | `String` | - |
| `connected_enterprise` | `String` | - |
| `out_owner` | `String` | - |
| `out_tenant_id` | `String` | - |
| `data_auth_code` | `String` | - |
| `out_data_auth_code` | `String` | - |
| `data_own_organization` | `String` | - |
| `out_data_own_department` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `is_deleted` | `Int8` | - |
| `bi_sys_flag` | `Int8` | - |
| `bi_sys_batch_id` | `Int64` | - |
| `bi_sys_is_deleted` | `UInt8` | - |
| `bi_sys_version` | `DateTime` | - |
| `sys_modified_time` | `Int64` | - |
| `bi_sys_modified_time` | `Int64` | - |
| `bi_sys_ods_part` | `String` | - |
| `flow_type` | `String` | - |
| `flow_name` | `String` | - |
| `traceid` | `String` | - |
| `source` | `String` | - |
| `menu_name` | `String` | - |
| `license_flag` | `Int8` | - |

### `biz_user_api_name_operation_ods`

**说明**: 业务用户 API 调用统计 ODS 层（贴源层）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `name` | `String` | - |
| `tenant_id` | `String` | - |
| `operator` | `String` | - |
| `operator_dept` | `String` | - |
| `operate_time` | `Int64` | - |
| `api_name` | `String` | - |
| `operate_data_id` | `String` | - |
| `operate_type` | `String` | - |
| `app_name` | `String` | - |
| `last_modified_time` | `Int64` | - |
| `last_modified_by` | `String` | - |
| `create_time` | `Int64` | - |
| `created_by` | `String` | - |
| `data_own_department` | `String` | - |
| `data_own_organization` | `String` | - |
| `out_data_own_department` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `owner_department` | `String` | - |
| `owner` | `String` | - |
| `connected_enterprise` | `String` | - |
| `out_owner` | `String` | - |
| `data_create_time` | `DateTime64(9)` | - |
| `sys_modified_time` | `Int64` | - |
| `bi_sys_modified_time` | `Int64` | - |
| `dt` | `String` | - |
| `flow_type` | `String` | - |
| `flow_name` | `String` | - |
| `traceid` | `String` | - |
| `source` | `String` | - |
| `menu_name` | `String` | - |
| `bi_sys_version` | `DateTime` | - |
| `license_flag` | `Int8` | - |

### `biz_user_bi_operation`

**说明**: 业务用户 BI 操作统计表，汇总用户在 BI 平台的操作行为

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `name` | `String` | - |
| `tenant_id` | `String` | - |
| `operator` | `String` | - |
| `operate_type` | `String` | - |
| `operator_dept` | `String` | - |
| `operate_time` | `Int64` | - |
| `api_name` | `String` | - |
| `object_id` | `String` | - |
| `resource_type` | `String` | - |
| `resource_name` | `String` | - |
| `app_name` | `String` | - |
| `terminal_type` | `String` | - |
| `target_rule` | `String` | - |
| `last_modified_time` | `Int64` | - |
| `last_modified_by` | `String` | - |
| `create_time` | `Int64` | - |
| `created_by` | `String` | - |
| `data_own_department` | `String` | - |
| `owner` | `String` | - |
| `owner_dept` | `String` | - |
| `connected_enterprise` | `String` | - |
| `out_owner` | `String` | - |
| `out_tenant_id` | `String` | - |
| `data_auth_code` | `String` | - |
| `out_data_auth_code` | `String` | - |
| `is_deleted` | `Int8` | - |
| `bi_sys_flag` | `Int8` | - |
| `bi_sys_batch_id` | `Int64` | - |
| `bi_sys_is_deleted` | `UInt8` | - |
| `bi_sys_version` | `DateTime` | - |
| `sys_modified_time` | `Int64` | - |
| `bi_sys_modified_time` | `Int64` | - |
| `bi_sys_ods_part` | `String` | - |
| `subscription_type` | `String` | - |
| `auth_flag` | `String` | - |
| `data_own_organization` | `String` | - |
| `out_data_own_department` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `license_flag` | `Int8` | - |

### `biz_user_bi_operation_ods`

**说明**: 业务用户 BI 操作统计 ODS 层（贴源层）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `name` | `String` | - |
| `tenant_id` | `String` | - |
| `operator` | `String` | - |
| `operate_type` | `String` | - |
| `operator_dept` | `String` | - |
| `operate_time` | `Int64` | - |
| `api_name` | `String` | - |
| `object_id` | `String` | - |
| `resource_type` | `String` | - |
| `resource_name` | `String` | - |
| `app_name` | `String` | - |
| `terminal_type` | `String` | - |
| `target_rule` | `String` | - |
| `last_modified_time` | `Int64` | - |
| `last_modified_by` | `String` | - |
| `create_time` | `Int64` | - |
| `created_by` | `String` | - |
| `data_own_department` | `String` | - |
| `owner` | `String` | - |
| `owner_dept` | `String` | - |
| `connected_enterprise` | `String` | - |
| `out_owner` | `String` | - |
| `out_data_own_department` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `data_create_time` | `DateTime64(9)` | - |
| `sys_modified_time` | `Int64` | - |
| `bi_sys_modified_time` | `Int64` | - |
| `dt` | `String` | - |
| `subscription_type` | `String` | - |
| `auth_flag` | `String` | - |
| `data_own_organization` | `String` | - |
| `bi_sys_version` | `DateTime` | - |
| `license_flag` | `Int8` | - |

### `biz_user_login_online_operation`

**说明**: 业务用户登录在线统计表，汇总用户登录和在线行为

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `name` | `String` | - |
| `tenant_id` | `String` | - |
| `login_user` | `String` | - |
| `login_user_dept` | `String` | - |
| `active_time` | `Int64` | - |
| `login_type` | `String` | - |
| `login_type_name` | `String` | - |
| `device_model` | `String` | - |
| `login_ip` | `String` | - |
| `app_name` | `String` | - |
| `last_modified_time` | `Int64` | - |
| `last_modified_by` | `String` | - |
| `create_time` | `Int64` | - |
| `created_by` | `String` | - |
| `owner` | `String` | - |
| `data_own_department` | `String` | - |
| `connected_enterprise` | `String` | - |
| `out_owner` | `String` | - |
| `out_tenant_id` | `String` | - |
| `data_auth_code` | `String` | - |
| `out_data_auth_code` | `String` | - |
| `data_own_organization` | `String` | - |
| `out_data_own_department` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `is_deleted` | `Int8` | - |
| `bi_sys_flag` | `Int8` | - |
| `bi_sys_batch_id` | `Int64` | - |
| `bi_sys_is_deleted` | `UInt8` | - |
| `bi_sys_version` | `DateTime` | - |
| `sys_modified_time` | `Int64` | - |
| `bi_sys_modified_time` | `Int64` | - |
| `bi_sys_ods_part` | `String` | - |
| `traceid` | `String` | - |
| `portal_site_id` | `String` | - |
| `license_flag` | `Int8` | - |

### `biz_user_login_online_operation_ods`

**说明**: 业务用户登录在线统计 ODS 层（贴源层）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `name` | `String` | - |
| `tenant_id` | `String` | - |
| `login_user` | `String` | - |
| `login_user_dept` | `String` | - |
| `active_time` | `Int64` | - |
| `login_type` | `String` | - |
| `login_type_name` | `String` | - |
| `device_model` | `String` | - |
| `login_ip` | `String` | - |
| `app_name` | `String` | - |
| `last_modified_time` | `Int64` | - |
| `last_modified_by` | `String` | - |
| `create_time` | `Int64` | - |
| `created_by` | `String` | - |
| `owner` | `String` | - |
| `data_own_department` | `String` | - |
| `data_own_organization` | `String` | - |
| `out_data_own_department` | `String` | - |
| `out_data_own_organization` | `String` | - |
| `connected_enterprise` | `String` | - |
| `out_owner` | `String` | - |
| `data_create_time` | `DateTime64(9)` | - |
| `sys_modified_time` | `Int64` | - |
| `bi_sys_modified_time` | `Int64` | - |
| `dt` | `String` | - |
| `traceid` | `String` | - |
| `portal_site_id` | `String` | - |
| `bi_sys_version` | `DateTime` | - |
| `license_flag` | `Int8` | - |

### `dim_name_data`

**说明**: 维度名称数据表，存储维度字段的名称映射

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `String` | - |
| `data_id` | `String` | - |
| `describe_api_name` | `String` | - |
| `tenant_id` | `String` | - |
| `name` | `String` | - |
| `lang` | `String` | - |
| `last_modified_time` | `Int64` | - |
| `i18n_key` | `String` | - |
| `sys_modified_time` | `Int64` | - |
| `bi_sys_flag` | `Int8` | - |
| `bi_sys_batch_id` | `Int64` | - |
| `bi_sys_is_deleted` | `UInt8` | - |
| `bi_sys_version` | `DateTime` | - |
| `timestamp` | `DateTime64(9)` | - |

### `dim_value_embedding`

**说明**: 维度值向量嵌入表，存储维度值的向量嵌入

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `String` | - |
| `dimension_id` | `String` | mt_dimension.diemnsion_id |
| `field_id` | `String` | udf_obj_field.field_id |
| `type` | `String` | udf_obj_field.type |
| `biz_type` | `String` | employee、department、country、province、city、custom_type、name |
| `option_id` | `String` | MD5码 |
| `value` | `String` | 主属性ID、组织架构ID、枚举Code |
| `display_value` | `String` | 显示值/文本-- 向量相关字段 |
| `embedding` | `Array(Float32)` | 向量化数据 |
| `is_deleted` | `UInt8` | - |
| `create_time` | `Int64` | - |
| `bi_sys_is_deleted` | `UInt8` | - |
| `bi_sys_version` | `DateTime` | - |
| `describe_api_name` | `String` | crm obj 名称 |

### `dwd_inc_id_wide_data`

**说明**: DWD 层增量 ID 宽表，存储明细增量数据

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `tenant_id` | `LowCardinality(String)` | - |
| `batch_num` | `UInt64` | - |
| `rule_id` | `LowCardinality(String)` | - |
| `hash_code` | `UInt64` | - |
| `wide_string_1` | `String` | - |
| `wide_string_2` | `String` | - |
| `wide_string_3` | `String` | - |
| `wide_string_4` | `String` | - |
| `wide_string_5` | `String` | - |
| `wide_string_6` | `String` | - |
| `wide_string_7` | `String` | - |
| `wide_string_8` | `String` | - |
| `wide_string_9` | `String` | - |
| `wide_string_10` | `String` | - |
| `wide_string_11` | `String` | - |
| `wide_string_12` | `String` | - |
| `wide_string_13` | `String` | - |
| `wide_string_14` | `String` | - |
| `wide_string_15` | `String` | - |
| `wide_string_16` | `String` | - |
| `wide_string_17` | `String` | - |
| `wide_string_18` | `String` | - |
| `wide_string_19` | `String` | - |
| `wide_string_20` | `String` | - |
| `wide_string_21` | `String` | - |
| `wide_string_22` | `String` | - |
| `wide_string_23` | `String` | - |
| `wide_string_24` | `String` | - |
| `wide_string_25` | `String` | - |
| `wide_string_26` | `String` | - |
| `wide_string_27` | `String` | - |
| `wide_string_28` | `String` | - |
| `wide_string_29` | `String` | - |
| `wide_string_30` | `String` | - |
| `timestamp` | `DateTime64(9)` | - |
| `is_deleted` | `UInt8` | - |
| `pg_db_name` | `LowCardinality(String)` | - |
