package task

import (
	"context"
	"testing"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

func TestMemoryRepositoryReturnsStoredAndMissingTasks(t *testing.T) {
	repo := MemoryRepository{Tasks: map[string]reminder.DailyTask{
		Key("u1", "2026-09-20"): {UserID: "u1", TaskDate: "2026-09-20", RequiredCount: 1},
	}}
	stored, err := repo.GetDailyTask(context.Background(), "u1", "2026-09-20")
	if err != nil || stored.RequiredCount != 1 {
		t.Fatalf("stored task: %+v err=%v", stored, err)
	}
	missing, err := repo.GetDailyTask(context.Background(), "u2", "2026-09-20")
	if err != nil || missing.HasTask() || missing.UserID != "u2" || missing.TaskDate != "2026-09-20" {
		t.Fatalf("missing task: %+v err=%v", missing, err)
	}
}

func TestKeyRejectsIncompleteFixtureKeys(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Fatal("expected invalid fixture key panic")
		}
	}()
	_ = Key("", "2026-09-20")
}
