package main

import (
	"context"
	"fmt"
	"path/filepath"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

func TestZZDebugEvaluateThroughAssembly(t *testing.T) {
	restore := nowFunc
	nowFunc = func() time.Time { return fixedEntryNow }
	defer func() { nowFunc = restore }()

	store := openIntegrationStore(t, filepath.Join(t.TempDir(), "debug.db"))
	defer func() { _ = store.Close() }()
	seeds, err := loadFixtures(repoFixturePath(t), nowFunc)
	if err != nil {
		t.Fatalf("fixtures: %v", err)
	}
	server := assemble(store, seeds, testServiceToken)
	service, ok := server.Evaluate.(evaluate.Service)
	if !ok {
		t.Fatalf("unexpected evaluate type %T", server.Evaluate)
	}
	result, err := service.Evaluate(context.Background(), evaluate.Request{
		UserID: "user-passive", TaskDate: fixedEntryNow.Format("2006-01-02"), Trigger: reminder.TriggerDaily,
	})
	fmt.Printf("RESULT=%+v\nERR=%v\n", result.Decision, err)
}
