---
name: a22-existing-asset-discovery
description: "在 A22 中构造或复用 112 BI 测试资产，并用业务 API 与 bug-finder 只读取证验证源数据、拓扑、维度、聚合和基线。修改 A22 数据构造、脏数据反查或 N27 验收时使用。"
---

# A22 已有测试资产发现

A22 内部先发现、后规划，不增加工作流节点。系统在派发 A22 前生成只读的
`existing_asset_discovery`，A22 只能消费证据，不直接读取凭证或调用任意网络工具。
确定性实现位于 `src/qa_agents/existing_asset_discovery.py`；A22 派发器在同一组件内部调用，
不是独立工作流节点。候选清单来自 `a22_existing_asset_inventory`，未配置时读取当前运行登记的
`current/constructed-test-assets.json`。外部数据库取证只经 `bug-finder` 登记的公共
`fxops_query` CLI 调用，不导入其内部模块，也不允许写 SQL。

## 选择规则

- 对每个 case 先检查 `existing_asset_discovery.candidates`。
- 只选择 `decision=reusable`，且 `case_id`、`resource_key`、`resource_type` 与当前需求完全一致的候选。
- 名称相似、关键词命中或模型推断不能授权复用。
- 所需资源全部有合格候选时使用 `lifecycle_mode=existing_read_only`；任一资源缺失时按原能力目录走 `create`，禁止拼凑半套场景。
- 输出中的 `resource_id`、`existing_asset_evidence`、`discovery`、`readiness`、`validity_contract` 和 `discovery_hash` 必须逐字复制冻结输入；`resource_id_variable` 沿用当前资源需求。N08 会将已有 `resource_id` 注入该变量，并再次执行冻结的只读验真步骤。

## 构造与验真

- 新建资产仍由现有受控业务 API 完成；`bug-finder` 只负责查询证据。
- 图表创建计划必须声明 fail-closed 的 `validity_contract`。配置回读、源数据、
  `bi_mt_topology_table`、`dim_data`、`agg_data` 和基线查询均通过，才能判定有效。
- `integrity_probes` 由确定性组件执行，`argv` 从 `idp` 开始（外层已固定为公共
  `fxops_query`），必须带租户/环境范围、精确资产或对象条件和
  `LIMIT`；响应冻结为 `test-data-integrity-evidence/1.0`，只记录行数、状态和响应哈希。
- 任一检查为空、失败、超时、结构不符或证据哈希改变，都不得标记 `reusable`。
- 失败后按证据分类：源无数据则重选/重造源记录；拓扑缺失则重建图表；dim/agg 缺失则
  等待同步或修复字段/slot 后重建；仅目标请求失败而基线和对照成功时才进入产品缺陷判断。

## 合格证据

可复用图表必须同时具备：真实资源 ID、在线配置回读成功、配置哈希、基线查询通过、
基线响应哈希，以及 source/topology/dim/agg 四类完整性证据。TraceId 有记录时必须原样保留。

A22 不得自行生成哈希、TraceId 或成功状态。N27 必须把未绑定冻结候选、字段被改写、缺少在线回读或缺少基线验证的计划判为无效。

## 回退

发现失败、候选不完整、配置改变或基线失败时使用 `create`。不能因为复用失败而跳过 case，也不能把未验证资源交给 N08。
