# 本地开发入口。默认自动注入仓库内的 Go 工具链（../../.cache/go-env.sh），
# 因此在未全局安装 Go 的机器上也能直接 make build / make test / make debug。
REPO_ROOT := $(abspath $(CURDIR)/../..)
TOOLCHAIN_ENV := $(REPO_ROOT)/.cache/go-env.sh

ifeq ($(wildcard $(TOOLCHAIN_ENV)),)
GO := go
else
GO := . $(TOOLCHAIN_ENV) && go
endif

BIN_DIR := bin
SERVICE_BIN := $(BIN_DIR)/reminder-service
SERVICE_PKG := ./cmd/reminder-service
DEMO_DB := $(CURDIR)/data/reminder-demo.db

.PHONY: help env build run test vet fmt tidy smoke debug clean

help:
	@echo "make env    打印当前生效的 Go/Delve 环境"
	@echo "make build  编译 reminder-service 到 $(SERVICE_BIN)"
	@echo "make run    运行一次 FR-001 被动型用户 Demo"
	@echo "make test   运行全部单元测试"
	@echo "make vet    静态检查"
	@echo "make fmt    gofmt 格式化"
	@echo "make tidy   整理 go.mod / go.sum"
	@echo "make smoke   冒烟验证 Delve 调试链路（断点+打印变量）"
	@echo "make debug   交互式调试 reminder-service"
	@echo "make clean   清理编译产物与本地 Demo 数据库"

env:
	@. $(TOOLCHAIN_ENV) && go version && go env GOROOT GOPATH GOCACHE GOPROXY && dlv version | head -2

build:
	@$(GO) build -o $(SERVICE_BIN) $(SERVICE_PKG)

run:
	@$(GO) run $(SERVICE_PKG) -user user-passive -task-date 2026-09-20 -db $(DEMO_DB)

test:
	@$(GO) test ./...

vet:
	@$(GO) vet ./...

fmt:
	@$(GO) fmt ./...

tidy:
	@$(GO) mod tidy

smoke:
	@./scripts/dlv-smoke.sh

debug:
	@$(GO) build -o $(SERVICE_BIN) $(SERVICE_PKG)
	@. $(TOOLCHAIN_ENV) && dlv exec $(SERVICE_BIN) -- -user user-passive -task-date 2026-09-20 -db $(DEMO_DB)

clean:
	@. $(TOOLCHAIN_ENV) && go clean -testcache
	@rm -rf $(BIN_DIR) $(CURDIR)/data
