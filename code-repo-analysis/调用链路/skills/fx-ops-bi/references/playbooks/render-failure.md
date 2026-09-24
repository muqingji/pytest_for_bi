# render-failure：报表/驾驶舱渲染失败排查

```yaml
symptom: 报表白屏 / 驾驶舱白屏 / 图表样式错乱 / 组件加载失败
inputs:
 required: [tenant_id, occurred_time]
 optional: [report_id, dashboard_id, traceId, browser_console_errors]
outputs:
 signals: [error_type, api_status, api_response_time, js_error_message]
 next_skills: [fx-ops-tracing, fx-ops-monitoring, fx-ops-query]
escalate_when:
 - API 返回 500/超时 → 回抛主控（need_further + route_hint，target_capability=fx-ops-tracing）追踪后端链路
 - CH 查询超时导致渲染失败 → 回抛主控转 slow-query 模块
```

**与 slow-query 的消歧**：白屏/组件渲染异常/前端报错 → 本模块；转圈后超时/查询耗时/加载慢 → slow-query。Step 1 判定为后端超时后不自行跨界，回抛主控转 slow-query。

## 排查步骤

### Step 1：区分前后端问题

| 现象 | 前端 or 后端 |
| --- | --- |
| 页面白屏，F12 Console 有 JS 报错 | 前端 |
| 页面加载中一直转圈 | 后端 API 超时 |
| 图表区域空白但页面框架正常 | API 返回空数据或错误 |
| 页面显示错误提示（如"查询超时"） | 后端 |

### Step 2：后端问题排查

1. 如果有 traceId，回抛主控派发 `fx-ops-tracing`（`target_capability=fx-ops-tracing`）追踪 API 请求链路，不自行调用
2. 如果没有 traceId：
- 查 API 错误日志（入口见 `_common.md`「查询入口总表」）
- 检查报表 API 的响应状态码和耗时
3. 如果后端报 CH 查询超时，不自行跨界排查，回抛主控转 slow-query 模块

### Step 3：前端问题排查

1. 收集浏览器 Console 错误信息
2. 检查返回数据格式是否符合前端预期
3. 检查数据量是否超过前端渲染能力（如数万行数据导致 DOM 爆炸）
4. 检查前端组件版本是否有已知 bug

### Step 4：数据为空场景

如果渲染正常但数据为空（页面框架在、图在、只是没数 / `--`）：
1. 这不是白屏。下游统计图没主题对象权限经常无 toast、只是没数 → 转 `permission-issue.md` Step 0，不要当渲染失败
2. 先按 sync-delay.md 确认数据是否同步到位
3. 检查报表过滤条件是否过于严格
4. 检查数据权限是否限制了可见范围（先过权限产品口径，再查 dt_auth）

## 线上高频模式（来自 Bug 归纳）

### 模式 A：手机端/企微 H5 全局筛选参数缺失

手机端/企微 H5 打开驾驶舱报表报错"缺少全局筛选的人员范围"，PC/Web 端正常。根因：移动端在加载报表时未正确传递全局筛选参数（人员范围、数据范围）。

排查：确认终端类型（手机/企微 H5/PC/Web），如果是移动端特有，检查全局筛选参数传递逻辑。用户临时解决方案：手动变更数据范围后重新加载。

### 模式 B：PC 客户端特有卡顿

PC 客户端驾驶舱加载很慢或卡死，但谷歌浏览器正常。根因：PC 客户端内嵌浏览器的性能差异或缓存问题。

排查：对比 PC 客户端和谷歌浏览器的加载表现，检查 PC 客户端的内嵌浏览器版本和缓存状态。

### 模式 C：Edge vs Chrome 兼容性

Edge 浏览器始终显示加载中，Chrome 正常。根因：Edge 浏览器对某些前端组件的渲染兼容性问题。

排查：建议用户使用 Chrome 浏览器，或检查 Edge 的兼容性视图设置。

### 模式 D：驾驶舱预设数据为空

新开通账套的预设驾驶舱无数据。根因：预设数据未通过刷库写入，或指标分析模块未开通。

排查：检查预设数据是否已刷库、模块开通状态。

## 输出要求

本模块收口属**运维性能类**。若 Step 1 判定为后端超时/慢查询，不自行跨界排查，回抛主控转 slow-query。

结论中必须包含：
- 问题分类（前端/后端/数据）
- 错误信息（API 状态码 / JS 错误 / 查询错误）
- 根因和证据
- 建议修复动作
- 收口行三选一：`排查结论：需要研发处理` / `排查结论：需要基础设施或运维处理` / `排查结论：已定位，建议动作如下`
