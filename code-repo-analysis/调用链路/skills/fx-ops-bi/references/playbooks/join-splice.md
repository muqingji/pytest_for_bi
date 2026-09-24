# join-splice：拼表/JOIN 异常排查

```yaml
symptom: 拼表结果不对 / JOIN 数据不正确 / 多表关联异常 / 宽表字段缺失
inputs:
 required: [tenant_id, occurred_time]
 optional: [report_id, join_config, table_names]
outputs:
 signals: [join_type, left_count, right_count, join_result_count, missing_field]
 next_skills: [fx-ops-query, fx-ops-tracing, code-search]
escalate_when:
 - 拼表配置/逻辑有代码缺陷 → 回抛主控（need_further + route_hint，target_capability=code-search）
```

## 排查步骤

> SQL 执行入口：按 `_common.md`「查询入口总表」选择 biz 与方言（CH 业务数据 `query bi-clickhouse`、PG 元数据 `query bi-postgresql`）。

### Step 1：确认拼表配置

获取拼表的 JOIN 配置：
- 左表和右表
- JOIN 类型（INNER / LEFT / RIGHT / FULL）
- JOIN 条件（关联键）
- 字段映射

### Step 2：分表验证

分别查左表和右表的数据，确认单表数据正确性：

```sql
-- 左表数据样本
SELECT <join_key>, <relevant_fields>
FROM <left_table>
WHERE tenant_id = '<EI>'
 AND <filter_conditions>
LIMIT 20

-- 右表数据样本
SELECT <join_key>, <relevant_fields>
FROM <right_table>
WHERE tenant_id = '<EI>'
 AND <filter_conditions>
LIMIT 20
```

### Step 3：验证 JOIN 结果

手动执行 JOIN 查询，对比结果：

```sql
SELECT l.<join_key>, l.<left_fields>, r.<right_fields>
FROM <left_table> l
LEFT JOIN <right_table> r ON l.<join_key> = r.<join_key>
WHERE l.tenant_id = '<EI>'
 AND <filter_conditions>
LIMIT 20
```

对比手动 JOIN 结果与报表显示结果是否一致。

### Step 4：分类根因

| 根因类型 | 特征 | 方向 |
| --- | --- | --- |
| JOIN 键不匹配 | 左表/右表关联键值不一致 | 检查数据清洗、键值格式 |
| JOIN 类型选择错误 | 应该 LEFT JOIN 用了 INNER JOIN 导致数据缺失 | 检查拼表配置 |
| 数据重复膨胀 | 一对多关联导致行数膨胀 | 检查关联粒度、是否需要去重 |
| 字段缺失 | 右表无匹配数据导致 LEFT JOIN 右侧字段为空 | 确认右表数据是否同步到位 |
| 时区/时间格式不一致 | 时间字段 JOIN 时因时区差异匹配不到 | 统一时区处理 |

## 线上高频模式（来自 Bug 归纳）

### 模式 A：CH 拼表 OOM（已知 suspended 问题）

大数据量拼表查询时 CH OOM 导致报表无法加载或导出失败。已知 TAPD Bug #1374282 和 #1385401 处于 suspended 状态（待季度复审）。

排查：检查 CH 内存使用是否接近上限，确认拼表涉及的数据量。临时解决方案：切 PG 引擎。长期方案：优化 CH 内存配置或增加节点。

### 模式 B：百分比格式化放大

拼表后源表的"销量同步增长率"在拼表中放大了 100 倍。根因：百分比格式化数据在 JOIN/拼接时未正确处理（如 0.15 显示为 15%）。

排查：检查拼表配置中百分比字段的格式化设置，确认 JOIN 后的值是否被二次格式化。

### 模式 C：纵向拼接列错位

纵向拼接后数据列出现错位（如远程拜访源表字段列与预期不符）。根因：纵向拼接时源表的列顺序或列数不一致。

排查：检查各源表的列定义是否完全一致（字段名、类型、顺序），纵向拼接要求列结构完全匹配。

### 模式 D：源表字段变为"不可用"

源表中的某个字段被停用或删除后，引用该字段的拼表无法打开。根因：拼表依赖的字段元数据与源表不同步。

排查：检查拼表引用的字段是否在源表中仍为启用状态。

### 模式 E：低基数公共维度导致笛卡尔积爆炸与查询超时（TAPD Bug #1120019471001423635）

**表现**：拼表报表或统计图加载时报“系统服务繁忙/查询超时异常”。

**机制与根因**：用户在多表拼接配置中，仅使用了低基数且重复度极高的字段（如仅使用“客户名称”）作为唯一的公共关联维度。当两张源表均存在大量同名客户历史订单时，JOIN 过程产生平方级的**笛卡尔积爆炸（Cartesian Product）**，导致计算结果集急剧膨胀并耗尽内存与查询时限。

**排查与修复**：
1. 检查拼表配置中参与关联的公共维度列表；
2. 必须要求用户为每个源表补充高基数唯一性键（如 `客户ID` + `销售订单ID` / `单据主键ID`）作为联合公共维度进行拼接。

## 输出要求

本模块收口属**运维性能类**。

结论中必须包含：
- 拼表配置（左右表、JOIN 类型、关联键）
- 分表数据量 vs JOIN 后数据量
- 根因类型和证据
- 修复建议
- 收口行三选一：`排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下`
