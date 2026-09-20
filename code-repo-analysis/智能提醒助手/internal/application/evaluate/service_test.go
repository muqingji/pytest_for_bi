package evaluate

import (
	"context"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

type fixedClock struct{ now time.Time }

func (c fixedClock) Now() time.Time { return c.now }

type taskFake struct{ task reminder.DailyTask }

func (f taskFake) GetDailyTask(context.Context, string, string) (reminder.DailyTask, error) {
	return f.task, nil
}

type preferenceFake struct{ preference reminder.ReminderPreference }

func (f preferenceFake) Get(context.Context, string) (reminder.ReminderPreference, error) {
	return f.preference, nil
}

type behaviorFake struct{ behavior reminder.BehaviorSummary }

func (f behaviorFake) GetRecent(context.Context, string, int) (reminder.BehaviorSummary, error) {
	return f.behavior, nil
}

type reminderFake struct {
	usage    reminder.DailyUsage
	decision reminder.Decision
	event    reminder.ReminderEvent
}

func (f *reminderFake) GetDailyUsage(context.Context, string, string) (reminder.DailyUsage, error) {
	return f.usage, nil
}

func (f *reminderFake) CreateDecisionAndSchedule(_ context.Context, decision reminder.Decision, _ *reminder.Schedule) (port.CreateResult, error) {
	f.decision = decision
	return port.CreateResult{Decision: decision}, nil
}

func (f *reminderFake) AppendEvent(_ context.Context, event reminder.ReminderEvent) error {
	f.event = event
	return nil
}

func TestServicePersistsDecisionAndEvent(t *testing.T) {
	now := time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC)
	repository := &reminderFake{}
	service := Service{
		Tasks:           taskFake{task: reminder.DailyTask{UserID: "u1", TaskDate: "2026-09-20", RequiredCount: 3, CompletedCount: 1, Deadline: now.Add(4 * time.Hour)}},
		Preferences:     preferenceFake{preference: reminder.ReminderPreference{Enabled: true, PushEnabled: true, DailyPushCap: 1, Timezone: time.UTC}},
		Behaviors:       behaviorFake{behavior: reminder.BehaviorSummary{HistoryDaysAvailable: 7}},
		Reminders:       repository,
		Clock:           fixedClock{now: now},
		StrategyVersion: "v1",
	}
	result, err := service.Evaluate(context.Background(), Request{UserID: "u1", TaskDate: "2026-09-20"})
	if err != nil {
		t.Fatalf("evaluate: %v", err)
	}
	if !result.Decision.ShouldRemind || repository.event.EventName != "reminder_decision_created" {
		t.Fatalf("unexpected result: %+v event=%+v", result.Decision, repository.event)
	}
}
