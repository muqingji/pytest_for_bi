# goal-management：BI 多维度目标管理排查

```yaml
symptom: 目标值不显示 / 目标完成值为空 / 完成值与报表不一致 / 目标规则初始化中 / 已停用员工出现在目标图
inputs:
 required: [tenant_id, occurred_time]
 optional: [goal_rule_id, goal_name, department_name]
outputs:
 signals: [goal_rule_status, goal_value_obj_count, agg_data_exists, agg_rule_registered, agg_data_auth_code_status]
next_skills: [fx-ops-query, fx-ops-tracing, fx-ops-monitoring]
escalate_when:
 - 目标规则状态卡死在初始化（status=1或2） → 检查离线计算是否触发
 - agg 表数据被 MQ 误删（大面积目标值突然清零）→ 回抛 fx-ops 升级
 - 已排除产品口径（共享/谁能改/T+1/离职配置）仍不对 → 才升级研发（收口：需要研发处理）
```

FAQ 里「目标主题暂不支持共享」不能用来否完成值可见。结论只能写 `排查结论：设计如此` 或 `排查结论：需要研发处理`。

## Step 0：产品口径门禁（先于 agg_rule / goal_value_obj）

### 0.1 完成值权限 ≠ 目标主题共享

- 「目标主题暂不支持共享」只约束**主题本身**
- **完成值走考核对象的数据权限/共享**（人员/客户/产品各自那套）
- 有人能在目标完成情况看到全公司目标值和完成值，但不一定有订单明细权限——完成值可见 ≠ 考核对象明细可见
- 不同角色：目标管理员可见全部完成值，但选人控件范围不一定放大；报表管理员/CRM 管理员完成值 + 选人控件都是全部。查看明细仍走个人对客户/产品的权限

### 0.2 谁能改目标值

- 多维度目标「允许个人修改」：**规则可见即可改**对应维度目标值，不是「只有管理员能改」
- 「不允许个人修改」时，按对应 FAQ 的角色矩阵，不要默认只有超管
- 自定义目标管理员角色 ≠ 预置目标管理员角色

### 0.3 T+1、组织调整、不设目标不算完成

- 新建目标规则 T+1 生效是预期（模式 E），不要当初始化卡死
- 人调整部门后，需要**重新设置目标值**才会算完成值
- 不设置目标值不算完成（新目标）
- 部门筛选查询**不包含下级部门**目标值（新目标）

### 0.4 离职员工出现在目标图

先分清：

- 目标规则/聚合未过滤停用用户 → 才是模式 G（CH `agg_data.life_status`，PG `dim_data` 做侧证）
- 驾驶舱「是否包含离职员工」只管负责人/主属部门等字段，**不管**目标规则自己的人员范围

不要用驾驶舱离职配置直接解释目标图里的停用员工。

命中 0.1–0.3 且符合口径 → `设计如此`，不要进 Step 1。

## 排查步骤

> 本模块跨三个引擎：Step 1 查 **bi-system**（PG）、Step 2 查 **PG bi**、Step 3/4 查 **CH bi**，入口命令见 `_common.md`「查询入口总表」。
> ⚠️ **schema 校准（2026-09-07 hwcloud 实测）**：`agg_data` 无 `object_describe_api_name`/`object_api_name`（对象列是 `object_id`）；`goal_value_obj` 实存 PG bi（CH 疑似存在）；`agg_effect_field` 实存 CH bi（非 bi-system）。列名以 `show columns` 实测为准，不同云/租户 schema 可能不同。

### Step 1：确认目标规则状态

执行入口：`fx-ops idp --profile <p> query bi-system --tenant-id <EI> --sql "<SQL>" -j`（实测必填 `--tenant-id`）。

```sql
-- 查目标规则是否已注册到聚合引擎
SELECT a.rule_id, a.field_id, a.create_time, a.wheres, b.field_name, b.status
FROM agg_rule a, stat_field b
WHERE a.tenant_id = '{tenant_id}'
 AND a.is_deleted = 0
 AND a.theme_api_name = 'salesgoal'
 AND a.field_id = b.field_id;
```

关注 `status` 字段：
- `status = 1`：未进入离线计算，规则未生效
- `status = 2`：初始化中，等待离线计算完成
- 正常状态：离线计算完成后的稳定态

### Step 2：确认目标值是否同步到 BI

执行入口：`fx-ops idp --profile <p> query bi-postgresql --tenant-id <EI> --sql "<SQL>" -j`（PG bi）。

> `goal_value_obj` 实存于 **PG bi**（勿先入为主按 CH 查）；`goal_value_name`/`annual_value`/`goal_rule_id` 及租户列名以 `show columns` 实测为准，类型不明先探测再比较（数值列不加引号）。

```sql
-- 查 goal_value_obj 表是否有数据（列名以 show columns 实测为准）
SELECT goal_value_name, annual_value, *
FROM goal_value_obj
WHERE tenant_id = '{tenant_id}'
 AND goal_rule_id = '{rule_id}'
 AND goal_value_name LIKE '{部门名}%'
 AND annual_value > 0;
```

如果查不到记录但 CRM 侧已设置目标值 → **goal_value_obj 同步未完成**。

### Step 3：确认聚合数据是否存在

执行入口：`fx-ops idp --profile <p> query bi-clickhouse --tenant-id <EI> --sql "<SQL>" -j`（CH bi）。

> ⚠️ **schema 校准（2026-09-07 hwcloud 实测）**：`agg_data` 无 `object_describe_api_name`/`object_api_name` 列，对象列是 `object_id`；目标值聚合按 `object_id LIKE '%{rule_id}_nogoaldetail'` 圈定。度量列名未列全，读取聚合值需先 `show columns` 实测再用 `finalizeAggregation()` 解码（见 aggregation.md）；`action_date` 为 String，按日过滤用 `toDate(action_date)`。

```sql
-- 查 agg_data 中目标完成值的聚合数据（先确认记录存在，再按需解码度量列）
SELECT object_id, dim_string_1, data_auth_code,
    toDate(action_date) AS d
FROM agg_data
WHERE tenant_id = '{tenant_id}'
 AND object_id LIKE '%{rule_id}_nogoaldetail'
LIMIT 20;
```

### Step 4：确认生效字段配置

执行入口：`fx-ops idp --profile <p> query bi-clickhouse --tenant-id <EI> --sql "<SQL>" -j`（CH bi）。

> `agg_effect_field` 实测在 **CH bi**（非 bi-system，见 `_common.md` 关键表）；`rule_id` 值域与列名以 `show columns` 实测为准。

```sql
SELECT *
FROM agg_effect_field
WHERE tenant_id = '{tenant_id}'
 AND rule_id = '{rule_id}|nogoaldetail'
LIMIT 20;
```

### Step 5：对比报表数据验证

用报表/数据看板的数据作为基准，对比目标完成情况中的值是否一致。

## 线上高频模式（来自 Bug 归纳）

### 模式 A：goal_value_obj 表少数据（最高频）

设置了目标值后，目标完成情况中显示"未设置目标值"或为 0。

**根因**：目标规则创建/修改后，数据未同步到 BI 侧的 `goal_value_obj` 表。
**排查**：查 `goal_value_obj` 表确认无记录 → 检查目标值同步任务 → 手动触发同步。
**修复**：手动触发目标值同步，或通过后台补数据。

### 模式 B：MQ 消费异常导致 agg 表数据被误删

目标完成值之前正常，突然清零或不显示。

**根因**：MQ 消费异常导致 agg 表中 `goal_value_obj` 相关的聚合数据被误删除。
**排查**：查 `agg_data` 表确认数据是否存在 → 查 MQ 消费日志 → 确认是否有误删操作。
**修复**：修复 MQ 消费逻辑，重新触发离线计算恢复数据。

### 模式 C：离线计算未触发/失败

新建目标规则后，完成值始终为空，规则状态卡在"初始化中"。

**根因**：离线计算任务未执行或执行失败，导致规则状态无法从初始化流转到正常。
**排查**：查 `agg_rule` 表的 `status` 字段 → 查离线计算任务日志 → 确认失败原因。
**修复**：手动触发离线计算任务，将规则状态推进到正常。

### 模式 D：实时计算数据不完整

目标完成值与报表统计值不一致（通常偏少）。

**根因**：实时计算跳过了部分变更事件（如订单作废、数据修改），agg 数据未及时更新。
**排查**：对比 `agg_data` 和明细数据 → 检查实时计算消费日志 → 确认是否有事件丢失。
**修复**：重新触发对应时间窗口的离线计算。

### 模式 E：规则同步延迟（T+1 机制）

新建目标规则后当日不生效。

**根因**：规则同步需等到次日（T+1 机制），属于预期行为。
**排查**：确认规则创建时间，告知客户 T+1 生效机制。

### 模式 F：字段变更导致规则自动禁用

对象字段被禁用或改名后，目标规则自动失效。

**根因**：paas/bi 两侧字段命名不一致（如 status → states），导致规则引用的字段无法匹配。
**排查**：查 `agg_effect_field`（CH bi）和 `stat_field`（bi-system）确认字段状态 → 检查字段变更记录。

### 模式 G：已停用员工出现在目标统计图

**先过 Step 0.4**：驾驶舱离职配置不管目标规则人员范围。

**根因**：聚合计算时未过滤已停用用户，或组织架构变更后历史聚合数据未清理。
**排查**：查 `agg_data` 中该人员记录的 `life_status` 状态列（CH 无独立 `dim_data`；确需维表侧证时查 PG bi 的 `dim_data`，入口 `query bi-postgresql`）→ 确认是否同步了最新的员工状态。
**修复**：重新同步组织架构数据，或手动清理历史聚合中的停用用户。

### 模式 H：包含子规则的老目标升级新 UI 时字段驼峰与下划线不兼容（TAPD Bug #1120019471001428189）

**根因**：包含子规则的老目标升级新 UI 时，父规则的 `check_dimension_fields` 属性名由下划线（`field_xxx__c`）转换为驼峰命名格式，导致查询元数据描述时找不到匹配描述直接抛系统异常。
**排查**：检查老目标规则的维度属性命名，执行历史数据刷库或让管理员重新编辑并保存该目标规则。

### 模式 I：归属部门与人员目标规则双重考核遗漏（TAPD Bug #1120019471001403903）

**表现**：员工个人业绩完成正常，但归属部门下的目标完成值未统计该人员。
**业务设计规则**：当目标规则配置为「归属部门 + 人员」联合考核时，若目标值仅配置在人员名下而该人员所在的归属部门没有单独设置目标配额，系统默认不会将该人员的完成值汇总到部门。必须在目标部门下显式为该员工配置目标值。

### 模式 J：完成值能看、明细不能看 / 被当成权限放大

客户说「他没订单权限却能看目标完成值」。

**口径**：完成值走考核对象共享；查看明细仍走个人对客户/产品权限。能看完成值不能看明细是产品行为，不是数据泄露。
**不要**：用「目标主题暂不支持共享」把完成值可见判成 bug。

### 模式 K：普通员工改了目标值被当成越权

多维度「允许个人修改」开启时，规则可见即可改。先核规则可见范围和开关，不要当权限漏洞。

## 排查决策树

```
目标管理问题
├── 目标值不显示 / 为 0
│  ├── 查 goal_value_obj → 无记录 → 同步未完成（模式 A）
│  ├── 查 goal_value_obj → 有记录 → 查 agg_rule 状态
│  │  ├── status=1 → 未进入离线计算（模式 C）
│  │  ├── status=2 → 初始化中（模式 C/E）
│  │  └── 正常 → 查 agg_data 是否存在
│  │    ├── 无数据 → agg 数据被删（模式 B）
│  │    └── 有数据 → 检查槽位映射是否正确
│
├── 完成值不显示 / 为 0
│  ├── 之前正常，突然清零 → MQ 误删（模式 B）
│  ├── 新建规则，始终为空 → 离线计算未执行（模式 C）
│  └── 数据延迟更新 → 实时计算阻塞（模式 D）
│
├── 完成值与报表不一致
│  ├── 完成值偏少 → 实时计算少数据（模式 D）
│  ├── 删除/作废后未更新 → 变更事件未触发重聚（模式 D）
│  └── 统计口径差异 → 检查 agg 聚合维度和过滤条件
│
├── 完成值能看、明细不能看 → 考核对象共享 vs 明细权限（模式 J，设计如此）
├── 普通员工能改目标值 → 先核「允许个人修改」+ 规则可见（模式 K）
│
└── 显示异常人员
  ├── 已停用员工 → 先分驾驶舱离职配置 vs 员工 life_status 状态列（模式 G / Step 0.4）
  └── 非目标部门人员 → 检查目标规则的人员范围配置
```

## 输出要求

结论中必须包含：
- Step 0 产品口径判定（完成值共享 / 谁能改 / T+1 / 离职配置是否已排除）
- 目标规则状态（agg_rule status）
- 目标值同步状态（goal_value_obj 记录数）
- 聚合数据状态（agg_data 是否存在）
- 根因类型和证据
- 建议动作（触发同步/离线计算/告知 T+1）
- 收口必须是 `排查结论：设计如此` 或 `排查结论：需要研发处理`
