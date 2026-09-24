# fx-ops-tracing Playbook 索引

基于 traceId / CEP 错误码的单请求链路追踪场景索引。

## 场景路由

| 你的问题 | 进入 |
| --- | --- |
| 给我一个 traceId，告诉我哪里出错 | trace-end-to-end.md |
| 有 traceId 但不知道时间，帮我找到它 | traceid-time-unknown.md |
| 用户截图里的 CEP 错误码或报错截图，要完整排查 | cep-error-code.md |
| 有服务名和时间但无 traceId，需反查 | trace-end-to-end.md（反查模式：用 app + 时间窗口从 `eye_trace_dist` 或 `log_cep_dist` 查 traceId） |
| bizName → app 映射（四表全空时） | **fx-ops-knowledge** skill |

## 注意

- Pod CPU/内存异常 → 调用 `fx-ops` skill，由它进入 Pod 资源排查路径
- 应用级报错聚合排查（无特定 traceId） → 调用 `fx-ops` skill，由它从应用报错聚合入口开始
- 下游存储排查 → 调用 `fx-ops` skill，由它选择对应的 downstream 场景
