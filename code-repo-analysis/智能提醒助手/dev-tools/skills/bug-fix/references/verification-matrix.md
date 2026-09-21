# 验证范围对照表

按改动类型决定必跑项。没跑的项必须写进「未验证」并说明原因，不允许默认省略。

## 通用必跑

| 层级 | 命令 | 说明 |
| --- | --- | --- |
| 格式化 | `make fmt` | 改动后必须执行，避免空白噪音混进 diff |
| 静态检查 | `make vet` | |
| 全量单元测试 | `make test`（= `go test ./...`） | 不是只跑改动包 |
| 覆盖率 | `go test -covermode=atomic -coverprofile=/tmp/fix.cover ./...` + `go tool cover -func=/tmp/fix.cover` | 修前修后都要记录，不得下降 |
| 模块集成测试 | 按 `module-integration-test`：`go test -count=1 <本轮涉及包>` | 只验证生产模块之间的契约与装配，不用单元测试结果替代 |
| 业务接口用例 | `make test-api-fresh` | 优先用 fresh：复用已有进程会命中幂等返回 `REUSED` |
| 用例管线自检 | `make test-selftest` | 改动 `tests/` 下任何文件时必跑 |

## 按改动类型追加

| 改动类型 | 追加必跑 |
| --- | --- |
| 领域规则（`internal/domain/reminder/**`） | 回归用例、相关包覆盖率；涉及时钟或并发时 `go test -race ./...` |
| 应用编排（`internal/application/**`） | `go test -race ./...`、业务接口用例 |
| 仓储与迁移（`internal/adapter/storage/**`） | 空库迁移、旧库升级、重复迁移、幂等重放；SQLite 文件不要复用旧数据 |
| 端口与适配器（`internal/port/**`、`internal/adapter/task`、`adapter/user`） | 业务接口用例 |
| HTTP 传输与 DTO | 改了 IDL 时 `make lint-idl`；业务接口用例 |
| 事件链路 | `make test` 内的库表断言；接口用例看不到事件，必须在「未验证」里写清 |
| 前端不可见的渠道能力（Push 文案、发送失败重试） | 需要渠道桩；没有桩时只能写未验证，不得声称已验证 |
| 用例数据（`tests/cases/**`） | `pytest -m subject --collect-only -q`、`make test-selftest`；按 `test-case-to-automation` 的回查脚本校验 |
| 引擎（`tests/common/**`） | `make test-selftest` + 全量业务接口用例 |
| dev-tools 脚本（`dev-tools/**/scripts/**`） | 该脚本的自检用例 + 用真实输入跑一次 |
| 文档契约 | 对应回查脚本：`check_tech_design.py` / `check_acceptance_criteria.py` / `check_test_cases.py` |

## 覆盖率怎么写

写成「修前 x% → 修后 y%」，两侧都要有真实数字。只用「已通过」不能证明覆盖率没有下降。
下降时不允许交付：要么补测试，要么说明为什么这次下降是合理的并得到人工确认。

## skip 一律不计入通过

`module-integration-test` 明确规定：任何 skip、ignore 或 pending 都不能计入「集成测试全部通过」。
业务接口用例同理。结论里必须区分通过 / 失败 / 跳过 / 未执行四类数字，不能只写「全部通过」。

## 业务接口用例有 skip 时

被测服务不可达时业务用例会整体 skip，这**不是通过**：

- 整体 skip → 写「未获得业务结论」，本次不得声明业务行为已验证；
- 部分 skip（例如时钟依赖的 pending 用例）→ 在「未验证」里写明跳过多少条、为什么、解锁条件是什么。

`make test-api-fresh` 会先启动本地入口再跑，能避免服务不可达导致的空跑；失败信息指向缺陷本身时才可信。
