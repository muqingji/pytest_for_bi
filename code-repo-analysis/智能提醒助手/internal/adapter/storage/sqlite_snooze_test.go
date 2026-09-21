package storage

import (
	"context"
	"database/sql"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

// snoozeFixture 构造一条带 INITIAL 排程的决策，作为延后路径的持久化前置事实。
func snoozeFixture(now time.Time) (reminder.Decision, *reminder.Schedule) {
	decision := reminder.Decision{
		ID: "decision-snooze", UserID: "user-snooze", TaskDate: "2026-09-20", ShouldRemind: true,
		Channel: reminder.ChannelPush, ReasonCode: reminder.ReasonEligible, StrategyVersion: "v1",
		UserSegment: reminder.SegmentPassive, DedupeKey: "user-snooze|2026-09-20|v1",
		Status: reminder.DecisionScheduled, Version: 1, CreatedAt: now, UpdatedAt: now,
	}
	schedule := &reminder.Schedule{
		ID: "schedule-initial", DecisionID: decision.ID, UserID: decision.UserID, TaskDate: decision.TaskDate,
		ScheduleVersion: 1, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleInitial,
		ScheduledAt: now.Add(time.Hour), Status: reminder.ScheduleScheduled, CreatedAt: now, UpdatedAt: now,
	}
	return decision, schedule
}

func openSnoozeStore(t *testing.T) (*Store, reminder.Decision, *reminder.Schedule) {
	t.Helper()
	store, err := Open(filepath.Join(t.TempDir(), "snooze.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if err := store.Migrate(context.Background()); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	decision, schedule := snoozeFixture(time.Now().UTC())
	if _, err := store.CreateDecisionAndSchedule(context.Background(), decision, schedule); err != nil {
		t.Fatalf("seed decision: %v", err)
	}
	return store, decision, schedule
}

func snoozeRequestAt(schedule reminder.Schedule, now time.Time) reminder.SnoozeRequest {
	return reminder.SnoozeRequest{
		RequestID: "snooze-1", DecisionID: schedule.DecisionID, ScheduleID: schedule.ID,
		UserID: schedule.UserID, TaskDate: schedule.TaskDate, CreatedAt: now,
	}
}

func snoozeScheduleFor(decision reminder.Decision, now time.Time) reminder.Schedule {
	return reminder.Schedule{
		ID: "schedule-snooze", DecisionID: decision.ID, UserID: decision.UserID, TaskDate: decision.TaskDate,
		ScheduleVersion: 2, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleSnooze,
		ScheduledAt: now.Add(time.Hour), Status: reminder.ScheduleScheduled, CreatedAt: now, UpdatedAt: now,
	}
}

// 用量口径：INITIAL 计入系统主动上限，SNOOZE 独立计量但计入合计（AC-013）。
func TestStoreCountsSnoozeUsageAndReadsLatestSchedule(t *testing.T) {
	store, decision, initial := openSnoozeStore(t)
	defer func() { _ = store.Close() }()
	ctx := context.Background()
	now := time.Now().UTC()
	sentAt := now

	latest, err := store.GetLatestScheduleByDecision(ctx, decision.ID)
	if err != nil || latest.ID != initial.ID || latest.ScheduleType != reminder.ScheduleInitial {
		t.Fatalf("unexpected latest schedule: %+v err=%v", latest, err)
	}
	if err := store.UpdateDeliveryStatus(ctx, reminder.Delivery{
		ID: "delivery-initial", DecisionID: decision.ID, ScheduleID: initial.ID, Channel: reminder.ChannelPush,
		IdempotencyKey: reminder.DeliveryIdempotencyKey(*initial), AttemptNo: 1, Status: reminder.DeliverySent, SentAt: &sentAt,
	}); err != nil {
		t.Fatalf("record initial delivery: %v", err)
	}
	usage, err := store.GetDailyUsage(ctx, decision.UserID, decision.TaskDate)
	if err != nil || usage != (reminder.DailyUsage{PushSentCount: 1}) {
		t.Fatalf("unexpected usage after the system push: %+v err=%v", usage, err)
	}

	snooze := snoozeScheduleFor(decision, now)
	created, err := store.CreateSnoozeSchedule(ctx, snoozeRequestAt(snooze, now), snooze)
	if err != nil || created.Reused {
		t.Fatalf("create snooze schedule: result=%+v err=%v", created, err)
	}
	if err := store.UpdateDeliveryStatus(ctx, reminder.Delivery{
		ID: "delivery-snooze", DecisionID: decision.ID, ScheduleID: snooze.ID, Channel: reminder.ChannelPush,
		IdempotencyKey: reminder.DeliveryIdempotencyKey(snooze), AttemptNo: 1, Status: reminder.DeliverySent, SentAt: &sentAt,
	}); err != nil {
		t.Fatalf("record snooze delivery: %v", err)
	}
	usage, err = store.GetDailyUsage(ctx, decision.UserID, decision.TaskDate)
	if err != nil || usage.PushSentCount != 1 || usage.SnoozeSentCount != 1 {
		t.Fatalf("expected snooze usage to be metered separately: %+v err=%v", usage, err)
	}
	latest, err = store.GetLatestScheduleByDecision(ctx, decision.ID)
	if err != nil || latest.ID != snooze.ID || latest.ScheduleVersion != 2 || latest.ScheduleType != reminder.ScheduleSnooze {
		t.Fatalf("expected the snooze schedule to be the latest: %+v err=%v", latest, err)
	}
	record, err := store.GetSnoozeRequest(ctx, "snooze-1", decision.ID)
	if err != nil || record.ScheduleID != snooze.ID || record.UserID != decision.UserID || !record.CreatedAt.Equal(now) {
		t.Fatalf("unexpected snooze request record: %+v err=%v", record, err)
	}
}

func TestStoreSnoozeLookupsReportMissingRecords(t *testing.T) {
	store, decision, _ := openSnoozeStore(t)
	ctx := context.Background()
	if _, err := store.GetLatestScheduleByDecision(ctx, "missing"); !errors.Is(err, port.ErrNotFound) {
		t.Fatalf("expected ErrNotFound for an unknown decision: %v", err)
	}
	if _, err := store.GetSnoozeRequest(ctx, "missing", decision.ID); !errors.Is(err, port.ErrNotFound) {
		t.Fatalf("expected ErrNotFound for an unknown snooze request: %v", err)
	}
	_ = store.Close()
	// 依赖错误必须与「不存在」可区分：snooze 对前者返回依赖错误，对后者返回 DECISION_NOT_FOUND。
	if _, err := store.GetLatestScheduleByDecision(ctx, decision.ID); err == nil || errors.Is(err, port.ErrNotFound) {
		t.Fatalf("expected a dependency error for a closed database: %v", err)
	}
	if _, err := store.GetSnoozeRequest(ctx, "snooze-1", decision.ID); err == nil || errors.Is(err, port.ErrNotFound) {
		t.Fatalf("expected a dependency error for a closed database: %v", err)
	}
	// 幂等冲突后的回读路径同样要区分依赖错误与「未命中」。
	if _, err := store.readExistingSnoozeAfterConflict(ctx, reminder.SnoozeRequest{RequestID: "snooze-1", DecisionID: decision.ID}); err == nil || errors.Is(err, port.ErrNotFound) {
		t.Fatalf("expected a dependency error while re-reading after conflict: %v", err)
	}
}

// 同一 request_id 重复调用只产生一条幂等记录与一条 SNOOZE 排程（AC-013）。
func TestStoreCreateSnoozeScheduleIsIdempotent(t *testing.T) {
	store, decision, _ := openSnoozeStore(t)
	defer func() { _ = store.Close() }()
	ctx := context.Background()
	now := time.Now().UTC()
	snooze := snoozeScheduleFor(decision, now)
	first, err := store.CreateSnoozeSchedule(ctx, snoozeRequestAt(snooze, now), snooze)
	if err != nil || first.Reused {
		t.Fatalf("first create: result=%+v err=%v", first, err)
	}
	second, err := store.CreateSnoozeSchedule(ctx, snoozeRequestAt(snooze, now), snooze)
	if err != nil || !second.Reused || second.Schedule.ID != snooze.ID {
		t.Fatalf("duplicate create must reuse the first schedule: result=%+v err=%v", second, err)
	}
	var requests, schedules int
	if err := store.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM reminder_snooze_request`).Scan(&requests); err != nil {
		t.Fatalf("count snooze requests: %v", err)
	}
	if err := store.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM reminder_schedule WHERE schedule_type = 'SNOOZE'`).Scan(&schedules); err != nil {
		t.Fatalf("count snooze schedules: %v", err)
	}
	if requests != 1 || schedules != 1 {
		t.Fatalf("duplicate snooze must not create new rows: requests=%d schedules=%d", requests, schedules)
	}
}

// 并发/异常下由 (decision_id, schedule_version) 唯一键拦截：换 request_id 的写入返回已有排程。
func TestStoreCreateSnoozeScheduleReusesExistingScheduleOnVersionConflict(t *testing.T) {
	store, decision, _ := openSnoozeStore(t)
	defer func() { _ = store.Close() }()
	ctx := context.Background()
	now := time.Now().UTC()
	snooze := snoozeScheduleFor(decision, now)
	if _, err := store.CreateSnoozeSchedule(ctx, snoozeRequestAt(snooze, now), snooze); err != nil {
		t.Fatalf("seed snooze schedule: %v", err)
	}
	other := snoozeRequestAt(snooze, now)
	other.RequestID = "snooze-2"
	conflicted, err := store.CreateSnoozeSchedule(ctx, other, snooze)
	if err != nil || !conflicted.Reused || conflicted.Schedule.ID != snooze.ID {
		t.Fatalf("expected the unique key to reuse the existing schedule: result=%+v err=%v", conflicted, err)
	}
}

// 幂等记录的插入冲突同样落到回读路径：写入被触发器拒绝后返回既有排程。
func TestStoreCreateSnoozeScheduleReusesScheduleOnRequestConflict(t *testing.T) {
	store, decision, _ := openSnoozeStore(t)
	defer func() { _ = store.Close() }()
	ctx := context.Background()
	now := time.Now().UTC()
	snooze := snoozeScheduleFor(decision, now)
	// 先写一条与请求幂等键无关的 SNOOZE 排程，使回读路径能取到既有排程。
	seed := snooze
	seed.ID = "schedule-snooze-seed"
	if _, err := store.db.ExecContext(ctx, `INSERT INTO reminder_schedule (id, decision_id, user_id, task_date, schedule_version, channel, schedule_type, scheduled_at, status, attempt_no, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		seed.ID, seed.DecisionID, seed.UserID, seed.TaskDate, seed.ScheduleVersion, string(seed.Channel), string(seed.ScheduleType), seed.ScheduledAt.UTC().Format(time.RFC3339Nano), string(seed.Status), seed.AttemptNo, seed.CreatedAt.UTC().Format(time.RFC3339Nano), seed.UpdatedAt.UTC().Format(time.RFC3339Nano)); err != nil {
		t.Fatalf("seed snooze schedule: %v", err)
	}
	if _, err := store.db.ExecContext(ctx, `CREATE TRIGGER force_snooze_unique BEFORE INSERT ON reminder_snooze_request BEGIN SELECT RAISE(ABORT, 'UNIQUE conflict'); END;`); err != nil {
		t.Fatalf("create conflict trigger: %v", err)
	}
	result, err := store.CreateSnoozeSchedule(ctx, snoozeRequestAt(seed, now), snooze)
	if err != nil || !result.Reused || result.Schedule.ID != seed.ID {
		t.Fatalf("expected the request unique key to reuse the existing schedule: result=%+v err=%v", result, err)
	}
}

func TestStoreCreateSnoozeScheduleReportsFailures(t *testing.T) {
	ctx := context.Background()
	now := time.Now().UTC()
	decision, initial := snoozeFixture(now)
	snooze := snoozeScheduleFor(decision, now)

	// 预检查（读幂等记录）依赖错误：关闭数据库后直接返回错误，不进入写事务。
	closed, _, _ := openSnoozeStore(t)
	_ = closed.Close()
	if _, err := closed.CreateSnoozeSchedule(ctx, snoozeRequestAt(snooze, now), snooze); err == nil {
		t.Fatal("expected the pre-check to surface a dependency error")
	}

	// 开启事务失败。
	beginStore, _, _ := openSnoozeStore(t)
	defer func() { _ = beginStore.Close() }()
	oldBegin := beginSnooze
	beginSnooze = func(*sql.DB, context.Context) (*sql.Tx, error) { return nil, errors.New("begin snooze failed") }
	if _, err := beginStore.CreateSnoozeSchedule(ctx, snoozeRequestAt(snooze, now), snooze); err == nil {
		t.Fatal("expected a begin transaction error")
	}
	beginSnooze = oldBegin

	// 排程表缺失：插入排程返回非唯一键错误。
	noTable, _, _ := openSnoozeStore(t)
	defer func() { _ = noTable.Close() }()
	if _, err := noTable.db.ExecContext(ctx, `DROP TABLE reminder_schedule`); err != nil {
		t.Fatalf("drop schedule table: %v", err)
	}
	if _, err := noTable.CreateSnoozeSchedule(ctx, snoozeRequestAt(snooze, now), snooze); err == nil {
		t.Fatal("expected a schedule insert error")
	}

	// 幂等记录表缺失：排程写入成功后幂等记录插入失败，事务回滚。
	noRequest, _, _ := openSnoozeStore(t)
	defer func() { _ = noRequest.Close() }()
	if _, err := noRequest.db.ExecContext(ctx, `DROP TABLE reminder_snooze_request`); err != nil {
		t.Fatalf("drop snooze request table: %v", err)
	}
	if _, err := noRequest.CreateSnoozeSchedule(ctx, snoozeRequestAt(snooze, now), snooze); err == nil {
		t.Fatal("expected a snooze request insert error")
	}

	// 提交失败：事务回滚，幂等记录与排程都不落库。
	commitStore, commitDecision, _ := openSnoozeStore(t)
	defer func() { _ = commitStore.Close() }()
	commitSchedule := snoozeScheduleFor(commitDecision, now)
	cancelCtx, cancel := context.WithCancel(ctx)
	beforeSnoozeCommit = cancel
	if _, err := commitStore.CreateSnoozeSchedule(cancelCtx, snoozeRequestAt(commitSchedule, now), commitSchedule); err == nil {
		t.Fatal("expected a commit error")
	}
	beforeSnoozeCommit = nil
	var count int
	if err := commitStore.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM reminder_snooze_request`).Scan(&count); err != nil {
		t.Fatalf("count snooze requests after rollback: %v", err)
	}
	if count != 0 {
		t.Fatalf("a failed commit must not leave a request record: %d", count)
	}
	_ = initial
}
