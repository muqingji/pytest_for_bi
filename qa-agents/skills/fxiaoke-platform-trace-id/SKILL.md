---
name: fxiaoke-platform-trace-id
description: "112/纷享销客 HTTP 请求必须使用页面同款平台 TraceId（查询参数 FSW-企业账号.员工ID-xxxx）。修改 HttpClient、CaseRunner、N08 lifecycle 或 N11 回显时必须遵循；禁止自造 QA-uuid 冒充 Trace。"
---

# 纷享销客平台 TraceId

适用范围：`src/framework/clients/http.py`（唯一发出方）、
`src/framework/core/runner.py`（写入 lifecycle）、
`qa-agents/src/qa_agents/quality_results.py`（N11 回显）。

本 Skill 只定义契约。真正发请求、记证据的是受控执行器，Agent 不得在 Case JSON
里手写 `traceId`，也不得事后编一个 UUID 填进任务详情。

## 页面真实形态

浏览器请求同时带两种 ID，任务详情展示的是查询参数，不是自造请求头：

```text
?traceId=FSW-91863.1002-0mtl76wigmqpatp66agb
x-trace-id: 91863_1002_1788415780388:4044
```

- `traceId`：`FSW-{企业账号}.{员工ID}-{20 位小写字母数字}`
- `x-trace-id`：`{企业账号}_{员工ID}_{毫秒时间戳}:{序号}`

## 强制规则

1. 所有 `ceshi112.com` / `fxiaoke.com` / `/FHH/` 请求由 `HttpClient.request` 自动注入上述两个字段。
2. 企业账号来自登录身份；员工 ID 从登录或后续响应 `UserInfo.EmployeeID` 回填。未知员工时先用 `0`，一旦拿到真实 ID 立即切换。
3. lifecycle 的 `trace_id` 必须记录查询参数 `traceId`（`FSW-...`）。N11 只回显这个值。
4. 禁止 `QA-{uuid}`、随机 UUID、或把 `x-trace-id` 当成任务详情主 Trace。
5. 没有实际发出请求时写 `未记录`，禁止编造。
6. Case 生成器（A14/A15）不要把 `traceId` 写进步骤；执行期由客户端注入。

## 验收

- 112 实跑 lifecycle 里 test 步骤的 `trace_id` 形如 `FSW-91863.1002-...`
- N11 任务详情能按这个值去平台查日志
- `tests/test_http_client.py` 覆盖 FSW 注入与禁止 `QA-` 前缀
