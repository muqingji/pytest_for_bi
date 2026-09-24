# aggregation：聚合计算错误排查

```yaml
symptom: 聚合错误 / 统计值偏差 / SUM/COUNT 不对 / 去重计数异常 / 时间维度聚合不准
inputs:
 required: [tenant_id, occurred_time]
 optional: [metric_name, aggregation_sql, time_dimension]
outputs:
 signals: [expected_value, actual_value, diff_ratio, aggregation_level]
 next_skills: [fx-ops-query, fx-ops-tracing, code-search]
escalate_when:
 - 聚合逻辑代码缺陷 → 回抛主控（need_further + route_hint，target_capability=code-search）
 - 去重计数问题可能与 CH 引擎特性有关 → 回抛主控（target_capability=fx-ops-query）
```

## 排查步骤

> SQL 执行入口：按 `_common.md`「查询入口总表」选择 biz 与方言（CH 业务数据 `query bi-clickhouse`、PG 元数据 `query bi-postgresql`、聚合引擎元数据 `query bi-system`、应用日志 `query biz-app-log`）。

### Step 1：复现聚合结果

拿到报表的聚合 SQL（或根据报表配置推导），手动执行：

```sql
SELECT <dimension_columns>,
    <aggregate_function>(<measure_column>) AS agg_result
FROM <ch_table>
WHERE tenant_id = '<EI>'
 AND <time_filter>
GROUP BY <dimension_columns>
```

### Step 2：对比原始数据

将聚合结果与逐条明细对比：

```sql
-- 明细数据
SELECT <dimension_columns>, <measure_column>
FROM <ch_table>
WHERE tenant_id = '<EI>'
 AND <time_filter>
 AND <dimension_filter>
ORDER BY <time_column>
```

手动计算期望值，与聚合结果对比。

### Step 3：分类根因

| 根因类型 | 特征 | 方向 |
| --- | --- | --- |
| 去重计数异常 | uniqExact vs uniq 结果差异大 | CH 的 uniq 用 HyperLogLog，有误差；需要精度时用 uniqExact |
| 时间维度聚合不准 | 按天/周/月聚合结果与预期不符 | 检查时区处理、时间字段精度（date vs datetime） |
| NULL 值影响 | SUM/COUNT 包含/排除了 NULL | 检查字段是否有 NULL 值，COUNT(*) vs COUNT(col) 差异 |
| 重复数据导致多算 | 聚合前数据有重复行 | 检查同步是否产生重复记录 |
| 聚合粒度不匹配 | 报表展示粒度与 SQL GROUP BY 粒度不同 | 检查 SQL 的 GROUP BY 是否与报表维度一致 |
| 浮点精度 | SUM 后的金额与逐条累加不一致 | 检查是否需要用 Decimal 替代 Float |

## 线上高频模式（来自 Bug 归纳）

### 模式 A：agg 消费阻塞

统计图显示数值（如 90）但 CRM 前台实际不同（如 112）。根因：agg 消费阻塞导致部分变更事件未被聚合。

排查：检查 agg 任务执行状态（是否 running/failed/queued）、MQ 消费 lag、agg 表最近更新时间。如果 agg 任务阻塞，检查阻塞原因（CH 写入慢、数据格式错误等）。

### 模式 B：agg 日志丢失导致数据不完整

聚合结果中遗漏了部分记录（如统计图显示 23 条但明细有 24 条）。根因：op-log 在某个时间窗口内丢失（如 2020-01-26 日志丢失），导致 agg 计算时缺少输入。

排查：对比 agg 表和明细表的记录，找出缺失的时间窗口，检查该窗口的 op-log 是否完整。

### 模式 C：归属部门汇总偏差

选了 4 个子部门做维度，但指标只显示 1 个部门数据。根因：归属部门字段在 agg 中的粒度处理不当（平铺 vs 层级）。

排查：检查 agg 中部门维度的 GROUP BY 逻辑，确认是按部门 ID 还是部门名称分组。验证是否因部门层级关系导致数据归并。

## 实战排查路径

### 路径 1：agg_data 聚合值的完整验证

统计图数值与预期不符时，按以下步骤在 CH 中验证 agg 数据：

**Step 1：查 agg_data 中的聚合值**

```sql
-- 查 agg_data 中的聚合值（租户列 tenant_id，对象列 object_id——无 object_api_name 列；必须用 finalizeAggregation 解码）
-- 度量列（agg_uniq_N/agg_sum_N 等）字典未列全，执行前用 show columns 实测列名
SELECT dim_string_3,
    finalizeAggregation(<agg_uniq_N_实测列名>) AS unique_count
FROM agg_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
 AND toDate(action_date) >= <time_filter>
LIMIT 20
```

注意：agg_data 中的聚合值使用了 CH 的 `AggregateFunction` 类型，查询时必须用 `finalizeAggregation()` 解码才能得到实际值。直接 SELECT 会得到二进制数据。

**Step 2：查维度映射（schema 校准）**

> ⚠️ **schema 校准（2026-09-07 hwcloud 实测）**：CH 侧 **不存在 `dim_data` 表**（`Table not found`）；当前 agg_data 自带 `dim_string_N`/`data_auth_code`/`life_status`/`object_id` 列，无需 JOIN 独立维表。旧双表架构（`dim_data` JOIN `agg_data`）的 JOIN 模式**不适用当前环境**，直接改用 agg_data 自身列过滤/取值。若确需独立维表，`dim_data` 在 **PG bi**（`query bi-postgresql`，异构库无法与 CH JOIN，只能分别查询后在分析侧关联）。

```sql
-- 当前 schema：直接从 agg_data 取维度与权限列（无需 dim_data）
SELECT object_id, dim_string_1, dim_string_2, dim_string_3,
    data_auth_code
FROM agg_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
 AND dim_string_3 = '<dimension_value>'
LIMIT 20
```

（旧架构参考，仅当环境仍为双表时使用）

```sql
-- 查 dim_data 确认维度值是否正确
SELECT dim_key, dim_string_1, dim_string_2, dim_string_3,
    data_auth_code
FROM dim_data
WHERE tenant_id = '<EI>'
 AND object_api_name = '<obj>'
 AND dim_string_3 = '<dimension_value>'
LIMIT 20
```

**Step 3：关联聚合与维度（schema 校准）**

> 当前环境 agg_data 已自含维度列，直接单表查询即可；下列 `dim_data LEFT JOIN agg_data` 仅适用旧双表架构环境（实测已下线）。

```sql
-- dim_data LEFT JOIN agg_data 查完整聚合结果
SELECT d.dim_string_3,
    finalizeAggregation(a.agg_uniq_1) AS unique_count
FROM dim_data d
LEFT JOIN agg_data a
 ON d.dim_key = a.dim_key
 AND d.object_api_name = a.object_api_name
 AND d.tenant_id = a.tenant_id
WHERE d.tenant_id = '<EI>'
 AND d.object_api_name = '<obj>'
LIMIT 50
```

这是线上排查统计图数据的标准 JOIN 模式。如果 LEFT JOIN 后右侧为空，说明 agg_data 中缺少对应的聚合记录。

**Step 4：检查 stat_field 和 udf_obj_field 元数据**

执行入口：`fx-ops idp --profile <p> query bi-system --tenant-id <EI> --sql "<SQL>" -j`（聚合引擎元数据；实测必填 `--tenant-id`）。

```sql
-- 查 stat_field 确认指标定义（租户列为 tenant_id）
SELECT id, api_name, display_name, agg_type, status
FROM stat_field
WHERE tenant_id = '<EI>'
 AND object_api_name = '<obj>'
 AND api_name = '<metric_api_name>'

-- 查 udf_obj_field 确认字段槽位映射（租户列为 ei）
SELECT id, api_name, display_name, slot, field_type, status
FROM udf_obj_field
WHERE ei = '<EI>'
 AND object_api_name = '<obj>'
 AND api_name = '<field_api_name>'
```

如果 `udf_obj_field` 的 slot 值与 `bi_mt_topology_table` 中的映射不一致，会导致查询用错误的 slot 去读 agg_data，得到错误的聚合值。

### 路径 2：去重计数偏差的排查

当 `uniq()` / `uniqExact()` 结果与业务系统不一致时：

**Step 1：确认 CH 使用的去重函数**

```sql
-- 查看 stat_field 中该指标的 agg_type
-- 如果 agg_type = 'uniq' → 使用 HyperLogLog，有约 1-2% 误差
-- 如果 agg_type = 'uniqExact' → 精确去重，无误差
SELECT api_name, agg_type FROM stat_field
WHERE tenant_id = '<EI>'
 AND api_name = '<metric_api_name>'
```

**Step 2：如果使用了 uniq，尝试用 uniqExact 对比**

```sql
SELECT uniq(<field>) AS approx_count,
    uniqExact(<field>) AS exact_count,
    abs(uniq(<field>) - uniqExact(<field>)) / uniqExact(<field>) AS error_ratio
FROM <table>
WHERE tenant_id = '<EI>'
 AND <time_filter>
```

**Step 3：如果 uniqExact 仍不对，检查源数据是否完整**

对比 PG 侧的 count(DISTINCT field) 与 CH 侧的 uniqExact(field)，差值说明同步链路丢失了部分数据。

### 路径 3：agg 槽位重复排查

统计值与明细数据不一致，且差值不是简单的"少"而是"多了不相关的值"时，可能是槽位重复：

**Step 1：查 udf_obj_field 槽位映射**

执行入口：`query bi-system`（udf_obj_field 租户列为 `ei`，无 `ea` 列）。

```sql
SELECT db_obj_name, db_field_name, field_id, slot
FROM udf_obj_field
WHERE ei = '<EI>'
 AND db_obj_name IN ('<object_table>', '<object_table>_udef')
ORDER BY slot
```

**Step 2：检查是否有多个字段共享同一 slot**

如果不同字段的 `slot` 值相同，说明槽位重复，agg 存值会互相覆盖。

**Step 3：检查是否涉及停用/启用规则的槽位冲突**

停用的规则和已启用的规则共享槽位时，会导致 agg 存值错误。

**已知根因**：
- 规则创建/删除/修改时的并发竞争
- 主题删除后相应规则未禁用，槽位未释放
- 字段槽位底层重新分配后，规则里引用的槽位值未同步更新

### 路径 4：维度/统计图全零排查

统计图全部显示 0 或维度数据缺失时：

> ⚠️ **schema 校准（2026-09-07 hwcloud 实测）**：CH 侧 `dim_data` 已不存在，下列检查改以 `agg_data` 自带维度/权限/生命状态列执行；若确认某环境仍为旧双表架构，可换查 PG bi 的 `dim_data`（`query bi-postgresql`）做侧证。

**Step 1：检查 agg_data 是否有该对象记录**

```sql
SELECT count(*) AS total, count(data_auth_code) AS has_auth
FROM agg_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
```

**Step 2：如果 agg_data 完全无数据**

可能原因：
- 主题未被 dim/agg 层检测到开启（底层主题注册/发现机制缺陷，参考 bug 1156211）
- 同步任务未执行
- 聚合数据被误删（MQ 消费阻塞级联）

**Step 3：检查 data_auth_code**

```sql
SELECT object_id, dim_string_1, data_auth_code
FROM agg_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
LIMIT 20
```

如果 `data_auth_code` 为空，非管理员用户看不到统计数据。

**Step 4：检查员工维度生命状态**

```sql
SELECT object_id, dim_string_1, life_status
FROM agg_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
 AND life_status != 'active'
LIMIT 20
```

如果已停用员工仍出现在统计图中，检查 `agg_data.life_status` 是否同步了最新的员工状态。

## 常见 CH 聚合陷阱

- `uniq()` 是近似去重，误差率约 1-2%，精确去重用 `uniqExact()`
- `toDateTime` 默认用 UTC 时区，中国时间需要 `toDateTime(col, 'Asia/Shanghai')`
- `toStartOfDay` / `toStartOfWeek` / `toStartOfMonth` 的时区参数容易漏
- `countIf` 和 `sumIf` 的条件要仔细检查边界
- `agg_data` 中的 `AggregateFunction` 类型必须用 `finalizeAggregation()` 解码
- `udf_obj_field` 的 slot 变化会导致 `bi_mt_topology_table` 映射失效

## 输出要求

本模块收口属**运维性能类**。

结论中必须包含：
- 期望值 vs 实际值，偏差比例
- 聚合 SQL 和维度信息
- 根因类型和证据
- SQL 修正建议（如果适用）
- 收口行三选一：`排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下`
