package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/adapter/channel"
	"intelligent-reminder-assistant/internal/adapter/storage"
	"intelligent-reminder-assistant/internal/adapter/task"
	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/application/snooze"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

// 本文件是 FR-007 的模块集成测试：真实 SQLite + 真实应用装配（CLI 入口或进程内用例）。
// 覆盖延后排程落库、幂等重放、第二次入口、资源不可用统一口径、频控合计上限与事件关联。

type fixedClock struct{ now time.Time }

func (c fixedClock) Now() time.Time { return c.now }

// snoozeServiceFor 用固定时钟装配延后用例，保证「一小时后」与免打扰判定可复现（不必依赖真实运行时刻）。
func snoozeServiceFor(store *storage.Store, now time.Time, _ string) snooze.Service {
	return snooze.Service{
		Reminders:   store,
		Preferences: fixtureUsers("user-passive"),
		Tasks:       integrationTasks("user-passive", todayTaskDate()),
		Clock:       fixedClock{now: now},
	}
}

func TestSnoozeIntegrationSchedulesReusesAndRejects(t *testing.T) {
	path := filepath.Join(t.TempDir(), "snooze.db")
	now := time.Now().UTC()
	store := openIntegrationStore(t, path, seededSchedule{id: "schedule-1", scheduledAt: now.Add(-time.Minute)})
	defer func() { _ = store.Close() }()
	service := snoozeServiceFor(store, now, path)
	ctx := context.Background()

	first, err := service.Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: "decision-1", RequestID: "snooze-1"})
	if err != nil {
		t.Fatalf("snooze: %v", err)
	}
	// AC-013：延后固定安排在一小时后，排程类型为 SNOOZE，延后链条只有一个版本。
	if first.Status != reminder.SnoozeScheduled || first.ScheduleType != reminder.ScheduleSnooze ||
		first.Channel != reminder.ChannelPush || first.SnoozeUntil == nil || !first.SnoozeUntil.Equal(now.Add(reminder.SnoozeDelay)) {
		t.Fatalf("unexpected snooze result: %+v", first)
	}

	var scheduleType, status string
	var version int
	if err := directQueryRow(t, path, `SELECT schedule_type, status, schedule_version FROM reminder_schedule WHERE id = ?`, []any{first.ScheduleID}, func(row *sql.Row) error {
		return row.Scan(&scheduleType, &status, &version)
	}); err != nil {
		t.Fatalf("read snooze schedule: %v", err)
	}
	if scheduleType != string(reminder.ScheduleSnooze) || status != string(reminder.ScheduleScheduled) || version != 2 {
		t.Fatalf("unexpected persisted schedule: type=%s status=%s version=%d", scheduleType, status, version)
	}
	// reminder_snoozed 必须带延后时刻、固定时长与延后前的计划时间，并关联到原 decision。
	var payload string
	var decisionID string
	if err := directQueryRow(t, path, `SELECT decision_id, payload FROM reminder_event WHERE event_name = ?`, []any{"reminder_snoozed"}, func(row *sql.Row) error {
		return row.Scan(&decisionID, &payload)
	}); err != nil {
		t.Fatalf("read snooze event: %v", err)
	}
	if decisionID != "decision-1" {
		t.Fatalf("snooze event must be linked to the decision: %s", decisionID)
	}
	var decoded map[string]any
	if err := json.Unmarshal([]byte(payload), &decoded); err != nil {
		t.Fatalf("decode snooze payload: %v", err)
	}
	if decoded["snooze_duration_minutes"] != float64(reminder.SnoozeDurationMinutes) || decoded["snooze_until"] == nil || decoded["original_scheduled_at"] == nil {
		t.Fatalf("unexpected snooze payload: %v", decoded)
	}

	// 同一 request_id 重复调用：幂等命中，返回原排程，不新增排程与事件。
	replay, err := service.Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: "decision-1", RequestID: "snooze-1"})
	if err != nil || replay.Status != reminder.SnoozeReused || replay.ScheduleID != first.ScheduleID {
		t.Fatalf("expected REUSED with the original schedule: %+v err=%v", replay, err)
	}
	var schedules, events int
	if err := directQueryRow(t, path, `SELECT COUNT(*) FROM reminder_schedule WHERE decision_id = ?`, []any{"decision-1"}, func(row *sql.Row) error {
		return row.Scan(&schedules)
	}); err != nil {
		t.Fatalf("count schedules: %v", err)
	}
	if err := directQueryRow(t, path, `SELECT COUNT(*) FROM reminder_event WHERE event_name = ?`, []any{"reminder_snoozed"}, func(row *sql.Row) error {
		return row.Scan(&events)
	}); err != nil {
		t.Fatalf("count snooze events: %v", err)
	}
	if schedules != 2 || events != 1 {
		t.Fatalf("a replayed request must not create rows: schedules=%d events=%d", schedules, events)
	}

	// 换 request_id 的第二次入口属非法调用（400 INVALID_REQUEST），不产生第三次 Push。
	if _, err := service.Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: "decision-1", RequestID: "snooze-2"}); !errors.Is(err, snooze.ErrInvalidRequest) {
		t.Fatalf("expected INVALID_REQUEST for the second entry: %v", err)
	}

	// 资源不可用统一口径：未知 decision_id 与不属于该 user 的 decision_id 都返回同一拒绝体。
	unknown, err := service.Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: "decision-missing", RequestID: "snooze-3"})
	if err != nil || unknown.Status != reminder.SnoozeRejected || unknown.ReasonCode != reminder.ReasonDecisionNotFound {
		t.Fatalf("expected DECISION_NOT_FOUND for an unknown decision: %+v err=%v", unknown, err)
	}
	foreign, err := service.Snooze(ctx, snooze.Request{UserID: "other-user", DecisionID: "decision-1", RequestID: "snooze-4"})
	if err != nil || foreign.Status != unknown.Status || foreign.ReasonCode != unknown.ReasonCode || foreign.ScheduleID != unknown.ScheduleID {
		t.Fatalf("a foreign decision must be indistinguishable from an unknown one: %+v err=%v", foreign, err)
	}
}

// AC-013：延后 Push 不占当日系统主动上限，但要计入「同一天最多 2 次 Push」的合计口径。
func TestSnoozeIntegrationMetersUsageSeparatelyFromTheSystemCap(t *testing.T) {
	path := filepath.Join(t.TempDir(), "snooze-usage.db")
	now := time.Now().UTC()
	store := openIntegrationStore(t, path, seededSchedule{id: "schedule-1", scheduledAt: now.Add(-time.Minute)})
	defer func() { _ = store.Close() }()
	ctx := context.Background()

	// 先让系统主动 Push 真正发出：当日主动上限已用掉 1 次，但延后仍应成功。
	counts, err := integrationService(store, fixtureUsers("user-passive"), &channel.MockPushSender{}, integrationTasks("user-passive", todayTaskDate())).
		DispatchDue(ctx, dispatch.Request{BatchSize: 50})
	if err != nil || counts.Sent != 1 {
		t.Fatalf("expected one system push to be sent: counts=%+v err=%v", counts, err)
	}
	allowed, err := snoozeServiceFor(store, now, path).Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: "decision-1", RequestID: "snooze-usage-1"})
	if err != nil || allowed.Status != reminder.SnoozeScheduled {
		t.Fatalf("a snooze must not be blocked by the system cap: %+v err=%v", allowed, err)
	}

	// 另一个用户日期：主动 1 次 + 延后 1 次 = 当日合计 2 次，第二条延后链被频控拒绝。
	cappedPath := filepath.Join(t.TempDir(), "snooze-cap.db")
	capped := openIntegrationStore(t, cappedPath,
		seededSchedule{id: "schedule-cap-1", scheduledAt: now.Add(-time.Minute)},
		seededSchedule{id: "schedule-cap-2", scheduledAt: now.Add(-time.Minute), scheduleType: reminder.ScheduleSnooze},
	)
	defer func() { _ = capped.Close() }()
	sentAt := now
	for _, delivery := range []reminder.Delivery{
		{ID: "delivery-cap-1", DecisionID: "decision-1", ScheduleID: "schedule-cap-1", Channel: reminder.ChannelPush,
			IdempotencyKey: "user-passive_" + todayTaskDate() + "_push_decision-cap-1_1", AttemptNo: 1, Status: reminder.DeliverySent, SentAt: &sentAt},
		{ID: "delivery-cap-2", DecisionID: "decision-2", ScheduleID: "schedule-cap-2", Channel: reminder.ChannelPush,
			IdempotencyKey: "user-passive_" + todayTaskDate() + "_push_decision-cap-2_2", AttemptNo: 1, Status: reminder.DeliverySent, SentAt: &sentAt},
	} {
		if err := capped.UpdateDeliveryStatus(ctx, delivery); err != nil {
			t.Fatalf("seed delivery %s: %v", delivery.ID, err)
		}
	}
	usage, err := capped.GetDailyUsage(ctx, "user-passive", todayTaskDate())
	if err != nil || usage.PushSentCount != 1 || usage.SnoozeSentCount != 1 {
		t.Fatalf("expected both usage counters to be metered: %+v err=%v", usage, err)
	}
	result, err := snoozeServiceFor(capped, now, cappedPath).Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: "decision-1", RequestID: "snooze-cap-1"})
	if err != nil {
		t.Fatalf("snooze at the daily total: %v", err)
	}
	if result.Status != reminder.SnoozeRejected || result.ReasonCode != reminder.ReasonDailyCapReached {
		t.Fatalf("expected DAILY_CAP_REACHED at the daily total: %+v", result)
	}
}

// 免打扰与任务完成两个拒绝路径在真实装配下的端到端行为。
func TestSnoozeIntegrationRejectsQuietHoursAndCompletedTask(t *testing.T) {
	path := filepath.Join(t.TempDir(), "snooze-reject.db")
	now := time.Date(2026, 9, 20, 20, 45, 0, 0, time.UTC)
	store := openIntegrationStore(t, path, seededSchedule{id: "schedule-1", scheduledAt: now.Add(-time.Minute)})
	defer func() { _ = store.Close() }()
	ctx := context.Background()
	service := snoozeServiceFor(store, now, path)
	// fixture 的截止时间相对真实时间计算，固定时钟下改为显式给出紧截止时间，验证「无可用窗口」。
	estimated := 30
	service.Tasks = task.MemoryRepository{Tasks: map[string]reminder.DailyTask{
		task.Key("user-passive", todayTaskDate()): {
			UserID: "user-passive", TaskDate: todayTaskDate(), RequiredCount: 5, CompletedCount: 2,
			EstimatedMinutes: &estimated, Deadline: time.Date(2026, 9, 21, 2, 0, 0, 0, time.UTC),
		},
	}}
	quiet, err := service.Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: "decision-1", RequestID: "snooze-quiet"})
	if err != nil || quiet.Status != reminder.SnoozeRejected || quiet.ReasonCode != reminder.ReasonQuietHours {
		t.Fatalf("expected QUIET_HOURS: %+v err=%v", quiet, err)
	}
	service.Tasks = completedTasks("user-passive", todayTaskDate())
	completed, err := service.Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: "decision-1", RequestID: "snooze-completed"})
	if err != nil || completed.Status != reminder.SnoozeRejected || completed.ReasonCode != reminder.ReasonTaskCompleted {
		t.Fatalf("expected TASK_COMPLETED: %+v err=%v", completed, err)
	}
}

// CLI 入口：-snooze 分支输出 IDL 形状的结果，非法调用按错误返回。
func TestRunSnoozeBranchEndToEnd(t *testing.T) {
	path := filepath.Join(t.TempDir(), "snooze-cli.db")
	seedDueSchedule(t, path)
	var output bytes.Buffer
	if err := run([]string{"-snooze", "-decision", "decision-1", "-request-id", "snooze-cli", "-user", "user-passive", "-db", path}, &output); err != nil {
		t.Fatalf("snooze run: %v", err)
	}
	if !strings.Contains(output.String(), `"status": "SCHEDULED"`) || !strings.Contains(output.String(), `"schedule_type": "SNOOZE"`) {
		t.Fatalf("unexpected snooze output: %s", output.String())
	}
	// 同一 request_id 重放返回 REUSED，schedule_id 与首次一致。
	var firstID string
	if err := directQueryRow(t, path, `SELECT schedule_id FROM reminder_snooze_request WHERE request_id = ?`, []any{"snooze-cli"}, func(row *sql.Row) error {
		return row.Scan(&firstID)
	}); err != nil {
		t.Fatalf("read snooze request: %v", err)
	}
	output.Reset()
	if err := run([]string{"-snooze", "-decision", "decision-1", "-request-id", "snooze-cli", "-user", "user-passive", "-db", path}, &output); err != nil {
		t.Fatalf("replayed snooze run: %v", err)
	}
	if !strings.Contains(output.String(), `"status": "REUSED"`) || !strings.Contains(output.String(), firstID) {
		t.Fatalf("unexpected replayed output: %s", output.String())
	}
	// 换 request_id 的第二次入口是调用错误。
	if err := run([]string{"-snooze", "-decision", "decision-1", "-request-id", "snooze-cli-2", "-user", "user-passive", "-db", path}, &bytes.Buffer{}); err == nil {
		t.Fatal("expected the second entry to fail")
	}
	if err := run([]string{"-snooze", "-decision", "decision-1", "-db", path}, &bytes.Buffer{}); err == nil {
		t.Fatal("expected a missing request id to fail")
	}
}

func TestRunSnoozeBranchReportsInjectedFailures(t *testing.T) {
	oldSnooze, oldMarshal := snoozeReminder, marshalDecision
	t.Cleanup(func() { snoozeReminder, marshalDecision = oldSnooze, oldMarshal })
	snoozeReminder = func(snooze.Service, context.Context, snooze.Request) (snooze.Result, error) {
		return snooze.Result{}, errors.New("snooze injected")
	}
	if err := run([]string{"-snooze", "-decision", "decision-1", "-request-id", "snooze-1", "-db", filepath.Join(t.TempDir(), "snooze-error.db")}, &bytes.Buffer{}); err == nil {
		t.Fatal("expected the injected snooze error")
	}
	snoozeReminder = oldSnooze
	marshalDecision = func(any, string, string) ([]byte, error) { return nil, errors.New("marshal injected") }
	if err := run([]string{"-snooze", "-decision", "decision-1", "-request-id", "snooze-1", "-db", filepath.Join(t.TempDir(), "snooze-marshal.db")}, &bytes.Buffer{}); err == nil {
		t.Fatal("expected the injected marshal error on the snooze path")
	}
}
