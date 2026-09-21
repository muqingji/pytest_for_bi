package user

import (
	"context"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

// FixtureReminderRepository 是本地 Fixture 装配所需的仓储能力集合：评估与发送依赖的 ReminderRepository、
// 拒绝路径取消未发送排程的 CancelPendingSchedules（FR-003、FR-004）、延后幂等记录的读写（FR-007）。
// 方法显式列出而不层层嵌入端口，避免同一端口被嵌入两次导致方法集歧义；生产实现是 adapter/storage 的 SQLite Store。
type FixtureReminderRepository interface {
	port.ReminderRepository
	CancelPendingSchedules(ctx context.Context, userID, taskDate string, reason reminder.ReasonCode, now time.Time) ([]reminder.Schedule, error)
	GetSnoozeRequest(ctx context.Context, requestID, decisionID string) (reminder.SnoozeRequest, error)
	CreateSnoozeSchedule(ctx context.Context, request reminder.SnoozeRequest, schedule reminder.Schedule) (port.SnoozeCreateResult, error)
}

// UsageOverlay 把 Fixture 的「当天已存在用量」叠加到真实仓储的当日统计之上，只用于本地种子装配。
// 叠加而不是覆盖：种子表达服务启动前已经发生的用量，测试期间新产生的用量仍从库里统计，二者相加才是当日真实用量
// （技术方案 4.3.3 的 DailyUsage 口径，评估、dispatch 与 snooze 三条路径必须读到同一份事实）。
type UsageOverlay struct {
	FixtureReminderRepository
	// Baseline 按 user_id 提供种子用量；未登记的用户按零值处理。
	Baseline map[string]reminder.DailyUsage
}

func (o UsageOverlay) GetDailyUsage(ctx context.Context, userID, taskDate string) (reminder.DailyUsage, error) {
	usage, err := o.FixtureReminderRepository.GetDailyUsage(ctx, userID, taskDate)
	if err != nil {
		return reminder.DailyUsage{}, err
	}
	baseline := o.Baseline[userID]
	usage.PushSentCount += baseline.PushSentCount
	usage.SnoozeSentCount += baseline.SnoozeSentCount
	return usage, nil
}
