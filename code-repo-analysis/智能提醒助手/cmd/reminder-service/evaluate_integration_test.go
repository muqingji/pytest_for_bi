package main

import (
	"context"
	"database/sql"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

// 本文件是 FR-004 评估路径的模块集成测试：真实 SQLite + 真实评估用例。
// 断言决策拒绝时取消未发送排程、保留 CANCELLED 行作为历史，并逐条发布 reminder_cancelled。

func TestEvaluateIntegrationCancelsPendingScheduleWhenTaskCompleted(t *testing.T) {
	path := filepath.Join(t.TempDir(), "evaluate-cancel.db")
	now := time.Now().UTC()
	taskDate := todayTaskDate()
	store := openIntegrationStore(t, path, seededSchedule{id: "schedule-1", scheduledAt: now.Add(time.Hour)})
	defer func() { _ = store.Close() }()

	users := fixtureUsers("user-passive")
	service := evaluate.Service{
		Tasks:       completedTasks("user-passive", taskDate),
		Preferences: users,
		Behaviors:   users,
		Reminders:   store,
		Clock:       systemClock{},
	}
	result, err := service.Evaluate(context.Background(), evaluate.Request{UserID: "user-passive", TaskDate: taskDate})
	if err != nil {
		t.Fatalf("evaluate: %v", err)
	}
	if result.Decision.ReasonCode != reminder.ReasonTaskCompleted || result.Decision.ShouldRemind {
		t.Fatalf("expected a task-completed rejection: %+v", result.Decision)
	}

	var status, cancelReason string
	if err := directQueryRow(t, path, `SELECT status, cancel_reason FROM reminder_schedule WHERE id = ?`, []any{"schedule-1"}, func(row *sql.Row) error {
		return row.Scan(&status, &cancelReason)
	}); err != nil {
		t.Fatalf("read cancelled schedule: %v", err)
	}
	if status != string(reminder.ScheduleCancelled) || cancelReason != string(reminder.ReasonTaskCompleted) {
		t.Fatalf("cancelled row must be kept as history: status=%s reason=%s", status, cancelReason)
	}

	var payload string
	var eventCount, scheduleCount int
	if err := directQueryRow(t, path, `SELECT COUNT(*) FROM reminder_event WHERE event_name = ?`, []any{"reminder_cancelled"}, func(row *sql.Row) error {
		return row.Scan(&eventCount)
	}); err != nil {
		t.Fatalf("count cancellation events: %v", err)
	}
	if eventCount != 1 {
		t.Fatalf("expected exactly one cancellation event: %d", eventCount)
	}
	if err := directQueryRow(t, path, `SELECT payload FROM reminder_event WHERE event_name = ?`, []any{"reminder_cancelled"}, func(row *sql.Row) error {
		return row.Scan(&payload)
	}); err != nil {
		t.Fatalf("read cancellation payload: %v", err)
	}
	if !containsAll(payload, `"cancel_reason":"TASK_COMPLETED"`, `"previous_status":"SCHEDULED"`) {
		t.Fatalf("unexpected cancellation payload: %s", payload)
	}
	if err := directQueryRow(t, path, `SELECT COUNT(*) FROM reminder_schedule`, nil, func(row *sql.Row) error {
		return row.Scan(&scheduleCount)
	}); err != nil {
		t.Fatalf("count schedules: %v", err)
	}
	if scheduleCount != 1 {
		t.Fatalf("cancellation must keep the historical row: %d", scheduleCount)
	}

	// AC-006 同口径：重复评估命中已有决策时不重复取消、不重复发布事件。
	reused, err := service.Evaluate(context.Background(), evaluate.Request{UserID: "user-passive", TaskDate: taskDate})
	if err != nil || !reused.Reused {
		t.Fatalf("expected idempotent re-evaluation: result=%+v err=%v", reused, err)
	}
	if err := directQueryRow(t, path, `SELECT COUNT(*) FROM reminder_event WHERE event_name = ?`, []any{"reminder_cancelled"}, func(row *sql.Row) error {
		return row.Scan(&eventCount)
	}); err != nil {
		t.Fatalf("recount cancellation events: %v", err)
	}
	if eventCount != 1 {
		t.Fatalf("repeated evaluation must not repeat the cancellation event: %d", eventCount)
	}
}

func containsAll(value string, fragments ...string) bool {
	for _, fragment := range fragments {
		if !strings.Contains(value, fragment) {
			return false
		}
	}
	return true
}
