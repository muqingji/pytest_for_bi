# BUG-002 修复记录：CR 待确认项按确认方案落地

## 缺陷归属

归属：业务代码、接口与配置、契约文档、数据与迁移。

依据：CR-003 定位到 `Makefile` 与 `internal/transport/http/server.go` 的功能开关装配和错误映射；CR-006 定位到 `internal/adapter/storage/sqlite.go:GetDailyUsage` 与投递状态契约；CR-007 定位到 `internal/application/evaluate/service.go`、`internal/application/snooze/service.go` 的排程事件；CR-010 定位到 `internal/adapter/storage/migrations/003_nullable_event_decision.up.sql` 的历史兼容职责。四项产品/技术取舍已由用户确认，随后进入业务代码修复流程。

## 复现

```bash
go test -count=1 ./internal/transport/http ./internal/adapter/storage ./internal/application/evaluate ./internal/application/snooze ./cmd/reminder-service
```

实际：修复前 HTTP 测试无法编译（缺少 `dispatch.ErrFeatureDisabled`）；`DELIVERED` 行被计入用量；免打扰回退事件仍写 `INITIAL_PLAN`；Snooze 只产生 `reminder_snoozed`，重放也不补 `reminder_scheduled`；事件链集成测试只有 3 条事件而预期 4 条。

期望：开关关闭返回不可重试的 503；P0 用量只统计 `SENT`；初始、免打扰回退、Snooze 分别写正确排程原因；Snooze 重放补缺且不重复落事件行；迁移 003 的历史兼容场景有测试保护。

## 根因

本地入口没有显式开启服务级灰度开关，HTTP 又把配置态错误当成普通依赖故障；用量 SQL 和文档保留了本期没有生产者的 `DELIVERED`；评估事件原因被写死且 Snooze 未发布排程事件；迁移 003 缺少说明和历史 schema 回归用例，无法解释重复重建的必要性。

## 改动清单

- `Makefile`、HTTP/application：本地服务入口显式开启开关；增加共享的关闭态错误并映射为 `503 FEATURE_DISABLED`、`retryable=false`。
- domain/evaluate/snooze：增加三类 `RescheduleReason`；初始与免打扰回退写对应原因，Snooze 发布 `reminder_snoozed` 与 `reminder_scheduled(SNOOZE)`，重放按确定性 `event_id` 补写。
- storage/migration：当日用量只统计 `SENT`；迁移 003 增加不可合并的历史兼容说明和 version 2 旧约束升级测试。
- OpenAPI、技术方案、测试方案和实现记录：同步开关、投递状态、事件与迁移口径。
- 测试：增加 HTTP、用量、排程原因、Snooze 事件/幂等、迁移兼容和跨模块事件链断言。
- 没有改：PRD、验收标准、数据库表结构、真实 Push/事件总线接入、固定测试时钟和生产配置。

## 回归用例

- `internal/transport/http/server_test.go:TestHandlerMapsFeatureDisabledSeparately`
- `internal/adapter/storage/sqlite_dispatch_test.go:TestStoreDailyUsageDoesNotCountUnimplementedDeliveredStatus`
- `internal/application/evaluate/service_test.go:TestServiceMarksScheduleDeferredFromQuietHours`
- `internal/application/snooze/service_test.go:TestSnoozeCreatesScheduleAndEvent`
- `internal/application/snooze/service_test.go:TestSnoozeReusesExistingScheduleForRepeatedRequest`
- `internal/adapter/storage/sqlite_test.go:TestStoreMigrationThreeRepairsVersionTwoLegacyEventSchema`
- `cmd/reminder-service/event_chain_integration_test.go:TestEventChainIntegrationLinksSnoozeEvents`
- 修复前：红（编译错误及上述语义断言失败）。修复后：绿。

## 验证范围

| 层级 | 命令 | 结果 |
| --- | --- | --- |
| 格式/静态/构建 | `make fmt`、`make vet`、`make build` | 全部通过 |
| 全量单元测试 | `make test` | 11 个含测试的 Go 包通过，失败 0 |
| 受影响包 | `go test -count=1 ./internal/domain/reminder ./internal/application/evaluate ./internal/application/snooze ./internal/application/dispatch ./internal/adapter/storage ./internal/transport/http ./cmd/reminder-service` | 7 个包通过，失败 0 |
| 全量竞态 | `go test -race -count=1 ./...` | 11 个含测试的 Go 包通过，无 data race |
| 模块集成 | `go test -count=1 -run Integration -v ./...` | 18 通过、0 失败、0 跳过、0 未执行 |
| 集成竞态 | `go test -race -count=1 -run Integration ./cmd/reminder-service ./internal/adapter/storage ./internal/adapter/channel` | 通过，无 data race |
| 迁移专项 | `go test -count=1 -run 'TestStore(MigratesAndKeepsDecisionIdempotent|UpgradesVersionOneEventTable|MigrationThreeRepairsVersionTwoLegacyEventSchema|MigrationBeginAndCommitFailures|MigrationSchemaAndTriggerFailures|MigrateAndQueriesRespectCanceledContext)' -v ./internal/adapter/storage` | 6 通过，覆盖空库/重复、v1、version 2 兼容、失败回滚与 context 取消 |
| OpenAPI | `make lint-idl` | 通过，0 error |
| 业务接口 | `SERVE_ADDR=127.0.0.1:18123 make test-api-fresh` | 20 通过、0 失败、20 跳过；跳过不计通过 |
| 用例管线自检 | `make test-selftest` | 17 通过、0 失败、0 跳过 |
| 文档回查 | `check_tech_design.py`、`check_acceptance_criteria.py` | 均为阻塞 0、建议 0 |
| Skill 校验 | `quick_validate.py dev-tools/skills/{bug-fix,code-review}`（PyYAML 临时安装于 `mktemp` 目录） | 两个 Skill 均为 `Skill is valid!` |
| 覆盖率 | `go test -covermode=atomic -coverprofile=/tmp/bug-002.cover ./...` | 修前 100.0% -> 修后 100.0% |

## CR

| finding | 级别 | 处置 |
| --- | --- | --- |
| CR-003 本地入口与功能开关语义不一致 | P1 | 已修复并复验 |
| CR-006 本期投递状态与用量口径不一致 | P2 | 已修复并复验 |
| CR-007 `reminder_scheduled` 契约与实现不一致 | P2 | 已修复并复验 |
| CR-010 迁移 003 的历史职责不清 | P3 | 已修复并复验 |

本轮修复 diff 按 `code-review` Skill 复审，新增 finding 0；原 CR-001 至 CR-011 全部为已修复。

## 未验证

- 业务接口仍有 20 条既有 pending，依赖固定测试时钟、独立测试库或可控渠道失败状态，本轮未执行，不能计为通过。
- 未执行真实 Push 厂商、事件总线、用户/任务服务、生产数据库、线上调度、性能和容量验证。
- 未实现真实 `DELIVERED` 回执与 reconcile；它们已明确移至后续真实渠道能力，不属于本期 P0。

## 剩余风险

本地事件仍通过数据库唯一键和请求重放补缺，没有 outbox/reconcile；进程提交排程后若调用方永不重试，事件缺口仍需后续生产补偿能力处理。已检查 evaluate 与 snooze 两条本期排程生产路径，均使用确定性事件 ID；dispatch 发送重试不会新增 `reminder_scheduled`。

## 回滚

回退本记录“改动清单”所列代码、测试和文档即可。迁移 003 仅增加注释、没有新增迁移版本或修改表结构，不需要数据回滚；回滚 Makefile 后本地入口需手动传 `-feature-enabled`，否则会恢复 CR-003。
