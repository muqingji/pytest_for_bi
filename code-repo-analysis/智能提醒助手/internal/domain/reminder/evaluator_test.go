package reminder

import (
	"testing"
	"time"
)

func TestEvaluatePassiveUserCreatesPushSchedule(t *testing.T) {
	now := time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC)
	plan := Evaluate(EvaluationInput{
		Now: now, Trigger: TriggerDaily,
		Task:       DailyTask{UserID: "u1", TaskDate: "2026-09-20", RequiredCount: 5, CompletedCount: 2, Deadline: now.Add(4 * time.Hour)},
		Preference: ReminderPreference{Enabled: true, PushEnabled: true, DailyPushCap: 1, Timezone: time.UTC},
		Behavior:   BehaviorSummary{HistoryDaysAvailable: 7, InactiveDays: 0},
		Usage:      DailyUsage{}, StrategyVersion: "v1",
	})
	if !plan.Decision.ShouldRemind || plan.Decision.Channel != ChannelPush {
		t.Fatalf("expected push reminder, got %+v", plan.Decision)
	}
	if plan.Schedule == nil || plan.Schedule.Status != ScheduleScheduled {
		t.Fatalf("expected scheduled push, got %+v", plan.Schedule)
	}
}

func TestEvaluateDecisionBoundaries(t *testing.T) {
	now := time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC)
	base := EvaluationInput{
		Now: now, Trigger: TriggerDaily,
		Task:       DailyTask{UserID: "u1", TaskDate: "2026-09-20", RequiredCount: 5, CompletedCount: 2, Deadline: now.Add(time.Hour)},
		Preference: ReminderPreference{Enabled: true, PushEnabled: true, DailyPushCap: 1, Timezone: time.UTC},
		Behavior:   BehaviorSummary{HistoryDaysAvailable: 7}, Usage: DailyUsage{}, StrategyVersion: "v1",
	}
	tests := []struct {
		name   string
		mutate func(*EvaluationInput)
		reason ReasonCode
	}{
		{"no task", func(in *EvaluationInput) { in.Task.RequiredCount = 0 }, ReasonNoTask},
		{"completed", func(in *EvaluationInput) { in.Task.CompletedCount = 5 }, ReasonTaskCompleted},
		{"expired", func(in *EvaluationInput) { in.Now = in.Task.Deadline.Add(time.Second) }, ReasonTaskExpired},
		{"disabled", func(in *EvaluationInput) { in.Preference.Enabled = false }, ReasonReminderDisabled},
		{"inactive", func(in *EvaluationInput) { in.Behavior.InactiveDays = 3 }, ReasonUserInactive},
		{"daily cap", func(in *EvaluationInput) { in.Usage.PushSentCount = 1 }, ReasonDailyCapReached},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			input := base
			test.mutate(&input)
			plan := Evaluate(input)
			if plan.Decision.ShouldRemind || plan.Decision.ReasonCode != test.reason || plan.Schedule != nil {
				t.Fatalf("unexpected plan: %+v", plan)
			}
		})
	}
}

func TestEvaluateHistoryReturningAndSelfDrivenRules(t *testing.T) {
	now := time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC)
	base := EvaluationInput{
		Now: now, Trigger: TriggerDaily,
		Task:       DailyTask{UserID: "u1", TaskDate: "2026-09-20", RequiredCount: 5, CompletedCount: 2, Deadline: now.Add(4 * time.Hour)},
		Preference: ReminderPreference{Enabled: true, PushEnabled: true, DailyPushCap: 1, Timezone: time.UTC},
		Behavior:   BehaviorSummary{HistoryDaysAvailable: 2}, Usage: DailyUsage{}, StrategyVersion: "v1",
	}
	historyPlan := Evaluate(base)
	if historyPlan.Decision.ReasonCode != ReasonInsufficientHistory || !historyPlan.Decision.ShouldRemind {
		t.Fatalf("expected insufficient history fallback, got %+v", historyPlan.Decision)
	}

	days := 3
	base.Trigger = TriggerAppOpen
	base.Behavior = BehaviorSummary{HistoryDaysAvailable: 7, InactiveDays: 0, DaysSinceLastOpen: &days}
	returningPlan := Evaluate(base)
	if returningPlan.Decision.ReasonCode != ReasonReturningFirstDay || returningPlan.Decision.UserSegment != SegmentReturning || returningPlan.Decision.ShouldRemind || returningPlan.Schedule != nil {
		t.Fatalf("expected returning cooldown with no schedule, got %+v", returningPlan)
	}

	base.Trigger = TriggerDaily
	base.Behavior = BehaviorSummary{HistoryDaysAvailable: 7, CompleteDays7D: 5, ReminderAttributedComplete7D: 1}
	selfDrivenPlan := Evaluate(base)
	if selfDrivenPlan.Decision.UserSegment != SegmentSelfDriven || !selfDrivenPlan.Decision.ShouldRemind {
		t.Fatalf("expected low-disturbance self-driven plan, got %+v", selfDrivenPlan.Decision)
	}
}
