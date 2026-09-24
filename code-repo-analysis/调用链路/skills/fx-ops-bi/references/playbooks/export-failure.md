# export-failure：报表导出失败排查

```yaml
symptom: 报表导出无反应 / 导出报错 / 导出超时 / 同环比统计图导出异常
inputs:
 required: [tenant_id, occurred_time]
 optional: [report_id, traceId, export_type, error_message]
outputs:
 signals: [export_error_type, query_duration_ms, data_rows, ch_memory_usage, oom_flag]
 next_skills: [fx-ops-query, fx-ops-tracing, fx-ops-monitoring]
escalate_when:
 - CH OOM 导致导出失败（已知 suspended 问题）→ 回抛 fx-ops 评估是否需要临时切 PG
 - 批量客户同时导出失败 → 回抛 fx-ops 升级为 S2
 - 已过 PaaS 功能权限 2 小时窗口，导出按钮仍没有 → 才转权限同步/研发
```

FAQ 标题「看不到图表或没有导出」正文往往只覆盖导出功能权限，不要拿来否查看权限。结论只能写 `排查结论：设计如此` 或 `排查结论：需要研发处理`。

## Step 0：产品口径门禁（先于导出 SQL / OOM）

### 0.1 没有导出按钮 ≠ 导出失败

- 后台给角色勾了导出等功能权限 → **最长 2 小时**（PaaS API，BI 控不了）
- 预览页导出按钮「等几分钟」是经验值，上界仍是 2 小时，不构成硬冲突
- 窗口内没有导出按钮：`设计如此`，不要当导出服务挂了
- 报表/交叉表还要主对象功能权限；主题分析权限不够时是看不到图，不是导出失败 → 转 `permission-issue.md`

### 0.2 导出文件为空

先按 `permission-issue.md` Step 0 分清：没图、没数、还是权限过滤把行滤光。下游没主题对象权限经常导出空文件且无 toast。

### 0.3 导出求和 vs 报表求和

分组/合并单元格会导致 Excel 重复加和，不是导出算错。有「合并导出不重复计算」灰度。不要当 CH 聚合 bug。

过完 Step 0 仍是点了导出无文件/报错/超时，再进下面步骤。

## 排查步骤

### Step 1：区分错误类型

| 错误表现 | 类型 | 排查方向 |
| --- | --- | --- |
| 点击导出后无反应 | 异步任务未启动或超时 | 检查导出服务状态和异步队列 |
| 提示"导出失败" | SQL 超时或服务异常 | 检查 traceId 追踪链路 |
| 导出文件为空 | 查询返回 0 条但有数据 | 检查查询条件、权限过滤 |
| CH OOM 导致导出崩溃 | 内存不足 | 检查 CH 内存使用、数据量 |

### Step 2：追踪导出请求

如果有 traceId，回抛主控派发 `fx-ops-tracing`（`target_capability=fx-ops-tracing`）追踪导出链路，不自行调用：
1. 导出 API → 查询构建 → CH SQL 执行 → 数据序列化 → 文件生成 → 下载
2. 定位哪个环节失败

如果没有 traceId：

```sql
-- 查 CH 慢查询中是否有导出相关的查询（hwcloud 实测：去掉 clusterAllReplicas 直接 system.query_log；
-- 该查询无租户列，扫全集群行；--tenant-id 只做连接级路由）
SELECT query_duration_ms, query, read_rows, memory_usage
FROM system.query_log
WHERE query_start_time >= now() - INTERVAL 1 HOUR
 AND type = 'QueryFinish'
 AND (query LIKE '%EXPORT%' OR query_duration_ms > 60000)
ORDER BY query_duration_ms DESC
LIMIT 10
```

### Step 3：分类根因

| 根因类型 | 特征 | 处置 |
| --- | --- | --- |
| SQL 执行超时 | 导出查询耗时超过阈值（通常 60s） | 优化查询、缩小数据范围 |
| CH OOM | CH 内存使用超限导致查询被 kill | 临时切 PG 或减小导出范围 |
| 同环比统计图导出异常 | 仅同环比类型的统计图导出失败 | 已知代码缺陷，回抛主控（target_capability=code-search）跟进 |
| 导出服务不可用 | 异步导出队列积压或服务重启 | 检查导出服务状态 |
| 数据量过大 | 行数超过导出限制 | 建议分批导出或缩小筛选范围 |

## 常见模式

### 模式 A：CH 拼表 OOM（已知 suspended 问题）

已知 TAPD Bug #1374282 和 #1385401（suspended，待季度复审）：大数据量拼表导出时 CH OOM。

1. 确认是否为拼表导出场景
2. 检查 CH 内存使用是否接近上限
3. 临时解决方案：切 PG 引擎导出
4. 长期方案：优化 CH 内存配置或增加节点

### 模式 B：批量客户同时导出失败

2022-11-11 曾出现 4 条同根因导出 bug（均指向 Bug 1296191）：

1. 检查是否为全局性导出服务故障
2. 检查 DB 连接池是否耗尽
3. 检查导出服务是否需要扩容

## 输出要求

结论中必须包含：
- Step 0 产品口径判定（无导出按钮是否仍在 PaaS 2 小时窗口 / 空文件是否其实没权限）
- 导出失败的类型（无按钮等缓存 / SQL 超时 / OOM / 服务异常 / 功能缺陷）
- traceId 和失败环节（仅实际点了导出之后）
- 数据量评估（导出行数、CH 内存使用）
- 建议动作（等待权限生效 / 切 PG / 缩小范围 / 等待修复）
- 收口：产品口径类结论（如未过 PaaS 权限窗口）用 `排查结论：设计如此` 或 `排查结论：需要研发处理` 二选一；过完 Step 0 后定位为纯基础设施根因（CH OOM 切 PG、导出服务扩容）时，按运维性能类用 `排查结论：需要基础设施或运维处理` 或 `排查结论：已定位，建议动作如下`
