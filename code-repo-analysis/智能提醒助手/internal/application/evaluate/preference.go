package evaluate

import (
	"context"
	"fmt"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

// PreferenceChangedEvent is the transport-neutral form of the
// reminder_preference_updated event. The preference service remains the
// source of truth; payload values are retained for the audit event only.
type PreferenceChangedEvent struct {
	EventID         string
	UserID          string
	TaskDate        string
	Timezone        string
	EventTime       time.Time
	ChangedFields   []string
	ReminderEnabled bool
	QuietHoursStart string
	QuietHoursEnd   string
	EffectiveAt     time.Time
}

// PreferenceChangedHandler applies a preference update to the user's current
// day's reminder decision. It deliberately delegates business evaluation to
// Service so the daily, AppOpened, and preference-change paths share rules.
type PreferenceChangedHandler struct {
	Service Service
}

func (h PreferenceChangedHandler) Handle(ctx context.Context, event PreferenceChangedEvent) (Result, error) {
	if event.EventID == "" || event.UserID == "" || event.TaskDate == "" {
		return Result{}, fmt.Errorf("event_id, user_id and task_date are required")
	}
	if event.EventTime.IsZero() {
		event.EventTime = h.Service.Clock.Now()
	}
	if event.EffectiveAt.IsZero() {
		event.EffectiveAt = event.EventTime
	}
	if err := h.Service.Reminders.AppendEvent(ctx, reminder.ReminderEvent{
		EventID:       event.EventID,
		EventName:     "reminder_preference_updated",
		SchemaVersion: "v1",
		Source:        "app",
		UserID:        event.UserID,
		TaskDate:      event.TaskDate,
		Timezone:      event.Timezone,
		EventTime:     event.EventTime,
		Payload: map[string]any{
			"changed_fields":    event.ChangedFields,
			"reminder_enabled":  event.ReminderEnabled,
			"quiet_hours_start": event.QuietHoursStart,
			"quiet_hours_end":   event.QuietHoursEnd,
			"effective_at":      event.EffectiveAt.UTC().Format(time.RFC3339Nano),
		},
	}); err != nil {
		return Result{}, fmt.Errorf("append preference event: %w", err)
	}

	// Read the external source before mutating a pending schedule. A failed
	// read therefore cannot cancel or create a schedule from stale data.
	preference, err := h.Service.Preferences.Get(ctx, event.UserID)
	if err != nil {
		return Result{}, fmt.Errorf("read reminder preference: %w", err)
	}
	if !preference.ReminderEnabled {
		repository, ok := h.Service.Reminders.(port.PreferenceScheduleRepository)
		if !ok {
			return Result{}, fmt.Errorf("reminder repository does not support preference schedule updates")
		}
		if err := repository.CancelPendingSchedules(ctx, event.UserID, event.TaskDate, reminder.ReasonReminderDisabled, event.EventTime); err != nil {
			return Result{}, fmt.Errorf("cancel pending schedules: %w", err)
		}
	}

	return h.Service.Evaluate(ctx, Request{
		UserID:   event.UserID,
		TaskDate: event.TaskDate,
		Trigger:  reminder.TriggerPreferenceChanged,
	})
}
