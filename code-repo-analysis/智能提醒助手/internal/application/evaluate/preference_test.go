package evaluate

import (
	"context"
	"errors"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

type preferenceScheduleFake struct {
	decision        reminder.Decision
	preferenceEvent reminder.ReminderEvent
	decisionEvent   reminder.ReminderEvent
	cancelled       int
	cancelErr       error
	createErr       error
}

func (f *preferenceScheduleFake) GetDailyUsage(context.Context, string, string) (reminder.DailyUsage, error) {
	return reminder.DailyUsage{}, nil
}

func (f *preferenceScheduleFake) CreateDecisionAndSchedule(_ context.Context, decision reminder.Decision, _ *reminder.Schedule) (port.CreateResult, error) {
	f.decision = decision
	return port.CreateResult{Decision: decision}, f.createErr
}

func (f *preferenceScheduleFake) AppendEvent(_ context.Context, event reminder.ReminderEvent) error {
	if event.EventName == "reminder_preference_updated" {
		f.preferenceEvent = event
	} else {
		f.decisionEvent = event
	}
	return nil
}

func (f *preferenceScheduleFake) CancelPendingSchedules(context.Context, string, string, reminder.ReasonCode, time.Time) error {
	f.cancelled++
	return f.cancelErr
}

var _ port.PreferenceScheduleRepository = (*preferenceScheduleFake)(nil)

func preferenceService(repository port.ReminderRepository, preference reminder.ReminderPreference) Service {
	now := time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC)
	return Service{
		Tasks:       taskFake{task: reminder.DailyTask{UserID: "u1", TaskDate: "2026-09-20", RequiredCount: 2, CompletedCount: 1, Deadline: now.Add(5 * time.Hour)}},
		Preferences: preferenceFake{preference: preference},
		Behaviors:   behaviorFake{behavior: reminder.BehaviorSummary{HistoryDaysAvailable: 7}},
		Reminders:   repository,
		Clock:       fixedClock{now: now},
	}
}

func TestPreferenceChangedHandlerDisablesPendingSchedule(t *testing.T) {
	repository := &preferenceScheduleFake{}
	service := preferenceService(repository, reminder.ReminderPreference{PushEnabled: true, Timezone: "UTC"})
	handler := PreferenceChangedHandler{Service: service}
	result, err := handler.Handle(context.Background(), PreferenceChangedEvent{
		EventID: "pref-1", UserID: "u1", TaskDate: "2026-09-20", Timezone: "UTC",
		ReminderEnabled: false, ChangedFields: []string{"reminder_enabled"},
	})
	if err != nil {
		t.Fatalf("handle preference change: %v", err)
	}
	if result.Decision.ShouldRemind || result.Decision.ReasonCode != reminder.ReasonReminderDisabled {
		t.Fatalf("expected disabled decision, got %+v", result.Decision)
	}
	if repository.cancelled != 1 {
		t.Fatalf("expected one pending schedule cancellation, got %d", repository.cancelled)
	}
	if repository.preferenceEvent.EventName != "reminder_preference_updated" || repository.preferenceEvent.DecisionID != "" {
		t.Fatalf("unexpected preference event: %+v", repository.preferenceEvent)
	}
	if repository.decisionEvent.EventName != "reminder_decision_created" {
		t.Fatalf("expected decision event, got %+v", repository.decisionEvent)
	}
}

func TestPreferenceChangedHandlerUsesLatestSettingForReschedule(t *testing.T) {
	repository := &preferenceScheduleFake{}
	service := preferenceService(repository, reminder.ReminderPreference{ReminderEnabled: true, PushEnabled: true, QuietHoursStart: "18:00", QuietHoursEnd: "20:00", Timezone: "UTC"})
	result, err := (PreferenceChangedHandler{Service: service}).Handle(context.Background(), PreferenceChangedEvent{
		EventID: "pref-2", UserID: "u1", TaskDate: "2026-09-20", Timezone: "UTC",
		ReminderEnabled: true, QuietHoursStart: "18:00", QuietHoursEnd: "20:00", ChangedFields: []string{"quiet_hours_start", "quiet_hours_end"},
	})
	if err != nil {
		t.Fatalf("handle preference change: %v", err)
	}
	if !result.Decision.ShouldRemind || result.Decision.ScheduledAt == nil {
		t.Fatalf("expected rescheduled decision, got %+v", result.Decision)
	}
	want := time.Date(2026, 9, 20, 17, 0, 0, 0, time.UTC)
	if !result.Decision.ScheduledAt.Equal(want) {
		t.Fatalf("expected quiet-hours fallback at %s, got %s", want, result.Decision.ScheduledAt)
	}
	if repository.cancelled != 0 {
		t.Fatalf("enabled setting must not cancel schedules, got %d", repository.cancelled)
	}
}

func TestPreferenceChangedHandlerDoesNotMutateAfterPreferenceReadFailure(t *testing.T) {
	repository := &preferenceScheduleFake{}
	service := preferenceService(repository, reminder.ReminderPreference{})
	service.Preferences = preferenceFake{err: errors.New("preference unavailable")}
	_, err := (PreferenceChangedHandler{Service: service}).Handle(context.Background(), PreferenceChangedEvent{
		EventID: "pref-3", UserID: "u1", TaskDate: "2026-09-20",
	})
	if err == nil {
		t.Fatal("expected preference read error")
	}
	if repository.cancelled != 0 || repository.decision.ID != "" {
		t.Fatalf("preference read failure mutated state: cancelled=%d decision=%+v", repository.cancelled, repository.decision)
	}
	if repository.preferenceEvent.EventName != "reminder_preference_updated" {
		t.Fatalf("expected audit event despite evaluation failure, got %+v", repository.preferenceEvent)
	}
}

func TestPreferenceChangedHandlerRejectsInvalidEventAndPropagatesCancellationFailure(t *testing.T) {
	repository := &preferenceScheduleFake{cancelErr: errors.New("cancel failed")}
	service := preferenceService(repository, reminder.ReminderPreference{PushEnabled: true, Timezone: "UTC"})
	handler := PreferenceChangedHandler{Service: service}
	if _, err := handler.Handle(context.Background(), PreferenceChangedEvent{UserID: "u1", TaskDate: "2026-09-20"}); err == nil {
		t.Fatal("expected invalid event error")
	}
	_, err := handler.Handle(context.Background(), PreferenceChangedEvent{EventID: "pref-4", UserID: "u1", TaskDate: "2026-09-20"})
	if err == nil {
		t.Fatal("expected cancellation error")
	}
}
