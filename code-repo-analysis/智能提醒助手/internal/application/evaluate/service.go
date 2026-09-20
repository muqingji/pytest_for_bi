package evaluate

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strconv"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

type Request struct {
	UserID   string
	TaskDate string
	Trigger  reminder.Trigger
}

type Service struct {
	Tasks           port.TaskRepository
	Preferences     port.PreferenceRepository
	Behaviors       port.BehaviorRepository
	Reminders       port.ReminderRepository
	Clock           port.Clock
	StrategyVersion string
}

type Result struct {
	Decision reminder.Decision
	Reused   bool
}

func (s Service) Evaluate(ctx context.Context, request Request) (Result, error) {
	if request.UserID == "" || request.TaskDate == "" {
		return Result{}, fmt.Errorf("user_id and task_date are required")
	}
	if request.Trigger == "" {
		request.Trigger = reminder.TriggerDaily
	}
	now := s.Clock.Now()
	task, err := s.Tasks.GetDailyTask(ctx, request.UserID, request.TaskDate)
	if err != nil {
		return Result{}, fmt.Errorf("read daily task: %w", err)
	}
	preference, err := s.Preferences.Get(ctx, request.UserID)
	if err != nil {
		return Result{}, fmt.Errorf("read reminder preference: %w", err)
	}
	behavior, err := s.Behaviors.GetRecent(ctx, request.UserID, 7)
	if err != nil {
		// Behavior is a weak dependency. Missing history must not turn a
		// potentially eligible user into a hard dependency failure.
		behavior = reminder.BehaviorSummary{HistoryDaysAvailable: 0}
	}
	usage, err := s.Reminders.GetDailyUsage(ctx, request.UserID, request.TaskDate)
	if err != nil {
		return Result{}, fmt.Errorf("read daily usage: %w", err)
	}

	plan := reminder.Evaluate(reminder.EvaluationInput{
		Now:             now,
		Trigger:         request.Trigger,
		Task:            task,
		Preference:      preference,
		Behavior:        behavior,
		Usage:           usage,
		StrategyVersion: s.StrategyVersion,
	})
	decision := plan.Decision
	decision.ID = stableID("decision", decision.DedupeKey)
	if plan.Schedule != nil {
		plan.Schedule.DecisionID = decision.ID
		plan.Schedule.ID = stableID("schedule", decision.ID+"|1")
	}
	created, err := s.Reminders.CreateDecisionAndSchedule(ctx, decision, plan.Schedule)
	if err != nil {
		return Result{}, fmt.Errorf("persist reminder decision: %w", err)
	}
	if created.Reused {
		return Result{Decision: created.Decision, Reused: true}, nil
	}
	persisted := created.Decision
	event := reminder.ReminderEvent{
		EventID:         stableID("event", persisted.ID+"|"+strconv.Itoa(persisted.Version)+"|reminder_decision_created"),
		EventName:       "reminder_decision_created",
		DecisionID:      persisted.ID,
		UserID:          persisted.UserID,
		TaskDate:        persisted.TaskDate,
		EventTime:       now,
		StrategyVersion: persisted.StrategyVersion,
		Payload: map[string]any{
			"should_remind":   persisted.ShouldRemind,
			"reason_code":     string(persisted.ReasonCode),
			"user_segment":    string(persisted.UserSegment),
			"decision_source": string(request.Trigger),
		},
	}
	if err := s.Reminders.AppendEvent(ctx, event); err != nil {
		return Result{}, fmt.Errorf("append decision event: %w", err)
	}
	return Result{Decision: decision}, nil
}

func stableID(prefix, value string) string {
	sum := sha256.Sum256([]byte(value))
	return prefix + "-" + hex.EncodeToString(sum[:16])
}
