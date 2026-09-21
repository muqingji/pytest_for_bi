package main

import (
	"context"
	"database/sql"
	"path/filepath"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/application/evaluate"
)

func TestZZDebugCancelChain(t *testing.T) {
	path := filepath.Join(t.TempDir(), "debug.db")
	now := time.Now().UTC()
	taskDate := now.Format("2006-01-02")
	store := openIntegrationStore(t, path, seededSchedule{id: "schedule-1", scheduledAt: now.Add(time.Hour)})
	defer func() { _ = store.Close() }()
	users := fixtureUsers("user-passive")
	result, _ := evaluate.Service{
		Tasks: completedTasks("user-passive", taskDate), Preferences: users, Behaviors: users,
		Reminders: store, Clock: systemClock{}, StrategyVersion: "v1",
	}.Evaluate(context.Background(), evaluate.Request{UserID: "user-passive", TaskDate: taskDate})
	t.Logf("returned decision id=%s reuse=%v reason=%s", result.Decision.ID, result.Reused, result.Decision.ReasonCode)
	_ = directQueryRow(t, path, `SELECT id FROM reminder_decision`, nil, func(row *sql.Row) error {
		var id string
		err := row.Scan(&id)
		t.Logf("persisted decision row: %s", id)
		return err
	})
	_ = directQueryRow(t, path, `SELECT event_name || ' @ ' || decision_id || ' | ' || strategy_version FROM reminder_event`, nil, func(row *sql.Row) error {
		var line string
		err := row.Scan(&line)
		t.Logf("event: %s", line)
		return err
	})
}
