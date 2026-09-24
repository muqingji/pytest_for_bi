# slow-query：报表/驾驶舱加载慢排查

```yaml
symptom: 报表加载慢 / 驾驶舱白屏 / CH 查询超时 / SQL 慢
inputs:
 required: [tenant_id, occurred_time]
 optional: [report_id, dashboard_id, traceId, query_sql]
outputs:
 signals: [slow_query_sql, query_duration_ms, rows_read, memory_usage, bottleneck_type]
 next_skills: [fx-ops-query, fx-ops-monitoring, fx-ops-tracing]
escalate_when:
 - CH 集群级别性能问题（多租户同时慢）→ 回抛主控（target_capability=fx-ops-monitoring）查集群指标
 - 慢查询因缺索引/表结构问题导致 → 回抛主控（target_capability=code-search）确认是否可优化
```

**与 render-failure 的消歧**：白屏/组件渲染异常/前端报错 → render-failure；转圈后超时/查询耗时/加载慢 → 本模块。

## 排查步骤

> SQL 执行入口：CH 系统表查询走 `query bi-clickhouse`（`bi` biz 双方言，禁止无后缀 `query bi`）。

### Step 1：定位慢查询

如果有 traceId，回抛主控派发 `fx-ops-tracing`（`target_capability=fx-ops-tracing`）追踪报表请求链路，拿到实际执行的 CH SQL。

如果没有 traceId，直接查 CH 慢查询日志：

```sql
-- 查 CH 慢查询（最近 1 小时，按耗时降序）
SELECT
  query_duration_ms,
  query,
  read_rows,
  result_rows,
  memory_usage,
  query_start_time
FROM clusterAllReplicas('default', system, query_log)
WHERE query_start_time >= now() - INTERVAL 1 HOUR
 AND type = 'QueryFinish'
 AND query NOT LIKE '%system.%'  -- 排除 system.xxx 形式的系统表查询，避免误杀含 system 字样的业务 SQL
 AND query NOT LIKE '%system,%'  -- 排除 clusterAllReplicas('default', system, ...) 形式的系统查询（含本次诊断 SQL 自身）
 AND query NOT LIKE 'SYSTEM %'
ORDER BY query_duration_ms DESC
LIMIT 20
```

### Step 2：分析慢查询特征

从慢查询 SQL 中提取关键信息：

| 指标 | 关注点 |
| --- | --- |
| `query_duration_ms` | 是否超过正常基线（通常报表查询 < 10s） |
| `read_rows` vs `result_rows` | 高比值说明过滤不够或缺少分区裁剪 |
| `memory_usage` | 内存峰值是否接近 CH 内存限制 |
| `query` 内容 | 是否有全表扫描、大 JOIN、子查询嵌套 |

### Step 3：分类处置

| 瓶颈类型 | 特征 | 处置 |
| --- | --- | --- |
| 缺少分区/索引 | read_rows 远大于 result_rows，扫描了大量无用数据 | 建议添加分区键或优化 WHERE 条件 |
| 大表 JOIN | 多表关联，内存使用高 | 检查 JOIN 键是否有索引、是否可以先过滤再 JOIN |
| 聚合计算重 | GROUP BY 后数据量大 | 检查是否可以用物化视图预聚合 |
| 并发查询争抢 | 同一时间段大量查询，CH CPU/IO 飙高 | 回抛主控（target_capability=fx-ops-monitoring）查 CH 集群负载 |
| CH 集群资源不足 | 单查询不慢但并发时变慢 | 检查 CH 集群扩容需求 |

### Step 4：确认前端耗时（如需要）

如果 SQL 执行不慢但页面仍然加载慢：

- 回抛主控派发 `fx-ops-tracing` 追踪完整请求链路（API → CH → 序列化 → 传输 → 前端渲染）
- 检查返回数据量是否过大（几千行数据序列化和传输也需要时间）
- 检查前端是否有重复请求或瀑布式加载

## 线上高频模式（来自 Bug 归纳）

### 模式 A：CH DDL 并发超时

新建字段时提示"新建字段超时，请尽量避免在业务高峰期新建字段"。根因：CH DDL 操作（ALTER TABLE ADD COLUMN）在大数据量表上耗时长，且多个 DDL 并发时互相阻塞。

排查：检查 CH 中是否有正在执行的 DDL 操作（`system.mutations` 表），检查 DDL 执行耗时。避免在业务高峰期执行 DDL。

### 模式 B：双维度查询性能差

双维度统计图打开报错或超时。根因：双维度 GROUP BY 导致计算量指数级增长，CH 需要扫描和聚合大量数据。

排查：检查慢查询 SQL 的 GROUP BY 列数，评估是否可以通过预聚合或物化视图优化。

### 模式 C：CH 日志不全导致无法排查

多条 bug 标注"clickhouse日志不全"，查询 `system.query_log` 找不到对应的查询记录。根因：CH 查询日志可能因为配置限制未记录所有查询，或查询在到达 CH 之前就被上层服务拦截。

排查：如果 CH 日志中无对应记录，检查上层服务（如查询层重构）的日志，确认请求是否到达 CH。

### 模式 D：统计图拓扑表缺失

统计图一直提示"数据量过大，稍后查询"或"初始化中"。根因：`bi_mt_topology_table` 中没有该图的元数据，导致查询无法正确构建。

排查：检查 `bi_mt_topology_table` 中是否有该统计图的记录。

## 实战排查路径

### 路径 1：CH 日志不全时的排查方法

线上频繁出现 `system.query_log` 中找不到对应查询记录的情况。此时不能依赖 CH 日志，需要从 pod 级日志入手：

**Step 1：查 CH system.query_log**

```sql
SELECT query_duration_ms, query, read_rows, memory_usage, query_start_time
FROM clusterAllReplicas('default', system, query_log)
WHERE query_start_time >= now() - INTERVAL 1 HOUR
 AND type = 'QueryFinish'
 AND query NOT LIKE '%system.%'  -- 排除 system.xxx 形式的系统表查询，避免误杀含 system 字样的业务 SQL
 AND query NOT LIKE '%system,%'  -- 排除 clusterAllReplicas('default', system, ...) 形式的系统查询（含本次诊断 SQL 自身）
 AND query NOT LIKE 'SYSTEM %'
ORDER BY query_duration_ms DESC
LIMIT 20
```

**Step 2：如果 CH 日志中无记录，查上层服务日志**

```
服务：fs-paas-metadata-rest 或 BI 查询网关
日志关键词：query、timeout、clickhouse、error
```

可能原因：
- 请求未到达 CH（被上层服务拦截或路由错误）
- 查询在到达 CH 之前就超时了（如连接池耗尽）
- CH query_log 配置限制了记录数量

**Step 3：查 pod 级日志**

入口：`fs-k8s-cli`（fx-ops-k8s-app，只读日志操作无需确认）。先确认 CH 中间件 pod 是否在 fs-k8s-app-manager 管理范围内；不在范围内则回抛主控处理。

```bash
# 查 CH pod 的标准输出日志（fs-k8s-cli 只读日志命令；错误关键字过滤在结果内检索，不用 shell 管道）
fs-k8s-cli --profile <profile> app pod logs --cluster <cluster> -n <namespace> --pod <ch-pod> --tail-lines 1000
# --profile 每次显式传：firstshare=测试/112，foneshare=生产/线上；主控派发时用 anchor_context.env
# 落盘后在 evidence_dir 内检索 error / timeout / oom 关键字
```

### 路径 2：CH DDL 阻塞的完整追查

新建字段超时是线上高频问题。已知根因："CH部分表结构影响历史字段rename操作，导致数据库夯住了"。

**Step 1：确认 DDL 阻塞**

```sql
-- 查正在执行的 mutations（ALTER TABLE 操作）
SELECT database, table, mutation_id, command, is_done, parts_to_do
FROM clusterAllReplicas('default', system, mutations)
WHERE is_done = 0
ORDER BY create_time DESC
```

**Step 2：确认阻塞的根因**

常见原因：
- 历史字段 rename 操作阻塞：旧字段的 rename 和新字段的 add 互相等待
- 大数据量表上的 DDL 耗时过长：ALTER TABLE ADD COLUMN 需要重建 part
- 多个 DDL 并发执行：互相持有锁

**Step 3：修复方案**

- 短期：将历史槽位从 rename 操作调整为 drop 操作，避免 rename 阻塞
- 中期：避免在业务高峰期执行 CH DDL
- 长期：优化 DDL 执行策略（如分批执行、低峰期自动调度）

### 路径 3：统计图"数据量过大，稍后查询"

统计图一直提示"数据量过大，稍后查询"或"初始化中"：

**Step 1：查 topology 表**

执行入口：`fx-ops idp --profile <p> query bi-system --tenant-id <EI> --sql "<SQL>"`（`bi_mt_topology_table` 租户列为 `tenant_id`；实测 `bi-system` 必填 `--tenant-id`）。

```sql
SELECT *
FROM bi_mt_topology_table
WHERE tenant_id = '<EI>'
 AND stat_id = '<stat_field_id>'
```

**Step 2：如果无记录，需要重新生成 topology**

当 `udf_obj_field` 的槽位变化后，topology 不会自动重建。需要发消息触发 topology 重新生成。

**Step 3：确认 topology 生成是否完成**

重新生成后，检查 `bi_mt_topology_table` 中是否已写入记录，以及记录中的 slot 映射是否与当前 `udf_obj_field` 一致。

## 输出要求

本模块收口属**运维性能类**。与 render-failure 的消歧：白屏/组件渲染异常/前端报错 → render-failure；转圈后超时/查询耗时/加载慢 → 本模块。

结论中必须包含：
- 慢查询 SQL（脱敏后）
- 耗时、扫描行数、返回行数、内存使用
- 瓶颈类型判断
- 优化建议（索引/分区/SQL 改写/预聚合/扩容）
- 收口行三选一：`排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下`
