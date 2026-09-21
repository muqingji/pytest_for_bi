# 本地 Go 环境与调试

本文件记录本机 Go 环境的位置、启用方式和运行/调试命令，供 FR-001 及后续切片复用。

## 1. 环境概览

| 项目 | 值 |
| --- | --- |
| Go | go1.22.12 darwin/amd64（与 `go.mod` 的 `go 1.22` 对齐） |
| Delve | dlv v1.25.2（含 ad-hoc 签名，用于断点调试） |
| 安装位置 | 仓库根目录 `.cache/`（工作区内，不写 `/usr/local`，不需要 sudo） |
| 模块代理 | `https://goproxy.cn,direct`（本机无法直连 `proxy.golang.org`） |
| 工具链切换 | `GOTOOLCHAIN=local`，禁止自动下载工具链，避免离线/代理失败 |

目录布局：

| 路径 | 用途 |
| --- | --- |
| `.cache/go-sdk/go` | `GOROOT`，Go 源码与 `go`、`gofmt`、`go vet` 等工具 |
| `.cache/gopath` | `GOPATH`，`GOBIN=.cache/gopath/bin`（`dlv` 在此）、`GOMODCACHE=.cache/gopath/pkg/mod` |
| `.cache/go-build-cache` | `GOCACHE`，编译缓存 |
| `.cache/go-env.sh` | 环境变量脚本，所有命令的唯一环境来源 |
| `.cache/go-dl/` | Go tarball 下载缓存，确认环境稳定后可删除 |

`.cache/` 已在仓库根 `.gitignore` 中忽略，不会进入提交。

## 2. 启用环境

每次新开终端执行一次：

~~~bash
source scripts/go-env.sh
~~~

输出示例：

~~~text
Go      : go version go1.22.12 darwin/amd64
GOROOT  : /Users/muqingji/code/study/pytest_for_bi/.cache/go-sdk/go
GOPATH  : /Users/muqingji/code/study/pytest_for_bi/.cache/gopath
GOPROXY : https://goproxy.cn,direct
Delve   : version: 1.25.2
~~~

如需每个终端自动生效，由本人把下面一行追加到 `~/.zshrc`（需要改用户主目录文件，故未自动写入）：

~~~bash
source /Users/muqingji/code/study/pytest_for_bi/.cache/go-env.sh
~~~

## 3. 运行与验证

`Makefile` 已内置环境注入，无需先 `source`：

~~~bash
make env      # 打印当前生效的 Go / Delve 环境
make build    # 编译到 bin/reminder-service
make run      # 运行一次 FR-001 被动型用户 Demo
make test     # 运行全部单元测试
make vet      # 静态检查
make fmt      # gofmt 格式化
make tidy     # 整理 go.mod / go.sum
make clean    # 清理测试缓存、编译产物和本地 Demo 数据库
~~~

等价的直接命令（已 `source scripts/go-env.sh` 后）：

~~~bash
go build ./...
go test ./...
go run ./cmd/reminder-service -user user-passive -task-date 2026-09-20 -db data/reminder.db
~~~

当前基线（本机实测）：

~~~text
ok  intelligent-reminder-assistant/internal/adapter/storage      0.481s
ok  intelligent-reminder-assistant/internal/application/evaluate 1.124s
ok  intelligent-reminder-assistant/internal/domain/reminder      0.788s
~~~

Demo 输出（`user-passive` + `2026-09-20`，与 `demo-data/fr001-passive.json` 期望一致）：

~~~json
{
  "ShouldRemind": true,
  "ScheduledAt": "2026-09-20T19:30:00Z",
  "Channel": "push",
  "ReasonCode": "ELIGIBLE",
  "UserSegment": "PASSIVE",
  "Status": "SCHEDULED",
  "Version": 1
}
~~~

## 4. 调试

### 4.1 先跑冒烟检查

~~~bash
make smoke
~~~

脚本在 `internal/domain/reminder.Evaluate` 打断点，命中后打印 `input.Task.UserID`、`input.Task.CompletedCount`、`input.Preference.DailyPushCap`，用于确认「能停下、能看变量」这条链路可用。通过时输出 `调试链路验证通过：断点命中，变量读取成功。`

### 4.2 终端交互式调试

~~~bash
make debug
~~~

进入 dlv REPL 后常用命令：

~~~text
break internal/domain/reminder.Evaluate   设置断点
break internal/adapter/storage/sqlite.go:150
continue                                  继续运行
next / step                               单步（跨过 / 进入函数）
print input.Task                          查看变量
locals                                    当前栈帧所有局部变量
goroutines / stack                        协程与调用栈
exit                                      退出
~~~

调试单测：

~~~bash
dlv test ./internal/domain/reminder -- -test.run TestEvaluateDecisionBoundaries
~~~

### 4.3 VS Code

`.vscode/launch.json` 和 `.vscode/settings.json` 已配好本地 GOROOT、GOPATH、GOPROXY 和终端环境变量。安装 Go 扩展后按 F5，选择：

- `Debug reminder-service (FR-001 被动型用户)`：以 Demo 参数启动服务。
- `Debug 当前文件所在包的测试`：调试当前打开的测试文件。
- `Debug reminder.Evaluate 单测`：调试 `TestEvaluateDecisionBoundaries`。

首次使用扩展会提示安装 `dlv`、`gopls` 等工具，按提示安装即可（代理已指向 `goproxy.cn`，会装到 `.cache/gopath/bin`）。

当前机器已预装 `dlv v1.25.2` 和 `gopls v0.16.2`，无需再由扩展下载。注意 `gopls v0.17` 及以上要求 Go ≥ 1.23，而本项目固定 `GOTOOLCHAIN=local` 并使用 Go 1.22.12，升级 gopls 前需先升级本地 Go 工具链。

### 4.4 IntelliJ IDEA Ultimate

本机 IDEA 尚未安装 Go 插件，需先在 `Settings > Plugins > Marketplace` 安装 `Go` 插件并重启。然后：

1. `Settings > Languages & Frameworks > Go > GOROOT` 选择 `/Users/muqingji/code/study/pytest_for_bi/.cache/go-sdk/go`。
2. 同页 `Go Modules` 将代理设为 `https://goproxy.cn,direct`；`GOPATH` 设为 `/Users/muqingji/code/study/pytest_for_bi/.cache/gopath`。
3. 新建 `Go Build` 运行配置：`Run kind=Package`，`Package path=intelligent-reminder-assistant/cmd/reminder-service`，`Working directory` 为项目根，`Program arguments` 填 `-user user-passive -task-date 2026-09-20 -db data/reminder.db`。
4. 新建 `Go Test` 运行配置即可调试单测；断点直接打在源码行上。

若 IDEA 从 Dock 启动、读不到环境变量，在上述运行配置的 `Environment variables` 中补 `GOROOT`、`GOPATH`、`GOBIN`、`GOCACHE`、`GOMODCACHE`、`GOPROXY`、`GOTOOLCHAIN`，取值见 `.cache/go-env.sh`。

## 5. 故障排查

### 5.1 `could not launch process: stub exited while waiting for connection`

Delve 没能真正接管目标进程。按顺序排查：

1. 是否在受限沙箱/无调试权限的环境中运行。本机 Codex 沙箱会拒绝 `ptrace`，在该沙箱内无法进行调试，需在本人终端执行。
2. dlv 是否可被系统授权调试。已对 `.cache/gopath/bin/dlv` 做 ad-hoc 签名并带上 `com.apple.security.cs.debugger`、`com.apple.security.get-task-allow` 权限，重装 dlv 后需重新签名：

   ~~~bash
   codesign --force --sign - --entitlements /tmp/dlv-entitlements.plist \
     /Users/muqingji/code/study/pytest_for_bi/.cache/gopath/bin/dlv
   ~~~

3. 仍失败时，在 `系统设置 > 隐私与安全性 > 开发者工具` 中勾选所使用的终端/IDE。

### 5.2 `go: command not found`

未执行 `source scripts/go-env.sh`。`make` 目标不受影响，因为 Makefile 会自动注入环境。

### 5.3 依赖拉取超时

`proxy.golang.org` 在本机不可达，环境已固定使用 `goproxy.cn`。若出现超时，确认 `go env GOPROXY` 输出为 `https://goproxy.cn,direct`。

### 5.4 想改用系统级 Go

本环境可整体迁移：

~~~bash
mv /Users/muqingji/code/study/pytest_for_bi/.cache/go-sdk/go /usr/local/go
~~~

然后修改 `.cache/go-env.sh` 中的 `GOROOT`（以及可选的 `GOPATH`、`GOCACHE`）。迁移后 `.vscode/settings.json` 与上述 IDEA 配置需同步修改。

## 6. 本次搭建顺带修复的编译问题

原代码无法编译，为达成「可运行、可调试」做了 3 处最小修复，未改动业务规则：

| 文件 | 问题 | 处理 |
| --- | --- | --- |
| `internal/domain/reminder/evaluator.go` | `EvaluationPlan` 复合字面量缺少收尾 `}`，语法错误 | 补齐大括号 |
| `internal/domain/reminder/types.go` | `sqlite.go` 调用了不存在的 `Decision.ScheduledAtEqual` | 新增该方法，按时间点比较可空的 `ScheduledAt`（nil 仅与 nil 相等） |
| `cmd/`、`internal/` 下 8 个文件 | `gofmt` 未对齐 | 执行 `gofmt -w`，仅空白与对齐变化 |

完成后 `go build ./...`、`go vet ./...`、`go test ./...` 全部通过。

## 本地 HTTP 入口与业务测试

本地入口把技术方案 4.3 的三个内部接口跑在 `127.0.0.1` 上，业务测试（pytest）直接发真实 HTTP 请求：

```bash
make build                                  # 编译 bin/reminder-service
make serve                                  # 显式开启 feature_enabled 并启动本地入口（默认 127.0.0.1:8080）
make test-api-fresh                         # 显式开启开关 → 跑 pytest → 自动关闭（推荐）
```

- 启动参数：`-serve`（开启入口）、`-addr`（默认 `127.0.0.1:8080`，只接受回环地址或 `localhost`）、`-token`（默认 `local-dev-token`）、`-fixtures`（默认 `testenv/fixtures/users.json`）、`-db`（不传时用进程内 SQLite，每次启动回到 Fixture 基线）。
- 直接请求示例：

```bash
curl -s -X POST http://127.0.0.1:8080/internal/v1/reminders/evaluate \
  -H 'Authorization: Bearer local-dev-token' -H 'Content-Type: application/json' \
  -d '{"request_id":"req-1","user_id":"user-passive","task_date":"2026-09-20","trigger":"DAILY_BATCH"}'
```

- 退出与重启：入口收到 `SIGINT/SIGTERM` 后优雅关闭（等待在途请求，最长 5s）。**不要复用同一个进程连跑两遍业务测试**：重复评估会命中幂等返回 `REUSED`，应改用 `make test-api-fresh` 或手动重启。
- 灰度开关：二进制的 `-feature-enabled` 默认 false；`make serve` 与 `make test-api-fresh` 已显式传入。关闭状态下 evaluate/dispatch 返回 `503 FEATURE_DISABLED`、`retryable=false`。
- 未实现项：入口限流（`rate_limit_caller_qps`、`rate_limit_user_qps`）与固定测试时钟仍未实现，依赖运行时刻的用例保持 `pending`。
