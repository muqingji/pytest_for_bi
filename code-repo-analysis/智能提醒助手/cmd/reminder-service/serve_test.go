package main

import (
	"bytes"
	"context"
	"flag"
	"io"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// testServiceToken 是本地入口测试使用的静态令牌，与生产缺省值区分。
const testServiceToken = "serve-test-token"

// repoFixturePath 返回仓库内真实种子文件路径。本地入口按相对路径加载它，
// 因此集成测试必须与运行时使用同一份种子，才能证明 pytest 的请求路径成立。
func repoFixturePath(t *testing.T) string {
	t.Helper()
	path := filepath.Join("..", "..", "testenv", "fixtures", "users.json")
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("fixture file is required for local runs: %v", err)
	}
	return path
}

// TestValidateLoopbackAddr 覆盖入口绑定地址的白名单：只允许回环地址与 localhost，
// 其余（含空主机、缺端口、不可解析主机、非回环 IP）一律拒绝，避免把联调入口暴露到内网。
func TestValidateLoopbackAddr(t *testing.T) {
	cases := []struct {
		addr    string
		wantErr bool
	}{
		{addr: "127.0.0.1:8080"},
		{addr: "localhost:8080"},
		{addr: "[::1]:8080"},
		{addr: "127.0.0.1:0"},
		{addr: "", wantErr: true},
		{addr: "127.0.0.1", wantErr: true},
		{addr: ":8080", wantErr: true},
		{addr: "0.0.0.0:8080", wantErr: true},
		{addr: "10.1.2.3:8080", wantErr: true},
		{addr: "not-an-ip:8080", wantErr: true},
	}
	for _, testCase := range cases {
		t.Run(testCase.addr, func(t *testing.T) {
			err := validateLoopbackAddr(testCase.addr)
			if testCase.wantErr && err == nil {
				t.Fatalf("%q must be rejected", testCase.addr)
			}
			if !testCase.wantErr && err != nil {
				t.Fatalf("%q must be accepted: %v", testCase.addr, err)
			}
		})
	}
}

// TestFlagProvided 覆盖「参数是否被显式传入」的判定：未传时用进程内数据库，
// 显式传入 -db 时保留文件路径，避免上一次运行的决策污染下一次业务测试。
func TestFlagProvided(t *testing.T) {
	flags := flag.NewFlagSet("test", flag.ContinueOnError)
	database := flags.String("db", "data/reminder.db", "database path")
	if err := flags.Parse([]string{"-db", ":memory:"}); err != nil {
		t.Fatalf("parse: %v", err)
	}
	if !flagProvided(flags, "db") || *database != inMemoryDatabase {
		t.Fatalf("explicit -db must be detected: %v %q", flagProvided(flags, "db"), *database)
	}
	empty := flag.NewFlagSet("test", flag.ContinueOnError)
	empty.String("db", "data/reminder.db", "database path")
	if err := empty.Parse(nil); err != nil {
		t.Fatalf("parse: %v", err)
	}
	if flagProvided(empty, "db") {
		t.Fatal("omitted -db must not be reported as provided")
	}
}

// TestAssembleWiresFixtureEntry 覆盖本地入口的装配：三个用例都接上同一份种子与真实仓储，
// 鉴权令牌来自启动参数。
func TestAssembleWiresFixtureEntry(t *testing.T) {
	path := filepath.Join(t.TempDir(), "assemble.db")
	store := openIntegrationStore(t, path)
	defer func() { _ = store.Close() }()
	seeds, err := loadFixtures(repoFixturePath(t), nowFunc)
	if err != nil {
		t.Fatalf("load fixtures: %v", err)
	}

	server := assemble(store, seeds, "assemble-token")
	if server.Evaluate == nil || server.Dispatch == nil || server.Snooze == nil {
		t.Fatalf("all three use cases must be wired: %+v", server)
	}
	if server.Config.Token != "assemble-token" {
		t.Fatalf("token not wired: %q", server.Config.Token)
	}
	if server.Handler() == nil {
		t.Fatal("handler must be constructed")
	}
}

// TestServeValidatesAddressAndFixtures 覆盖本地入口的启动前校验与失败关闭：
// 非回环地址与缺失的种子文件都必须在开始服务之前返回错误。
func TestServeValidatesAddressAndFixtures(t *testing.T) {
	if err := serve(context.Background(), serveOptions{
		Addr: "0.0.0.0:8080", Token: testServiceToken, Fixtures: repoFixturePath(t), Database: inMemoryDatabase,
	}, io.Discard); err == nil {
		t.Fatal("non-loopback address must be rejected")
	}
	if err := serve(context.Background(), serveOptions{
		Addr: "127.0.0.1:0", Token: testServiceToken,
		Fixtures: filepath.Join(t.TempDir(), "missing.json"), Database: inMemoryDatabase,
	}, io.Discard); err == nil {
		t.Fatal("missing fixtures must be rejected")
	}
	if err := serve(context.Background(), serveOptions{
		Addr: "127.0.0.1:0", Token: testServiceToken,
		Fixtures: filepath.Join(t.TempDir(), "missing.json"), Database: "not/a/directory/db.sqlite",
	}, io.Discard); err == nil {
		t.Fatal("missing fixtures must be rejected regardless of the storage path")
	}
}

// TestServeStartsLocalEntryAndStopsOnContextCancel 覆盖本地入口的成功启动与退出：
// 进程内数据库 + 真实种子 + 真实 HTTP 装配，ctx 取消后必须干净退出。
func TestServeStartsLocalEntryAndStopsOnContextCancel(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	output := &bytes.Buffer{}
	done := make(chan error, 1)
	go func() {
		done <- serve(ctx, serveOptions{
			Addr: "127.0.0.1:0", Token: testServiceToken, Fixtures: repoFixturePath(t), Database: inMemoryDatabase,
		}, output)
	}()

	deadline := time.After(10 * time.Second)
	for !bytes.Contains(output.Bytes(), []byte("listening on")) {
		select {
		case err := <-done:
			t.Fatalf("local entry exited early: %v", err)
		case <-deadline:
			t.Fatal("local entry did not start in time")
		default:
			time.Sleep(10 * time.Millisecond)
		}
	}
	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("graceful shutdown must not report an error: %v", err)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("local entry did not stop after context cancellation")
	}
}

// TestRunServeBranchFailsFastOnNonLoopbackAddress 覆盖 -serve 参数解析与分支：
// 未传 -db 时必须改用进程内数据库，并且仍在服务启动前拦住非回环地址。
func TestRunServeBranchFailsFastOnNonLoopbackAddress(t *testing.T) {
	fixtures := repoFixturePath(t)
	if err := run([]string{"-serve", "-addr", "0.0.0.0:1234", "-fixtures", fixtures}, io.Discard); err == nil {
		t.Fatal("non-loopback address must fail")
	}
	database := filepath.Join(t.TempDir(), "serve.db")
	if err := run([]string{"-serve", "-addr", "0.0.0.0:1234", "-fixtures", fixtures, "-db", database}, io.Discard); err == nil {
		t.Fatal("non-loopback address must fail with an explicit database too")
	}
}
