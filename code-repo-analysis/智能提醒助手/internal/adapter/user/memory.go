package user

import (
	"context"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

type MemoryRepository struct {
	Preferences      map[string]reminder.ReminderPreference
	Behaviors        map[string]reminder.BehaviorSummary
	PreferenceErrors map[string]error
	BehaviorErrors   map[string]error
}

func (r MemoryRepository) Get(ctx context.Context, userID string) (reminder.ReminderPreference, error) {
	if err := contextError(ctx); err != nil {
		return reminder.ReminderPreference{}, err
	}
	if err := r.PreferenceErrors[userID]; err != nil {
		return reminder.ReminderPreference{}, err
	}
	preference, ok := r.Preferences[userID]
	if !ok {
		return reminder.ReminderPreference{
			Enabled:      true,
			PushEnabled:  true,
			DailyPushCap: 1,
		}, nil
	}
	if preference.DailyPushCap <= 0 {
		preference.DailyPushCap = 1
	}
	return preference, nil
}

func (r MemoryRepository) GetRecent(ctx context.Context, userID string, _ int) (reminder.BehaviorSummary, error) {
	if err := contextError(ctx); err != nil {
		return reminder.BehaviorSummary{}, err
	}
	if err := r.BehaviorErrors[userID]; err != nil {
		return reminder.BehaviorSummary{}, err
	}
	return r.Behaviors[userID], nil
}

func contextError(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
		return nil
	}
}
