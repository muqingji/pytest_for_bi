package main

import (
	"bytes"
	"context"
	"database/sql"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/adapter/channel"
	"intelligent-reminder-assistant/internal/adapter/storage"
	"intelligent-reminder-assistant/internal/adapter/user"
	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/domain/reminder"
	_ "modernc.org/sqlite"
)

// 本文件是 FR-005 的模块集成测试：真实 SQLite 迁移 + 真实 dispatch 装配 + Mock Push 渠道。
// 断言覆盖持久化、状态流转、事件关联、重试与重复请求，不连接真实 Push、App 或事件总线。

type seededSchedule struct {
	id          string
	scheduledAt time.Time
}

func openIntegrationStore(t *testing.T, path string, schedules ...seededSchedule) *storage.Store {
	t.Helper()
	store, err := storage.Open(path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	ctx := context.Background()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	now := time.Now().UTC()
	taskDate := now.Format("2006-01-02")
	for index, seeded := range schedules {
		// 每条排程使用独立决策：唯一键是 (user_id, task_date, strategy_version)，
		// 重复写同一决策会替换其待发送排程，无法构造同一天的多条到期排程。
		strategyVersion := "v" + strconv.Itoa(index+1)
		decision := reminder.Decision{
			ID: "decision-" + strconv.Itoa(index+1), UserID: "user-passive", TaskDate: taskDate, ShouldRemind: true,
			Channel: reminder.ChannelPush, ReasonCode: reminder.ReasonEligible, StrategyVersion: strategyVersion,
			UserSegment: reminder.SegmentPassive, DedupeKey: "user-passive|" + taskDate + "|" + strategyVersion,
			Status: reminder.DecisionScheduled, Version: 1, CreatedAt: now, UpdatedAt: now,
		}
		schedule := &reminder.Schedule{
			ID: seeded.id, DecisionID: decision.ID, UserID: decision.UserID, TaskDate: decision.TaskDate,
			ScheduleVersion: 1, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleInitial,
			ScheduledAt: seeded.scheduledAt, Status: reminder.ScheduleScheduled, CreatedAt: now, UpdatedAt: now,
		}
		if _, err := store.CreateDecisionAndSchedule(ctx, decision, schedule); err != nil {
			t.Fatalf("seed %s: %v", seeded.id, err)
		}
	}
	return store
}

func integrationService(store *storage.Store, preferences user.MemoryRepository, push *channel.MockPushSender) dispatch.Service {
	return dispatch.Service{
		Reminders:       store,
		Preferences:     preferences,
		Renderer:        channel.PlaceholderRenderer{},
		Push:            push,
		Clock:           systemClock{},
		MaxPushPerDay:   1,
		MaxSendAttempts: 2,
		BatchSize:       50,
	}
}

func TestDispatchIntegrationStopsAtDailyCapWithinOneBatch(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cap.db")
	now := time.Now().UTC()
	store := openIntegrationStore(t, path,
		seededSchedule{id: "schedule-1", scheduledAt: now.Add(-2 * time.Minute)},
		seededSchedule{id: "schedule-2", scheduledAt: now.Add(-time.Minute)},
	)
	defer func() { _ = store.Close() }()
	push := &channel.MockPushSender{}
	counts, err := integrationService(store, fixtureUsers("user-passive"), push).DispatchDue(context.Background(), dispatch.Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	// AC-005：同一用户同一天只允许 1 次系统主动 Push，第二条排程被频控取消。
	if counts.Sent != 1 || counts.Cancelled != 1 {
		t.Fatalf("unexpected counts: %+v", counts)
	}
	if len(push.Requests()) != 1 {
		t.Fatalf("second system push must not reach the channel: %+v", push.Requests())
	}
	var status, cancelReason string
	if err := directQueryRow(t, path, `SELECT status, cancel_reason FROM reminder_schedule WHERE id = ?`, []any{"schedule-2"}, func(row *sql.Row) error {
		return row.Scan(&status, &cancelReason)
	}); err != nil {
		t.Fatalf("read cancelled schedule: %v", err)
	}
	if status != string(reminder.ScheduleCancelled) || cancelReason != string(reminder.ReasonDailyCapReached) {
		t.Fatalf("unexpected cancelled schedule: %s %s", status, cancelReason)
	}
	if records := countDeliveries(t, path); records != 1 {
		t.Fatalf("expected exactly one delivery record: %d", records)
	}
}

func TestDispatchIntegrationRetriesOnceAndKeepsSingleDelivery(t *testing.T) {
	path := filepath.Join(t.TempDir(), "retry.db")
	store := openIntegrationStore(t, path, seededSchedule{id: "schedule-1", scheduledAt: time.Now().UTC().Add(-time.Minute)})
	defer func() { _ = store.Close() }()
	push := &channel.MockPushSender{Results: []reminder.PushResult{
		{Status: string(reminder.DeliveryFailed), ErrorCode: "CHANNEL_SEND_FAILED"},
		{Status: string(reminder.DeliveryFailed), ErrorCode: "CHANNEL_SEND_FAILED"},
	}}
	counts, err := integrationService(store, fixtureUsers("user-passive"), push).DispatchDue(context.Background(), dispatch.Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	// AC-007：明确失败最多增加一次发送尝试，复用同一幂等键，不产生第二条业务提醒。
	if counts.Failed != 1 || counts.Retried != 1 || counts.Sent != 0 {
		t.Fatalf("unexpected counts: %+v", counts)
	}
	requests := push.Requests()
	if len(requests) != 2 || requests[0].IdempotencyKey != requests[1].IdempotencyKey {
		t.Fatalf("expected one retry with the same idempotency key: %+v", requests)
	}
	if records := countDeliveries(t, path); records != 1 {
		t.Fatalf("retry must not add a second delivery record: %d", records)
	}
	var status string
	var attemptNo int
	if err := directQueryRow(t, path, `SELECT status, attempt_no FROM reminder_delivery WHERE idempotency_key = ?`, []any{requests[0].IdempotencyKey}, func(row *sql.Row) error {
		return row.Scan(&status, &attemptNo)
	}); err != nil {
		t.Fatalf("read delivery: %v", err)
	}
	if status != string(reminder.DeliveryFailed) || attemptNo != 2 {
		t.Fatalf("unexpected delivery row: %s %d", status, attemptNo)
	}
	usage, err := store.GetDailyUsage(context.Background(), "user-passive", time.Now().UTC().Format("2006-01-02"))
	if err != nil || usage.PushSentCount != 0 {
		// 明确失败不算成功发送，因此不占用当日系统主动 Push 上限。
		t.Fatalf("failed send must not consume the cap: %+v err=%v", usage, err)
	}
}

func TestDispatchIntegrationSkipsChannelWhenPushUnauthorized(t *testing.T) {
	path := filepath.Join(t.TempDir(), "unauthorized.db")
	store := openIntegrationStore(t, path, seededSchedule{id: "schedule-1", scheduledAt: time.Now().UTC().Add(-time.Minute)})
	defer func() { _ = store.Close() }()
	push := &channel.MockPushSender{}
	preferences := user.MemoryRepository{Preferences: map[string]reminder.ReminderPreference{
		"user-passive": {ReminderEnabled: true, PushEnabled: false, DailyPushCap: 1, Timezone: "UTC"},
	}}
	counts, err := integrationService(store, preferences, push).DispatchDue(context.Background(), dispatch.Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Cancelled != 1 || counts.Sent != 0 || len(push.Requests()) != 0 {
		t.Fatalf("unauthorized push must be skipped: %+v requests=%+v", counts, push.Requests())
	}
	var status, cancelReason string
	if err := directQueryRow(t, path, `SELECT status, cancel_reason FROM reminder_schedule WHERE id = ?`, []any{"schedule-1"}, func(row *sql.Row) error {
		return row.Scan(&status, &cancelReason)
	}); err != nil {
		t.Fatalf("read schedule: %v", err)
	}
	if status != string(reminder.ScheduleCancelled) || cancelReason != string(reminder.ReasonNoAvailableChannel) {
		t.Fatalf("unexpected cancelled schedule: %s %s", status, cancelReason)
	}
	// 未触达原因随事件落库，供链路追溯。
	var eventCount int
	if err := directQueryRow(t, path, `SELECT COUNT(*) FROM reminder_event WHERE event_name = ?`, []any{"reminder_cancelled"}, func(row *sql.Row) error {
		return row.Scan(&eventCount)
	}); err != nil {
		t.Fatalf("count events: %v", err)
	}
	if eventCount != 1 {
		t.Fatalf("expected one cancellation event: %d", eventCount)
	}
}

func TestDispatchIntegrationRepeatedBatchThroughCLI(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cli.db")
	seedDueSchedule(t, path)
	var first bytes.Buffer
	if err := run([]string{"-dispatch", "-db", path}, &first); err != nil {
		t.Fatalf("first batch: %v", err)
	}
	if !strings.Contains(first.String(), `"Sent": 1`) {
		t.Fatalf("unexpected first batch output: %s", first.String())
	}
	var second bytes.Buffer
	if err := run([]string{"-dispatch", "-db", path}, &second); err != nil {
		t.Fatalf("second batch: %v", err)
	}
	// AC-006：重复调度不新增发送记录，第二次批次不再发送。
	if !strings.Contains(second.String(), `"Sent": 0`) {
		t.Fatalf("unexpected second batch output: %s", second.String())
	}
	if records := countDeliveries(t, path); records != 1 {
		t.Fatalf("repeated dispatch must keep one delivery record: %d", records)
	}
}

func countDeliveries(t *testing.T, path string) int {
	t.Helper()
	var count int
	if err := directQueryRow(t, path, `SELECT COUNT(*) FROM reminder_delivery`, nil, func(row *sql.Row) error {
		return row.Scan(&count)
	}); err != nil {
		t.Fatalf("count deliveries: %v", err)
	}
	return count
}

// directQueryRow 用第二个只读连接核对持久化结果，避免为测试新增生产读接口。
func directQueryRow(t *testing.T, path, query string, args []any, scan func(*sql.Row) error) error {
	t.Helper()
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return err
	}
	defer func() { _ = db.Close() }()
	return scan(db.QueryRow(query, args...))
}
