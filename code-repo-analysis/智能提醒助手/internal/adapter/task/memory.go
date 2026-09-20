package task

import (
	"context"
	"fmt"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

type MemoryRepository struct {
	Tasks map[string]reminder.DailyTask
}

func (r MemoryRepository) GetDailyTask(_ context.Context, userID, taskDate string) (reminder.DailyTask, error) {
	key := userID + "|" + taskDate
	task, ok := r.Tasks[key]
	if !ok {
		return reminder.DailyTask{UserID: userID, TaskDate: taskDate}, nil
	}
	return task, nil
}

func Key(userID, taskDate string) string {
	if userID == "" || taskDate == "" {
		panic(fmt.Sprintf("invalid task fixture key: %q|%q", userID, taskDate))
	}
	return userID + "|" + taskDate
}
