# fx-ops-bi 共享约束

## 查询入口总表（执行任何 SQL 前先看这里）

BI 排查涉及四类数据，入口各不相同。**`bi` 是双方言 biz：禁止无后缀 `query bi`，会报 `dialect_required` 或推断到错误库。**

| 数据类别 | biz | 方言 | 命令模板 | 典型表 |
| --- | --- | --- | --- | --- |
| CH 业务数据（聚合结果/明细日志） | `bi` | clickhouse | `fx-ops idp --profile <p> query bi-clickhouse --tenant-id <EI> --sql "<SQL>" -j` | `agg_data`、`agg_data_history`、`agg_data_sync_info`、`agg_log_data_v1..v7`、`bi_query_log` |
| PG 业务元数据 | `bi` | postgresql | `fx-ops idp --profile <p> query bi-postgresql --tenant-id <EI> --sql "<SQL>" -j` | `dt_auth_simple`、`goal_value`、`goal_value_obj` |
| 聚合引擎元数据 | `bi-system` | postgresql | `fx-ops idp --profile <p> query bi-system --tenant-id <EI> --sql "<SQL>" -j`（**实测必填 `--tenant-id`**；WHERE 按 filterHint 拼） | `agg_rule`、`stat_field`、`udf_obj_field`、`bi_mt_topology_table`、`bi_data_sync_log`、`bi_scheduler_task` |
| copier/应用日志 | `biz-app-log` | clickhouse | `fx-ops idp --profile <p> query biz-app-log --sql "<SQL>" -j`（fixed 路由） | 按 filterHint 选表 |

执行前可用 `fx-ops idp --profile <p> show columns <biz> <table> --dialect <d> -j` 核对列名与 `filterHint`。表/列的权威字典由 fx-ops-query 技能维护，需要时经主控调度查阅，不直接引用其文件路径。

## 数据同步链路

BI 数据的关键路径：

```
业务操作 → paas-op-log → MQ 消息 → paas-bi-copier 消费 → 聚合框架 → ClickHouse 仓库 → 报表/驾驶舱
```

## 关键服务名

排查时需要查日志的服务列表：

| 服务 | 职责 | 典型排查场景 |
| --- | --- | --- |
| `paas-bi-copier` | 消费 MQ，同步数据到 CH | 同步延迟、数据丢失 |
| `fs-paas-job-schedule` | 调度计算字段重算任务 | 计算字段未生效 |
| `fs-paas-calculate-task` | 执行计算字段重算 | 重算未完成/报错 |
| `fs-paas-metadata-rest` | BI 元数据查询服务 | 字段查不到、拓扑信息 |
| 聚合框架（agg worker） | 聚合计算写入 agg_data | 聚合值不准确 |

## 关键 MQ Topic

| Topic | 用途 |
| --- | --- |
| `calculate-task-job-default` | 计算字段重算任务消息 |

## 关键表（含归属）

> 归属以 fx-ops-query 字典 + **2026-09-07 hwcloud（华为云北京四，海尔 60001247）坏列实测**为准；不同云/租户 schema 可能不同，执行前用 `show tables`（若 CLI 支持）或对目标表做 `SELECT <不存在列> FROM <表> LIMIT 1` 探测：报 `Table not found` = 表不存在，报 `Unknown identifier/column does not exist` = 表存在。

| 表 | 归属 biz（方言） | 用途 | 排查场景 |
| --- | --- | --- | --- |
| `agg_data` | `bi`（clickhouse） | 聚合数据主表；自带 `dim_string_N`/`data_auth_code`/`life_status` 列，租户列 `tenant_id`，`action_date` 为 `LowCardinality(String)`（比较需 `toDate(action_date)`） | 聚合值验证 |
| `dim_data` | **`bi`（postgresql）**（CH 实测不存在；字典未收录但 PG 实测存在） | 维度映射 + 权限编码 + 员工生命状态（旧双表架构的 CH 维表已下线） | 维度缺失、权限过滤、停用员工 |
| `mt_data` | `bi`（postgresql，字典收录） | 明细数据 | ⚠️ 字典收录但 hwcloud 60001247 **实测 not found**，按租户 `show tables` 确认后再引用 |
| `object_data` | **`bi`（clickhouse）**（字典未收录但实测存在） | 对象原始数据 | 源数据对比 |
| `stat_field` | `bi-system`（postgresql） | 指标元数据（agg_type 等） | 聚合函数确认 |
| `udf_obj_field` | `bi-system`（postgresql） | 字段槽位映射（租户列 `ei`） | slot 变化/重复导致查询错误 |
| `bi_mt_topology_table` | `bi-system`（postgresql） | 统计图拓扑表 | 统计图初始化失败 |
| `dt_auth_simple` | `bi`（postgresql） | 数据权限表 | 权限过滤异常 |
| `goal_value_obj` | `bi`（postgresql，实测存在；CH 疑似存在） | 目标值对象（BI 侧） | 目标值不显示 |
| `goal_value` | `bi`（postgresql） | 目标值主表 | 目标值同步检查 |
| `agg_rule` | `bi-system`（postgresql） | 聚合规则表 | 规则注册状态、槽位分配 |
| `agg_effect_field` | **`bi`（clickhouse）**（非 bi-system，实测存在） | 聚合生效字段表 | 规则字段配置 |
| `bi_field_desc` | **三库实测均不存在**（CH/PG/bi-system 均 `Table not found`） | 字段描述表（已下线/纯幻影） | ——：引用前必须换替代路径 |

## 已知排查限制

- **CH 日志不全**：`system.query_log` 可能因配置限制未记录所有查询，线上频繁出现"clickhouse上的日志不全导致排查困难"。此时需查 pod 级日志或上层服务日志。
- **CH DDL 阻塞**：历史字段 rename 操作会阻塞后续 DDL，导致"新建字段超时"。短期方案是将历史槽位从 rename 改为 drop。
- **topology 不自动重建**：`udf_obj_field` 的 slot 变化后，`bi_mt_topology_table` 不会自动更新，需要发消息触发重建。
- **agg 槽位重复**：规则创建/删除/修改时的并发竞争导致槽位分配冲突，停用/启用规则共享槽位。从 2019 到 2024 持续出现。
- **dim 主题未检测开启**：底层主题注册/发现机制缺陷，dim 层未检测到主题开启导致统计图全部显示 0（bug 1156211 主 bug，被 6+ 个后续 bug 引用）。
- **目标规则 T+1 生效**：新建目标规则需等到次日生效，属预期行为，但客户常误报为 bug。
- **MQ 阻塞级联影响**：MQ 消费延迟不仅导致同步延迟，还可能导致 agg 数据误删、dim 同步延迟、实时计算少数据等级联问题。
- **权限三层缓存不是一种时长**：组织成员（进部门/角色/用户组）最长 6h；PaaS 对象功能/数据权限点最长 2h；单图/单驾驶舱授权 10–30min。窗口内是预期，超窗口才查 dt_auth。
- **新基建 CH 不含作废**：作废配置已下线；「数据已作废或已删除」是查找关联记录没了。
- **订阅当天改点次日生效**：任务凌晨备好，当日仍按旧点推。

## 全局反模式

- **不要只看终端症状**：报表加载慢可能是同步延迟导致数据不全，不一定是 SQL 性能问题
- **不要跳过链路检查**：看到"数据不对"时，先确认同步链路完整性再查 SQL
- **不要忽略时间窗口**：聚合框架有窗口概念，数据可能在窗口未关闭时看不到
- **不要跨租户对比**：不同租户的同步配置、数据量、聚合策略可能不同
- **不要裸 SELECT 大表**：CH 查询必须带时间范围和租户过滤，避免全表扫描
- **不要跳过产品口径**：权限/离职/作废/驾驶舱默认值/不落库字段，先过 Step 0 再查 CH
- **不要把 FAQ 互殴当 bug**：过期口径与现行口径打架，按 playbook 建议口径收口 `设计如此`
- **收口必须按模块类别**：产品口径类（权限/对数/字段/目标/导出/订阅）必须二选一：`排查结论：设计如此` 或 `排查结论：需要研发处理`；运维性能类（同步延迟/慢查询/聚合/拼表/渲染）用：`排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下`（产品口径类过完 Step 0 后定位为纯基础设施根因时，可用后两种收口）

## 查询约定（租户过滤与方言）

- **租户过滤**：统一写 `tenant_id = '<EI>'`（`tenant_id` 的取值就是 EI，无需转换）；个别表租户列名为 `ei`（如 `bi-system` 的 `udf_obj_field`、`stat_field_level`、`bi_scheduler_task`）以表清单标注和 `show columns` 的 `filterHint` 为准；**没有 `ea` 这种列**——ea 是租户账号（EA），只在个别日志表作为列出现
- **方言**：`bi` biz 是双方言，必须 `query bi-clickhouse` / `query bi-postgresql`（或 `--dialect`），禁止无后缀 `query bi`
- 时间范围必须用 `toDate` / `toDateTime` 明确限定
- 查 `system.query_log` 做慢查询分析时，按 `query_duration_ms DESC` 排序
- 证据 SQL 必须保存到 `evidence_dir`

## 证据落盘

- 所有查询结果保存到主控分配的 `evidence_dir`
- 文件命名约定：`<模块>-<序号>-<简述>.<ext>`
- SQL 结果以 markdown 表格或 CSV 格式保存
- 结论必须引用证据文件路径
