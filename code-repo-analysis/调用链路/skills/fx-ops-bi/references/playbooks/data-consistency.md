# data-consistency：BI 数据一致性排查

```yaml
symptom: BI 数据不准 / 数据对不上 / 多算 / 漏算 / 数据重复
inputs:
 required: [tenant_id, occurred_time]
 optional: [source_table, ch_table, specific_field, sample_ids]
outputs:
 signals: [source_count, ch_count, diff_count, diff_sample_ids, root_cause_type]
 next_skills: [fx-ops-query, fx-ops-tracing, code-search]
escalate_when:
 - 大面积数据不一致（diff_count / source_count > 10%）→ 回抛 fx-ops 评估影响面
 - 不一致因代码缺陷导致 → 回抛主控（need_further + route_hint，target_capability=code-search）定位
```

FAQ 口径互殴不是同步 / 聚合 bug。结论只能写 `排查结论：设计如此` 或 `排查结论：需要研发处理`。

## Step 0：产品口径门禁（先于 copier / CH 对数）

未排除下列产品规则，禁止下「同步丢失 / 删除残留 / 聚合错误」结论。

### 0.1 报表 vs 统计图数据权限

- 报表 / 交叉表：数据权限走**主业务对象**
- 统计图：数据权限走**主题对象**
- 人员主题：只走数据负责人/来源共享
- 部门主题非目标：归属部门共享取交集；「部门主题暂不支持共享」是过期口径
- 目标完成值：走**考核对象**共享，不要用「目标主题暂不支持共享」否掉

### 0.2 作废数据：新基建 CH 不含作废

- 新基建/CH 报表**不含作废单据**，作废相关配置已下线
- 单元格提示「数据已作废或已删除」= **查找关联的那条记录没了**，不是在统计作废单
- 业务侧含作废、BI 不含 → `设计如此`，不要当删除事件没同步

### 0.3 离职/停用员工：配置只管一部分字段

「是否包含离职员工」作用范围：

- **管**：负责人、负责人主属部门，以及同类选人控件（员工 id / 人员.主属部门）
- **不管**：创建人、自定义人员、归属部门

额外：

- 人员字段为空，或图表不参与人员全局筛选 → **默认包含离职**
- 驾驶舱「图表级」= 驾驶舱里**每张图自己的**配置，**不是**个人图表上的配置
- 目标图里出现停用员工，先分清是目标规则口径还是驾驶舱离职配置，转 `goal-management.md`，不要当 dim 丢了就结案

### 0.4 驾驶舱 / 首页对数

- 企业级 vs 个人级驾驶舱范围不同，先确认类型
- 新版企业级：日期筛选可解锁，员工筛选仍锁
- 830 后：驾驶舱级默认值应覆盖个人默认值；对不上先核默认值谁生效
- 自定义部门默认只**追加**筛选、不传值，要对齐需图表级筛选
- 「用管理员身份查看」会放大个人级驾驶舱数据
- 图表放首页后受全局筛选；不参与全局筛选的图不要拿首页数去对编辑态

### 0.5 对象显示字段 / 不落库计算字段

- 查找关联跟业务侧显示值不一样：灰度 + 全局配置「是否开启查找关联字段按显示值回显」
- 对象/字段改名后图表还是旧名：先当同步延迟，不要当 CH 脏数据
- 简单公式的不落库计算字段可以做筛选/聚合；旧文档「一律不支持」过期

命中以上且符合口径 → `设计如此`，不要进 Step 1。

## 排查步骤

### Step 1：确认不一致范围

用相同过滤条件分别查源数据和 CH 仓库，对比结果：

```sql
-- 源数据（op-log 或业务表）计数
SELECT count(*) AS source_count
FROM <source_table>
WHERE <filter_conditions>

-- CH 仓库计数
SELECT count(*) AS ch_count
FROM <ch_table>
WHERE tenant_id = '<EI>'
 AND <same_filter_conditions>
```

记录差值 `diff_count = source_count - ch_count`。

### Step 2：取不一致的样本 ID

找出在源数据中存在但 CH 中缺失的记录（或反过来）：

```sql
-- 源有仓无
SELECT id
FROM <source_table>
WHERE <filter_conditions>
 AND id NOT IN (
  SELECT id FROM <ch_table>
  WHERE tenant_id = '<EI>'
   AND <same_filter_conditions>
 )
LIMIT 20

-- 仓有源无（可能是重复同步）
SELECT id, count(*) AS cnt
FROM <ch_table>
WHERE tenant_id = '<EI>'
 AND <filter_conditions>
GROUP BY id
HAVING cnt > 1
LIMIT 20
```

### Step 3：沿同步链路追因

拿着样本 ID 回追：

1. **源数据有，仓库没有**：检查这些 ID 是否经过 copier 同步（查 copier 日志或同步记录表）
2. **仓库有重复**：检查 copier 是否重复消费了同一批消息
3. **数值不一致（不是行数差异）**：检查聚合逻辑是否正确（是否重复聚合 / 聚合维度错误 / 聚合窗口重叠）

### Step 4：确定根因类型

| 根因类型 | 特征 | 方向 |
| --- | --- | --- |
| 同步丢失 | 源有仓无，且 copier 日志中找不到这些记录 | 检查 MQ 是否丢消息、copier 是否跳过 |
| 重复同步 | 仓库中同一 ID 有多条记录 | 检查 copier 消费幂等性 |
| 聚合错误 | 原始数据正确但聚合后数值偏差 | 检查聚合 SQL 逻辑、维度分组 |
| 时间窗口偏差 | 数据存在但时间归属不对 | 检查时区处理、聚合窗口边界 |
| 字段映射错误 | 某个字段值不对但其他字段正确 | 检查字段映射配置 |

## 线上高频模式（来自 Bug 归纳）

### 模式 A：paas2bi 残留数据

客户删除数据（含回收站）后 BI 仍显示旧数据。根因：paas2bi 同步管道的删除事件丢失或延迟。

排查：对比源表当前记录数 vs CH 仓库记录数，重点关注已删除但 CH 仍存在的记录。检查 copier 是否消费了删除事件。

### 模式 B：状态映射不一致

列表中订单状态为"已审批"，报表中显示"未生效"。根因：paas2bi 字段值映射与源系统不同步（枚举值变更后映射未更新）。

排查：对比同一记录在源系统和 CH 中的字段值，检查字段枚举映射配置。

### 模式 C：dim 维度数据缺失

列表/明细有数据但报表维度中缺失（如 dept_id 为 null、地理维度灰度表为空）。根因：dim 表同步不完整或维度补全任务未执行。

排查：查 dim 表中该维度的记录数，对比源表。检查 dim_sys_area_gray 等灰度维度表是否有数据。

### 模式 D：灰度引擎差异

灰度新 agg 引擎后，新旧引擎计算结果不一致。根因：灰度期间新旧引擎并行，查询路由到不同引擎。

排查：确认租户是否在灰度名单中，对比新旧引擎的 agg 结果。

### 模式 E：多时区影响

海外节点（如法兰克福）的驾驶舱数据与报表不一致。根因：CH 查询时区与业务时区不匹配。

排查：检查 CH 查询中的时区参数，对比 `toDateTime(col, 'Asia/Shanghai')` 和 `toDateTime(col)` 的结果差异。

## 实战排查路径

### 路径 1：报表数值与业务系统不一致的标准排查

业务系统显示 X 条但报表显示 Y 条（X ≠ Y）：

**Step 1：确认 PG 侧的准确值**

```sql
-- PG 侧（业务表）带相同过滤条件的 count
SELECT count(*) AS pg_count
FROM <object_table>
WHERE tenant_id = '<TENANT_ID>'
 AND <same_filter_as_report>
```

**Step 2：确认 CH 侧的值**

> ⚠️ **schema 校准（2026-09-07 hwcloud 实测）**：CH 侧无 `dim_data`（维度映射已随 agg 合入 agg_data / 移 PG）；对象列是 `object_id`（无 `object_api_name`）。下列 SQL 以 agg_data（实存，租户列 `tenant_id`）为 CH 侧基数。

```sql
-- CH 侧仓库计数（agg_data；时间列 action_date 为 String，用 toDate() 比较）
SELECT count() AS ch_count
FROM agg_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
 AND toDate(action_date) >= <同报表时间起点>
```

**Step 3：找出差异数据**

```sql
-- 找 PG 有但 CH 没有的记录（用业务主键对比；<ch_主键列> 以 show columns 实测为准）
SELECT <primary_key>
FROM <object_table> pg
WHERE pg.tenant_id = '<TENANT_ID>'
 AND pg.<primary_key> NOT IN (
  SELECT <ch_主键列_实测> FROM agg_data
  WHERE tenant_id = '<EI>'
   AND object_id = '<obj>'
 )
LIMIT 50
```

**Step 4：沿同步链路追查差异记录**

对于差异数据，检查：
1. op-log 中是否有对应的变更事件
2. copier 是否消费了该事件（查 copier 同步记录表或日志）
3. 如果 copier 已消费，检查 CH 是否写入成功（查 `agg_data`/`agg_log_data_vN` 或 `object_data`，实存于 CH）
4. 若 CH 有数据但统计图仍缺失，检查 agg 消费/聚合链路与维度状态列（`life_status`/`data_auth_code`），不要按已下线的 `dim_data` 补全任务排查

### 路径 2：聚合值不一致的排查

报表 SUM/COUNT 值与逐条累加不一致：

**Step 1：用 finalizeAggregation 验证 agg 值**

> 度量列名（`agg_sum_N`/`agg_uniq_N`）字典未列全，执行前用 `show columns` 实测；对象列 `object_id`（无 `object_api_name`）。

```sql
SELECT finalizeAggregation(<agg_sum_N_实测列名>) AS agg_value
FROM agg_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
 AND <dimension_filter>
```

**Step 2：逐条累加验证**

> `object_data` 实测存在于 CH（列名以 `show columns` 为准；租户列 `tenant_id`）。

```sql
SELECT sum(<field>) AS manual_sum
FROM object_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
 AND <same_filter>
```

**Step 3：如果逐条累加正确但 agg 值不对**

- 检查 agg 聚合窗口是否覆盖了所有变更事件
- 检查是否有变更事件丢失（op-log 不完整）
- 检查 agg 任务的消费是否阻塞

## 输出要求

结论中必须包含：
- Step 0 产品口径是否已排除（报表/统计图权限对象、作废、离职字段范围、驾驶舱默认值、对象显示字段）
- 不一致的具体数值（源 count vs 仓库 count，diff 百分比）
- 不一致的样本 ID（至少 5 个）
- 根因类型和证据
- 影响范围（是否影响报表统计结论）
- 修复建议
- 收口必须是 `排查结论：设计如此` 或 `排查结论：需要研发处理`
