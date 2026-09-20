package storage

import (
	"context"
	"database/sql"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
	_ "modernc.org/sqlite"
)

//go:embed migrations/001_initial.up.sql
var migrationFS embed.FS

type Store struct {
	db *sql.DB
}

func Open(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}
	db.SetMaxOpenConns(1)
	return &Store{db: db}, nil
}

func (s *Store) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

func (s *Store) Migrate(ctx context.Context) error {
	if _, err := s.db.ExecContext(ctx, `CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)`); err != nil {
		return fmt.Errorf("create migration table: %w", err)
	}
	var version int
	if err := s.db.QueryRowContext(ctx, `SELECT COALESCE(MAX(version), 0) FROM schema_migrations`).Scan(&version); err != nil {
		return fmt.Errorf("read migration version: %w", err)
	}
	if version >= 1 {
		return nil
	}
	sqlText, err := migrationFS.ReadFile("migrations/001_initial.up.sql")
	if err != nil {
		return fmt.Errorf("read migration: %w", err)
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin migration: %w", err)
	}
	if _, err := tx.ExecContext(ctx, string(sqlText)); err != nil {
		_ = tx.Rollback()
		return fmt.Errorf("apply migration: %w", err)
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO schema_migrations(version, applied_at) VALUES(1, ?)`, time.Now().UTC().Format(time.RFC3339Nano)); err != nil {
		_ = tx.Rollback()
		return fmt.Errorf("record migration: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit migration: %w", err)
	}
	return nil
}

func (s *Store) GetDailyUsage(ctx context.Context, userID, taskDate string) (reminder.DailyUsage, error) {
	const query = `
SELECT
  COALESCE(SUM(CASE WHEN d.channel = 'push' AND rd.status IN ('SENT', 'DELIVERED') THEN 1 ELSE 0 END), 0)
FROM reminder_delivery rd
JOIN reminder_decision d ON d.id = rd.decision_id
WHERE d.user_id = ? AND d.task_date = ?`
	var usage reminder.DailyUsage
	if err := s.db.QueryRowContext(ctx, query, userID, taskDate).Scan(&usage.PushSentCount); err != nil {
		return reminder.DailyUsage{}, fmt.Errorf("query daily usage: %w", err)
	}
	return usage, nil
}

func (s *Store) CreateDecisionAndSchedule(ctx context.Context, decision reminder.Decision, schedule *reminder.Schedule) (port.CreateResult, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return port.CreateResult{}, fmt.Errorf("begin decision transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	var existing reminder.Decision
	err = scanDecision(tx.QueryRowContext(ctx, `SELECT id, user_id, task_date, should_remind, scheduled_at, channel, reason_code, strategy_version, user_segment, dedupe_key, status, version, created_at, updated_at FROM reminder_decision WHERE user_id = ? AND task_date = ? AND strategy_version = ?`, decision.UserID, decision.TaskDate, decision.StrategyVersion), &existing)
	if err == nil {
		if sameDecision(existing, decision) {
			return port.CreateResult{Decision: existing, Reused: true}, nil
		}
		decision.ID = existing.ID
		decision.Version = existing.Version + 1
		decision.CreatedAt = existing.CreatedAt
		if _, err := tx.ExecContext(ctx, `UPDATE reminder_decision SET should_remind = ?, scheduled_at = ?, channel = ?, reason_code = ?, user_segment = ?, dedupe_key = ?, status = ?, version = ?, updated_at = ? WHERE id = ?`,
			boolInt(decision.ShouldRemind), nullableTime(decision.ScheduledAt), string(decision.Channel), string(decision.ReasonCode), string(decision.UserSegment), decision.DedupeKey, string(decision.Status), decision.Version, decision.UpdatedAt.UTC().Format(time.RFC3339Nano), decision.ID); err != nil {
			return port.CreateResult{}, fmt.Errorf("update decision: %w", err)
		}
		if _, err := tx.ExecContext(ctx, `DELETE FROM reminder_schedule WHERE decision_id = ? AND status = 'SCHEDULED'`, decision.ID); err != nil {
			return port.CreateResult{}, fmt.Errorf("replace pending schedule: %w", err)
		}
		if schedule != nil && decision.ShouldRemind {
			schedule.DecisionID = decision.ID
			if _, err := tx.ExecContext(ctx, `INSERT INTO reminder_schedule (id, decision_id, user_id, task_date, schedule_version, channel, schedule_type, scheduled_at, status, attempt_no, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
				schedule.ID, schedule.DecisionID, schedule.UserID, schedule.TaskDate, schedule.ScheduleVersion, string(schedule.Channel), string(schedule.ScheduleType), schedule.ScheduledAt.UTC().Format(time.RFC3339Nano), string(schedule.Status), schedule.AttemptNo, schedule.CreatedAt.UTC().Format(time.RFC3339Nano), schedule.UpdatedAt.UTC().Format(time.RFC3339Nano)); err != nil {
				return port.CreateResult{}, fmt.Errorf("insert replacement schedule: %w", err)
			}
		}
		if err := tx.Commit(); err != nil {
			return port.CreateResult{}, fmt.Errorf("commit updated decision: %w", err)
		}
		return port.CreateResult{Decision: decision}, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return port.CreateResult{}, fmt.Errorf("query existing decision: %w", err)
	}

	if _, err := tx.ExecContext(ctx, `INSERT INTO reminder_decision (id, user_id, task_date, should_remind, scheduled_at, channel, reason_code, strategy_version, user_segment, dedupe_key, status, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		decision.ID, decision.UserID, decision.TaskDate, boolInt(decision.ShouldRemind), nullableTime(decision.ScheduledAt), string(decision.Channel), string(decision.ReasonCode), decision.StrategyVersion, string(decision.UserSegment), decision.DedupeKey, string(decision.Status), decision.Version, decision.CreatedAt.UTC().Format(time.RFC3339Nano), decision.UpdatedAt.UTC().Format(time.RFC3339Nano)); err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "unique") {
			_ = tx.Rollback()
			return s.readExistingAfterConflict(ctx, decision)
		}
		return port.CreateResult{}, fmt.Errorf("insert decision: %w", err)
	}
	if schedule != nil && decision.ShouldRemind {
		if _, err := tx.ExecContext(ctx, `INSERT INTO reminder_schedule (id, decision_id, user_id, task_date, schedule_version, channel, schedule_type, scheduled_at, status, attempt_no, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			schedule.ID, schedule.DecisionID, schedule.UserID, schedule.TaskDate, schedule.ScheduleVersion, string(schedule.Channel), string(schedule.ScheduleType), schedule.ScheduledAt.UTC().Format(time.RFC3339Nano), string(schedule.Status), schedule.AttemptNo, schedule.CreatedAt.UTC().Format(time.RFC3339Nano), schedule.UpdatedAt.UTC().Format(time.RFC3339Nano)); err != nil {
			return port.CreateResult{}, fmt.Errorf("insert schedule: %w", err)
		}
	}
	if err := tx.Commit(); err != nil {
		return port.CreateResult{}, fmt.Errorf("commit decision transaction: %w", err)
	}
	return port.CreateResult{Decision: decision}, nil
}

func sameDecision(left, right reminder.Decision) bool {
	return left.ShouldRemind == right.ShouldRemind &&
		sameTime(left.ScheduledAt, right.ScheduledAt) &&
		left.Channel == right.Channel &&
		left.ReasonCode == right.ReasonCode &&
		left.UserSegment == right.UserSegment &&
		left.Status == right.Status
}

func sameTime(left, right *time.Time) bool {
	if left == nil || right == nil {
		return left == right
	}
	return left.Equal(*right)
}

func (s *Store) readExistingAfterConflict(ctx context.Context, decision reminder.Decision) (port.CreateResult, error) {
	var existing reminder.Decision
	err := scanDecision(s.db.QueryRowContext(ctx, `SELECT id, user_id, task_date, should_remind, scheduled_at, channel, reason_code, strategy_version, user_segment, dedupe_key, status, version, created_at, updated_at FROM reminder_decision WHERE user_id = ? AND task_date = ? AND strategy_version = ?`, decision.UserID, decision.TaskDate, decision.StrategyVersion), &existing)
	if err != nil {
		return port.CreateResult{}, fmt.Errorf("read decision after conflict: %w", err)
	}
	return port.CreateResult{Decision: existing, Reused: true}, nil
}

func (s *Store) AppendEvent(ctx context.Context, event reminder.ReminderEvent) error {
	payload, err := json.Marshal(event.Payload)
	if err != nil {
		return fmt.Errorf("marshal event payload: %w", err)
	}
	_, err = s.db.ExecContext(ctx, `INSERT OR IGNORE INTO reminder_event (event_id, event_name, decision_id, user_id, task_date, event_time, strategy_version, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`, event.EventID, event.EventName, event.DecisionID, event.UserID, event.TaskDate, event.EventTime.UTC().Format(time.RFC3339Nano), event.StrategyVersion, string(payload))
	if err != nil {
		return fmt.Errorf("insert event: %w", err)
	}
	return nil
}

func scanDecision(row interface{ Scan(...any) error }, decision *reminder.Decision) error {
	var shouldRemind int
	var scheduledAt sql.NullString
	var channel, reason, strategy, segment, status, createdAt, updatedAt string
	if err := row.Scan(&decision.ID, &decision.UserID, &decision.TaskDate, &shouldRemind, &scheduledAt, &channel, &reason, &strategy, &segment, &decision.DedupeKey, &status, &decision.Version, &createdAt, &updatedAt); err != nil {
		return err
	}
	decision.ShouldRemind = shouldRemind == 1
	decision.Channel = reminder.Channel(channel)
	decision.ReasonCode = reminder.ReasonCode(reason)
	decision.StrategyVersion = strategy
	decision.UserSegment = reminder.Segment(segment)
	decision.Status = reminder.DecisionStatus(status)
	decision.CreatedAt, _ = time.Parse(time.RFC3339Nano, createdAt)
	decision.UpdatedAt, _ = time.Parse(time.RFC3339Nano, updatedAt)
	if scheduledAt.Valid {
		parsed, err := time.Parse(time.RFC3339Nano, scheduledAt.String)
		if err != nil {
			return fmt.Errorf("parse scheduled_at: %w", err)
		}
		decision.ScheduledAt = &parsed
	}
	return nil
}

func boolInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func nullableTime(value *time.Time) any {
	if value == nil {
		return nil
	}
	return value.UTC().Format(time.RFC3339Nano)
}

var _ port.ReminderRepository = (*Store)(nil)
