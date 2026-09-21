package user

import (
	"context"
	"errors"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

// reminderStub 只为满足 FixtureReminderRepository 的方法集：本用例只走 GetDailyUsage，
// 其余能力通过嵌入端口接口占位，避免为了一个取值方法去搭一整套仓储替身。
type reminderStub struct {
	port.ReminderRepository
	usage reminder.DailyUsage
	err   error
}

func (s reminderStub) GetDailyUsage(context.Context, string, string) (reminder.DailyUsage, error) {
	return s.usage, s.err
}

func (s reminderStub) CancelPendingSchedules(context.Context, string, string, reminder.ReasonCode, time.Time) ([]reminder.Schedule, error) {
	return nil, nil
}

func (s reminderStub) GetSnoozeRequest(context.Context, string, string) (reminder.SnoozeRequest, error) {
	return reminder.SnoozeRequest{}, nil
}

func (s reminderStub) CreateSnoozeSchedule(context.Context, reminder.SnoozeRequest, reminder.Schedule) (port.SnoozeCreateResult, error) {
	return port.SnoozeCreateResult{}, nil
}

// TestUsageOverlayAddsFixtureBaseline 覆盖用量叠加口径：种子表达服务启动前已发生的用量，
// 运行期新产生的用量仍从真实仓储统计，二者相加才是当日真实用量（4.3.3 的 DailyUsage）。
func TestUsageOverlayAddsFixtureBaseline(t *testing.T) {
	overlay := UsageOverlay{
		FixtureReminderRepository: reminderStub{usage: reminder.DailyUsage{PushSentCount: 1, SnoozeSentCount: 1}},
		Baseline: map[string]reminder.DailyUsage{
			"user-snoozed": {PushSentCount: 1, SnoozeSentCount: 1},
		},
	}

	usage, err := overlay.GetDailyUsage(context.Background(), "user-snoozed", "2026-09-20")
	if err != nil {
		t.Fatalf("daily usage: %v", err)
	}
	if usage.PushSentCount != 2 || usage.SnoozeSentCount != 2 {
		t.Fatalf("expected the fixture baseline to be added: %+v", usage)
	}

	// 未登记的用户按零值基线处理，不改变真实仓储的统计结果。
	unregistered, err := overlay.GetDailyUsage(context.Background(), "user-other", "2026-09-20")
	if err != nil {
		t.Fatalf("daily usage: %v", err)
	}
	if unregistered != (reminder.DailyUsage{PushSentCount: 1, SnoozeSentCount: 1}) {
		t.Fatalf("unregistered users must keep the persisted usage: %+v", unregistered)
	}
}

// TestUsageOverlayPropagatesRepositoryErrors 覆盖仓储读取失败：叠加层不吞错、不返回部分结果。
func TestUsageOverlayPropagatesRepositoryErrors(t *testing.T) {
	failure := errors.New("usage query failed")
	overlay := UsageOverlay{FixtureReminderRepository: reminderStub{err: failure}}
	if _, err := overlay.GetDailyUsage(context.Background(), "user-passive", "2026-09-20"); !errors.Is(err, failure) {
		t.Fatalf("expected the repository error to surface, got %v", err)
	}
}
