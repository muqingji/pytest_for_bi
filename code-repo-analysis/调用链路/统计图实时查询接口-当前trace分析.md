# 统计图“实时查询”当前 Trace 调用链分析

## 1. 分析对象与结论

| 项目 | 当前事实 |
| --- | --- |
| traceId | `FSW-fktest7572.1001-0mt2ru8o8l3b7cghc0i0` |
| 企业 / 用户 | `fktest7572` / `fktest7572.1001`，`ei=816324` |
| 网关时间 | `2026-08-21 17:53:11.173` |
| 网关接口 | `/FHH/EM1HBISTAT/fs-bi-stat/stat/data/query` |
| 应用入口 | `fs-bi-stat`，Pod `fs-bi-stat-786759494c-nzqp9` |
| 返回 | CEP 200；Tomcat 200 |
| 耗时 | CEP `1214 ms`；Tomcat `1209 ms`；EasyStat 内部总账 `597 ms` |

结论先行：这条请求确实是一次“实时发起”的统计图查询，但从真实入口 URI 看，它仍然走统计图接口 `/stat/data/query`，不是明细接口 `/stat/detail/data/query`。应用日志又出现了 `PreSqlCHBDSampleQueryFlowNode`、`DataQueryPageLimitAsyncQueryFlowNode` 和统计图结果缓存写回，说明它沿用了与预聚合查询相同的 EasyStat 统计图流水线。现有证据不足以证明 `dataQuerySource`、`dbObjName` 或最终 ClickHouse 表名，因此不能把“实时查询”直接等同于“实时扫描明细表”。更稳妥的判断是：**实时触发 + 预聚合式统计图执行框架；底层数据源尚未被入口参数/SQL 证据最终确认，当前更偏向仍读预聚合数据。**

## 2. 调用链路

```text
纷享 Web（FSW）
  -> CEP 网关（BISTAT / EM1HBISTAT）
  -> fs-bi-stat /stat/data/query
  -> StatBaseController（图查询入口、缓存、权限和配置）
  -> EasyStat RootFlowServiceImpl
       -> 组织/权限前置上下文（部分节点是否执行，当前未完整打印）
       -> PreSqlCHBDSampleQueryFlowNode（124 ms）
       -> DataQueryPageLimitAsyncQueryFlowNode（281 ms）
       -> DataQueryFlowNode（EasyStat-watch-dataQuery-sql 280 ms）
       -> 统计结果组装/资源释放
  -> bi_stat_querycache_*_binary 写回
  -> CEP 返回 200
```

当前 trace 能直接证明的应用日志如下：

| 时间 | 日志 / 节点 | 事实 |
| --- | --- | --- |
| 17:53:12.326 | `DataQueryFlowNode` | `EasyStat-watch-dataQuery-sql = 280 ms` |
| 17:53:12.326 | `RootFlowServiceImpl` | `EasyStat-MainStep-2 = 280 ms` |
| 17:53:12.328 | `RootFlowServiceImpl` | `EasyStat-MainStep-3 = 1 ms` |
| 17:53:12.336 | `RootFlowServiceImpl` | `EasyStat-MainStep-3.1 = 7 ms` |
| 17:53:12.336 | `RootFlowServiceImpl` | `DataQueryPageLimitAsyncQueryFlowNode = 281 ms`；`PreSqlCHBDSampleQueryFlowNode = 124 ms`；`StatBuildModelBasicCoreViewFieldMultiCurrencyNode = 113 ms` |
| 17:53:12.336 | `RootFlowServiceImpl` | `EasyStat-watch-all = 597 ms` |
| 17:53:12.383 | `StatBaseController` | `cacheSyncReqResultWithBinary`，出现 `bi_stat_querycache_*_binary` 请求键 |
| 17:53:12.384 | `tomcat_access_dist` | `/fs-bi-stat/stat/data/query`，HTTP 200，`time_cost=1209 ms` |

`cacheSyncReqResultWithBinary:4588` 是日志中的写回记录值，当前证据没有说明它是毫秒，不能把 4588 当耗时。

## 3. 当前耗时分解

### 3.1 已观测耗时

| 层次 | 耗时 | 解释 |
| --- | ---: | --- |
| EasyStat 总账 | 597 ms | 重构流水线自身的 StopWatch |
| 主数据查询 | 280 ms | `DataQueryFlowNode` / `MainStep-2` |
| 分页节点 | 281 ms | `DataQueryPageLimitAsyncQueryFlowNode`，与主查询基本重合 |
| 预 SQL 采样 | 124 ms | `PreSqlCHBDSampleQueryFlowNode` |
| 多币种模型节点 | 113 ms | `StatBuildModelBasicCoreViewFieldMultiCurrencyNode`，当前 trace 突出节点 |
| CEP 网关 | 1214 ms | 用户请求端到端网关耗时 |
| Tomcat | 1209 ms | 应用 HTTP 入口耗时 |

EasyStat 总账到 Tomcat 入口之间约有 `612 ms`（`1209-597`）未被这组 StopWatch 覆盖；CEP 到 Tomcat 约 `5 ms`。这 `612 ms` 不能直接归因于 ClickHouse，可能包含入口参数/图配置/权限准备、超时降级封装、结果序列化、缓存写回及日志观测未覆盖段。

### 3.2 与历史预聚合样本的量化对照

历史样本见 [统计图预聚合查询接口-调用链路分析.md](/Users/liushanshan/code/my/pytest_for_bi/code-repo-analysis/调用链路/统计图预聚合查询接口-调用链路分析.md)，其 trace 为另一条请求 `FSW-fktest7572.1001-0mt2cugmb6ngk5upexig`，不能当作当前 trace 事实。

| 指标 | 当前 trace | 历史预聚合样本 | 差异 |
| --- | ---: | ---: | ---: |
| EasyStat 总账 | 597 ms | 1407 ms | 当前少 810 ms，约为 42.4% |
| 主数据查询 | 280 ms | 851 ms | 当前少 571 ms |
| `PreSqlCHBDSampleQueryFlowNode` | 124 ms | 188 ms | 当前少 64 ms |
| 分页节点 | 281 ms | 852 ms | 当前少 571 ms |
| CEP 请求 | 1214 ms | 1873 ms | 当前少 659 ms |

当前请求更快，主要差异来自主查询/分页阶段，而不是预 SQL 采样阶段。当前新增的可见节点是多币种模型节点 113 ms；历史样本没有该节点日志。当前没有打印历史样本中的 `MainStep-1`、主属部门权限节点等信息，不能据此断言这些节点一定没有执行，最多只能说“本次目标 trace 日志未观察到”。

## 4. 与预聚合查询的差异

### 4.1 可以确认的差异

| 对比维度 | 当前“实时查询” trace | 历史预聚合查询样本 |
| --- | --- | --- |
| 业务语义 | 用户侧称实时查询；请求发生在实时点击/刷新场景 | 用户侧称预聚合查询 |
| Trace / 时间 | `...0mt2ru8o8l3b7cghc0i0`，17:53:11 | `...0mt2cugmb6ngk5upexig`，另一时间/另一请求 |
| URI | `/stat/data/query` | `/stat/data/query` |
| 执行框架 | EasyStat 重构；有预 SQL 采样、真分页节点、统计图缓存 | EasyStat 重构；有组织权限前置、预 SQL 采样、真分页节点、统计图缓存 |
| 主查询 | 280 ms | 851 ms |
| 结果缓存 | 有 `bi_stat_querycache_*_binary` 写回日志 | 有同类二进制结果缓存写回 |
| 当前突出的节点 | `StatBuildModelBasicCoreViewFieldMultiCurrencyNode` 113 ms | `PreSqlBaseDataMainDeptAuthDataFlowNode` 236 ms、采样 188 ms、主查询 851 ms |

### 4.2 不能直接确认、但决定“实时”含义的差异

| 关键字段/证据 | 当前 trace | 预聚合样本基线 | 结论 |
| --- | --- | --- | --- |
| `dataQuerySource` | 未在当前 trace 日志中打印 | 历史样本为 `0` | 当前不能写成 `0`，只能说 URI/节点形态偏向同一路径 |
| `dbObjName` | 未取到 | `agg_data` / `dim_data` | 当前不能确认最终物理表 |
| 实际 ClickHouse SQL | `eye_trace_dist` 无 span；app log 无 SQL | 历史样本有 SQL/p6spy 观测 | 当前无法判定是否 `finalizeAggregation()` 或明细扫描 |
| 明细接口 | 当前不是 `/stat/detail/data/query` | 预聚合样本也不是 | “实时查询”不能据此定义为明细查询 |
| `mt_data/object_data` | 未观察到 | 预聚合对照文档将其列为明细路径 | 没有正向证据，不应声称已走明细 |

因此，当前最关键的不同点不是“接口已经切换到另一条实时明细链路”，而是**请求耗时和节点构成不同，但入口协议及 EasyStat 统计图框架一致**。只有补到 `dataQuerySource/dbObjName` 或实际 SQL，才能把差异提升为“预聚合 vs 明细”的确定结论。

## 5. 故障与证据边界

- CEP、Tomcat 均为 200，当前 trace 的 `log_error_dist`、CEP 慢错、Tomcat 慢表、SQL 慢表、Mongo 慢表均为空；这只能说明本次采集没有对应错误/慢表记录，不能证明所有内部路径都正常。
- `eye_trace_dist` 按当前 traceId 和 rpcId 在 `17:52:30–17:54:30` 均为 0 行；这表示没有可用的下游 span 证据，不表示没有下游调用。
- `rpc_dist` / `service_dist` 是聚合表，无法按本次 trace 精确关联；窗口内 `fs-bi-stat` 的背景流量不属于当前请求证据，不能拿来推断当前请求访问了哪些库。
- `DIA-incident-facts.json` 因 observations 的 `evidence_refs` schema 校验失败未生成完整事实投影；本报告基于原始 evidence、manifest 和目标 trace 的应用日志，不能声称完整 RCA 已收敛。

## 6. 最终判断与后续取证建议

1. 当前请求没有表现出错误或超时失败；端到端约 1.21 s，其中 EasyStat 内部可见部分 597 ms，主查询 280 ms。
2. 当前请求不是明细接口，而是统计图 `/stat/data/query`；它与历史预聚合样本共享 EasyStat、预 SQL 采样、分页查询和结果缓存结构。
3. “实时”目前只能解释为实时触发/刷新，不能解释为实时明细数据源。底层更偏向预聚合路径，但尚缺 `dataQuerySource/dbObjName/实际 SQL` 的直接证据。
4. 若要完成确定性对比，应在同一 trace 的入口日志补采 `StatBaseController` 的 `dataQuery arg`，并补 `p6spy/ClickHouseSQLExecutor` SQL；若仍无日志，再按结果缓存 key 反查查询上下文或对同 view 复现一次并保留入口参数。

## 7. 当前 trace 证据索引

- [CEP 入口](/Users/liushanshan/code/QA/bug-finder/output/evidence/20260821-stat-chart-realtime-FSW-fktest7572/evidence/TRC-tracing-log-cep.json)
- [应用 StopWatch 与节点账](/Users/liushanshan/code/QA/bug-finder/output/evidence/20260821-stat-chart-realtime-FSW-fktest7572/evidence/TRC-app-log-analysis.json)
- [精确 HTTP / eye_trace / app_log 探针摘要](/Users/liushanshan/code/QA/bug-finder/output/evidence/20260821-stat-chart-realtime-FSW-fktest7572/evidence/TRC-precision-probes.json)
- [采集清单](/Users/liushanshan/code/QA/bug-finder/output/evidence/20260821-stat-chart-realtime-FSW-fktest7572/CTX-collect-manifest.json)
