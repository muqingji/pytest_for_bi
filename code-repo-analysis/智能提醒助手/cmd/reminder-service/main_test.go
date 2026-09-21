package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRunAndSystemClock(t *testing.T) {
	if (systemClock{}).Now().IsZero() {
		t.Fatal("system clock returned zero")
	}
	var output bytes.Buffer
	err := run([]string{"-user", "u1", "-task-date", "2026-09-20", "-db", filepath.Join(t.TempDir(), "demo.db")}, &output)
	if err != nil || !strings.Contains(output.String(), `"ShouldRemind": true`) {
		t.Fatalf("run: err=%v output=%s", err, output.String())
	}
}

func TestRunRejectsInvalidArgumentsAndDatabaseDirectory(t *testing.T) {
	if err := run([]string{"-unknown"}, &bytes.Buffer{}); err == nil {
		t.Fatal("expected flag parse error")
	}
	parent := filepath.Join(t.TempDir(), "file")
	if err := os.WriteFile(parent, []byte("not a directory"), 0o600); err != nil {
		t.Fatalf("create blocking parent: %v", err)
	}
	if err := run([]string{"-db", filepath.Join(parent, "nested.db")}, &bytes.Buffer{}); err == nil {
		t.Fatal("expected database directory error")
	}
}

func TestMainRoutesErrorsToExitProcess(t *testing.T) {
	oldArgs := os.Args
	oldExit := exitProcess
	t.Cleanup(func() { os.Args = oldArgs; exitProcess = oldExit })
	os.Args = []string{"reminder-service", "-unknown"}
	called := 0
	exitProcess = func(code int) { called = code }
	main()
	if called != 1 {
		t.Fatalf("expected exit code 1, got %d", called)
	}
}
