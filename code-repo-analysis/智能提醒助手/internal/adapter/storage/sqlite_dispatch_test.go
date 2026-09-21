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

func seededStore(t *testing.T) (*Store, reminder.Decision, reminder.Schedule, time.Time) {
	t.Helper()
	store, err := Open(filepath.Join(t.TempDir(), "dispatch.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	ctx := context.Background()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	now := time.Date(2026, 9, 20, 19, 30, 0, 0, time.UTC)
	decision := reminder.Decision{
		ID: "decision-1", UserID: "user-passive", TaskDate: "2026-09-20", ShouldRemind: true,
		Channel: reminder.ChannelPush, ReasonCode: reminder.ReasonEligible, StrategyVersion: "v1",
		UserSegment: reminder.SegmentPassive, DedupeKey: "user-passive|2026-09-20|v1",
		Status: reminder.DecisionScheduled, Version: 1, CreatedAt: now, UpdatedAt: now,
	}
	schedule := reminder.Schedule{
		ID: "schedule-1", DecisionID: decision.ID, UserID: decision.UserID, TaskDate: decision.TaskDate,
		ScheduleVersion: 1, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleInitial,
		ScheduledAt: now.Add(-time.Minute), Status: reminder.ScheduleScheduled, CreatedAt: now, UpdatedAt: now,
	}
	if _, err := store.CreateDecisionAndSchedule(ctx, decision, &schedule); err != nil {
		t.Fatalf("create decision and schedule: %v", err)
	}
	return store, decision, schedule, now
}

func TestStoreListDueSchedulesFiltersStatusAndLimit(t *testing.T) {
	store, decision, _, now := seededStore(t)
	ctx := context.Background()
	future := reminder.Schedule{
		ID: "schedule-future", DecisionID: decision.ID, UserID: decision.UserID, TaskDate: decision.TaskDate,
		ScheduleVersion: 2, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleInitial,
		ScheduledAt: now.Add(time.Hour), Status: reminder.ScheduleScheduled, CreatedAt: now, UpdatedAt: now,
	}
	if _, err := store.CreateDecisionAndSchedule(ctx, decision, &future); err != nil {
		t.Fatalf("create future schedule: %v", err)
	}
	due, err := store.ListDueSchedules(ctx, now, 10)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(due) != 1 || due[0].ID != "schedule-1" || due[0].ScheduleType != reminder.ScheduleInitial {
		t.Fatalf("unexpected due schedules: %+v", due)
	}
	if due[0].AttemptNo != 0 {
		t.Fatalf("unexpected attempt number: %+v", due[0])
	}
	// 抢占后的排程不再是待发送对象。
	if _, err := store.ClaimSchedule(ctx, "schedule-1", now); err != nil {
		t.Fatalf("claim: %v", err)
	}
	due, err = store.ListDueSchedules(ctx, now, 10)
	if err != nil || len(due) != 0 {
		t.Fatalf("claimed schedules must leave the scan: %+v err=%v", due, err)
	}
	if err := store.Close(); err != nil {
		t.Fatalf("close: %v", err)
	}
	if _, err := store.ListDueSchedules(ctx, now, 10); err == nil {
		t.Fatal("expected a closed database error")
	}
}

func TestStoreClaimScheduleUsesLeaseAndConditionalUpdate(t *testing.T) {
	store, _, _, now := seededStore(t)
	ctx := context.Background()
	claimed, err := store.ClaimSchedule(ctx, "schedule-1", now)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	if claimed.Status != reminder.ScheduleClaimed || claimed.LeaseUntil == nil {
		t.Fatalf("unexpected claimed schedule: %+v", claimed)
	}
	// 默认租约时长取技术方案 4.7 的 lease_duration=2m。
	if claimed.LeaseUntil.UTC() != now.Add(2*time.Minute) {
		t.Fatalf("unexpected lease: %s", claimed.LeaseUntil)
	}
	// 并发抢占失败结束：第二次抢占同名排程返回条件失败，不重复调用渠道。
	if _, err := store.ClaimSchedule(ctx, "schedule-1", now); !errors.Is(err, port.ErrConditionFailed) {
		t.Fatalf("expected a conditional failure on the second claim: %v", err)
	}
	store.LeaseDuration = 30 * time.Second
	if err := store.UpdateSchedule(ctx, reminder.ScheduleUpdate{ScheduleID: "schedule-1", FromStatus: reminder.ScheduleClaimed, ToStatus: reminder.ScheduleScheduled, UpdatedAt: now}); err != nil {
		t.Fatalf("release: %v", err)
	}
	reclaimed, err := store.ClaimSchedule(ctx, "schedule-1", now)
	if err != nil {
		t.Fatalf("re-claim: %v", err)
	}
	if reclaimed.LeaseUntil == nil || reclaimed.LeaseUntil.UTC() != now.Add(30*time.Second) {
		t.Fatalf("unexpected configured lease: %+v", reclaimed.LeaseUntil)
	}
	// 未到期的排程不能被抢占。
	if _, err := store.ClaimSchedule(ctx, "schedule-missing", now); !errors.Is(err, port.ErrConditionFailed) {
		t.Fatalf("expected a conditional failure for an unknown schedule: %v", err)
	}
	store.Close()
	if _, err := store.ClaimSchedule(ctx, "schedule-1", now); err == nil {
		t.Fatal("expected a closed database error")
	}
}

func TestStoreUpdateSchedulePersistsStateAndCancelReason(t *testing.T) {
	store, _, _, now := seededStore(t)
	ctx := context.Background()
	if _, err := store.ClaimSchedule(ctx, "schedule-1", now); err != nil {
		t.Fatalf("claim: %v", err)
	}
	if err := store.UpdateSchedule(ctx, reminder.ScheduleUpdate{
		ScheduleID: "schedule-1", FromStatus: reminder.ScheduleClaimed, ToStatus: reminder.ScheduleSending, AttemptNo: 1, UpdatedAt: now,
	}); err != nil {
		t.Fatalf("advance to sending: %v", err)
	}
	if err := store.UpdateSchedule(ctx, reminder.ScheduleUpdate{
		ScheduleID: "schedule-1", FromStatus: reminder.ScheduleSending, ToStatus: reminder.ScheduleCancelled,
		AttemptNo: 1, CancelReason: reminder.ReasonDailyCapReached, UpdatedAt: now,
	}); err != nil {
		t.Fatalf("cancel: %v", err)
	}
	var status, cancelReason string
	var leaseUntil *string
	if err := store.db.QueryRowContext(ctx, `SELECT status, cancel_reason, lease_until FROM reminder_schedule WHERE id = ?`, "schedule-1").Scan(&status, &cancelReason, &leaseUntil); err != nil {
		t.Fatalf("read schedule: %v", err)
	}
	if status != string(reminder.ScheduleCancelled) || cancelReason != string(reminder.ReasonDailyCapReached) || leaseUntil != nil {
		t.Fatalf("unexpected persisted schedule: %s %s %v", status, cancelReason, leaseUntil)
	}
	// 条件更新失败即放弃本次动作，不覆盖已终态的排程。
	if err := store.UpdateSchedule(ctx, reminder.ScheduleUpdate{
		ScheduleID: "schedule-1", FromStatus: reminder.ScheduleSending, ToStatus: reminder.ScheduleSent, UpdatedAt: now,
	}); !errors.Is(err, port.ErrConditionFailed) {
		t.Fatalf("expected a conditional failure: %v", err)
	}
	store.Close()
	if err := store.UpdateSchedule(ctx, reminder.ScheduleUpdate{ScheduleID: "schedule-1", FromStatus: reminder.ScheduleSent, ToStatus: reminder.ScheduleSending}); err == nil {
		t.Fatal("expected a closed database error")
	}
}

func TestStoreDeliveryUpsertKeepsOneRecordPerIdempotencyKey(t *testing.T) {
	store, decision, schedule, now := seededStore(t)
	ctx := context.Background()
	delivery := reminder.Delivery{
		ID: "delivery-1", DecisionID: decision.ID, ScheduleID: schedule.ID, Channel: reminder.ChannelPush,
		IdempotencyKey: "user-passive_2026-09-20_push_decision-1_1", AttemptNo: 1, Status: reminder.DeliverySending,
	}
	if err := store.UpdateDeliveryStatus(ctx, delivery); err != nil {
		t.Fatalf("record attempt: %v", err)
	}
	sentAt := now.Add(time.Second)
	delivery.Status = reminder.DeliverySent
	delivery.ProviderCode = "mock"
	delivery.SentAt = &sentAt
	if err := store.UpdateDeliveryStatus(ctx, delivery); err != nil {
		t.Fatalf("record success: %v", err)
	}
	// 明确失败重试复用同一幂等键：只更新同一条记录，不新增第二条发送记录。
	delivery.AttemptNo = 2
	delivery.Status = reminder.DeliveryFailed
	delivery.ErrorCode = "CHANNEL_SEND_FAILED"
	if err := store.UpdateDeliveryStatus(ctx, delivery); err != nil {
		t.Fatalf("record retry failure: %v", err)
	}
	var rows, attemptNo int
	var status, errorCode, sent string
	if err := store.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM reminder_delivery`).Scan(&rows); err != nil {
		t.Fatalf("count deliveries: %v", err)
	}
	if err := store.db.QueryRowContext(ctx, `SELECT attempt_no, status, error_code, sent_at FROM reminder_delivery WHERE idempotency_key = ?`, delivery.IdempotencyKey).Scan(&attemptNo, &status, &errorCode, &sent); err != nil {
		t.Fatalf("read delivery: %v", err)
	}
	if rows != 1 || attemptNo != 2 || status != string(reminder.DeliveryFailed) || errorCode != "CHANNEL_SEND_FAILED" {
		t.Fatalf("unexpected delivery row: rows=%d attempt=%d status=%s error=%s", rows, attemptNo, status, errorCode)
	}
	// 首次成功时间在重试失败后仍保留。
	if sent == "" {
		t.Fatal("sent_at must be preserved across retries")
	}
	usage, err := store.GetDailyUsage(ctx, decision.UserID, decision.TaskDate)
	if err != nil {
		t.Fatalf("usage: %v", err)
	}
	if usage.PushSentCount != 1 {
		t.Fatalf("unexpected usage: %+v", usage)
	}
	store.Close()
	if err := store.UpdateDeliveryStatus(ctx, delivery); err == nil {
		t.Fatal("expected a closed database error")
	}
}

func TestStoreDailyUsageOnlyCountsInitialPush(t *testing.T) {
	store, decision, schedule, now := seededStore(t)
	ctx := context.Background()
	sentAt := now.Add(time.Second)
	// SNOOZE 排程与投递记录：用量独立计量，不计入系统主动上限。
	if err := store.UpdateSchedule(ctx, reminder.ScheduleUpdate{
		ScheduleID: schedule.ID, FromStatus: reminder.ScheduleScheduled, ToStatus: reminder.ScheduleSent, AttemptNo: 1, UpdatedAt: now,
	}); err != nil {
		t.Fatalf("mark initial sent: %v", err)
	}
	if err := store.UpdateDeliveryStatus(ctx, reminder.Delivery{
		ID: "delivery-initial", DecisionID: decision.ID, ScheduleID: schedule.ID, Channel: reminder.ChannelPush,
		IdempotencyKey: "user-passive_2026-09-20_push_decision-1_1", AttemptNo: 1, Status: reminder.DeliverySent, SentAt: &sentAt,
	}); err != nil {
		t.Fatalf("record initial delivery: %v", err)
	}
	if usage, err := store.GetDailyUsage(ctx, decision.UserID, decision.TaskDate); err != nil || usage.PushSentCount != 1 {
		t.Fatalf("unexpected usage after the initial push: %+v err=%v", usage, err)
	}
	snooze := reminder.Schedule{
		ID: "schedule-snooze", DecisionID: decision.ID, UserID: decision.UserID, TaskDate: decision.TaskDate,
		ScheduleVersion: 2, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleSnooze,
		ScheduledAt: now.Add(-time.Minute), Status: reminder.ScheduleScheduled, CreatedAt: now, UpdatedAt: now,
	}
	if _, err := store.CreateDecisionAndSchedule(ctx, decision, &snooze); err != nil {
		t.Fatalf("create snooze schedule: %v", err)
	}
	if err := store.UpdateDeliveryStatus(ctx, reminder.Delivery{
		ID: "delivery-snooze", DecisionID: decision.ID, ScheduleID: snooze.ID, Channel: reminder.ChannelPush,
		IdempotencyKey: "user-passive_2026-09-20_push_decision-1_2", AttemptNo: 1, Status: reminder.DeliverySent, SentAt: &sentAt,
	}); err != nil {
		t.Fatalf("record snooze delivery: %v", err)
	}
	usage, err := store.GetDailyUsage(ctx, decision.UserID, decision.TaskDate)
	if err != nil {
		t.Fatalf("usage: %v", err)
	}
	if usage.PushSentCount != 1 {
		t.Fatalf("snooze delivery must not consume the system cap: %+v", usage)
	}
}

func TestStoreReadsDecisionAndSurfacesFailures(t *testing.T) {
	store, decision, _, _ := seededStore(t)
	ctx := context.Background()
	loaded, err := store.GetDecision(ctx, decision.ID)
	if err != nil || loaded.StrategyVersion != "v1" || loaded.UserID != decision.UserID {
		t.Fatalf("unexpected decision: %+v err=%v", loaded, err)
	}
	if _, err := store.GetDecision(ctx, "missing"); err == nil {
		t.Fatal("expected an error for an unknown decision")
	}
	store.Close()
	if _, err := store.GetDecision(ctx, decision.ID); err == nil {
		t.Fatal("expected a closed database error")
	}
}

func TestScanScheduleParsesLeaseAndRejectsMalformedRows(t *testing.T) {
	now := time.Now().UTC()
	valid := now.Format(time.RFC3339Nano)
	row := nullableRow{values: []any{"schedule-1", "decision-1", "user-passive", "2026-09-20", 2, "push", "SNOOZE", valid, "CLAIMED", valid, 1, "DAILY_CAP_REACHED", valid, valid}}
	schedule, err := scanSchedule(row)
	if err != nil {
		t.Fatalf("scan schedule: %v", err)
	}
	if schedule.ScheduleType != reminder.ScheduleSnooze || schedule.Status != reminder.ScheduleClaimed ||
		schedule.LeaseUntil == nil || schedule.CancelReason != reminder.ReasonDailyCapReached || schedule.AttemptNo != 1 {
		t.Fatalf("unexpected schedule: %+v", schedule)
	}
	// 租约非法时保留为空，不影响其余字段解析。
	withoutLease := nullableRow{values: []any{"schedule-1", "decision-1", "user-passive", "2026-09-20", 1, "push", "INITIAL", valid, "SCHEDULED", nil, 0, nil, valid, valid}}
	parsed, err := scanSchedule(withoutLease)
	if err != nil {
		t.Fatalf("scan schedule without lease: %v", err)
	}
	if parsed.LeaseUntil != nil || parsed.CancelReason != "" {
		t.Fatalf("unexpected optional fields: %+v", parsed)
	}
	if _, err := scanSchedule(sqlmockRow{values: []any{"only-one"}}); err == nil {
		t.Fatal("expected a scan error for a malformed row")
	}
}

// nullableRow 是支持 NULL 的扫描桩，用于覆盖 scanSchedule 的可空字段分支。
type nullableRow struct{ values []any }

func (r nullableRow) Scan(dest ...any) error {
	if len(dest) != len(r.values) {
		return errors.New("scan arity mismatch")
	}
	for index, value := range r.values {
		switch target := dest[index].(type) {
		case *string:
			*target = value.(string)
		case *int:
			*target = value.(int)
		case *sql.NullString:
			if value == nil {
				target.Valid = false
				continue
			}
			target.Valid = true
			target.String = value.(string)
		default:
			return errors.New("unsupported scan target")
		}
	}
	return nil
}
