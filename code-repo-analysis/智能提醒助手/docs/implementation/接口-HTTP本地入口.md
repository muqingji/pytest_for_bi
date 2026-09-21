# 接口-HTTP 本地入口：功能进度与完成证据

> 本记录对应技术方案 3.4 已登记的 `transport/http`（本地 HTTP/JSON 触发入口），不是单个 FR：它让 FR-001～FR-008 的三个接口可以在本地用真实 HTTP 请求（pytest）验证。范围与验收仍由各 FR 的记录承接。

## 功能信息

| 字段 | 值 |
| --- | --- |
| 功能名称 | 本地 HTTP 入口（三个内部接口的 transport 层） |
| FR | 横切（`transport/http` 不是 FR 的实现落点，是 FR-001/005/007 三个接口的本地入口） |
| AC | 承接 SC-022（AppOpened 同步入口）、SC-025/SC-026（参数与枚举校验）、SC-027（鉴权）；业务结论仍按对应 FR 的 AC 验收 |
| 优先级 | P0（本地可测试性前置） |
| 状态 | 完成（代码与文档已落地；联调见「未解决事项」的 EVAL-011 时点问题） |
| 范围边界 | 只做本地 `127.0.0.1` 的 HTTP 入口：路由、报文解析与字段校验、静态令牌鉴权、接口级超时、统一错误信封、`X-Request-ID` 回写；不做入口限流、不做固定测试时钟、不发真实 Push、不注册生产服务 |

## 模块范围

来源：技术方案 `### 3.4 模块划分`。本轮涉及的每个模块登记一行。

| 模块 | 职责 | 入口 | 主要落点 | 异常边界 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `transport/http`（3.4 第 111 行） | 本地 HTTP/JSON 触发入口，承载 `AppOpened` 同步通道 | `cmd/reminder-service -serve`、模块集成测试 | `internal/transport/http/{server.go,handler.go,dto/dto.go}` | 报文非法 → `400 INVALID_REQUEST`；未带/错令牌 → `401`；未知路由 → `404`；用例超时 → `504 DEPENDENCY_TIMEOUT`；其余依赖失败 → `500 DEPENDENCY_UNAVAILABLE` | 已测异常边界 |
| `adapter/task`（3.4 第 105 行） | Fixture 任务快照 | 入口装配 | `internal/adapter/task/fixture.go` | 未登记用户返回无必做任务（NO_TASK 由领域判定）；截止时间写法非法返回零值 | 已测异常边界 |
| `adapter/user`（3.4 第 106 行） | Fixture 设置/行为 + 当日用量基线叠加 | 入口装配 | `internal/adapter/user/usage_overlay.go` | 仓储读取失败向上返回，不返回部分结果 | 已测异常边界 |
| `cmd/reminder-service`（3.4 第 114 行的单进程装配） | 种子加载、装配与进程入口 | `-serve` | `cmd/reminder-service/{serve.go,fixtures.go,main.go}` | 非回环地址、种子文件缺失/非法、引用不存在的任务模板、迁移失败都在服务启动前失败关闭 | 已测异常边界 |

- 是否新增了 `3.4` 未列出的模块或代码位置：否。全部落在已登记的 `transport/http`、`adapter/task`、`adapter/user` 与 `cmd/reminder-service` 装配内。
- 模块依赖顺序与本轮实现顺序：`dto` -> `transport/http`（handler/server）-> `cmd/reminder-service` 装配（`fixtures.go`、`serve.go`）-> 模块集成测试。

## 契约追踪

| 层级 | 证据 |
| --- | --- |
| PRD 预期行为 | PRD 7.x 的三个接口行为与 10.4 原因码；业务结论由应用层用例给出，入口只做契约映射 |
| 验收场景 | SC-022、SC-025、SC-026、SC-027；业务结论用例见 `tests/cases/*.json` |
| 技术方案章节 | 4.3.1（协议/鉴权/超时/错误语义与限流）、4.3.2.1～4.3.2.3（三个接口全字段与状态码）、4.3.4（错误码）、4.7（入口配置）、9.3（2026-09-21 本地 HTTP 入口实现） |
| 代码模块 | `internal/transport/http/server.go`、`handler.go`、`dto/dto.go`、`internal/adapter/task/fixture.go`、`internal/adapter/user/usage_overlay.go`、`cmd/reminder-service/{serve.go,fixtures.go,main.go}` |
| 持久化/迁移 | 不新增表、不改迁移；本地入口默认使用进程内 SQLite（`-db` 未显式指定时），种子来自 `testenv/fixtures/users.json` |
| 单元测试 | `internal/transport/http/server_test.go`、`dto/dto_test.go`、`internal/adapter/task/fixture_test.go`、`internal/adapter/user/usage_overlay_test.go`、`cmd/reminder-service/{fixtures_test.go,serve_test.go}` |
| 单测覆盖的 AC 清单 | SC-022（`TestHandlerMapsAppOpenedLastOpenAt` 覆盖 `last_open_at` 两种合法写法）、SC-025/026（`TestHandlerRejectsInvalidEvaluateFields`、`TestHandlerValidatesDispatchBatchSize`、`TestHandlerValidatesSnoozeRequest`）、SC-027（`TestHandlerRejectsCredentialVariants`、`TestHandlerAcceptsDefaultTokenWhenUnconfigured`）、SC-024（`TestHandlerMapsDependencyFailures`） |
| 联调场景 | `cmd/reminder-service/http_integration_test.go`：真实 SQLite + 真实种子 + `assemble()` + 真实监听，验证评估→调度→延后闭环 |

## 未决项与开关

| 检查项 | 结果 |
| --- | --- |
| 技术方案第 9 章未决项是否阻塞本功能 | 不阻塞。原 9.3 的 D7-A「不实现 transport 层」已于 2026-09-21 被本切片取代并回写；限流与固定测试时钟登记为本地缺口 |
| 未决项确认结论是否已回写文档并重跑回查 | 是，回写位置：技术方案 4.3.1、4.3.2.1、4.7、9.3、9.4；回查脚本阻塞 0 / 建议 0 |
| FR 与 AC 编号存在性校验 | `check_tech_design.py` 与 `check_acceptance_criteria.py` 均阻塞 0、建议 0（见验证记录） |
| 功能开关默认值 | 程序的 `-feature-enabled` 默认保持关闭；`make serve` 与 `make test-api-fresh` 显式开启，并只绑定回环地址。直接运行二进制但不开启时，evaluate/dispatch 返回 `503 FEATURE_DISABLED`、`retryable=false` |
| 渠道独立开关 | 不适用：入口不直接调渠道，Push 由 `dispatch` 用例经 `PushSender` 端口调用，本地为 `MockPushSender` |
| 回退路径（停止智能排程、恢复既有策略、保留历史记录） | 未演练：关闭 `-serve` 即回到进程内调用，本地不改历史记录；生产回退需接入时核验 |

## 验证记录

| 检查项 | 命令/结果 |
| --- | --- |
| 基线/回归测试 | `go test -count=1 ./...`：11 个包全部 `ok`（含 `cmd/reminder-service`） |
| 单元测试 | `go test -count=1 ./internal/transport/http/... ./internal/adapter/task/ ./internal/adapter/user/ ./cmd/reminder-service/` 通过 |
| 单测覆盖率（本轮新增/修改代码） | `go test -covermode=atomic -coverprofile=/tmp/slice.cover ./internal/transport/http/... ./internal/adapter/task/ ./internal/adapter/user/`；`transport/http` 与 `dto` 100.0%、`adapter/task` 100.0%、`adapter/user` 100.0%；`cmd/reminder-service` 的 `fixtures.go`、`serve.go` 100.0%；未覆盖位置：无 |
| 模块集成测试 | `go test -count=1 -run Integration ./cmd/reminder-service/`：全部通过，0 失败、0 跳过；含新增 2 条 HTTP 入口用例 |
| 联调类型（真实或 Mock） | 本地 Mock 联调：真实 HTTP 请求 + 真实 SQLite + `MockPushSender`（不发真实 Push、不联外网） |
| 联调测试 | `make test-api-fresh` 显式传入 `-feature-enabled`，验证本地业务入口不会因默认灰度开关关闭而出现伪失败；最新结果见本轮时间戳集成测试报告 |
| PRD/AC 回查 | 通过：`check_acceptance_criteria.py` 阻塞 0、建议 0 |
| 技术方案回查 | 通过：`check_tech_design.py` 阻塞 0、建议 0 |
| 回查脚本 | 命令见上；阻塞项 0 / 建议项 0 |
| 未验证项 | 入口限流（`rate_limit_caller_qps`、`rate_limit_user_qps`）未实现，SC-028 本地不覆盖；固定测试时钟未实现，20 条依赖时钟的用例保持 `pending`；真实 Push 渠道、事件总线、生产存储未联调；未做性能与容量验证 |
| `git diff --check` 或格式化检查 | `gofmt -l cmd internal` 无输出；`git diff --check` 干净 |

## 决策与阻塞项

- 未解决事项：`tests/cases/evaluate_reminder.json` 的 EVAL-011（push 未授权 → 期望 `NO_AVAILABLE_CHANNEL`）在当前时刻失败，实际返回 `INSUFFICIENT_TIME`。已用同一用户的两次真实请求定位：`task_date=2026-09-20`（窗口已过）返回 `INSUFFICIENT_TIME`，`task_date=2026-09-22`（窗口未到）返回 `NO_AVAILABLE_CHANNEL`，即应用层的校验顺序把「时间不可用」排在「渠道不可用」之前，用例期望值只在行为窗口尚未过去时可复现。属应用层校验顺序与用例期望的口径问题，不在本切片范围内。
- 需要人工确认：①是否把 EVAL-011 的期望值改为 `INSUFFICIENT_TIME`（或在用例里用固定测试时钟锁定运行时刻）；②是否调整 `application/evaluate` 的校验顺序，让 Push 不可用先于时间不可用；③入口限流是否在本期本地补齐。
- 人工确认结果：待确认（本切片未改 PRD、AC、技术方案与用例期望值）。
- 已知限制：本地入口只在回环地址监听、使用静态令牌；进程内 SQLite 使每次启动回到 Fixture 基线，复用同一进程连续跑两次业务测试会命中幂等返回 `REUSED`。
