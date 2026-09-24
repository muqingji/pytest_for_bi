# 对象 PG/Elasticsearch 查询与对账

适用于用户明确指定查 Elasticsearch，或要求在相同业务条件下比较对象 PG 与 Elasticsearch。普通查询使用 SOQL，由平台完成元数据字段映射和 Elasticsearch DSL 编译；不要为这类查询手写 DSL。

## 输入与前置

单对象查询先确定以下输入，缺一项就先补齐，不猜。企业 Elasticsearch 总量只要求 `profile` 和 `tenant_id`，不要求对象：

| 输入 | 来源 |
| --- | --- |
| `profile` | 租户所在环境 |
| `tenant_id` | 已解析的租户上下文 |
| `object_api_name` | 对象文档或 `object describe list` |
| 字段 API 名 | 对象文档或 `object describe get` |
| 业务范围 | 用户给出的 ID、时间窗和筛选条件 |

## 企业 Elasticsearch 数据总量

用户要求"不限定对象的企业 Elasticsearch 总量"时，不要默认补 `AccountObj`，也不要让模型手工读取 CMS 或拼 tenant-router。直接执行无对象 `count`：

```bash
fx-ops idp --profile <profile> es query \
  -t <TENANT_ID> \
  --operation count \
  --dsl '{"query":{"match_all":{}}}' -j
```

平台会读取 `fs-sql2esdsl.sharding_config`：默认路由 count 排除已配置的大对象，再逐个查询大对象专属路由并累加。服务端强制注入 `ei=<TENANT_ID>`；调用方不传 `api_name`。

响应解释：

- `result.count`：默认路由与全部大对象路由的汇总总量。
- `result.routeCounts`：每条默认/对象路由的分项 count、当前路由和索引证据。
- `warnings` 包含 `count_aggregated_across_routes`：本次确实跨多条路由汇总。
- 配置、默认路由或任一大对象路由失败：整体失败，禁止把已返回或自行重跑得到的部分 count 描述为企业总量。

无对象模式只用于 `count`。search、mapping、field-caps 和 analyze 仍必须提供 `--object`；跨路由命中列表和任意聚合不能通用合并。

首次查询对象时校验字段：

```bash
fx-ops idp --profile <profile> object describe get <ObjectApiName> \
  -t <TENANT_ID> --verbose -j
```

## 指定数据源查询

默认 source 是 PG，但诊断证据中显式写出 source，避免结果来源不清楚：

```bash
fx-ops idp --profile <profile> object query \
  -t <TENANT_ID> \
  --source pg \
  --soql "SELECT id, name FROM <ObjectApiName> WHERE <CONDITION> ORDER BY id LIMIT 100" -j

fx-ops idp --profile <profile> object query \
  -t <TENANT_ID> \
  --source es \
  --soql "SELECT id, name FROM <ObjectApiName> WHERE <CONDITION> ORDER BY id LIMIT 100" -j
```

两条命令的租户、对象、SELECT、WHERE、GROUP BY、ORDER BY 和 LIMIT 必须一致，唯一差异只能是 `--source`。平台会把 `fieldApiName` 映射为元数据 `indexName`，再根据实时 field caps 选择可用的 keyword/wildcard 字段和当前 tenant-router 索引。

## 对账顺序

### 1. 比较 count

对同一份 count SOQL 分别查 PG 和 Elasticsearch：

```bash
fx-ops idp --profile <profile> object query -t <TENANT_ID> --source pg \
  --soql "SELECT COUNT(*) AS total FROM <ObjectApiName> WHERE <CONDITION>" -j

fx-ops idp --profile <profile> object query -t <TENANT_ID> --source es \
  --soql "SELECT COUNT(*) AS total FROM <ObjectApiName> WHERE <CONDITION>" -j
```

count 相同只能说明数量一致，不能证明记录和值完全一致；需要时继续比较 ID。

### 2. 比较 ID 集合

固定 `ORDER BY id LIMIT 100`，两边使用相同 SOQL。响应 `hasMore=true` 时，分别使用各自返回的 `next` 继续翻页：

```bash
fx-ops idp --profile <profile> object query -t <TENANT_ID> --source <pg|es> \
  --soql "SELECT id FROM <ObjectApiName> WHERE <CONDITION> ORDER BY id LIMIT 100" \
  --next '<NEXT_JSON_ARRAY>' -j
```

报告默认展示前 100 个 PG-only 和 ES-only ID，并注明是否还有后续页。用户要求完整清单时继续翻页后落盘，不把大列表全部塞进对话。

### 3. 比较同 ID 的原始时间戳

对共同 ID 或疑似延迟 ID 查询 PG `sys_modified_time` 与 Elasticsearch 映射后的 `sys_ts`。SOQL 字段仍写业务 API 名 `sys_modified_time`，并关闭时间展示转换：

```bash
fx-ops idp --profile <profile> object query -t <TENANT_ID> --source pg \
  --disable-time-transform \
  --soql "SELECT id, sys_modified_time FROM <ObjectApiName> WHERE id IN ('<ID>') ORDER BY id LIMIT 100" -j

fx-ops idp --profile <profile> object query -t <TENANT_ID> --source es \
  --disable-time-transform \
  --soql "SELECT id, sys_modified_time FROM <ObjectApiName> WHERE id IN ('<ID>') ORDER BY id LIMIT 100" -j
```

比较响应中的原始值，不转换毫秒、秒、时区或字符串格式。值相等就是一致；PG 值大于 Elasticsearch 值才形成"Elasticsearch 可能滞后"的证据。

### 4. 比较同 ID 的业务字段值

当记录两边都存在，但用户反馈某字段筛选、聚合或展示值不对时，用同一 SOQL 同时查询目标字段和可能相关的计算/统计字段：

```bash
fx-ops idp --profile <profile> object query -t <TENANT_ID> --source <pg|es> \
  --disable-time-transform \
  --soql "SELECT id,<FIELD_A>,<FIELD_B>,sys_modified_time FROM <OBJECT_API_NAME> WHERE id IN ('<ID>') ORDER BY id LIMIT 100" -j
```

按以下顺序分流：

- PG `sys_modified_time` 大于 Elasticsearch `sys_ts`：保留为同步延迟候选。
- 时间戳相等但目标字段值不同：不能归因同步延迟，回抛 `need_further: 元数据 Elasticsearch 字段映射/物理槽位专项取证`。
- Elasticsearch 中两个逻辑字段总是返回同一值，而 PG 中两字段不同：优先检查两个字段是否共享 `index_name`，回抛 `index_slot_collision_candidate`。
- 字段槽位唯一：继续检查 mapping、派生字段写入和最终查询 DSL。

本层只形成候选并回抛，不在数据查询能力中展开元数据 oplog、原始 RequestLog 或源码归因。

## PG-only ID 的删除态归类

Elasticsearch 只包含 active 记录，不同步以下 PG 逻辑删除数据：

| PG `is_deleted` | 含义 | 对账归类 |
| --- | --- | --- |
| `-1` | 普通逻辑删除 | `expected_excluded` |
| `-2` | 批量工具逻辑删除 | `expected_excluded` |

主对账保持默认 active 范围。发现 PG-only ID，或用户给定的缺失 ID 在 active PG 也查不到时，再仅在 PG 做二次归类：

```bash
fx-ops idp --profile <profile> object query -t <TENANT_ID> --source pg \
  --life-status all_with_deleted \
  --disable-time-transform \
  --soql "SELECT id, is_deleted, sys_modified_time FROM <ObjectApiName> WHERE id IN ('<PG_ONLY_ID>') ORDER BY id LIMIT 100" -j
```

- `-1/-2` 从可行动漏数中剔除，但保留在报告的"预期排除"统计里。
- `is_deleted=0` 且 Elasticsearch 不存在，才继续按同步、路由、mapping 或查询语义排查。
- `life_status` 是业务字段，与 `is_deleted` / Elasticsearch `is_del` 没有对应关系，禁止用于删除态归类。
- 不对 Elasticsearch 执行 `recycled`、`pending_purge` 或 `all_with_deleted`；Elasticsearch 本身没有这些记录。
- 若 `--life-status all_with_deleted` 因 recycle-read 权限被拒绝，删除态标为 `unverified`，不能把该 ID 计入已确认的 Elasticsearch 漏数。

## 聚合对比

枚举分布、分组统计和聚合也使用同一 SOQL 双源执行：

```bash
fx-ops idp --profile <profile> object query -t <TENANT_ID> --source pg \
  --soql "SELECT <ENUM_FIELD>, COUNT(*) AS total FROM <ObjectApiName> WHERE <CONDITION> GROUP BY <ENUM_FIELD>" -j

fx-ops idp --profile <profile> object query -t <TENANT_ID> --source es \
  --soql "SELECT <ENUM_FIELD>, COUNT(*) AS total FROM <ObjectApiName> WHERE <CONDITION> GROUP BY <ENUM_FIELD>" -j
```

不要因为 Elasticsearch 是检索引擎就绕过 SOQL 手写 DSL。只有复现已有线上搜索 DSL、检查 mapping/field caps 或验证分词时，才进入受控的 `idp es query` 原始诊断。

## 输出合同

```text
scope: tenant / object / condition / time window
pg_count: <N>
es_count: <N>
pg_only: <N> (first 100 IDs, has_more)
es_only: <N> (first 100 IDs, has_more)
expected_excluded: <N> (-1 ordinary delete, -2 bulk-tool delete)
timestamp_equal: <N>
timestamp_mismatch: <N> (raw PG sys_modified_time, raw ES sys_ts)
field_value_mismatch: <N>
index_slot_collision_candidate: true | false | unverified
actionable_difference: <N>
next_step: none | inspect metadata slot | inspect search log | inspect route/mapping | inspect sync writer
```

结论必须引用实际命令和结果。count 不同但尚未取得差异 ID 时只能报 `partial`，不能直接断言 Elasticsearch 同步故障。

## 已知限制

`ES-FONESHARE-*` 格式的集群别名（foneshare 生产环境 default 路由）依赖平台侧别名解析。若 `--source es` 或 `idp es query` 返回 `ROUTE_ERROR` 且消息包含 `cluster_alias_unresolved`，说明当前环境暂不支持该操作，应标记为 `partial` 并注明平台限制，不报告为 Elasticsearch 同步故障。
