---
name: fx-ops-bi
description: BI 数仓域诊断：同步延迟/推送延迟/MQ 积压之 BI 消费视角（根因排查归 fx-ops-mq）/copier 报错/数据未更新、BI 与源数据一致性对账、慢查询（CH SQL/执行计划）、拼表 JOIN 宽表、聚合计算、报表/驾驶舱渲染失败/打不开/加载慢/白屏、字段选不到/不落库、导出失败/CH OOM/超时、BI 字段权限三层缓存/改权限看不到图、目标管理（目标值/完成值/考核对象共享）、聚合订阅推送。权限/对数/字段/目标/导出/订阅类问题先过 Step 0 产品口径；收口按模块类别：产品口径类二选一（设计如此/需研发处理），运维性能类三选一（需研发处理/需基础设施或运维处理/已定位，建议动作如下）。
---

# fx-ops-bi BI 数据仓库诊断子技能

## 激活门禁

- **直进**：仅报表/数仓/聚合机制说明，无 traceId/reqId、无「排查/反馈管理员」→ 继续本 skill。
- **traceId / reqId**：用户已提供 → 仅 **fx-ops** 首跳；本 skill 仅 handoff 后执行。
- **首跳改 fx-ops**：无 trace/reqId 但有 CEP/报表异常/超时排查且尚无 handoff → 加载 **fx-ops**。
- handoff 后：读本技能 references，按主控契约回抛。

## 技能边界

### 可以做的事

- 查询 ClickHouse / MySQL 底层数据验证数据正确性
- 追踪报表请求链路（traceId → API → CH SQL → 响应耗时）
- 查看 ClickHouse 集群指标（查询 QPS、慢查询、内存、连接数）
- 查阅 paas-bi-copier 服务负责人、历史故障、发布记录
- 定位 copier / 聚合框架的代码层缺陷
- 做数据变更与同步延迟的多信号时间线关联

### 不做的事（边界外）

- **MQ 积压根因排查**归 `fx-ops-mq`；本技能仅在 handoff 后查 BI 消费视角（topic `calculate-task-job-default` 的下游表现：agg 误删、dim 延迟、少数据）
- **BI 团队告警工单 RCA** 归 `fx-ops-team-alert-rca`
- **前端性能问题**（非渲染失败语义）交回主控，并由 `fx-ops-bfe` 选择 `perf` route
- 不做主控级事故编排；需要跨域跟进时回抛主控（`need_further` + `route_hint` + `target_capability`），不直接调用兄弟技能

## 查询入口

本域四类数据入口不同，执行任何 SQL 前先查 references/playbooks/_common.md 的「查询入口总表」。关键约束：

- `bi` biz 是双方言：**必须** `fx-ops idp --profile <p> query bi-clickhouse --tenant-id <EI> --sql "<SQL>" -j`（CH）或 `query bi-postgresql`（PG），禁止无后缀 `query bi`
- 聚合引擎元数据（`agg_rule`、`stat_field`、`udf_obj_field`、`bi_mt_topology_table`）走 `query bi-system`；**该子命令实测必填 `--tenant-id`**（CLI 错误消息：`--tenant-id is required for bi <engine>`），与字典"fixed 路由免 --tenant-id"的说法相反
- copier/应用日志走 `query biz-app-log`
- 租户过滤统一 `tenant_id = '<EI>'`（值即 EI）；个别表租户列为 `ei`，以 `_common.md` 表清单和 `show columns` 的 filterHint 为准

## 模块路由

按关键词匹配模块后进入对应 playbook 展开。完整路由见 references/playbooks/index.md。

## 输出回抛

完成本领域取证后，按 fx-ops 总控回抛协议返回:
- status: completed / partial / empty / error
- findings: 模块归类和首轮取证发现
- evidence_files: 已落盘的证据文件列表
- confidence: high / medium / low
- need_further: 人类摘要，不作为唯一下一跳依据；机器路由使用 `route_hint` + `target_capability`

## 参考文档

- 诊断编排骨架（归一化输入、输入门禁） → references/diagnosis-framework.md
- 标准输出契约 → references/output-template.md
- 核心知识（同步链路、CH 性能、取证原则） → references/core-knowledge.md
- 常见错误与反模式 → references/anti-patterns.md
- 共享约束（查询入口总表、关键表归属、租户过滤） → references/playbooks/_common.md
- 模块路由表（11 个模块，模块清单唯一事实源） → references/playbooks/index.md

## 出结论前自检

- [ ] 已归一化 `tenant_id`、`bi_module`、`occurred_time`、`channel`
- [ ] 已生成并使用 `evidence_dir`
- [ ] 同步链路问题：已确认至少两段链路的状态（op-log → MQ → copier → CH）
- [ ] 数据一致性问题：已做源数据 vs 仓库数据双向对比
- [ ] 慢查询问题：已拿到 CH 慢查询 SQL + 执行计划关键指标
- [ ] 已证伪至少 1 条高概率备选路径，或明确说明未完成证伪
- [ ] 已说明是否需要回到 `fx-ops` 继续分发，或已可在当前模块收口
- [ ] 权限/对数/字段/目标/导出/订阅：已过对应 playbook Step 0 产品口径，或本模块无 Step 0
- [ ] 收口按模块类别：产品口径类（权限/对数/字段/目标/导出/订阅）为 `排查结论：设计如此` 或 `排查结论：需要研发处理` 二选一；运维性能类（同步延迟/慢查询/聚合/拼表/渲染）为 `排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下` 三选一

任一项缺失：继续补查，或明确标注"未取证"，不要编造结论。
