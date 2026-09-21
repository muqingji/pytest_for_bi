package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"

	"intelligent-reminder-assistant/internal/adapter/channel"
	"intelligent-reminder-assistant/internal/adapter/storage"
	"intelligent-reminder-assistant/internal/adapter/user"
	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/application/snooze"
	transport "intelligent-reminder-assistant/internal/transport/http"
)

// 本地入口默认装配值，对应技术方案 4.7 的 max_push_per_day=1、max_send_attempts=2、dispatch_batch_size=50。
const (
	defaultMaxPushPerDay   = 1
	defaultMaxSendAttempts = 2
	defaultDispatchBatch   = 50
	defaultStrategyVersion = "v1"
)

// inMemoryDatabase 是本地入口默认使用的进程内数据库：每次启动都回到 Fixture 基线，
// 重复跑业务测试不会读到上一次运行的决策与排程；需要保留数据时用 -db 指定文件路径。
const inMemoryDatabase = ":memory:"

// serveOptions 是本地 HTTP 入口的启动参数（技术方案 4.3.1、4.7）。
type serveOptions struct {
	Addr     string
	Token    string
	Fixtures string
	Database string
}

// serve 装配并启动本地 HTTP 入口：任务与用户来自 Fixture 种子，三个应用用例复用生产实现，
// HTTP 层只做报文契约、鉴权与超时。入口只允许绑定回环地址，避免把联调入口暴露到内网。
func serve(ctx context.Context, options serveOptions, output io.Writer) error {
	if err := validateLoopbackAddr(options.Addr); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(options.Database), 0o700); err != nil {
		return fmt.Errorf("create database directory: %w", err)
	}
	store, err := openStore(options.Database)
	if err != nil {
		return err
	}
	defer store.Close()
	if err := migrateStore(store, ctx); err != nil {
		return err
	}
	seeds, err := loadFixtures(options.Fixtures, nowFunc)
	if err != nil {
		return err
	}
	fmt.Fprintf(output, "reminder-service local HTTP entry listening on http://%s (fixtures: %s)\n", options.Addr, options.Fixtures)
	return assemble(store, seeds, options.Token).Serve(ctx, options.Addr)
}

// assemble 组装本地入口的三个用例与路由。抽出来是为了让模块集成测试用临时端口启动同一套装配，
// 避免测试与真实入口各写一份装配而出现口径漂移。
func assemble(store *storage.Store, seeds fixtures, token string) transport.Server {
	clock := systemClock{}
	// 用量基线叠加在真实仓储之上：种子表达服务启动前已发生的用量，运行期新产生的用量仍从库里统计。
	reminders := user.UsageOverlay{FixtureReminderRepository: store, Baseline: seeds.usage}
	return transport.Server{
		Evaluate: evaluate.Service{
			Tasks: seeds.tasks, Preferences: seeds.users, Behaviors: seeds.users,
			Reminders: reminders, Clock: clock, StrategyVersion: defaultStrategyVersion,
		},
		Dispatch: dispatch.Service{
			Reminders: reminders, Preferences: seeds.users, Tasks: seeds.tasks,
			Renderer: channel.NewTemplateRenderer(), Push: &channel.MockPushSender{}, Clock: clock,
			MaxPushPerDay: defaultMaxPushPerDay, MaxSendAttempts: defaultMaxSendAttempts, BatchSize: defaultDispatchBatch,
		},
		Snooze: snooze.Service{
			Reminders: reminders, Preferences: seeds.users, Tasks: seeds.tasks, Clock: clock,
		},
		Config: transport.Config{Token: token},
	}
}

// validateLoopbackAddr 校验入口只绑定回环地址（技术方案 4.3.1：本地入口仅监听 127.0.0.1）。
func validateLoopbackAddr(addr string) error {
	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		return fmt.Errorf("invalid addr %q: %w", addr, err)
	}
	if host == "" || port == "" {
		return fmt.Errorf("invalid addr %q: host and port are required", addr)
	}
	if host == "localhost" {
		return nil
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return fmt.Errorf("invalid addr %q: host must be loopback", addr)
	}
	return nil
}
