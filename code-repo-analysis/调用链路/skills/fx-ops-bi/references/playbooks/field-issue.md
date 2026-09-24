# field-issue：BI 字段问题排查

```yaml
symptom: 字段选不到 / 字段不显示 / 计算字段未生效 / 归属部门停用误报 / 引用字段搜索无结果
inputs:
 required: [tenant_id, occurred_time]
 optional: [field_name, object_api_name, field_type, report_id]
outputs:
 signals: [field_exists_in_backend, field_in_bi_desc, field_type_supported, calc_field_status, dept_stop_flag]
 next_skills: [fx-ops-query, fx-ops-tracing, code-search]
escalate_when:
 - 字段类型是 BI 明确不支持的（复杂不落库计算字段、部分多选/产品字段等）→ 告知用户产品限制（`设计如此`）
 - 大面积字段消失（组织架构变更触发）→ 回抛 fx-ops 评估影响面
```

FAQ 里「BI 暂不支持对象显示字段」「不落库一律不能分析」是过期口径，不要当产品限制结案。结论只能写 `排查结论：设计如此` 或 `排查结论：需要研发处理`。

## Step 0：产品口径门禁（先于字段描述侧排查）

### 0.1 对象显示字段：不是「BI 暂不支持」

查找关联 / 查找关联多选跟业务侧显示值不一样：

1. 租户是否灰度「BI 图表对象显示字段」
2. 全局配置是否开启「是否开启查找关联字段按显示值回显」
3. 灰度了仍不生效：按对应 FAQ 排查配置，不要先当 CH 取值错或字段没同步

### 0.2 对象/字段改名后图表还是旧名

先当**元数据同步延迟**，让客户重保存对象/字段触发同步（报表里缺字段同理）。不要一上来当 CH 脏数据或前端缓存。

### 0.3 不落库计算字段：简单公式可以分析

- 简单公式：支持做数据范围 / 分组 / 统计
- 复杂展示型：仍可能只展示、不能分析
- 旧字段列表写「一律不支持」→ 过期，不要用它结案
- 预设字段选不到：先分「类型本就不支持」vs「同步丢了」；后者才进 Step 1

### 0.4 计算字段未生效

试算成功但前端无值：走下方计算字段链路（job-schedule → MQ → calculate-task）。这是同步/重算问题，不是「不落库不支持」。

## 排查步骤

### Step 1：确认字段状态

```sql
-- 查字段是否在后台存在且已启用
SELECT api_name, display_name, field_type, status
FROM <field_table>
WHERE object_api_name = '<obj>'
 AND tenant_id = '<EI>'
 AND api_name = '<field_api_name>'
```

### Step 2：检查 BI 字段描述同步

字段在后台存在但报表中选不到时，检查字段描述是否同步到 BI 侧：

> ⚠️ **schema 校准（2026-09-07 hwcloud 实测）**：`bi_field_desc` 表在 CH/PG/bi-system 三库均不存在（`Table not found`），字段描述元数据以 `fs-paas-metadata-rest` 服务为准。下列 SQL 仅作语义参考，落库表以 `show tables`/`show columns` 实测为准；优先走服务日志。

```sql
-- 语义参考：BI 字段描述/映射（表名以实测为准，勿直接引用 bi_field_desc）
SELECT *
FROM <bi_field_desc_table_实测确认>
WHERE object_api_name = '<obj>'
 AND field_api_name = '<field_api_name>'
 AND tenant_id = '<EI>'
```

如果字段描述侧无该字段，说明描述同步未完成（查 `fs-paas-metadata-rest` 日志确认同步链路）。

### Step 3：分类根因

| 根因类型 | 特征 | 方向 |
| --- | --- | --- |
| BI 描述未同步 | 后台有字段但 BI 描述侧无记录 | 检查字段描述同步任务 / `fs-paas-metadata-rest` 日志 |
| 字段类型不支持 | 复杂不落库计算字段、部分多选/产品字段等 | 告知用户产品限制（先过 Step 0，简单公式不落库可以分析） |
| API Name 过长 | 字段 API Name 超出 BI 限制 | 检查字段命名规范 |
| 计算字段未重算 | 试算成功但前端无值，copier 未触发重算 | 检查计算字段重算任务 |
| 引用字段同步问题 | 引用字段配置了允许筛选但搜不到结果 | 检查引用字段在 CH 中的数据 |
| 归属部门停用误报 | 提示"已被停用"但实际未停用 | 检查 VIP 数据库部门状态映射 |
| 组织架构变更后丢失 | 调整组织架构后创建人/部门字段不显示 | 检查 dt_auth_simple 权限表同步 |

## 常见模式

### 模式 A：计算字段试算成功但前端无值

1. 检查计算字段重算任务是否触发（copier 是否收到变更事件）
2. 检查 CH 中该字段的值是否已写入
3. 如果是新增计算字段，检查全量重算是否完成

### 模式 B：归属部门停用误报

1. 查 VIP 数据库中部门的 status 字段
2. 对比 BI 维度表中部门的状态映射
3. 检查部门是否被标记为"停用"但在业务上仍在使用

### 模式 C：组织架构变更后字段丢失

1. 检查 dt_auth_simple 表是否同步了新的组织架构
2. 检查创建人/归属部门字段的映射是否指向已变更的部门 ID
3. 重新触发组织架构同步

## 实战排查路径

### 路径 1：计算字段未生效的完整追踪

计算字段试算成功但报表无值时，按以下链路逐段追查：

**Step 1：确认 job-schedule 是否触发了重算任务**

```
服务：fs-paas-job-schedule
日志关键词：calculate、schedule、trigger、重算
```

查 job-schedule 日志，确认是否为该计算字段创建了重算 job。如果未触发，检查：
- 字段变更事件是否到达 job-schedule
- job-schedule 的调度规则是否覆盖了该字段类型

**Step 2：确认 MQ 消息是否投递**

```
Topic：calculate-task-job-default
```

如果 job-schedule 已触发但 calculate-task 未执行，检查 MQ topic `calculate-task-job-default` 是否有消息积压或投递失败。

**Step 3：确认 calculate-task 是否执行**

```
服务：fs-paas-calculate-task
日志关键词：calculate、field_value、agg_data、dim_data
```

查 calculate-task 日志，确认是否收到了重算消息并开始执行。关键信息：
- 重算的 object_api_name 和 field_api_name
- 重算涉及的数据范围（全量 or 增量）
- 执行结果（成功 / 失败 / 部分成功）

**Step 4：对比 PG 和 CH 的数据量**

```sql
-- PG 侧（业务表）记录数
SELECT count(*) FROM <object_table> WHERE <filter_conditions>

-- CH 侧（agg_data 或 object_data）记录数（对象列 object_id，无 object_api_name）
SELECT count() FROM agg_data
WHERE tenant_id = '<EI>'
 AND object_id = '<obj>'
```

如果 CH 侧数量远少于 PG 侧，说明同步或重算未完成。

**Step 5：检查 topology 是否需要重建**

```
表：bi_mt_topology_table
关联表：udf_obj_field、stat_field
```

如果 `udf_obj_field` 的槽位（slot）发生了变化（如新增/删除字段导致 slot 重排），需要发消息重新生成 `bi_mt_topology_table`。否则查询可能用错误的 slot 去查 agg_data，导致字段值不正确。

### 路径 2：新增字段后报表选不到

1. 查 `fs-paas-metadata-rest` 日志，确认字段元数据是否已同步到 BI 侧
2. 查 BI 字段描述同步状态（`bi_field_desc` 表已实测不存在，改查元数据服务日志/接口确认字段是否写入 BI 侧）
3. 如果字段涉及 CH DDL（ALTER TABLE ADD COLUMN），检查 CH DDL 是否执行成功（参考 slow-query.md 模式 A）

## 输出要求

结论中必须包含：
- Step 0 产品口径判定（对象显示字段配置 / 改名同步延迟 / 不落库简单公式是否可分析）
- 字段在后台的存在状态和启用状态
- BI 字段描述同步状态（`bi_field_desc` 已实测不存在，按元数据服务日志判定）
- 根因类型和证据
- 建议动作（等待同步/重算/告知产品限制）
- 收口必须是 `排查结论：设计如此` 或 `排查结论：需要研发处理`
