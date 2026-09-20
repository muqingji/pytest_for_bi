package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"intelligent-reminder-assistant/internal/adapter/storage"
	"intelligent-reminder-assistant/internal/adapter/task"
	"intelligent-reminder-assistant/internal/adapter/user"
	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

type systemClock struct{}

func (systemClock) Now() time.Time { return time.Now().UTC() }

func main() {
	userID := flag.String("user", "user-passive", "fixture user id")
	taskDate := flag.String("task-date", time.Now().UTC().Format("2006-01-02"), "local task date")
	databasePath := flag.String("db", "data/reminder.db", "SQLite database path")
	flag.Parse()

	if err := os.MkdirAll(filepath.Dir(*databasePath), 0o700); err != nil {
		fatal(err)
	}
	store, err := storage.Open(*databasePath)
	if err != nil {
		fatal(err)
	}
	defer store.Close()
	if err := store.Migrate(context.Background()); err != nil {
		fatal(err)
	}

	now := time.Now().UTC()
	tasks := task.MemoryRepository{Tasks: map[string]reminder.DailyTask{
		task.Key(*userID, *taskDate): {
			UserID: *userID, TaskDate: *taskDate, RequiredCount: 5, CompletedCount: 2,
			EstimatedMinutes: 30, Deadline: now.Add(4 * time.Hour),
		},
	}}
	users := user.MemoryRepository{
		Preferences: map[string]reminder.ReminderPreference{
			*userID: {Enabled: true, PushEnabled: true, DailyPushCap: 1, Timezone: time.UTC},
		},
		Behaviors: map[string]reminder.BehaviorSummary{
			*userID: {HistoryDaysAvailable: 7, InactiveDays: 0},
		},
	}
	service := evaluate.Service{
		Tasks: tasks, Preferences: users, Behaviors: users, Reminders: store,
		Clock: systemClock{}, StrategyVersion: "v1",
	}
	result, err := service.Evaluate(context.Background(), evaluate.Request{UserID: *userID, TaskDate: *taskDate, Trigger: reminder.TriggerDaily})
	if err != nil {
		fatal(err)
	}
	encoded, err := json.MarshalIndent(result.Decision, "", "  ")
	if err != nil {
		fatal(err)
	}
	fmt.Println(string(encoded))
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
