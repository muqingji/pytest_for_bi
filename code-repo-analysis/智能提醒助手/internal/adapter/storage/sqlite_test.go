package storage

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

func TestStoreMigratesAndKeepsDecisionIdempotent(t *testing.T) {
	store, err := Open(filepath.Join(t.TempDir(), "reminder.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer store.Close()
	ctx := context.Background()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	now := time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC)
	decision := reminder.Decision{
		ID: "decision-1", UserID: "u1", TaskDate: "2026-09-20", ShouldRemind: true,
		Channel: reminder.ChannelPush, ReasonCode: reminder.ReasonEligible, StrategyVersion: "v1",
		UserSegment: reminder.SegmentPassive, DedupeKey: "u1|2026-09-20|v1",
		Status: reminder.DecisionScheduled, Version: 1, CreatedAt: now, UpdatedAt: now,
	}
	schedule := &reminder.Schedule{
		ID: "schedule-1", DecisionID: decision.ID, UserID: decision.UserID, TaskDate: decision.TaskDate,
		ScheduleVersion: 1, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleInitial,
		ScheduledAt: now.Add(time.Hour), Status: reminder.ScheduleScheduled, CreatedAt: now, UpdatedAt: now,
	}
	first, err := store.CreateDecisionAndSchedule(ctx, decision, schedule)
	if err != nil || first.Reused {
		t.Fatalf("first create: result=%+v err=%v", first, err)
	}
	second, err := store.CreateDecisionAndSchedule(ctx, decision, schedule)
	if err != nil || !second.Reused || second.Decision.ID != decision.ID {
		t.Fatalf("duplicate create: result=%+v err=%v", second, err)
	}
	usage, err := store.GetDailyUsage(ctx, decision.UserID, decision.TaskDate)
	if err != nil {
		t.Fatalf("usage: %v", err)
	}
	if usage != (reminder.DailyUsage{}) {
		t.Fatalf("unexpected usage before delivery: %+v", usage)
	}
}

func TestStoreDeduplicatesEvents(t *testing.T) {
	store, err := Open(filepath.Join(t.TempDir(), "reminder.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer store.Close()
	ctx := context.Background()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	now := time.Now().UTC()
	decision := reminder.Decision{ID: "decision-1", UserID: "u1", TaskDate: "2026-09-20", ShouldRemind: false, ReasonCode: reminder.ReasonTaskCompleted, StrategyVersion: "v1", UserSegment: reminder.SegmentSelfDriven, DedupeKey: "u1|2026-09-20|v1", Status: reminder.DecisionCancelled, Version: 1, CreatedAt: now, UpdatedAt: now}
	if _, err := store.CreateDecisionAndSchedule(ctx, decision, nil); err != nil {
		t.Fatalf("create decision: %v", err)
	}
	event := reminder.ReminderEvent{EventID: "event-1", EventName: "reminder_decision_created", DecisionID: decision.ID, UserID: decision.UserID, TaskDate: decision.TaskDate, EventTime: now, StrategyVersion: decision.StrategyVersion, Payload: map[string]any{"should_remind": false}}
	if err := store.AppendEvent(ctx, event); err != nil {
		t.Fatalf("append event: %v", err)
	}
	if err := store.AppendEvent(ctx, event); err != nil {
		t.Fatalf("append duplicate event: %v", err)
	}
	var count int
	if err := store.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM reminder_event WHERE event_id = ?`, event.EventID).Scan(&count); err != nil {
		t.Fatalf("count events: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected one event, got %d", count)
	}
}

func TestStoreCancelsPendingDecisionWhenReturningUserEntersCooldown(t *testing.T) {
	store, err := Open(filepath.Join(t.TempDir(), "reminder.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer store.Close()
	ctx := context.Background()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	now := time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC)
	initial := reminder.Decision{
		ID: "decision-1", UserID: "u1", TaskDate: "2026-09-20", ShouldRemind: true,
		Channel: reminder.ChannelPush, ReasonCode: reminder.ReasonEligible, StrategyVersion: "v1", UserSegment: reminder.SegmentPassive,
		DedupeKey: "u1|2026-09-20|v1", Status: reminder.DecisionScheduled, Version: 1,
		CreatedAt: now, UpdatedAt: now,
	}
	initialSchedule := &reminder.Schedule{
		ID: "schedule-1", DecisionID: initial.ID, UserID: initial.UserID, TaskDate: initial.TaskDate,
		ScheduleVersion: 1, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleInitial,
		ScheduledAt: now.Add(time.Hour), Status: reminder.ScheduleScheduled, CreatedAt: now, UpdatedAt: now,
	}
	if _, err := store.CreateDecisionAndSchedule(ctx, initial, initialSchedule); err != nil {
		t.Fatalf("create initial decision: %v", err)
	}

	returningAt := now.Add(time.Hour)
	returning := initial
	returning.ShouldRemind = false
	returning.ScheduledAt = nil
	returning.Channel = ""
	returning.ReasonCode = reminder.ReasonReturningFirstDay
	returning.UserSegment = reminder.SegmentReturning
	returning.Status = reminder.DecisionCancelled
	returning.UpdatedAt = returningAt
	result, err := store.CreateDecisionAndSchedule(ctx, returning, nil)
	if err != nil {
		t.Fatalf("replace returning decision: %v", err)
	}
	if result.Reused || result.Decision.Version != 2 || result.Decision.ShouldRemind {
		t.Fatalf("expected cooldown decision version 2, got %+v reused=%v", result.Decision, result.Reused)
	}

	var reason, channel, status string
	var scheduleCount int
	if err := store.db.QueryRowContext(ctx, `SELECT reason_code, channel, status FROM reminder_decision WHERE id = ?`, initial.ID).Scan(&reason, &channel, &status); err != nil {
		t.Fatalf("read updated decision: %v", err)
	}
	if err := store.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM reminder_schedule WHERE decision_id = ? AND status = 'SCHEDULED'`, initial.ID).Scan(&scheduleCount); err != nil {
		t.Fatalf("count schedules: %v", err)
	}
	if reason != string(reminder.ReasonReturningFirstDay) || channel != "" || status != string(reminder.DecisionCancelled) || scheduleCount != 0 {
		t.Fatalf("unexpected returning state: reason=%s channel=%s status=%s schedules=%d", reason, channel, status, scheduleCount)
	}
}
