package port

import (
	"context"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

type TaskRepository interface {
	GetDailyTask(ctx context.Context, userID, taskDate string) (reminder.DailyTask, error)
}

type PreferenceRepository interface {
	Get(ctx context.Context, userID string) (reminder.ReminderPreference, error)
}

type BehaviorRepository interface {
	GetRecent(ctx context.Context, userID string, days int) (reminder.BehaviorSummary, error)
}

type ReminderRepository interface {
	GetDailyUsage(ctx context.Context, userID, taskDate string) (reminder.DailyUsage, error)
	CreateDecisionAndSchedule(ctx context.Context, decision reminder.Decision, schedule *reminder.Schedule) (CreateResult, error)
	AppendEvent(ctx context.Context, event reminder.ReminderEvent) error
}

type CreateResult struct {
	Decision reminder.Decision
	Reused   bool
}

type Clock interface {
	Now() time.Time
}
